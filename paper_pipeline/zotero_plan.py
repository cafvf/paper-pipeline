from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    DISCARD_TAG,
    OPERATIONAL_LLM_TAGS,
    STAGE_TAGS,
    CollectionAction,
    Stage,
    ValidationError,
    stage_from_collection_action,
)
from .zotero_collections import CollectionResolution


@dataclass(frozen=True)
class ZoteroItemState:
    item_key: str
    current_stage: Stage
    collection_keys: list[str]
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ZoteroActionPlan:
    item_key: str
    current_stage: Stage
    target_stage: Stage | None
    collection_action: CollectionAction
    collections_to_set: list[str]
    tags_to_add: list[str]
    tags_to_remove: list[str]
    final_tags: list[str]
    status: str
    reason: str = ""


def build_zotero_action_plan(
    *,
    item: ZoteroItemState,
    collection_action: CollectionAction,
    recommended_stage: Stage | None,
    operational_collections: dict[Stage, CollectionResolution],
    analysis_stage: Stage | None,
    analysis_complete: bool,
    recommended_tags_add: list[str] | None = None,
    recommended_tags_remove: list[str] | None = None,
) -> ZoteroActionPlan:
    target_stage = stage_from_collection_action(collection_action, recommended_stage)
    operational_keys = {resolution.collection_key for resolution in operational_collections.values()}
    current_operational = [key for key in item.collection_keys if key in operational_keys]
    if len(current_operational) > 1:
        return _blocked(item, target_stage, collection_action, "multiple_operational_collections")

    if collection_action in {CollectionAction.NO_COLLECTION_CHANGE, CollectionAction.MANUAL_ONLY}:
        target_stage = None

    collections_to_set = _planned_collections(item, target_stage, operational_collections)
    tags_to_add, tags_to_remove, final_tags = _planned_tags(
        item=item,
        target_stage=target_stage,
        analysis_stage=analysis_stage,
        analysis_complete=analysis_complete,
        recommended_tags_add=recommended_tags_add or [],
        recommended_tags_remove=recommended_tags_remove or [],
    )
    status = "noop"
    if sorted(collections_to_set) != sorted(item.collection_keys) or tags_to_add or tags_to_remove:
        status = "planned"
    return ZoteroActionPlan(
        item_key=item.item_key,
        current_stage=item.current_stage,
        target_stage=target_stage,
        collection_action=collection_action,
        collections_to_set=collections_to_set,
        tags_to_add=tags_to_add,
        tags_to_remove=tags_to_remove,
        final_tags=final_tags,
        status=status,
    )


def _planned_collections(
    item: ZoteroItemState,
    target_stage: Stage | None,
    operational_collections: dict[Stage, CollectionResolution],
) -> list[str]:
    operational_keys = {resolution.collection_key for resolution in operational_collections.values()}
    preserved = [key for key in item.collection_keys if key not in operational_keys]
    if target_stage is None:
        return sorted(preserved + [key for key in item.collection_keys if key in operational_keys])
    target = operational_collections.get(target_stage)
    if target is None:
        raise ValidationError(f"missing collection resolution for {target_stage.value}")
    return sorted(preserved + [target.collection_key])


def _planned_tags(
    *,
    item: ZoteroItemState,
    target_stage: Stage | None,
    analysis_stage: Stage | None,
    analysis_complete: bool,
    recommended_tags_add: list[str],
    recommended_tags_remove: list[str],
) -> tuple[list[str], list[str], list[str]]:
    current = [tag for tag in item.tags if tag]
    final = set(current)
    remove = set(recommended_tags_remove)
    add = set(recommended_tags_add)

    if target_stage in {Stage.TO_LOOK, Stage.TO_REVISE, Stage.TO_DIG, Stage.EXPENDABLE}:
        for tag in STAGE_TAGS.values():
            if tag in final:
                remove.add(tag)
                final.discard(tag)
        if target_stage == Stage.EXPENDABLE:
            add.add(DISCARD_TAG)
        elif target_stage in STAGE_TAGS:
            add.add(STAGE_TAGS[target_stage])

    if analysis_complete and analysis_stage in OPERATIONAL_LLM_TAGS:
        add.add(OPERATIONAL_LLM_TAGS[analysis_stage])

    for tag in remove:
        final.discard(tag)
    final.update(add)
    tags_to_add = sorted(tag for tag in final if tag not in current)
    tags_to_remove = sorted(tag for tag in current if tag not in final)
    return tags_to_add, tags_to_remove, sorted(final)


def _blocked(
    item: ZoteroItemState,
    target_stage: Stage | None,
    collection_action: CollectionAction,
    reason: str,
) -> ZoteroActionPlan:
    return ZoteroActionPlan(
        item_key=item.item_key,
        current_stage=item.current_stage,
        target_stage=target_stage,
        collection_action=collection_action,
        collections_to_set=list(item.collection_keys),
        tags_to_add=[],
        tags_to_remove=[],
        final_tags=list(item.tags),
        status="blocked",
        reason=reason,
    )
