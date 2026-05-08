from pathlib import Path
import pytest
import yaml

from paper_pipeline.config import load_config


@pytest.mark.integration
def test_runtime_config_template_is_loadable(tmp_path):
    path = Path("config.example.yaml")
    vault = tmp_path / "vault"
    cfg = load_config(
        path,
        env={
            "VAULT_ROOT": str(vault),
            "OBSIDIAN_HUMAN_REVIEW_INBOX_DIR": "Inbox/Human Review",
        },
    )
    assert cfg.lmstudio.analysis_model
    assert cfg.paths.vault_root == vault.resolve()
    assert cfg.paths.inbox_dir == (vault / "Inbox/Human Review").resolve()
    assert cfg.paths.llm_root == Path(".").resolve()
    assert cfg.paths.papers_root == Path("papers").resolve()


def test_runtime_config_template_does_not_contain_obsidian_paths():
    raw = yaml.safe_load(Path("config.example.yaml").read_text(encoding="utf-8"))
    assert "vault_root" not in raw
    assert "PAPERS_DIR" not in raw
    paths = raw["paths"]
    assert "inbox_dir" not in paths
    assert "templates_dir" not in paths


def test_env_example_contains_only_placeholders_and_expected_keys():
    raw = Path(".env.example").read_text(encoding="utf-8").splitlines()
    mapping = dict(line.split("=", 1) for line in raw if line and not line.startswith("#"))
    assert set(mapping) == {
        "VAULT_ROOT",
        "OBSIDIAN_HUMAN_REVIEW_INBOX_DIR",
        "ZOTERO_API_KEY",
        "ZOTERO_USER_ID",
        "LMSTUDIO_URL",
        "LMSTUDIO_KEY",
    }
    assert mapping["VAULT_ROOT"] == "<ABSOLUTE_VAULT_ROOT_PATH>"
    assert mapping["OBSIDIAN_HUMAN_REVIEW_INBOX_DIR"] == "<OBSIDIAN_HUMAN_REVIEW_INBOX_DIR>"
    assert mapping["ZOTERO_API_KEY"] == ""
    assert mapping["ZOTERO_USER_ID"] == ""
    assert mapping["LMSTUDIO_KEY"] == ""
