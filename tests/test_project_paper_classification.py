import json
from pathlib import Path

import pytest

from paper_pipeline.cli import main as cli_main
from paper_pipeline.contracts import PipelineError, ValidationError
from paper_pipeline.lmstudio_chat import LLMCompletion
from paper_pipeline.project_paper_classification import (
    CLASSIFICATION_PROMPT_HASH,
    build_classification_messages,
    run_classify_from_jsonl,
    write_classifications_jsonl,
)
from paper_pipeline.schema_validation import validate_instance


FIXTURE_ROOT = Path("tests/fixtures/contracts")


class FixedClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete_json(self, messages, schema):
        self.calls += 1
        return self.response


class FixedCompletionClient:
    def __init__(self, response: LLMCompletion):
        self.response = response
        self.calls = 0

    def complete_json(self, messages, schema):
        self.calls += 1
        return self.response


def test_write_classifications_jsonl_is_atomic_when_classification_is_invalid(tmp_path: Path):
    output = tmp_path / "data" / "classifications.jsonl"
    output.parent.mkdir(parents=True)
    output.write_text("previous\n", encoding="utf-8")
    invalid = _fixture("llm_classification.valid.json")
    invalid["confidence"] = "certain"

    with pytest.raises(ValidationError, match="llm_classification.schema.json validation failed"):
        write_classifications_jsonl(output, [invalid])

    assert output.read_text(encoding="utf-8") == "previous\n"
    assert not output.with_suffix(".jsonl.tmp").exists()


def test_run_classify_from_jsonl_writes_valid_deterministic_classifications(tmp_path: Path):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])

    rows = run_classify_from_jsonl(
        candidates_path=candidates,
        projects_path=projects,
        papers_path=papers,
        output_path=output,
        client=FixedClient(json.dumps(_fixture("llm_classification.valid.json"))),
    )

    assert len(rows) == 1
    persisted_lines = output.read_text(encoding="utf-8").splitlines()
    persisted = [json.loads(line) for line in persisted_lines]
    assert persisted == rows
    assert persisted[0]["project_id"] == "cptu_bayesian_classification"
    assert persisted[0]["citekey"] == "robertson1990soilclassification"
    assert persisted[0]["input_layer"] == "metadata"
    assert persisted[0]["prompt_hash"] == CLASSIFICATION_PROMPT_HASH
    assert persisted[0]["input_products"] == ["papers/robertson1990soilclassification/metadata_snapshot.json"]
    assert persisted_lines[0] == json.dumps(persisted[0], ensure_ascii=False, sort_keys=True)
    validate_instance(persisted[0], "llm_classification.schema.json")


def test_run_classify_fails_when_candidate_project_is_missing_without_partial_output(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    projects = tmp_path / "projects.jsonl"
    papers = tmp_path / "papers.jsonl"
    output = tmp_path / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])

    with pytest.raises(PipelineError, match="classify input missing project: cptu_bayesian_classification"):
        run_classify_from_jsonl(
            candidates_path=candidates,
            projects_path=projects,
            papers_path=papers,
            output_path=output,
            client=FixedClient(json.dumps(_fixture("llm_classification.valid.json"))),
        )

    assert not output.exists()


def test_run_classify_retries_invalid_model_output_without_partial_output(tmp_path: Path):
    candidates = tmp_path / "candidates.jsonl"
    projects = tmp_path / "projects.jsonl"
    papers = tmp_path / "papers.jsonl"
    output = tmp_path / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    client = FixedClient("Here is JSON:\n{}")

    with pytest.raises(PipelineError, match="single JSON object without prose"):
        run_classify_from_jsonl(
            candidates_path=candidates,
            projects_path=projects,
            papers_path=papers,
            output_path=output,
            client=client,
            max_attempts=2,
        )

    assert client.calls == 2
    assert not output.exists()


def test_run_classify_accepts_valid_reasoning_json_when_content_is_empty(tmp_path: Path):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    client = FixedCompletionClient(
        LLMCompletion(
            "",
            reasoning_content=json.dumps(_fixture("llm_classification.valid.json")),
        )
    )

    rows = run_classify_from_jsonl(
        candidates_path=candidates,
        projects_path=projects,
        papers_path=papers,
        output_path=output,
        client=client,
    )

    assert client.calls == 1
    assert len(rows) == 1
    assert rows[0]["citekey"] == "robertson1990soilclassification"


def test_run_classify_prefers_valid_content_over_reasoning_fallback(tmp_path: Path):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    valid = _fixture("llm_classification.valid.json")
    alternate = {**valid, "utility_class": "background"}

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    client = FixedCompletionClient(
        LLMCompletion(
            json.dumps(valid),
            reasoning_content=json.dumps(alternate),
        )
    )

    rows = run_classify_from_jsonl(
        candidates_path=candidates,
        projects_path=projects,
        papers_path=papers,
        output_path=output,
        client=client,
    )

    assert rows[0]["utility_class"] == valid["utility_class"]


def test_cli_classify_writes_classifications_with_explicit_paths(tmp_path: Path, monkeypatch, capsys):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    monkeypatch.setattr(
        "paper_pipeline.cli.LMStudioChatClient.complete_json",
        lambda self, messages, schema: json.dumps(_fixture("llm_classification.valid.json")),
    )

    exit_code = cli_main(
        [
            "classify",
            "--candidates",
            str(candidates),
            "--projects",
            str(projects),
            "--papers",
            str(papers),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "classifications=1" in captured.out
    assert f"output={output}" in captured.out
    assert "Traceback" not in captured.err
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["citekey"] == "robertson1990soilclassification"


def test_cli_classify_reports_invalid_llm_output_without_traceback_or_partial_output(
    tmp_path: Path, monkeypatch, capsys
):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    output.parent.mkdir(parents=True)
    output.write_text("previous\n", encoding="utf-8")

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    monkeypatch.setattr("paper_pipeline.cli.LMStudioChatClient.complete_json", lambda self, messages, schema: "Here is JSON:\n{}")

    exit_code = cli_main(
        [
            "classify",
            "--candidates",
            str(candidates),
            "--projects",
            str(projects),
            "--papers",
            str(papers),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "classify error:" in captured.err
    assert "single JSON object without prose" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_text(encoding="utf-8") == "previous\n"


def test_build_classification_messages_is_metadata_only():
    messages = build_classification_messages(
        project=_fixture("project_profile.valid.json"),
        paper=_fixture("paper_profile.valid.json"),
        candidate=_fixture("project_paper_match.valid.json"),
    )

    assert messages[0]["role"] == "system"
    assert "metadata-only" in messages[0]["content"]
    assert "PDF content" in messages[0]["content"]
    assert "Packet JSON:" in messages[1]["content"]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
