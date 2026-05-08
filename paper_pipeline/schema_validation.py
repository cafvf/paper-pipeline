from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .contracts import ValidationError


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_ROOT / name
    if path.parent != SCHEMA_ROOT:
        raise ValidationError(f"schema must be loaded from schemas/: {name}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValidationError(f"schema root must be a mapping: {name}")
    return loaded


def validate_instance(instance: Any, schema_name: str) -> Any:
    schema = load_schema(schema_name)
    try:
        Draft202012Validator(schema).validate(instance)
    except JsonSchemaValidationError as exc:
        raise ValidationError(f"{schema_name} validation failed: {exc.message}") from exc
    return instance


def validate_json_file(path: str | Path, schema_name: str) -> Any:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_instance(loaded, schema_name)
