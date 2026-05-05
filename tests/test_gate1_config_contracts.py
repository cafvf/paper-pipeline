from pathlib import Path

import pytest

from paper_pipeline.config import default_config, load_config
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
    cfg = load_config(cfg_path, vault_root=".")
    assert cfg.lmstudio.analysis_model == "qwen-test"
    assert cfg.operational_collections.todig == [".ToDig"]


def test_contract_enums_and_stage_mapping():
    assert DecisionState("approved") == DecisionState.APPROVED
    assert stage_from_collection_action(CollectionAction.MOVE_TO_REVISE) == Stage.TO_REVISE
    assert stage_from_collection_action(CollectionAction.NO_COLLECTION_CHANGE) is None


def test_normalize_citekey_rejects_empty():
    assert normalize_citekey(" yao:Test 2025 ") == "yaoTest2025"
    with pytest.raises(ValidationError):
        normalize_citekey("!!!")
