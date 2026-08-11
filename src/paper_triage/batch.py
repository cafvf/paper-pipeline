"""Canonical local batch execution over an immutable, approved preview.

The executor receives a plan hash rather than in-memory approval artifacts.  It
therefore has exactly one authority source: the ``AuditLedger`` record that
bound the preview and apply request before execution.  The mutation port is
injected, which makes this boundary usable with an in-process fake and keeps it
free from connector configuration or network behavior.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date
from typing import Protocol

from .audit import AttemptEvidence, AuditLedger, OperationLedgerEntry
from .plans import ApplyRequest, PlannedItem, PlannedOperation, PreviewPlan
from .zotero import ManagedMutationProvenance, ZoteroMutationCommand, ZoteroMutationReceipt


class BatchMutationPort(Protocol):
    """The preflight/write capability needed by the canonical batch executor."""

    def capture_attempt_evidence(
        self, *, operation_id: str, idempotency_key: str, item_key: str, run_date: date
    ) -> AttemptEvidence:
        """Read a fresh, complete item snapshot before a possible external write."""

    def mutate_item(self, command: ZoteroMutationCommand) -> ZoteroMutationReceipt: ...


@dataclass(frozen=True)
class BatchApplyResult:
    """Observed results of one complete, persisted-preview batch execution."""

    plan_hash: str
    preview_id: str
    authorization_id: str
    commands: tuple[ZoteroMutationCommand, ...]
    receipts: tuple[ZoteroMutationReceipt, ...]


def command_for_operation(
    preview: PreviewPlan,
    item: PlannedItem,
    operation: PlannedOperation,
    *,
    expected_version: int,
) -> ZoteroMutationCommand:
    """Create one command using the version observed immediately before it."""
    return ZoteroMutationCommand(
        operation_id=operation.operation_id,
        idempotency_key=hashlib.sha256(
            f"{preview.plan_hash}:{operation.operation_id}".encode()
        ).hexdigest(),
        item_key=item.item_key,
        expected_version=expected_version,
        resource=operation.resource_type,
        action=operation.action,
        target=operation.target,
        expected_present=operation.before_present,
        desired_present=operation.after_present,
    )


def commands_for_approved_preview(
    preview: PreviewPlan, request: ApplyRequest
) -> tuple[ZoteroMutationCommand, ...]:
    """Derive only the explicitly reviewed operations in deterministic order."""
    request.validates(preview)
    commands: list[ZoteroMutationCommand] = []
    for item in preview.items:
        for operation in item.operations:
            # This projection is useful for preview/reporting only. A write
            # executor must call ``command_for_operation`` after every reread.
            commands.append(command_for_operation(preview, item, operation, expected_version=item.preview_item_version))
    return tuple(commands)


def execute_persisted_preview(
    plan_hash: str, ledger: AuditLedger, port: BatchMutationPort
) -> BatchApplyResult:
    """Apply every reviewed operation from one exact persisted ten-item preview.

    No preview, approval, command, or allowlist is accepted from the caller.
    ``AuditLedger.load_preview_request`` reconstructs and validates the immutable
    pair; validation is repeated at this execution boundary before any command
    exists or the injected port can be called.  Preview items are already
    canonicalized by ``PreviewPlan`` in ascending item-key order, so projecting
    their operations produces deterministic port calls.  A fresh pre-call
    snapshot is committed to the operation ledger before every mutation.  A
    port exception is terminal for this invocation: the operation is marked
    uncertain and no later item may be attempted.
    """

    preview, request = ledger.load_preview_request(plan_hash)
    if preview.plan_hash != plan_hash:
        raise ValueError("persisted preview hash does not match requested plan")
    request.validates(preview)
    authorization_id = ledger.persist_preview_authorization(plan_hash)
    commands: list[ZoteroMutationCommand] = []
    receipts: list[ZoteroMutationReceipt] = []

    for item in preview.items:
        verified_version: int | None = None
        for operation in item.operations:
            idempotency_key = _idempotency_key(preview, operation)
            prior = _latest_operation_entry(ledger, authorization_id, operation.operation_id)

            # A completed operation is immutable history.  Reapplying the same
            # approved plan must neither re-read nor replay its external write.
            if prior is not None and prior.state == "verified":
                if prior.observed_version is None:
                    _abort_remaining(
                        preview, ledger, authorization_id, item.item_key, operation.operation_id,
                        expected_version=item.preview_item_version,
                    )
                    raise ValueError("verified operation has no observed version")
                verified_version = prior.observed_version
                continue
            if prior is not None and prior.state in {"failed", "skipped_stale", "aborted"}:
                raise ValueError("persisted batch execution is already terminal")

            evidence = port.capture_attempt_evidence(
                operation_id=operation.operation_id,
                idempotency_key=idempotency_key,
                item_key=item.item_key,
                run_date=preview.run_date,
            )
            _validate_attempt_evidence(evidence, item, operation, idempotency_key)

            expected_version = (
                item.preview_item_version if verified_version is None else verified_version
            )
            if prior is not None and prior.state in {"attempted", "uncertain"}:
                # Recovery sees the post-write version, so it cannot use the
                # original optimistic-lock comparison.  It must instead prove
                # that the fresh snapshot is the exact approved membership
                # delta from the durable pre-write evidence.
                try:
                    _recover_attempted_operation(
                        ledger,
                        authorization_id,
                        operation,
                        evidence,
                        prior.expected_version,
                    )
                except ValueError:
                    _abort_remaining(
                        preview,
                        ledger,
                        authorization_id,
                        item.item_key,
                        operation.operation_id,
                        expected_version=prior.expected_version,
                    )
                    raise
                verified_version = evidence.item_version
                continue

            if not _snapshot_matches_expected(
                evidence,
                item,
                expected_version=expected_version,
                require_source_fingerprint=verified_version is None,
            ):
                ledger.record_operation(
                    authorization_id,
                    operation.operation_id,
                    "skipped_stale",
                    expected_version,
                    evidence.item_version,
                )
                _abort_remaining(
                    preview,
                    ledger,
                    authorization_id,
                    item.item_key,
                    operation.operation_id,
                    expected_version=expected_version,
                )
                raise ValueError("fresh item snapshot does not match the approved preview")

            command = command_for_operation(
                preview, item, operation, expected_version=evidence.item_version
            )
            command = _with_ledger_removal_provenance(
                command, operation, ledger, expected_version=evidence.item_version
            )
            if prior is None:
                ledger.record_operation(
                    authorization_id, operation.operation_id, "planned", evidence.item_version
                )
            elif prior.state == "planned" and prior.expected_version != evidence.item_version:
                # Dependent operations are authorized before execution but
                # receive their concrete optimistic-lock version only after
                # their predecessor's verified receipt.  This append-only
                # transition keeps both facts durable without rewriting the
                # immutable authorization row.
                ledger.prepare_operation(
                    authorization_id, operation.operation_id, expected_version=evidence.item_version
                )
            elif prior.state not in {"planned", "prepared"}:
                # Defensive: all legal active and terminal states were handled above.
                raise ValueError("operation has an illegal persisted execution state")
            # This durable transaction must complete before the port is allowed
            # to issue an external write.
            ledger.record_attempt(authorization_id, evidence)
            try:
                receipt = port.mutate_item(command)
            except Exception:
                ledger.record_operation(
                    authorization_id, operation.operation_id, "uncertain", evidence.item_version
                )
                raise
            if receipt.item_key != item.item_key or receipt.accepted_version <= evidence.item_version:
                ledger.record_operation(
                    authorization_id,
                    operation.operation_id,
                    "failed",
                    evidence.item_version,
                    receipt.accepted_version,
                )
                raise ValueError("mutation receipt does not advance the planned item version")
            ledger.record_operation(
                authorization_id,
                operation.operation_id,
                "verified",
                evidence.item_version,
                receipt.accepted_version,
            )
            if operation.action == "add":
                ledger.record_managed_provenance(
                    authorization_id,
                    evidence,
                    resource=operation.resource_type,
                    target=operation.target,
                    verified_version=receipt.accepted_version,
                )
            commands.append(command)
            receipts.append(receipt)
            verified_version = receipt.accepted_version

    return BatchApplyResult(
        plan_hash=preview.plan_hash,
        preview_id=preview.preview_id,
        authorization_id=authorization_id,
        commands=tuple(commands),
        receipts=tuple(receipts),
    )


def _idempotency_key(preview: PreviewPlan, operation: PlannedOperation) -> str:
    return hashlib.sha256(f"{preview.plan_hash}:{operation.operation_id}".encode()).hexdigest()


def _validate_attempt_evidence(
    evidence: AttemptEvidence,
    item: PlannedItem,
    operation: PlannedOperation,
    idempotency_key: str,
) -> None:
    if (
        evidence.operation_id != operation.operation_id
        or evidence.idempotency_key != idempotency_key
        or evidence.item_key != item.item_key
    ):
        raise ValueError("fresh attempt evidence does not match the planned operation")


def _snapshot_matches_expected(
    evidence: AttemptEvidence,
    item: PlannedItem,
    *,
    expected_version: int,
    require_source_fingerprint: bool,
) -> bool:
    """Check the fresh optimistic-lock version and the initial source snapshot.

    The preview fingerprint is carried in the write-ahead evidence under the
    explicit ``source`` key.  Later operations on the same item deliberately
    compare against the immediately verified version instead: the executor's
    own preceding membership write necessarily changed the Zotero version.
    """
    return evidence.item_version == expected_version and (
        not require_source_fingerprint
        or evidence.preserved_field_hashes.get("source") == item.source_fingerprint
    )


def _latest_operation_entry(
    ledger: AuditLedger, authorization_id: str, operation_id: str
) -> OperationLedgerEntry | None:
    entries = ledger.operation_entries_for(authorization_id)
    return next((entry for entry in reversed(entries) if entry.operation_id == operation_id), None)


def _is_exact_recovery_diff(
    before: AttemptEvidence, after: AttemptEvidence, operation: PlannedOperation
) -> bool:
    """Accept recovery only when evidence proves the sole approved delta.

    Membership snapshots prove the requested tag/collection delta precisely;
    the complete safe fingerprint map prevents an unrelated data-field edit
    from being mistaken for a successful mutation.  A port that cannot provide
    stable target-excluded safe fingerprints is therefore conservatively
    unrecoverable rather than allowed to replay or claim success.
    """
    before_tags = set(before.tags)
    before_collections = set(before.collection_keys)
    expected_tags = before_tags.copy()
    expected_collections = before_collections.copy()
    target_set = expected_tags if operation.resource_type == "tag" else expected_collections
    if operation.after_present:
        target_set.add(operation.target)
    else:
        target_set.discard(operation.target)
    return (
        set(after.tags) == expected_tags
        and set(after.collection_keys) == expected_collections
        and after.preserved_field_hashes == before.preserved_field_hashes
    )


def _recover_attempted_operation(
    ledger: AuditLedger,
    authorization_id: str,
    operation: PlannedOperation,
    evidence: AttemptEvidence,
    attempted_version: int,
) -> None:
    """Resolve a possibly-issued write with read-back, never a replay."""
    attempted_evidence = ledger.attempt_evidence_for(authorization_id, operation.operation_id)
    if attempted_evidence is None:
        raise ValueError("attempted operation has no durable attempt evidence")
    if evidence.item_version > attempted_version and _is_exact_recovery_diff(
        attempted_evidence, evidence, operation
    ):
        ledger.record_operation(
            authorization_id,
            operation.operation_id,
            "verified",
            attempted_version,
            evidence.item_version,
        )
        if operation.action == "add":
            ledger.record_managed_provenance(
                authorization_id,
                attempted_evidence,
                resource=operation.resource_type,
                target=operation.target,
                verified_version=evidence.item_version,
            )
        return

    ledger.record_operation(
        authorization_id,
        operation.operation_id,
        "failed",
        attempted_version,
        evidence.item_version,
    )
    raise ValueError("interrupted operation cannot be verified by fresh read-back")


def _abort_remaining(
    preview: PreviewPlan,
    ledger: AuditLedger,
    authorization_id: str,
    current_item_key: str,
    current_operation_id: str,
    *,
    expected_version: int,
) -> None:
    """Make a stale preflight a fully terminal, non-resumable batch outcome."""
    current_seen = False
    for item in preview.items:
        for operation in item.operations:
            if not current_seen:
                current_seen = (
                    item.item_key == current_item_key and operation.operation_id == current_operation_id
                )
                continue
            prior = _latest_operation_entry(ledger, authorization_id, operation.operation_id)
            if prior is None or prior.state in {"planned", "prepared"}:
                ledger.record_operation(
                    authorization_id, operation.operation_id, "aborted", expected_version
                )


def _with_ledger_removal_provenance(
    command: ZoteroMutationCommand,
    operation: PlannedOperation,
    ledger: AuditLedger,
    *,
    expected_version: int,
) -> ZoteroMutationCommand:
    if operation.action != "remove":
        return command
    assert operation.ownership_mutation_id is not None  # Guaranteed by PlannedOperation.
    ownership = ledger.managed_provenance_for(
        operation.ownership_mutation_id,
        item_key=command.item_key,
        resource=command.resource,
        target=command.target,
        expected_version=expected_version,
    )
    if ownership is None:
        raise PermissionError("planned removal has no current ledger-owned provenance")
    ownership_evidence = ledger.attempt_evidence_for(
        ownership.authorization_id, ownership.operation_id
    )
    if ownership_evidence is None:
        raise PermissionError("ledger-owned removal provenance has no attempt evidence")
    return replace(
        command,
        provenance=ManagedMutationProvenance(
            operation_id=ownership.operation_id,
            idempotency_key=ownership_evidence.idempotency_key,
            item_key=ownership.item_key,
            resource=ownership.resource,
            target=ownership.target,
            added_version=ownership.verified_version,
        ),
    )
