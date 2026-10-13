import json
from pathlib import Path

import pytest

from mma.cli import main
from mma.transcript import fmt_ts, merge_turns, parse_names, render_clean_md

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "examples" / "sample-meeting" / "demo.json"
NAMES = "SPEAKER_00=Layla,SPEAKER_01=Omar"


def seg(start, end, speaker, text):
    return {"start": start, "end": end, "speaker": speaker, "text": f" {text}"}


def test_merge_same_speaker_within_gap():
    turns = merge_turns([
        seg(0, 5, "SPEAKER_00", "a"),
        seg(6, 9, "SPEAKER_00", "b"),        # gap 1s -> merge
        seg(23.9, 25, "SPEAKER_00", "c"),    # gap 14.9s -> merge
        seg(40, 42, "SPEAKER_00", "d"),      # gap 15s -> new turn
        seg(43, 44, "SPEAKER_01", "e"),      # other speaker -> new turn
        seg(44, 45, "SPEAKER_01", "  "),     # blank text dropped
    ])
    assert [(t.speaker, t.text, t.start, t.end) for t in turns] == [
        ("SPEAKER_00", "a b c", 0, 25),
        ("SPEAKER_00", "d", 40, 42),
        ("SPEAKER_01", "e", 43, 44),
    ]


def test_fmt_ts():
    assert fmt_ts(0) == "00:00"
    assert fmt_ts(146.5) == "02:26"
    assert fmt_ts(3725) == "1:02:05"


def test_parse_names():
    assert parse_names("SPEAKER_00=Layla, SPEAKER_01 = Omar") == {
        "SPEAKER_00": "Layla", "SPEAKER_01": "Omar"}
    assert parse_names(None) == {}
    with pytest.raises(ValueError):
        parse_names("SPEAKER_00")


def test_clean_md_unknown_and_unnamed_labels():
    md = render_clean_md(
        {"language": "ar", "segments": [seg(0, 1, "SPEAKER_02", "x"), seg(2, 3, None, "y")]},
        "s",
    )
    assert "[00:00] SPEAKER_02: x" in md
    assert "[00:02] Unknown: y" in md


def test_transcript_cli_on_demo(tmp_path, capsys):
    assert main(["transcript", str(DEMO), "--names", NAMES, "--out", str(tmp_path)]) == 0
    md = (tmp_path / "demo.clean.md").read_text(encoding="utf-8")
    lines = [ln for ln in md.splitlines() if ln.startswith("[")]

    # 23 segments: the first two Layla segments merge (0.4s gap); Omar's
    # 123.3-129.0 and 146.5-153.2 segments stay apart (17.5s gap).
    assert len(lines) == 22
    assert lines[0].startswith("[00:00] Layla: صباح الخير عمر، shall we start?")
    assert lines[0].endswith("they want a demo before end of month.")
    assert lines[1].startswith("[00:13] Omar: ")
    assert any(ln.startswith("[01:30] Unknown: Okay.") for ln in lines)
    assert any(ln.startswith("[02:03] Omar: ") for ln in lines)
    assert any(ln.startswith("[02:26] Omar: Okay، الـ staging شغال.") for ln in lines)

    data = json.loads((tmp_path / "demo.json").read_text(encoding="utf-8"))
    assert data["speaker_names"] == {"SPEAKER_00": "Layla", "SPEAKER_01": "Omar"}
    assert data["segments"] == json.loads(DEMO.read_text(encoding="utf-8"))["segments"]

    html = (tmp_path / "demo.transcript.html").read_text(encoding="utf-8")
    assert 'dir="auto"' in html and "Layla" in html and "<script" not in html


def test_transcript_rerender_keeps_names_and_allows_rename(tmp_path):
    main(["transcript", str(DEMO), "--names", NAMES, "--out", str(tmp_path)])
    out = tmp_path / "demo.json"
    # No --names: names stored in the JSON are reused.
    assert main(["transcript", str(out), "--out", str(tmp_path)]) == 0
    assert "] Layla: " in (tmp_path / "demo.clean.md").read_text(encoding="utf-8")
    # Rename one speaker; the other keeps its stored name.
    assert main(["transcript", str(out), "--names", "SPEAKER_01=Omar K.",
                 "--out", str(tmp_path)]) == 0
    md = (tmp_path / "demo.clean.md").read_text(encoding="utf-8")
    assert "] Omar K.: " in md and "] Layla: " in md


def test_html_escapes_transcript_text(tmp_path):
    src = tmp_path / "in" / "x.json"
    src.parent.mkdir()
    src.write_text(json.dumps({"segments": [seg(0, 1, "SPEAKER_00", "<script>alert(1)</script>")]}))
    assert main(["transcript", str(src), "--out", str(tmp_path / "out")]) == 0
    html = (tmp_path / "out" / "x.transcript.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("content", ["not json", '{"no": "segments"}'])
def test_transcript_cli_bad_input(tmp_path, content, capsys):
    p = tmp_path / "bad.json"
    p.write_text(content)
    assert main(["transcript", str(p), "--out", str(tmp_path)]) == 2
    assert "mma transcript" in capsys.readouterr().err


def test_transcript_cli_bad_names(tmp_path):
    assert main(["transcript", str(DEMO), "--names", "oops", "--out", str(tmp_path)]) == 2
