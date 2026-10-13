"""Pure helpers for joining Whisper segments with pyannote speaker turns.

No heavy imports (no modal, torch, or pyannote), so this module is importable
and unit-testable anywhere, and safe to load at the top of the Modal app.
"""

from __future__ import annotations


def align_segments(segments: list[dict], turns: list[dict],
                   *, fill_nearest: bool) -> list[dict]:
    """Assign each Whisper segment the speaker with the most temporal overlap.

    Ported from diarize.py: turns are time-sorted, so we can break early.

    `segments`: [{"start", "end", "text", ...}] from faster-whisper.
    `turns`:    [{"start", "end", "speaker"}] from pyannote, sorted by start.
    A segment that overlaps no turn gets "UNKNOWN", unless `fill_nearest` is
    set, in which case it takes the speaker of the turn whose midpoint is
    closest to the segment's midpoint.
    """
    out: list[dict] = []
    for seg in segments:
        seg_start, seg_end = float(seg["start"]), float(seg["end"])
        overlap: dict[str, float] = {}
        for t in turns:
            if t["end"] <= seg_start:
                continue
            if t["start"] >= seg_end:
                break
            ov = max(0.0, min(seg_end, t["end"]) - max(seg_start, t["start"]))
            if ov > 0:
                overlap[t["speaker"]] = overlap.get(t["speaker"], 0.0) + ov
        if overlap:
            speaker = max(overlap.items(), key=lambda kv: kv[1])[0]
        elif fill_nearest and turns:
            mid = (seg_start + seg_end) / 2
            speaker = min(turns, key=lambda t: abs((t["start"] + t["end"]) / 2 - mid))["speaker"]
        else:
            speaker = "UNKNOWN"
        out.append({**seg, "speaker": speaker})
    return out


def summarize_speakers(segments: list[dict]) -> list[dict]:
    """Per-speaker talk time and segment count, most talkative first."""
    by: dict[str, dict] = {}
    for seg in segments:
        sp = seg["speaker"]
        info = by.setdefault(sp, {"speaker": sp, "total_seconds": 0.0, "segment_count": 0})
        info["total_seconds"] += float(seg["end"]) - float(seg["start"])
        info["segment_count"] += 1
    return sorted(by.values(), key=lambda s: s["total_seconds"], reverse=True)
