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
    validate_classification_coherence,
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


class SequencedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.message_history = []

    def complete_json(self, messages, schema):
        self.calls += 1
        self.message_history.append(list(messages))
        return self.responses.pop(0)


def test_write_classifications_jsonl_is_atomic_when_classification_is_invalid(
    tmp_path: Path,
):
    output = tmp_path / "data" / "classifications.jsonl"
    output.parent.mkdir(parents=True)
    output.write_text("previous\n", encoding="utf-8")
    invalid = _fixture("llm_classification.valid.json")
    invalid["confidence"] = "certain"

    with pytest.raises(
        ValidationError, match="llm_classification.schema.json validation failed"
    ):
        write_classifications_jsonl(output, [invalid])

    assert output.read_text(encoding="utf-8") == "previous\n"
    assert not output.with_suffix(".jsonl.tmp").exists()


def test_run_classify_from_jsonl_writes_valid_deterministic_classifications(
    tmp_path: Path,
):
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
    assert persisted[0]["input_products"] == [
        "papers/robertson1990soilclassification/metadata_snapshot.json"
    ]
    assert persisted_lines[0] == json.dumps(
        persisted[0], ensure_ascii=False, sort_keys=True
    )
    validate_instance(persisted[0], "llm_classification.schema.json")
    item_files = sorted((tmp_path / "data" / "classifications").glob("*.json"))
    assert len(item_files) == 1
    assert json.loads(item_files[0].read_text(encoding="utf-8")) == persisted[0]
    progress = json.loads(
        (tmp_path / "data" / "classifications.progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert progress["status"] == "complete"
    assert progress["completed_candidates"] == 1
    assert progress["total_candidates"] == 1
    assert progress["items_dir"].endswith("data/classifications")


def test_run_classify_fails_when_candidate_project_is_missing_without_partial_output(
    tmp_path: Path,
):
    candidates = tmp_path / "candidates.jsonl"
    projects = tmp_path / "projects.jsonl"
    papers = tmp_path / "papers.jsonl"
    output = tmp_path / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])

    with pytest.raises(
        PipelineError,
        match="classify input missing project: cptu_bayesian_classification",
    ):
        run_classify_from_jsonl(
            candidates_path=candidates,
            projects_path=projects,
            papers_path=papers,
            output_path=output,
            client=FixedClient(json.dumps(_fixture("llm_classification.valid.json"))),
        )

    assert not output.exists()


def test_run_classify_retries_invalid_model_output_without_partial_output(
    tmp_path: Path,
):
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


def test_run_classify_persists_completed_candidates_and_failure_progress(
    tmp_path: Path,
):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    candidate_a = _fixture("project_paper_match.valid.json")
    candidate_b = {**candidate_a, "citekey": "secondpaper2026", "rank": 2}
    paper_a = _fixture("paper_profile.valid.json")
    paper_b = {
        **paper_a,
        "citekey": "secondpaper2026",
        "metadata_snapshot_path": "papers/secondpaper2026/metadata_snapshot.json",
    }

    write_jsonl(candidates, [candidate_a, candidate_b])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [paper_a, paper_b])
    client = SequencedClient(
        [
            json.dumps(_fixture("llm_classification.valid.json")),
            "Here is JSON:\n{}",
            "Here is JSON:\n{}",
        ]
    )

    with pytest.raises(PipelineError, match="single JSON object without prose"):
        run_classify_from_jsonl(
            candidates_path=candidates,
            projects_path=projects,
            papers_path=papers,
            output_path=output,
            client=client,
            max_attempts=2,
        )

    assert client.calls == 3
    assert not output.exists()
    item_files = sorted((tmp_path / "data" / "classifications").glob("*.json"))
    assert len(item_files) == 1
    persisted = json.loads(item_files[0].read_text(encoding="utf-8"))
    assert persisted["citekey"] == "robertson1990soilclassification"
    progress = json.loads(
        (tmp_path / "data" / "classifications.progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert progress["status"] == "failed"
    assert progress["completed_candidates"] == 1
    assert progress["total_candidates"] == 2
    assert progress["last_completed"]["citekey"] == "robertson1990soilclassification"
    assert progress["error"].endswith("single JSON object without prose")


def test_run_classify_accepts_valid_reasoning_json_when_content_is_empty(
    tmp_path: Path,
):
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


def test_run_classify_respects_max_candidates_cap(tmp_path: Path):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    candidate_a = _fixture("project_paper_match.valid.json")
    candidate_b = {**candidate_a, "citekey": "secondpaper2026", "rank": 2}
    paper_a = _fixture("paper_profile.valid.json")
    paper_b = {
        **paper_a,
        "citekey": "secondpaper2026",
        "metadata_snapshot_path": "papers/secondpaper2026/metadata_snapshot.json",
    }
    client = FixedClient(json.dumps(_fixture("llm_classification.valid.json")))

    write_jsonl(candidates, [candidate_a, candidate_b])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [paper_a, paper_b])

    rows = run_classify_from_jsonl(
        candidates_path=candidates,
        projects_path=projects,
        papers_path=papers,
        output_path=output,
        client=client,
        max_candidates=1,
    )

    assert client.calls == 1
    assert len(rows) == 1
    assert rows[0]["citekey"] == "robertson1990soilclassification"


def test_run_classify_filters_candidates_by_paper_stage(tmp_path: Path):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    candidate_a = _fixture("project_paper_match.valid.json")
    candidate_b = {**candidate_a, "citekey": "todig2026", "rank": 2}
    paper_a = _fixture("paper_profile.valid.json")
    paper_b = {
        **paper_a,
        "citekey": "todig2026",
        "collections": [".ToDig", "CPTu"],
        "metadata_snapshot_path": "papers/todig2026/metadata_snapshot.json",
    }
    valid = _fixture("llm_classification.valid.json")
    valid["recommended_zotero_stage"] = ".ToDig"
    client = FixedClient(json.dumps(valid))

    write_jsonl(candidates, [candidate_a, candidate_b])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [paper_a, paper_b])

    rows = run_classify_from_jsonl(
        candidates_path=candidates,
        projects_path=projects,
        papers_path=papers,
        output_path=output,
        client=client,
        paper_stages=(".ToDig",),
    )

    assert client.calls == 1
    assert len(rows) == 1
    assert rows[0]["citekey"] == "todig2026"


def test_validate_classification_coherence_rejects_useful_expendable_pair():
    classification = _fixture("llm_classification.valid.json")
    classification.update(
        {
            "utility_class": "essential",
            "recommended_action": "read_now",
            "recommended_zotero_stage": "Expendable",
        }
    )

    with pytest.raises(
        ValidationError, match="useful classifications must not recommend Expendable"
    ):
        validate_classification_coherence(classification)


def test_validate_classification_coherence_rejects_irrelevant_active_action():
    classification = _fixture("llm_classification.valid.json")
    classification.update(
        {
            "utility_class": "irrelevant_now",
            "recommended_action": "read_now",
            "recommended_zotero_stage": ".To Revise",
        }
    )

    with pytest.raises(ValidationError, match="irrelevant_now must use ignore_for_now"):
        validate_classification_coherence(classification)


def test_validate_classification_coherence_rejects_equation_extraction_outside_todig():
    classification = _fixture("llm_classification.valid.json")
    classification.update(
        {
            "utility_class": "formulational",
            "recommended_action": "extract_equations",
            "recommended_zotero_stage": ".To Revise",
        }
    )

    with pytest.raises(
        ValidationError,
        match="extract_equations requires recommended_zotero_stage .ToDig",
    ):
        validate_classification_coherence(classification)


def test_validate_classification_coherence_rejects_metadata_only_demotion_from_todig():
    classification = _fixture("llm_classification.valid.json")
    classification.update(
        {
            "current_zotero_stage": ".ToDig",
            "recommended_zotero_stage": ".To Revise",
        }
    )

    with pytest.raises(
        ValidationError, match="metadata-only classification must not demote .ToDig"
    ):
        validate_classification_coherence(classification)


def test_run_classify_retries_semantically_incoherent_model_output(tmp_path: Path):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    invalid = _fixture("llm_classification.valid.json")
    invalid["recommended_zotero_stage"] = "Expendable"
    valid = _fixture("llm_classification.valid.json")

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    client = SequencedClient([json.dumps(invalid), json.dumps(valid)])

    rows = run_classify_from_jsonl(
        candidates_path=candidates,
        projects_path=projects,
        papers_path=papers,
        output_path=output,
        client=client,
        max_attempts=2,
    )

    assert client.calls == 2
    assert rows[0]["recommended_zotero_stage"] == ".To Revise"
    retry_message = client.message_history[1][-1]["content"]
    assert "Previous output failed validation" in retry_message
    assert "useful classifications must not recommend Expendable" in retry_message


def test_run_classify_reports_coherence_failure_without_partial_output(
    tmp_path: Path, monkeypatch, capsys
):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"
    invalid = _fixture("llm_classification.valid.json")
    invalid["recommended_zotero_stage"] = "Expendable"
    output.parent.mkdir(parents=True)
    output.write_text("previous\n", encoding="utf-8")

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    monkeypatch.setattr(
        "paper_pipeline.cli.LMStudioChatClient.complete_json",
        lambda self, messages, schema: json.dumps(invalid),
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
    assert exit_code == 2
    assert "useful classifications must not recommend Expendable" in captured.err
    assert output.read_text(encoding="utf-8") == "previous\n"


def test_cli_classify_writes_classifications_with_explicit_paths(
    tmp_path: Path, monkeypatch, capsys
):
    candidates = tmp_path / "data" / "candidates.jsonl"
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "classifications.jsonl"

    write_jsonl(candidates, [_fixture("project_paper_match.valid.json")])
    write_jsonl(projects, [_fixture("project_profile.valid.json")])
    write_jsonl(papers, [_fixture("paper_profile.valid.json")])
    monkeypatch.setattr(
        "paper_pipeline.cli.LMStudioChatClient.complete_json",
        lambda self, messages, schema: json.dumps(
            _fixture("llm_classification.valid.json")
        ),
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
    assert "classified=1/1" in captured.out
    assert "classifications=1" in captured.out
    assert f"output={output}" in captured.out
    assert "Traceback" not in captured.err
    rows = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
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
    monkeypatch.setattr(
        "paper_pipeline.cli.LMStudioChatClient.complete_json",
        lambda self, messages, schema: "Here is JSON:\n{}",
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
