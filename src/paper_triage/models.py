"""Strict, pure Pydantic contracts for normalized papers and classifications."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import Issue


class ItemTypeClass(StrEnum):
    ORIGINAL_CANDIDATE = "original_candidate"
    SUPPORT_OR_NONPAPER = "support_or_nonpaper"
    UNKNOWN = "unknown"


class PaperKind(StrEnum):
    ORIGINAL = "original"
    REVIEW = "review"
    AMBIGUOUS = "ambiguous"


class Stage(StrEnum):
    LOOK = "look"
    REVIEW = "review"
    DIG = "dig"


class Outcome(StrEnum):
    HIGH_CONFIDENCE = "high_confidence"
    NEEDS_REREAD = "needs_reread"
    UNCLASSIFIABLE = "unclassifiable"


class CriterionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class TagAction(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    KEEP = "keep"
    SKIP = "skip"


class CollectionAction(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    KEEP = "keep"
    SKIP = "skip"
    MISSING = "missing"


class Author(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    family: str | None = None
    given: str | None = None
    literal: str | None = None
    orcid: str | None = None

    @model_validator(mode="after")
    def has_name(self) -> Author:
        if not any((self.family, self.given, self.literal)):
            raise ValueError("author requires a name representation")
        return self


class AttachmentRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    attachment_key: str = Field(min_length=1)
    content_type: str | None = None
    link_mode: str | None = None
    available: bool


class Paper(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"] = "1.0"
    library_id: str = Field(min_length=1)
    item_key: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")
    item_version: int = Field(ge=0)
    raw_item_type: str = Field(min_length=1)
    item_type_class: ItemTypeClass
    paper_kind: PaperKind
    citekey: str | None = None
    title: str = Field(min_length=1, max_length=1000)
    authors: tuple[Author, ...] = ()
    year: int | None = Field(default=None, ge=1000)
    doi: str | None = None
    venue: str | None = None
    abstract: str | None = None
    collections: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()
    pdf_attachments: tuple[AttachmentRef, ...] = ()
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalization_warnings: tuple[Issue, ...] = ()


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    evidence_id: str = Field(min_length=1)
    source_field: Literal[
        "tag", "title", "abstract", "venue", "author", "project_profile", "item_type"
    ]
    match_kind: Literal[
        "existing_canonical_tag",
        "exact_rule_phrase",
        "frozen_alias",
        "project_profile_exact",
        "recency_window",
        "venue_allowlist_exact",
        "author_allowlist_exact",
        "zotero_type_allowlist_exact",
    ]
    normalized_excerpt: str = Field(max_length=240)
    value_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    criterion_id: str
    status: CriterionStatus
    reason_code: str
    evidence_refs: tuple[str, ...] = ()


class ConfidenceComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    coverage: Decimal
    specificity: Decimal
    agreement: Decimal
    completeness: Decimal


class TagDecision(BaseModel):
    """Pure proposed action for one tag; this model carries no write capability."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    tag: str = Field(min_length=2)
    action: TagAction
    managed: bool
    confidence: Decimal
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def obey_namespace_policy(self) -> TagDecision:
        namespace = self.tag[0]
        if namespace not in {"#", "%", "@", "$", "!"}:
            raise ValueError("tag must use a recognized canonical namespace")
        if namespace in {"$", "!"} and self.action not in {TagAction.KEEP, TagAction.SKIP}:
            raise ValueError("advisory tags may only be kept or skipped")
        if self.action is TagAction.REMOVE:
            raise ValueError("tag decisions must preserve existing tags")
        if self.managed != (namespace in {"#", "%", "@"} and self.action is TagAction.ADD):
            raise ValueError("managed must exactly describe a writable tag mutation")
        return self


class CollectionDecision(BaseModel):
    """Pure proposed action for an existing configured collection key."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    collection_key: str = Field(min_length=1)
    role: Literal["stage", "by_subject"]
    action: CollectionAction
    subject_tag: str | None = None
    confidence: Decimal
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def obey_collection_policy(self) -> CollectionDecision:
        if self.action is CollectionAction.REMOVE:
            raise ValueError("collection decisions must preserve existing collections")
        if self.role == "by_subject" and (self.subject_tag is None or not self.subject_tag.startswith("#")):
            raise ValueError("by-subject decisions require a canonical subject tag")
        if self.role == "stage" and self.subject_tag is not None:
            raise ValueError("stage decisions cannot carry a subject tag")
        if self.action is CollectionAction.MISSING and not self.reason_codes:
            raise ValueError("missing collection decisions require a reason")
        return self


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    decision_id: UUID = Field(default_factory=uuid4)
    paper_key: str
    ruleset_version: str
    taxonomy_version: str
    run_date: date
    subjects: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    project_uses: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    proposed_stage: Stage | None = None
    look_triggers: tuple[CriterionResult, ...]
    review_criteria: tuple[CriterionResult, ...]
    dig_criteria: tuple[CriterionResult, ...] = ()
    confidence: Decimal
    confidence_components: ConfidenceComponents
    evidence: tuple[EvidenceRef, ...] = ()
    warnings: tuple[Issue, ...] = ()
    outcome: Outcome

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, value: Decimal) -> Decimal:
        if not Decimal(0) <= value <= Decimal(1):
            raise ValueError("confidence must be in [0, 1]")
        return value
