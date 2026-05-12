import json
from pathlib import Path

from paper_pipeline.schema_validation import validate_instance
from paper_pipeline.zotero_adapter import ZoteroItem
from paper_pipeline.zotero_inventory import (
    export_paper_inventory,
    load_fixture_items,
    main,
    paper_profile_from_item,
)


def test_paper_profile_from_zotero_item_is_neutral_and_schema_valid():
    item = ZoteroItem(
        key="Z1",
        citekey="smith2025",
        title="Bayesian CPT classification",
        abstract="Soil uncertainty and CPT interpretation.",
        collections=["Books", ".ToLook"],
        tags=["cpt", "cpt", "@look"],
        publication_year=2025,
        pdf_paths=["/tmp/paper.pdf"],
        doi="10.1000/example",
        authors=["A Smith", "B Costa"],
    )

    profile = paper_profile_from_item(item)

    assert profile == {
        "citekey": "smith2025",
        "zotero_key": "Z1",
        "title": "Bayesian CPT classification",
        "year": 2025,
        "authors": ["A Smith", "B Costa"],
        "abstract": "Soil uncertainty and CPT interpretation.",
        "collections": ["Books", ".ToLook"],
        "tags": ["cpt", "@look"],
        "doi": "10.1000/example",
        "has_pdf": True,
        "pdf_paths": ["/tmp/paper.pdf"],
        "paper_hash": profile["paper_hash"],
        "metadata_snapshot_path": "papers/smith2025/metadata_snapshot.json",
    }
    assert profile["paper_hash"].startswith("sha256:")
    validate_instance(profile, "paper_profile.schema.json")


def test_export_paper_inventory_writes_jsonl_and_preserves_snapshot_fields(tmp_path: Path):
    existing_snapshot = tmp_path / "papers" / "smith2025" / "metadata_snapshot.json"
    existing_snapshot.parent.mkdir(parents=True)
    existing_snapshot.write_text(
        json.dumps(
            {
                "citekey": "smith2025",
                "manual_review_note": "keep this local annotation",
                "title": "Old title",
            }
        ),
        encoding="utf-8",
    )
    items = [
        ZoteroItem(
            key="Z2",
            citekey="brown2024",
            title="Offshore foundations review",
            collections=["Books"],
            tags=["review"],
            publication_year=2024,
        ),
        ZoteroItem(
            key="Z1",
            citekey="smith2025",
            title="Bayesian CPT classification",
            abstract="Soil uncertainty",
            collections=[".ToLook"],
            tags=["cpt"],
            publication_year=2025,
        ),
    ]

    output = export_paper_inventory(
        items,
        output_path=tmp_path / "data" / "papers.jsonl",
        papers_root=tmp_path / "papers",
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["citekey"] for row in rows] == ["brown2024", "smith2025"]
    assert rows[0]["collections"] == ["Books"]
    assert rows[0]["metadata_snapshot_path"] == "papers/brown2024/metadata_snapshot.json"
    for row in rows:
        validate_instance(row, "paper_profile.schema.json")

    merged = json.loads(existing_snapshot.read_text(encoding="utf-8"))
    assert merged["title"] == "Bayesian CPT classification"
    assert merged["manual_review_note"] == "keep this local annotation"
    assert merged["metadata_snapshot_path"] == "papers/smith2025/metadata_snapshot.json"


def test_load_fixture_items_reads_export_without_credentials_or_secret_leakage(tmp_path: Path):
    fixture = tmp_path / "zotero_fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "api_key": "SHOULD_NOT_APPEAR",
                "user_id": "123456",
                "items": [
                    {
                        "key": "Z1",
                        "citekey": "fixture2026",
                        "title": "Fixture paper",
                        "abstract": "metadata only",
                        "collections": [".ToLook"],
                        "tags": ["soil"],
                        "publication_year": 2026,
                        "pdf_paths": [],
                        "doi": "10.1000/fixture",
                        "authors": ["Fixture Author"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    items = load_fixture_items(fixture)
    output = export_paper_inventory(items, output_path=tmp_path / "data" / "papers.jsonl", papers_root=tmp_path / "papers")

    text = output.read_text(encoding="utf-8")
    assert "SHOULD_NOT_APPEAR" not in text
    assert "123456" not in text
    assert json.loads(text)["citekey"] == "fixture2026"


def test_zotero_inventory_module_main_supports_offline_fixture(tmp_path: Path, capsys):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "key": "Z1",
                    "citekey": "fixture2026",
                    "title": "Fixture paper",
                    "collections": ["Library"],
                    "tags": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "data" / "papers.jsonl"

    exit_code = main(["--offline-fixture", str(fixture), "--output", str(output), "--papers-root", str(tmp_path / "papers")])

    assert exit_code == 0
    assert "papers=1" in capsys.readouterr().out
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["citekey"] == "fixture2026"
    assert (tmp_path / "papers" / "fixture2026" / "metadata_snapshot.json").exists()


def test_zotero_inventory_module_main_reports_missing_offline_fixture_without_traceback(tmp_path: Path, capsys):
    output = tmp_path / "data" / "papers.jsonl"

    exit_code = main(
        [
            "--offline-fixture",
            "path/to/zotero_fixture.json",
            "--output",
            str(output),
            "--papers-root",
            str(tmp_path / "papers"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "offline fixture not found" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_zotero_inventory_module_main_reports_invalid_json_fixture_without_traceback(tmp_path: Path, capsys):
    fixture = tmp_path / "broken.json"
    fixture.write_text("{not json", encoding="utf-8")
    output = tmp_path / "data" / "papers.jsonl"

    exit_code = main(["--offline-fixture", str(fixture), "--output", str(output), "--papers-root", str(tmp_path / "papers")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "offline fixture is not valid JSON" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_zotero_inventory_module_main_reports_invalid_item_without_partial_artifacts(tmp_path: Path, capsys):
    fixture = tmp_path / "invalid_item.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "key": "",
                    "citekey": "",
                    "title": "Cannot build a valid PaperProfile without any stable key",
                    "collections": ["Library"],
                    "tags": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "data" / "papers.jsonl"

    exit_code = main(["--offline-fixture", str(fixture), "--output", str(output), "--papers-root", str(tmp_path / "papers")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "paper_profile.schema.json validation failed" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()
    assert not (tmp_path / "papers").exists()
