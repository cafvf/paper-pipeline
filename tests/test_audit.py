from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
import stat
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from paper_triage.audit import (
    ApplyAuthorization,
    Approval,
    AttemptEvidence,
    AuditLedger,
    DiffEntry,
    ExactDiffMismatch,
    InMemoryMutationPort,
    Mutation,
    MutationPlan,
    UncertainApplyError,
    VersionedMutationPort,
    apply_approved_plan,
    apply_versioned_plan,
    canonical_plan_hash,
    canonical_reviewed_diff_hash,
)
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


def plan() -> MutationPlan:
    return MutationPlan(
        library_id="local-library",
        item_key="ABC123",
        source_fingerprint="a" * 64,
        mutations=(
            Mutation(kind="tag", target="#rock-mechanics", action="add"),
            Mutation(kind="collection", target="to-look", action="add"),
        ),
    )


def _batch_preview() -> tuple[PreviewPlan, ApplyRequest]:
    items = []
    for number in range(10):
        operation = PlannedOperation.build(sequence=0, resource_type="tag", action="add", target=f"#topic-{number}", before_present=False, after_present=True, version_precondition=PreviewVersion(version=1))
        items.append(PlannedItem(item_key=f"ITEM{number:02d}", source_fingerprint="a" * 64, preview_item_version=1, classification_projection={}, operations=(operation,)))
    frozen_items = tuple(items)
    snapshot = Snapshot(value={}, digest=canonical_sha256({}))
    payload = {
        "preview_id": "batch-preview",
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
    operation_ids = tuple(operation.operation_id for item in preview.items for operation in item.operations)
    evidence = ApprovalEvidence.create(approval_id="batch-approval", approved_plan_hash=preview.plan_hash, approved_at=datetime(2026, 1, 1, tzinfo=UTC), approved_item_keys=preview.selected_item_keys, reviewed_operation_ids=operation_ids, reviewed_diff_hash=preview.reviewed_diff_hash)
    return preview, ApplyRequest(preview_id=preview.preview_id, plan_hash=preview.plan_hash, approval=evidence)


def test_canonical_ten_item_preview_is_persisted_and_revalidated(tmp_path: Path) -> None:
    preview, request = _batch_preview()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    assert ledger.persist_preview_request(preview, request)
    assert not ledger.persist_preview_request(preview, request)
    loaded_preview, loaded_request = ledger.load_preview_request(preview.plan_hash)
    assert loaded_preview.plan_hash == preview.plan_hash
    assert loaded_request == request


def test_plan_json_round_trip_and_hash_are_canonical() -> None:
    first = plan()
    reordered = MutationPlan(
        library_id=first.library_id,
        item_key=first.item_key,
        source_fingerprint=first.source_fingerprint,
        mutations=tuple(reversed(first.mutations)),
    )

    assert MutationPlan.model_validate_json(first.model_dump_json()) == first
    assert canonical_plan_hash(first) == canonical_plan_hash(reordered)
    assert first.plan_hash == canonical_plan_hash(first)


def test_approval_requires_the_exact_plan_hash() -> None:
    with pytest.raises(ValidationError):
        Approval(plan_hash="not-a-hash", approved_by="local-user")


def authorization(mutation_plan: MutationPlan | None = None) -> ApplyAuthorization:
    approved_plan = mutation_plan or plan()
    return ApplyAuthorization.for_plan(approved_plan, authorization_id="approval-001")


def test_apply_authorization_is_immutable_and_digest_bound() -> None:
    approved = authorization()

    assert approved.confirmation_digest == ApplyAuthorization.confirmation_digest_for(
        plan_hash=approved.plan_hash,
        reviewed_diff_hash=approved.reviewed_diff_hash,
        approved_item_keys=approved.approved_item_keys,
        approved_operation_ids=approved.approved_operation_ids,
    )
    with pytest.raises(ValidationError):
        ApplyAuthorization.model_validate(
            {**approved.model_dump(), "approved_item_keys": ("OTHER",)}
        )
    with pytest.raises(ValidationError):
        approved.plan_hash = "b" * 64  # type: ignore[misc]


def test_reviewed_diff_hash_is_a_complete_ordered_golden_projection() -> None:
    mutation_plan = plan()
    independently_projected_rows = [
        {
            "item_key": "ABC123",
            "operation_id": "0f1c766e98ced6dd17a77fd54a967b451ed7184890e879a5295360e4ae0e4118",
            "kind": "collection",
            "target": "to-look",
            "action": "add",
        },
        {
            "item_key": "ABC123",
            "operation_id": "a43f8d2072631a768ad61baf7c32856601591c5186f3a36497812ec1d12891a6",
            "kind": "tag",
            "target": "#rock-mechanics",
            "action": "add",
        },
    ]
    canonical_json = json.dumps(
        independently_projected_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    independently_hashed = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    assert canonical_reviewed_diff_hash(mutation_plan) == independently_hashed
    assert independently_hashed == "5e0b555710d869f608303b6f2b43b106bf6c2099645db5efb03f2879ea804b7f"
    assert authorization(mutation_plan).reviewed_diff_hash == independently_hashed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plan_hash", "b" * 64),
        ("reviewed_diff_hash", "b" * 64),
        ("approved_item_keys", ("OTHER",)),
        ("approved_operation_ids", ("b" * 64,)),
    ],
)
def test_authorization_digest_rejects_tampering_with_bound_content(
    field: str, value: object
) -> None:
    approved = authorization()

    with pytest.raises(ValidationError, match="confirmation digest"):
        ApplyAuthorization.model_validate({**approved.model_dump(), field: value})


def test_authorization_is_immutable_in_sqlite_and_planned_rows_require_its_fk(
    tmp_path: Path,
) -> None:
    mutation_plan = plan()
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")

    ledger.persist_authorization_and_plan(approved, mutation_plan)

    row = ledger.connection.execute(
        "SELECT plan_hash, confirmation_digest FROM apply_authorization WHERE authorization_id = ?",
        (approved.authorization_id,),
    ).fetchone()
    assert row == (approved.plan_hash, approved.confirmation_digest)
    assert ledger.connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.connection.execute(
            "UPDATE apply_authorization SET plan_hash = ? WHERE authorization_id = ?",
            ("b" * 64, approved.authorization_id),
        )
    with pytest.raises(sqlite3.IntegrityError):
        ledger.connection.execute(
            "DELETE FROM apply_authorization WHERE authorization_id = ?",
            (approved.authorization_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        ledger.connection.execute(
            "INSERT INTO mutation_ledger(plan_hash, authorization_id, state) VALUES (?, ?, 'planned')",
            (mutation_plan.plan_hash, "missing-authorization"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        ledger.connection.execute(
            "INSERT INTO operation_ledger "
            "(authorization_id, operation_id, state, expected_version, observed_version) "
            "VALUES (?, ?, 'planned', 0, NULL)",
            ("missing-authorization", "a" * 64),
        )


def test_audit_artifacts_are_owner_only_and_reject_symlink_paths(tmp_path: Path) -> None:
    database = tmp_path / "private" / "audit.sqlite3"
    ledger = AuditLedger(database)
    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    ledger.close()
    link = tmp_path / "link.sqlite3"
    link.symlink_to(database)
    with pytest.raises(ValueError, match="symlinks"):
        AuditLedger(link)


def test_preview_contract_is_data_only_and_never_calls_a_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingPort(InMemoryMutationPort):
        calls = 0

        def apply(self, mutation_plan: MutationPlan):  # type: ignore[no-untyped-def]
            self.calls += 1
            return super().apply(mutation_plan)

    monkeypatch.setattr(
        socket, "create_connection", lambda *args, **kwargs: pytest.fail("network access")
    )
    preview = plan()
    port = CountingPort()

    assert preview.model_dump(mode="json")["library_id"] == "local-library"
    assert not hasattr(preview, "apply")
    assert port.calls == 0


def test_attempt_evidence_is_durable_before_attempt_and_only_verified_adds_establish_ownership(
    tmp_path: Path,
) -> None:
    mutation_plan = plan()
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_authorization_and_plan(approved, mutation_plan)
    operation_id = mutation_plan.operation_ids[0]
    ledger.record_operation(approved.authorization_id, operation_id, "planned", expected_version=7)
    evidence = AttemptEvidence(
        operation_id=operation_id, idempotency_key="b" * 64, item_key=mutation_plan.item_key,
        item_version=7, tags=("#human",), collection_keys=("LOOKKEY",),
        preserved_field_hashes={"metadata": "c" * 64},
    )
    ledger.record_attempt(approved.authorization_id, evidence)
    assert ledger.attempt_evidence_for(approved.authorization_id, operation_id) == evidence
    assert ledger.operation_entries_for(approved.authorization_id)[-1].state == "attempted"
    with pytest.raises(ValueError, match="planned"):
        ledger.record_attempt(approved.authorization_id, evidence)

    ledger.record_operation(approved.authorization_id, operation_id, "verified", 7, observed_version=8)
    ledger.record_managed_provenance(
        approved.authorization_id, evidence, resource="tag", target="#managed", verified_version=8
    )
    assert ledger.managed_removal_is_authorized(
        operation_id, item_key=mutation_plan.item_key, resource="tag", target="#managed", expected_version=8
    )
    assert not ledger.managed_removal_is_authorized(
        operation_id, item_key=mutation_plan.item_key, resource="tag", target="#managed", expected_version=9
    )


def test_approved_plan_records_wal_states_and_verifies_exact_diff(tmp_path: Path) -> None:
    mutation_plan = plan()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    port = InMemoryMutationPort()
    approval = Approval(plan_hash=mutation_plan.plan_hash, approved_by="local-user")

    result = apply_approved_plan(mutation_plan, approval, port, ledger)

    assert result.plan_hash == mutation_plan.plan_hash
    assert result.actual_diff == mutation_plan.expected_diff
    assert [entry.state for entry in ledger.entries_for(mutation_plan.plan_hash)] == [
        "planned",
        "attempted",
        "verified",
    ]
    assert ledger.journal_mode == "wal"


def test_apply_fails_closed_when_port_returns_a_non_exact_diff(tmp_path: Path) -> None:
    class WrongPort(InMemoryMutationPort):
        def apply(self, mutation_plan: MutationPlan):  # type: ignore[no-untyped-def]
            return mutation_plan.expected_diff[:-1]

    mutation_plan = plan()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")

    with pytest.raises(ExactDiffMismatch):
        apply_approved_plan(
            mutation_plan,
            Approval(plan_hash=mutation_plan.plan_hash, approved_by="local-user"),
            WrongPort(),
            ledger,
        )

    assert [entry.state for entry in ledger.entries_for(mutation_plan.plan_hash)] == [
        "planned",
        "attempted",
    ]


class ScriptedVersionedPort(VersionedMutationPort):
    def __init__(self, initial_version: int, next_versions: list[int]) -> None:
        self.initial_version = initial_version
        self.next_versions = iter(next_versions)
        self.calls: list[tuple[str, int]] = []
        self.read_calls: list[tuple[str, int]] = []
        self._applied: dict[str, tuple[DiffEntry, int]] = {}

    def read_version(self, mutation_plan: MutationPlan) -> int:
        return self.initial_version

    def apply_operation(self, mutation: Mutation, *, expected_version: int, operation_id: str):  # type: ignore[no-untyped-def]
        self.calls.append((operation_id, expected_version))
        result = (
            DiffEntry(kind=mutation.kind, target=mutation.target, action=mutation.action),
            next(self.next_versions),
        )
        self._applied[operation_id] = result
        return result

    def read_operation(self, mutation: Mutation, *, expected_version: int, operation_id: str):  # type: ignore[no-untyped-def]
        del mutation
        self.read_calls.append((operation_id, expected_version))
        return self._applied.get(operation_id)


def test_versioned_apply_chains_only_verified_observed_versions(tmp_path: Path) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    port = ScriptedVersionedPort(initial_version=7, next_versions=[8, 9])

    result = apply_versioned_plan(mutation_plan, approved, port, ledger)

    assert result.terminal_state == "verified"
    assert [expected_version for _, expected_version in port.calls] == [7, 8]
    assert [expected_version for _, expected_version in port.read_calls] == [7, 8]
    assert [entry.state for entry in result.entries] == [
        "planned",
        "attempted",
        "verified",
        "planned",
        "attempted",
        "verified",
    ]


def test_ledger_persistence_failure_prevents_any_versioned_port_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    port = ScriptedVersionedPort(initial_version=7, next_versions=[8, 9])

    def fail_before_authority_is_durable(*_: object) -> None:
        raise sqlite3.OperationalError("injected ledger failure")

    monkeypatch.setattr(ledger, "persist_authorization_and_plan", fail_before_authority_is_durable)

    with pytest.raises(sqlite3.OperationalError, match="injected ledger failure"):
        apply_versioned_plan(mutation_plan, approved, port, ledger)

    assert port.calls == []
    assert port.read_calls == []


def test_stale_version_marks_terminal_paths_without_port_calls(tmp_path: Path) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    port = ScriptedVersionedPort(initial_version=8, next_versions=[])

    result = apply_versioned_plan(mutation_plan, approved, port, ledger)

    assert result.terminal_state == "skipped_stale"
    assert port.calls == []
    assert [entry.state for entry in result.entries] == ["skipped_stale", "aborted"]


def test_identical_reapply_replays_stale_terminal_events_without_new_calls(tmp_path: Path) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    stale_port = ScriptedVersionedPort(initial_version=8, next_versions=[])

    first = apply_versioned_plan(mutation_plan, approved, stale_port, ledger)
    replay_port = ScriptedVersionedPort(initial_version=7, next_versions=[8, 9])
    replay = apply_versioned_plan(mutation_plan, approved, replay_port, ledger)

    assert first == replay
    assert replay_port.calls == []


def test_restart_recovery_uses_exact_persisted_authorization_and_no_port(tmp_path: Path) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    database = tmp_path / "audit.sqlite3"
    initial_ledger = AuditLedger(database)
    apply_versioned_plan(
        mutation_plan,
        approved,
        ScriptedVersionedPort(initial_version=8, next_versions=[]),
        initial_ledger,
    )
    initial_ledger.close()

    restarted_ledger = AuditLedger(database)
    report = restarted_ledger.recover_authorized_plan(approved, mutation_plan)

    assert report.state == "skipped_stale"
    assert report.counts == {
        "planned": 0,
        "attempted": 0,
        "verified": 0,
        "skipped_stale": 1,
        "aborted": 1,
    }
    with pytest.raises(ValueError, match="exact persisted"):
        restarted_ledger.recover_authorized_plan(
            approved.model_copy(update={"authorization_id": "different-approval"}), mutation_plan
        )


def test_lost_response_reapply_uses_readback_never_replays_or_synthesizes_verified(
    tmp_path: Path,
) -> None:
    class LostResponsePort(ScriptedVersionedPort):
        def apply_operation(self, mutation: Mutation, *, expected_version: int, operation_id: str):  # type: ignore[no-untyped-def]
            super().apply_operation(
                mutation, expected_version=expected_version, operation_id=operation_id
            )
            raise TimeoutError("response lost after write")

    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    first_port = LostResponsePort(initial_version=7, next_versions=[8])

    with pytest.raises(TimeoutError, match="response lost"):
        apply_versioned_plan(mutation_plan, approved, first_port, ledger)
    assert [entry.state for entry in ledger.operation_entries_for(approved.authorization_id)] == [
        "planned",
        "attempted",
    ]

    readback_port = ScriptedVersionedPort(initial_version=7, next_versions=[])
    readback_port._applied[mutation_plan.operation_ids[0]] = (
        mutation_plan.expected_diff[0],
        8,
    )
    result = apply_versioned_plan(mutation_plan, approved, readback_port, ledger)

    assert result.terminal_state == "aborted"
    assert readback_port.calls == []
    assert readback_port.read_calls == [(mutation_plan.operation_ids[0], 7)]
    assert [entry.state for entry in result.entries] == [
        "planned",
        "attempted",
        "verified",
        "aborted",
    ]


def test_reapply_of_unverified_nonversioned_apply_fails_closed(tmp_path: Path) -> None:
    class LostResponsePort(InMemoryMutationPort):
        def apply(self, mutation_plan: MutationPlan):  # type: ignore[no-untyped-def]
            del mutation_plan
            raise TimeoutError("response lost after write")

    mutation_plan = plan()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    approval = Approval(plan_hash=mutation_plan.plan_hash, approved_by="local-user")

    with pytest.raises(TimeoutError):
        apply_approved_plan(mutation_plan, approval, LostResponsePort(), ledger)
    with pytest.raises(UncertainApplyError, match="explicit read-back"):
        apply_approved_plan(mutation_plan, approval, InMemoryMutationPort(), ledger)


class LostResponseVersionedPort(ScriptedVersionedPort):
    """Simulates a remote operation whose response was lost after the attempt."""

    def apply_operation(self, mutation: Mutation, *, expected_version: int, operation_id: str):  # type: ignore[no-untyped-def]
        self.calls.append((operation_id, expected_version))
        raise TimeoutError("response lost after remote mutation")


def test_lost_response_reapply_never_verifies_by_replay_alone(tmp_path: Path) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    lost_response_port = LostResponseVersionedPort(initial_version=7, next_versions=[])

    with pytest.raises(TimeoutError, match="response lost"):
        apply_versioned_plan(mutation_plan, approved, lost_response_port, ledger)

    assert [entry.state for entry in ledger.operation_entries_for(approved.authorization_id)] == [
        "planned",
        "attempted",
    ]

    replay_port = ScriptedVersionedPort(initial_version=7, next_versions=[8, 9])
    replay = apply_versioned_plan(mutation_plan, approved, replay_port, ledger)

    assert replay.terminal_state == "aborted"
    assert replay_port.calls == []
    assert all(entry.state != "verified" for entry in replay.entries)


def test_restart_recovery_marks_attempted_only_operation_uncertain(tmp_path: Path) -> None:
    mutation_plan = plan().model_copy(update={"source_version": 7})
    approved = authorization(mutation_plan)
    database = tmp_path / "audit.sqlite3"
    initial_ledger = AuditLedger(database)

    with pytest.raises(TimeoutError):
        apply_versioned_plan(
            mutation_plan,
            approved,
            LostResponseVersionedPort(initial_version=7, next_versions=[]),
            initial_ledger,
        )
    initial_ledger.close()

    report = AuditLedger(database).recover_authorized_plan(approved, mutation_plan)

    assert report.state == "aborted"
    assert report.counts["attempted"] == 1
    assert report.counts["verified"] == 0
