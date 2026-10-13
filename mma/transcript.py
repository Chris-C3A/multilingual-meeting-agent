"""Render a Modal transcript JSON into clean.md and transcript.html.

The JSON is the shape `modal_app/app.py` returns:
  {"filename", "language", "duration", "text",
   "segments": [{"start", "end", "text", "speaker"}], "speakers": [...], "diarized"}

We add one optional key, `speaker_names` ({"SPEAKER_00": "Layla", ...}), so a
rename survives re-renders. No network here; everything is pure and testable.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path

MERGE_GAP_SECONDS = 15.0


@dataclass
class Turn:
    start: float
    end: float
    speaker: str
    text: str


# ── speaker names ────────────────────────────────────────────────────────────
def parse_names(spec: str | None) -> dict[str, str]:
    """Parse "SPEAKER_00=Alice,SPEAKER_01=Bob" into a dict."""
    names: dict[str, str] = {}
    if not spec:
        return names
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        label, sep, name = part.partition("=")
        if not sep or not label.strip() or not name.strip():
            raise ValueError(f"bad --names entry {part!r}; expected SPEAKER_00=Name")
        names[label.strip()] = name.strip()
    return names


def speaker_names(transcript: dict, overrides: dict[str, str] | None = None) -> dict[str, str]:
    names = dict(transcript.get("speaker_names") or {})
    names.update(overrides or {})
    return names


def display_name(label: str | None, names: dict[str, str]) -> str:
    label = label or "UNKNOWN"
    if label in names:
        return names[label]
    if label == "UNKNOWN":
        return "Unknown"
    return label


# ── turns ────────────────────────────────────────────────────────────────────
def merge_turns(segments: list[dict], gap: float = MERGE_GAP_SECONDS) -> list[Turn]:
    """Merge consecutive same-speaker segments whose silence gap is < `gap` seconds."""
    turns: list[Turn] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        speaker = seg.get("speaker") or "UNKNOWN"
        start, end = float(seg["start"]), float(seg["end"])
        last = turns[-1] if turns else None
        if last and last.speaker == speaker and start - last.end < gap:
            last.text = f"{last.text} {text}"
            last.end = max(last.end, end)
        else:
            turns.append(Turn(start, end, speaker, text))
    return turns


def fmt_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── renderers ────────────────────────────────────────────────────────────────
def _talk_time(transcript: dict, names: dict[str, str]) -> list[str]:
    out = []
    for sp in transcript.get("speakers") or []:
        secs = float(sp.get("total_seconds", 0))
        amount = f"{secs:.0f}s" if secs < 60 else f"{secs / 60:.1f} min"
        out.append(f"{display_name(sp.get('speaker'), names)} {amount}")
    return out


def render_clean_md(transcript: dict, stem: str, names: dict[str, str] | None = None) -> str:
    names = speaker_names(transcript, names)
    lines = [f"# {stem}", ""]
    meta = [f"language: {transcript.get('language', '?')}"]
    if transcript.get("duration") is not None:
        meta.append(f"duration: {fmt_ts(float(transcript['duration']))}")
    talk = _talk_time(transcript, names)
    if talk:
        meta.append("speakers: " + ", ".join(talk))
    lines += [f"> {' · '.join(meta)}", ""]
    for turn in merge_turns(transcript.get("segments") or []):
        lines.append(f"[{fmt_ts(turn.start)}] {display_name(turn.speaker, names)}: {turn.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_HTML_HEAD = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:760px;margin:0 auto;padding:32px 20px;
  line-height:1.7;color:#20242A;background:#FBFAF7}}
h1{{font-size:24px;margin-bottom:4px}} .meta{{color:#6E7378;font-size:14px}}
.turn{{margin-top:18px}} .ts{{font-family:ui-monospace,monospace;font-size:12px;color:#6E7378}}
.sp{{font-weight:600;font-size:13px;margin-left:8px}} .text{{margin-top:2px}}
.text[dir="auto"]{{line-height:1.95}}
@media (prefers-color-scheme: dark){{body{{color:#EAE8E2;background:#191B1E}}}}
</style>
</head>
<body>
"""


def render_html(transcript: dict, stem: str, names: dict[str, str] | None = None) -> str:
    names = speaker_names(transcript, names)
    esc = html.escape
    parts = [_HTML_HEAD.format(lang=esc(str(transcript.get("language") or "ar")),
                               title=esc(f"{stem} transcript"))]
    parts.append(f"<h1>{esc(stem)}</h1>\n")
    meta = [f"language: {transcript.get('language', '?')}"]
    if transcript.get("duration") is not None:
        meta.append(f"duration: {fmt_ts(float(transcript['duration']))}")
    meta += _talk_time(transcript, names)
    parts.append(f'<p class="meta">{esc(" · ".join(meta))}</p>\n')
    for turn in merge_turns(transcript.get("segments") or []):
        parts.append(
            '<div class="turn">'
            f'<span class="ts">{fmt_ts(turn.start)}</span>'
            f'<span class="sp">{esc(display_name(turn.speaker, names))}</span>'
            f'<div class="text" dir="auto">{esc(turn.text)}</div>'
            "</div>\n"
        )
    parts.append("</body>\n</html>\n")
    return "".join(parts)


# ── files ────────────────────────────────────────────────────────────────────
def output_paths(out_dir: Path, stem: str) -> dict[str, Path]:
    return {
        "json": out_dir / f"{stem}.json",
        "clean_md": out_dir / f"{stem}.clean.md",
        "html": out_dir / f"{stem}.transcript.html",
    }


def load_transcript(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise ValueError(f"{path}: not a transcript JSON (missing 'segments' list)")
    return data


def write_outputs(
    transcript: dict, out_dir: Path, stem: str, names: dict[str, str] | None = None
) -> dict[str, Path]:
    """Write <stem>.json (with merged speaker_names), .clean.md and .transcript.html."""
    out_dir.mkdir(parents=True, exist_ok=True)
    merged = speaker_names(transcript, names)
    data = dict(transcript)
    if merged:
        data["speaker_names"] = merged
    paths = output_paths(out_dir, stem)
    paths["json"].write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    paths["clean_md"].write_text(render_clean_md(data, stem), encoding="utf-8")
    paths["html"].write_text(render_html(data, stem), encoding="utf-8")
    return paths
