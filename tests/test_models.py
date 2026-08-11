from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_triage.models import (
    Classification,
    CollectionAction,
    CollectionDecision,
    ConfidenceComponents,
    CriterionResult,
    CriterionStatus,
    Outcome,
    TagAction,
    TagDecision,
)


def _classification() -> Classification:
    return Classification(
        paper_key="ITEM001",
        ruleset_version="1.0.0",
        taxonomy_version="1.0.0",
        run_date=date(2026, 1, 1),
        look_triggers=(CriterionResult(criterion_id="look.subject", status=CriterionStatus.PASS, reason_code="MATCH"),),
        review_criteria=(),
        confidence=Decimal("0.8500"),
        confidence_components=ConfidenceComponents(
            coverage=Decimal("1.0000"), specificity=Decimal("1.0000"), agreement=Decimal("1.0000"), completeness=Decimal("1.0000")
        ),
        outcome=Outcome.HIGH_CONFIDENCE,
    )


def test_classification_is_strict_and_confidence_is_bounded() -> None:
    classification = _classification()
    assert classification.confidence == Decimal("0.8500")
    with pytest.raises(ValidationError):
        Classification(**{**classification.model_dump(), "unexpected": "forbidden"})
    with pytest.raises(ValidationError):
        Classification(**{**classification.model_dump(), "confidence": Decimal("1.0001")})


@pytest.mark.parametrize(
    ("tag", "managed"),
    (("#human-topic", True), ("%human-method", True), ("@human-stage", True)),
)
def test_tag_decisions_cannot_remove_human_or_unmanaged_tags(tag: str, managed: bool) -> None:
    with pytest.raises(ValidationError, match="preserve existing tags"):
        TagDecision(
            tag=tag,
            action=TagAction.REMOVE,
            managed=managed,
            confidence=Decimal("1.0000"),
        )


@pytest.mark.parametrize("role", ("stage", "by_subject"))
def test_collection_decisions_cannot_remove_existing_collections(role: str) -> None:
    with pytest.raises(ValidationError, match="preserve existing collections"):
        CollectionDecision(
            collection_key="human-collection",
            role=role,
            subject_tag="#human-topic" if role == "by_subject" else None,
            action=CollectionAction.REMOVE,
            confidence=Decimal("1.0000"),
        )
