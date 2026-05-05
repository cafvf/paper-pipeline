from pathlib import Path

from paper_pipeline.artifacts import PaperArtifactStore
from paper_pipeline.contracts import CollectionAction, DecisionState, FullDecision, MissingPdfDecision, MissingPdfAction, PartialAnalysisDecision, PartialAnalysisAction, Stage
from paper_pipeline.decision_applier import apply_decision_note, scan_decision_notes
from paper_pipeline.decision_notes import render_full_decision_note, render_missing_pdf_note, render_partial_analysis_note
from paper_pipeline.zotero_plan import ZoteroActionPlan


class FakeApplier:
    def __init__(self, status="applied"):
        self.status = status
        self.applied = []

    def apply_plan(self, plan):
        self.applied.append(plan)
        return {"status": self.status}


def plan(target=Stage.TO_REVISE):
    return ZoteroActionPlan(
        item_key="I1",
        current_stage=Stage.TO_LOOK,
        target_stage=target,
        collection_action=CollectionAction.MOVE_TO_REVISE,
        collections_to_set=[],
        tags_to_add=[],
        tags_to_remove=[],
        final_tags=[],
        status="planned",
    )


def test_scan_decision_notes(tmp_path):
    (tmp_path / "a - LLM Paper Decision.md").write_text("x")
    (tmp_path / "other.md").write_text("x")
    assert scan_decision_notes(tmp_path) == [tmp_path / "a - LLM Paper Decision.md"]


def test_approved_zotero_only_applies_and_deletes(tmp_path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    text = render_full_decision_note(
        citekey="paper2026",
        title="Paper",
        current_collection=".ToLook",
        recommended_collection=".To Revise",
        recommended_tags_add=[],
        existing_decision=FullDecision(decision_state=DecisionState.APPROVED, apply_knowledge_actions=False),
    )
    note.write_text(text, encoding="utf-8")
    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"),
        zotero_plan=plan(),
        zotero_applier=FakeApplier(),
    )
    assert result.status == "applied"
    assert result.delete_note is True
    assert not note.exists()


def test_zotero_error_keeps_note(tmp_path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToLook",
            recommended_collection=".To Revise",
            recommended_tags_add=[],
            existing_decision=FullDecision(decision_state=DecisionState.APPROVED),
        ),
        encoding="utf-8",
    )
    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"),
        zotero_plan=plan(),
        zotero_applier=FakeApplier(status="error"),
    )
    assert result.status == "error"
    assert note.exists()


def test_manual_only_logs_and_deletes(tmp_path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToLook",
            recommended_collection=".To Revise",
            recommended_tags_add=[],
            existing_decision=FullDecision(decision_state=DecisionState.MANUAL_ONLY),
        ),
        encoding="utf-8",
    )
    result = apply_decision_note(note_path=note, citekey="paper2026", artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"))
    assert result.status == "manual_only"
    assert not note.exists()


def test_missing_pdf_discard_applies_reduced_plan(tmp_path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_missing_pdf_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToLook",
            existing=MissingPdfDecision(decision_state=DecisionState.APPROVED, missing_pdf_action=MissingPdfAction.MOVE_TO_EXPENDABLE),
        ),
        encoding="utf-8",
    )
    result = apply_decision_note(
        note_path=note,
        citekey="paper2026",
        artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"),
        zotero_plan=plan(Stage.EXPENDABLE),
        zotero_applier=FakeApplier(),
    )
    assert result.status == "applied"
    assert not note.exists()


def test_pending_partial_retry_stays_pending(tmp_path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_partial_analysis_note(
            citekey="paper2026",
            title="Paper",
            reason="failed",
            existing=PartialAnalysisDecision(partial_analysis_action=PartialAnalysisAction.RETRY_NEXT_RUN),
        ),
        encoding="utf-8",
    )
    result = apply_decision_note(note_path=note, citekey="paper2026", artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"))
    assert result.status == "pending"
    assert note.exists()


def test_approved_partial_retry_deletes_note_for_reprocessing(tmp_path):
    note = tmp_path / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_partial_analysis_note(
            citekey="paper2026",
            title="Paper",
            reason="failed",
            existing=PartialAnalysisDecision(
                decision_state=DecisionState.APPROVED,
                partial_analysis_action=PartialAnalysisAction.RETRY_NEXT_RUN,
            ),
        ),
        encoding="utf-8",
    )
    result = apply_decision_note(note_path=note, citekey="paper2026", artifact_store=PaperArtifactStore(tmp_path / "papers", "paper2026"))
    assert result.status == "retry_queued"
    assert result.delete_note is True
    assert not note.exists()
