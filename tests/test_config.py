from pathlib import Path

import pytest

from mma.config import Config, ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env={})
    assert isinstance(cfg, Config)
    assert cfg.stt.language == "ar"
    assert cfg.stt.submit_url == ""
    assert cfg.stt.poll_interval == 10.0
    assert cfg.stt.num_speakers is None
    assert cfg.agent.runner == "claude-code"
    assert cfg.sinks.brief.formats == ["md", "html"]
    assert cfg.rules.privacy_mode == "owner-only"


def test_example_config_loads():
    cfg = load_config(REPO_ROOT / "config.example.yaml", env={})
    assert cfg.stt.language == "ar"
    assert cfg.stt.poll_timeout == 3600.0
    assert cfg.stt.diarize is True
    assert cfg.sinks.email.smtp_port == 587
    assert cfg.agent.fallback == "opencode"


def test_yaml_values_and_types(tmp_path):
    p = write(
        tmp_path,
        """
stt:
  submit_url: https://example.invalid/submit
  language: en
  num_speakers: 4
  poll_interval: 2
sinks:
  github: {enabled: true, repo: acme/meetings}
rules:
  routing: {sales: [a@example.com, b@example.com]}
""",
    )
    cfg = load_config(p, env={})
    assert cfg.stt.submit_url == "https://example.invalid/submit"
    assert cfg.stt.language == "en"
    assert cfg.stt.num_speakers == 4
    assert cfg.stt.poll_interval == 2.0
    assert isinstance(cfg.stt.poll_interval, float)
    assert cfg.sinks.github.enabled is True
    assert cfg.sinks.github.repo == "acme/meetings"
    assert cfg.sinks.github.labels == ["meeting-action"]  # untouched default
    assert cfg.rules.routing == {"sales": ["a@example.com", "b@example.com"]}


def test_env_overrides_yaml(tmp_path):
    p = write(tmp_path, "stt:\n  submit_url: https://from-yaml.invalid\n  poll_timeout: 10\n")
    env = {
        "MMA_STT_SUBMIT_URL": "https://from-env.invalid/submit",
        "MMA_STT_RESULT_URL": "https://from-env.invalid/result",
        "MMA_STT_POLL_TIMEOUT": "120",
        "MMA_STT_LANGUAGE": "auto",
        "SMTP_PORT": "2525",
        "SMTP_HOST": "smtp.example.invalid",
    }
    cfg = load_config(p, env=env)
    assert cfg.stt.submit_url == "https://from-env.invalid/submit"
    assert cfg.stt.result_url == "https://from-env.invalid/result"
    assert cfg.stt.poll_timeout == 120.0
    assert cfg.stt.language == "auto"
    assert cfg.sinks.email.smtp_port == 2525
    assert cfg.sinks.email.smtp_host == "smtp.example.invalid"


def test_empty_env_var_does_not_override(tmp_path):
    p = write(tmp_path, "stt:\n  submit_url: https://from-yaml.invalid\n")
    cfg = load_config(p, env={"MMA_STT_SUBMIT_URL": ""})
    assert cfg.stt.submit_url == "https://from-yaml.invalid"


def test_mma_config_env_selects_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "custom.yaml"
    p.write_text("stt:\n  language: en\n", encoding="utf-8")
    cfg = load_config(env={"MMA_CONFIG": str(p)})
    assert cfg.stt.language == "en"


def test_secrets_from_env_only_and_masked(tmp_path):
    p = write(tmp_path, "{}\n")
    env = {"HF_TOKEN": "hf_secret_value", "SLACK_WEBHOOK_URL": "https://hooks.invalid/x"}
    cfg = load_config(p, env=env)
    assert cfg.secrets.hf_token == "hf_secret_value"
    assert cfg.secrets.slack_webhook_url == "https://hooks.invalid/x"
    assert cfg.secrets.github_token is None
    assert "hf_secret_value" not in repr(cfg)


def test_secrets_in_yaml_rejected(tmp_path):
    p = write(tmp_path, "secrets:\n  hf_token: nope\n")
    with pytest.raises(ConfigError, match="environment"):
        load_config(p, env={})


def test_empty_file_is_defaults(tmp_path):
    cfg = load_config(write(tmp_path, ""), env={})
    assert cfg.stt.language == "ar"


@pytest.mark.parametrize(
    "text, match",
    [
        ("stt:\n  submit_ulr: x\n", "unknown key"),
        ("bogus: 1\n", "unknown key"),
        ("stt:\n  poll_interval: soon\n", "expected float"),
        ("stt:\n  diarize: maybe\n", "expected a boolean"),
        ("sinks:\n  brief:\n    formats: md\n", "expected a list"),
        ("stt: [1, 2]\n", "expected a mapping"),
        ("- just\n- a list\n", "top level"),
    ],
)
def test_invalid_config(tmp_path, text, match):
    with pytest.raises(ConfigError, match=match):
        load_config(write(tmp_path, text), env={})


def test_missing_explicit_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml", env={})


def test_invalid_env_value(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="MMA_STT_POLL_INTERVAL"):
        load_config(env={"MMA_STT_POLL_INTERVAL": "fast"})
