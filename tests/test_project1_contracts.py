import copy
import json
from pathlib import Path

import pytest
import yaml

from paper_pipeline.contracts import ValidationError
from paper_pipeline.project_paper_classification import append_validated_classification, parse_llm_classification
from paper_pipeline.schema_validation import load_schema, validate_json_file, validate_instance


FIXTURE_ROOT = Path("tests/fixtures/contracts")


@pytest.mark.parametrize(
    ("fixture_name", "schema_name"),
    [
        ("project_profile.valid.json", "project_profile.schema.json"),
        ("paper_profile.valid.json", "paper_profile.schema.json"),
        ("project_paper_match.valid.json", "project_paper_match.schema.json"),
        ("llm_classification.valid.json", "llm_classification.schema.json"),
    ],
)
def test_contract_fixtures_validate_against_schemas(fixture_name, schema_name):
    validate_json_file(FIXTURE_ROOT / fixture_name, schema_name)


def test_project_profile_rejects_archived_state():
    project = _fixture("project_profile.valid.json")
    project["project_state"] = "archived"
    with pytest.raises(ValidationError, match="project_profile.schema.json validation failed"):
        validate_instance(project, "project_profile.schema.json")


def test_llm_classification_rejects_invalid_utility_class():
    raw = _fixture("llm_classification.valid.json")
    raw["utility_class"] = "interesting"
    with pytest.raises(ValidationError, match="llm_classification.schema.json validation failed"):
        validate_instance(raw, "llm_classification.schema.json")


def test_llm_classification_rejects_invalid_action():
    raw = _fixture("llm_classification.valid.json")
    raw["recommended_action"] = "apply_zotero_tag"
    with pytest.raises(ValidationError, match="llm_classification.schema.json validation failed"):
        validate_instance(raw, "llm_classification.schema.json")


def test_llm_classification_rejects_invalid_input_layer():
    raw = _fixture("llm_classification.valid.json")
    raw["input_layer"] = "raw_pdf"
    with pytest.raises(ValidationError, match="llm_classification.schema.json validation failed"):
        validate_instance(raw, "llm_classification.schema.json")


def test_llm_classification_requires_explicit_pdf_fallback_authorization():
    raw = _fixture("llm_classification.valid.json")
    raw["input_layer"] = "pdf_fallback"
    with pytest.raises(ValidationError, match="pdf_fallback_authorized"):
        validate_instance(raw, "llm_classification.schema.json")
    raw["pdf_fallback_authorized"] = True
    validate_instance(raw, "llm_classification.schema.json")


def test_parse_llm_classification_requires_single_json_object_without_prose():
    valid = json.dumps(_fixture("llm_classification.valid.json"))
    assert parse_llm_classification(valid).utility_class == "essential"
    with pytest.raises(ValidationError, match="without prose"):
        parse_llm_classification("Here is JSON:\n" + valid)
    with pytest.raises(ValidationError, match="exactly one JSON object"):
        parse_llm_classification(valid + valid)


def test_invalid_llm_classification_is_not_persisted(tmp_path):
    output = tmp_path / "data" / "classifications.jsonl"
    valid = _fixture("llm_classification.valid.json")
    invalid = copy.deepcopy(valid)
    invalid["confidence"] = "certain"
    with pytest.raises(ValidationError):
        append_validated_classification(json.dumps(invalid), output)
    assert not output.exists()

    classification = append_validated_classification(json.dumps(valid), output)
    assert classification.citekey == "robertson1990soilclassification"
    assert output.read_text(encoding="utf-8").count("\n") == 1


def test_utility_taxonomy_matches_llm_classification_schema_enums():
    taxonomy = yaml.safe_load(Path("configs/utility_taxonomy.yaml").read_text(encoding="utf-8"))
    schema = load_schema("llm_classification.schema.json")
    assert taxonomy["utility_classes"] == schema["properties"]["utility_class"]["enum"]
    assert taxonomy["actions"] == schema["properties"]["recommended_action"]["enum"]
    assert taxonomy["confidence_levels"] == schema["properties"]["confidence"]["enum"]
    assert taxonomy["input_layers"] == schema["properties"]["input_layer"]["enum"]


def test_zotero_tag_config_preserves_stage_contract():
    config = yaml.safe_load(Path("configs/zotero_tags.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["tolook"]["collection"] == ".ToLook"
    assert config["stages"]["torevise"]["collection"] == ".To Revise"
    assert config["stages"]["todig"]["collection"] == ".ToDig"
    assert config["stages"]["expendable"]["collection"] == "Expendable"
    assert config["stages"]["expendable"]["stage_tag"] == "!discarded"


def _fixture(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
