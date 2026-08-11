"""Pure conversion from a durable approved preview to Zotero mutation commands.

This module deliberately has no I/O.  The executor layer must load the exact
preview/request pair from ``AuditLedger`` before invoking this converter.
"""

from __future__ import annotations

import hashlib

from .plans import ApplyRequest, PreviewPlan
from .zotero import ZoteroMutationCommand


def commands_for_approved_preview(
    preview: PreviewPlan, request: ApplyRequest
) -> tuple[ZoteroMutationCommand, ...]:
    """Derive only the explicitly reviewed operations in deterministic order."""
    request.validates(preview)
    commands: list[ZoteroMutationCommand] = []
    for item in preview.items:
        for operation in item.operations:
            commands.append(
                ZoteroMutationCommand(
                    operation_id=operation.operation_id,
                    idempotency_key=hashlib.sha256(
                        f"{preview.plan_hash}:{operation.operation_id}".encode()
                    ).hexdigest(),
                    item_key=item.item_key,
                    expected_version=item.preview_item_version,
                    resource=operation.resource_type,
                    action=operation.action,
                    target=operation.target,
                    expected_present=operation.before_present,
                    desired_present=operation.after_present,
                )
            )
    return tuple(commands)
