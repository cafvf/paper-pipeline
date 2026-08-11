from __future__ import annotations

from test_audit import _batch_preview

from paper_triage.batch import command_for_operation, commands_for_approved_preview


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
