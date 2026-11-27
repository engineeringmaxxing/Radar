"""Serial discovery and timestamped, byte-exact capture."""

from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import monotonic_ns
from typing import BinaryIO

MAX_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class SerialSettings:
    data_port: str
    data_baud: int
    control_port: str | None = None
    control_baud: int | None = None

    def __post_init__(self) -> None:
        if not self.data_port or self.data_baud <= 0:
            raise ValueError("Provide a data port and a positive baud rate")
        if (self.control_port is None) != (self.control_baud is None):
            raise ValueError("Provide both the control port and control baud rate")
        if self.control_baud is not None and self.control_baud <= 0:
            raise ValueError("Control baud must be positive")
        if self.control_port is not None and self.control_port.casefold() == self.data_port.casefold():
            raise ValueError("Control and data ports must be distinct")


def discover_ports() -> list[tuple[str, str, str]]:
    from serial.tools.list_ports import comports

    return [(port.device, port.description, port.hwid) for port in sorted(comports())]


def record_stream(
    stream: BinaryIO,
    directory: Path,
    *,
    metadata: dict[str, object],
    stop=None,
    duration: float | None = None,
) -> int:
    """Capture until stopped. Empty serial reads indicate a timeout."""
    directory.mkdir(parents=True, exist_ok=False)
    start = monotonic_ns()
    offset = 0
    status = "complete"
    with (directory / "data.bin").open("xb") as raw, (
        directory / "index.jsonl"
    ).open("x", encoding="utf-8") as index:
        def log(entry: dict) -> None:
            index.write(json.dumps(entry, allow_nan=False) + "\n")
            index.flush()

        log({
            "format": 1,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
        })
        try:
            while stop is None or not stop():
                if duration is not None and monotonic_ns() - start >= duration * 1e9:
                    break
                chunk = stream.read(MAX_CHUNK_SIZE)
                timestamp = monotonic_ns() - start
                if not chunk:
                    continue
                raw.write(chunk)
                raw.flush()
                log({"offset": offset, "size": len(chunk), "elapsed_ns": timestamp})
                offset += len(chunk)
        except KeyboardInterrupt:
            status = "interrupted"
        except Exception:
            status = "error"
            raise
        finally:
            log({"status": status, "bytes": offset})
    return offset


def record_serial(
    settings: SerialSettings, directory: Path, *,
    config: Path | None = None, duration: float | None = None,
) -> int:
    from serial import Serial

    metadata = asdict(settings)
    config_bytes = None
    if config is not None:
        if settings.control_port is None:
            raise ValueError("A control port and baud rate are required for --config")
        config_bytes = config.read_bytes()
        commands = [
            line.strip() for line in config_bytes.splitlines()
            if line.strip() and not line.lstrip().startswith((b"%", b"#"))
        ]
        if not commands:
            raise ValueError("Configuration contains no commands")
        metadata["config_name"] = config.name
        metadata["config_sha256"] = hashlib.sha256(config_bytes).hexdigest()
    if directory.exists():
        raise FileExistsError(directory)
    with ExitStack() as stack:
        control = None
        data = stack.enter_context(Serial(settings.data_port, settings.data_baud, timeout=0.1))
        if config_bytes is not None:
            control = stack.enter_context(Serial(
                settings.control_port, settings.control_baud, timeout=0.2, write_timeout=2,
            ))
        if control is not None:
            control.reset_input_buffer()
            for command in commands:
                control.write(command + b"\n")
                deadline = monotonic_ns() + 3_000_000_000
                while monotonic_ns() < deadline:
                    response = control.readline(1024).strip()
                    if response == b"Done":
                        break
                    if b"error" in response.lower():
                        raise OSError(f"Radar rejected {command!r}: {response!r}")
                else:
                    raise OSError(f"Radar did not acknowledge {command!r}")
        return record_stream(data, directory, metadata=metadata, duration=duration)
