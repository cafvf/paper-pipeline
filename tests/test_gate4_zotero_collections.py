import pytest

from paper_pipeline.config import OperationalCollectionsConfig
from paper_pipeline.contracts import Stage, ValidationError
from paper_pipeline.zotero_collections import resolve_operational_collections


class FakeZoteroCollectionsClient:
    def __init__(self, collections):
        self.collections = list(collections)
        self.created = []

    def list_collections(self):
        return list(self.collections)

    def create_collection(self, name, parent_collection=None):
        item = {"key": f"NEW{len(self.created)}", "data": {"name": name, "parentCollection": parent_collection}}
        self.created.append(item)
        self.collections.append(item)
        return item


def collection(key, name):
    return {"key": key, "data": {"name": name}}


def test_resolves_operational_collections_by_name():
    client = FakeZoteroCollectionsClient(
        [
            collection("A", ".ToLook"),
            collection("B", ".To Revise"),
            collection("C", ".ToDig"),
            collection("D", "Expendable"),
        ]
    )
    resolved = resolve_operational_collections(client, OperationalCollectionsConfig())
    assert resolved[Stage.TO_LOOK].collection_key == "A"
    assert resolved[Stage.TO_DIG].name == ".ToDig"
    assert resolved[Stage.EXPENDABLE].created is False


def test_creates_expendable_at_root_when_missing():
    client = FakeZoteroCollectionsClient(
        [
            collection("A", ".ToLook"),
            collection("B", ".To Revise"),
            collection("C", ".ToDig"),
        ]
    )
    resolved = resolve_operational_collections(client, OperationalCollectionsConfig())
    assert resolved[Stage.EXPENDABLE].name == "Expendable"
    assert resolved[Stage.EXPENDABLE].created is True
    assert client.created[0]["data"]["parentCollection"] is None


def test_duplicate_operational_collection_blocks_resolution():
    client = FakeZoteroCollectionsClient(
        [
            collection("A", ".ToLook"),
            collection("AA", ".ToLook"),
            collection("B", ".To Revise"),
            collection("C", ".ToDig"),
            collection("D", "Expendable"),
        ]
    )
    with pytest.raises(ValidationError, match="multiple Zotero collections"):
        resolve_operational_collections(client, OperationalCollectionsConfig())


def test_missing_required_collection_blocks_resolution():
    client = FakeZoteroCollectionsClient([collection("A", ".ToLook"), collection("C", ".ToDig")])
    with pytest.raises(ValidationError, match="missing Zotero collection"):
        resolve_operational_collections(client, OperationalCollectionsConfig(), create_expendable=False)
