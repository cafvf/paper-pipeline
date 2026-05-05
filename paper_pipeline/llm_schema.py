from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from jsonschema import validate
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .contracts import READING_PROTOCOL_LLM_TAGS, READING_PROTOCOL_SUBJECT_TAGS, Stage, ValidationError
from .reading_protocol import criteria_for_stage, protocol_gate_label


@dataclass(frozen=True)
class LLMAssessment:
    citekey: str
    stage: Stage
    recommended_collection: Stage
    confidence: float
    summary: str
    article_type: str = "original"
    review_type: str = "none"
    article_type_confidence: float = 0.0
    gate_result: str = ""
    recommendation_action: str = ""
    recommendation_rationale: str = ""
    evidence: list[str] = field(default_factory=list)
    recommended_tags_add: list[str] = field(default_factory=list)
    recommended_subject_tags: list[str] = field(default_factory=list)
    knowledge_suggestions: list[dict[str, Any]] = field(default_factory=list)
    protocol_criteria: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def render_schema_for_stage(stage: Stage) -> dict[str, Any]:
    section_properties = {
        "whole_paper_scan": {"type": "string"},
        "abstract_keywords": {"type": "string"},
        "introduction": {"type": "string"},
        "conclusion": {"type": "string"},
    }
    if stage in {Stage.TO_REVISE, Stage.TO_DIG}:
        section_properties["results"] = {"type": "string"}
    if stage == Stage.TO_DIG:
        section_properties.update(
            {
                "method_formulation": {"type": "string"},
                "results_validation": {"type": "string"},
                "limitations_insights_conclusion": {"type": "string"},
            }
        )
    properties: dict[str, Any] = {
        "citekey": {"type": "string", "minLength": 1},
        "stage": {"enum": [item.value for item in Stage]},
        "article_type": {"type": "string", "enum": ["original", "review"]},
        "review_type": {
            "type": "string",
            "enum": ["none", "narrative-review", "systematic-review", "scoping-review", "meta-analysis"],
        },
        "article_type_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "gate_result": {"type": "string", "enum": ["pass", "hold", "fail"]},
        "recommendation_action": {
            "type": "string",
            "enum": ["move_to_revise", "keep_in_revise", "move_to_dig", "keep_in_dig", "move_to_expendable"],
        },
        "recommended_collection": {"enum": [item.value for item in Stage]},
        "recommendation_rationale": {"type": "string", "minLength": 10, "maxLength": 360},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string", "maxLength": 700},
        "evidence": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 360}},
        "recommended_tags_add": {
            "type": "array",
            "items": {"type": "string", "enum": list(READING_PROTOCOL_LLM_TAGS)},
            "uniqueItems": True,
            "maxItems": 4,
        },
        "recommended_subject_tags": {
            "type": "array",
            **_subject_tag_schema_for_stage(stage),
            "uniqueItems": True,
        },
        "knowledge_suggestions": _knowledge_suggestion_schema_for_stage(stage),
        "protocol_criteria": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["criterion_id", "criterion", "status", "evidence", "rationale"],
                "properties": {
                    "criterion_id": {"type": "string", "enum": [item.id for item in criteria_for_stage(stage)]},
                    "criterion": {"type": "string"},
                    "status": {"type": "string", "enum": ["yes", "partial", "no", "unknown"]},
                    "evidence": {"type": "string", "maxLength": 260},
                    "rationale": {"type": "string", "maxLength": 220},
                },
                "additionalProperties": False,
            },
        },
        "metrics": {
            "type": "object",
            "required": ["criteria_met", "criteria_total", "criteria_score", "evidence_coverage", "decision_readiness"],
            "properties": {
                "criteria_met": {"type": "integer", "minimum": 0},
                "criteria_total": {"type": "integer", "minimum": 1},
                "criteria_score": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence_coverage": {"type": "number", "minimum": 0, "maximum": 1},
                "decision_readiness": {"type": "string", "enum": ["low", "medium", "high"]},
                "protocol_gate": {"type": "string", "default": protocol_gate_label(stage)},
            },
            "additionalProperties": True,
        },
    }
    if stage != Stage.TO_LOOK:
        properties["section_findings"] = {"type": "object", "properties": section_properties}
    schema: dict[str, Any] = {
        "type": "object",
        "required": [
            "citekey",
            "stage",
            "article_type",
            "review_type",
            "article_type_confidence",
            "gate_result",
            "recommendation_action",
            "recommended_collection",
            "recommendation_rationale",
            "confidence",
            "summary",
            "evidence",
            "recommended_tags_add",
            "recommended_subject_tags",
            "knowledge_suggestions",
            "protocol_criteria",
            "metrics",
        ],
        "properties": properties,
        "additionalProperties": stage != Stage.TO_LOOK,
    }
    if stage == Stage.TO_DIG:
        schema["properties"]["figures_to_register"] = {"type": "array", "items": {"type": "object"}}
    return schema


def parse_llm_assessment(text: str) -> LLMAssessment:
    stripped = _extract_single_json_object(text)
    if not stripped:
        raise ValidationError("LLM output must be a single JSON object without prose")
    try:
        raw = _normalize_obj(_repair_obj(json.loads(stripped)))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON output: {exc}") from exc
    try:
        stage = Stage(raw.get("stage"))
    except ValueError as exc:
        raise ValidationError(f"invalid LLM stage: {raw.get('stage')}") from exc
    schema = render_schema_for_stage(stage)
    try:
        validate(instance=raw, schema=schema)
    except JsonSchemaValidationError as exc:
        raise ValidationError(f"LLM output does not match schema: {exc.message}") from exc
    _validate_decision_contract(raw, stage)
    return LLMAssessment(
        citekey=str(raw["citekey"]),
        stage=stage,
        article_type=str(raw["article_type"]),
        review_type=str(raw["review_type"]),
        article_type_confidence=float(raw["article_type_confidence"]),
        gate_result=str(raw["gate_result"]),
        recommendation_action=str(raw["recommendation_action"]),
        recommended_collection=_parse_stage(raw["recommended_collection"], field="recommended_collection"),
        recommendation_rationale=str(raw["recommendation_rationale"]),
        confidence=float(raw["confidence"]),
        summary=str(raw["summary"]),
        evidence=[str(item) for item in raw.get("evidence", [])],
        recommended_tags_add=[str(item) for item in raw.get("recommended_tags_add", [])],
        recommended_subject_tags=[str(item) for item in raw.get("recommended_subject_tags", [])],
        knowledge_suggestions=list(raw.get("knowledge_suggestions", [])),
        protocol_criteria=list(raw.get("protocol_criteria", [])),
        metrics=dict(raw.get("metrics", {})),
    )


def _extract_single_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    if start < 0:
        return ""
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(stripped[start:])
    except json.JSONDecodeError:
        return ""
    candidate = stripped[start : start + end].strip()
    remaining = stripped[start + end :].strip()
    if "{" in remaining:
        return ""
    return candidate


def _normalize_obj(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    raw = dict(value)
    raw["recommended_tags_add"] = _dedupe_list(raw.get("recommended_tags_add", []))
    raw["recommended_subject_tags"] = _dedupe_list(raw.get("recommended_subject_tags", []))
    raw["protocol_criteria"] = _dedupe_protocol_criteria(raw.get("protocol_criteria", []))
    raw["metrics"] = _normalize_metrics(raw.get("metrics", {}))
    return raw


def _subject_tag_schema_for_stage(stage: Stage) -> dict[str, Any]:
    return {"items": {"type": "string", "enum": list(READING_PROTOCOL_SUBJECT_TAGS)}, "maxItems": 8}


def _knowledge_suggestion_schema_for_stage(stage: Stage) -> dict[str, Any]:
    if stage == Stage.TO_LOOK:
        return {"type": "array", "items": {"type": "object"}}
    return {
        "type": "array",
        "maxItems": 5,
        "items": {
            "type": "object",
            "required": [
                "type",
                "target",
                "knowledge_claim",
                "article_use",
                "evidence",
                "applicability",
                "limitations",
                "integration_notes",
                "review_tasks",
                "justification",
            ],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["concept", "dot", "moc", "literature_note_update", "project_link", "method_check"],
                },
                "target": {"type": "string"},
                "knowledge_claim": {"type": "string", "minLength": 40, "maxLength": 520},
                "article_use": {"type": "string", "minLength": 30, "maxLength": 420},
                "evidence": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "maxLength": 260}},
                "applicability": {"type": "string", "minLength": 30, "maxLength": 420},
                "limitations": {"type": "string", "minLength": 20, "maxLength": 320},
                "integration_notes": {"type": "string", "minLength": 20, "maxLength": 320},
                "review_tasks": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 180}},
                "justification": {"type": "string", "maxLength": 240},
            },
            "additionalProperties": False,
        },
    }


def _validate_decision_contract(raw: dict[str, Any], stage: Stage) -> None:
    action = str(raw["recommendation_action"])
    recommended_collection = _parse_stage(raw["recommended_collection"], field="recommended_collection")
    article_type = str(raw["article_type"])
    review_type = str(raw["review_type"])
    subject_tags = [str(item) for item in raw.get("recommended_subject_tags", [])]
    recommended_tags = [str(item) for item in raw.get("recommended_tags_add", [])]
    knowledge_suggestions = raw.get("knowledge_suggestions", [])
    criteria = list(raw.get("protocol_criteria", []))
    metrics = raw.get("metrics", {})

    expected_collection = _collection_for_action(action)
    if recommended_collection != expected_collection:
        raise ValidationError("recommendation_action does not match recommended_collection")

    _validate_article_type_tags(article_type=article_type, review_type=review_type, subject_tags=subject_tags)
    _validate_criteria_for_article_type(stage=stage, article_type=article_type, criteria=criteria)
    score = _validate_metrics_against_criteria(metrics, criteria)
    _validate_stage_gate(stage=stage, article_type=article_type, action=action, gate_result=str(raw["gate_result"]), score=score)
    _validate_discard_policy(action=action, recommended_tags=recommended_tags, subject_tags=subject_tags, knowledge_suggestions=knowledge_suggestions)
    _validate_recommended_tags(action=action, recommended_tags=recommended_tags)
    if stage == Stage.TO_LOOK and knowledge_suggestions:
        raise ValidationError("ToLook output must keep knowledge_suggestions empty")
    _add_decision_warnings(raw, stage=stage, action=action, score=score)


def _collection_for_action(action: str) -> Stage:
    mapping = {
        "move_to_revise": Stage.TO_REVISE,
        "keep_in_revise": Stage.TO_REVISE,
        "move_to_dig": Stage.TO_DIG,
        "keep_in_dig": Stage.TO_DIG,
        "move_to_expendable": Stage.EXPENDABLE,
    }
    return mapping[action]


def _validate_article_type_tags(*, article_type: str, review_type: str, subject_tags: list[str]) -> None:
    review_tags = {"%narrative-review", "%systematic-review", "%scoping-review", "%meta-analysis"}
    used_review_tags = review_tags.intersection(subject_tags)
    if used_review_tags and article_type != "review":
        raise ValidationError("review tag requires article_type review")
    if article_type == "review":
        if not used_review_tags:
            raise ValidationError("review article requires a review method tag")
        expected = f"%{review_type}"
        if review_type == "none" or expected not in used_review_tags:
            raise ValidationError("review_type must match a recommended review method tag")
    elif review_type != "none":
        raise ValidationError("article_type original requires review_type none")


def _validate_criteria_for_article_type(*, stage: Stage, article_type: str, criteria: list[dict[str, Any]]) -> None:
    if stage == Stage.TO_LOOK:
        expected = {item.id for item in criteria_for_stage(Stage.TO_LOOK)}
    elif article_type == "review":
        expected = {
            "defines_state_of_art",
            "identifies_actionable_gaps",
            "selective_and_transparent_review",
            "reference_mining_value",
            "positions_extension_or_rebuttal",
        }
    else:
        expected = {
            "new_method_for_toolkit",
            "reproducible_equations_and_parameters",
            "validated_results",
            "domain_applicability",
            "paper_section_value",
        }
    actual = {str(item.get("criterion_id")) for item in criteria}
    if actual != expected:
        if stage != Stage.TO_LOOK and article_type == "review":
            raise ValidationError("article_type review requires review ToDig criteria")
        if stage != Stage.TO_LOOK:
            raise ValidationError("article_type original requires original ToDig criteria")
        raise ValidationError("ToLook requires To Review criteria")


def _validate_metrics_against_criteria(metrics: dict[str, Any], criteria: list[dict[str, Any]]) -> float:
    weights = {"yes": 1.0, "partial": 0.5, "no": 0.0, "unknown": 0.0}
    statuses = [str(item.get("status", "unknown")) for item in criteria]
    criteria_met = statuses.count("yes")
    criteria_total = len(statuses)
    weighted_score = sum(weights[status] for status in statuses)
    criteria_score = weighted_score / criteria_total if criteria_total else 0.0
    if int(metrics.get("criteria_met", -1)) != criteria_met:
        raise ValidationError("metrics.criteria_met does not match protocol_criteria")
    if int(metrics.get("criteria_total", -1)) != criteria_total:
        raise ValidationError("metrics.criteria_total does not match protocol_criteria")
    if abs(float(metrics.get("criteria_score", -1)) - criteria_score) > 0.001:
        raise ValidationError("metrics.criteria_score does not match protocol_criteria")
    return weighted_score


def _validate_stage_gate(*, stage: Stage, article_type: str, action: str, gate_result: str, score: float) -> None:
    if stage == Stage.TO_LOOK:
        if score >= 3:
            if action != "move_to_revise" or gate_result != "pass":
                raise ValidationError("ToLook pass gate requires move_to_revise")
        elif action != "move_to_expendable" or gate_result != "fail":
            raise ValidationError("ToLook fail gate requires move_to_expendable")
        return
    if stage == Stage.TO_REVISE:
        if score == 5:
            if action != "move_to_dig" or gate_result != "pass":
                kind = "review" if article_type == "review" else "original"
                raise ValidationError(f"To Revise {kind} hard gate requires move_to_dig")
        elif action == "move_to_dig":
            raise ValidationError("move_to_dig requires all five ToDig criteria yes")


def _validate_recommended_tags(*, action: str, recommended_tags: list[str]) -> None:
    expected_stage_tag = {
        "move_to_revise": "@review",
        "keep_in_revise": "@review",
        "move_to_dig": "@dig",
        "keep_in_dig": "@dig",
    }.get(action)
    if expected_stage_tag and expected_stage_tag not in recommended_tags:
        raise ValidationError(f"{action} requires {expected_stage_tag}")


def _validate_discard_policy(
    *,
    action: str,
    recommended_tags: list[str],
    subject_tags: list[str],
    knowledge_suggestions: Any,
) -> None:
    if action == "move_to_expendable" and "!discarded" not in recommended_tags:
        raise ValidationError("move_to_expendable requires !discarded")
    if action != "move_to_expendable" and "!discarded" in recommended_tags:
        raise ValidationError("!discarded requires move_to_expendable")
    if action != "move_to_expendable":
        return
    if knowledge_suggestions:
        raise ValidationError("move_to_expendable conflicts with knowledge_suggestions")
    blocking_tags = {
        "@review",
        "@dig",
        "$background",
        "$gap-signal",
        "$methods-cite",
        "$discussion",
        "$extend",
        "$paper-01",
        "$paper-02",
        "!seminal",
        "!high-impact",
        "!data-available",
    }
    if blocking_tags.intersection([*recommended_tags, *subject_tags]):
        raise ValidationError("move_to_expendable conflicts with blocking tags")


def _add_decision_warnings(raw: dict[str, Any], *, stage: Stage, action: str, score: float) -> None:
    metrics = raw.setdefault("metrics", {})
    warnings = list(metrics.get("warnings", []))
    if float(metrics.get("evidence_coverage", 1.0)) < 0.3:
        warnings.append("low evidence_coverage")
    if float(raw.get("confidence", 1.0)) < 0.4 and action in {"move_to_revise", "move_to_dig", "keep_in_dig"}:
        warnings.append("low confidence for strong recommendation")
    if float(raw.get("article_type_confidence", 1.0)) < 0.6:
        warnings.append("low article_type_confidence")
    if stage == Stage.TO_REVISE and 0 < score < 5 and any(
        str(item.get("status")) == "partial" for item in raw.get("protocol_criteria", [])
    ):
        warnings.append("partial criterion on hard ToDig gate")
    if warnings:
        metrics["warnings"] = _dedupe_list(warnings)


def _normalize_metrics(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    raw = dict(value)
    for key in ["criteria_score", "evidence_coverage"]:
        if key not in raw:
            continue
        try:
            number = float(raw[key])
        except (TypeError, ValueError):
            continue
        if number > 10:
            number = number / 100
        elif number > 1:
            number = number / 10
        raw[key] = max(0, min(1, number))
    return raw


def _dedupe_protocol_criteria(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    seen = set()
    items = []
    for item in value:
        if not isinstance(item, dict):
            items.append(item)
            continue
        key = item.get("criterion_id")
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def _dedupe_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    seen = set()
    items = []
    for item in value:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else item
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def _repair_obj(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _repair_obj(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_obj(item) for item in value]
    if isinstance(value, str):
        return _repair_mojibake(value)
    return value


def _repair_mojibake(value: str) -> str:
    if ("Ã" in value or "Â" in value) and "Ãƒ" not in value and "Ã‚" not in value:
        try:
            repaired = value.encode("latin-1").decode("utf-8")
        except UnicodeError:
            return value
        return repaired if repaired.count("ï¿½") <= value.count("ï¿½") else value
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
    return repaired if repaired.count("�") <= value.count("�") else value


def _parse_stage(value: Any, *, field: str) -> Stage:
    try:
        return Stage(value)
    except ValueError as exc:
        raise ValidationError(f"invalid LLM {field}: {value}") from exc
