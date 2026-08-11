from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_triage.classification import classify
from paper_triage.config import StageCollections, TriageConfig
from paper_triage.decisions import plan_decisions
from paper_triage.models import CollectionAction, Stage, TagAction, TagDecision
from paper_triage.normalization import normalize_paper


def _config() -> TriageConfig:
    return TriageConfig(
        stage_collections=StageCollections(look="look-key", review="review-key", dig="dig-key"),
        by_subject={"#rock-mechanics": ("rock-subject-key",)},
        credible_venues=("Trusted Journal",),
    )


def _paper(*, tags: list[str] | None = None):
    return normalize_paper(
        {
            "library_id": "library",
            "item_key": "ITEM001",
            "item_version": 1,
            "raw_item_type": "journalArticle",
            "title": "Rock mechanics study",
            "authors": [{"family": "Doe"}],
            "year": 2026,
            "doi": "10.1000/test",
            "venue": "Trusted Journal",
            "abstract": "We show a research gap. This method gives results with a limitation.",
            "tags": tags or ["#rock-mechanics", "%finite-element", "!data-available"],
        },
        run_date=date(2026, 1, 1),
    )


def _high_classification():
    paper = _paper()
    return paper, classify(paper, _config(), run_date=date(2026, 1, 1))


def test_advisory_tag_actions_are_schema_limited() -> None:
    with pytest.raises(ValidationError, match="advisory"):
        TagDecision(
            tag="$methods-cite",
            action=TagAction.ADD,
            managed=True,
            confidence=Decimal("1.0000"),
        )
    with pytest.raises(ValidationError, match="advisory"):
        TagDecision(
            tag="!seminal",
            action=TagAction.REMOVE,
            managed=True,
            confidence=Decimal("1.0000"),
        )


def test_advisory_tags_are_skipped_when_absent_even_at_high_confidence() -> None:
    paper, classification = _high_classification()
    classification = classification.model_copy(
        update={"project_uses": ("$methods-cite",), "quality_flags": ("!seminal",)}
    )

    tags, _ = plan_decisions(paper, classification, _config())

    assert {(item.tag, item.action, item.managed) for item in tags if item.tag.startswith(("$", "!"))} == {
        ("!seminal", TagAction.SKIP, False),
        ("$methods-cite", TagAction.SKIP, False),
    }


def test_low_confidence_only_plans_needs_reread_and_no_collections() -> None:
    paper, high = _high_classification()
    low = high.model_copy(update={"confidence": Decimal("0.8499")})

    tags, collections = plan_decisions(paper, low, _config())

    assert collections == ()
    assert {(item.tag, item.action) for item in tags} == {
        ("!data-available", TagAction.KEEP),
        ("#rock-mechanics", TagAction.KEEP),
        ("%finite-element", TagAction.KEEP),
        ("@needs-reread", TagAction.ADD),
    }
    assert all(not item.managed or item.tag == "@needs-reread" for item in tags)


def test_low_confidence_preserves_existing_stage_and_needs_reread() -> None:
    paper, high = _high_classification()
    paper = paper.model_copy(update={"tags": frozenset({"@dig", "@needs-reread"}), "collections": frozenset({"dig-key"})})
    low = high.model_copy(update={"confidence": Decimal("0.8499")})

    tags, collections = plan_decisions(paper, low, _config())

    assert collections == ()
    assert {(item.tag, item.action, item.managed) for item in tags} == {
        ("!data-available", TagAction.SKIP, False),
        ("#rock-mechanics", TagAction.SKIP, False),
        ("%finite-element", TagAction.SKIP, False),
        ("@needs-reread", TagAction.KEEP, False),
    }


@pytest.mark.parametrize(
    ("confidence", "expected_stage_action", "expected_collection_action"),
    (
        (Decimal("0.8499"), None, None),
        (Decimal("0.8500"), TagAction.ADD, CollectionAction.ADD),
    ),
)
def test_confidence_threshold_controls_stage_and_collection_mutations(
    confidence: Decimal,
    expected_stage_action: TagAction | None,
    expected_collection_action: CollectionAction | None,
) -> None:
    paper, classification = _high_classification()
    classification = classification.model_copy(update={"confidence": confidence})

    tags, collections = plan_decisions(
        paper,
        classification,
        _config(),
        available_collection_keys=frozenset({"dig-key", "rock-subject-key"}),
    )

    stage_actions = {item.action for item in tags if item.tag == "@dig"}
    stage_collection_actions = {item.action for item in collections if item.collection_key == "dig-key"}
    reread_actions = {item.action for item in tags if item.tag == "@needs-reread"}
    assert stage_actions == ({expected_stage_action} if expected_stage_action is not None else set())
    assert stage_collection_actions == (
        {expected_collection_action} if expected_collection_action is not None else set()
    )
    assert reread_actions == ({TagAction.ADD} if confidence < Decimal("0.8500") else set())
    if confidence < Decimal("0.8500"):
        assert collections == ()
        assert {item.tag for item in tags if item.managed} == {"@needs-reread"}


def test_high_confidence_plans_existing_stage_and_by_subject_targets() -> None:
    paper, classification = _high_classification()
    tags, collections = plan_decisions(
        paper,
        classification,
        _config(),
        available_collection_keys=frozenset({"dig-key", "rock-subject-key"}),
    )

    assert ("@dig", TagAction.ADD) in {(item.tag, item.action) for item in tags}
    assert {(item.collection_key, item.action) for item in collections} == {
        ("dig-key", CollectionAction.ADD),
        ("rock-subject-key", CollectionAction.ADD),
    }
    advisory = next(item for item in tags if item.tag == "!data-available")
    assert advisory.action is TagAction.KEEP
    assert not advisory.managed


@pytest.mark.parametrize(
    ("stage", "stage_tag", "collection_key"),
    (
        (Stage.LOOK, "@look", "look-key"),
        (Stage.REVIEW, "@review", "review-key"),
        (Stage.DIG, "@dig", "dig-key"),
    ),
)
def test_stage_plan_uses_configured_stage_key(
    stage: Stage, stage_tag: str, collection_key: str
) -> None:
    paper, classification = _high_classification()
    classification = classification.model_copy(update={"proposed_stage": stage})

    tags, collections = plan_decisions(
        paper,
        classification,
        _config(),
        available_collection_keys=frozenset({collection_key, "rock-subject-key"}),
    )

    assert (stage_tag, TagAction.ADD) in {(item.tag, item.action) for item in tags}
    assert (collection_key, CollectionAction.ADD) in {
        (item.collection_key, item.action) for item in collections
    }


def test_missing_stage_root_blocks_stage_tag_but_not_other_resolved_destination() -> None:
    paper, classification = _high_classification()
    tags, collections = plan_decisions(
        paper,
        classification,
        _config(),
        available_collection_keys=frozenset({"rock-subject-key"}),
    )

    assert "@dig" not in {item.tag for item in tags}
    assert {(item.collection_key, item.action) for item in collections} == {
        ("dig-key", CollectionAction.MISSING),
        ("rock-subject-key", CollectionAction.ADD),
    }


def test_missing_by_subject_target_is_reported_without_suppressing_resolved_targets() -> None:
    paper, classification = _high_classification()
    config = TriageConfig(
        stage_collections=StageCollections(look="look-key", review="review-key", dig="dig-key"),
        by_subject={"#rock-mechanics": ("rock-subject-key", "missing-subject-key")},
        credible_venues=("Trusted Journal",),
    )

    _, collections = plan_decisions(
        paper,
        classification,
        config,
        available_collection_keys=frozenset({"dig-key", "rock-subject-key"}),
    )

    assert {(item.collection_key, item.action, item.reason_codes) for item in collections} == {
        ("dig-key", CollectionAction.ADD, ("PROPOSED_STAGE",)),
        ("rock-subject-key", CollectionAction.ADD, ("BY_SUBJECT_MATCH",)),
        ("missing-subject-key", CollectionAction.MISSING, ("COLLECTION_BY_SUBJECT_MISSING",)),
    }


def test_collection_adds_require_an_explicit_existing_key_snapshot() -> None:
    paper, classification = _high_classification()

    tags, collections = plan_decisions(paper, classification, _config())

    assert "@dig" not in {item.tag for item in tags}
    assert {(item.collection_key, item.action) for item in collections} == {
        ("dig-key", CollectionAction.MISSING),
        ("rock-subject-key", CollectionAction.MISSING),
    }
    assert all(item.action is not CollectionAction.ADD for item in collections)
