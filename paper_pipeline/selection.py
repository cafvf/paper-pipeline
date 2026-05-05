from __future__ import annotations

from dataclasses import dataclass, field
import re

from .contracts import OPERATIONAL_LLM_TAGS, Stage
from .vault_index import search_lexical


@dataclass(frozen=True)
class CandidatePaper:
    citekey: str
    stage: Stage
    title: str
    abstract: str = ""
    tags: list[str] = field(default_factory=list)
    publication_year: int | None = None
    has_pdf: bool = False
    pdf_paths: list[str] = field(default_factory=list)
    doi: str = ""
    source_type: str = ""
    journal: str = ""
    authors: list[str] = field(default_factory=list)
    zotero_item_key: str = field(default="", compare=False)
    collection_keys: list[str] = field(default_factory=list, compare=False)


DEFAULT_QUOTAS = {
    Stage.TO_LOOK: 5,
    Stage.TO_REVISE: 4,
    Stage.TO_DIG: 1,
}


def score_candidate(candidate: CandidatePaper, lexical_index: dict) -> int:
    text = " ".join(
        [
            candidate.title,
            candidate.abstract,
            " ".join(candidate.tags),
            candidate.journal,
            " ".join(candidate.authors),
            candidate.stage.value,
        ]
    )
    score = 0
    matches = search_lexical(lexical_index, text, limit=5)
    if matches:
        score += min(60, sum(int(match.get("weight", 0) or 0) for match in matches[:3]))
    if candidate.doi and re.match(r"^10\.\S+/\S+$", candidate.doi.strip(), re.I):
        score += 5
    if _looks_review(candidate):
        score += 10
    if candidate.publication_year:
        if candidate.publication_year >= 2016:
            score += 10
        elif candidate.publication_year < 2000 and not _looks_review(candidate):
            score -= 5
    if _outside_domain(text):
        score -= 20
    return max(0, min(100, score))


def select_batch(
    candidates: list[CandidatePaper],
    lexical_index: dict,
    *,
    quotas: dict[Stage, int] | None = None,
    max_total: int = 10,
) -> dict:
    quotas = quotas or DEFAULT_QUOTAS
    eligible = [candidate for candidate in candidates if not _has_same_layer_tag(candidate)]
    scored = [
        {
            "candidate": candidate,
            "score": score_candidate(candidate, lexical_index),
        }
        for candidate in eligible
    ]
    selected: list[dict] = []
    blocked_missing_pdf: list[dict] = []

    for stage in [Stage.TO_DIG, Stage.TO_REVISE, Stage.TO_LOOK]:
        selected.extend(_select_stage(scored, stage, quotas.get(stage, 0), blocked_missing_pdf))

    remaining_slots = max_total - len(selected)
    if remaining_slots > 0:
        for stage in [Stage.TO_DIG, Stage.TO_REVISE, Stage.TO_LOOK]:
            selected.extend(_select_stage(scored, stage, remaining_slots, blocked_missing_pdf, already=selected))
            remaining_slots = max_total - len(selected)
            if remaining_slots <= 0:
                break

    return {
        "selected": selected[:max_total],
        "blocked_missing_pdf": blocked_missing_pdf,
    }


def _select_stage(
    scored: list[dict],
    stage: Stage,
    count: int,
    blocked_missing_pdf: list[dict],
    already: list[dict] | None = None,
) -> list[dict]:
    if count <= 0:
        return []
    already_keys = {entry["candidate"].citekey for entry in (already or [])}
    stage_items = [entry for entry in scored if entry["candidate"].stage == stage and entry["candidate"].citekey not in already_keys]
    ordered = sorted(stage_items, key=_sort_key, reverse=True)
    selected: list[dict] = []
    deferred: list[dict] = []
    seen_topics: set[str] = set()
    for entry in ordered:
        candidate = entry["candidate"]
        if len(selected) >= count:
            break
        if not candidate.has_pdf:
            if candidate.citekey not in {item["candidate"].citekey for item in blocked_missing_pdf}:
                blocked_missing_pdf.append(entry)
            continue
        topic = _topic_key(candidate)
        if topic in seen_topics and any(abs(entry["score"] - other["score"]) <= 5 for other in selected):
            deferred.append(entry)
            continue
        selected.append(entry)
        seen_topics.add(topic)

    if len(selected) < count:
        selected_keys = {entry["candidate"].citekey for entry in selected}
        for entry in deferred:
            if len(selected) >= count:
                break
            if entry["candidate"].citekey not in selected_keys:
                selected.append(entry)
                selected_keys.add(entry["candidate"].citekey)
    return selected


def _sort_key(entry: dict) -> tuple:
    candidate = entry["candidate"]
    return (
        1 if candidate.has_pdf else 0,
        entry["score"],
        candidate.publication_year or 0,
    )


def _has_same_layer_tag(candidate: CandidatePaper) -> bool:
    tag = OPERATIONAL_LLM_TAGS.get(candidate.stage)
    return bool(tag and tag in candidate.tags)


def _looks_review(candidate: CandidatePaper) -> bool:
    text = f"{candidate.source_type} {candidate.title} {candidate.abstract}".lower()
    return "review" in text or "state of the art" in text or "meta-analysis" in text


def _outside_domain(text: str) -> bool:
    lowered = text.lower()
    domain_terms = ["soil", "geotech", "cpt", "offshore", "bayesian", "reliability", "rock", "foundation", "uncertainty"]
    return not any(term in lowered for term in domain_terms)


def _topic_key(candidate: CandidatePaper) -> str:
    text = " ".join(candidate.tags + [candidate.title]).lower()
    for token in ["cpt", "bayesian", "kriging", "offshore", "classification", "reliability", "rock"]:
        if token in text:
            return token
    return candidate.citekey
