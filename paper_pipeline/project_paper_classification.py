from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from .contracts import PipelineError, ValidationError
from .registry import load_jsonl
from .schema_validation import load_schema, validate_instance

CLASSIFICATION_PROMPT_VERSION = "project_paper_classify_v1"
CLASSIFICATION_PROMPT_HASH = "sha256:" + hashlib.sha256(CLASSIFICATION_PROMPT_VERSION.encode("utf-8")).hexdigest()
CLASSIFICATION_INPUT_LAYER = "metadata"


class ChatJsonClient(Protocol):
    def complete_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str: ...


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


def write_classifications_jsonl(output_path: str | Path, classifications: Iterable[dict[str, Any]]) -> Path:
    path = Path(output_path)
    validated = [validate_instance(classification, "llm_classification.schema.json") for classification in classifications]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for classification in validated:
            handle.write(json.dumps(classification, ensure_ascii=False, sort_keys=True) + "\n")
    tmp_path.replace(path)
    return path


def run_classify_from_jsonl(
    *,
    candidates_path: str | Path,
    projects_path: str | Path,
    papers_path: str | Path,
    output_path: str | Path,
    client: ChatJsonClient,
    max_attempts: int = 2,
) -> list[dict[str, Any]]:
    candidates, _candidate_warnings = load_jsonl(candidates_path, artifact_name="candidates")
    projects, _project_warnings = load_jsonl(projects_path, artifact_name="projects")
    papers, _paper_warnings = load_jsonl(papers_path, artifact_name="papers")

    candidate_rows = [validate_instance(candidate, "project_paper_match.schema.json") for candidate in candidates]
    project_rows = {row["project_id"]: validate_instance(row, "project_profile.schema.json") for row in projects}
    paper_rows = {row["citekey"]: validate_instance(row, "paper_profile.schema.json") for row in papers}

    schema = load_schema("llm_classification.schema.json")
    classifications: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        project = project_rows.get(candidate["project_id"])
        if project is None:
            raise PipelineError(f"classify input missing project: {candidate['project_id']}")
        paper = paper_rows.get(candidate["citekey"])
        if paper is None:
            raise PipelineError(f"classify input missing paper: {candidate['citekey']}")
        classifications.append(
            classify_project_paper_candidate(
                candidate=candidate,
                project=project,
                paper=paper,
                client=client,
                schema=schema,
                max_attempts=max_attempts,
            )
        )
    write_classifications_jsonl(output_path, classifications)
    return classifications


def classify_project_paper_candidate(
    *,
    candidate: dict[str, Any],
    project: dict[str, Any],
    paper: dict[str, Any],
    client: ChatJsonClient,
    schema: dict[str, Any] | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    classification_schema = schema or load_schema("llm_classification.schema.json")
    messages = build_classification_messages(project=project, paper=paper, candidate=candidate)
    errors: list[str] = []

    for _attempt in range(max_attempts):
        try:
            response = client.complete_json(messages, classification_schema)
            response_text = _accepted_classification_text(response)
            parsed = parse_llm_classification(response_text)
            managed = _managed_fields(candidate=candidate, paper=paper)
            normalized = validate_instance({**parsed.raw, **managed}, "llm_classification.schema.json")
            return normalized
        except Exception as exc:
            errors.append(str(exc))
            messages.append(
                {
                    "role": "user",
                    "content": "Return exactly one valid JSON object matching the schema. No prose before or after JSON.",
                }
            )
    raise PipelineError(
        "classify failed for "
        f"{candidate['project_id']} -> {candidate['citekey']}: {errors[-1]}"
    )


def build_classification_messages(
    *,
    project: dict[str, Any],
    paper: dict[str, Any],
    candidate: dict[str, Any],
) -> list[dict[str, str]]:
    packet = {
        "project": {
            "project_id": project["project_id"],
            "title": project["title"],
            "objectives": project.get("objectives", []),
            "methods": project.get("methods", []),
            "knowledge_gaps": project.get("knowledge_gaps", []),
            "expected_outputs": project.get("expected_outputs", []),
            "priority": project.get("priority"),
            "project_state": project.get("project_state"),
            "tags": project.get("tags", []),
        },
        "paper": {
            "citekey": paper["citekey"],
            "title": paper["title"],
            "abstract": paper.get("abstract", ""),
            "year": paper.get("year"),
            "authors": paper.get("authors", []),
            "collections": paper.get("collections", []),
            "tags": paper.get("tags", []),
            "doi": paper.get("doi"),
            "has_pdf": paper.get("has_pdf", False),
            "metadata_snapshot_path": paper.get("metadata_snapshot_path"),
        },
        "candidate": {
            "candidate_score": candidate["candidate_score"],
            "rank": candidate["rank"],
            "evidence": candidate.get("evidence", []),
            "method": candidate.get("method"),
            "created_at": candidate.get("created_at"),
        },
        "managed_fields": {
            "project_id": candidate["project_id"],
            "citekey": candidate["citekey"],
            "prompt_hash": CLASSIFICATION_PROMPT_HASH,
            "input_layer": CLASSIFICATION_INPUT_LAYER,
            "input_products": _input_products(paper),
            "current_zotero_stage": _current_zotero_stage(paper),
            "requires_human_review": True,
        },
    }
    packet_json = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    return [
        {
            "role": "system",
            "content": (
                "You classify how useful one paper is for one project. "
                "Return exactly one valid JSON object and no prose. "
                "Use metadata-only evidence. Do not rely on PDF content. "
                "Do not invent citekeys or project ids."
            ),
        },
        {
            "role": "user",
            "content": (
                "Assess project-paper utility for the provided packet. "
                "Choose utility class, recommended action, confidence, stage recommendation, "
                "scores, reason, possible uses, limitations, gate results, and reading protocol evidence. "
                "Keep requires_human_review true. Packet JSON: "
                f"{packet_json}"
            ),
        },
    ]


def _managed_fields(*, candidate: dict[str, Any], paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": candidate["project_id"],
        "citekey": candidate["citekey"],
        "prompt_hash": CLASSIFICATION_PROMPT_HASH,
        "input_layer": CLASSIFICATION_INPUT_LAYER,
        "input_products": _input_products(paper),
        "current_zotero_stage": _current_zotero_stage(paper),
        "requires_human_review": True,
    }


def _input_products(paper: dict[str, Any]) -> list[str]:
    metadata_snapshot_path = str(paper.get("metadata_snapshot_path") or "").strip()
    return [metadata_snapshot_path] if metadata_snapshot_path else [f"papers/{paper['citekey']}/metadata_snapshot.json"]


def _current_zotero_stage(paper: dict[str, Any]) -> str:
    collections = [str(item) for item in paper.get("collections", [])]
    for stage in (".ToLook", ".To Revise", ".ToDig", "Expendable"):
        if stage in collections:
            return stage
    return ".ToLook"


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


def _accepted_classification_text(response: object) -> str:
    errors: list[str] = []
    for channel, text in (
        ("content", str(response)),
        ("reasoning_content", str(getattr(response, "reasoning_content", "") or "")),
    ):
        try:
            parse_llm_classification(text)
        except Exception as exc:
            errors.append(f"{channel}: {exc}")
            continue
        return text
    raise ValidationError(
        "LLM classification output must be a single JSON object without prose"
        if not errors
        else "; ".join(errors)
    )


__all__ = [
    "CLASSIFICATION_PROMPT_HASH",
    "CLASSIFICATION_PROMPT_VERSION",
    "LLMClassification",
    "append_validated_classification",
    "build_classification_messages",
    "classify_project_paper_candidate",
    "parse_llm_classification",
    "run_classify_from_jsonl",
    "write_classifications_jsonl",
]
