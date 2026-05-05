from pathlib import Path

from paper_pipeline.run_summary import write_run_summary
from paper_pipeline.runner import NightlyRunResult


def test_write_run_summary_creates_inbox_report(tmp_path: Path):
    result = NightlyRunResult(
        applied_decisions=[{"citekey": "old", "status": "pending", "errors": []}],
        selected=["a"],
        blocked_missing_pdf=["b"],
        notes_written=["+/a - LLM Paper Decision.md"],
    )
    path = write_run_summary(tmp_path / "+", result, run_id="run1")
    text = path.read_text(encoding="utf-8")
    assert "LLM Paper Pipeline Run run1" in text
    assert "`a`" in text
    assert "`b`" in text
    assert "`old`" in text
