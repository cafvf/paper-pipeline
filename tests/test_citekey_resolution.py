from pathlib import Path

from paper_pipeline.citekey_resolver import resolve_citekey_from_vault


def test_resolve_citekey_from_vault_by_doi(tmp_path: Path):
    note = tmp_path / "Atlas" / "Literature" / "Zotero" / "smithKey.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        '---\ncitekey: "smithUsefulPaper2025"\ndoi: "10.1000/example"\ntitle: "Useful Paper"\n---\n',
        encoding="utf-8",
    )
    assert resolve_citekey_from_vault(tmp_path, doi="10.1000/example", title="Other") == "smithUsefulPaper2025"


def test_resolve_citekey_from_vault_by_title_when_doi_absent(tmp_path: Path):
    note = tmp_path / "Atlas" / "Literature" / "Zotero" / "zhao.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        '---\ncitekey: "zhaoProbabilisticCharacterization3D2026"\ntitle: "Probabilistic characterization of 3D geotechnical variability"\n---\n',
        encoding="utf-8",
    )
    assert (
        resolve_citekey_from_vault(tmp_path, doi="", title="Probabilistic characterization of 3D geotechnical variability")
        == "zhaoProbabilisticCharacterization3D2026"
    )
