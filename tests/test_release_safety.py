"""Release gate tests: policy-only and deliberately free of connector I/O."""

import ast
from datetime import UTC, date, datetime
from pathlib import Path

from paper_triage.plans import (
    ApplyRequest,
    ApprovalEvidence,
    PlannedItem,
    PlannedOperation,
    PreviewPlan,
    PreviewVersion,
    Snapshot,
    canonical_sha256,
)
from paper_triage.release_safety import (
    ReleaseMode,
    ReleaseRequest,
    ValidationEvidence,
    authorize,
)


def _passing_evidence() -> ValidationEvidence:
    return ValidationEvidence(all_required_passed=True, evidence_reference="local-qa-2026-08-10")


def _approved_release_artifacts() -> tuple[PreviewPlan, ApplyRequest, ValidationEvidence]:
    items = tuple(
        PlannedItem(
            item_key=f"ITEM{number:02d}",
            source_fingerprint="a" * 64,
            preview_item_version=1,
            classification_projection={},
            operations=(
                PlannedOperation.build(
                    sequence=0,
                    resource_type="tag",
                    action="add",
                    target=f"#topic-{number:02d}",
                    before_present=False,
                    after_present=True,
                    version_precondition=PreviewVersion(version=1),
                ),
            ),
        )
        for number in range(10)
    )
    snapshot = Snapshot(value={}, digest=canonical_sha256({}))
    payload = {
        "preview_id": "release-preview",
        "created_at": datetime(2026, 8, 10, tzinfo=UTC),
        "run_date": date(2026, 8, 10),
        "selected_item_keys": tuple(item.item_key for item in items),
        "library_scope": {},
        "config_snapshot": snapshot,
        "collection_snapshot": snapshot,
        "project_profile_snapshot": snapshot,
        "ruleset_snapshot": snapshot,
        "taxonomy_snapshot": snapshot,
        "items": items,
        "reviewed_diff_projection": PreviewPlan.reviewed_diff_for(items),
    }
    preview_plan = PreviewPlan(**payload, plan_hash=PreviewPlan.plan_hash_for(**payload))
    operation_ids = tuple(
        operation.operation_id for item in preview_plan.items for operation in item.operations
    )
    apply_request = ApplyRequest(
        preview_id=preview_plan.preview_id,
        plan_hash=preview_plan.plan_hash,
        approval=ApprovalEvidence.create(
            approval_id="release-approval",
            approved_plan_hash=preview_plan.plan_hash,
            approved_at=datetime(2026, 8, 10, tzinfo=UTC),
            approved_item_keys=preview_plan.selected_item_keys,
            reviewed_operation_ids=operation_ids,
            reviewed_diff_hash=preview_plan.reviewed_diff_hash,
        ),
    )
    return (
        preview_plan,
        apply_request,
        ValidationEvidence.create(plan_hash=preview_plan.plan_hash, checks=("pytest", "mypy")),
    )


def test_request_defaults_to_dry_run_without_live_authority() -> None:
    authorization = authorize(ReleaseRequest())

    assert authorization.allowed is False
    assert "dry-run" in authorization.reason.lower()


def test_live_mode_requires_explicit_human_approval() -> None:
    authorization = authorize(
        ReleaseRequest(mode=ReleaseMode.LIVE, validation_evidence=_passing_evidence())
    )

    assert authorization.allowed is False
    assert "approved preview" in authorization.reason.lower()


def test_live_mode_requires_validation_evidence() -> None:
    authorization = authorize(ReleaseRequest(mode=ReleaseMode.LIVE, human_approved=True))

    assert authorization.allowed is False
    assert "approved preview" in authorization.reason.lower()


def test_live_mode_rejects_failed_validation_evidence() -> None:
    authorization = authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=True,
            validation_evidence=ValidationEvidence(
                all_required_passed=False, evidence_reference="failing-local-check"
            ),
        )
    )

    assert authorization.allowed is False
    assert "approved preview" in authorization.reason.lower()


def test_live_mode_is_authorized_only_with_approval_and_passing_evidence() -> None:
    authorization = authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=True,
            validation_evidence=_passing_evidence(),
        )
    )

    assert authorization.allowed is False
    assert "approved preview plan" in authorization.reason.lower()


def test_live_mode_fails_closed_without_human_approval_despite_valid_artifacts() -> None:
    preview_plan, apply_request, validation_evidence = _approved_release_artifacts()

    authorization = authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=False,
            preview_plan=preview_plan,
            apply_request=apply_request,
            validation_evidence=validation_evidence,
        )
    )

    assert authorization.allowed is False
    assert "human approval" in authorization.reason.lower()


def test_live_mode_authorizes_valid_artifacts_after_human_approval() -> None:
    preview_plan, apply_request, validation_evidence = _approved_release_artifacts()

    authorization = authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=True,
            preview_plan=preview_plan,
            apply_request=apply_request,
            validation_evidence=validation_evidence,
        )
    )

    assert authorization.allowed is True
    assert authorization.plan_hash == preview_plan.plan_hash
    assert authorization.is_bound


def test_validation_evidence_is_hash_bound_not_a_passing_boolean() -> None:
    evidence = ValidationEvidence.create(plan_hash="a" * 64, checks=("pytest", "mypy"))

    assert evidence.verifies()
    assert ValidationEvidence.model_validate(
        {**evidence.model_dump(), "validation_digest": "b" * 64}
    ).verifies() is False


def test_release_gate_module_has_no_network_or_zotero_client_imports() -> None:
    module_path = Path("src/paper_triage/release_safety.py")
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(module_path.read_text()))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert imports.isdisjoint({"requests", "httpx", "urllib", "zotero", "pyzotero", "socket"})
