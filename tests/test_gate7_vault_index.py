from pathlib import Path

from paper_pipeline.vault_index import build_lexical_index, search_lexical, write_index


def write_note(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_index_includes_expected_efforts_and_atlas_but_not_plus_or_terminated(tmp_path):
    write_note(tmp_path / "Efforts" / "On" / "A.md", "---\ntags: [focus]\naliases: []\n---\n# CPT Work\nBayesian CPT")
    write_note(tmp_path / "Efforts" / "Terminated" / "Old.md", "# Old")
    write_note(tmp_path / "Atlas" / "Concepts" / "Bayes.md", "---\ntags: [atlas/concept]\naliases: [Bayesian]\n---\n# Bayesian Inference")
    write_note(tmp_path / "Atlas" / "People" / "P.md", "# Person")
    write_note(tmp_path / "+" / "Inbox.md", "# Inbox")
    index = build_lexical_index(tmp_path)
    paths = {note["path"] for note in index["notes"]}
    assert "Efforts/On/A.md" in paths
    assert "Atlas/Concepts/Bayes.md" in paths
    assert "Efforts/Terminated/Old.md" not in paths
    assert "+/Inbox.md" not in paths
    assert "Atlas/People/P.md" not in paths


def test_search_lexical_uses_indexed_content(tmp_path):
    write_note(tmp_path / "Efforts" / "On" / "A.md", "# CPT Work\nBayesian CPT")
    index = build_lexical_index(tmp_path)
    results = search_lexical(index, "bayesian cpt")
    assert results[0]["path"] == "Efforts/On/A.md"


def test_write_index_persists_json(tmp_path):
    path = write_index(tmp_path / "index", {"notes": []})
    assert path.exists()
    assert path.name == "lexical_index.json"
