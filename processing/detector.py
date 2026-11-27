"""An experimental fall-like activity demonstrator using room-frame Z."""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .features import TrackFeatures, TrackKey


@dataclass(frozen=True, slots=True)
class Event:
    key: TrackKey
    onset_seconds: float
    confirmation_seconds: float
    label: str = "fall-like activity"


class ActivityDetector(Protocol):
    """A future classifier can consume the same per-frame features."""

    def update(
        self, seconds: float, subframe: int, tracks: list[TrackFeatures],
    ) -> list[Event]: ...


@dataclass(frozen=True, slots=True)
class Thresholds:
    min_descent_rate: float = 0.9
    min_total_drop: float = 0.6
    max_descent_seconds: float = 0.8
    low_z: float = 0.6
    low_max_z: float = 0.85
    max_settled_speed: float = 0.25
    settle_seconds: float = 0.7
    candidate_seconds: float = 2.5

    def __post_init__(self) -> None:
        values = (
            self.min_descent_rate, self.min_total_drop, self.max_descent_seconds,
            self.low_z, self.low_max_z, self.max_settled_speed,
            self.settle_seconds, self.candidate_seconds,
        )
        if any(not isfinite(value) or value <= 0 for value in values):
            raise ValueError("Thresholds must be positive and finite")
        if self.max_descent_seconds + self.settle_seconds > self.candidate_seconds:
            raise ValueError("Descent and settling must fit within the candidate window")


@dataclass(slots=True)
class _Candidate:
    onset: float
    start_z: float
    settled_since: float | None = None
    rapid_drop_complete: bool = False


class RuleBasedDetector:
    def __init__(self, thresholds: Thresholds = Thresholds()) -> None:
        self.thresholds = thresholds
        self._pending: dict[TrackKey, _Candidate] = {}

    def update(
        self, seconds: float, subframe: int, tracks: list[TrackFeatures],
    ) -> list[Event]:
        limits = self.thresholds
        active = {track.key for track in tracks}
        self._pending = {
            key: candidate for key, candidate in self._pending.items()
            if 0 <= seconds - candidate.onset <= limits.candidate_seconds
            and (key[0] != subframe or key in active)
        }
        events = []
        for track in tracks:
            key = track.key
            if track.drop is None or track.descent_rate is None:
                self._pending.pop(key, None)
                continue
            z = track.position[2]
            candidate = self._pending.get(key)
            if candidate is None:
                if (
                    track.descent_rate < limits.min_descent_rate
                    or track.vertical_velocity > -limits.min_descent_rate
                ):
                    continue
                onset = seconds - (track.interval_seconds or 0.0)
                candidate = self._pending[key] = _Candidate(onset, z + track.drop)

            drop = candidate.start_z - z
            if not candidate.rapid_drop_complete:
                if seconds - candidate.onset > limits.max_descent_seconds:
                    del self._pending[key]
                    continue
                candidate.rapid_drop_complete = drop >= limits.min_total_drop
            elif drop < limits.min_total_drop:
                # A rebound ends this candidate instead of lending its onset to a later descent.
                del self._pending[key]
                continue

            if (
                not candidate.rapid_drop_complete or z > limits.low_z
                or max(track.speed, track.observed_speed or 0.0) > limits.max_settled_speed
                or (track.max_z is not None and track.max_z > limits.low_max_z)
            ):
                candidate.settled_since = None
                continue
            if candidate.settled_since is None:
                candidate.settled_since = seconds
            if seconds - candidate.settled_since >= limits.settle_seconds:
                events.append(Event(key, candidate.onset, seconds))
                del self._pending[key]
        return events
