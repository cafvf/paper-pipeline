from datetime import UTC, datetime
from pathlib import Path

import pytest

from paper_triage.cli import main, render_report
from paper_triage.projects import ReadOnlyEfforts
from paper_triage.reporting import ItemRunResult, RunCounters, RunReport


def test_efforts_discovery_is_read_only_and_returns_empty_for_empty_root(tmp_path: Path) -> None:
    assert ReadOnlyEfforts(tmp_path).discover() == ()
    (tmp_path / "Project.md").write_text("# Project", encoding="utf-8")
    profile = ReadOnlyEfforts(tmp_path).discover()[0]
    assert profile.display_name == "Project"
    assert profile.source_relative_path == "Project.md"
    assert not hasattr(ReadOnlyEfforts, "write")


def test_efforts_rejects_a_symlink_root_before_resolving(tmp_path: Path) -> None:
    target = tmp_path / "real-efforts"
    target.mkdir()
    alias = tmp_path / "Efforts"
    alias.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="real directory"):
        ReadOnlyEfforts(alias)

def test_report_is_sanitized_and_counter_bound() -> None:
    counters = RunCounters(operations_planned=1, operations_attempted=1, operations_verified=1, operations_failed=0, operations_uncertain=0, operations_skipped_stale=0, operations_aborted=0)
    report = RunReport(mode="preview", status="success", started_at=datetime(2026, 1, 1, tzinfo=UTC), finished_at=datetime(2026, 1, 1, tzinfo=UTC), ruleset_version="1", taxonomy_version="1", selected_item_count=1, item_results=(ItemRunResult(item_key="ABC", outcome="verified"),), counters=counters)
    assert report.model_dump(mode="json")["selected_item_count"] == 1
    assert '"status": "success"' in render_report(report)
    assert main(("report",)) == 0
    with pytest.raises(ValueError, match="monotonic"):
        RunReport(**{**report.model_dump(), "finished_at": datetime(2025, 1, 1, tzinfo=UTC)})


def test_rendered_report_redacts_credential_like_issue_text() -> None:
    counters = RunCounters(operations_planned=0, operations_attempted=0, operations_verified=0, operations_failed=0, operations_uncertain=0, operations_skipped_stale=0, operations_aborted=0)
    report = RunReport(mode="preview", status="failed", started_at=datetime(2026, 1, 1, tzinfo=UTC), finished_at=datetime(2026, 1, 1, tzinfo=UTC), ruleset_version="1", taxonomy_version="1", selected_item_count=0, counters=counters)
    # RunReport itself permits only sanitized Issue models; check the renderer's
    # independent last-line defense with a model copy containing a safe field.
    rendered = render_report(report.model_copy(update={"redaction_summary": {"token=not-a-secret": 1}}))
    assert "token=[REDACTED]" in rendered
    assert "token=not-a-secret" not in rendered
