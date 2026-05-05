import json

import pytest

from paper_pipeline.contracts import Stage, ValidationError
from paper_pipeline.llm_schema import parse_llm_assessment, render_schema_for_stage

ORIGINAL_DIG_CRITERIA = [
    "new_method_for_toolkit",
    "reproducible_equations_and_parameters",
    "validated_results",
    "domain_applicability",
    "paper_section_value",
]
REVIEW_DIG_CRITERIA = [
    "defines_state_of_art",
    "identifies_actionable_gaps",
    "selective_and_transparent_review",
    "reference_mining_value",
    "positions_extension_or_rebuttal",
]
LOOK_CRITERIA = [
    "direct_relevance",
    "comparable_methodology",
    "recent_or_seminal",
    "author_credibility",
    "explorable_gap",
    "citation_sentence_ready",
]


def assessment_json(
    *,
    stage: Stage,
    recommended_collection: Stage,
    recommendation_action: str,
    gate_result: str,
    statuses: list[str],
    criterion_ids: list[str] | None = None,
    article_type: str = "original",
    review_type: str = "none",
    article_type_confidence: float = 0.9,
    recommended_tags_add: list[str] | None = None,
    recommended_subject_tags: list[str] | None = None,
    knowledge_suggestions: list[dict] | None = None,
    confidence: float = 0.8,
    evidence_coverage: float = 0.6,
) -> str:
    criterion_ids = criterion_ids or (LOOK_CRITERIA if stage == Stage.TO_LOOK else ORIGINAL_DIG_CRITERIA)
    criteria = [
        {
            "criterion_id": criterion_id,
            "criterion": criterion_id.replace("_", " "),
            "status": status,
            "evidence": "evidence",
            "rationale": "rationale",
        }
        for criterion_id, status in zip(criterion_ids, statuses, strict=True)
    ]
    weighted = sum({"yes": 1.0, "partial": 0.5, "no": 0.0, "unknown": 0.0}[item] for item in statuses)
    payload = {
        "citekey": "paper2026",
        "stage": stage.value,
        "article_type": article_type,
        "review_type": review_type,
        "article_type_confidence": article_type_confidence,
        "gate_result": gate_result,
        "recommendation_action": recommendation_action,
        "recommended_collection": recommended_collection.value,
        "recommendation_rationale": "Gate decision follows the protocol.",
        "confidence": confidence,
        "summary": "Relevant paper.",
        "evidence": ["abstract"],
        "recommended_tags_add": recommended_tags_add if recommended_tags_add is not None else [],
        "recommended_subject_tags": recommended_subject_tags if recommended_subject_tags is not None else [],
        "knowledge_suggestions": knowledge_suggestions if knowledge_suggestions is not None else [],
        "protocol_criteria": criteria,
        "metrics": {
            "criteria_met": statuses.count("yes"),
            "criteria_total": len(statuses),
            "criteria_score": weighted / len(statuses),
            "evidence_coverage": evidence_coverage,
            "decision_readiness": "high",
        },
    }
    return json.dumps(payload)


def test_schema_requires_decision_contract_fields():
    schema = render_schema_for_stage(Stage.TO_LOOK)
    for field in [
        "article_type",
        "review_type",
        "article_type_confidence",
        "gate_result",
        "recommendation_action",
        "recommendation_rationale",
    ]:
        assert field in schema["required"]
        assert field in schema["properties"]


def test_tolook_passes_gate_only_when_recommending_move_to_revise():
    assessment = parse_llm_assessment(
        assessment_json(
            stage=Stage.TO_LOOK,
            statuses=["yes", "yes", "yes", "no", "no", "no"],
            gate_result="pass",
            recommendation_action="move_to_revise",
            recommended_collection=Stage.TO_REVISE,
            recommended_tags_add=["@review"],
            recommended_subject_tags=["#prob-soil-characterization", "%machine-learning"],
        )
    )

    assert assessment.recommendation_action == "move_to_revise"
    assert assessment.metrics["criteria_score"] == 0.5
    assert assessment.recommended_subject_tags == ["#prob-soil-characterization", "%machine-learning"]


def test_tolook_rejects_expendable_when_weighted_score_passes_review_gate():
    with pytest.raises(ValidationError, match="ToLook pass gate requires move_to_revise"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_LOOK,
                statuses=["yes", "yes", "yes", "no", "no", "no"],
                gate_result="fail",
                recommendation_action="move_to_expendable",
                recommended_collection=Stage.EXPENDABLE,
                recommended_tags_add=["!discarded"],
            )
        )


def test_tolook_low_score_recommends_discard_and_can_still_suggest_subject_tags():
    assessment = parse_llm_assessment(
        assessment_json(
            stage=Stage.TO_LOOK,
            statuses=["yes", "partial", "no", "no", "no", "no"],
            gate_result="fail",
            recommendation_action="move_to_expendable",
            recommended_collection=Stage.EXPENDABLE,
            recommended_tags_add=["!discarded"],
            recommended_subject_tags=["#prob-soil-characterization"],
        )
    )

    assert assessment.recommendation_action == "move_to_expendable"
    assert assessment.recommended_collection == Stage.EXPENDABLE
    assert assessment.recommended_subject_tags == ["#prob-soil-characterization"]


def test_revise_original_with_five_yes_must_move_to_dig():
    assessment = parse_llm_assessment(
        assessment_json(
            stage=Stage.TO_REVISE,
            statuses=["yes", "yes", "yes", "yes", "yes"],
            gate_result="pass",
            recommendation_action="move_to_dig",
            recommended_collection=Stage.TO_DIG,
            recommended_tags_add=["@dig"],
            recommended_subject_tags=["#prob-soil-characterization", "%machine-learning", "$methods-cite"],
        )
    )

    assert assessment.recommendation_action == "move_to_dig"
    assert assessment.recommended_collection == Stage.TO_DIG


def test_revise_original_partial_does_not_pass_hard_todig_gate():
    assessment = parse_llm_assessment(
        assessment_json(
            stage=Stage.TO_REVISE,
            statuses=["yes", "yes", "yes", "yes", "partial"],
            gate_result="hold",
            recommendation_action="keep_in_revise",
            recommended_collection=Stage.TO_REVISE,
            recommended_tags_add=["@review"],
            recommended_subject_tags=["#prob-soil-characterization", "%machine-learning"],
        )
    )

    assert assessment.recommendation_action == "keep_in_revise"
    assert assessment.metrics["criteria_score"] == 0.9
    assert "partial criterion on hard ToDig gate" in assessment.metrics["warnings"]


def test_revise_original_rejects_review_criteria_and_can_retry():
    with pytest.raises(ValidationError, match="article_type original requires original ToDig criteria"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                article_type="original",
                review_type="none",
                criterion_ids=REVIEW_DIG_CRITERIA,
                statuses=["yes", "yes", "yes", "yes", "yes"],
                gate_result="pass",
                recommendation_action="move_to_dig",
                recommended_collection=Stage.TO_DIG,
                recommended_tags_add=["@dig"],
            )
        )


def test_revise_review_uses_review_criteria_and_requires_review_tag():
    assessment = parse_llm_assessment(
        assessment_json(
            stage=Stage.TO_REVISE,
            article_type="review",
            review_type="scoping-review",
            criterion_ids=REVIEW_DIG_CRITERIA,
            statuses=["yes", "yes", "yes", "yes", "yes"],
            gate_result="pass",
            recommendation_action="move_to_dig",
            recommended_collection=Stage.TO_DIG,
            recommended_tags_add=["@dig"],
            recommended_subject_tags=["%scoping-review", "$background"],
        )
    )

    assert assessment.article_type == "review"
    assert assessment.review_type == "scoping-review"


def test_rejects_review_type_without_review_tag():
    with pytest.raises(ValidationError, match="review article requires a review method tag"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                article_type="review",
                review_type="scoping-review",
                criterion_ids=REVIEW_DIG_CRITERIA,
                statuses=["yes", "yes", "yes", "yes", "yes"],
                gate_result="pass",
                recommendation_action="move_to_dig",
                recommended_collection=Stage.TO_DIG,
                recommended_tags_add=["@dig"],
            )
        )


def test_rejects_review_tag_with_original_article_type():
    with pytest.raises(ValidationError, match="review tag requires article_type review"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                article_type="original",
                review_type="none",
                statuses=["yes", "yes", "yes", "yes", "yes"],
                gate_result="pass",
                recommendation_action="move_to_dig",
                recommended_collection=Stage.TO_DIG,
                recommended_tags_add=["@dig"],
                recommended_subject_tags=["%scoping-review"],
            )
        )


def test_rejects_action_collection_mismatch():
    with pytest.raises(ValidationError, match="recommendation_action does not match recommended_collection"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                statuses=["yes", "yes", "yes", "yes", "yes"],
                gate_result="pass",
                recommendation_action="move_to_dig",
                recommended_collection=Stage.TO_REVISE,
                recommended_tags_add=["@dig"],
            )
        )


def test_rejects_discard_without_discard_tag_and_discard_tag_without_discard_action():
    with pytest.raises(ValidationError, match="move_to_expendable requires !discarded"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_LOOK,
                statuses=["no", "no", "no", "no", "no", "no"],
                gate_result="fail",
                recommendation_action="move_to_expendable",
                recommended_collection=Stage.EXPENDABLE,
            )
        )
    with pytest.raises(ValidationError, match="!discarded requires move_to_expendable"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                statuses=["yes", "no", "no", "no", "no"],
                gate_result="hold",
                recommendation_action="keep_in_revise",
                recommended_collection=Stage.TO_REVISE,
                recommended_tags_add=["!discarded"],
            )
        )


def test_rejects_discard_with_absolute_blockers():
    with pytest.raises(ValidationError, match="move_to_expendable conflicts with knowledge_suggestions"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                statuses=["no", "no", "no", "no", "no"],
                gate_result="fail",
                recommendation_action="move_to_expendable",
                recommended_collection=Stage.EXPENDABLE,
                recommended_tags_add=["!discarded"],
                knowledge_suggestions=[
                    {
                        "type": "method_check",
                        "target": "Matrix completion",
                        "knowledge_claim": "Low-rank completion may help sparse geotechnical datasets in constrained characterization workflows.",
                        "article_use": "The paper applies the method to missing multivariate geotechnical data.",
                        "evidence": ["method section"],
                        "applicability": "Useful when datasets have correlated variables and sparse measurements.",
                        "limitations": "Accuracy depends on the low-rank assumption.",
                        "integration_notes": "Link to probabilistic soil characterization notes.",
                        "review_tasks": [],
                        "justification": "The paper supplies reusable method details.",
                    }
                ],
            )
        )
    with pytest.raises(ValidationError, match="move_to_expendable conflicts with blocking tags"):
        parse_llm_assessment(
            assessment_json(
                stage=Stage.TO_REVISE,
                statuses=["no", "no", "no", "no", "no"],
                gate_result="fail",
                recommendation_action="move_to_expendable",
                recommended_collection=Stage.EXPENDABLE,
                recommended_tags_add=["!discarded"],
                recommended_subject_tags=["$methods-cite"],
            )
        )


def test_adds_warnings_for_low_evidence_and_low_confidence_strong_recommendation():
    assessment = parse_llm_assessment(
        assessment_json(
            stage=Stage.TO_REVISE,
            statuses=["yes", "yes", "yes", "yes", "yes"],
            gate_result="pass",
            recommendation_action="move_to_dig",
            recommended_collection=Stage.TO_DIG,
            recommended_tags_add=["@dig"],
            confidence=0.35,
            evidence_coverage=0.2,
        )
    )

    assert "low evidence_coverage" in assessment.metrics["warnings"]
    assert "low confidence for strong recommendation" in assessment.metrics["warnings"]
