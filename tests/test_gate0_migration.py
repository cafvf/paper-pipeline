from pathlib import Path


def test_legacy_layout_exists():
    root = Path("x/LLM")
    assert (root / "legacy" / "local_paper_pipeline_runtime").is_dir()
    assert (root / "legacy" / "tests").is_dir()
    assert (root / "legacy" / "__lmstudio_pipeline_artifacts").is_dir()
    assert (root / "legacy" / "root_docs").is_dir()


def test_v2_roots_exist_and_old_plus_outputs_are_gone():
    root = Path("x/LLM")
    assert (root / "paper_pipeline").is_dir()
    assert (root / "papers").is_dir()
    assert (root / "index").is_dir()
    assert not (root / "local_paper_pipeline_runtime").exists()
    assert not Path("+/outputs").exists()
    assert not list(Path("+").glob("Nightly Zotero Review*.md"))
