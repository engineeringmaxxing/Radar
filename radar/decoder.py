"""Bounded streaming decoder for TI 40-byte-header UART frames."""

from math import cos, isfinite, sin
from struct import error as StructError
from typing import Literal

from .packets import (
    HEADER, HEIGHT, MAGIC, POINT, POINT_UNITS, PRESENCE, TARGET, TLV,
    Frame, FrameHeader, Point, Target, TargetHeight, TlvType,
)

LengthMode = Literal["payload", "inclusive"]
DEFAULT_MAX_PACKET = 256 * 1024
ALIGNMENT = 32
STREAM_BLOCK_SIZE = 4096
RECORD_SIZES = {TlvType.TARGETS: TARGET.size, TlvType.TARGET_HEIGHTS: HEIGHT.size}
KNOWN_TLVS = frozenset(TlvType)


class PacketError(ValueError):
    """Invalid header, TLV layout or payload."""


def _points(payload: bytes) -> tuple[Point, ...]:
    if len(payload) < POINT_UNITS.size:
        raise PacketError("Point cloud is missing its scale factors")
    units = POINT_UNITS.unpack_from(payload)
    if any(not isfinite(unit) or unit <= 0 for unit in units):
        raise PacketError("Invalid point scale factors")
    points = []
    for raw in POINT.iter_unpack(payload[POINT_UNITS.size:]):
        elevation, azimuth, doppler, distance, snr = (
            value * unit for value, unit in zip(raw, units, strict=True)
        )
        planar = distance * cos(elevation)
        position = (planar * sin(azimuth), planar * cos(azimuth), distance * sin(elevation))
        points.append(Point(position, doppler, snr))
    return tuple(points)


def _targets(payload: bytes) -> tuple[Target, ...]:
    targets = []
    ids = set()
    for track_id, *values in TARGET.iter_unpack(payload):
        if not all(map(isfinite, values[:9])):
            raise PacketError("Non-finite target position or motion")
        if track_id in ids:
            raise PacketError("Duplicate target ID")
        ids.add(track_id)
        targets.append(Target(
            track_id, tuple(values[:3]), tuple(values[3:6]), tuple(values[6:9]),
            tuple(values[9:25]), values[25], values[26],
        ))
    return tuple(targets)


def _heights(payload: bytes) -> tuple[TargetHeight, ...]:
    heights = []
    ids = set()
    for track_id, max_z, min_z in HEIGHT.iter_unpack(payload):
        if not (isfinite(max_z) and isfinite(min_z) and min_z <= max_z):
            raise PacketError("Invalid target height bounds")
        if track_id in ids:
            raise PacketError("Duplicate target height ID")
        ids.add(track_id)
        heights.append(TargetHeight(track_id, max_z, min_z))
    return tuple(heights)


class StreamDecoder:
    def __init__(
        self, *, max_packet_size: int = DEFAULT_MAX_PACKET,
        length_mode: LengthMode = "payload",
    ) -> None:
        if max_packet_size < HEADER.size:
            raise ValueError("Packet limit must accommodate a frame header")
        if length_mode not in ("payload", "inclusive"):
            raise ValueError("Invalid TLV length mode")
        self.max_packet_size = max_packet_size
        self.length_mode = length_mode
        self.rejected_packets = 0
        self.discarded_bytes = 0
        self._buffer = bytearray()
        self._offset = 0
        self.truncated_packets = 0
        self._header_in_progress: FrameHeader | None = None
        self._cursor = HEADER.size
        self._spans: list[tuple[int, int, int]] = []
        self._seen: set[int] = set()

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer) - self._offset

    def _discard(self, count: int, *, rejected: bool = False) -> None:
        self.discarded_bytes += count
        self.rejected_packets += rejected
        self._advance(count)

    def _advance(self, count: int) -> None:
        self._offset += count
        self._header_in_progress = None
        self._cursor = HEADER.size
        self._spans.clear()
        self._seen.clear()

    def _header(self, offset: int) -> FrameHeader:
        header = FrameHeader(*HEADER.unpack_from(self._buffer, offset)[1:])
        if not HEADER.size <= header.total_length <= self.max_packet_size:
            raise PacketError("Invalid packet length")
        if header.tlv_count > (header.total_length - HEADER.size) // TLV.size:
            raise PacketError("TLV headers exceed packet length")
        return header

    def _layout_ready(self, header: FrameHeader) -> bool:
        """Validate headers incrementally, without examining bytes inside payloads."""
        while len(self._spans) < header.tlv_count:
            next_payload = self._cursor + TLV.size
            remaining_headers = header.tlv_count - len(self._spans) - 1
            last_payload_end = header.total_length - remaining_headers * TLV.size
            if next_payload > last_payload_end:
                raise PacketError("Truncated TLV header")
            if next_payload > self.pending_bytes:
                return False
            kind, size = TLV.unpack_from(self._buffer, self._offset + self._cursor)
            if self.length_mode == "inclusive":
                size -= TLV.size
            end = next_payload + size
            if size < 0 or end > last_payload_end:
                raise PacketError("Invalid TLV length")
            if kind in KNOWN_TLVS:
                if kind in self._seen:
                    raise PacketError("Duplicate known TLV")
                self._seen.add(kind)
            if kind == TlvType.POINTS and size != POINT_UNITS.size + header.detected_objects * POINT.size:
                raise PacketError("Invalid point cloud length for header point count")
            if kind in RECORD_SIZES and size % RECORD_SIZES[kind]:
                raise PacketError("Partial TLV record")
            if kind == TlvType.PRESENCE and size != PRESENCE.size:
                raise PacketError("Invalid presence length")
            self._spans.append((kind, next_payload, end))
            self._cursor = end

        padding = header.total_length - self._cursor
        if padding and (padding >= ALIGNMENT or header.total_length % ALIGNMENT):
            raise PacketError("Invalid packet padding")
        return self.pending_bytes >= header.total_length

    def _decode(self, header: FrameHeader) -> Frame:
        fields = {}
        unknown = []
        for kind, start, end in self._spans:
            if kind not in KNOWN_TLVS:
                unknown.append(kind)
                continue
            payload = bytes(self._buffer[self._offset + start:self._offset + end])
            try:
                if kind == TlvType.POINTS:
                    fields["points"] = _points(payload)
                elif kind == TlvType.TARGETS:
                    fields["targets"] = _targets(payload)
                elif kind == TlvType.TARGET_HEIGHTS:
                    fields["heights"] = _heights(payload)
                elif kind == TlvType.TARGET_INDICES:
                    fields["previous_point_target_ids"] = payload
                elif kind == TlvType.PRESENCE:
                    (presence,) = PRESENCE.unpack(payload)
                    if presence not in (0, 1):
                        raise PacketError("Presence must be 0 or 1")
                    fields["presence"] = bool(presence)
            except StructError as exc:
                raise PacketError(f"Invalid payload size for TLV {kind}") from exc
        return Frame(header, unknown_tlv_types=tuple(unknown), **fields)

    def _drain(self, frames: list[Frame], *, final: bool = False) -> None:
        while self.pending_bytes:
            start = self._buffer.find(MAGIC, self._offset)
            if start < 0:
                retain = 0 if final else len(MAGIC) - 1
                self._discard(max(0, self.pending_bytes - retain))
                break
            if start > self._offset:
                self._discard(start - self._offset)
            try:
                if self.pending_bytes >= HEADER.size:
                    if self._header_in_progress is None:
                        self._header_in_progress = self._header(start)
                    header = self._header_in_progress
                    if self._layout_ready(header):
                        frames.append(self._decode(header))
                        self._advance(header.total_length)
                        continue
            except PacketError:
                self._discard(1, rejected=True)
                continue

            if not final:
                break
            # This candidate cannot finish. Try subsequent sync words at EOF only.
            self.truncated_packets += 1
            self._discard(1, rejected=True)

    def _compact(self) -> None:
        del self._buffer[:self._offset]
        self._offset = 0

    def feed(self, data: bytes) -> list[Frame]:
        frames: list[Frame] = []
        for start in range(0, len(data), STREAM_BLOCK_SIZE):
            self._buffer.extend(data[start:start + STREAM_BLOCK_SIZE])
            self._drain(frames)
            self._compact()
        return frames

    def finish(self) -> list[Frame]:
        """End the input stream, report truncation and salvage remaining complete frames."""
        frames: list[Frame] = []
        self._drain(frames, final=True)
        self._compact()
        return frames
