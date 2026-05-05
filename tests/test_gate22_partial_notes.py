from paper_pipeline.assessment_notes import render_partial_note_from_llm_result
from paper_pipeline.contracts import Stage
from paper_pipeline.lmstudio_chat import LLMRunResult
from paper_pipeline.selection import CandidatePaper


def test_partial_llm_result_renders_partial_decision_note_with_warning():
    note = render_partial_note_from_llm_result(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="Paper"),
        result=LLMRunResult(status="partial", raw_outputs=["bad"], errors=["invalid JSON"]),
    )
    assert "Analise parcial" in note
    assert "invalid JSON" in note
    assert "retry_next_run" in note
