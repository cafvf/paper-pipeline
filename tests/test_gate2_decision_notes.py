import pytest

from paper_pipeline.contracts import CollectionAction, DecisionState, FullDecision, KnowledgeAction, MissingPdfAction, MissingPdfDecision, PartialAnalysisAction, PartialAnalysisDecision, ValidationError
from paper_pipeline.decision_notes import (
    decision_note_path,
    parse_decision_from_text,
    render_full_decision_note,
    render_missing_pdf_note,
    render_partial_analysis_note,
    validate_full_decision,
)


def test_decision_note_path_uses_citekey():
    assert decision_note_path("+", "abc:123").as_posix() == "+/abc123 - LLM Paper Decision.md"


def test_full_note_round_trips_default_yaml():
    text = render_full_decision_note(
        citekey="paper2026",
        title="A Paper",
        current_collection=".ToLook",
        recommended_collection=".To Revise",
        recommended_tags_add=["@review", "@looked_by_llm"],
    )
    assert "type: inbox" in text
    assert "## Guia de decisao" in text
    assert "`decision_state`: `pending`, `approved`, `rejected`, `deferred`, `manual_only`" in text
    assert "`collection_action`: `accept_recommendation`, `keep_current`, `move_to_tolook`, `move_to_revise`, `move_to_dig`, `move_to_expendable`, `no_collection_change`, `manual_only`" in text
    assert "`knowledge_actions.suggestions`: opcional" in text
    parsed = parse_decision_from_text(text)
    assert isinstance(parsed, FullDecision)
    assert parsed.decision_state == DecisionState.PENDING
    assert parsed.collection_action == CollectionAction.ACCEPT_RECOMMENDATION


def test_rejected_accept_recommendation_is_invalid():
    with pytest.raises(ValidationError):
        validate_full_decision(
            FullDecision(
                decision_state=DecisionState.REJECTED,
                collection_action=CollectionAction.ACCEPT_RECOMMENDATION,
            )
        )


def test_missing_pdf_note_uses_reduced_schema():
    text = render_missing_pdf_note(citekey="paper2026", title="A Paper", current_collection=".ToLook")
    assert "`missing_pdf_action`: `attach_pdf`, `defer`, `move_to_expendable`, `manual_only`" in text
    parsed = parse_decision_from_text(text)
    assert isinstance(parsed, MissingPdfDecision)
    assert parsed.missing_pdf_action == MissingPdfAction.ATTACH_PDF


def test_partial_analysis_note_uses_reduced_schema():
    text = render_partial_analysis_note(citekey="paper2026", title="A Paper", reason="LLM failed")
    assert "`partial_analysis_action`: `retry_next_run`, `defer`, `move_to_expendable`, `manual_only`" in text
    parsed = parse_decision_from_text(text)
    assert isinstance(parsed, PartialAnalysisDecision)
    assert parsed.partial_analysis_action == PartialAnalysisAction.RETRY_NEXT_RUN


def test_existing_decision_is_preserved_when_rendering_update():
    existing = FullDecision(
        decision_state=DecisionState.APPROVED,
        apply_knowledge_actions=True,
        knowledge_actions=__import__("paper_pipeline.contracts", fromlist=["KnowledgeActions"]).KnowledgeActions(
            literature_note=KnowledgeAction.UPDATE_EXISTING
        ),
    )
    text = render_full_decision_note(
        citekey="paper2026",
        title="A Paper",
        current_collection=".To Revise",
        recommended_collection=".ToDig",
        recommended_tags_add=["@dig"],
        existing_decision=existing,
    )
    parsed = parse_decision_from_text(text)
    assert isinstance(parsed, FullDecision)
    assert parsed.decision_state == DecisionState.APPROVED
    assert parsed.apply_knowledge_actions is True
    assert parsed.knowledge_actions.literature_note == KnowledgeAction.UPDATE_EXISTING
