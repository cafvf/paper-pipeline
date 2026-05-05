from paper_pipeline.contracts import DISCARD_TAG, CollectionAction, Stage
from paper_pipeline.zotero_collections import CollectionResolution
from paper_pipeline.zotero_plan import ZoteroItemState, build_zotero_action_plan


def resolutions():
    return {
        Stage.TO_LOOK: CollectionResolution(Stage.TO_LOOK, "look", ".ToLook", ".ToLook"),
        Stage.TO_REVISE: CollectionResolution(Stage.TO_REVISE, "revise", ".To Revise", ".To Revise"),
        Stage.TO_DIG: CollectionResolution(Stage.TO_DIG, "dig", ".ToDig", ".ToDig"),
        Stage.EXPENDABLE: CollectionResolution(Stage.EXPENDABLE, "exp", "Expendable", "Expendable"),
    }


def test_move_tolook_to_revise_preserves_external_collections_and_updates_tags():
    item = ZoteroItemState("I1", Stage.TO_LOOK, ["look", "topic"], ["@look", "#cpt"])
    plan = build_zotero_action_plan(
        item=item,
        collection_action=CollectionAction.MOVE_TO_REVISE,
        recommended_stage=None,
        operational_collections=resolutions(),
        analysis_stage=Stage.TO_LOOK,
        analysis_complete=True,
    )
    assert plan.collections_to_set == ["revise", "topic"]
    assert "@review" in plan.tags_to_add
    assert "@looked_by_llm" in plan.tags_to_add
    assert "@look" in plan.tags_to_remove


def test_move_to_expendable_removes_stage_tags_and_adds_discard_without_operational_tag_when_partial():
    item = ZoteroItemState("I1", Stage.TO_LOOK, ["look"], ["@look"])
    plan = build_zotero_action_plan(
        item=item,
        collection_action=CollectionAction.MOVE_TO_EXPENDABLE,
        recommended_stage=None,
        operational_collections=resolutions(),
        analysis_stage=Stage.TO_LOOK,
        analysis_complete=False,
    )
    assert plan.collections_to_set == ["exp"]
    assert DISCARD_TAG in plan.tags_to_add
    assert "@looked_by_llm" not in plan.tags_to_add
    assert "@look" in plan.tags_to_remove


def test_multiple_operational_collections_blocks_plan():
    item = ZoteroItemState("I1", Stage.TO_LOOK, ["look", "revise"], ["@look"])
    plan = build_zotero_action_plan(
        item=item,
        collection_action=CollectionAction.MOVE_TO_REVISE,
        recommended_stage=None,
        operational_collections=resolutions(),
        analysis_stage=Stage.TO_LOOK,
        analysis_complete=True,
    )
    assert plan.status == "blocked"
    assert plan.reason == "multiple_operational_collections"


def test_repeated_plan_can_be_noop():
    item = ZoteroItemState("I1", Stage.TO_REVISE, ["revise"], ["@review", "@looked_by_llm"])
    plan = build_zotero_action_plan(
        item=item,
        collection_action=CollectionAction.KEEP_CURRENT,
        recommended_stage=Stage.TO_REVISE,
        operational_collections=resolutions(),
        analysis_stage=None,
        analysis_complete=False,
    )
    assert plan.status == "noop"
