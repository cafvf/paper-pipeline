from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Protocol

from .contracts import PipelineError, ValidationError
from .registry import load_jsonl
from .schema_validation import load_schema, validate_instance

CLASSIFICATION_PROMPT_VERSION = "project_paper_classify_v1"
CLASSIFICATION_PROMPT_HASH = (
    "sha256:"
    + hashlib.sha256(CLASSIFICATION_PROMPT_VERSION.encode("utf-8")).hexdigest()
)
CLASSIFICATION_INPUT_LAYER = "metadata"
HIGH_UTILITY_CLASSES = {
    "essential",
    "methodological",
    "formulational",
    "implementable",
}
ACTIVE_READING_ACTIONS = {
    "read_now",
    "read_later",
    "extract_equations",
    "reproduce_code",
    "link_to_project",
}
DEEP_TECHNICAL_ACTIONS = {"extract_equations", "reproduce_code"}


class ChatJsonClient(Protocol):
    def complete_json(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> str: ...


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
    validate_classification_coherence(raw)
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


def append_validated_classification(
    text: str, output_path: str | Path
) -> LLMClassification:
    classification = parse_llm_classification(text)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(classification.raw, ensure_ascii=False, sort_keys=True) + "\n"
        )
    return classification


def write_classifications_jsonl(
    output_path: str | Path, classifications: Iterable[dict[str, Any]]
) -> Path:
    path = Path(output_path)
    validated = [
        _validate_classification_record(classification)
        for classification in classifications
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for classification in validated:
            handle.write(
                json.dumps(classification, ensure_ascii=False, sort_keys=True) + "\n"
            )
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
    paper_stages: tuple[str, ...] | None = None,
    max_candidates: int | None = None,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    if max_candidates is not None and max_candidates <= 0:
        raise PipelineError("max_candidates must be positive")
    candidates, _candidate_warnings = load_jsonl(
        candidates_path, artifact_name="candidates"
    )
    projects, _project_warnings = load_jsonl(projects_path, artifact_name="projects")
    papers, _paper_warnings = load_jsonl(papers_path, artifact_name="papers")

    candidate_rows = [
        validate_instance(candidate, "project_paper_match.schema.json")
        for candidate in candidates
    ]
    project_rows = {
        row["project_id"]: validate_instance(row, "project_profile.schema.json")
        for row in projects
    }
    paper_rows = {
        row["citekey"]: validate_instance(row, "paper_profile.schema.json")
        for row in papers
    }
    selected_candidates = [
        candidate
        for candidate in candidate_rows
        if _candidate_in_allowed_stages(
            candidate,
            paper_rows=paper_rows,
            paper_stages=paper_stages,
        )
    ]
    if max_candidates is not None:
        selected_candidates = selected_candidates[:max_candidates]

    schema = load_schema("llm_classification.schema.json")
    classifications: list[dict[str, Any]] = []
    tracker = _ClassificationProgressTracker(
        output_path, total_candidates=len(selected_candidates)
    )
    tracker.start()
    try:
        for index, candidate in enumerate(selected_candidates, start=1):
            project = project_rows.get(candidate["project_id"])
            if project is None:
                raise PipelineError(
                    f"classify input missing project: {candidate['project_id']}"
                )
            paper = paper_rows.get(candidate["citekey"])
            if paper is None:
                raise PipelineError(
                    f"classify input missing paper: {candidate['citekey']}"
                )
            classification = classify_project_paper_candidate(
                candidate=candidate,
                project=project,
                paper=paper,
                client=client,
                schema=schema,
                max_attempts=max_attempts,
            )
            classifications.append(classification)
            tracker.record_completed(index=index, classification=classification)
            if progress_callback is not None:
                progress_callback(index, len(selected_candidates), classification)
    except Exception as exc:
        tracker.mark_failed(error=str(exc))
        raise
    write_classifications_jsonl(output_path, classifications)
    tracker.mark_complete()
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
    messages = build_classification_messages(
        project=project, paper=paper, candidate=candidate
    )
    errors: list[str] = []

    for _attempt in range(max_attempts):
        try:
            response = client.complete_json(messages, classification_schema)
            response_text = _accepted_classification_text(response)
            parsed = parse_llm_classification(response_text)
            managed = _managed_fields(candidate=candidate, paper=paper)
            normalized = _validate_classification_record({**parsed.raw, **managed})
            return normalized
        except Exception as exc:
            errors.append(str(exc))
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Previous output failed validation: "
                        f"{exc}. "
                        "Return exactly one valid JSON object matching the schema. "
                        "No prose before or after JSON. "
                        "Fix the violated coherence rule instead of repeating it."
                    ),
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
                "Do not invent citekeys or project ids. "
                "Keep utility, action, and stage recommendation semantically coherent. "
                "Useful papers must not recommend Expendable. "
                "Expendable is valid only for irrelevant_now plus ignore_for_now. "
                "extract_equations and reproduce_code require .ToDig. "
                "Do not demote papers already in .To Revise or .ToDig in this metadata-only pass."
            ),
        },
        {
            "role": "user",
            "content": (
                "Assess project-paper utility for the provided packet. "
                "Choose utility class, recommended action, confidence, stage recommendation, "
                "scores, reason, possible uses, limitations, gate results, and reading protocol evidence. "
                "The stage recommendation is secondary to project utility and must remain coherent: "
                "useful outcomes stay active, Expendable is only for irrelevant_now/ignore_for_now, "
                "technical extraction actions require .ToDig, and metadata-only classification must not demote "
                "papers already in deeper stages. "
                "Keep requires_human_review true. Packet JSON: "
                f"{packet_json}"
            ),
        },
    ]


def _managed_fields(
    *, candidate: dict[str, Any], paper: dict[str, Any]
) -> dict[str, Any]:
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
    return (
        [metadata_snapshot_path]
        if metadata_snapshot_path
        else [f"papers/{paper['citekey']}/metadata_snapshot.json"]
    )


def _current_zotero_stage(paper: dict[str, Any]) -> str:
    collections = [str(item) for item in paper.get("collections", [])]
    for stage in (".ToLook", ".To Revise", ".ToDig", "Expendable"):
        if stage in collections:
            return stage
    return ".ToLook"


def _candidate_in_allowed_stages(
    candidate: dict[str, Any],
    *,
    paper_rows: dict[str, dict[str, Any]],
    paper_stages: tuple[str, ...] | None,
) -> bool:
    if paper_stages is None:
        return True
    paper = paper_rows.get(str(candidate.get("citekey") or ""))
    if paper is None:
        return True
    return _current_zotero_stage(paper) in paper_stages


def validate_classification_coherence(classification: dict[str, Any]) -> dict[str, Any]:
    utility = str(classification.get("utility_class") or "")
    action = str(classification.get("recommended_action") or "")
    recommended_stage = str(classification.get("recommended_zotero_stage") or "")
    current_stage = str(classification.get("current_zotero_stage") or "")

    if utility == "irrelevant_now" and action != "ignore_for_now":
        raise ValidationError("irrelevant_now must use ignore_for_now")
    if action == "ignore_for_now":
        if utility != "irrelevant_now":
            raise ValidationError(
                "ignore_for_now is only valid for irrelevant_now classifications"
            )
        if recommended_stage not in {".ToLook", "Expendable"}:
            raise ValidationError("ignore_for_now must recommend .ToLook or Expendable")

    if recommended_stage == "Expendable":
        if utility != "irrelevant_now" or action != "ignore_for_now":
            raise ValidationError(
                "useful classifications must not recommend Expendable"
            )
        if current_stage in {".To Revise", ".ToDig"}:
            raise ValidationError(
                f"metadata-only classification must not demote {current_stage} to Expendable"
            )

    if utility in HIGH_UTILITY_CLASSES:
        if action not in ACTIVE_READING_ACTIONS:
            raise ValidationError(
                f"{utility} classifications require an active reading action"
            )
        if recommended_stage not in {".To Revise", ".ToDig"}:
            raise ValidationError(
                f"{utility} classifications must recommend .To Revise or .ToDig"
            )

    if action == "read_now" and recommended_stage not in {".To Revise", ".ToDig"}:
        raise ValidationError(
            "read_now requires recommended_zotero_stage .To Revise or .ToDig"
        )
    if action == "read_later" and recommended_stage == "Expendable":
        raise ValidationError("read_later must not recommend Expendable")
    if action == "link_to_project" and recommended_stage == "Expendable":
        raise ValidationError("link_to_project must not recommend Expendable")
    if action == "summarize_only":
        if utility in HIGH_UTILITY_CLASSES:
            raise ValidationError(
                "summarize_only is too weak for high-utility classifications"
            )
        if recommended_stage == ".ToDig":
            raise ValidationError("summarize_only must not recommend .ToDig")

    if action in DEEP_TECHNICAL_ACTIONS and recommended_stage != ".ToDig":
        raise ValidationError(f"{action} requires recommended_zotero_stage .ToDig")

    if current_stage == ".To Revise" and recommended_stage == ".ToLook":
        raise ValidationError(
            "metadata-only classification must not demote .To Revise to .ToLook"
        )
    if current_stage == ".ToDig" and recommended_stage != ".ToDig":
        raise ValidationError("metadata-only classification must not demote .ToDig")

    return classification


def _validate_classification_record(classification: dict[str, Any]) -> dict[str, Any]:
    validated = validate_instance(classification, "llm_classification.schema.json")
    return validate_classification_coherence(validated)


def _load_single_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        raise ValidationError(
            "LLM classification output must be a single JSON object without prose"
        )
    decoder = json.JSONDecoder()
    try:
        loaded, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON output: {exc}") from exc
    if stripped[end:].strip():
        raise ValidationError(
            "LLM classification output must contain exactly one JSON object"
        )
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


@dataclass
class _ClassificationProgressTracker:
    output_path: str | Path
    total_candidates: int

    def __post_init__(self) -> None:
        self.output_path = Path(self.output_path)

    @property
    def items_dir(self) -> Path:
        return self.output_path.parent / self.output_path.stem

    @property
    def progress_path(self) -> Path:
        return self.output_path.parent / f"{self.output_path.stem}.progress.json"

    def start(self) -> None:
        self.items_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.items_dir.exists():
            for path in self.items_dir.glob("*.json"):
                path.unlink()
        else:
            self.items_dir.mkdir(parents=True, exist_ok=True)
        self._write_progress({"status": "running", "completed_candidates": 0})

    def record_completed(self, *, index: int, classification: dict[str, Any]) -> None:
        filename = f"{index:04d}__{_artifact_slug(classification['project_id'])}__{_artifact_slug(classification['citekey'])}.json"
        item_path = self.items_dir / filename
        _write_json_atomic(item_path, classification)
        self._write_progress(
            {
                "status": "running",
                "completed_candidates": index,
                "last_completed": {
                    "project_id": classification["project_id"],
                    "citekey": classification["citekey"],
                    "artifact_path": str(item_path.as_posix()),
                },
            }
        )

    def mark_failed(self, *, error: str) -> None:
        completed = self._completed_candidates()
        last_completed = self._last_completed()
        self._write_progress(
            {
                "status": "failed",
                "completed_candidates": completed,
                "error": error,
                **({"last_completed": last_completed} if last_completed else {}),
            }
        )

    def mark_complete(self) -> None:
        completed = self._completed_candidates()
        last_completed = self._last_completed()
        self._write_progress(
            {
                "status": "complete",
                "completed_candidates": completed,
                **({"last_completed": last_completed} if last_completed else {}),
            }
        )

    def _write_progress(self, payload: dict[str, Any]) -> None:
        merged = {
            "output_path": str(self.output_path.as_posix()),
            "items_dir": str(self.items_dir.as_posix()),
            "total_candidates": self.total_candidates,
            "updated_at": _utc_timestamp(),
            **payload,
        }
        _write_json_atomic(self.progress_path, merged)

    def _read_progress(self) -> dict[str, Any]:
        if not self.progress_path.exists():
            return {}
        try:
            loaded = json.loads(self.progress_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _completed_candidates(self) -> int:
        return len(list(self.items_dir.glob("*.json")))

    def _last_completed(self) -> dict[str, Any] | None:
        existing = self._read_progress()
        value = existing.get("last_completed")
        return value if isinstance(value, dict) else None


def _artifact_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return slug or "item"


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


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
