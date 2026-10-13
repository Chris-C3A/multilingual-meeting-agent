"""Install the bundled agent skill(s) into Claude Code / OpenCode / Hermes.

Skill roots (each gets a `process-meeting/` folder):
  claude    ~/.claude/skills/
  opencode  $XDG_CONFIG_HOME/opencode/skills/  (default ~/.config/opencode/skills/)
  hermes    ~/.hermes/skills/
"""

from __future__ import annotations

import filecmp
import os
import shutil
from pathlib import Path

SKILL_NAME = "process-meeting"
TARGETS = ("claude", "opencode", "hermes")

# Skills live at the repo root (skills/), next to the mma package. Running from
# a clone (uv sync / pip install -e .) is the supported layout.
REPO_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def source_dir(name: str = SKILL_NAME) -> Path:
    return REPO_SKILLS_DIR / name


def target_root(target: str) -> Path:
    home = Path.home()
    if target == "claude":
        return home / ".claude" / "skills"
    if target == "opencode":
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else home / ".config"
        return base / "opencode" / "skills"
    if target == "hermes":
        return home / ".hermes" / "skills"
    raise ValueError(f"unknown target {target!r}; choose from {', '.join(TARGETS)}")


def is_installed(root: Path, name: str = SKILL_NAME) -> bool:
    return (root / name / "SKILL.md").is_file()


def _same_tree(a: Path, b: Path) -> bool:
    if not b.is_dir():
        return False
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.diff_files or cmp.funny_files:
        return False
    # dircmp is shallow by default; compare file contents explicitly.
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def install(root: Path, name: str = SKILL_NAME) -> tuple[Path, bool]:
    """Copy skills/<name>/ into <root>/<name>/. Returns (dest, changed)."""
    src = source_dir(name)
    if not (src / "SKILL.md").is_file():
        raise FileNotFoundError(f"skill source not found: {src} (run from a repo clone)")
    dest = root / name
    if _same_tree(src, dest):
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return dest, True
