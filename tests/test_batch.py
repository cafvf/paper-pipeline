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


def _latest_states(ledger: AuditLedger, authorization_id: str) -> dict[str, str]:
    return {
        entry.operation_id: entry.state
        for entry in ledger.operation_entries_for(authorization_id)
    }


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
        self, *, operation_id: str, idempotency_key: str, item_key: str, run_date: date
    ) -> AttemptEvidence:
        del run_date
        return AttemptEvidence(
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            item_key=item_key,
            item_version=next(self._versions),
            tags=(),
            collection_keys=(),
            preserved_field_hashes={"source": "a" * 64},
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
    port = LocalBatchPort([1] * 10)
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
    port = LocalBatchPort([1] * 10)

    with pytest.raises(RuntimeError, match="disk is unavailable"):
        execute_persisted_preview(preview.plan_hash, ledger, port)

    assert port.mutation_calls == 0


def test_executor_chains_the_receipt_version_for_later_operations_on_one_item(
    tmp_path: Path,
) -> None:
    preview, request = _two_operation_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([1, 2] + [1] * 9)

    result = execute_persisted_preview(preview.plan_hash, ledger, port)

    first_item_commands = [command for command in result.commands if command.item_key == "ITEM00"]
    assert [command.expected_version for command in first_item_commands] == [1, 2]
    assert len(result.receipts) == 11


def test_executor_marks_the_attempt_uncertain_and_stops_after_write_exception(tmp_path: Path) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([1] * 10, fail_write=True)

    with pytest.raises(RuntimeError, match="simulated transport failure"):
        execute_persisted_preview(preview.plan_hash, ledger, port)

    authorization_id = request.approval.approval_id
    assert port.mutation_calls == 1
    assert _latest_states(ledger, authorization_id)[preview.items[0].operations[0].operation_id] == "uncertain"


def test_executor_rejects_a_stale_first_snapshot_without_any_write_and_terminalizes_batch(
    tmp_path: Path,
) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    port = LocalBatchPort([2])

    with pytest.raises(ValueError, match="does not match the approved preview"):
        execute_persisted_preview(preview.plan_hash, ledger, port)

    entries = ledger.operation_entries_for(request.approval.approval_id)
    assert port.mutation_calls == 0
    states = _latest_states(ledger, request.approval.approval_id)
    assert states[preview.items[0].operations[0].operation_id] == "skipped_stale"
    assert all(
        states[operation.operation_id] == "aborted"
        for item in preview.items[1:]
        for operation in item.operations
    )
    stale = next(entry for entry in entries if entry.state == "skipped_stale")
    assert stale.expected_version == 1
    assert stale.observed_version == 2


def test_executor_rejects_a_changed_first_snapshot_fingerprint_without_any_write(
    tmp_path: Path,
) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)

    class ChangedFingerprintPort(LocalBatchPort):
        def capture_attempt_evidence(self, **kwargs: object) -> AttemptEvidence:
            evidence = super().capture_attempt_evidence(**kwargs)
            return evidence.model_copy(update={"preserved_field_hashes": {"source": "b" * 64}})

    port = ChangedFingerprintPort([1])
    with pytest.raises(ValueError, match="does not match the approved preview"):
        execute_persisted_preview(preview.plan_hash, ledger, port)

    assert port.mutation_calls == 0
    assert _latest_states(ledger, request.approval.approval_id)[
        preview.items[0].operations[0].operation_id
    ] == "skipped_stale"


def test_executor_reapply_of_a_completed_batch_is_idempotent_without_port_calls(tmp_path: Path) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    first_port = LocalBatchPort([1] * 10)
    execute_persisted_preview(preview.plan_hash, ledger, first_port)

    replay_port = LocalBatchPort([])
    result = execute_persisted_preview(preview.plan_hash, ledger, replay_port)

    assert first_port.mutation_calls == 10
    assert replay_port.mutation_calls == 0
    assert result.commands == ()
    assert result.receipts == ()


def test_executor_recovers_uncertain_write_by_fresh_readback_without_replaying_it(
    tmp_path: Path,
) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    with pytest.raises(RuntimeError, match="simulated transport failure"):
        execute_persisted_preview(preview.plan_hash, ledger, LocalBatchPort([1] * 10, fail_write=True))

    class RecoveredFirstPort(LocalBatchPort):
        def __init__(self) -> None:
            super().__init__([2] + [1] * 9)
            self.capture_calls = 0

        def capture_attempt_evidence(self, **kwargs: object) -> AttemptEvidence:
            evidence = super().capture_attempt_evidence(**kwargs)
            self.capture_calls += 1
            if self.capture_calls == 1:
                return evidence.model_copy(update={"tags": ("#topic-0",)})
            return evidence

    recovery_port = RecoveredFirstPort()
    result = execute_persisted_preview(preview.plan_hash, ledger, recovery_port)

    assert recovery_port.mutation_calls == 9
    assert [command.item_key for command in result.commands] == list(preview.selected_item_keys[1:])
    first_entries = [
        entry
        for entry in ledger.operation_entries_for(request.approval.approval_id)
        if entry.operation_id == preview.items[0].operations[0].operation_id
    ]
    assert [entry.state for entry in first_entries] == ["planned", "attempted", "uncertain", "verified"]


def test_executor_refuses_ambiguous_recovery_with_unrelated_safe_fingerprint_change(
    tmp_path: Path,
) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)

    class RawEvidenceFailPort(LocalBatchPort):
        def capture_attempt_evidence(self, **kwargs: object) -> AttemptEvidence:
            evidence = super().capture_attempt_evidence(**kwargs)
            return evidence.model_copy(
                update={
                    "preserved_field_hashes": {
                        "source": "a" * 64,
                        "raw_item_data": "a" * 64,
                    }
                }
            )

    with pytest.raises(RuntimeError, match="simulated transport failure"):
        execute_persisted_preview(
            preview.plan_hash, ledger, RawEvidenceFailPort([1] * 10, fail_write=True)
        )

    class AmbiguousRecoveryPort(LocalBatchPort):
        def __init__(self) -> None:
            super().__init__([2])

        def capture_attempt_evidence(self, **kwargs: object) -> AttemptEvidence:
            evidence = super().capture_attempt_evidence(**kwargs)
            return evidence.model_copy(
                update={
                    "tags": ("#topic-0",),
                    "preserved_field_hashes": {
                        "source": "a" * 64,
                        "raw_item_data": "b" * 64,
                    },
                }
            )

    recovery_port = AmbiguousRecoveryPort()
    with pytest.raises(ValueError, match="cannot be verified"):
        execute_persisted_preview(preview.plan_hash, ledger, recovery_port)

    operation = preview.items[0].operations[0]
    states = _latest_states(ledger, request.approval.approval_id)
    assert recovery_port.mutation_calls == 0
    assert states[operation.operation_id] == "failed"
    assert ledger.managed_provenance_for(
        operation.operation_id,
        item_key=preview.items[0].item_key,
        resource=operation.resource_type,
        target=operation.target,
        expected_version=2,
    ) is None
    assert all(
        states[later.operation_id] == "aborted"
        for item in preview.items[1:]
        for later in item.operations
    )


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
