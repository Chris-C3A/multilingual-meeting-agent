"""Static checks on the Modal app. Never builds images, deploys, or touches the network."""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

APP_PATH = Path(__file__).resolve().parent.parent / "modal_app" / "app.py"
ENV_VARS = ("MMA_MODAL_APP_NAME", "MMA_MODAL_VOLUME", "MMA_MODAL_GPU", "MMA_MODAL_HF_SECRET")


def test_app_parses():
    ast.parse(APP_PATH.read_text(encoding="utf-8"))


def load_app_standalone(monkeypatch, name):
    """Import app.py the way the container does: a top-level module, no package."""
    modal = pytest.importorskip("modal")  # optional: `uv sync --group modal`
    monkeypatch.setitem(sys.modules, "modal_app", None)  # package import -> ModuleNotFoundError
    monkeypatch.syspath_prepend(str(APP_PATH.parent))
    monkeypatch.delitem(sys.modules, "alignment", raising=False)
    spec = importlib.util.spec_from_file_location(name, APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return modal, mod


def test_app_imports_with_defaults_without_fastapi(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    modal, mod = load_app_standalone(monkeypatch, "mma_app_defaults")

    assert importlib.util.find_spec("fastapi") is None or mod.UploadFile is not None
    assert mod.app.name == "mma-stt"
    assert mod.VOLUME_NAME == "mma-whisper-models"
    assert mod.HF_SECRET_NAME == "huggingface-secret"
    assert mod.GPU == "L4"
    for name in ("convert_model", "transcribe", "submit", "result"):
        assert isinstance(getattr(mod, name), modal.Function)
    assert mod.align_segments.__module__ == "alignment"  # sibling-file fallback used


def test_app_settings_from_env(monkeypatch):
    monkeypatch.setenv("MMA_MODAL_APP_NAME", "custom-stt")
    monkeypatch.setenv("MMA_MODAL_VOLUME", "custom-vol")
    monkeypatch.setenv("MMA_MODAL_GPU", "T4")
    monkeypatch.setenv("MMA_MODAL_HF_SECRET", "custom-secret")
    _, mod = load_app_standalone(monkeypatch, "mma_app_env")

    assert mod.app.name == "custom-stt"
    assert (mod.VOLUME_NAME, mod.GPU, mod.HF_SECRET_NAME) == ("custom-vol", "T4", "custom-secret")
