from paper_pipeline.assessment_notes import render_note_from_assessment
from paper_pipeline.contracts import Stage
from paper_pipeline.llm_schema import LLMAssessment


def test_render_note_from_assessment_includes_artifact_links_and_recommended_tags():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_LOOK,
            recommended_collection=Stage.TO_REVISE,
            confidence=0.81,
            summary="Relevant to efforts.",
            evidence=["Abstract aligns with CPT."],
            recommended_tags_add=["@looked_by_llm"],
            knowledge_suggestions=[{"id": "k1", "target_note": "Atlas/Concepts/CPT.md", "summary": "Add CPT note"}],
        ),
        title="Paper",
        current_collection=".ToLook",
        artifact_links={"assessment": "x/LLM/papers/a/assessments/to_look_latest.json"},
    )
    assert "Recomendacao: `.To Revise`" in note
    assert "`@looked_by_llm`" in note
    assert "x/LLM/papers/a/assessments/to_look_latest.json" in note
    assert "k1" in note
    assert "Atlas/Concepts/CPT.md" in note
    assert "{'id':" not in note


def test_render_note_from_assessment_includes_protocol_table_and_metrics():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_LOOK,
            recommended_collection=Stage.TO_REVISE,
            confidence=0.81,
            summary="Relevant to efforts.",
            evidence=["Abstract aligns with CPT."],
            recommended_tags_add=[],
            knowledge_suggestions=[],
            protocol_criteria=[
                {
                    "criterion_id": "direct_relevance",
                    "criterion": "Relevancia direta ao trabalho atual",
                    "status": "yes",
                    "evidence": "Abstract aligns with CPT.",
                    "rationale": "Connects to probabilistic soil characterization.",
                }
            ],
            metrics={
                "criteria_met": 1,
                "criteria_total": 6,
                "criteria_score": 0.17,
                "evidence_coverage": 0.5,
                "decision_readiness": "medium",
                "protocol_gate": "Gate To Review: score >= 3/6",
            },
        ),
        title="Paper",
        current_collection=".ToLook",
    )
    assert "## Criterios do protocolo" in note
    assert "| Criterio | Status | Evidencia | Racional |" in note
    assert "| Relevancia direta ao trabalho atual | `sim` | Abstract aligns with CPT." in note
    assert "- Criterios atendidos: `1/6`" in note
    assert "- Cobertura de evidencias: `0.50`" in note


def test_render_note_from_assessment_includes_decision_contract_and_warnings():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_REVISE,
            recommended_collection=Stage.TO_REVISE,
            confidence=0.35,
            summary="Relevant but not deep enough.",
            article_type="original",
            review_type="none",
            article_type_confidence=0.65,
            gate_result="hold",
            recommendation_action="keep_in_revise",
            recommendation_rationale="Partial ToDig gate; keep as useful review material.",
            evidence=["Useful method context."],
            recommended_tags_add=["@review"],
            metrics={
                "criteria_met": 4,
                "criteria_total": 5,
                "criteria_score": 0.9,
                "evidence_coverage": 0.2,
                "decision_readiness": "medium",
                "warnings": ["low evidence_coverage", "partial criterion on hard ToDig gate"],
            },
        ),
        title="Paper",
        current_collection=".To Revise",
    )
    assert "## Contrato de decisao" in note
    assert "- Acao recomendada: `keep_in_revise`" in note
    assert "- Resultado do gate: `hold`" in note
    assert "- Tipo de artigo: `original`" in note
    assert "Partial ToDig gate" in note
    assert "## Avisos" in note
    assert "`low evidence_coverage`" in note


def test_render_note_from_assessment_includes_subject_tags_separately():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_DIG,
            recommended_collection=Stage.TO_DIG,
            confidence=0.81,
            summary="Relevant to efforts.",
            evidence=["CPT classification method."],
            recommended_tags_add=["@dug_by_llm"],
            recommended_subject_tags=["#soil-classification", "#CPT-classification", "%machine-learning", "$methods-cite"],
            knowledge_suggestions=[],
        ),
        title="Paper",
        current_collection=".ToDig",
    )
    assert "## Tags recomendadas" in note
    assert "`@dug_by_llm`" in note
    assert "## Tags de assunto sugeridas" in note
    assert "`#soil-classification`" in note
    assert "`%machine-learning`" in note
    assert "`$methods-cite`" in note


def test_render_note_from_assessment_filters_non_protocol_recommended_tags():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_LOOK,
            recommended_collection=Stage.TO_LOOK,
            confidence=0.6,
            summary="ok",
            evidence=[],
            recommended_tags_add=["free-tag"],
            knowledge_suggestions=[],
        ),
        title="Paper",
        current_collection=".ToLook",
    )
    assert "`@looked_by_llm`" in note
    assert "`free-tag`" not in note


def test_render_note_from_assessment_formats_structured_suggestions():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_LOOK,
            recommended_collection=Stage.TO_LOOK,
            confidence=0.6,
            summary="ok",
            evidence=[],
            recommended_tags_add=[],
            knowledge_suggestions=[
                {
                    "type": "concept",
                    "target": "Atlas/Concepts/CPT.md",
                    "content": "Add active learning kriging link.",
                    "justification": "CPT appears in the abstract.",
                }
            ],
        ),
        title="Paper",
        current_collection=".ToLook",
    )
    assert "- Tipo: `concept`; Alvo: `Atlas/Concepts/CPT.md`; Conhecimento: Add active learning kriging link.; Justificativa: CPT appears in the abstract." in note


def test_render_note_from_assessment_formats_unstructured_suggestions_as_human_text():
    note = render_note_from_assessment(
        assessment=LLMAssessment(
            citekey="a",
            stage=Stage.TO_LOOK,
            recommended_collection=Stage.TO_LOOK,
            confidence=0.6,
            summary="ok",
            evidence=[],
            recommended_tags_add=[],
            knowledge_suggestions=[
                {
                    "type": "methodology_check",
                    "content": "Verificar consistencia matematica.",
                }
            ],
        ),
        title="Paper",
        current_collection=".ToLook",
    )
    assert "- Tipo: `methodology_check`; Conhecimento: Verificar consistencia matematica." in note
    assert note.count("matematica.") == 1  # should appear exactly once, in the formatted suggestion
    assert "{'type':" not in note
