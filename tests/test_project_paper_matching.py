import json
from pathlib import Path

from paper_pipeline.cli import main as cli_main
from paper_pipeline.project_paper_matching import (
    DEFAULT_MATCH_STATES,
    build_paper_text,
    build_project_text,
    match_project_papers,
    score_project_paper,
    write_candidates_jsonl,
)
from paper_pipeline.registry import (
    initialize_registry,
    record_pair_hash,
    upsert_papers,
    upsert_projects,
)
from paper_pipeline.schema_validation import validate_instance


def project_profile(**overrides):
    profile = {
        "project_id": "cptu_bayesian_classification",
        "title": "CPTu Bayesian Soil Classification",
        "source_path": "Efforts/On/CPTu Bayesian Soil Classification.md",
        "objectives": [
            "Develop a hybrid probabilistic model for CPTu soil classification"
        ],
        "methods": ["CPTu", "Robertson chart", "Bayesian updating"],
        "knowledge_gaps": ["distance to nonlinear chart regions"],
        "expected_outputs": ["paper"],
        "priority": "high",
        "project_state": "on",
        "state_source": "Efforts/On",
        "tags": ["#soil-classification", "%probabilistic"],
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
        "abstract": "CPTu soil classification charts and cone penetration interpretation.",
        "collections": [".ToLook", "CPTu"],
        "tags": ["cptu", "soil-classification"],
        "doi": "10.0000/example",
        "has_pdf": True,
        "pdf_paths": [],
        "paper_hash": "sha256:paper-a",
        "metadata_snapshot_path": "papers/robertson1990soilclassification/metadata_snapshot.json",
    }
    profile.update(overrides)
    return profile


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_text_builders_include_only_bounded_contract_fields():
    project = project_profile(body="private body should never be used")
    paper = paper_profile(local_secret="secret should never be used")

    assert "private body" not in build_project_text(project)
    assert "secret" not in build_paper_text(paper)
    assert "CPTu Bayesian Soil Classification" in build_project_text(project)
    assert "Soil classification using the cone penetration test" in build_paper_text(
        paper
    )


def test_score_project_paper_returns_score_and_evidence_for_overlapping_terms():
    score, evidence = score_project_paper(project_profile(), paper_profile())

    assert 0 < score <= 1
    assert any("cptu" in item.lower() for item in evidence)
    assert any("soil classification" in item.lower() for item in evidence)


def test_score_project_paper_returns_zero_without_evidence_for_irrelevant_paper():
    score, evidence = score_project_paper(
        project_profile(),
        paper_profile(
            citekey="unrelated2025",
            title="Urban traffic signal optimization",
            abstract="Vehicle routing and traffic lights.",
            tags=["traffic"],
            collections=["Transportation"],
            paper_hash="sha256:traffic",
            metadata_snapshot_path="papers/unrelated2025/metadata_snapshot.json",
        ),
    )

    assert score == 0
    assert evidence == []


def test_match_project_papers_ranks_deterministically_and_validates_candidates():
    projects = [project_profile()]
    papers = [
        paper_profile(
            citekey="weak2024",
            title="Bayesian model comparison",
            abstract="Priors and posterior checks.",
            paper_hash="sha256:weak",
            metadata_snapshot_path="papers/weak2024/metadata_snapshot.json",
        ),
        paper_profile(),
    ]

    candidates, report = match_project_papers(
        projects, papers, now="2026-05-12T12:00:00"
    )

    assert report.warnings == []
    assert [candidate["citekey"] for candidate in candidates] == [
        "robertson1990soilclassification",
        "weak2024",
    ]
    assert [candidate["rank"] for candidate in candidates] == [1, 2]
    assert candidates[0]["candidate_score"] >= candidates[1]["candidate_score"]
    for candidate in candidates:
        assert candidate["method"] == "lexical_v1"
        assert candidate["created_at"] == "2026-05-12T12:00:00"
        validate_instance(candidate, "project_paper_match.schema.json")


def test_match_project_papers_excludes_simmering_and_terminated_by_default():
    projects = [
        project_profile(
            project_id="active", project_state="on", content_hash="sha256:active"
        ),
        project_profile(
            project_id="later", project_state="simmering", content_hash="sha256:later"
        ),
        project_profile(
            project_id="done", project_state="terminated", content_hash="sha256:done"
        ),
    ]

    candidates, report = match_project_papers(projects, [paper_profile()])

    assert {candidate["project_id"] for candidate in candidates} == {"active"}
    assert report.skipped_projects == {"simmering": 1, "terminated": 1}
    assert DEFAULT_MATCH_STATES == ("on", "ongoing")


def test_match_project_papers_can_include_simmering_when_explicitly_requested():
    projects = [project_profile(project_state="simmering")]

    candidates, _report = match_project_papers(
        projects, [paper_profile()], include_states=("simmering",)
    )

    assert len(candidates) == 1
    assert candidates[0]["project_id"] == "cptu_bayesian_classification"


def test_match_project_papers_limits_top_n_per_project():
    papers = [
        paper_profile(
            citekey=f"cptu{i}",
            title=f"CPTu soil classification {i}",
            paper_hash=f"sha256:p{i}",
            metadata_snapshot_path=f"papers/cptu{i}/metadata_snapshot.json",
        )
        for i in range(25)
    ]

    candidates, _report = match_project_papers([project_profile()], papers, top_n=20)

    assert len(candidates) == 20
    assert [candidate["rank"] for candidate in candidates] == list(range(1, 21))


def test_match_project_papers_filters_papers_by_zotero_stage():
    papers = [
        paper_profile(),
        paper_profile(
            citekey="todig2026",
            title="Bayesian CPTu formulation for deep analysis",
            collections=[".ToDig", "CPTu"],
            paper_hash="sha256:todig",
            metadata_snapshot_path="papers/todig2026/metadata_snapshot.json",
        ),
    ]

    candidates, _report = match_project_papers(
        [project_profile()],
        papers,
        paper_stages=(".ToDig",),
    )

    assert [candidate["citekey"] for candidate in candidates] == ["todig2026"]


def test_match_project_papers_limits_max_candidates_total_globally():
    projects = [
        project_profile(project_id="project_a", content_hash="sha256:project-a"),
        project_profile(
            project_id="project_b",
            title="CPTu Bayesian Soil Classification Extension",
            source_path="Efforts/On/CPTu Bayesian Soil Classification Extension.md",
            content_hash="sha256:project-b",
        ),
    ]
    papers = [
        paper_profile(),
        paper_profile(
            citekey="weak2024",
            title="Bayesian model comparison",
            abstract="Priors and posterior checks.",
            paper_hash="sha256:weak",
            metadata_snapshot_path="papers/weak2024/metadata_snapshot.json",
        ),
    ]

    uncapped, _report = match_project_papers(
        projects, papers, now="2026-05-12T12:00:00"
    )
    capped, _report = match_project_papers(
        projects,
        papers,
        now="2026-05-12T12:00:00",
        max_candidates_total=2,
    )

    assert len(uncapped) == 4
    assert len(capped) == 2
    expected = sorted(
        uncapped,
        key=lambda candidate: (
            -float(candidate["candidate_score"]),
            str(candidate["project_id"]),
            str(candidate["citekey"]),
        ),
    )[:2]
    assert capped == expected


def test_match_project_papers_skips_unchanged_pairs_when_registry_is_available(
    tmp_path: Path,
):
    db_path = tmp_path / "registry.sqlite"
    conn = initialize_registry(db_path)
    project = project_profile()
    unchanged = paper_profile()
    changed = paper_profile(
        citekey="changed2025",
        title="Bayesian CPTu soil classification update",
        paper_hash="sha256:changed",
        metadata_snapshot_path="papers/changed2025/metadata_snapshot.json",
    )
    upsert_projects(conn, [project])
    upsert_papers(conn, [unchanged, changed])
    record_pair_hash(
        conn,
        project_id=project["project_id"],
        citekey=unchanged["citekey"],
        project_hash=project["content_hash"],
        paper_hash=unchanged["paper_hash"],
        prompt_hash="sha256:lexical_v1",
    )

    candidates, report = match_project_papers(
        [project], [unchanged, changed], registry_db=db_path
    )

    assert [candidate["citekey"] for candidate in candidates] == ["changed2025"]
    assert report.skipped_pairs == 1
    assert report.warnings == [
        "skipped unchanged pair: cptu_bayesian_classification -> robertson1990soilclassification"
    ]


def test_write_candidates_jsonl_is_atomic_when_candidate_is_invalid(tmp_path: Path):
    output = tmp_path / "data" / "candidates.jsonl"
    output.parent.mkdir(parents=True)
    output.write_text("previous\n", encoding="utf-8")
    invalid = {
        "project_id": "project",
        "citekey": "paper",
        "candidate_score": 2,
        "rank": 1,
        "evidence": ["bad score"],
        "method": "lexical_v1",
        "created_at": "2026-05-12T12:00:00",
    }

    try:
        write_candidates_jsonl(output, [invalid])
    except Exception as exc:
        assert "project_paper_match.schema.json validation failed" in str(exc)
    else:
        raise AssertionError("invalid candidate should fail")

    assert output.read_text(encoding="utf-8") == "previous\n"


def test_cli_match_writes_candidates_with_defaults(tmp_path: Path, capsys):
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "candidates.jsonl"
    write_jsonl(projects, [project_profile()])
    write_jsonl(papers, [paper_profile()])

    exit_code = cli_main(
        [
            "match",
            "--projects",
            str(projects),
            "--papers",
            str(papers),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert "candidates=1" in capsys.readouterr().out
    rows = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["project_id"] == "cptu_bayesian_classification"
    assert rows[0]["citekey"] == "robertson1990soilclassification"


def test_cli_match_applies_stage_and_global_filters(tmp_path: Path, capsys):
    projects = tmp_path / "data" / "projects.jsonl"
    papers = tmp_path / "data" / "papers.jsonl"
    output = tmp_path / "data" / "candidates.jsonl"
    write_jsonl(
        projects,
        [
            project_profile(project_id="project_a", content_hash="sha256:project-a"),
            project_profile(
                project_id="project_b",
                title="CPTu Bayesian Soil Classification Extension",
                source_path="Efforts/On/CPTu Bayesian Soil Classification Extension.md",
                content_hash="sha256:project-b",
            ),
        ],
    )
    write_jsonl(
        papers,
        [
            paper_profile(),
            paper_profile(
                citekey="todig2026",
                title="Bayesian CPTu formulation for deep analysis",
                collections=[".ToDig", "CPTu"],
                paper_hash="sha256:todig",
                metadata_snapshot_path="papers/todig2026/metadata_snapshot.json",
            ),
        ],
    )

    exit_code = cli_main(
        [
            "match",
            "--projects",
            str(projects),
            "--papers",
            str(papers),
            "--output",
            str(output),
            "--paper-stages",
            ".ToDig",
            "--max-candidates-total",
            "1",
        ]
    )

    assert exit_code == 0
    assert "candidates=1" in capsys.readouterr().out
    rows = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["citekey"] == "todig2026"


def test_cli_match_reports_missing_inputs_without_traceback_or_partial_output(
    tmp_path: Path, capsys
):
    output = tmp_path / "data" / "candidates.jsonl"

    exit_code = cli_main(
        [
            "match",
            "--projects",
            str(tmp_path / "missing-projects.jsonl"),
            "--papers",
            str(tmp_path / "missing-papers.jsonl"),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "match error:" in captured.err
    assert "uv run paper-pipeline scan-obsidian" in captured.err
    assert "uv run paper-pipeline scan-zotero" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_cli_match_reports_invalid_input_without_partial_output(tmp_path: Path, capsys):
    projects = tmp_path / "projects.jsonl"
    papers = tmp_path / "papers.jsonl"
    output = tmp_path / "candidates.jsonl"
    projects.write_text(
        json.dumps(project_profile(project_id="bad id")) + "\n", encoding="utf-8"
    )
    papers.write_text(json.dumps(paper_profile()) + "\n", encoding="utf-8")

    exit_code = cli_main(
        [
            "match",
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
    assert "project_profile.schema.json validation failed" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()
