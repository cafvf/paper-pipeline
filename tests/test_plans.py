from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from paper_triage.plans import (
    ApplyRequest,
    ApprovalEvidence,
    PlannedItem,
    PlannedOperation,
    PreviewPlan,
    PreviewVersion,
    Snapshot,
    VerifiedVersionOf,
    canonical_sha256,
)


def _item(number: int) -> PlannedItem:
    item_key = f"ITEM{number:02d}"
    first = PlannedOperation.build(
        sequence=0,
        resource_type="tag",
        action="add",
        target=f"#topic-{number:02d}",
        before_present=False,
        after_present=True,
        version_precondition=PreviewVersion(version=1),
        reason_codes=("RULE_MATCH",),
        evidence_refs=("evidence-1",),
    )
    second = PlannedOperation.build(
        sequence=1,
        resource_type="collection",
        action="add",
        target="to-review",
        before_present=False,
        after_present=True,
        version_precondition=VerifiedVersionOf(operation_id=first.operation_id),
        depends_on=(first.operation_id,),
    )
    return PlannedItem(
        item_key=item_key,
        source_fingerprint="a" * 64,
        preview_item_version=1,
        classification_projection={"outcome": "high_confidence"},
        tag_decisions=(),
        collection_decisions=(),
        operations=(first, second),
    )


def _snapshot(value: object) -> Snapshot:
    return Snapshot(value=value, digest=canonical_sha256(value))


def _plan_payload() -> dict[str, object]:
    items = tuple(_item(number) for number in range(10))
    projection = PreviewPlan.reviewed_diff_for(items)
    return {
        "preview_id": "preview-001",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "run_date": date(2026, 1, 1),
        "selected_item_keys": tuple(item.item_key for item in items),
        "library_scope": {"library_id": "local"},
        "config_snapshot": _snapshot({"threshold": "0.85"}),
        "collection_snapshot": _snapshot({"collections": []}),
        "project_profile_snapshot": _snapshot({"profiles": []}),
        "ruleset_snapshot": _snapshot({"version": "1"}),
        "taxonomy_snapshot": _snapshot({"version": "1"}),
        "items": items,
        "reviewed_diff_projection": projection,
    }


def test_ten_item_preview_is_hash_bound_and_approval_binds_every_operation() -> None:
    payload = _plan_payload()
    plan_hash = PreviewPlan.plan_hash_for(**payload)
    plan = PreviewPlan(**payload, plan_hash=plan_hash)
    operation_ids = tuple(
        operation.operation_id for item in plan.items for operation in item.operations
    )
    approval = ApprovalEvidence.create(
        approval_id="approval-001",
        approved_plan_hash=plan.plan_hash,
        approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        approved_item_keys=plan.selected_item_keys,
        reviewed_operation_ids=operation_ids,
        reviewed_diff_hash=plan.reviewed_diff_hash,
    )

    request = ApplyRequest(preview_id=plan.preview_id, plan_hash=plan.plan_hash, approval=approval)
    assert request.validates(plan)
    assert len(plan.selected_item_keys) == 10
    assert plan.plan_hash == PreviewPlan.plan_hash_for(**payload)


def test_preview_rejects_tampered_hash_or_noncanonical_item_order() -> None:
    payload = _plan_payload()
    plan_hash = PreviewPlan.plan_hash_for(**payload)
    with pytest.raises(ValidationError, match="plan hash"):
        PreviewPlan(**payload, plan_hash="b" * 64)
    with pytest.raises(ValidationError, match="sorted"):
        PreviewPlan(**{**payload, "selected_item_keys": tuple(reversed(payload["selected_item_keys"]))}, plan_hash=plan_hash)


def test_operations_are_chained_and_cannot_cross_items_or_write_advisory_tags() -> None:
    first = _item(0).operations[0]
    with pytest.raises(ValidationError, match="advisory"):
        PlannedOperation.build(
            sequence=0,
            resource_type="tag",
            action="add",
            target="$advisory",
            before_present=False,
            after_present=True,
            version_precondition=PreviewVersion(version=1),
        )
    with pytest.raises(ValidationError, match="immediately preceding"):
        valid_first = PlannedOperation.build(
            sequence=0,
            resource_type="tag",
            action="add",
            target="#topic",
            before_present=False,
            after_present=True,
            version_precondition=PreviewVersion(version=1),
        )
        PlannedItem(
            item_key="ITEM99",
            source_fingerprint="a" * 64,
            preview_item_version=1,
            classification_projection={},
            operations=(
                valid_first,
                PlannedOperation.build(
                    sequence=1,
                    resource_type="collection",
                    action="add",
                    target="to-review",
                    before_present=False,
                    after_present=True,
                    version_precondition=VerifiedVersionOf(operation_id=first.operation_id),
                    depends_on=(first.operation_id,),
                ),
            ),
        )
