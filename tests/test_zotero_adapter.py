from __future__ import annotations

from dataclasses import replace
from datetime import date
from urllib.error import HTTPError, URLError

import pytest

from paper_triage.errors import TriageError
from paper_triage.release_safety import ReleaseAuthorization
from paper_triage.zotero import (
    DryRunBatch,
    FakeZoteroPort,
    ManagedMutationProvenance,
    ReadCollectionItemsRequest,
    ReadCollectionTreeRequest,
    ReadItemsRequest,
    ZoteroConfigurationError,
    ZoteroHttpMutationAdapter,
    ZoteroHttpReadAdapter,
    ZoteroMutationCommand,
    ZoteroReadConfig,
    ZoteroTransportError,
)


def _item(
    key: str,
    *,
    version: int = 1,
    year: int = 2026,
    collections: list[str] | None = None,
    item_type: str = "journalArticle",
    tags: list[str] | None = None,
    doi: str | None = None,
) -> dict[str, object]:
    return {
        "key": key,
        "version": version,
        "data": {
            "itemType": item_type,
            "title": f"Paper {key}",
            "date": f"{year}-01-01",
            "creators": [{"firstName": "Jane", "lastName": "Doe"}],
            "tags": [{"tag": tag} for tag in (tags or ["#topic"])],
            "collections": collections if collections is not None else ["LOOKKEY"],
            "DOI": doi,
        },
    }


def test_config_is_constructed_only_from_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZOTERO_LIBRARY_TYPE", "users")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "123")
    monkeypatch.setenv("ZOTERO_API_KEY", "secret-value")

    config = ZoteroReadConfig.from_environment()

    assert config.library_type == "users"
    assert config.library_id == "123"
    assert "secret-value" not in repr(config)


def test_http_adapter_maps_read_response_and_never_exposes_token() -> None:
    seen: dict[str, str] = {}

    def transport(url: str, headers: dict[str, str]) -> list[dict[str, object]]:
        seen.update(url=url, **headers)
        return [_item("ITEM0001")]

    adapter = ZoteroHttpReadAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        transport=transport,
    )

    snapshots = adapter.read_items(ReadItemsRequest(item_keys=("ITEM0001",)))

    assert snapshots[0].item_key == "ITEM0001"
    assert snapshots[0].year == 2026
    assert snapshots[0].collections == frozenset({"LOOKKEY"})
    assert seen["url"] == "https://api.zotero.org/users/123/items?itemKey=ITEM0001"
    assert seen["Zotero-API-Key"] == "token"
    assert seen["Zotero-API-Version"] == "3"
    assert "token" not in repr(snapshots[0])
    assert not hasattr(adapter, "mutate_item")


def test_http_errors_are_sanitized() -> None:
    def transport(_: str, __: dict[str, str]) -> list[dict[str, object]]:
        raise HTTPError("https://api.zotero.org", 401, "token should not leak", {}, None)

    adapter = ZoteroHttpReadAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        transport=transport,
    )

    with pytest.raises(ZoteroTransportError, match="HTTP 401") as error:
        adapter.read_items(ReadItemsRequest(item_keys=("ITEM0001",)))

    assert "token" not in str(error.value)


def test_http_adapter_retries_only_transient_read_failures_without_changing_origin() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def transient_transport(url: str, headers: dict[str, str]) -> list[dict[str, object]]:
        calls.append((url, headers))
        if len(calls) < 3:
            raise URLError("temporary outage")
        return [_item("ITEM0001")]

    adapter = ZoteroHttpReadAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        transport=transient_transport,
    )

    assert [item.item_key for item in adapter.read_items(ReadItemsRequest(("ITEM0001",)))] == [
        "ITEM0001"
    ]
    assert len(calls) == 3
    assert {url for url, _ in calls} == {"https://api.zotero.org/users/123/items?itemKey=ITEM0001"}
    assert all(headers["Zotero-API-Key"] == "token" for _, headers in calls)


def test_http_adapter_does_not_retry_permanent_errors_or_accept_path_injection() -> None:
    calls = 0

    def forbidden_transport(_: str, __: dict[str, str]) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        raise HTTPError("https://api.zotero.org", 401, "token must not leak", {}, None)

    adapter = ZoteroHttpReadAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        transport=forbidden_transport,
    )
    with pytest.raises(ZoteroTransportError, match="HTTP 401"):
        adapter.read_items(ReadItemsRequest(("ITEM0001",)))
    assert calls == 1
    with pytest.raises(ValueError, match="invalid"):
        ReadCollectionItemsRequest("LOOKKEY/evil")
    with pytest.raises(ZoteroConfigurationError, match="invalid"):
        ZoteroReadConfig(library_type="users", library_id="123/evil", api_key="token")


def test_timeout_failures_are_sanitized_without_exposing_credentials() -> None:
    def transport(_: str, __: dict[str, str]) -> list[dict[str, object]]:
        raise TimeoutError("timeout while using token")

    adapter = ZoteroHttpReadAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        transport=transport,
    )

    with pytest.raises(ZoteroTransportError, match="transport failed") as error:
        adapter.read_items(ReadItemsRequest(item_keys=("ITEM0001",)))

    assert "token" not in str(error.value)


def test_dry_run_discovers_paginated_tolook_items_and_selects_first_ten_without_mutation() -> None:
    eligible = [_item(f"ITEM{index:04}") for index in range(12, 0, -1)]
    ineligible = [_item(f"OLD{index:05}", year=2025) for index in range(89)]
    fake = FakeZoteroPort(
        [*eligible, *ineligible], collections={"LOOKKEY": ".ToLook", "OTHER": ".ToRevise"}
    )

    result = DryRunBatch(fake).run(run_date=date(2026, 8, 10))

    assert [paper.item_key for paper in result.papers] == [
        f"ITEM{index:04}" for index in range(1, 11)
    ]
    assert fake.mutation_calls == 0
    assert fake.read_requests == []
    assert fake.collection_item_requests == [
        ReadCollectionItemsRequest(collection_key="LOOKKEY", start=0, limit=100),
        ReadCollectionItemsRequest(collection_key="LOOKKEY", start=100, limit=100),
    ]


def test_dry_run_fails_closed_for_ambiguous_or_insufficient_tolook_without_mutation() -> None:
    ambiguous = FakeZoteroPort(
        [_item("ITEM0001")], collections={"LOOKA": ".ToLook", "LOOKB": ".ToLook"}
    )

    with pytest.raises(ValueError, match="exactly one resolved"):
        DryRunBatch(ambiguous).run(run_date=date(2026, 8, 10))

    fake = FakeZoteroPort([_item("ITEM0001")], collections={"LOOKKEY": ".ToLook"})

    with pytest.raises(TriageError, match="LOT_INSUFFICIENT_ELIGIBLE_PAPERS"):
        DryRunBatch(fake).run(run_date=date(2026, 8, 10))

    assert fake.mutation_calls == 0


def test_http_adapter_paginates_collection_tree_and_reads_collection_items() -> None:
    seen: list[str] = []

    def transport(url: str, _: dict[str, str]) -> list[dict[str, object]]:
        seen.append(url)
        if url.endswith("/collections?limit=2&start=0"):
            return [
                {"key": "PARENT", "data": {"name": "Inbox"}},
                {"key": "LOOKKEY", "data": {"name": ".ToLook", "parentCollection": "PARENT"}},
            ]
        if url.endswith("/collections?limit=2&start=2"):
            return [{"key": "OTHER", "data": {"name": ".ToRevise"}}]
        if url.endswith("/collections/LOOKKEY/items?limit=2&start=0"):
            return [_item("ITEM0001")]
        raise AssertionError(f"unexpected URL: {url}")

    adapter = ZoteroHttpReadAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        transport=transport,
    )

    tree = adapter.read_collection_tree(ReadCollectionTreeRequest(page_size=2))
    items = adapter.read_collection_items(ReadCollectionItemsRequest("LOOKKEY", limit=2))

    assert tree.collections == {"PARENT": "Inbox", "LOOKKEY": ".ToLook", "OTHER": ".ToRevise"}
    assert [item.item_key for item in items] == ["ITEM0001"]
    assert seen == [
        "https://api.zotero.org/users/123/collections?limit=2&start=0",
        "https://api.zotero.org/users/123/collections?limit=2&start=2",
        "https://api.zotero.org/users/123/collections/LOOKKEY/items?limit=2&start=0",
    ]


class InMemoryZoteroHttp:
    """Small HTTP-shaped fake: reads expose snapshots and writes replace item data."""

    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.writes: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def read(self, _: str, __: dict[str, str]) -> list[dict[str, object]]:
        return [self.row]

    def write(
        self, url: str, headers: dict[str, str], payload: dict[str, object]
    ) -> tuple[int, str]:
        self.writes.append((url, headers, payload))
        self.row = {
            "key": self.row["key"],
            "version": int(self.row["version"]) + 1,
            "data": payload,
        }
        return (204, "write-1")


def _live_authorization() -> ReleaseAuthorization:
    return ReleaseAuthorization(
        allowed=True,
        reason="test-only release authorization",
        plan_hash="a" * 64,
        approval_confirmation_digest="b" * 64,
        validation_digest="c" * 64,
    )


def _managed_adapter(fake: InMemoryZoteroHttp, **kwargs: object) -> ZoteroHttpMutationAdapter:
    return ZoteroHttpMutationAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        _live_authorization(),
        transport=fake.read,
        write_transport=fake.write,
        allowed_tag_targets=frozenset({"#managed"}),
        **kwargs,
    )


def test_managed_http_mutation_requires_authorization_and_verifies_exact_diff() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001", tags=["#human"], collections=["LOOKKEY"]))
    config = ZoteroReadConfig(library_type="users", library_id="123", api_key="token")

    with pytest.raises(PermissionError, match="ReleaseAuthorization"):
        ZoteroHttpMutationAdapter(
            config,
            ReleaseAuthorization(allowed=False, reason="dry run"),
            transport=fake.read,
            write_transport=fake.write,
        )

    adapter = _managed_adapter(fake)
    receipt = adapter.mutate_item(
        ZoteroMutationCommand(
            operation_id="op-1",
            idempotency_key="idempotency-1",
            item_key="ITEM0001",
            expected_version=1,
            resource="tag",
            action="add",
            target="#managed",
            expected_present=False,
            desired_present=True,
        )
    )

    assert receipt.accepted_version == 2
    assert receipt.provenance is not None
    assert receipt.provenance.target == "#managed"
    assert fake.writes[0][0].endswith("/items/ITEM0001")
    assert fake.writes[0][1]["If-Unmodified-Since-Version"] == "1"
    assert fake.writes[0][1]["Zotero-Write-Token"] == "idempotency-1"
    assert {tag["tag"] for tag in fake.writes[0][2]["tags"]} == {"#human", "#managed"}


def test_managed_http_mutation_rejects_changes_to_unrelated_item_data() -> None:
    class TamperingZoteroHttp(InMemoryZoteroHttp):
        def write(
            self, url: str, headers: dict[str, str], payload: dict[str, object]
        ) -> tuple[int, str]:
            status, request_id = super().write(url, headers, payload)
            data = self.row["data"]
            assert isinstance(data, dict)
            data["extra"] = "unexpected external change"
            return status, request_id

    fake = TamperingZoteroHttp(_item("ITEM0001", tags=["#human"]))
    adapter = _managed_adapter(fake)

    with pytest.raises(ZoteroTransportError, match="ZOTERO_EXACT_DIFF_VIOLATION"):
        adapter.mutate_item(
            ZoteroMutationCommand(
                operation_id="op-1",
                idempotency_key="idempotency-1",
                item_key="ITEM0001",
                expected_version=1,
                resource="tag",
                action="add",
                target="#managed",
                expected_present=False,
                desired_present=True,
            )
        )


def test_managed_http_mutation_rejects_unmanaged_removal_and_external_change() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001", version=2, tags=["#human", "#managed"]))
    adapter = _managed_adapter(fake)
    command = ZoteroMutationCommand(
        operation_id="remove-1",
        idempotency_key="idempotency-2",
        item_key="ITEM0001",
        expected_version=2,
        resource="tag",
        action="remove",
        target="#managed",
        expected_present=True,
        desired_present=False,
    )
    with pytest.raises(PermissionError, match="managed provenance"):
        adapter.mutate_item(command)

    provenance = ManagedMutationProvenance(
        operation_id="add-1",
        idempotency_key="idempotency-add",
        item_key="ITEM0001",
        resource="tag",
        target="#managed",
        added_version=2,
    )
    fake.row["version"] = 3  # Any outside advancement breaks the ownership lineage.
    with pytest.raises(ZoteroTransportError, match="superseded"):
        adapter.mutate_item(
            replace(command, expected_version=3, provenance=provenance)
        )
    assert fake.writes == []


@pytest.mark.parametrize("target", ["$advisory", "!flag", "plain", "#bad/evil"])
def test_managed_http_mutation_allows_only_canonical_writable_tag_targets(target: str) -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001"))
    adapter = _managed_adapter(fake)
    with pytest.raises(ValueError, match="canonical"):
        adapter.mutate_item(
            ZoteroMutationCommand(
                operation_id="op-1", idempotency_key="id-1", item_key="ITEM0001",
                expected_version=1, resource="tag", action="add", target=target,
                expected_present=False, desired_present=True,
            )
        )
    assert fake.writes == []


def test_managed_http_mutation_rejects_canonical_tag_outside_snapshot_allowlist() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001"))
    adapter = _managed_adapter(fake)

    with pytest.raises(PermissionError, match="snapshot allowlist"):
        adapter.mutate_item(
            ZoteroMutationCommand(
                operation_id="op-1", idempotency_key="id-1", item_key="ITEM0001",
                expected_version=1, resource="tag", action="add", target="#unreviewed",
                expected_present=False, desired_present=True,
            )
        )
    assert fake.writes == []


def test_managed_http_mutation_collection_target_must_be_from_snapshot_allowlist() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001", collections=[]))
    adapter = _managed_adapter(fake, allowed_collection_keys=frozenset({"STAGEKEY"}))
    command = ZoteroMutationCommand(
        operation_id="collection-1", idempotency_key="collection-id", item_key="ITEM0001",
        expected_version=1, resource="collection", action="add", target="OTHERKEY",
        expected_present=False, desired_present=True,
    )
    with pytest.raises(PermissionError, match="snapshot allowlist"):
        adapter.mutate_item(command)
    assert fake.writes == []
