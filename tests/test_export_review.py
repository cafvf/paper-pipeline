import json
import re
from pathlib import Path

import pytest
import yaml

from paper_pipeline.cli import main as cli_main, build_parser
from paper_pipeline.contracts import PipelineError, ValidationError
from paper_pipeline.export_review import (
    ExportReviewError,
    default_review_id,
    default_review_output_path,
    render_review_markdown,
    run_export_review_from_jsonl,
)

FIXTURE_ROOT = Path("tests/fixtures/contracts")


def test_cli_parser_supports_export_review():
    args = build_parser().parse_args(
        [
            "export-review",
            "--classifications",
            "data/classifications.jsonl",
            "--output",
            "data/custom-review.md",
            "--date",
            "2026-05-18",
            "--review-id",
            "review_2026-05-18_initial_triage",
        ]
    )
    assert args.command == "export-review"
    assert args.classifications == "data/classifications.jsonl"
    assert args.output == "data/custom-review.md"
    assert args.date == "2026-05-18"
    assert args.review_id == "review_2026-05-18_initial_triage"


def test_default_review_paths_are_dated():
    assert (
        default_review_output_path("2026-05-18")
        == "data/review-project-papers-2026-05-18.md"
    )
    assert default_review_id("2026-05-18") == "review_2026-05-18_initial_triage"


def test_render_review_markdown_groups_multi_project_citekeys_and_renders_yaml_blocks(
    tmp_path: Path,
):
    rows = [
        _classification(
            project_id="project_a",
            utility_class="methodological",
            recommended_action="read_later",
            recommended_zotero_stage="Expendable",
        ),
        _classification(
            project_id="project_b",
            utility_class="essential",
            recommended_action="read_now",
            citekey="samepaper2026",
            recommended_zotero_stage=".To Revise",
        ),
        _classification(
            project_id="project_a",
            utility_class="methodological",
            recommended_action="read_later",
            citekey="samepaper2026",
            recommended_zotero_stage="Expendable",
        ),
        _classification(
            project_id="project_c",
            utility_class="irrelevant_now",
            recommended_action="ignore_for_now",
            citekey="irrelevant2026",
            title="Irrelevant Paper",
        ),
    ]
    _write_metadata_snapshot(tmp_path, "samepaper2026", "Same Paper Title")
    _write_metadata_snapshot(
        tmp_path, "robertson1990soilclassification", "Robertson 1990"
    )
    _write_metadata_snapshot(tmp_path, "irrelevant2026", "Irrelevant Paper")

    markdown = render_review_markdown(
        rows,
        review_id="review_2026-05-18_initial_triage",
        review_path="data/review-project-papers-2026-05-18.md",
        artifact_root=tmp_path,
    )

    assert "# Project Paper Review - 2026-05-18" in markdown
    assert "## High-utility papers" in markdown
    assert "## No-use papers" in markdown
    assert markdown.count("Citekey: `samepaper2026`") == 1
    assert (
        "- `project_b`: essential, read_now, recommended stage .To Revise" in markdown
    )
    assert (
        "- `project_a`: methodological, read_later, recommended stage Expendable"
        in markdown
    )
    blocks = _yaml_blocks(markdown)
    assert len(blocks) == 3
    samepaper = next(block for block in blocks if block["citekey"] == "samepaper2026")
    assert samepaper["decision"] == "pending"
    assert samepaper["review_item_id"] == "samepaper2026"
    assert samepaper["review_path"] == "data/review-project-papers-2026-05-18.md"
    assert samepaper["approved_actions"] == ["read_now", "read_later"]
    assert samepaper["recommended_zotero_stage"] == ".To Revise"
    assert [item["project_id"] for item in samepaper["project_decisions"]] == [
        "project_b",
        "project_a",
    ]
    assert samepaper["project_decisions"][0]["approved_actions"] == ["read_now"]


def test_run_export_review_from_jsonl_writes_deterministic_review(tmp_path: Path):
    classifications = tmp_path / "data" / "classifications.jsonl"
    output = tmp_path / "data" / "review-project-papers-2026-05-18.md"
    rows = [
        _classification(
            project_id="project_a",
            utility_class="methodological",
            recommended_action="read_later",
        ),
        _classification(
            project_id="project_b",
            utility_class="essential",
            recommended_action="read_now",
            citekey="samepaper2026",
            recommended_zotero_stage=".To Revise",
        ),
        _classification(
            project_id="project_a",
            utility_class="methodological",
            recommended_action="read_later",
            citekey="samepaper2026",
            recommended_zotero_stage="Expendable",
        ),
    ]
    write_jsonl(classifications, rows)
    _write_metadata_snapshot(tmp_path, "samepaper2026", "Same Paper Title")
    _write_metadata_snapshot(
        tmp_path, "robertson1990soilclassification", "Robertson 1990"
    )

    result = run_export_review_from_jsonl(
        classifications_path=classifications,
        output_path=output,
        review_id="review_2026-05-18_initial_triage",
        review_date="2026-05-18",
        artifact_root=tmp_path,
    )

    assert result.output_path == output
    assert result.review_items == 2
    text = output.read_text(encoding="utf-8")
    assert text == output.read_text(encoding="utf-8")
    assert "Allowed project decisions" in text
    assert "Same Paper Title" in text


def test_run_export_review_from_jsonl_is_atomic_on_render_failure(
    tmp_path: Path, monkeypatch
):
    classifications = tmp_path / "data" / "classifications.jsonl"
    output = tmp_path / "data" / "review-project-papers-2026-05-18.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("previous\n", encoding="utf-8")
    write_jsonl(classifications, [_classification()])

    monkeypatch.setattr(
        "paper_pipeline.export_review.render_review_markdown",
        lambda *args, **kwargs: (_ for _ in ()).throw(PipelineError("boom")),
    )

    with pytest.raises(PipelineError, match="boom"):
        run_export_review_from_jsonl(
            classifications_path=classifications,
            output_path=output,
            review_id="review_2026-05-18_initial_triage",
            review_date="2026-05-18",
        )

    assert output.read_text(encoding="utf-8") == "previous\n"
    assert not output.with_suffix(".md.tmp").exists()


def test_run_export_review_from_jsonl_rejects_invalid_json_line(tmp_path: Path):
    classifications = tmp_path / "data" / "classifications.jsonl"
    classifications.parent.mkdir(parents=True, exist_ok=True)
    classifications.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(
        PipelineError, match="classifications JSONL invalid JSON at line 1"
    ):
        run_export_review_from_jsonl(
            classifications_path=classifications,
            output_path=tmp_path / "data" / "review-project-papers-2026-05-18.md",
            review_id="review_2026-05-18_initial_triage",
            review_date="2026-05-18",
        )


def test_run_export_review_from_jsonl_rejects_schema_invalid_row(tmp_path: Path):
    classifications = tmp_path / "data" / "classifications.jsonl"
    row = _classification(recommended_action="not_allowed")
    write_jsonl(classifications, [row])

    with pytest.raises(
        ValidationError,
        match="llm_classification\\.schema\\.json validation failed",
    ):
        run_export_review_from_jsonl(
            classifications_path=classifications,
            output_path=tmp_path / "data" / "review-project-papers-2026-05-18.md",
            review_id="review_2026-05-18_initial_triage",
            review_date="2026-05-18",
        )


def test_render_review_markdown_rejects_row_missing_citekey():
    with pytest.raises(ExportReviewError, match="classification row missing citekey"):
        render_review_markdown(
            [_classification(citekey="")],
            review_id="review_2026-05-18_initial_triage",
            review_path="data/review-project-papers-2026-05-18.md",
        )


def test_render_review_markdown_is_deterministic_across_input_order(tmp_path: Path):
    rows = [
        _classification(
            project_id="project_c",
            utility_class="irrelevant_now",
            recommended_action="ignore_for_now",
            citekey="samepaper2026",
            title="Same Paper",
        ),
        _classification(
            project_id="project_a",
            utility_class="essential",
            recommended_action="read_now",
            citekey="samepaper2026",
            title="Same Paper",
        ),
        _classification(
            project_id="project_b",
            utility_class="methodological",
            recommended_action="read_later",
            citekey="anotherpaper2026",
            title="Another Paper",
        ),
    ]
    _write_metadata_snapshot(tmp_path, "samepaper2026", "Same Paper")
    _write_metadata_snapshot(tmp_path, "anotherpaper2026", "Another Paper")

    first = render_review_markdown(
        rows,
        review_id="review_2026-05-18_initial_triage",
        review_path="data/review-project-papers-2026-05-18.md",
        artifact_root=tmp_path,
    )
    second = render_review_markdown(
        list(reversed(rows)),
        review_id="review_2026-05-18_initial_triage",
        review_path="data/review-project-papers-2026-05-18.md",
        artifact_root=tmp_path,
    )

    assert first == second


def test_render_review_markdown_escapes_multiline_and_quoted_content(tmp_path: Path):
    row = _classification(
        citekey="quotedpaper2026",
        reason='Line one with "quotes"\nand line two',
        possible_uses=['Use "A"', "Use\nB"],
        limitations=['Limit "X"', "Line\nY"],
        stage_recommendation_reason='Move to ".To Revise"\nwhen approved',
    )
    _write_metadata_snapshot(tmp_path, "quotedpaper2026", 'Quoted "Paper"\nTitle')

    markdown = render_review_markdown(
        [row],
        review_id="review_2026-05-18_initial_triage",
        review_path="data/review-project-papers-2026-05-18.md",
        artifact_root=tmp_path,
    )

    assert '### Quoted "Paper" Title' in markdown
    assert 'Summary: Line one with "quotes" and line two' in markdown
    assert '  - Use "A"' in markdown
    assert "  - Use B" in markdown
    block = _yaml_blocks(markdown)[0]
    assert block["stage_recommendation_reason"] == 'Move to ".To Revise"\nwhen approved'


def test_cli_export_review_writes_review_with_explicit_paths(tmp_path: Path, capsys):
    classifications = tmp_path / "data" / "classifications.jsonl"
    output = tmp_path / "data" / "review-project-papers-2026-05-18.md"
    write_jsonl(classifications, [_classification()])
    _write_metadata_snapshot(
        tmp_path, "robertson1990soilclassification", "Robertson 1990"
    )

    exit_code = cli_main(
        [
            "export-review",
            "--classifications",
            str(classifications),
            "--output",
            str(output),
            "--date",
            "2026-05-18",
            "--review-id",
            "review_2026-05-18_initial_triage",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"review_items=1 output={output}" in captured.out
    assert output.exists()
    assert "Traceback" not in captured.err


def test_cli_export_review_reports_missing_classifications_without_traceback(
    tmp_path: Path, capsys
):
    output = tmp_path / "data" / "review-project-papers-2026-05-18.md"

    exit_code = cli_main(
        [
            "export-review",
            "--classifications",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(output),
            "--date",
            "2026-05-18",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "export-review error:" in captured.err
    assert "classifications JSONL not found" in captured.err
    assert "Traceback" not in captured.err


def _classification(**overrides):
    row = json.loads(
        (FIXTURE_ROOT / "llm_classification.valid.json").read_text(encoding="utf-8")
    )
    row.update(overrides)
    row["input_products"] = [f"papers/{row['citekey']}/metadata_snapshot.json"]
    return row


def _write_metadata_snapshot(root: Path, citekey: str, title: str):
    path = root / "papers" / citekey / "metadata_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"citekey": citekey, "title": title}), encoding="utf-8")


def _yaml_blocks(text: str):
    blocks = re.findall(r"```yaml\n(.*?)\n```", text, re.S)
    return [yaml.safe_load(block) for block in blocks]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
