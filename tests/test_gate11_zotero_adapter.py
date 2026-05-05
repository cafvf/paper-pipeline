from paper_pipeline.contracts import CollectionAction, Stage
from paper_pipeline.selection import CandidatePaper
from paper_pipeline.zotero_adapter import MemoryZoteroAdapter, ZoteroItem
from paper_pipeline.zotero_plan import ZoteroActionPlan


def item(**kwargs):
    defaults = {
        "key": "Z1",
        "citekey": "paper2025",
        "title": "Bayesian CPT",
        "abstract": "soil uncertainty",
        "collections": [".ToLook", "Books"],
        "tags": ["@look"],
        "publication_year": 2025,
        "pdf_paths": ["paper.pdf"],
        "doi": "10.1000/example",
    }
    defaults.update(kwargs)
    return ZoteroItem(**defaults)


def test_memory_adapter_lists_candidates_by_operational_stage():
    adapter = MemoryZoteroAdapter([item(), item(key="Z2", citekey="book", collections=["Books"])])
    candidates = adapter.list_candidates()
    assert candidates == [
        CandidatePaper(
            citekey="paper2025",
            stage=Stage.TO_LOOK,
            title="Bayesian CPT",
            abstract="soil uncertainty",
            tags=["@look"],
            publication_year=2025,
            has_pdf=True,
            pdf_paths=["paper.pdf"],
            doi="10.1000/example",
            source_type="",
            journal="",
            authors=[],
        )
    ]


def test_adapter_apply_plan_preserves_non_operational_collections_and_creates_expendable():
    adapter = MemoryZoteroAdapter([item()])
    plan = ZoteroActionPlan(
        item_key="Z1",
        current_stage=Stage.TO_LOOK,
        target_stage=Stage.EXPENDABLE,
        collection_action=CollectionAction.MOVE_TO_EXPENDABLE,
        collections_to_set=["Books", "Expendable"],
        tags_to_add=["!discarded"],
        tags_to_remove=["@look"],
        final_tags=["!discarded"],
        status="planned",
    )
    result = adapter.apply_plan(plan)
    updated = adapter.items_by_key["Z1"]
    assert result["status"] == "applied"
    assert "Expendable" in adapter.collections
    assert updated.collections == ["Books", "Expendable"]
    assert updated.tags == ["!discarded"]
