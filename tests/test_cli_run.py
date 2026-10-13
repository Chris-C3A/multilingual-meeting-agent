"""`mma run` with a fake STT client: no network."""

import json
from pathlib import Path

import pytest

from mma import cli
from mma.stt.modal_client import STTError

DEMO = Path(__file__).resolve().parent.parent / "examples" / "sample-meeting" / "demo.json"


class FakeClient:
    calls: list = []
    error: Exception | None = None

    def __init__(self, stt, overrides):
        self.stt, self.overrides = stt, overrides

    @classmethod
    def from_config(cls, stt, **overrides):
        return cls(stt, overrides)

    def transcribe(self, path):
        FakeClient.calls.append((Path(path), self.overrides))
        if FakeClient.error:
            raise FakeClient.error
        return json.loads(DEMO.read_text(encoding="utf-8"))


@pytest.fixture
def fake(monkeypatch, tmp_path):
    FakeClient.calls = []
    FakeClient.error = None
    monkeypatch.setattr(cli, "ModalSTTClient", FakeClient)
    monkeypatch.chdir(tmp_path)  # no stray config.yaml
    monkeypatch.delenv("MMA_CONFIG", raising=False)
    audio = tmp_path / "standup.m4a"
    audio.write_bytes(b"\x00" * 64)
    return audio


def test_run_writes_outputs(fake, tmp_path):
    out = tmp_path / "res"
    rc = cli.main(["run", str(fake), "--language", "auto", "--num-speakers", "2",
                   "--names", "SPEAKER_00=Layla", "--out", str(out)])
    assert rc == 0
    assert FakeClient.calls == [(fake, {"language": "auto", "num_speakers": 2})]
    for name in ("standup.json", "standup.clean.md", "standup.transcript.html"):
        assert (out / name).is_file()
    assert "] Layla: " in (out / "standup.clean.md").read_text(encoding="utf-8")
    assert json.loads((out / "standup.json").read_text())["speaker_names"] == {
        "SPEAKER_00": "Layla"}


def test_run_is_idempotent(fake, tmp_path, capsys):
    out = tmp_path / "res"
    assert cli.main(["run", str(fake), "--out", str(out)]) == 0
    assert cli.main(["run", str(fake), "--out", str(out)]) == 0
    assert len(FakeClient.calls) == 1
    assert "skip: standup" in capsys.readouterr().out
    assert cli.main(["run", str(fake), "--out", str(out), "--force"]) == 0
    assert len(FakeClient.calls) == 2


def test_run_partial_outputs_are_redone(fake, tmp_path):
    out = tmp_path / "res"
    out.mkdir()
    (out / "standup.json").write_text("{}")
    assert cli.main(["run", str(fake), "--out", str(out)]) == 0
    assert len(FakeClient.calls) == 1


def test_run_default_out_is_results(fake, tmp_path):
    assert cli.main(["run", str(fake)]) == 0
    assert (tmp_path / "results" / "standup.clean.md").is_file()


def test_run_stt_error(fake, tmp_path, capsys):
    FakeClient.error = STTError("submit_url and result_url are required")
    assert cli.main(["run", str(fake), "--out", str(tmp_path / "res")]) == 1
    assert "required" in capsys.readouterr().err
    assert not (tmp_path / "res" / "standup.json").exists()


def test_run_missing_audio(fake, tmp_path, capsys):
    assert cli.main(["run", str(tmp_path / "nope.m4a")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_run_without_urls_fails_cleanly(tmp_path, monkeypatch, capsys):
    """Real client, no URLs configured: clear error, no network."""
    monkeypatch.chdir(tmp_path)
    for var in ("MMA_CONFIG", "MMA_STT_SUBMIT_URL", "MMA_STT_RESULT_URL"):
        monkeypatch.delenv(var, raising=False)
    audio = tmp_path / "a.m4a"
    audio.write_bytes(b"\x00")
    assert cli.main(["run", str(audio)]) == 1
    assert "MMA_STT_SUBMIT_URL" in capsys.readouterr().err
