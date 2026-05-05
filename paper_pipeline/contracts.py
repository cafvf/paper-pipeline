from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import re
from typing import Any


class PipelineError(RuntimeError):
    """Base error for the v2 paper pipeline."""


class ValidationError(PipelineError):
    """Raised when a human-editable contract is invalid."""


class Stage(StrEnum):
    TO_LOOK = ".ToLook"
    TO_REVISE = ".To Revise"
    TO_DIG = ".ToDig"
    EXPENDABLE = "Expendable"


class DecisionState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    MANUAL_ONLY = "manual_only"


class CollectionAction(StrEnum):
    ACCEPT_RECOMMENDATION = "accept_recommendation"
    KEEP_CURRENT = "keep_current"
    MOVE_TO_LOOK = "move_to_tolook"
    MOVE_TO_REVISE = "move_to_revise"
    MOVE_TO_DIG = "move_to_dig"
    MOVE_TO_EXPENDABLE = "move_to_expendable"
    NO_COLLECTION_CHANGE = "no_collection_change"
    MANUAL_ONLY = "manual_only"


class KnowledgeAction(StrEnum):
    CREATE_NEW = "create_new"
    UPDATE_EXISTING = "update_existing"
    LINK_EXISTING = "link_existing"
    REJECT = "reject"
    DEFER = "defer"


class MissingPdfAction(StrEnum):
    ATTACH_PDF = "attach_pdf"
    DEFER = "defer"
    MOVE_TO_EXPENDABLE = "move_to_expendable"
    MANUAL_ONLY = "manual_only"


class PartialAnalysisAction(StrEnum):
    RETRY_NEXT_RUN = "retry_next_run"
    DEFER = "defer"
    MOVE_TO_EXPENDABLE = "move_to_expendable"
    MANUAL_ONLY = "manual_only"


class AnalysisStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING_PDF = "missing_pdf"


STAGE_TAGS = {
    Stage.TO_LOOK: "@look",
    Stage.TO_REVISE: "@review",
    Stage.TO_DIG: "@dig",
}

OPERATIONAL_LLM_TAGS = {
    Stage.TO_LOOK: "@looked_by_llm",
    Stage.TO_REVISE: "@reviewed_by_llm",
    Stage.TO_DIG: "@dug_by_llm",
}

DISCARD_TAG = "!discarded"

READING_PROTOCOL_LLM_TAGS = tuple(
    dict.fromkeys([*STAGE_TAGS.values(), *OPERATIONAL_LLM_TAGS.values(), DISCARD_TAG])
)

READING_PROTOCOL_SUBJECT_TAGS = (
    "#rock-mechanics",
    "#rock-strength",
    "#failure-criteria",
    "#constitutive-models",
    "#rock-deformation",
    "#prob-soil-characterization",
    "#bayesian-inference",
    "#bayesian-updating",
    "#generative-models",
    "#dictionary-learning",
    "#PINNs-geomech",
    "#uncertainty-quantification",
    "#spatial-variability",
    "#random-fields",
    "#soil-classification",
    "#ML-classification",
    "#deep-learning-geotech",
    "#probabilistic-classification",
    "#CPT-classification",
    "#SPT-classification",
    "#transfer-learning",
    "#structural-reliability",
    "#Monte-Carlo",
    "#FORM-SORM",
    "#Markov-Chain",
    "#MCMC",
    "#failure-probability",
    "#fragility-curves",
    "#sensitivity-analysis",
    "#limit-state",
    "#wellbore-stability",
    "#drilling-geomech",
    "#mud-weight",
    "#borehole-failure",
    "#sand-production",
    "#fault-reactivation",
    "#induced-seismicity",
    "#structural-integrity",
    "#structural-analysis",
    "#stress-state",
    "#stress-path",
    "#overburden",
    "%analytical",
    "%semi-analytical",
    "%FEM",
    "%FDM",
    "%DEM",
    "%BEM",
    "%experimental",
    "%field-data",
    "%case-study",
    "%empirical",
    "%machine-learning",
    "%narrative-review",
    "%systematic-review",
    "%scoping-review",
    "%meta-analysis",
    "%abaqus",
    "%ansys",
    "%plaxis",
    "%flac",
    "%pfc",
    "%opensees",
    "%comsol",
    "%matlab",
    "%python-sci",
    "%opengeomech",
    "%rocscience",
    "$background",
    "$gap-signal",
    "$methods-cite",
    "$discussion",
    "$extend",
    "$paper-01",
    "$paper-02",
    "!seminal",
    "!high-impact",
    "!weak-methods",
    "!conflicting",
    "!data-available",
)


@dataclass(frozen=True)
class KnowledgeSuggestionDecision:
    id: str
    action: KnowledgeAction = KnowledgeAction.DEFER
    target_note: str = ""
    notes: str = ""


@dataclass(frozen=True)
class KnowledgeActions:
    literature_note: KnowledgeAction = KnowledgeAction.DEFER
    suggestions: list[KnowledgeSuggestionDecision] = field(default_factory=list)


@dataclass(frozen=True)
class FullDecision:
    decision_state: DecisionState = DecisionState.PENDING
    apply_zotero_actions: bool = True
    collection_action: CollectionAction = CollectionAction.ACCEPT_RECOMMENDATION
    override_collection: str = ""
    apply_recommended_tags: bool = True
    tag_overrides_add: list[str] = field(default_factory=list)
    tag_overrides_remove: list[str] = field(default_factory=list)
    apply_knowledge_actions: bool = False
    knowledge_actions: KnowledgeActions = field(default_factory=KnowledgeActions)
    manual_notes: str = ""


@dataclass(frozen=True)
class MissingPdfDecision:
    decision_state: DecisionState = DecisionState.PENDING
    missing_pdf_action: MissingPdfAction = MissingPdfAction.ATTACH_PDF
    manual_notes: str = ""


@dataclass(frozen=True)
class PartialAnalysisDecision:
    decision_state: DecisionState = DecisionState.PENDING
    partial_analysis_action: PartialAnalysisAction = PartialAnalysisAction.RETRY_NEXT_RUN
    manual_notes: str = ""


def normalize_citekey(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", value.strip())
    if not cleaned:
        raise ValidationError("citekey cannot be empty")
    return cleaned


def ensure_inside(base: Path, target: Path) -> Path:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    if target_resolved != base_resolved and base_resolved not in target_resolved.parents:
        raise ValidationError(f"path escapes base: {target}")
    return target_resolved


def stage_from_collection_action(action: CollectionAction, recommended: Stage | None = None) -> Stage | None:
    if action == CollectionAction.ACCEPT_RECOMMENDATION:
        return recommended
    if action == CollectionAction.MOVE_TO_LOOK:
        return Stage.TO_LOOK
    if action == CollectionAction.MOVE_TO_REVISE:
        return Stage.TO_REVISE
    if action == CollectionAction.MOVE_TO_DIG:
        return Stage.TO_DIG
    if action == CollectionAction.MOVE_TO_EXPENDABLE:
        return Stage.EXPENDABLE
    return None


def coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
