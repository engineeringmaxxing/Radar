"""Extract per-track features without coupling classification to the UART stream."""

from dataclasses import dataclass
from math import dist, isfinite

from radar.packets import Vector3
from radar.replay import Sample

TrackKey = tuple[int, int]  # Subframe number, track ID.


@dataclass(frozen=True, slots=True)
class TrackFeatures:
    key: TrackKey
    seconds: float
    position: Vector3
    speed: float
    vertical_velocity: float
    displacement: float | None
    drop: float | None
    descent_rate: float | None
    max_z: float | None
    vertical_extent: float | None
    observed_speed: float | None = None
    interval_seconds: float | None = None


class FeatureExtractor:
    def __init__(self, max_gap: float = 0.5) -> None:
        if not isfinite(max_gap) or max_gap <= 0:
            raise ValueError("Maximum feature gap must be positive and finite")
        self.max_gap = max_gap
        self._previous: dict[TrackKey, tuple[float, int, Vector3]] = {}

    def update(self, sample: Sample) -> list[TrackFeatures]:
        time, frame = sample.seconds, sample.frame
        if not isfinite(time):
            raise ValueError("Feature timestamp must be finite")
        subframe = frame.header.subframe_number
        number = frame.header.frame_number
        heights = {height.track_id: height for height in frame.heights}
        previous = self._previous
        self._previous = {
            key: value for key, value in previous.items()
            if key[0] != subframe and 0 <= time - value[0] <= self.max_gap
        }
        features = []
        for target in frame.targets:
            key = (subframe, target.track_id)
            displacement = drop = descent_rate = observed_speed = interval = None
            if key in previous:
                last_time, last_number, position = previous[key]
                elapsed = time - last_time
                if 0 < elapsed <= self.max_gap and number == (last_number + 1) % (1 << 32):
                    interval = elapsed
                    displacement = dist(position, target.position)
                    observed_speed = displacement / elapsed
                    drop = position[2] - target.position[2]
                    descent_rate = drop / elapsed
            self._previous[key] = (time, number, target.position)
            height = heights.get(target.track_id)
            features.append(TrackFeatures(
                key, time, target.position, dist(target.velocity, (0, 0, 0)),
                target.velocity[2], displacement, drop, descent_rate,
                height.max_z if height else None,
                height.max_z - height.min_z if height else None,
                observed_speed, interval,
            ))
        return features
