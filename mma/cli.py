"""`mma` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mma import __version__, skills
from mma.config import ConfigError, load_config
from mma.stt.modal_client import ModalSTTClient, STTError
from mma.transcript import load_transcript, output_paths, parse_names, write_outputs

DEFAULT_OUT = "results"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mma",
        description="Multilingual meeting agent: code-switched Arabic/English meetings to action.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    names_help = 'rename speakers, e.g. "SPEAKER_00=Layla,SPEAKER_01=Omar"'

    run = sub.add_parser("run", help="transcribe a recording on the deployed Modal app")
    run.add_argument("audio", help="path to an audio or video file")
    run.add_argument(
        "-c", "--config", help="path to config YAML (default: $MMA_CONFIG or ./config.yaml)"
    )
    run.add_argument("--language", choices=["ar", "en", "auto"],
                     help="transcription language (default: stt.language, usually ar)")
    run.add_argument("--names", help=names_help)
    run.add_argument("--num-speakers", type=int, help="exact speaker count, if known")
    run.add_argument("--out", help="output folder (default: sinks.output_dir, usually results/)")
    run.add_argument("--force", action="store_true", help="re-transcribe even if outputs exist")

    tr = sub.add_parser("transcript", help="re-render clean.md + html from a transcript JSON")
    tr.add_argument("json", help="path to <stem>.json")
    tr.add_argument("--names", help=names_help)
    tr.add_argument("--out", default=DEFAULT_OUT, help="output folder (default: results/)")

    sub.add_parser("doctor", help="check the local setup")

    val = sub.add_parser("validate", help="validate <stem>.actions.json against the brief schema")
    val.add_argument("actions", help="path to <stem>.actions.json")

    sk = sub.add_parser("skill", help="manage the agent skill")
    sk_sub = sk.add_subparsers(dest="skill_command", required=True)
    inst = sk_sub.add_parser("install", help=f"install skills/{skills.SKILL_NAME}/")
    inst.add_argument("--target", choices=[*skills.TARGETS, "all"], default="claude",
                      help="agent to install for (default: claude)")
    inst.add_argument("--dest", help=f"skills folder to install into instead "
                                     f"(creates <dest>/{skills.SKILL_NAME}/)")
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        names = parse_names(args.names)
    except (ConfigError, ValueError) as exc:
        print(f"mma run: {exc}", file=sys.stderr)
        return 2

    audio = Path(args.audio)
    if not audio.is_file():
        print(f"mma run: no such file: {audio}", file=sys.stderr)
        return 2

    out_dir = Path(args.out or cfg.sinks.output_dir)
    stem = audio.stem
    paths = output_paths(out_dir, stem)
    if not args.force and all(p.exists() for p in paths.values()):
        print(f"skip: {stem} already transcribed in {out_dir}/ (use --force to redo)")
        return 0

    overrides: dict = {}
    if args.language:
        overrides["language"] = args.language
    if args.num_speakers:
        overrides["num_speakers"] = args.num_speakers
    try:
        client = ModalSTTClient.from_config(cfg.stt, **overrides)
        print(f"transcribing {audio.name} (this can take a few minutes)...", file=sys.stderr)
        transcript = client.transcribe(audio)
    except STTError as exc:
        print(f"mma run: {exc}", file=sys.stderr)
        return 1

    for p in write_outputs(transcript, out_dir, stem, names).values():
        print(p)
    return 0


def cmd_transcript(args: argparse.Namespace) -> int:
    src = Path(args.json)
    try:
        names = parse_names(args.names)
        transcript = load_transcript(src)
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        print(f"mma transcript: {exc}", file=sys.stderr)
        return 2
    for p in write_outputs(transcript, Path(args.out), src.stem, names).values():
        print(p)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from mma.brief import validate_actions

    try:
        data = json.loads(Path(args.actions).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"mma validate: {exc}", file=sys.stderr)
        return 2
    errors = validate_actions(data)
    if errors:
        for e in errors:
            print(f"❌ {e}")
        return 1
    print(f"✅ {args.actions} matches the brief schema")
    return 0


def cmd_skill_install(args: argparse.Namespace) -> int:
    if args.dest:
        roots = [Path(args.dest).expanduser()]
    elif args.target == "all":
        roots = [skills.target_root(t) for t in skills.TARGETS]
    else:
        roots = [skills.target_root(args.target)]
    try:
        for root in roots:
            dest, changed = skills.install(root)
            print(f"{'installed' if changed else 'up to date'}: {dest}")
    except OSError as exc:
        print(f"mma skill install: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(args)
    if args.command == "transcript":
        return cmd_transcript(args)
    if args.command == "doctor":
        from mma.doctor import main as doctor_main

        return doctor_main()
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "skill":
        return cmd_skill_install(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
