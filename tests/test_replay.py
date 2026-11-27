from io import BytesIO
import json

import pytest

from radar.acquisition import SerialSettings, record_serial, record_stream
from radar.replay import replay, synthetic_packet


def test_binary_and_timestamp_round_trip(tmp_path):
    data = synthetic_packet(0) + synthetic_packet(1)
    recording = tmp_path / "capture"
    source = BytesIO(data)
    count = record_stream(
        source, recording, metadata={"data_port": "fake"},
        stop=lambda: source.tell() == len(data),
    )
    assert count == len(data)
    assert (recording / "data.bin").read_bytes() == data
    header, chunk, footer = map(json.loads, (recording / "index.jsonl").read_text().splitlines())
    assert header["metadata"] == {"data_port": "fake"}
    assert header["started_utc"].endswith("+00:00")
    assert footer == {"status": "complete", "bytes": count}
    frames = list(replay(recording))
    assert [sample.frame.header.frame_number for sample in frames] == [0, 1]
    assert [sample.seconds for sample in frames] == [chunk["elapsed_ns"] / 1e9] * 2
    assert [sample.seconds for sample in replay(recording, frame_period=0.1)] == [0, 0.1]
    with pytest.raises(FileExistsError):
        record_stream(BytesIO(), recording, metadata={})


def test_bare_capture_requires_frame_period(tmp_path):
    path = tmp_path / "uart.bin"
    path.write_bytes(synthetic_packet(0) + synthetic_packet(1))
    with pytest.raises(ValueError, match="frame period"):
        list(replay(path))
    assert [sample.seconds for sample in replay(path, frame_period=0.05)] == [0, 0.05]


def test_truncated_capture_is_reported(tmp_path):
    path = tmp_path / "capture"
    path.mkdir()
    (path / "data.bin").write_bytes(b"a")
    (path / "index.jsonl").write_text('{"format": 1}\n{"offset":0,"size":2,"elapsed_ns":0}\n')
    with pytest.raises(ValueError, match="truncated"):
        list(replay(path))


def test_interrupted_capture_preserves_bytes(tmp_path):
    class InterruptedStream:
        def __init__(self):
            self.stream = BytesIO(synthetic_packet(0))

        def read(self, size):
            data = self.stream.read(size)
            if not data:
                raise KeyboardInterrupt
            return data

    path = tmp_path / "capture"
    record_stream(InterruptedStream(), path, metadata={})
    footer = json.loads((path / "index.jsonl").read_text().splitlines()[-1])
    assert footer["status"] == "interrupted"
    assert len(list(replay(path))) == 1


def test_mock_serial_ports_and_firmware_configuration(tmp_path, monkeypatch):
    import serial

    opened = []
    data = synthetic_packet(0)

    class MockSerial:
        def __init__(self, port, baudrate, **kwargs):
            self.port = port
            self.sent = []
            self.closed = False
            self.source = BytesIO(data)
            assert baudrate == (921600 if port == "DATA" else 115200)
            opened.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True

        def reset_input_buffer(self):
            pass

        def write(self, command):
            self.sent.append(command)

        def readline(self, size):
            return b"Done\n"

        def read(self, size):
            packet = self.source.read(size)
            if not packet:
                raise KeyboardInterrupt
            return packet

    monkeypatch.setattr(serial, "Serial", MockSerial)
    config = tmp_path / "test.cfg"
    config.write_text("% comment\nsensorStop\nsensorStart\n")
    capture = tmp_path / "capture"
    count = record_serial(
        SerialSettings("DATA", 921600, "CONTROL", 115200), capture, config=config,
    )
    assert count == len(data)
    assert opened[1].sent == [b"sensorStop\n", b"sensorStart\n"]
    assert all(port.closed for port in opened)
    assert len(list(replay(capture))) == 1


def test_replay_recovers_at_eof(tmp_path):
    from struct import pack, pack_into

    from radar.decoder import StreamDecoder

    incomplete = bytearray(synthetic_packet(0)[:40])
    pack_into("<I", incomplete, 12, 4096)
    pack_into("<I", incomplete, 32, 1)
    incomplete += pack("<II", 9000, 4096 - 48)
    path = tmp_path / "truncated.bin"
    path.write_bytes(incomplete + synthetic_packet(1))
    decoder = StreamDecoder()
    (sample,) = replay(path, frame_period=0.1, decoder=decoder)
    assert sample.frame.header.frame_number == 1
    assert decoder.truncated_packets == 1


def test_replay_reports_truncated_final_frame(tmp_path):
    from radar.decoder import StreamDecoder

    path = tmp_path / "truncated.bin"
    path.write_bytes(synthetic_packet(0) + synthetic_packet(1)[:75])
    decoder = StreamDecoder()
    (sample,) = replay(path, frame_period=0.1, decoder=decoder)
    assert sample.frame.header.frame_number == 0
    assert decoder.truncated_packets == 1
    assert decoder.pending_bytes == 0
