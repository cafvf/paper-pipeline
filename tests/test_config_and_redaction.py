from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_triage.config import CONFIDENCE_THRESHOLD, STAGE_PATHS, StageCollections, TriageConfig
from paper_triage.errors import Issue, IssueCode
from paper_triage.redaction import redact_text


def _stages() -> StageCollections:
    return StageCollections(look="look-key", review="review-key", dig="dig-key")


def test_deployment_stage_paths_and_threshold_are_frozen() -> None:
    assert STAGE_PATHS == {"look": ".ToLook", "review": ".ToRevise", "dig": ".ToDig"}
    assert CONFIDENCE_THRESHOLD == Decimal("0.8500")
    config = TriageConfig(stage_collections=_stages())
    assert config.confidence_threshold == Decimal("0.8500")


@pytest.mark.parametrize(
    ("stages", "by_subject"),
    [
        ({"look": "same", "review": "same", "dig": "dig"}, {}),
        ({"look": "look", "review": "review", "dig": "dig"}, {"#rock": ("review",)}),
    ],
)
def test_collection_role_collisions_fail_closed(stages: dict[str, str], by_subject: dict[str, tuple[str, ...]]) -> None:
    with pytest.raises(ValidationError) as exc:
        TriageConfig(stage_collections=StageCollections(**stages), by_subject=by_subject)
    assert IssueCode.CONFIG_COLLECTION_ROLE_COLLISION in str(exc.value)


@pytest.mark.parametrize(
    ("stages", "by_subject"),
    [
        ({"look": "shared", "review": "shared", "dig": "dig-key"}, {}),
        ({"look": "look-key", "review": "shared", "dig": "shared"}, {}),
        ({"look": "shared", "review": "review-key", "dig": "shared"}, {}),
        ({"look": "look-key", "review": "review-key", "dig": "dig-key"}, {"#a": ("look-key",)}),
        ({"look": "look-key", "review": "review-key", "dig": "dig-key"}, {"#a": ("review-key",)}),
        ({"look": "look-key", "review": "review-key", "dig": "dig-key"}, {"#a": ("dig-key",)}),
    ],
)
def test_every_stage_role_collision_is_rejected(
    stages: dict[str, str], by_subject: dict[str, tuple[str, ...]]
) -> None:
    with pytest.raises(ValidationError) as exc:
        TriageConfig(stage_collections=StageCollections(**stages), by_subject=by_subject)

    assert IssueCode.CONFIG_COLLECTION_ROLE_COLLISION in str(exc.value)


def test_by_subject_destinations_can_be_reused_when_distinct_from_stage_roots() -> None:
    config = TriageConfig(
        stage_collections=_stages(),
        by_subject={"#first": ("subject-key",), "#second": ("subject-key",)},
    )

    assert config.by_subject == {"#first": ("subject-key",), "#second": ("subject-key",)}


def test_config_rejects_threshold_changes_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TriageConfig(stage_collections=_stages(), confidence_threshold=Decimal("0.8499"))
    with pytest.raises(ValidationError):
        TriageConfig(stage_collections=_stages(), unexpected="forbidden")  # type: ignore[call-arg]


def test_redaction_removes_secret_values() -> None:
    secret = "very-secret-token"
    redacted, counts = redact_text(f"Authorization: Bearer {secret}; api_key={secret}")
    assert secret not in redacted
    assert "[REDACTED]" in redacted
    assert counts == {"authorization": 1, "token": 1}

@pytest.mark.parametrize("key", ("api_key", "api-key"))
def test_issue_context_rejects_api_key_variants(key: str) -> None:
    with pytest.raises(ValidationError, match="sensitive key"):
        Issue(code="SAFE", message="safe message", context={key: "raw-secret"})


def test_redaction_removes_credentials_from_structured_payloads() -> None:
    raw_secret = "raw-secret-value"
    payload = (
        f'{{"authorization": "Bearer {raw_secret}", "api_key": "{raw_secret}", '
        f'"password": "{raw_secret}", "title": "safe metadata"}}'
    )

    redacted, counts = redact_text(payload)

    assert raw_secret not in redacted
    assert redacted == (
        '{"authorization": [REDACTED], "api_key": [REDACTED], '
        '"password": [REDACTED], "title": "safe metadata"}'
    )
    assert counts == {"authorization": 1, "token": 2}

@pytest.mark.parametrize(
    ("artifact", "payload"),
    [
        (
            "config",
            {
                "stage_collections": {"look": "look-key", "review": "review-key", "dig": "dig-key"},
                "token": "credential-canary",
            },
        ),
        (
            "mutation_plan",
            {
                "library_id": "library",
                "item_key": "ITEM001",
                "source_fingerprint": "a" * 64,
                "mutations": [{"kind": "tag", "target": "#topic", "action": "add"}],
                "api_key": "credential-canary",
            },
        ),
    ],
)
def test_persistable_artifacts_reject_credential_canaries(
    artifact: str, payload: dict[str, object]
) -> None:
    """A credential canary must not enter a serialized configuration or mutation plan."""
    from paper_triage.audit import MutationPlan

    model = TriageConfig if artifact == "config" else MutationPlan
    with pytest.raises(ValidationError):
        model.model_validate(payload)
