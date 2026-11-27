from dataclasses import replace

import pytest

from processing.detector import RuleBasedDetector
from processing.features import FeatureExtractor
from radar.replay import Sample, synthetic_samples


def test_feature_edges_and_disappearing_track():
    first, second = synthetic_samples(2)
    extractor = FeatureExtractor()
    (initial,) = extractor.update(first)
    assert initial.drop is None
    assert initial.vertical_extent == pytest.approx(0.6)
    (following,) = extractor.update(second)
    assert following.drop == 0
    assert following.displacement > 0
    assert extractor.update(Sample(0.2, replace(second.frame, targets=()))) == []
    (reacquired,) = extractor.update(Sample(0.3, second.frame))
    assert reacquired.displacement is None
    (stale,) = extractor.update(Sample(1, second.frame))
    assert stale.descent_rate is None
    (duplicate,) = extractor.update(Sample(1, second.frame))
    assert duplicate.descent_rate is None
    with pytest.raises(ValueError, match="finite"):
        extractor.update(Sample(float("inf"), second.frame))


def test_subframes_are_isolated():
    first, second = synthetic_samples(2)
    extractor = FeatureExtractor()
    extractor.update(first)
    interleaved = replace(first.frame, header=replace(first.frame.header, subframe_number=1))
    (other,) = extractor.update(Sample(0.05, interleaved))
    (following,) = extractor.update(second)
    assert other.drop is None
    assert following.drop == 0


@pytest.mark.parametrize("lose_track", [False, True])
def test_demonstrator_requires_continuous_post_event_observations(lose_track):
    features = FeatureExtractor()
    detector = RuleBasedDetector()
    events = []
    for sample in synthetic_samples():
        if lose_track and sample.frame.header.frame_number == 27:
            sample = replace(sample, frame=replace(sample.frame, targets=()))
        tracks = features.update(sample)
        events.extend(detector.update(sample.seconds, sample.frame.header.subframe_number, tracks))
    if lose_track:
        assert events == []
    else:
        (event,) = events
        assert event.key == (0, 7)
        assert event.label == "fall-like activity"
        assert event.confirmation_seconds >= 3.2


def test_feature_continuity_rejects_missing_frames_and_accepts_uint32_wrap():
    first, second = synthetic_samples(2)
    extractor = FeatureExtractor()
    frame = replace(first.frame, header=replace(first.frame.header, frame_number=0xFFFFFFFF))
    extractor.update(Sample(0, frame))
    (wrapped,) = extractor.update(Sample(0.1, first.frame))
    assert wrapped.drop == 0
    gap = replace(second.frame, header=replace(second.frame.header, frame_number=2))
    (missing,) = extractor.update(Sample(0.2, gap))
    assert missing.drop is None
    (out_of_order,) = extractor.update(Sample(0.3, second.frame))
    assert out_of_order.observed_speed is None


@pytest.mark.parametrize("hz", [10, 20, 50])
@pytest.mark.parametrize("scenario", ["fast", "slow", "moving", "gap", "delayed"])
def test_timing_and_stillness_across_sample_rates(hz, scenario):
    (template,) = synthetic_samples(1)
    frame = template.frame
    features = FeatureExtractor()
    detector = RuleBasedDetector()
    events = []
    for index in range(hz * 4):
        seconds = index / hz
        if scenario == "gap" and index == int(hz * 1.65):
            continue
        duration = 1.5 if scenario == "slow" else 0.5
        progress = max(0, min(1, (seconds - 1) / duration))
        vz = -0.95 / duration if 0 < progress < 1 else 0
        drop = progress * 0.95
        if scenario == "delayed":
            # A short quick descent stops before the drop threshold; the rest is slow.
            drop = min(0.2, max(0, (seconds - 1) * 1.9))
            if seconds > 1.5:
                drop += min(0.75, (seconds - 1.5) * 0.65)
            vz = -1.9 if 1 < seconds < 1.11 else 0
        x = max(0, seconds - 1.5) * 0.6 if scenario == "moving" else 0
        z = 1.3 - drop
        target = replace(frame.targets[0], position=(x, 2, z), velocity=(0, 0, vz))
        sample = Sample(seconds, replace(
            frame, header=replace(frame.header, frame_number=index),
            targets=(target,), heights=(),
        ))
        events.extend(detector.update(seconds, 0, features.update(sample)))
    if scenario == "fast":
        (event,) = events
        assert event.onset_seconds == pytest.approx(1.0)
        assert 2.2 <= event.confirmation_seconds <= 2.2 + 2 / hz
    else:
        assert events == []
