"""Pure deterministic tag and collection decision planning for the local MVP."""

from __future__ import annotations

from .config import CONFIDENCE_THRESHOLD, TriageConfig
from .models import (
    Classification,
    CollectionAction,
    CollectionDecision,
    Paper,
    TagAction,
    TagDecision,
)

_STAGE_TAGS = {"look": "@look", "review": "@review", "dig": "@dig"}


def plan_decisions(
    paper: Paper,
    classification: Classification,
    config: TriageConfig,
    *,
    available_collection_keys: frozenset[str] | None = None,
) -> tuple[tuple[TagDecision, ...], tuple[CollectionDecision, ...]]:
    """Return deterministic, advisory-only planning data without performing I/O.

    ``available_collection_keys`` must be a previously read snapshot before a
    collection-add proposal can be emitted.  Missing or unavailable snapshots fail
    closed as ``missing`` so this planning layer can never imply collection creation.
    """
    high = classification.confidence >= CONFIDENCE_THRESHOLD
    desired_tags = (*classification.subjects, *classification.methods)
    tags: list[TagDecision] = []
    for tag in sorted(desired_tags):
        tags.append(
            TagDecision(
                tag=tag,
                action=TagAction.KEEP if tag in paper.tags else TagAction.ADD if high else TagAction.SKIP,
                managed=high and tag not in paper.tags,
                confidence=classification.confidence,
                reason_codes=("CANONICAL_CLASSIFICATION" if high else "LOW_CONFIDENCE",),
            )
        )
    for tag in (*classification.project_uses, *classification.quality_flags):
        tags.append(
            TagDecision(
                tag=tag,
                action=TagAction.KEEP if tag in paper.tags else TagAction.SKIP,
                managed=False,
                confidence=classification.confidence,
                reason_codes=("ADVISORY_ONLY",),
            )
        )

    collections: list[CollectionDecision] = []
    if not high:
        reread = "@needs-reread"
        tags.append(
            TagDecision(
                tag=reread,
                action=TagAction.KEEP if reread in paper.tags else TagAction.ADD,
                managed=reread not in paper.tags,
                confidence=classification.confidence,
                reason_codes=("LOW_CONFIDENCE",),
            )
        )
        return tuple(sorted(tags, key=lambda decision: decision.tag)), ()

    if classification.proposed_stage is not None:
        stage = classification.proposed_stage.value
        root = getattr(config.stage_collections, stage)
        root_available = available_collection_keys is not None and root in available_collection_keys
        if root_available:
            collections.append(
                CollectionDecision(
                    collection_key=root,
                    role="stage",
                    action=CollectionAction.KEEP if root in paper.collections else CollectionAction.ADD,
                    confidence=classification.confidence,
                    reason_codes=("PROPOSED_STAGE",),
                )
            )
            stage_tag = _STAGE_TAGS[stage]
            tags.append(
                TagDecision(
                    tag=stage_tag,
                    action=TagAction.KEEP if stage_tag in paper.tags else TagAction.ADD,
                    managed=stage_tag not in paper.tags,
                    confidence=classification.confidence,
                    reason_codes=("PROPOSED_STAGE",),
                )
            )
        else:
            collections.append(
                CollectionDecision(
                    collection_key=root,
                    role="stage",
                    action=CollectionAction.MISSING,
                    confidence=classification.confidence,
                    reason_codes=("COLLECTION_ROOT_BLOCKS_STAGE",),
                )
            )

    for subject in classification.subjects:
        for key in config.by_subject.get(subject, ()):
            available = available_collection_keys is not None and key in available_collection_keys
            collections.append(
                CollectionDecision(
                    collection_key=key,
                    role="by_subject",
                    subject_tag=subject,
                    action=(CollectionAction.KEEP if key in paper.collections else CollectionAction.ADD)
                    if available
                    else CollectionAction.MISSING,
                    confidence=classification.confidence,
                    reason_codes=("BY_SUBJECT_MATCH",) if available else ("COLLECTION_BY_SUBJECT_MISSING",),
                )
            )
    return tuple(sorted(tags, key=lambda decision: decision.tag)), tuple(
        sorted(collections, key=lambda decision: (decision.role, decision.collection_key))
    )
