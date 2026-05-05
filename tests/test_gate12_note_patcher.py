from pathlib import Path

from paper_pipeline.note_patcher import (
    KnowledgePatch,
    apply_patch_plan,
    find_literature_note,
    plan_note_patch,
)


def test_find_literature_note_prefers_worked_note_not_zotero_source(tmp_path: Path):
    (tmp_path / "Atlas" / "Literature" / "Zotero").mkdir(parents=True)
    (tmp_path / "Atlas" / "Literature").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Atlas" / "Literature" / "Zotero" / "smith2024.md").write_text("source", encoding="utf-8")
    worked = tmp_path / "Atlas" / "Literature" / "smith2024 - Literature.md"
    worked.write_text("worked", encoding="utf-8")
    assert find_literature_note(tmp_path, "smith2024") == worked


def test_apply_patch_only_fills_placeholder_or_appends_new_block(tmp_path: Path):
    note = tmp_path / "Atlas" / "Literature" / "smith2024 - Literature.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Smith\n\n<!-- LLM:knowledge -->\n\nOld paragraph stays.\n", encoding="utf-8")
    patch = plan_note_patch(
        note_path=note,
        patch=KnowledgePatch(
            patch_id="p1",
            heading="Bayesian update",
            content="Preserve $p(\\theta | y)$ and markdown.",
            source_citekey="smith2024",
        ),
    )
    result = apply_patch_plan(patch)
    updated = note.read_text(encoding="utf-8")
    assert result["status"] == "applied"
    assert "Old paragraph stays." in updated
    assert "<!-- llm_patch_id: p1 -->" in updated
    assert "$p(\\theta | y)$" in updated


def test_plan_splits_long_concept_content_by_sections(tmp_path: Path):
    note = tmp_path / "Atlas" / "Concepts" / "Very long concept.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Concept\n", encoding="utf-8")
    plan = plan_note_patch(
        note_path=note,
        patch=KnowledgePatch(patch_id="long", heading="Long", content="A" * 2500, source_citekey="a"),
        note_kind="concept",
    )
    assert len(plan.blocks) == 3
    assert all(len(block.content) <= 1000 for block in plan.blocks)
