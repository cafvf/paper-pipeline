from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .contracts import Stage
from .selection import CandidatePaper
from .zotero_plan import ZoteroActionPlan


@dataclass
class ZoteroItem:
    key: str
    citekey: str
    title: str
    abstract: str = ""
    collections: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    publication_year: int | None = None
    pdf_paths: list[str] = field(default_factory=list)
    doi: str = ""
    source_type: str = ""
    journal: str = ""
    authors: list[str] = field(default_factory=list)


class ZoteroSource(Protocol):
    def list_candidates(self) -> list[CandidatePaper]: ..


class ZoteroPlanWriter(Protocol):
    def apply_plan(self, plan: ZoteroActionPlan) -> dict: ..


class MemoryZoteroAdapter:
    """Small deterministic adapter used by tests and future dry-run fixtures."""

    def __init__(self, items: list[ZoteroItem], collections: list[str] | None = None) -> None:
        self.items_by_key = {item.key: item for item in items}
        self.collections = set(collections or [])
        for item in items:
            self.collections.update(item.collections)

    def list_candidates(self) -> list[CandidatePaper]:
        candidates: list[CandidatePaper] = []
        for item in self.items_by_key.values():
            stage = _stage_from_collections(item.collections)
            if stage is None:
                continue
            candidates.append(
                CandidatePaper(
                    citekey=item.citekey,
                    stage=stage,
                    title=item.title,
                    abstract=item.abstract,
                    tags=list(item.tags),
                    publication_year=item.publication_year,
                    has_pdf=bool(item.pdf_paths),
                    pdf_paths=list(item.pdf_paths),
                    doi=item.doi,
                    source_type=item.source_type,
                    journal=item.journal,
                    authors=list(item.authors),
                    zotero_item_key=item.key,
                    collection_keys=list(item.collections),
                )
            )
        return candidates

    def apply_plan(self, plan: ZoteroActionPlan) -> dict:
        if plan.status == "blocked":
            return {"status": "blocked", "reason": plan.reason}
        if plan.status == "noop":
            return {"status": "noop"}
        item = self.items_by_key.get(plan.item_key)
        if item is None:
            return {"status": "error", "error": f"missing item {plan.item_key}"}
        before = {"collections": list(item.collections), "tags": list(item.tags)}
        for collection in plan.collections_to_set:
            self.collections.add(collection)
        item.collections = list(plan.collections_to_set)
        item.tags = list(plan.final_tags)
        return {"status": "applied", "before": before, "after": {"collections": list(item.collections), "tags": list(item.tags)}}


def _stage_from_collections(collections: list[str]) -> Stage | None:
    for stage in [Stage.TO_DIG, Stage.TO_REVISE, Stage.TO_LOOK, Stage.EXPENDABLE]:
        if stage.value in collections:
            return stage
    return None
