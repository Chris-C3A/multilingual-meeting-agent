"""Typed configuration: a YAML file, overridden by environment variables.

Precedence (lowest to highest): dataclass defaults -> YAML file -> env vars.

Secrets (tokens, passwords, webhook URLs) are never read from YAML; they come
from the environment only, so a config file can be shared or committed safely.

Environment variables
---------------------
Config overrides:
  MMA_CONFIG             path to the YAML file (default: ./config.yaml if present)
  MMA_STT_SUBMIT_URL     Modal `submit` endpoint URL
  MMA_STT_RESULT_URL     Modal `result` endpoint URL
  MMA_STT_LANGUAGE       transcription language ("ar", "en", ... or "auto")
  MMA_STT_POLL_INTERVAL  seconds between result polls
  MMA_STT_POLL_TIMEOUT   seconds before giving up on a transcription
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_FROM   email sink settings

Secrets (env only):
  HF_TOKEN               Hugging Face token (pyannote gated model; used on Modal)
  ANTHROPIC_API_KEY      Claude Code / agent runner
  GITHUB_TOKEN           GitHub issues sink
  SMTP_PASSWORD          email sink
  SLACK_WEBHOOK_URL      Slack sink
"""

from __future__ import annotations

import dataclasses
import os
import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(ValueError):
    """Raised for malformed config files or invalid values."""


# ── Sections ─────────────────────────────────────────────────────────────────
@dataclass
class STTConfig:
    submit_url: str = ""
    result_url: str = ""
    language: str = "ar"  # "auto" = let Whisper detect
    diarize: bool = True
    num_speakers: int | None = None  # None = let pyannote estimate
    poll_interval: float = 10.0
    poll_timeout: float = 3600.0


@dataclass
class AgentConfig:
    runner: str = "claude-code"  # "claude-code" | "opencode"
    fallback: str | None = "opencode"
    skills_dir: str = "skills"
    timeout: float = 900.0


@dataclass
class BriefSinkConfig:
    enabled: bool = True
    formats: list[str] = field(default_factory=lambda: ["md", "html"])


@dataclass
class GitHubSinkConfig:
    enabled: bool = False
    repo: str = ""  # "owner/name"
    labels: list[str] = field(default_factory=lambda: ["meeting-action"])


@dataclass
class EmailSinkConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    from_addr: str = ""
    to: list[str] = field(default_factory=list)


@dataclass
class SlackSinkConfig:
    enabled: bool = False


@dataclass
class WikiSinkConfig:
    enabled: bool = False
    path: str = "wiki"


@dataclass
class SinksConfig:
    output_dir: str = "results"
    brief: BriefSinkConfig = field(default_factory=BriefSinkConfig)
    github: GitHubSinkConfig = field(default_factory=GitHubSinkConfig)
    email: EmailSinkConfig = field(default_factory=EmailSinkConfig)
    slack: SlackSinkConfig = field(default_factory=SlackSinkConfig)
    wiki: WikiSinkConfig = field(default_factory=WikiSinkConfig)


@dataclass
class RulesConfig:
    privacy_mode: str = "owner-only"  # "owner-only" | "shared"
    owner: str = ""  # e.g. an email address; where owner-only output goes
    routing: dict[str, list[str]] = field(default_factory=dict)  # category -> recipients


@dataclass
class Secrets:
    """Credentials, from the environment only. Values are masked in repr()."""

    hf_token: str | None = field(default=None, repr=False)
    anthropic_api_key: str | None = field(default=None, repr=False)
    github_token: str | None = field(default=None, repr=False)
    smtp_password: str | None = field(default=None, repr=False)
    slack_webhook_url: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Secrets:
        return cls(
            hf_token=env.get("HF_TOKEN") or None,
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            github_token=env.get("GITHUB_TOKEN") or None,
            smtp_password=env.get("SMTP_PASSWORD") or None,
            slack_webhook_url=env.get("SLACK_WEBHOOK_URL") or None,
        )


@dataclass
class Config:
    stt: STTConfig = field(default_factory=STTConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    sinks: SinksConfig = field(default_factory=SinksConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)
    secrets: Secrets = field(default_factory=Secrets)


# env var -> (section path, field name). Secrets are handled by Secrets.from_env.
ENV_OVERRIDES: dict[str, tuple[tuple[str, ...], str]] = {
    "MMA_STT_SUBMIT_URL": (("stt",), "submit_url"),
    "MMA_STT_RESULT_URL": (("stt",), "result_url"),
    "MMA_STT_LANGUAGE": (("stt",), "language"),
    "MMA_STT_POLL_INTERVAL": (("stt",), "poll_interval"),
    "MMA_STT_POLL_TIMEOUT": (("stt",), "poll_timeout"),
    "SMTP_HOST": (("sinks", "email"), "smtp_host"),
    "SMTP_PORT": (("sinks", "email"), "smtp_port"),
    "SMTP_USER": (("sinks", "email"), "smtp_user"),
    "SMTP_FROM": (("sinks", "email"), "from_addr"),
}


# ── Loading ──────────────────────────────────────────────────────────────────
def load_config(
    path: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> Config:
    """Load config from YAML (optional) and apply env var overrides.

    If `path` is None, uses $MMA_CONFIG, else ./config.yaml if it exists, else
    defaults only. An explicitly given path that does not exist is an error.
    """
    env = os.environ if env is None else env

    explicit = path is not None or bool(env.get("MMA_CONFIG"))
    if path is not None:
        cfg_path = Path(path)
    else:
        cfg_path = Path(env.get("MMA_CONFIG") or DEFAULT_CONFIG_PATH)

    data: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"{cfg_path}: top level must be a mapping")
        data = loaded
    elif explicit:
        raise ConfigError(f"config file not found: {cfg_path}")

    if "secrets" in data:
        raise ConfigError("secrets must come from environment variables, not the config file")

    config = _build(Config, data, "")
    _apply_env(config, env)
    config.secrets = Secrets.from_env(env)
    return config


def _build(cls: type, data: Any, where: str) -> Any:
    if not isinstance(data, dict):
        raise ConfigError(f"{where or 'config'}: expected a mapping, got {type(data).__name__}")
    hints = typing.get_type_hints(cls)
    known = {f.name for f in dataclasses.fields(cls) if f.name != "secrets"}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"{where or 'config'}: unknown key(s) {sorted(unknown)}")
    kwargs = {
        name: _coerce(hints[name], value, f"{where}.{name}" if where else name)
        for name, value in data.items()
    }
    return cls(**kwargs)


def _coerce(tp: Any, value: Any, where: str) -> Any:
    origin = typing.get_origin(tp)

    if origin in (typing.Union, types.UnionType):
        args = typing.get_args(tp)
        if value is None and type(None) in args:
            return None
        (inner,) = [a for a in args if a is not type(None)]
        return _coerce(inner, value, where)

    if dataclasses.is_dataclass(tp):
        return _build(tp, value if value is not None else {}, where)

    if origin is list:
        if not isinstance(value, list):
            raise ConfigError(f"{where}: expected a list")
        (item,) = typing.get_args(tp)
        return [_coerce(item, v, f"{where}[{i}]") for i, v in enumerate(value)]

    if origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{where}: expected a mapping")
        kt, vt = typing.get_args(tp)
        return {_coerce(kt, k, where): _coerce(vt, v, f"{where}.{k}") for k, v in value.items()}

    return _scalar(tp, value, where)


def _scalar(tp: type, value: Any, where: str) -> Any:
    if tp is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"1", "true", "yes", "on", "0", "false",
                                                        "no", "off"}:
            return value.lower() in {"1", "true", "yes", "on"}
        raise ConfigError(f"{where}: expected a boolean, got {value!r}")
    if tp is str:
        if isinstance(value, (dict, list)) or value is None:
            raise ConfigError(f"{where}: expected a string, got {value!r}")
        return str(value)
    if tp in (int, float):
        if isinstance(value, bool):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        try:
            return tp(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{where}: expected {tp.__name__}, got {value!r}") from exc
    return value


def _apply_env(config: Config, env: Mapping[str, str]) -> None:
    for var, (section_path, name) in ENV_OVERRIDES.items():
        raw = env.get(var)
        if raw is None or raw == "":
            continue
        target: Any = config
        for part in section_path:
            target = getattr(target, part)
        tp = typing.get_type_hints(type(target))[name]
        setattr(target, name, _coerce(tp, raw, var))
