"""Command-line interface for HearthSense capture, replay and viewing."""

import argparse
from contextlib import closing
from math import isfinite
from pathlib import Path
import sys

from .acquisition import SerialSettings, discover_ports, record_serial
from .decoder import StreamDecoder
from .replay import replay, synthetic_samples


def _positive_float(value: str) -> float:
    result = float(value)
    if not isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite number")
    return result


def _source_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--frame-period", type=_positive_float, help="seconds per decoded frame")
    parser.add_argument("--tlv-length", choices=("payload", "inclusive"), default="payload")
    parser.add_argument(
        "--room-z", action="store_true",
        help="enable experimental detection for captures with floor at Z=0 and up as +Z",
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="hearthsense")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("ports", help="list available serial ports")
    record_parser = subcommands.add_parser("record", help="capture UART bytes")
    record_parser.add_argument("directory", type=Path)
    record_parser.add_argument("--data-port", required=True)
    record_parser.add_argument("--data-baud", required=True, type=int)
    record_parser.add_argument("--control-port")
    record_parser.add_argument("--control-baud", type=int)
    record_parser.add_argument("--config", type=Path)
    record_parser.add_argument("--duration", type=_positive_float)
    _source_options(subcommands.add_parser("replay", help="decode and summarise a stream"))
    viewer_parser = subcommands.add_parser("view", help="display decoded frames")
    _source_options(viewer_parser)
    viewer_parser.add_argument("--save", type=Path, help="save the last frame to an image")
    args = parser.parse_args()

    try:
        if args.command == "ports":
            ports = discover_ports()
            for device, description, hardware_id in ports:
                print(f"{device}\t{description}\t{hardware_id}")
            if not ports:
                print("No serial ports found.")
            return 0
        if args.command == "record":
            settings = SerialSettings(
                args.data_port, args.data_baud, args.control_port, args.control_baud,
            )
            count = record_serial(settings, args.directory, config=args.config, duration=args.duration)
            print(f"Recorded {count} bytes to {args.directory}")
            return 0

        if args.synthetic == (args.source is not None):
            parser.error("choose either a recording path or --synthetic")
        if args.synthetic and (args.frame_period is not None or args.tlv_length != "payload"):
            parser.error("synthetic frames have a fixed period and TLV length mode")
        from processing.detector import RuleBasedDetector
        from processing.features import FeatureExtractor

        decoder = StreamDecoder(length_mode=args.tlv_length)
        detector = RuleBasedDetector() if args.synthetic or args.room_z else None
        source = synthetic_samples() if args.synthetic else replay(
            args.source, frame_period=args.frame_period, decoder=decoder,
        )
        with closing(source) as samples:
            if args.command == "view":
                from visualisation.viewer import view

                view(samples, detector=detector, save=args.save)
            else:
                count = 0
                extractor = FeatureExtractor()
                for sample in samples:
                    count += 1
                    frame = sample.frame
                    if detector is not None:
                        tracks = extractor.update(sample)
                        for event in detector.update(sample.seconds, frame.header.subframe_number, tracks):
                            print(f"{event.confirmation_seconds:.2f}s experimental {event.label}, track {event.key[1]}")
                print(f"Decoded {count} frames.")
        if decoder.discarded_bytes or decoder.pending_bytes:
            print(
                f"UART diagnostics: {decoder.rejected_packets} rejected packets, "
                f"{decoder.truncated_packets} truncated candidates, "
                f"{decoder.discarded_bytes} discarded bytes.",
                file=sys.stderr,
            )
        if args.command == "replay" and not count:
            raise ValueError("No valid frames found")
    except (OSError, ValueError) as exc:
        print(f"hearthsense: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
