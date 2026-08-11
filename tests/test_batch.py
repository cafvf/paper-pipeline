from __future__ import annotations

import socket
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_audit import _batch_preview

from paper_triage.audit import AttemptEvidence, AuditLedger
from paper_triage.batch import (
    command_for_operation,
    commands_for_approved_preview,
    execute_persisted_preview,
)
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
from paper_triage.zotero import ZoteroMutationCommand, ZoteroMutationReceipt


class LocalBatchPort:
    """In-process fake: its pre-call evidence is the only version source."""

    def __init__(self, versions: list[int], *, fail_write: bool = False) -> None:
        self._versions = iter(versions)
        self._fail_write = fail_write
        self.commands: list[ZoteroMutationCommand] = []

    @property
    def mutation_calls(self) -> int:
        return len(self.commands)

    def capture_attempt_evidence(
        self, *, operation_id: str, idempotency_key: str, item_key: str
    ) -> AttemptEvidence:
        return AttemptEvidence(
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            item_key=item_key,
            item_version=next(self._versions),
            tags=(),
            collection_keys=(),
            preserved_field_hashes={"data": "a" * 64},
        )

    def mutate_item(self, command: ZoteroMutationCommand) -> ZoteroMutationReceipt:
        self.commands.append(command)
        if self._fail_write:
            raise RuntimeError("simulated transport failure")
        return ZoteroMutationReceipt(
            item_key=command.item_key,
            accepted_version=command.expected_version + 1,
            request_id="local-fake",
        )


def test_commands_are_derived_only_from_every_reviewed_preview_operation() -> None:
    preview, request = _batch_preview()
    commands = commands_for_approved_preview(preview, request)

    assert len(commands) == 10
    assert tuple(command.operation_id for command in commands) == request.approval.reviewed_operation_ids
    assert all(command.resource == "tag" and command.action == "add" for command in commands)


def test_operation_command_uses_the_fresh_verified_version_not_preview_version() -> None:
    preview, _request = _batch_preview()
    item = preview.items[0]
    command = command_for_operation(preview, item, item.operations[0], expected_version=42)

    assert command.expected_version == 42


def test_executor_loads_the_persisted_pair_and_applies_all_ten_items_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([7] * 10)
    monkeypatch.setattr(
        socket, "create_connection", lambda *args, **kwargs: pytest.fail("network access")
    )

    result = execute_persisted_preview(preview.plan_hash, ledger, port)

    assert port.mutation_calls == 10
    assert tuple(command.item_key for command in result.commands) == preview.selected_item_keys
    assert tuple(command.operation_id for command in result.commands) == (
        request.approval.reviewed_operation_ids
    )
    assert tuple(receipt.item_key for receipt in result.receipts) == preview.selected_item_keys
    assert result.plan_hash == preview.plan_hash
    assert result.preview_id == preview.preview_id


def test_executor_rejects_an_unpersisted_plan_without_calling_the_port(tmp_path: Path) -> None:
    preview, _request = _batch_preview()
    port = LocalBatchPort([])

    with pytest.raises(ValueError, match="not persisted"):
        execute_persisted_preview(preview.plan_hash, AuditLedger(tmp_path / "audit.sqlite3"), port)

    assert port.mutation_calls == 0


def test_executor_validates_loaded_request_before_deriving_or_applying_commands() -> None:
    preview, request = _batch_preview()
    invalid_request = ApplyRequest.model_construct(
        preview_id="different-preview", plan_hash=request.plan_hash, approval=request.approval
    )

    class InvalidLedger:
        def load_preview_request(self, plan_hash: str):  # type: ignore[no-untyped-def]
            assert plan_hash == preview.plan_hash
            return preview, invalid_request

    port = LocalBatchPort([])
    with pytest.raises(ValueError, match="does not match preview"):
        execute_persisted_preview(preview.plan_hash, InvalidLedger(), port)  # type: ignore[arg-type]

    assert port.mutation_calls == 0


def test_executor_never_mutates_when_write_ahead_evidence_cannot_persist(tmp_path: Path) -> None:
    preview, request = _batch_preview()

    class FailingEvidenceLedger(AuditLedger):
        def record_attempt(self, authorization_id: str, evidence: AttemptEvidence) -> None:
            del authorization_id, evidence
            raise RuntimeError("disk is unavailable")

    ledger = FailingEvidenceLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([4] * 10)

    with pytest.raises(RuntimeError, match="disk is unavailable"):
        execute_persisted_preview(preview.plan_hash, ledger, port)

    assert port.mutation_calls == 0


def test_executor_chains_the_receipt_version_for_later_operations_on_one_item(
    tmp_path: Path,
) -> None:
    preview, request = _two_operation_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([5, 6] + [5] * 9)

    result = execute_persisted_preview(preview.plan_hash, ledger, port)

    first_item_commands = [command for command in result.commands if command.item_key == "ITEM00"]
    assert [command.expected_version for command in first_item_commands] == [5, 6]
    assert len(result.receipts) == 11


def test_executor_marks_the_attempt_uncertain_and_stops_after_write_exception(tmp_path: Path) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([3] * 10, fail_write=True)

    with pytest.raises(RuntimeError, match="simulated transport failure"):
        execute_persisted_preview(preview.plan_hash, ledger, port)

    authorization_id = request.approval.approval_id
    assert port.mutation_calls == 1
    assert [entry.state for entry in ledger.operation_entries_for(authorization_id)] == [
        "planned",
        "attempted",
        "uncertain",
    ]


def _two_operation_preview() -> tuple[PreviewPlan, ApplyRequest]:
    items: list[PlannedItem] = []
    for number in range(10):
        first = PlannedOperation.build(
            sequence=0,
            resource_type="tag",
            action="add",
            target=f"#first-{number}",
            before_present=False,
            after_present=True,
            version_precondition=PreviewVersion(version=1),
        )
        operations = (first,)
        if number == 0:
            second = PlannedOperation.build(
                sequence=1,
                depends_on=(first.operation_id,),
                resource_type="tag",
                action="add",
                target="#second-0",
                before_present=False,
                after_present=True,
                version_precondition=VerifiedVersionOf(operation_id=first.operation_id),
            )
            operations = (first, second)
        items.append(
            PlannedItem(
                item_key=f"ITEM{number:02d}",
                source_fingerprint="a" * 64,
                preview_item_version=1,
                classification_projection={},
                operations=operations,
            )
        )
    frozen_items = tuple(items)
    snapshot = Snapshot(value={}, digest=canonical_sha256({}))
    payload = {
        "preview_id": "two-operation-preview",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "run_date": date(2026, 1, 1),
        "selected_item_keys": tuple(item.item_key for item in frozen_items),
        "library_scope": {},
        "config_snapshot": snapshot,
        "collection_snapshot": snapshot,
        "project_profile_snapshot": snapshot,
        "ruleset_snapshot": snapshot,
        "taxonomy_snapshot": snapshot,
        "items": frozen_items,
        "reviewed_diff_projection": PreviewPlan.reviewed_diff_for(frozen_items),
    }
    preview = PreviewPlan(**payload, plan_hash=PreviewPlan.plan_hash_for(**payload))
    operation_ids = tuple(
        operation.operation_id for item in preview.items for operation in item.operations
    )
    approval = ApprovalEvidence.create(
        approval_id="two-operation-approval",
        approved_plan_hash=preview.plan_hash,
        approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        approved_item_keys=preview.selected_item_keys,
        reviewed_operation_ids=operation_ids,
        reviewed_diff_hash=preview.reviewed_diff_hash,
    )
    return preview, ApplyRequest(
        preview_id=preview.preview_id, plan_hash=preview.plan_hash, approval=approval
    )
