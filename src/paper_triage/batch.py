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
from typing import Protocol

from .audit import AttemptEvidence, AuditLedger
from .plans import ApplyRequest, PlannedItem, PlannedOperation, PreviewPlan
from .zotero import ManagedMutationProvenance, ZoteroMutationCommand, ZoteroMutationReceipt


class BatchMutationPort(Protocol):
    """The preflight/write capability needed by the canonical batch executor."""

    def capture_attempt_evidence(
        self, *, operation_id: str, idempotency_key: str, item_key: str
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
            evidence = port.capture_attempt_evidence(
                operation_id=operation.operation_id,
                idempotency_key=idempotency_key,
                item_key=item.item_key,
            )
            _validate_attempt_evidence(evidence, item, operation, idempotency_key)
            if verified_version is not None and evidence.item_version != verified_version:
                ledger.record_operation(
                    authorization_id,
                    operation.operation_id,
                    "skipped_stale",
                    verified_version,
                    evidence.item_version,
                )
                raise ValueError("fresh item version does not match prior verified operation")

            command = command_for_operation(
                preview, item, operation, expected_version=evidence.item_version
            )
            command = _with_ledger_removal_provenance(
                command, operation, ledger, expected_version=evidence.item_version
            )
            ledger.record_operation(
                authorization_id, operation.operation_id, "planned", evidence.item_version
            )
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
                    "aborted",
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
