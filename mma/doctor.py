"""`mma doctor`: check the local environment. Local checks only, no network."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mma import skills
from mma.config import ConfigError, load_config

OK, WARN, FAIL = "ok", "warn", "fail"
ICONS = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}
MIN_PYTHON = (3, 11)


@dataclass
class Check:
    status: str
    label: str
    detail: str = ""


def run_checks(env: Mapping[str, str] | None = None) -> list[Check]:
    env = os.environ if env is None else env
    checks: list[Check] = []

    # Hard requirements ------------------------------------------------------
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        checks.append(Check(OK, "python", ver))
    else:
        checks.append(Check(FAIL, "python", f"{ver}; need >= {'.'.join(map(str, MIN_PYTHON))}"))

    try:
        cfg = load_config(env=env)
    except ConfigError as exc:
        cfg = None
        checks.append(Check(FAIL, "config", str(exc)))
    else:
        src = env.get("MMA_CONFIG") or ("config.yaml" if Path("config.yaml").exists() else None)
        checks.append(Check(OK, "config", src or "defaults (no config.yaml)"))

    if (skills.source_dir() / "SKILL.md").is_file():
        checks.append(Check(OK, "skill source", str(skills.source_dir())))
    else:
        checks.append(Check(FAIL, "skill source", f"missing {skills.source_dir()}"))

    # Optional / needed only for real audio ----------------------------------
    if shutil.which("ffmpeg"):
        checks.append(Check(OK, "ffmpeg", shutil.which("ffmpeg") or ""))
    else:
        checks.append(Check(WARN, "ffmpeg", "not on PATH (only needed to shrink large videos)"))

    if shutil.which("modal"):
        checks.append(Check(OK, "modal CLI", shutil.which("modal") or ""))
    else:
        checks.append(Check(WARN, "modal CLI", "not installed (uv sync --group modal)"))

    # Presence of a token only; we do not call Modal to verify it.
    modal_toml = Path(env.get("MODAL_CONFIG_PATH") or Path.home() / ".modal.toml")
    if modal_toml.is_file() or (
        env.get("MODAL_TOKEN_ID") and env.get("MODAL_TOKEN_SECRET")
    ):
        checks.append(Check(OK, "modal token", "found (not verified online)"))
    else:
        checks.append(Check(WARN, "modal token", "none; run `modal setup`"))

    if env.get("HF_TOKEN"):
        checks.append(Check(OK, "HF_TOKEN", "set"))
    else:
        checks.append(Check(WARN, "HF_TOKEN", "not set (needed once, for the Modal secret)"))

    if cfg is not None:
        for name, value in (("MMA_STT_SUBMIT_URL", cfg.stt.submit_url),
                            ("MMA_STT_RESULT_URL", cfg.stt.result_url)):
            if value:
                checks.append(Check(OK, name, "set"))
            else:
                checks.append(Check(WARN, name, "not set (needed for `mma run`)"))

    agents = [a for a in ("claude", "opencode", "hermes") if shutil.which(a)]
    if agents:
        checks.append(Check(OK, "agent CLI", ", ".join(agents)))
    else:
        checks.append(Check(WARN, "agent CLI", "none of claude / opencode / hermes on PATH"))

    installed = [t for t in skills.TARGETS if skills.is_installed(skills.target_root(t))]
    if installed:
        checks.append(Check(OK, "skill installed", ", ".join(installed)))
    else:
        checks.append(Check(WARN, "skill installed", "no; run `mma skill install`"))

    return checks


def main(env: Mapping[str, str] | None = None) -> int:
    checks = run_checks(env)
    for c in checks:
        line = f"{ICONS[c.status]} {c.label}"
        if c.detail:
            line += f": {c.detail}"
        print(line)
    failed = [c for c in checks if c.status == FAIL]
    if failed:
        print(f"\n{len(failed)} hard requirement(s) failed.")
        return 1
    return 0
