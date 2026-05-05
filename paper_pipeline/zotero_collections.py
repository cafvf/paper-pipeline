from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import OperationalCollectionsConfig
from .contracts import Stage, ValidationError


class ZoteroCollectionsClient(Protocol):
    def list_collections(self) -> list[dict]: ..

    def create_collection(self, name: str, parent_collection: str | None = None) -> dict: ..


@dataclass(frozen=True)
class CollectionResolution:
    stage: Stage
    collection_key: str
    name: str
    matched_alias: str
    created: bool = False


def resolve_operational_collections(
    client: ZoteroCollectionsClient,
    config: OperationalCollectionsConfig,
    *,
    create_expendable: bool = True,
) -> dict[Stage, CollectionResolution]:
    collections = client.list_collections()
    resolved: dict[Stage, CollectionResolution] = {}
    alias_map = {
        Stage.TO_LOOK: config.tolook,
        Stage.TO_REVISE: config.torevise,
        Stage.TO_DIG: config.todig,
        Stage.EXPENDABLE: config.expendable,
    }
    for stage, aliases in alias_map.items():
        matches = _find_matches(collections, aliases)
        if len(matches) > 1:
            names = ", ".join(_collection_name(item) for item in matches)
            raise ValidationError(f"multiple Zotero collections match {stage.value}: {names}")
        if not matches and stage == Stage.EXPENDABLE and create_expendable:
            created = client.create_collection("Expendable", parent_collection=None)
            resolved[stage] = CollectionResolution(
                stage=stage,
                collection_key=str(created.get("key")),
                name=_collection_name(created),
                matched_alias="Expendable",
                created=True,
            )
            continue
        if not matches:
            raise ValidationError(f"missing Zotero collection for {stage.value}")
        item = matches[0]
        resolved[stage] = CollectionResolution(
            stage=stage,
            collection_key=str(item.get("key")),
            name=_collection_name(item),
            matched_alias=_matched_alias(item, aliases),
            created=False,
        )
    return resolved


def _find_matches(collections: list[dict], aliases: list[str]) -> list[dict]:
    normalized_aliases = {_normalize(alias) for alias in aliases}
    return [item for item in collections if _normalize(_collection_name(item)) in normalized_aliases]


def _matched_alias(item: dict, aliases: list[str]) -> str:
    name = _normalize(_collection_name(item))
    for alias in aliases:
        if _normalize(alias) == name:
            return alias
    return _collection_name(item)


def _collection_name(item: dict) -> str:
    data = item.get("data", {}) if isinstance(item.get("data"), dict) else {}
    return str(data.get("name") or item.get("name") or "")


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())
