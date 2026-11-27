from math import cos, sin
from struct import pack, pack_into

import pytest

from radar.decoder import StreamDecoder

MAGIC = bytes.fromhex("02 01 04 03 06 05 08 07")


def packet(*items, points=0, number=42, inclusive=False, padded=True):
    """Build test bytes independently of the production struct definitions."""
    body = b"".join(
        pack("<II", identifier, len(value) + (8 if inclusive else 0)) + value
        for identifier, value in items
    )
    padding = bytes(-(40 + len(body)) % 32) if padded else b""
    return MAGIC + pack(
        "<8I", 0x03060000, 40 + len(body) + len(padding), 0xA6843,
        number, 123, points, len(items), 0,
    ) + body + padding


@pytest.mark.parametrize("inclusive", [False, True])
def test_all_tlvs(inclusive):
    cloud = pack("<5f", 0.01, 0.02, 0.125, 0.001, 0.5) + pack("<bbhHH", -25, 15, -80, 40000, 50000)
    targets = pack("<I27f", 7, *range(1, 28))
    data = packet(
        (1020, cloud), (1010, targets), (1011, bytes([7, 253, 254, 255])),
        (1012, pack("<Iff", 7, 1.75, 0.5)), (1021, pack("<I", 1)),
        (9876, b"unrecognised"), points=1, inclusive=inclusive,
    )
    decoder = StreamDecoder(length_mode="inclusive" if inclusive else "payload")
    (frame,) = decoder.feed(data)
    assert (frame.header.frame_number, frame.header.total_length, frame.header.cpu_cycles) == (42, len(data), 123)
    (point,) = frame.points
    assert point.position == pytest.approx((
        40 * cos(-0.25) * sin(0.3), 40 * cos(-0.25) * cos(0.3), 40 * sin(-0.25)
    ))
    assert (point.doppler, point.snr) == (-10, 25000)
    (target,) = frame.targets
    assert (target.track_id, target.position, target.velocity, target.acceleration) == (
        7, (1, 2, 3), (4, 5, 6), (7, 8, 9)
    )
    assert target.covariance == tuple(range(10, 26))
    assert (target.gain, target.confidence) == (26, 27)
    (height,) = frame.heights
    assert (height.track_id, height.max_z, height.min_z) == (7, 1.75, 0.5)
    assert frame.previous_point_target_ids == bytes([7, 253, 254, 255])
    assert frame.presence is True
    assert frame.unknown_tlv_types == (9876,)


def test_fragmentation_and_concatenation():
    data = packet((1021, pack("<I", 0)), padded=False)
    for split in range(len(data)):
        decoder = StreamDecoder()
        assert not decoder.feed(data[:split])
        frames = decoder.feed(data[split:] + data)
        assert len(frames) == 2
        assert frames[0].presence is False
        assert decoder.pending_bytes == 0


@pytest.mark.parametrize(("offset", "value"), [(12, 12), (12, 999999), (32, 99), (12, 1024)])
def test_resync_after_bad_header(offset, value):
    bad = bytearray(packet())
    pack_into("<I", bad, offset, value)
    decoder = StreamDecoder(max_packet_size=2048)
    data = bytes(bad) + packet(number=43)
    recovered = [frame for byte in data for frame in decoder.feed(bytes([byte]))]
    assert [frame.header.frame_number for frame in recovered] == [43]
    assert decoder.rejected_packets == 1


def test_truncated_header_then_recovery():
    decoder = StreamDecoder()
    assert not decoder.feed(packet()[:17])
    (frame,) = decoder.feed(packet(number=8))
    assert frame.header.frame_number == 8


@pytest.mark.parametrize("item", [
    (1020, bytes(20)),
    (1020, pack("<5f", 1, 1, 1, 1, 1) + b"short"),
    (1010, b"short"),
    (1012, pack("<Iff", 7, 0.5, 1.75)),
    (1012, pack("<Iff", 7, float("nan"), 0)),
    (1021, pack("<I", 7)),
    (1021, b""),
])
def test_rejects_malformed_tlv_payload(item):
    decoder = StreamDecoder()
    frames = decoder.feed(packet(item) + packet(number=5))
    assert [frame.header.frame_number for frame in frames] == [5]
    assert decoder.rejected_packets == 1


def test_tlv_length_crossing_packet_boundary():
    decoder = StreamDecoder()
    bad = bytearray(packet((1021, pack("<I", 1))))
    pack_into("<I", bad, 44, 10000)
    assert not decoder.feed(bad)
    assert decoder.rejected_packets == 1


def test_inclusive_length_underflow():
    decoder = StreamDecoder(length_mode="inclusive")
    bad = bytearray(packet((1021, pack("<I", 1)), inclusive=True))
    pack_into("<I", bad, 44, 7)
    assert not decoder.feed(bad)
    assert decoder.rejected_packets == 1


def test_buffer_remains_bounded_and_keeps_partial_magic():
    decoder = StreamDecoder(max_packet_size=1024)
    valid = packet()
    assert not decoder.feed(b"x" * 1_000_000 + valid[:4])
    assert decoder.pending_bytes < len(MAGIC)
    assert len(decoder.feed(valid[4:])) == 1
    assert decoder.discarded_bytes == 1_000_000


def test_embedded_frame_bytes_never_preempt_valid_packet():
    inner = packet(number=123)
    outer = packet((9000, inner + b"tail"), number=42)
    for split in range(len(outer)):
        decoder = StreamDecoder()
        assert not decoder.feed(outer[:split])
        frames = decoder.feed(outer[split:])
        assert [frame.header.frame_number for frame in frames] == [42]
        assert decoder.rejected_packets == 0


def test_rejects_impossible_tlv_layout_before_full_packet_arrives():
    bad = bytearray(packet((1021, pack("<I", 1))))
    pack_into("<I", bad, 12, 1024)
    pack_into("<I", bad, 44, 6)
    decoder = StreamDecoder()
    (frame,) = decoder.feed(bad[:48] + packet(number=43))
    assert frame.header.frame_number == 43
    assert decoder.rejected_packets == 1


def test_finish_salvages_complete_frame_after_plausible_truncation():
    interrupted = packet((9000, bytes(1024)))
    decoder = StreamDecoder()
    assert not decoder.feed(interrupted[:60] + packet(number=43))
    (frame,) = decoder.finish()
    assert frame.header.frame_number == 43
    assert decoder.truncated_packets == 1
    assert decoder.discarded_bytes == 60
    assert decoder.pending_bytes == 0
    assert decoder.finish() == []


@pytest.mark.parametrize("kind, record", [
    (1010, pack("<I27f", 7, *range(1, 28))),
    (1012, pack("<Iff", 7, 1.75, 0.5)),
])
def test_rejects_duplicate_track_records(kind, record):
    decoder = StreamDecoder()
    assert not decoder.feed(packet((kind, record * 2)))
    assert decoder.rejected_packets == 1


def test_nonzero_padding_is_opaque():
    data = bytearray(packet((1021, pack("<I", 1))))
    data[52:] = b"p" * (len(data) - 52)
    decoder = StreamDecoder()
    (frame,) = decoder.feed(data)
    assert frame.presence is True
    assert decoder.discarded_bytes == 0
