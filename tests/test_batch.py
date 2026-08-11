from __future__ import annotations

from test_audit import _batch_preview

from paper_triage.batch import commands_for_approved_preview


def test_commands_are_derived_only_from_every_reviewed_preview_operation() -> None:
    preview, request = _batch_preview()
    commands = commands_for_approved_preview(preview, request)

    assert len(commands) == 10
    assert tuple(command.operation_id for command in commands) == request.approval.reviewed_operation_ids
    assert all(command.resource == "tag" and command.action == "add" for command in commands)
