"""Lazy replay from indexed captures, bare UART streams and synthetic frames."""

from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
import json
from math import isfinite, sin
from pathlib import Path

from .acquisition import MAX_CHUNK_SIZE
from .decoder import StreamDecoder
from .packets import (
    HEADER, HEIGHT, MAGIC, POINT, POINT_UNITS, PRESENCE, TARGET, TLV,
    Frame, TlvType,
)


@dataclass(frozen=True, slots=True)
class Sample:
    seconds: float
    frame: Frame


def _indexed_blocks(path: Path) -> Iterator[tuple[float, bytes]]:
    with (path / "data.bin").open("rb") as raw, (
        path / "index.jsonl"
    ).open(encoding="utf-8") as index:
        try:
            if json.loads(next(index))["format"] != 1:
                raise ValueError("Unsupported recording format")
            elapsed = 0
            for line in index:
                entry = json.loads(line)
                if "status" in entry:
                    if entry["status"] not in ("complete", "interrupted", "error"):
                        raise ValueError("Invalid recording status")
                    if entry["bytes"] != raw.tell() or raw.read(1) or index.read(1):
                        raise ValueError("Recording size does not match its index")
                    return
                size, stamp = entry["size"], entry["elapsed_ns"]
                if (
                    entry["offset"] != raw.tell()
                    or type(size) is not int or not 0 < size <= MAX_CHUNK_SIZE
                    or type(stamp) is not int or stamp < elapsed
                ):
                    raise ValueError("Invalid recording index entry")
                chunk = raw.read(size)
                if len(chunk) != size:
                    raise ValueError("Recording data is truncated")
                elapsed = stamp
                yield elapsed / 1e9, chunk
        except (KeyError, TypeError, StopIteration) as exc:
            raise ValueError("Invalid recording index") from exc
        raise ValueError("Recording index has no completion entry; replay data.bin directly")


def replay(
    path: Path, *, frame_period: float | None = None,
    decoder: StreamDecoder | None = None,
) -> Iterator[Sample]:
    decoder = decoder if decoder is not None else StreamDecoder()
    if frame_period is not None and (not isfinite(frame_period) or frame_period <= 0):
        raise ValueError("Frame period must be positive and finite")
    indexed = path.is_dir()
    if not indexed and frame_period is None:
        raise ValueError("Replay of a bare UART stream needs a frame period in seconds")

    count = 0
    seconds = 0.0
    with closing(_indexed_blocks(path) if indexed else _raw_blocks(path)) as blocks:
        for seconds, block in blocks:
            for frame in decoder.feed(block):
                yield Sample(seconds if frame_period is None else count * frame_period, frame)
                count += 1
    for frame in decoder.finish():
        yield Sample(seconds if frame_period is None else count * frame_period, frame)
        count += 1


def _raw_blocks(path: Path) -> Iterator[tuple[float, bytes]]:
    with path.open("rb") as raw:
        while block := raw.read(MAX_CHUNK_SIZE):
            yield 0.0, block


def synthetic_packet(number: int) -> bytes:
    """Generate one deterministic, invented trajectory for offline development."""
    seconds = number / 10
    progress = min(1.0, max(0.0, (seconds - 2) / 0.5))
    z = 1.3 - progress * 0.95
    vz = -1.9 if 0 < progress < 1 else 0.0
    x = 0.2 * sin(min(seconds, 2))
    cloud = POINT_UNITS.pack(0.01, 0.01, 0.05, 0.01, 0.1)
    cloud += b"".join(
        POINT.pack(round(z * 55) + angle, round(x * 50) + angle, round(vz * 10),
                   220 + angle, 150)
        for angle in range(-8, 9)
    )
    items = [
        (TlvType.POINTS, cloud),
        (TlvType.TARGETS, TARGET.pack(7, x, 2, z, 0, 0, vz, 0, 0, 0, *([0] * 16), 1, 1)),
        (TlvType.TARGET_HEIGHTS, HEIGHT.pack(7, z + 0.2, max(0, z - 0.4))),
        (TlvType.PRESENCE, PRESENCE.pack(1)),
    ]
    if number:
        items.append((TlvType.TARGET_INDICES, bytes([7] * 17)))
    body = b"".join(TLV.pack(kind, len(payload)) + payload for kind, payload in items)
    padding = bytes(-(HEADER.size + len(body)) % 32)
    return HEADER.pack(
        MAGIC, 0x03060000, HEADER.size + len(body) + len(padding), 0xA6843,
        number, 0, 17, len(items), 0,
    ) + body + padding


def synthetic_samples(count: int = 60) -> Iterator[Sample]:
    decoder = StreamDecoder()
    for number in range(count):
        (frame,) = decoder.feed(synthetic_packet(number))
        yield Sample(number / 10, frame)
