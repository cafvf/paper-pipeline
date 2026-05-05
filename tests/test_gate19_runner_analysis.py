from pathlib import Path

from paper_pipeline.config import default_config
from paper_pipeline.contracts import DecisionState, PartialAnalysisAction, PartialAnalysisDecision, Stage
from paper_pipeline.decision_notes import render_partial_analysis_note
from paper_pipeline.llm_schema import LLMAssessment
from paper_pipeline.lmstudio_chat import LLMRunResult
from paper_pipeline.runner import run_once
from paper_pipeline.selection import CandidatePaper


class OneCandidate:
    def list_candidates(self):
        return [CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="Paper", abstract="soil", has_pdf=True)]


class FakeAnalyzer:
    def analyze(self, candidate, artifact_store):
        return LLMAssessment(
            citekey=candidate.citekey,
            stage=candidate.stage,
            recommended_collection=Stage.TO_REVISE,
            confidence=0.9,
            summary="Good fit.",
            evidence=["intro"],
            recommended_tags_add=["@looked_by_llm"],
            knowledge_suggestions=[],
        )


class PartialAnalyzer:
    def __init__(self):
        self.last_result = LLMRunResult(status="partial", raw_outputs=[], errors=["timeout"])

    def analyze(self, candidate, artifact_store):
        return None


def test_runner_uses_analyzer_to_write_assessment_backed_decision_note(tmp_path: Path):
    cfg = default_config(tmp_path)
    result = run_once(config=cfg, zotero_source=OneCandidate(), lexical_index={"notes": []}, analyzer=FakeAnalyzer())
    assert result.selected == ["a"]
    note = (cfg.paths.inbox_dir / "a - LLM Paper Decision.md").read_text(encoding="utf-8")
    assert "Recomendacao: `.To Revise`" in note
    assert "`@looked_by_llm`" in note
    assert (cfg.paths.papers_root / "a" / "assessments" / "to_look_latest.json").exists()


def test_runner_writes_partial_note_when_analyzer_records_partial_result(tmp_path: Path):
    cfg = default_config(tmp_path)
    result = run_once(config=cfg, zotero_source=OneCandidate(), lexical_index={"notes": []}, analyzer=PartialAnalyzer())
    assert result.selected == ["a"]
    note = (cfg.paths.inbox_dir / "a - LLM Paper Decision.md").read_text(encoding="utf-8")
    assert "Analise parcial" in note
    assert "timeout" in note


def test_runner_consumes_approved_partial_retry_even_when_decision_application_is_disabled(tmp_path: Path):
    cfg = default_config(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True)
    (cfg.paths.inbox_dir / "a - LLM Paper Decision.md").write_text(
        render_partial_analysis_note(
            citekey="a",
            title="Paper",
            reason="timeout",
            existing=PartialAnalysisDecision(
                decision_state=DecisionState.APPROVED,
                partial_analysis_action=PartialAnalysisAction.RETRY_NEXT_RUN,
            ),
        ),
        encoding="utf-8",
    )
    result = run_once(
        config=cfg,
        zotero_source=OneCandidate(),
        lexical_index={"notes": []},
        analyzer=FakeAnalyzer(),
        apply_existing_decisions=False,
    )
    assert result.selected == ["a"]
    note = (cfg.paths.inbox_dir / "a - LLM Paper Decision.md").read_text(encoding="utf-8")
    assert "Recomendacao: `.To Revise`" in note
