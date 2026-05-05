from pathlib import Path

from paper_pipeline.artifacts import PaperArtifactStore
from paper_pipeline.config import default_config
from paper_pipeline.contracts import CollectionAction, DecisionState, FullDecision, Stage
from paper_pipeline.decision_notes import render_full_decision_note
from paper_pipeline.runner import NightlyRunResult, run_once
from paper_pipeline.selection import CandidatePaper
from paper_pipeline.zotero_collections import CollectionResolution


class FakeSource:
    def list_candidates(self):
        return [
            CandidatePaper(
                citekey="ok2025",
                stage=Stage.TO_LOOK,
                title="Bayesian CPT",
                abstract="soil uncertainty",
                has_pdf=True,
                publication_year=2025,
            ),
            CandidatePaper(
                citekey="nopdf2024",
                stage=Stage.TO_REVISE,
                title="No PDF",
                abstract="soil uncertainty",
                has_pdf=False,
                publication_year=2024,
            ),
        ]


class RecordingApplier:
    def __init__(self):
        self.plans = []

    def apply_plan(self, plan):
        self.plans.append(plan)
        return {"status": "applied"}


class SourceWithDecisionCandidate:
    def list_candidates(self):
        return [
            CandidatePaper(
                citekey="paper2026",
                stage=Stage.TO_LOOK,
                title="Paper",
                abstract="soil uncertainty",
                has_pdf=True,
                tags=["@look"],
                zotero_item_key="I1",
                collection_keys=["look", "topic"],
            ),
            CandidatePaper(
                citekey="new2026",
                stage=Stage.TO_LOOK,
                title="New Paper",
                abstract="soil uncertainty",
                has_pdf=True,
                zotero_item_key="I2",
                collection_keys=["look"],
            ),
        ]


def resolutions():
    return {
        Stage.TO_LOOK: CollectionResolution(Stage.TO_LOOK, "look", ".ToLook", ".ToLook"),
        Stage.TO_REVISE: CollectionResolution(Stage.TO_REVISE, "revise", ".To Revise", ".To Revise"),
        Stage.TO_DIG: CollectionResolution(Stage.TO_DIG, "dig", ".ToDig", ".ToDig"),
        Stage.EXPENDABLE: CollectionResolution(Stage.EXPENDABLE, "exp", "Expendable", "Expendable"),
    }


def test_run_once_applies_existing_decisions_then_writes_new_decision_notes(tmp_path: Path):
    cfg = default_config(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True)
    store = PaperArtifactStore(cfg.paths.papers_root, "manual")
    note = cfg.paths.inbox_dir / "manual - LLM Paper Decision.md"
    note.write_text(
        "---\ntype: inbox\n---\n```yaml\ndecision_state: manual_only\nmissing_pdf_action: manual_only\nmanual_notes: done\n```\n",
        encoding="utf-8",
    )
    result = run_once(config=cfg, zotero_source=FakeSource(), lexical_index={"notes": []}, max_total=2)
    assert isinstance(result, NightlyRunResult)
    assert not note.exists()
    written = sorted(path.name for path in cfg.paths.inbox_dir.glob("* - LLM Paper Decision.md"))
    assert written == ["nopdf2024 - LLM Paper Decision.md", "ok2025 - LLM Paper Decision.md"]


def test_run_once_can_skip_applying_existing_decisions_for_pilot(tmp_path: Path):
    cfg = default_config(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True)
    note = cfg.paths.inbox_dir / "manual - LLM Paper Decision.md"
    note.write_text(
        "---\ntype: inbox\n---\n```yaml\ndecision_state: manual_only\nmissing_pdf_action: manual_only\nmanual_notes: done\n```\n",
        encoding="utf-8",
    )
    result = run_once(
        config=cfg,
        zotero_source=FakeSource(),
        lexical_index={"notes": []},
        max_total=1,
        apply_existing_decisions=False,
    )
    assert note.exists()
    assert result.applied_decisions == []


def test_run_once_applies_zotero_decision_then_selects_new_candidates(tmp_path: Path):
    cfg = default_config(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True)
    note = cfg.paths.inbox_dir / "paper2026 - LLM Paper Decision.md"
    note.write_text(
        render_full_decision_note(
            citekey="paper2026",
            title="Paper",
            current_collection=".ToLook",
            recommended_collection=".ToDig",
            recommended_tags_add=[],
            existing_decision=FullDecision(
                decision_state=DecisionState.APPROVED,
                apply_zotero_actions=True,
                collection_action=CollectionAction.MOVE_TO_DIG,
                apply_knowledge_actions=False,
            ),
        ),
        encoding="utf-8",
    )
    applier = RecordingApplier()

    result = run_once(
        config=cfg,
        zotero_source=SourceWithDecisionCandidate(),
        lexical_index={"notes": []},
        max_total=1,
        zotero_applier=applier,
        operational_collections=resolutions(),
    )

    assert result.applied_decisions == [{"citekey": "paper2026", "status": "applied", "errors": []}]
    assert len(applier.plans) == 1
    assert applier.plans[0].item_key == "I1"
    assert applier.plans[0].target_stage == Stage.TO_DIG
    assert not note.exists()
    assert result.selected == ["new2026"]
