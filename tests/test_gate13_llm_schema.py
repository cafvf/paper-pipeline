import json

import pytest

from paper_pipeline.contracts import Stage, ValidationError
from paper_pipeline.llm_schema import parse_llm_assessment, render_schema_for_stage

LOOK_CRITERIA = [
    "direct_relevance",
    "comparable_methodology",
    "recent_or_seminal",
    "author_credibility",
    "explorable_gap",
    "citation_sentence_ready",
]
ORIGINAL_DIG_CRITERIA = [
    "new_method_for_toolkit",
    "reproducible_equations_and_parameters",
    "validated_results",
    "domain_applicability",
    "paper_section_value",
]


RICH_KNOWLEDGE = {
    "type": "concept",
    "target": "Atlas/Concepts/CPT.md",
    "knowledge_claim": "CPT interpretation can be connected to active learning Kriging when cone resistance is treated as a sparse geotechnical signal for uncertainty reduction.",
    "article_use": "The paper uses CPT as the motivating geotechnical signal and relates it to surrogate-assisted reliability assessment.",
    "evidence": ["Abstract links CPT data to active learning Kriging for geotechnical reliability."],
    "applicability": "Use this as a bridge between CPT interpretation notes and surrogate reliability workflows in Atlas.",
    "limitations": "The packet does not prove direct field validation for every CPT setting.",
    "integration_notes": "Link with CPT, active learning Kriging and reliability analysis MOCs.",
    "review_tasks": ["Check whether existing CPT notes already cover this bridge."],
    "justification": "The paper uses CPT as the motivating geotechnical signal.",
}


def payload(
    *,
    stage: Stage = Stage.TO_LOOK,
    recommended_collection: Stage = Stage.TO_REVISE,
    recommendation_action: str = "move_to_revise",
    gate_result: str = "pass",
    criteria_ids: list[str] | None = None,
    statuses: list[str] | None = None,
    recommended_tags_add: list[str] | None = None,
    recommended_subject_tags: list[str] | None = None,
    knowledge_suggestions: list[dict] | None = None,
    metrics: dict | None = None,
    summary: str = "useful",
    evidence: list | None = None,
) -> str:
    criteria_ids = criteria_ids or (LOOK_CRITERIA if stage == Stage.TO_LOOK else ORIGINAL_DIG_CRITERIA)
    statuses = statuses or (["yes", "yes", "yes", "no", "no", "no"] if stage == Stage.TO_LOOK else ["yes"] * 5)
    criteria = [
        {
            "criterion_id": criterion_id,
            "criterion": criterion_id.replace("_", " "),
            "status": status,
            "evidence": "abstract",
            "rationale": "fits",
        }
        for criterion_id, status in zip(criteria_ids, statuses, strict=True)
    ]
    weighted = sum({"yes": 1.0, "partial": 0.5, "no": 0.0, "unknown": 0.0}[status] for status in statuses)
    raw = {
        "citekey": "a",
        "stage": stage.value,
        "article_type": "original",
        "review_type": "none",
        "article_type_confidence": 0.9,
        "gate_result": gate_result,
        "recommendation_action": recommendation_action,
        "recommended_collection": recommended_collection.value,
        "recommendation_rationale": "Gate decision follows the protocol.",
        "confidence": 0.75,
        "summary": summary,
        "evidence": evidence if evidence is not None else ["abstract"],
        "recommended_tags_add": recommended_tags_add if recommended_tags_add is not None else ["@review"],
        "recommended_subject_tags": recommended_subject_tags if recommended_subject_tags is not None else [],
        "knowledge_suggestions": knowledge_suggestions if knowledge_suggestions is not None else [],
        "protocol_criteria": criteria,
        "metrics": metrics
        if metrics is not None
        else {
            "criteria_met": statuses.count("yes"),
            "criteria_total": len(statuses),
            "criteria_score": weighted / len(statuses),
            "evidence_coverage": 0.5,
            "decision_readiness": "medium",
        },
    }
    return json.dumps(raw, ensure_ascii=False)


def test_parse_llm_assessment_requires_json_and_required_fields():
    assessment = parse_llm_assessment(payload())
    assert assessment.citekey == "a"
    assert assessment.recommended_collection == Stage.TO_REVISE
    assert assessment.recommendation_action == "move_to_revise"
    assert assessment.metrics["decision_readiness"] == "medium"


def test_parse_llm_assessment_extracts_single_prose_wrapped_json_object():
    assessment = parse_llm_assessment("Here is the JSON:\n```json\n" + payload() + "\n```")
    assert assessment.citekey == "a"


def test_parse_llm_assessment_rejects_ambiguous_multiple_json_objects():
    with pytest.raises(ValidationError):
        parse_llm_assessment(payload() + '{"citekey":"b"}')


def test_render_schema_includes_stage_specific_sections_and_decision_fields():
    schema = render_schema_for_stage(Stage.TO_DIG)
    assert "figures_to_register" in schema["properties"]
    assert "method_formulation" in schema["properties"]["section_findings"]["properties"]
    assert "recommendation_action" in schema["required"]
    assert "gate_result" in schema["required"]
    assert "recommendation_rationale" in schema["required"]


def test_schema_limits_recommended_tags_to_protocol_tags():
    schema = render_schema_for_stage(Stage.TO_LOOK)
    assert "recommended_subject_tags" in schema["required"]
    assert "enum" in schema["properties"]["recommended_subject_tags"]["items"]
    assert "maxItems" not in schema["properties"]["knowledge_suggestions"]
    assert "items" in schema["properties"]["knowledge_suggestions"]
    assert "section_findings" not in schema["properties"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["recommended_tags_add"]["items"]["enum"]) == {
        "@look",
        "@review",
        "@dig",
        "@looked_by_llm",
        "@reviewed_by_llm",
        "@dug_by_llm",
        "!discarded",
    }
    with pytest.raises(ValidationError):
        parse_llm_assessment(payload(recommended_tags_add=["soil"]))


def test_subject_tags_are_allowed_for_all_stages_but_must_be_protocol_tags():
    assessment = parse_llm_assessment(
        payload(
            stage=Stage.TO_DIG,
            recommended_collection=Stage.TO_DIG,
            recommendation_action="move_to_dig",
            recommended_tags_add=["@dig"],
            recommended_subject_tags=["#soil-classification", "#CPT-classification", "%machine-learning", "$methods-cite"],
        )
    )
    assert assessment.recommended_subject_tags == [
        "#soil-classification",
        "#CPT-classification",
        "%machine-learning",
        "$methods-cite",
    ]
    look = parse_llm_assessment(payload(recommended_subject_tags=["#soil-classification"]))
    assert look.recommended_subject_tags == ["#soil-classification"]
    with pytest.raises(ValidationError):
        parse_llm_assessment(
            payload(
                stage=Stage.TO_DIG,
                recommended_collection=Stage.TO_DIG,
                recommendation_action="move_to_dig",
                recommended_tags_add=["@dig"],
                recommended_subject_tags=["#free-topic"],
            )
        )


def test_parse_llm_assessment_deduplicates_subject_tags_before_validation():
    assessment = parse_llm_assessment(
        payload(
            stage=Stage.TO_REVISE,
            recommended_collection=Stage.TO_DIG,
            recommendation_action="move_to_dig",
            recommended_tags_add=["@dig"],
            recommended_subject_tags=["#CPT-classification", "#CPT-classification"],
        )
    )
    assert assessment.recommended_subject_tags == ["#CPT-classification"]


def test_parse_llm_assessment_normalizes_metric_percent_like_values():
    assessment = parse_llm_assessment(
        payload(
            stage=Stage.TO_DIG,
            recommended_collection=Stage.TO_DIG,
            recommendation_action="move_to_dig",
            recommended_tags_add=["@dig"],
            recommended_subject_tags=["#CPT-classification"],
            metrics={
                "criteria_met": 5,
                "criteria_total": 5,
                "criteria_score": 10,
                "evidence_coverage": 85,
                "decision_readiness": "medium",
            },
        )
    )
    assert assessment.metrics["criteria_score"] == 1
    assert assessment.metrics["evidence_coverage"] == 0.85


def test_parse_llm_assessment_deduplicates_recommended_tags_before_validation():
    assessment = parse_llm_assessment(payload(recommended_tags_add=["@review", "@review"]))
    assert assessment.recommended_tags_add == ["@review"]


def test_parse_llm_assessment_rejects_duplicate_or_missing_protocol_criteria():
    with pytest.raises(ValidationError, match="ToLook requires To Review criteria"):
        parse_llm_assessment(
            payload(
                statuses=["yes", "yes"],
                criteria_ids=["direct_relevance", "direct_relevance"],
                metrics={
                    "criteria_met": 1,
                    "criteria_total": 1,
                    "criteria_score": 1,
                    "evidence_coverage": 0.5,
                    "decision_readiness": "medium",
                },
            )
        )


def test_schema_forbids_knowledge_suggestions_in_tolook():
    with pytest.raises(ValidationError):
        parse_llm_assessment(payload(knowledge_suggestions=[RICH_KNOWLEDGE]))


def test_schema_requires_structured_knowledge_suggestions_for_revise_and_dig():
    assessment = parse_llm_assessment(
        payload(
            stage=Stage.TO_REVISE,
            recommended_collection=Stage.TO_REVISE,
            recommendation_action="keep_in_revise",
            gate_result="hold",
            statuses=["yes", "yes", "yes", "yes", "partial"],
            recommended_tags_add=["@review"],
            recommended_subject_tags=["#CPT-classification"],
            knowledge_suggestions=[RICH_KNOWLEDGE],
        )
    )
    assert assessment.knowledge_suggestions[0]["target"] == "Atlas/Concepts/CPT.md"
    assert "knowledge_claim" in assessment.knowledge_suggestions[0]
    with pytest.raises(ValidationError):
        parse_llm_assessment(
            payload(
                stage=Stage.TO_REVISE,
                recommended_collection=Stage.TO_REVISE,
                recommendation_action="keep_in_revise",
                gate_result="hold",
                statuses=["yes", "yes", "yes", "yes", "partial"],
                recommended_tags_add=["@review"],
                recommended_subject_tags=["#CPT-classification"],
                knowledge_suggestions=[{"summary": "loose note"}],
            )
        )


def test_schema_rejects_action_only_knowledge_suggestions():
    with pytest.raises(ValidationError):
        parse_llm_assessment(payload(knowledge_suggestions=[{"type": "method_check", "target": "Multi-fidelity framework"}]))


def test_parse_llm_assessment_repairs_common_mojibake():
    assessment = parse_llm_assessment(
        payload(summary="O artigo propÃƒÂµe uma aplicaÃƒÂ§ÃƒÂ£o geotÃƒÂ©cnica.", evidence=["anÃƒÂ¡lise"])
    )
    assert "artigo" in assessment.summary
    assert "lise" in assessment.evidence[0]


def test_parse_llm_assessment_repairs_single_pass_mojibake():
    assessment = parse_llm_assessment(
        payload(summary="O artigo propÃƒÂµe uma aplicaÃƒÂ§ÃƒÂ£o geotÃƒÂ©cnica com RÃ‚Â².", evidence=["anÃƒÂ¡lise"])
    )
    assert "R" in assessment.summary
    assert "lise" in assessment.evidence[0]


def test_parse_llm_assessment_rejects_legacy_single_pass_tolook_output_without_criteria_evidence():
    with pytest.raises(ValidationError):
        parse_llm_assessment(
            '{"citekey":"fengActiveLearningMethod2026","stage":".ToLook",'
            '"title":"An active-learning method based on hierarchical Kriging model",'
            '"protocol_criteria":[{"criterion_id":"direct_relevance","criterion":"Relevancia direta",'
            '"status":"yes"}],'
            '"metrics":{"gate_score":6.0,"evidence_density":0.75},'
            '"recommended_tags_add":["methodology","domain"],'
            '"recommended_subject_tags":[],"knowledge_suggestions":[],'
            '"evidence":[{"text":"AHK-MCS estimates failure probability with fewer HF samples.",'
            '"rationale":"Defines the performance benefit."}]}'
        )
