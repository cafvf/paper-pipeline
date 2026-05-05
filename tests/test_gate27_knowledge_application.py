import json
from pathlib import Path

from paper_pipeline.artifacts import PaperArtifactStore
from paper_pipeline.contracts import DecisionState, FullDecision, KnowledgeAction, KnowledgeActions
from paper_pipeline.decision_applier import apply_decision_note
from paper_pipeline.decision_notes import render_full_decision_note

ORIGINAL_TODIG_CRITERIA = [
    "new_method_for_toolkit",
    "reproducible_equations_and_parameters",
    "validated_results",
    "domain_applicability",
    "paper_section_value",
]


def valid_todig_assessment(
    *,
    summary: str,
    evidence: list[str] | None = None,
    knowledge_suggestions: list[dict] | None = None,
) -> dict:
    return {
        "citekey": "paper2026",
        "stage": ".ToDig",
        "article_type": "original",
        "review_type": "none",
        "article_type_confidence": 0.9,
        "gate_result": "pass",
        "recommendation_action": "keep_in_dig",
        "recommendation_rationale": "The paper remains useful for deep knowledge extraction.",
        "recommended_collection": ".ToDig",
        "confidence": 0.8,
        "summary": summary,
        "evidence": evidence if evidence is not None else [],
        "recommended_tags_add": ["@dig"],
        "recommended_subject_tags": [],
        "knowledge_suggestions": knowledge_suggestions if knowledge_suggestions is not None else [],
        "protocol_criteria": [
            {
                "criterion_id": criterion_id,
                "criterion": criterion_id.replace("_", " "),
                "status": "yes",
                "evidence": "The assessment artifact includes enough evidence for this criterion.",
                "rationale": "Useful for the current research protocol.",
            }
            for criterion_id in ORIGINAL_TODIG_CRITERIA
        ],
        "metrics": {
            "criteria_met": 5,
            "criteria_total": 5,
            "criteria_score": 1,
            "evidence_coverage": 1,
            "decision_readiness": "high",
        },
    }


def valid_tolook_pass_assessment() -> dict:
    criteria = [
        ("direct_relevance", "yes"),
        ("comparable_methodology", "yes"),
        ("recent_or_seminal", "yes"),
        ("author_credibility", "no"),
        ("explorable_gap", "no"),
        ("citation_sentence_ready", "yes"),
    ]
    return {
        "citekey": "paper2026",
        "stage": ".ToLook",
        "article_type": "original",
        "review_type": "none",
        "article_type_confidence": 0.9,
        "gate_result": "pass",
        "recommendation_action": "move_to_revise",
        "recommendation_rationale": "Four ToLook criteria are met.",
        "recommended_collection": ".To Revise",
        "confidence": 0.8,
        "summary": "Valid pass output.",
        "evidence": ["abstract"],
        "recommended_tags_add": ["@review"],
        "recommended_subject_tags": [],
        "knowledge_suggestions": [],
        "protocol_criteria": [
            {
                "criterion_id": criterion_id,
                "criterion": criterion_id.replace("_", " "),
                "status": status,
                "evidence": "abstract",
                "rationale": "fits" if status == "yes" else "not enough evidence",
            }
            for criterion_id, status in criteria
        ],
        "metrics": {
            "criteria_met": 4,
            "criteria_total": 6,
            "criteria_score": 4 / 6,
            "evidence_coverage": 0.5,
            "decision_readiness": "medium",
        },
    }


def test_approved_knowledge_actions_create_inbox_drafts_with_atlas_links(tmp_path: Path):
    vault = tmp_path / "vault"
    concept = vault / "Atlas" / "Concepts" / "Gaussian Process Regression.md"
    concept.parent.mkdir(parents=True)
    concept.write_text("---\ntype: concept\n---\n# Gaussian Process Regression\n", encoding="utf-8")
    (vault / "Atlas" / "Literature").mkdir(parents=True)
    note = vault / "+" / "paper2026 - LLM Paper Decision.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToDig",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=False,
                apply_knowledge_actions=True,
                knowledge_actions=KnowledgeActions(literature_note=KnowledgeAction.CREATE_NEW),
            ),
        ),
        encoding="utf-8",
    )
    store = PaperArtifactStore(vault / "x" / "LLM" / "papers", "paper2026")
    store.write_latest_and_history(
        "assessments",
        "to_dig",
        valid_todig_assessment(
            summary="GPR multi-fidelity method.",
            evidence=["Validated against field data."],
            knowledge_suggestions=[
                {
                    "type": "method_check",
                    "target": "Gaussian Process Regression",
                    "knowledge_claim": (
                        "Multi-fidelity Gaussian Process Regression can fuse sparse high-quality geotechnical "
                        "measurements with broader lower-fidelity measurements to characterize spatial variability."
                    ),
                    "article_use": "The paper uses GPR as the fusion model for multi-fidelity geotechnical measurements.",
                    "evidence": ["Validated against field data."],
                    "applicability": "Connect this to existing GPR notes as a geotechnical data fusion pattern.",
                    "limitations": "The assessment only confirms the method at the level available in the packet.",
                    "integration_notes": "Link to Gaussian Process Regression and geotechnical variability notes.",
                    "review_tasks": ["Check whether the existing GPR note already covers multi-fidelity fusion."],
                    "justification": "The paper extends the current method note.",
                }
            ],
        ),
    )
    lexical_index = {
        "notes": [
            {
                "path": "Atlas/Concepts/Gaussian Process Regression.md",
                "family": "atlas/Concepts",
                "title": "Gaussian Process Regression",
                "aliases": [],
                "tags": ["atlas/concept"],
                "headings": [],
                "text": "Gaussian Process Regression GPR",
                "weight": 10,
            }
        ]
    }

    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=store,
        vault_root=vault,
        lexical_index=lexical_index,
    )

    assert result.status == "applied"
    assert not note.exists()
    assert "<!-- llm_patch_id: paper2026-suggestion-1 -->" not in concept.read_text(encoding="utf-8")
    literature = vault / "+" / "paper2026 - Literature Draft.md"
    assert literature.exists()
    assert "type: inbox" in literature.read_text(encoding="utf-8")
    assert "target_type: literature" in literature.read_text(encoding="utf-8")
    suggestion = vault / "+" / "paper2026 - Gaussian Process Regression Draft.md"
    assert suggestion.exists()
    suggestion_text = suggestion.read_text(encoding="utf-8")
    assert "[[Atlas/Concepts/Gaussian Process Regression|Gaussian Process Regression]]" in suggestion_text
    assert "## Definicao formal" in suggestion_text
    assert "## Intuicao fisica" in suggestion_text
    assert "## Hipoteses e limites" in suggestion_text
    assert "## Como aparece na literatura" in suggestion_text
    assert "## Conexoes com meu trabalho" in suggestion_text
    assert "## Links" in suggestion_text
    assert "Multi-fidelity Gaussian Process Regression can fuse sparse high-quality geotechnical" in suggestion_text
    assert "Pendencias de revisao" in suggestion_text
    integration = vault / "+" / "paper2026 - Knowledge Integration Draft.md"
    assert integration.exists()
    assert "[[Atlas/Concepts/Gaussian Process Regression|Gaussian Process Regression]]" in integration.read_text(encoding="utf-8")
    assert "[[+/paper2026 - Gaussian Process Regression Draft|Gaussian Process Regression]]" in integration.read_text(encoding="utf-8")
    assert "template_source: x/Templates/MOCTemplate.md" in integration.read_text(encoding="utf-8")


def test_knowledge_actions_create_new_suggestion_draft_in_inbox_when_no_atlas_match(tmp_path: Path):
    vault = tmp_path / "vault"
    note = vault / "+" / "paper2026 - LLM Paper Decision.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToDig",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=False,
                apply_knowledge_actions=True,
            ),
        ),
        encoding="utf-8",
    )
    store = PaperArtifactStore(vault / "x" / "LLM" / "papers", "paper2026")
    store.write_latest_and_history(
        "assessments",
        "to_dig",
        valid_todig_assessment(
            summary="A new idea.",
            knowledge_suggestions=[
                {
                    "type": "concept",
                    "target": "New Concept",
                    "knowledge_claim": "New Concept describes a reusable idea extracted from the paper rather than a task to be done later.",
                    "article_use": "The paper uses the idea as a named methodological contribution in the analyzed packet.",
                    "evidence": ["The packet presents New Concept as the central contribution."],
                    "applicability": "Use this draft as a candidate Atlas concept linked to the source literature note.",
                    "limitations": "The concept still needs human review before promotion from inbox.",
                    "integration_notes": "Compare with nearby Atlas concept notes before moving it.",
                    "review_tasks": ["Decide whether this should become a concept or dot."],
                    "justification": "No current Atlas note matches.",
                }
            ],
        ),
    )

    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=store,
        vault_root=vault,
        lexical_index={"notes": []},
    )

    assert result.status == "applied"
    draft = vault / "+" / "paper2026 - New Concept Draft.md"
    assert draft.exists()
    text = draft.read_text(encoding="utf-8")
    assert "type: inbox" in text
    assert "target_type: concept" in text
    assert "template_source: x/Templates/ConceptTemplate.md" in text
    assert "## Definicao formal" in text
    assert "rather than a task to be done later" in text


def test_knowledge_actions_create_dot_draft_with_dot_template_sections(tmp_path: Path):
    vault = tmp_path / "vault"
    note = vault / "+" / "paper2026 - LLM Paper Decision.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToDig",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=False,
                apply_knowledge_actions=True,
            ),
        ),
        encoding="utf-8",
    )
    store = PaperArtifactStore(vault / "x" / "LLM" / "papers", "paper2026")
    store.write_latest_and_history(
        "assessments",
        "to_dig",
        valid_todig_assessment(
            summary="A reusable observation.",
            knowledge_suggestions=[
                {
                    "type": "dot",
                    "target": "Sparse CPT profiles can guide local refinement",
                    "knowledge_claim": "Sparse CPT profiles can guide local refinement when the reliability surrogate needs more information near a failure boundary.",
                    "article_use": "The paper uses sparse geotechnical measurements as a reason to refine local surrogate behavior.",
                    "evidence": ["The packet links sparse field signals to local refinement of the surrogate."],
                    "applicability": "Use as a dot connected to CPT and active learning notes.",
                    "limitations": "The dot should stay tied to cases where sparse measurements inform the limit state.",
                    "integration_notes": "Link to CPT and Active Learning Kriging concepts.",
                    "review_tasks": ["Check whether this belongs under a CPT MOC."],
                    "justification": "This is an atomic reusable insight.",
                }
            ],
        ),
    )

    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=store,
        vault_root=vault,
        lexical_index={"notes": []},
    )

    assert result.status == "applied"
    draft = vault / "+" / "paper2026 - Sparse CPT profiles can guide local refinement Draft.md"
    text = draft.read_text(encoding="utf-8")
    assert "target_type: dot" in text
    assert "template_source: x/Templates/DotTemplate.md" in text
    assert "## Definicao" in text
    assert "## Essencia" in text
    assert "## Contexto" in text
    assert "## Relacoes" in text
    assert "## Exemplos" in text
    assert "## Referencias" in text


def test_knowledge_actions_create_moc_draft_with_linked_notes(tmp_path: Path):
    vault = tmp_path / "vault"
    concept = vault / "Atlas" / "Concepts" / "CPT.md"
    dot = vault / "Atlas" / "Dots" / "Sparse CPT.md"
    concept.parent.mkdir(parents=True)
    dot.parent.mkdir(parents=True)
    concept.write_text("---\ntype: concept\n---\n# CPT\n", encoding="utf-8")
    dot.write_text("---\ntype: dot\n---\n# Sparse CPT\n", encoding="utf-8")
    note = vault / "+" / "paper2026 - LLM Paper Decision.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToDig",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=False,
                apply_knowledge_actions=True,
            ),
        ),
        encoding="utf-8",
    )
    store = PaperArtifactStore(vault / "x" / "LLM" / "papers", "paper2026")
    store.write_latest_and_history(
        "assessments",
        "to_dig",
        valid_todig_assessment(
            summary="A local map.",
            knowledge_suggestions=[
                {
                    "type": "moc",
                    "target": "CPT reliability workflow",
                    "knowledge_claim": "CPT reliability workflow maps how sparse cone penetration measurements can feed surrogate reliability analysis.",
                    "article_use": "The paper connects CPT-like measurements, surrogate models and reliability assessment into one workflow.",
                    "evidence": ["The packet links field measurements to surrogate reliability assessment."],
                    "applicability": "Use this map to navigate between CPT, sparse data and reliability analysis notes.",
                    "limitations": "The map is a starting point and needs human curation before promotion.",
                    "integration_notes": "Connect CPT concepts and sparse CPT dots under a workflow map.",
                    "review_tasks": ["Decide whether this should merge with an existing geostatistics MOC."],
                    "justification": "The suggestion is navigational rather than atomic.",
                }
            ],
        ),
    )
    lexical_index = {
        "notes": [
            {
                "path": "Atlas/Concepts/CPT.md",
                "family": "atlas/Concepts",
                "title": "CPT",
                "aliases": [],
                "tags": [],
                "headings": [],
                "text": "CPT reliability workflow cone penetration",
                "weight": 10,
            },
            {
                "path": "Atlas/Dots/Sparse CPT.md",
                "family": "atlas/Dots",
                "title": "Sparse CPT",
                "aliases": [],
                "tags": [],
                "headings": [],
                "text": "Sparse CPT measurements reliability workflow",
                "weight": 10,
            },
        ]
    }

    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=store,
        vault_root=vault,
        lexical_index=lexical_index,
    )

    assert result.status == "applied"
    draft = vault / "+" / "paper2026 - CPT reliability workflow Draft.md"
    text = draft.read_text(encoding="utf-8")
    assert "target_type: moc" in text
    assert "template_source: x/Templates/MOCTemplate.md" in text
    assert "## Visao geral" in text
    assert "## Conceitos principais" in text
    assert "[[Atlas/Concepts/CPT|CPT]]" in text
    assert "[[Atlas/Dots/Sparse CPT|Sparse CPT]]" in text
    assert "## Fontes" in text


def test_knowledge_actions_require_vault_root(tmp_path: Path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToDig",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=False,
                apply_knowledge_actions=True,
            ),
        ),
        encoding="utf-8",
    )
    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"),
    )

    assert result.status == "error"
    assert "vault_root required" in result.errors[0]
    assert note.exists()


def test_knowledge_actions_skip_stale_invalid_assessment_and_use_pass_output(tmp_path: Path):
    vault = tmp_path / "vault"
    note = vault / "+" / "paper2026 - LLM Paper Decision.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToLook",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=False,
                apply_knowledge_actions=True,
            ),
        ),
        encoding="utf-8",
    )
    store = PaperArtifactStore(vault / "x" / "LLM" / "papers", "paper2026")
    store.write_latest_and_history("assessments", "to_look", {"citekey": "paper2026", "stage": ".ToLook"})
    store.write_passes(
        "to_look",
        "latest",
        {
            "llm_result": {
                "raw_outputs": [
                    json.dumps(valid_tolook_pass_assessment())
                ]
            }
        },
    )

    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=store,
        vault_root=vault,
        lexical_index={"notes": []},
    )

    assert result.status == "applied"
    assert (vault / "+" / "paper2026 - Knowledge Integration Draft.md").exists()
