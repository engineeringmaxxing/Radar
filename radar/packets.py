"""Wire structures and immutable decoded data for TI 3D People Tracking."""

from dataclasses import dataclass
from enum import IntEnum
from struct import Struct

MAGIC = bytes.fromhex("02 01 04 03 06 05 08 07")
HEADER = Struct("<8s8I")
TLV = Struct("<2I")
POINT_UNITS = Struct("<5f")
POINT = Struct("<bbhHH")
TARGET = Struct("<I27f")
HEIGHT = Struct("<Iff")
PRESENCE = Struct("<I")

Vector3 = tuple[float, float, float]


class TlvType(IntEnum):
    TARGETS = 1010
    TARGET_INDICES = 1011
    TARGET_HEIGHTS = 1012
    POINTS = 1020
    PRESENCE = 1021


@dataclass(frozen=True, slots=True)
class FrameHeader:
    version: int
    total_length: int
    platform: int
    frame_number: int
    cpu_cycles: int
    detected_objects: int
    tlv_count: int
    subframe_number: int


@dataclass(frozen=True, slots=True)
class Point:
    position: Vector3
    doppler: float
    snr: float


@dataclass(frozen=True, slots=True)
class Target:
    track_id: int
    position: Vector3
    velocity: Vector3
    acceleration: Vector3
    covariance: tuple[float, ...]
    gain: float
    confidence: float


@dataclass(frozen=True, slots=True)
class TargetHeight:
    track_id: int
    max_z: float
    min_z: float


@dataclass(frozen=True, slots=True)
class Frame:
    header: FrameHeader
    points: tuple[Point, ...] = ()
    targets: tuple[Target, ...] = ()
    heights: tuple[TargetHeight, ...] = ()
    # These IDs belong to the preceding frame's points.
    previous_point_target_ids: bytes | None = None
    presence: bool | None = None
    unknown_tlv_types: tuple[int, ...] = ()
