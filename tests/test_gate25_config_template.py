from pathlib import Path

from paper_pipeline.config import load_config


def test_runtime_config_template_is_loadable():
    path = Path("x/LLM/pipeline_config.example.yaml")
    cfg = load_config(path, vault_root=".")
    assert cfg.lmstudio.analysis_model
    assert cfg.paths.vault_root.name == "ChrisVault4.0"
    assert cfg.paths.inbox_dir == cfg.paths.vault_root / "+"
    assert cfg.paths.papers_root == cfg.paths.vault_root / "x" / "LLM" / "papers"
