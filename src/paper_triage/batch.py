"""Pure conversion from a durable approved preview to Zotero mutation commands.

This module deliberately has no I/O.  The executor layer must load the exact
preview/request pair from ``AuditLedger`` before invoking this converter.
"""

from __future__ import annotations

import hashlib

from .plans import ApplyRequest, PlannedItem, PlannedOperation, PreviewPlan
from .zotero import ZoteroMutationCommand


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
