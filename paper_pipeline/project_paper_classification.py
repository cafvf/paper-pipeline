from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ValidationError
from .schema_validation import validate_instance


@dataclass(frozen=True)
class LLMClassification:
    project_id: str
    citekey: str
    utility_class: str
    recommended_action: str
    confidence: str
    recommended_zotero_stage: str
    input_layer: str
    raw: dict[str, Any]


def parse_llm_classification(text: str) -> LLMClassification:
    raw = _load_single_json_object(text)
    validate_instance(raw, "llm_classification.schema.json")
    return LLMClassification(
        project_id=str(raw["project_id"]),
        citekey=str(raw["citekey"]),
        utility_class=str(raw["utility_class"]),
        recommended_action=str(raw["recommended_action"]),
        confidence=str(raw["confidence"]),
        recommended_zotero_stage=str(raw["recommended_zotero_stage"]),
        input_layer=str(raw["input_layer"]),
        raw=raw,
    )


def append_validated_classification(text: str, output_path: str | Path) -> LLMClassification:
    classification = parse_llm_classification(text)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(classification.raw, ensure_ascii=False, sort_keys=True) + "\n")
    return classification


def _load_single_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        raise ValidationError("LLM classification output must be a single JSON object without prose")
    decoder = json.JSONDecoder()
    try:
        loaded, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON output: {exc}") from exc
    if stripped[end:].strip():
        raise ValidationError("LLM classification output must contain exactly one JSON object")
    if not isinstance(loaded, dict):
        raise ValidationError("LLM classification output must be a JSON object")
    return loaded
