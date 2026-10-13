import ast
from pathlib import Path

from modal_app.alignment import align_segments, summarize_speakers


def seg(start, end, text="x"):
    return {"start": start, "end": end, "text": text}


def turn(start, end, speaker):
    return {"start": start, "end": end, "speaker": speaker}


def test_importable_without_modal():
    import modal_app.alignment as a

    tree = ast.parse(Path(a.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= {"__future__"}


def test_overlap_winner_takes_segment():
    turns = [turn(0.0, 3.0, "A"), turn(3.0, 10.0, "B")]
    out = align_segments([seg(2.0, 6.0)], turns, fill_nearest=False)
    assert out[0]["speaker"] == "B"  # 1s with A vs 3s with B


def test_overlap_summed_per_speaker():
    # A has two short slices (1.0 + 1.0) that together beat B's single 1.5.
    turns = [turn(0.0, 1.0, "A"), turn(1.0, 2.5, "B"), turn(2.5, 3.5, "A")]
    out = align_segments([seg(0.0, 3.5)], turns, fill_nearest=False)
    assert out[0]["speaker"] == "A"


def test_preserves_segment_fields():
    out = align_segments([seg(0.0, 1.0, "مرحبا hello")], [turn(0, 1, "A")], fill_nearest=False)
    assert out[0] == {"start": 0.0, "end": 1.0, "text": "مرحبا hello", "speaker": "A"}


def test_no_overlap_is_unknown():
    turns = [turn(0.0, 1.0, "A"), turn(5.0, 6.0, "B")]
    out = align_segments([seg(2.0, 3.0)], turns, fill_nearest=False)
    assert out[0]["speaker"] == "UNKNOWN"


def test_touching_boundaries_do_not_count_as_overlap():
    turns = [turn(0.0, 2.0, "A"), turn(3.0, 4.0, "B")]
    out = align_segments([seg(2.0, 3.0)], turns, fill_nearest=False)
    assert out[0]["speaker"] == "UNKNOWN"


def test_no_turns_is_unknown_even_with_fill_nearest():
    out = align_segments([seg(0.0, 1.0)], [], fill_nearest=True)
    assert out[0]["speaker"] == "UNKNOWN"


def test_fill_nearest_uses_closest_turn_midpoint():
    # segment mid = 4.5; A mid = 0.5 (4.0 away), B mid = 6.5 (2.0 away)
    turns = [turn(0.0, 1.0, "A"), turn(6.0, 7.0, "B")]
    out = align_segments([seg(4.0, 5.0)], turns, fill_nearest=True)
    assert out[0]["speaker"] == "B"


def test_early_break_relies_on_sorted_turns():
    # Sorted: the loop stops at the first turn starting after the segment ends.
    turns = [turn(0.0, 1.0, "A"), turn(10.0, 11.0, "B"), turn(1.0, 2.0, "C")]
    out = align_segments([seg(1.0, 2.0)], turns, fill_nearest=False)
    # C overlaps fully but sits after B (which starts past seg_end): never reached.
    assert out[0]["speaker"] == "UNKNOWN"

    out_sorted = align_segments(
        [seg(1.0, 2.0)], sorted(turns, key=lambda t: t["start"]), fill_nearest=False
    )
    assert out_sorted[0]["speaker"] == "C"


def test_multiple_segments():
    turns = [turn(0.0, 5.0, "A"), turn(5.0, 10.0, "B")]
    out = align_segments([seg(0.5, 4.0), seg(6.0, 9.0), seg(11.0, 12.0)], turns,
                         fill_nearest=False)
    assert [s["speaker"] for s in out] == ["A", "B", "UNKNOWN"]


def test_summarize_speakers_sorted_by_talk_time():
    segments = [
        {"start": 0.0, "end": 2.0, "speaker": "A"},
        {"start": 2.0, "end": 7.0, "speaker": "B"},
        {"start": 7.0, "end": 8.0, "speaker": "A"},
        {"start": 8.0, "end": 8.5, "speaker": "UNKNOWN"},
    ]
    out = summarize_speakers(segments)
    assert [s["speaker"] for s in out] == ["B", "A", "UNKNOWN"]
    assert out[0] == {"speaker": "B", "total_seconds": 5.0, "segment_count": 1}
    assert out[1] == {"speaker": "A", "total_seconds": 3.0, "segment_count": 2}


def test_summarize_speakers_empty():
    assert summarize_speakers([]) == []
