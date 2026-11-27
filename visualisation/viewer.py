"""Local Matplotlib viewer for synthetic and recorded data."""

from collections.abc import Iterable
from math import dist
from pathlib import Path

from processing.detector import ActivityDetector
from processing.features import FeatureExtractor
from radar.replay import Sample


def view(
    samples: Iterable[Sample], *,
    detector: ActivityDetector | None = None,
    save: Path | None = None,
) -> None:
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(9, 7), layout="constrained")
    axes = figure.add_subplot(projection="3d")
    extractor = FeatureExtractor()
    previous = None
    last_event = None
    try:
        if save is None:
            plt.show(block=False)
        for sample in samples:
            if save is None and not plt.fignum_exists(figure.number):
                return
            frame = sample.frame
            tracks = extractor.update(sample)
            if detector is not None:
                events = detector.update(sample.seconds, frame.header.subframe_number, tracks)
                if events:
                    last_event = events[-1]
            axes.clear()
            if frame.points:
                axes.scatter(*zip(*(p.position for p in frame.points)), s=8, alpha=0.5)
            if frame.targets:
                axes.scatter(
                    *zip(*(target.position for target in frame.targets)),
                    marker="^", color="tab:orange", s=50,
                )
            heights = {height.track_id: height for height in frame.heights}
            for target in frame.targets:
                x, y, z = target.position
                speed = dist(target.velocity, (0, 0, 0))
                height = heights.get(target.track_id)
                label = f"ID {target.track_id} · {speed:.2f} m/s"
                if height:
                    label += f" · Z {height.min_z:.2f}–{height.max_z:.2f} m"
                    axes.plot([x, x], [y, y], [height.min_z, height.max_z], color="tab:orange")
                axes.text(x, y, z, label, fontsize=8)
            axes.set(xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)")
            title = (
                f"Frame {frame.header.frame_number} · "
                f"Subframe {frame.header.subframe_number} · {sample.seconds:.2f} s"
            )
            if frame.presence is not None:
                title += f" · Presence {'yes' if frame.presence else 'no'}"
            if last_event:
                title += f"\nExperimental {last_event.label} at {last_event.confirmation_seconds:.2f} s"
            axes.set_title(title)
            if save is None:
                delay = 0.01 if previous is None else sample.seconds - previous
                plt.pause(max(0.01, min(delay, 1.0)))
            previous = sample.seconds
        if previous is None:
            raise ValueError("No valid frames to display")
        if save is not None:
            figure.savefig(save, dpi=150)
        elif plt.fignum_exists(figure.number):
            plt.show()
    finally:
        plt.close(figure)
