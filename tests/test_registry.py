import json
import sqlite3
from pathlib import Path

import pytest

from paper_pipeline.cli import main as cli_main
from paper_pipeline.contracts import PipelineError, ValidationError
from paper_pipeline.registry import (
    PairProcessingDecision,
    initialize_registry,
    load_jsonl,
    record_pair_hash,
    should_process_pair,
    sync_registry_from_jsonl,
    upsert_papers,
    upsert_projects,
)


def project_profile(**overrides):
    profile = {
        "project_id": "cptu_bayesian_classification",
        "title": "CPTu Bayesian Soil Classification",
        "source_path": "Efforts/On/CPTu Bayesian Soil Classification.md",
        "objectives": ["Develop a hybrid probabilistic model for CPTu soil classification"],
        "methods": ["CPTu", "Robertson chart"],
        "knowledge_gaps": ["distance to nonlinear chart regions"],
        "expected_outputs": ["paper"],
        "priority": "high",
        "project_state": "on",
        "state_source": "Efforts/On",
        "tags": ["#soil-classification"],
        "links": [],
        "content_hash": "sha256:project-a",
    }
    profile.update(overrides)
    return profile


def paper_profile(**overrides):
    profile = {
        "citekey": "robertson1990soilclassification",
        "zotero_key": "ABC123",
        "title": "Soil classification using the cone penetration test",
        "year": 1990,
        "authors": ["Robertson"],
        "abstract": "Abstract text when available.",
        "collections": [".ToLook", "CPTu"],
        "tags": ["cpt", "classification"],
        "doi": "10.0000/example",
        "has_pdf": True,
        "pdf_paths": [],
        "paper_hash": "sha256:paper-a",
        "metadata_snapshot_path": "papers/robertson1990soilclassification/metadata_snapshot.json",
    }
    profile.update(overrides)
    return profile


def test_initialize_registry_creates_expected_tables(tmp_path: Path):
    db_path = tmp_path / "data" / "registry" / "registry.sqlite"

    conn = initialize_registry(db_path)

    tables = {
        row[0]
        for row in conn.execute(
            "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
        )
    }
    assert db_path.exists()
    assert {
        "schema_migrations",
        "projects",
        "papers",
        "project_paper_candidates",
        "llm_classifications",
        "human_reviews",
        "processing_runs",
        "hashes",
    }.issubset(tables)
    assert conn.execute("select version from schema_migrations").fetchall() == [(1,)]


def test_upsert_projects_and_papers_are_idempotent_and_update_hashes(tmp_path: Path):
    conn = initialize_registry(tmp_path / "registry.sqlite")
    project = project_profile()
    paper = paper_profile()

    first_projects = upsert_projects(conn, [project])
    first_papers = upsert_papers(conn, [paper])
    second_projects = upsert_projects(conn, [project])
    updated_papers = upsert_papers(conn, [paper_profile(title="Updated title", paper_hash="sha256:paper-b")])

    assert first_projects.inserted == 1
    assert first_papers.inserted == 1
    assert second_projects.unchanged == 1
    assert updated_papers.updated == 1
    assert conn.execute("select count(*) from projects").fetchone() == (1,)
    assert conn.execute("select count(*) from papers").fetchone() == (1,)
    assert conn.execute("select title, paper_hash from papers").fetchone() == ("Updated title", "sha256:paper-b")


def test_invalid_project_profile_rolls_back_without_partial_rows(tmp_path: Path):
    conn = initialize_registry(tmp_path / "registry.sqlite")
    valid = project_profile()
    invalid = project_profile(project_id="broken id with spaces")

    with pytest.raises(ValidationError, match="project_profile.schema.json validation failed"):
        upsert_projects(conn, [valid, invalid])

    assert conn.execute("select count(*) from projects").fetchone() == (0,)


def test_duplicate_project_ids_with_conflicting_hashes_emit_warning_and_keep_latest(tmp_path: Path):
    conn = initialize_registry(tmp_path / "registry.sqlite")
    first = project_profile(title="Old title", content_hash="sha256:project-a")
    second = project_profile(title="New title", content_hash="sha256:project-b")

    report = upsert_projects(conn, [first, second])

    assert report.inserted == 1
    assert report.updated == 1
    assert report.warnings == [
        "duplicate project_id in batch with different content_hash: cptu_bayesian_classification"
    ]
    assert conn.execute("select title, content_hash from projects").fetchone() == ("New title", "sha256:project-b")


def test_pair_processing_decision_skips_unchanged_hashes_and_processes_changes(tmp_path: Path):
    conn = initialize_registry(tmp_path / "registry.sqlite")
    upsert_projects(conn, [project_profile()])
    upsert_papers(conn, [paper_profile()])

    before_record = should_process_pair(
        conn,
        project_id="cptu_bayesian_classification",
        citekey="robertson1990soilclassification",
        project_hash="sha256:project-a",
        paper_hash="sha256:paper-a",
        prompt_hash="sha256:prompt-a",
    )
    record_pair_hash(
        conn,
        project_id="cptu_bayesian_classification",
        citekey="robertson1990soilclassification",
        project_hash="sha256:project-a",
        paper_hash="sha256:paper-a",
        prompt_hash="sha256:prompt-a",
    )
    unchanged = should_process_pair(
        conn,
        project_id="cptu_bayesian_classification",
        citekey="robertson1990soilclassification",
        project_hash="sha256:project-a",
        paper_hash="sha256:paper-a",
        prompt_hash="sha256:prompt-a",
    )
    changed = should_process_pair(
        conn,
        project_id="cptu_bayesian_classification",
        citekey="robertson1990soilclassification",
        project_hash="sha256:project-a",
        paper_hash="sha256:paper-b",
        prompt_hash="sha256:prompt-a",
    )

    assert before_record == PairProcessingDecision(should_process=True, reason="new_pair", warnings=[])
    assert unchanged == PairProcessingDecision(should_process=False, reason="unchanged", warnings=[])
    assert changed == PairProcessingDecision(should_process=True, reason="hash_changed", warnings=[])


def test_pair_processing_warns_when_registry_rows_are_missing(tmp_path: Path):
    conn = initialize_registry(tmp_path / "registry.sqlite")

    decision = should_process_pair(
        conn,
        project_id="missing_project",
        citekey="missing_paper",
        project_hash="sha256:project-a",
        paper_hash="sha256:paper-a",
        prompt_hash="sha256:prompt-a",
    )

    assert decision.should_process is True
    assert decision.reason == "missing_registry_row"
    assert decision.warnings == [
        "project missing from registry: missing_project",
        "paper missing from registry: missing_paper",
    ]


def test_registry_connection_enables_foreign_key_enforcement(tmp_path: Path):
    conn = initialize_registry(tmp_path / "registry.sqlite")

    with pytest.raises(sqlite3.IntegrityError):
        record_pair_hash(
            conn,
            project_id="missing_project",
            citekey="missing_paper",
            project_hash="sha256:project-a",
            paper_hash="sha256:paper-a",
            prompt_hash="sha256:prompt-a",
        )


def test_load_jsonl_reads_valid_rows_and_warns_about_blank_lines(tmp_path: Path):
    path = tmp_path / "projects.jsonl"
    path.write_text(json.dumps(project_profile()) + "\n\n", encoding="utf-8")

    rows, warnings = load_jsonl(path, artifact_name="projects")

    assert rows == [project_profile()]
    assert warnings == ["projects JSONL contains blank line at 2"]


def test_load_jsonl_reports_invalid_json_with_line_number(tmp_path: Path):
    path = tmp_path / "papers.jsonl"
    path.write_text(json.dumps(paper_profile()) + "\n{broken json}\n", encoding="utf-8")

    with pytest.raises(PipelineError, match=r"papers JSONL invalid JSON at line 2"):
        load_jsonl(path, artifact_name="papers")


def test_load_jsonl_rejects_non_object_lines(tmp_path: Path):
    path = tmp_path / "projects.jsonl"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(PipelineError, match="projects JSONL line 1 must be a JSON object"):
        load_jsonl(path, artifact_name="projects")


def test_load_jsonl_reports_missing_artifact_without_creating_registry(tmp_path: Path):
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(PipelineError, match="projects JSONL not found"):
        load_jsonl(missing, artifact_name="projects")


def test_sync_registry_from_jsonl_imports_projects_and_papers_idempotently(tmp_path: Path):
    projects_path = tmp_path / "data" / "projects.jsonl"
    papers_path = tmp_path / "data" / "papers.jsonl"
    projects_path.parent.mkdir(parents=True)
    projects_path.write_text(json.dumps(project_profile()) + "\n", encoding="utf-8")
    papers_path.write_text(json.dumps(paper_profile()) + "\n", encoding="utf-8")
    db_path = tmp_path / "data" / "registry" / "registry.sqlite"

    first = sync_registry_from_jsonl(db_path, projects_path=projects_path, papers_path=papers_path)
    second = sync_registry_from_jsonl(db_path, projects_path=projects_path, papers_path=papers_path)

    assert first.projects.inserted == 1
    assert first.papers.inserted == 1
    assert second.projects.unchanged == 1
    assert second.papers.unchanged == 1
    conn = sqlite3.connect(db_path)
    assert conn.execute("select count(*) from projects").fetchone() == (1,)
    assert conn.execute("select count(*) from papers").fetchone() == (1,)


def test_sync_registry_from_jsonl_initializes_empty_registry_when_default_artifacts_are_missing(tmp_path: Path):
    db_path = tmp_path / "data" / "registry" / "registry.sqlite"

    report = sync_registry_from_jsonl(
        db_path,
        projects_path=tmp_path / "data" / "projects.jsonl",
        papers_path=tmp_path / "data" / "papers.jsonl",
    )

    assert report.projects.inserted == 0
    assert report.papers.inserted == 0
    assert report.warnings == [
        f"projects JSONL not found, skipping: {tmp_path / 'data' / 'projects.jsonl'}",
        f"papers JSONL not found, skipping: {tmp_path / 'data' / 'papers.jsonl'}",
    ]
    conn = sqlite3.connect(db_path)
    assert conn.execute("select count(*) from projects").fetchone() == (0,)
    assert conn.execute("select count(*) from papers").fetchone() == (0,)


def test_sync_registry_from_jsonl_can_import_only_available_inventory(tmp_path: Path):
    projects_path = tmp_path / "data" / "projects.jsonl"
    papers_path = tmp_path / "data" / "papers.jsonl"
    projects_path.parent.mkdir(parents=True)
    projects_path.write_text(json.dumps(project_profile()) + "\n", encoding="utf-8")

    report = sync_registry_from_jsonl(
        tmp_path / "data" / "registry" / "registry.sqlite",
        projects_path=projects_path,
        papers_path=papers_path,
    )

    assert report.projects.inserted == 1
    assert report.papers.inserted == 0
    assert report.warnings == [f"papers JSONL not found, skipping: {papers_path}"]


def test_sync_registry_from_jsonl_rolls_back_when_paper_artifact_is_invalid(tmp_path: Path):
    projects_path = tmp_path / "projects.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    projects_path.write_text(json.dumps(project_profile()) + "\n", encoding="utf-8")
    papers_path.write_text(json.dumps(paper_profile(citekey="bad citekey")) + "\n", encoding="utf-8")
    db_path = tmp_path / "registry.sqlite"

    with pytest.raises(ValidationError, match="paper_profile.schema.json validation failed"):
        sync_registry_from_jsonl(db_path, projects_path=projects_path, papers_path=papers_path)

    conn = sqlite3.connect(db_path)
    assert conn.execute("select count(*) from projects").fetchone() == (0,)
    assert conn.execute("select count(*) from papers").fetchone() == (0,)


def test_sync_registry_from_jsonl_combines_warnings_from_loader_and_upserts(tmp_path: Path):
    projects_path = tmp_path / "projects.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    projects_path.write_text(
        "\n".join(
            [
                json.dumps(project_profile(content_hash="sha256:project-a")),
                "",
                json.dumps(project_profile(title="Changed", content_hash="sha256:project-b")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    papers_path.write_text(json.dumps(paper_profile()) + "\n", encoding="utf-8")

    report = sync_registry_from_jsonl(tmp_path / "registry.sqlite", projects_path=projects_path, papers_path=papers_path)

    assert report.warnings == [
        "projects JSONL contains blank line at 2",
        "duplicate project_id in batch with different content_hash: cptu_bayesian_classification",
    ]


def test_cli_sync_registry_writes_sqlite_and_reports_warnings(tmp_path: Path, capsys):
    projects_path = tmp_path / "projects.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    projects_path.write_text(json.dumps(project_profile()) + "\n\n", encoding="utf-8")
    papers_path.write_text(json.dumps(paper_profile()) + "\n", encoding="utf-8")
    db_path = tmp_path / "data" / "registry" / "registry.sqlite"

    exit_code = cli_main(
        [
            "sync-registry",
            "--db",
            str(db_path),
            "--projects",
            str(projects_path),
            "--papers",
            str(papers_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "projects inserted=1 updated=0 unchanged=0" in output
    assert "papers inserted=1 updated=0 unchanged=0" in output
    assert "WARNING projects JSONL contains blank line at 2" in output
    assert db_path.exists()


def test_cli_sync_registry_with_no_arguments_uses_default_paths_and_warns_for_missing_artifacts(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)

    exit_code = cli_main(["sync-registry"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "projects inserted=0 updated=0 unchanged=0" in output
    assert "papers inserted=0 updated=0 unchanged=0" in output
    assert "WARNING projects JSONL not found, skipping: data/projects.jsonl" in output
    assert "WARNING papers JSONL not found, skipping: data/papers.jsonl" in output
    assert (tmp_path / "data" / "registry" / "registry.sqlite").exists()


def test_cli_sync_registry_with_only_db_argument_uses_default_inventory_paths(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "custom.sqlite"

    exit_code = cli_main(["sync-registry", "--db", str(db_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "WARNING projects JSONL not found, skipping: data/projects.jsonl" in output
    assert "WARNING papers JSONL not found, skipping: data/papers.jsonl" in output
    assert db_path.exists()


def test_cli_sync_registry_with_only_projects_imports_projects_and_warns_for_missing_papers(tmp_path: Path, capsys):
    projects_path = tmp_path / "projects.jsonl"
    projects_path.write_text(json.dumps(project_profile()) + "\n", encoding="utf-8")
    db_path = tmp_path / "registry.sqlite"

    exit_code = cli_main(["sync-registry", "--db", str(db_path), "--projects", str(projects_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "projects inserted=1 updated=0 unchanged=0" in output
    assert "papers inserted=0 updated=0 unchanged=0" in output
    assert "WARNING papers JSONL not found, skipping: data/papers.jsonl" in output


def test_cli_sync_registry_reports_errors_without_traceback_or_partial_rows(tmp_path: Path, capsys):
    projects_path = tmp_path / "projects.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    projects_path.write_text(json.dumps(project_profile()) + "\n", encoding="utf-8")
    papers_path.write_text("{broken json}\n", encoding="utf-8")
    db_path = tmp_path / "registry.sqlite"

    exit_code = cli_main(
        [
            "sync-registry",
            "--db",
            str(db_path),
            "--projects",
            str(projects_path),
            "--papers",
            str(papers_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "sync-registry error: papers JSONL invalid JSON at line 1" in captured.err
    assert "Traceback" not in captured.err
    assert not db_path.exists()


def test_cli_sync_registry_validation_error_rolls_back_created_database(tmp_path: Path, capsys):
    projects_path = tmp_path / "projects.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    projects_path.write_text(json.dumps(project_profile()) + "\n", encoding="utf-8")
    papers_path.write_text(json.dumps(paper_profile(citekey="bad citekey")) + "\n", encoding="utf-8")
    db_path = tmp_path / "registry.sqlite"

    exit_code = cli_main(
        [
            "sync-registry",
            "--db",
            str(db_path),
            "--projects",
            str(projects_path),
            "--papers",
            str(papers_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "paper_profile.schema.json validation failed" in captured.err
    assert "Traceback" not in captured.err
    conn = sqlite3.connect(db_path)
    assert conn.execute("select count(*) from projects").fetchone() == (0,)
    assert conn.execute("select count(*) from papers").fetchone() == (0,)


def test_cli_sync_registry_reports_corrupt_existing_database_without_traceback(tmp_path: Path, capsys):
    db_path = tmp_path / "data" / "registry" / "registry.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("not a sqlite database", encoding="utf-8")

    exit_code = cli_main(["sync-registry", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "sync-registry error:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_sync_registry_reports_database_path_directory_without_traceback(tmp_path: Path, capsys):
    db_path = tmp_path / "data" / "registry.sqlite"
    db_path.mkdir(parents=True)

    exit_code = cli_main(["sync-registry", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "sync-registry error:" in captured.err
    assert "Traceback" not in captured.err
