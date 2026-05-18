from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Iterable

from .contracts import PipelineError
from .registry import load_jsonl, should_process_pair
from .schema_validation import validate_instance


DEFAULT_MATCH_STATES = ("on", "ongoing")
LEXICAL_PROMPT_HASH = "sha256:lexical_v1"
STOPWORDS = {
    "and",
    "the",
    "with",
    "using",
    "for",
    "from",
    "into",
    "uma",
    "para",
    "com",
    "dos",
    "das",
    "que",
    "por",
    "em",
    "de",
    "do",
    "da",
}


@dataclass(frozen=True)
class MatchReport:
    warnings: list[str] = field(default_factory=list)
    skipped_projects: dict[str, int] = field(default_factory=dict)
    skipped_pairs: int = 0


def build_project_text(project: dict[str, Any]) -> str:
    parts = [
        project.get("title", ""),
        *project.get("objectives", []),
        *project.get("methods", []),
        *project.get("knowledge_gaps", []),
        *project.get("expected_outputs", []),
        *project.get("tags", []),
    ]
    return " ".join(str(part) for part in parts if str(part).strip())


def build_paper_text(paper: dict[str, Any]) -> str:
    parts = [
        paper.get("title", ""),
        paper.get("abstract", ""),
        *paper.get("tags", []),
        *paper.get("collections", []),
    ]
    return " ".join(str(part) for part in parts if str(part).strip())


def score_project_paper(
    project: dict[str, Any], paper: dict[str, Any]
) -> tuple[float, list[str]]:
    project_text = _normalize(build_project_text(project))
    paper_text = _normalize(build_paper_text(paper))
    primary_paper_text = _normalize(
        " ".join([str(paper.get("title", "")), str(paper.get("abstract", ""))])
    )
    project_tokens = _tokens(project_text)
    paper_tokens = _tokens(paper_text)
    primary_paper_tokens = _tokens(primary_paper_text)
    token_overlap = sorted(set(project_tokens) & set(paper_tokens))
    primary_token_overlap = sorted(set(project_tokens) & set(primary_paper_tokens))
    phrase_overlap = _phrase_overlap(project_tokens, paper_text)
    primary_phrase_overlap = _phrase_overlap(project_tokens, primary_paper_text)
    evidence = [
        f"{phrase} appears in project and paper title/abstract"
        for phrase in primary_phrase_overlap
    ]
    evidence.extend(
        f"{phrase} appears in project and paper metadata"
        for phrase in phrase_overlap
        if phrase not in primary_phrase_overlap
    )
    phrase_words = _phrase_words(phrase_overlap)
    evidence.extend(
        f"{token} appears in project and paper title/abstract"
        for token in primary_token_overlap
        if token not in phrase_words
    )
    evidence.extend(
        f"{token} appears in project and paper metadata"
        for token in token_overlap
        if token not in phrase_words and token not in primary_token_overlap
    )
    evidence = evidence[:8]
    if not evidence:
        return 0, []
    score = min(
        1.0,
        round(
            (0.25 * len(primary_phrase_overlap))
            + (0.08 * len(phrase_overlap))
            + (0.05 * len(primary_token_overlap))
            + (0.02 * len(token_overlap)),
            4,
        ),
    )
    return score, evidence


def match_project_papers(
    projects: Iterable[dict[str, Any]],
    papers: Iterable[dict[str, Any]],
    *,
    include_states: tuple[str, ...] = DEFAULT_MATCH_STATES,
    paper_stages: tuple[str, ...] | None = None,
    top_n: int = 20,
    max_candidates_total: int | None = None,
    now: str | None = None,
    registry_db: str | Path | None = None,
) -> tuple[list[dict[str, Any]], MatchReport]:
    if top_n <= 0:
        raise PipelineError("top_n must be positive")
    if max_candidates_total is not None and max_candidates_total <= 0:
        raise PipelineError("max_candidates_total must be positive")
    project_rows = [
        validate_instance(project, "project_profile.schema.json")
        for project in projects
    ]
    paper_rows = [
        validate_instance(paper, "paper_profile.schema.json") for paper in papers
    ]
    filtered_paper_rows = [
        paper
        for paper in paper_rows
        if paper_stages is None or _current_zotero_stage(paper) in paper_stages
    ]
    created_at = now or _now()
    warnings: list[str] = []
    skipped_projects: Counter[str] = Counter()
    skipped_pairs = 0
    conn = sqlite3.connect(registry_db) if registry_db else None
    if conn is not None:
        conn.execute("pragma foreign_keys = on")
    candidates: list[dict[str, Any]] = []
    try:
        for project in project_rows:
            state = project["project_state"]
            if state not in include_states:
                skipped_projects[state] += 1
                continue
            scored: list[dict[str, Any]] = []
            for paper in filtered_paper_rows:
                if conn is not None:
                    decision = should_process_pair(
                        conn,
                        project_id=project["project_id"],
                        citekey=paper["citekey"],
                        project_hash=project["content_hash"],
                        paper_hash=paper["paper_hash"],
                        prompt_hash=LEXICAL_PROMPT_HASH,
                    )
                    if not decision.should_process:
                        skipped_pairs += 1
                        warnings.append(
                            f"skipped unchanged pair: {project['project_id']} -> {paper['citekey']}"
                        )
                        continue
                    warnings.extend(decision.warnings)
                score, evidence = score_project_paper(project, paper)
                if score <= 0:
                    continue
                scored.append(
                    {
                        "project_id": project["project_id"],
                        "citekey": paper["citekey"],
                        "candidate_score": score,
                        "evidence": evidence,
                        "method": "lexical_v1",
                        "created_at": created_at,
                    }
                )
            for rank, candidate in enumerate(
                sorted(scored, key=_candidate_sort_key)[:top_n], start=1
            ):
                candidate["rank"] = rank
                candidates.append(
                    validate_instance(candidate, "project_paper_match.schema.json")
                )
    finally:
        if conn is not None:
            conn.close()
    if max_candidates_total is not None:
        candidates = sorted(candidates, key=_candidate_sort_key)[:max_candidates_total]
    return candidates, MatchReport(
        warnings=list(dict.fromkeys(warnings)),
        skipped_projects=dict(skipped_projects),
        skipped_pairs=skipped_pairs,
    )


def write_candidates_jsonl(
    output_path: str | Path, candidates: Iterable[dict[str, Any]]
) -> Path:
    path = Path(output_path)
    validated = [
        validate_instance(candidate, "project_paper_match.schema.json")
        for candidate in candidates
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for candidate in validated:
            handle.write(
                json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n"
            )
    tmp_path.replace(path)
    return path


def run_match_from_jsonl(
    *,
    projects_path: str | Path,
    papers_path: str | Path,
    output_path: str | Path,
    include_states: tuple[str, ...] = DEFAULT_MATCH_STATES,
    paper_stages: tuple[str, ...] | None = None,
    top_n: int = 20,
    max_candidates_total: int | None = None,
    registry_db: str | Path | None = None,
) -> tuple[list[dict[str, Any]], MatchReport]:
    projects, _project_warnings = load_jsonl(projects_path, artifact_name="projects")
    papers, _paper_warnings = load_jsonl(papers_path, artifact_name="papers")
    candidates, report = match_project_papers(
        projects,
        papers,
        include_states=include_states,
        paper_stages=paper_stages,
        top_n=top_n,
        max_candidates_total=max_candidates_total,
        registry_db=registry_db,
    )
    write_candidates_jsonl(output_path, candidates)
    return candidates, report


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, str, str]:
    return (
        -float(candidate["candidate_score"]),
        str(candidate["project_id"]),
        str(candidate["citekey"]),
    )


def _current_zotero_stage(paper: dict[str, Any]) -> str:
    collections = [str(item) for item in paper.get("collections", [])]
    for stage in (".ToLook", ".To Revise", ".ToDig", "Expendable"):
        if stage in collections:
            return stage
    return ".ToLook"


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_value = ascii_value.replace("#", " ").replace("%", " ")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


def _tokens(value: str) -> list[str]:
    return [
        token for token in value.split() if len(token) >= 3 and token not in STOPWORDS
    ]


def _phrase_overlap(project_tokens: list[str], paper_text: str) -> list[str]:
    phrases = []
    for left, right in zip(project_tokens, project_tokens[1:]):
        phrase = f"{left} {right}"
        if phrase in paper_text and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _phrase_words(phrases: list[str]) -> set[str]:
    words: set[str] = set()
    for phrase in phrases:
        words.update(phrase.split())
    return words


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


__all__ = [
    "DEFAULT_MATCH_STATES",
    "MatchReport",
    "build_paper_text",
    "build_project_text",
    "match_project_papers",
    "run_match_from_jsonl",
    "score_project_paper",
    "write_candidates_jsonl",
]
