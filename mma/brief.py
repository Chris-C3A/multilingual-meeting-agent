"""Validate the structured brief (`<stem>.actions.json`) the agent writes."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from mma.skills import source_dir

SCHEMA_PATH = source_dir() / "templates" / "brief.schema.json"


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_actions(data: dict, schema: dict | None = None) -> list[str]:
    """Return a list of human-readable errors (empty = valid)."""
    schema = schema if schema is not None else load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
