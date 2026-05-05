from pathlib import Path
import pytest

from paper_pipeline.config import load_config


@pytest.mark.integration
def test_runtime_config_template_is_loadable():
    path = Path("config.example.yaml")
    cfg = load_config(path, vault_root=".")
    assert cfg.lmstudio.analysis_model
    # Do not assert a specific vault name; ensure a vault_root is present
    assert cfg.paths.vault_root.name
    assert cfg.paths.inbox_dir == cfg.paths.vault_root / "+"
    assert cfg.paths.llm_root == Path(".").resolve()
    assert cfg.paths.papers_root == Path("papers").resolve()
