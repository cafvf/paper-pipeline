from pathlib import Path

import pytest

from paper_pipeline.config import ConfigError, default_config, load_config
from paper_pipeline.contracts import CollectionAction, DecisionState, Stage, ValidationError, normalize_citekey, stage_from_collection_action


def test_default_config_resolves_vault_paths():
    cfg = default_config(".")
    assert cfg.paths.vault_root == Path(".").resolve()
    assert cfg.paths.llm_root == Path(".").resolve()
    assert cfg.paths.papers_root == Path("papers").resolve()
    assert cfg.lmstudio.embedding_model == ""
    assert cfg.operational_collections.tolook == [".ToLook"]


def test_load_config_from_json(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"lmstudio": {"analysis_model": "qwen-test"}, "operational_collections": {"todig": [".ToDig"]}}')
    vault = tmp_path / "vault"
    cfg = load_config(
        cfg_path,
        env={
            "VAULT_ROOT": str(vault),
            "OBSIDIAN_HUMAN_REVIEW_INBOX_DIR": "Inbox/Human Review",
        },
    )
    assert cfg.lmstudio.analysis_model == "qwen-test"
    assert cfg.operational_collections.todig == [".ToDig"]
    assert cfg.paths.vault_root == vault.resolve()
    assert cfg.paths.inbox_dir == (vault / "Inbox/Human Review").resolve()


def test_load_config_auto_loads_dotenv_from_working_directory(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}")
    vault = tmp_path / "vault"
    (tmp_path / ".env").write_text(
        f"VAULT_ROOT={vault}\nOBSIDIAN_HUMAN_REVIEW_INBOX_DIR='Inbox/Human Review'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VAULT_ROOT", raising=False)
    monkeypatch.delenv("OBSIDIAN_HUMAN_REVIEW_INBOX_DIR", raising=False)

    cfg = load_config(cfg_path)

    assert cfg.paths.vault_root == vault.resolve()
    assert cfg.paths.inbox_dir == (vault / "Inbox/Human Review").resolve()


def test_real_environment_overrides_dotenv(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}")
    dotenv_vault = tmp_path / "dotenv-vault"
    env_vault = tmp_path / "env-vault"
    (tmp_path / ".env").write_text(f"VAULT_ROOT={dotenv_vault}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VAULT_ROOT", str(env_vault))

    cfg = load_config(cfg_path)

    assert cfg.paths.vault_root == env_vault.resolve()


def test_load_config_rejects_relative_vault_root(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}")
    with pytest.raises(ConfigError, match="VAULT_ROOT must be an absolute path"):
        load_config(cfg_path, env={"VAULT_ROOT": "relative/vault"})


def test_load_config_requires_vault_root_when_no_legacy_override_is_provided(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}")
    with pytest.raises(ConfigError, match="VAULT_ROOT is required"):
        load_config(cfg_path, env={})


def test_load_config_accepts_absolute_obsidian_inbox(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}")
    vault = tmp_path / "vault"
    inbox = tmp_path / "obsidian-inbox"
    cfg = load_config(
        cfg_path,
        env={
            "VAULT_ROOT": str(vault),
            "OBSIDIAN_HUMAN_REVIEW_INBOX_DIR": str(inbox),
        },
    )
    assert cfg.paths.inbox_dir == inbox.resolve()


@pytest.mark.parametrize(
    "content, message",
    [
        ('{"vault_root": "/tmp/vault"}', "vault_root belongs in VAULT_ROOT"),
        ('{"PAPERS_DIR": "papers"}', "PAPERS_DIR"),
        ('{"paths": {"inbox_dir": "+"}}', "paths.inbox_dir"),
        ('{"paths": {"templates_dir": "templates"}}', "paths.templates_dir"),
    ],
)
def test_load_config_rejects_legacy_obsidian_yaml_fields(tmp_path, content, message):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(content)
    with pytest.raises(ConfigError, match=message):
        load_config(cfg_path, env={"VAULT_ROOT": str(tmp_path / "vault")})


def test_contract_enums_and_stage_mapping():
    assert DecisionState("approved") == DecisionState.APPROVED
    assert stage_from_collection_action(CollectionAction.MOVE_TO_REVISE) == Stage.TO_REVISE
    assert stage_from_collection_action(CollectionAction.NO_COLLECTION_CHANGE) is None


def test_normalize_citekey_rejects_empty():
    assert normalize_citekey(" yao:Test 2025 ") == "yaoTest2025"
    with pytest.raises(ValidationError):
        normalize_citekey("!!!")
