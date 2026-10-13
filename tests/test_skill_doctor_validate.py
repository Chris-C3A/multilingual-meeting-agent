import json
from pathlib import Path

import pytest

from mma import doctor, skills
from mma.brief import load_schema, validate_actions
from mma.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_ACTIONS = REPO_ROOT / "examples" / "sample-meeting" / "expected" / "demo.actions.json"
SKILL_FILES = {"SKILL.md", "templates/brief.template.html", "templates/brief.schema.json"}


def tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return h


# ── skill install ────────────────────────────────────────────────────────────
def test_skill_source_files_exist():
    assert tree(skills.source_dir()) == SKILL_FILES


def test_skill_frontmatter():
    text = (skills.source_dir() / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: process-meeting\ndescription: Use when ")


def test_skill_install_dest_is_idempotent(tmp_path, capsys):
    dest = tmp_path / "skills"
    assert main(["skill", "install", "--dest", str(dest)]) == 0
    assert tree(dest / "process-meeting") == SKILL_FILES
    assert "installed:" in capsys.readouterr().out
    assert main(["skill", "install", "--dest", str(dest)]) == 0
    assert "up to date:" in capsys.readouterr().out

    # A modified copy gets refreshed.
    (dest / "process-meeting" / "SKILL.md").write_text("stale")
    assert main(["skill", "install", "--dest", str(dest)]) == 0
    assert "installed:" in capsys.readouterr().out
    assert (dest / "process-meeting" / "SKILL.md").read_text().startswith("---")


def test_skill_install_targets(home):
    assert main(["skill", "install", "--target", "all"]) == 0
    for root in (".claude/skills", ".config/opencode/skills", ".hermes/skills"):
        assert (home / root / "process-meeting" / "SKILL.md").is_file()


def test_skill_install_default_is_claude(home):
    assert main(["skill", "install"]) == 0
    assert (home / ".claude/skills/process-meeting/SKILL.md").is_file()
    assert not (home / ".hermes").exists()


def test_opencode_respects_xdg(home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert skills.target_root("opencode") == tmp_path / "xdg" / "opencode" / "skills"


# ── doctor ───────────────────────────────────────────────────────────────────
def test_doctor_runs_and_exits_zero(home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")  # no ffmpeg/modal/agents: warnings only
    for var in ("MMA_CONFIG", "HF_TOKEN", "MMA_STT_SUBMIT_URL", "MMA_STT_RESULT_URL",
                "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "MODAL_CONFIG_PATH"):
        monkeypatch.delenv(var, raising=False)
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "✅ python" in out
    assert "⚠️  ffmpeg" in out
    assert "⚠️  HF_TOKEN" in out
    assert "⚠️  skill installed" in out
    assert "❌" not in out


def test_doctor_sees_installed_skill_and_urls(home, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["skill", "install"])
    env = {"MMA_STT_SUBMIT_URL": "https://x.invalid/s", "MMA_STT_RESULT_URL": "https://x.invalid/r",
           "HF_TOKEN": "hf_x"}
    checks = {c.label: c for c in doctor.run_checks(env)}
    assert checks["skill installed"].status == doctor.OK
    assert checks["MMA_STT_SUBMIT_URL"].status == doctor.OK
    assert checks["HF_TOKEN"].status == doctor.OK


def test_doctor_fails_on_bad_config(home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MMA_CONFIG", raising=False)
    (tmp_path / "config.yaml").write_text("bogus: 1\n")
    assert main(["doctor"]) == 1
    assert "❌ config" in capsys.readouterr().out


# ── brief schema ─────────────────────────────────────────────────────────────
def test_sample_actions_valid():
    data = json.loads(SAMPLE_ACTIONS.read_text(encoding="utf-8"))
    assert validate_actions(data) == []
    assert main(["validate", str(SAMPLE_ACTIONS)]) == 0


def test_invalid_actions_reported(tmp_path, capsys):
    data = json.loads(SAMPLE_ACTIONS.read_text(encoding="utf-8"))
    del data["summary"]
    data["action_items"][0]["status"] = "maybe"
    data["action_items"][1]["ts"] = "1 minute in"
    errors = validate_actions(data, load_schema())
    assert any("summary" in e for e in errors)
    assert any(e.startswith("action_items/0/status") for e in errors)
    assert any(e.startswith("action_items/1/ts") for e in errors)

    p = tmp_path / "bad.actions.json"
    p.write_text(json.dumps(data))
    assert main(["validate", str(p)]) == 1
    assert "❌" in capsys.readouterr().out


def test_validate_unreadable(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{")
    assert main(["validate", str(p)]) == 2
