from pathlib import Path

import pytest

from paper_pipeline.config import default_config
from paper_pipeline.contracts import CollectionAction, Stage, ValidationError
from paper_pipeline.llm_schema import parse_llm_assessment
from paper_pipeline.note_patcher import KnowledgePatch, apply_patch_plan, plan_note_patch
from paper_pipeline.runner import run_once
from paper_pipeline.selection import CandidatePaper
from paper_pipeline.zotero_adapter import MemoryZoteroAdapter, ZoteroItem
from paper_pipeline.zotero_plan import ZoteroActionPlan


def test_memory_adapter_refuses_blocked_plan_without_mutating_item():
    adapter = MemoryZoteroAdapter(
        [
            ZoteroItem(
                key="Z1",
                citekey="paper",
                title="Paper",
                collections=[".ToLook", "Books"],
                tags=["@look"],
            )
        ]
    )
    plan = ZoteroActionPlan(
        item_key="Z1",
        current_stage=Stage.TO_LOOK,
        target_stage=Stage.TO_REVISE,
        collection_action=CollectionAction.MOVE_TO_REVISE,
        collections_to_set=["Books", ".To Revise"],
        tags_to_add=[],
        tags_to_remove=[],
        final_tags=["@review"],
        status="blocked",
        reason="multiple_operational_collections",
    )
    result = adapter.apply_plan(plan)
    assert result["status"] == "blocked"
    assert adapter.items_by_key["Z1"].collections == [".ToLook", "Books"]
    assert adapter.items_by_key["Z1"].tags == ["@look"]


class SourceWithPending:
    def list_candidates(self):
        return [
            CandidatePaper(citekey="pending", stage=Stage.TO_LOOK, title="Pending", abstract="soil", has_pdf=True),
            CandidatePaper(citekey="fresh", stage=Stage.TO_LOOK, title="Fresh", abstract="soil", has_pdf=True),
        ]


class SourceWithBroken:
    def list_candidates(self):
        return [
            CandidatePaper(citekey="broken", stage=Stage.TO_LOOK, title="Broken", abstract="soil", has_pdf=True),
            CandidatePaper(citekey="fresh", stage=Stage.TO_LOOK, title="Fresh", abstract="soil", has_pdf=True),
        ]


def test_runner_excludes_existing_pending_decision_notes_before_selection(tmp_path: Path):
    cfg = default_config(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True)
    (cfg.paths.inbox_dir / "pending - LLM Paper Decision.md").write_text(
        "---\ntype: inbox\n---\n```yaml\ndecision_state: pending\ncollection_action: accept_recommendation\n```\n",
        encoding="utf-8",
    )
    result = run_once(config=cfg, zotero_source=SourceWithPending(), lexical_index={"notes": []}, max_total=1)
    assert result.selected == ["fresh"]
    assert sorted(path.name for path in cfg.paths.inbox_dir.glob("* - LLM Paper Decision.md")) == [
        "fresh - LLM Paper Decision.md",
        "pending - LLM Paper Decision.md",
    ]


def test_llm_schema_wraps_invalid_stage_as_contract_validation_error():
    with pytest.raises(ValidationError):
        parse_llm_assessment(
            '{"citekey":"a","stage":"Bad","recommended_collection":".ToLook","confidence":0.1,'
            '"summary":"x","evidence":[],"recommended_tags_add":[],"knowledge_suggestions":[]}'
        )


def test_runner_keeps_malformed_decision_note_and_continues_selection(tmp_path: Path):
    cfg = default_config(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True)
    malformed = cfg.paths.inbox_dir / "broken - LLM Paper Decision.md"
    malformed.write_text("# no yaml block\n", encoding="utf-8")
    result = run_once(config=cfg, zotero_source=SourceWithBroken(), lexical_index={"notes": []}, max_total=1)
    assert malformed.exists()
    assert result.applied_decisions[0]["status"] == "error"
    assert result.selected == ["fresh"]


def test_note_patcher_refuses_zotero_source_note(tmp_path: Path):
    source = tmp_path / "Atlas" / "Literature" / "Zotero" / "smith2024.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Source\n", encoding="utf-8")
    plan = plan_note_patch(
        note_path=source,
        patch=KnowledgePatch(patch_id="p1", heading="Do not write", content="x", source_citekey="smith2024"),
    )
    with pytest.raises(ValidationError):
        apply_patch_plan(plan)
    assert source.read_text(encoding="utf-8") == "# Source\n"
