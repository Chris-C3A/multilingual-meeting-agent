"""`mma` command-line entry point."""

from __future__ import annotations

import argparse
import sys

from mma import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mma",
        description="Multilingual meeting agent: code-switched Arabic/English meetings to action.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="transcribe and process a recording (Phase 2)")
    run.add_argument("audio", help="path to an audio or video file")
    run.add_argument(
        "-c", "--config", help="path to config YAML (default: $MMA_CONFIG or ./config.yaml)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        print("mma run: not implemented yet (Phase 2, see ROADMAP.md).", file=sys.stderr)
        return 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
