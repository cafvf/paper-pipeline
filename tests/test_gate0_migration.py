from pathlib import Path
import pytest


@pytest.mark.integration
def test_standalone_repository_layout_exists():
    root = Path(".")
    assert (root / "paper_pipeline").is_dir()
    assert (root / "tests").is_dir()
    assert (root / "tools").is_dir()
    assert (root / "config.example.yaml").is_file()


@pytest.mark.integration
def test_old_vault_embedded_layout_is_gone():
    root = Path(".")
    assert not (root / "x" / "LLM").exists()
    assert not (root / "local_paper_pipeline_runtime").exists()
    assert not Path("+/outputs").exists()
    assert not list(Path("+").glob("Nightly Zotero Review*.md"))
