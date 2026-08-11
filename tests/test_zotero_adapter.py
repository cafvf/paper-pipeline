from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from paper_triage.audit import AttemptEvidence, AuditLedger
from paper_triage.errors import TriageError
from paper_triage.normalization import normalize_paper
from paper_triage.plans import (
    ApplyRequest,
    ApprovalEvidence,
    PlannedItem,
    PlannedOperation,
    PreviewPlan,
    PreviewVersion,
    Snapshot,
    canonical_sha256,
)
from paper_triage.release_safety import (
    ReleaseAuthorization,
    ReleaseMode,
    ReleaseRequest,
    ValidationEvidence,
    authorize,
)
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


def _release_artifacts(
    *, resource: str = "tag", action: str = "add", ownership_mutation_id: str | None = None
) -> tuple[PreviewPlan, ApplyRequest, ValidationEvidence]:
    target = "#managed" if resource == "tag" else "STAGEKEY"
    items = tuple(
        PlannedItem(
            item_key=f"ITEM{number:02d}",
            source_fingerprint="a" * 64,
            preview_item_version=1,
            classification_projection={},
            operations=(
                PlannedOperation.build(
                    sequence=0,
                    resource_type=resource,
                    action=action,
                    target=target,
                    before_present=action == "remove",
                    after_present=action == "add",
                    version_precondition=PreviewVersion(version=1),
                    ownership_mutation_id=(
                        (ownership_mutation_id or "owned-add") if action == "remove" else None
                    ),
                    reason_codes=(f"test-{number}",),
                ),
            ),
        )
        for number in range(10)
    )
    snapshot = Snapshot(value={}, digest=canonical_sha256({}))
    payload = {
        "preview_id": f"{resource}-preview",
        "created_at": datetime(2026, 8, 11, tzinfo=UTC),
        "run_date": date(2026, 8, 11),
        "selected_item_keys": tuple(item.item_key for item in items),
        "library_scope": {},
        "config_snapshot": snapshot,
        "collection_snapshot": snapshot,
        "project_profile_snapshot": snapshot,
        "ruleset_snapshot": snapshot,
        "taxonomy_snapshot": snapshot,
        "items": items,
        "reviewed_diff_projection": PreviewPlan.reviewed_diff_for(items),
    }
    preview = PreviewPlan(**payload, plan_hash=PreviewPlan.plan_hash_for(**payload))
    operation_ids = tuple(operation.operation_id for item in items for operation in item.operations)
    request = ApplyRequest(
        preview_id=preview.preview_id,
        plan_hash=preview.plan_hash,
        approval=ApprovalEvidence.create(
            approval_id=f"{resource}-approval",
            approved_plan_hash=preview.plan_hash,
            approved_at=datetime(2026, 8, 11, tzinfo=UTC),
            approved_item_keys=preview.selected_item_keys,
            reviewed_operation_ids=operation_ids,
            reviewed_diff_hash=preview.reviewed_diff_hash,
        ),
    )
    validation_evidence = ValidationEvidence.create(plan_hash=preview.plan_hash, checks=("pytest",))
    return preview, request, validation_evidence


def _live_authorization(
    *, resource: str = "tag", action: str = "add", ownership_mutation_id: str | None = None
) -> ReleaseAuthorization:
    preview, request, validation_evidence = _release_artifacts(
        resource=resource, action=action, ownership_mutation_id=ownership_mutation_id
    )
    return authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=True,
            preview_plan=preview,
            apply_request=request,
            validation_evidence=validation_evidence,
        )
    )


def _managed_adapter(
    fake: InMemoryZoteroHttp,
    *,
    resource: str = "tag",
    action: str = "add",
    ledger: AuditLedger | None = None,
    ownership_mutation_id: str | None = None,
) -> ZoteroHttpMutationAdapter:
    return ZoteroHttpMutationAdapter(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        _live_authorization(
            resource=resource, action=action, ownership_mutation_id=ownership_mutation_id
        ),
        transport=fake.read,
        write_transport=fake.write,
        ledger=ledger,
    )


def _approved_command(
    *,
    resource: str = "tag",
    action: str = "add",
    ownership_mutation_id: str | None = None,
    item_key: str = "ITEM01",
    expected_version: int = 1,
) -> ZoteroMutationCommand:
    preview, _request, _validation = _release_artifacts(
        resource=resource, action=action, ownership_mutation_id=ownership_mutation_id
    )
    item = next(value for value in preview.items if value.item_key == item_key)
    operation = item.operations[0]
    return ZoteroMutationCommand(
        operation_id=operation.operation_id,
        idempotency_key=hashlib.sha256(
            f"{preview.plan_hash}:{operation.operation_id}".encode()
        ).hexdigest(),
        item_key=item.item_key,
        expected_version=expected_version,
        resource=operation.resource_type,
        action=operation.action,
        target=operation.target,
        expected_present=operation.before_present,
        desired_present=operation.after_present,
    )

def test_managed_http_mutation_requires_authorization_and_verifies_exact_diff() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human"], collections=["LOOKKEY"]))
    config = ZoteroReadConfig(library_type="users", library_id="123", api_key="token")

    with pytest.raises(PermissionError, match="ReleaseAuthorization"):
        ZoteroHttpMutationAdapter(
            config,
            ReleaseAuthorization(allowed=False, reason="dry run"),
            transport=fake.read,
            write_transport=fake.write,
        )

    adapter = _managed_adapter(fake)
    receipt = adapter.mutate_item(_approved_command())

    assert receipt.accepted_version == 2
    assert receipt.provenance is not None
    assert receipt.provenance.target == "#managed"
    assert fake.writes[0][0].endswith("/items/ITEM01")
    assert fake.writes[0][1]["If-Unmodified-Since-Version"] == "1"
    assert fake.writes[0][1]["Zotero-Write-Token"] == _approved_command().idempotency_key
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

    fake = TamperingZoteroHttp(_item("ITEM01", tags=["#human"]))
    adapter = _managed_adapter(fake)

    with pytest.raises(ZoteroTransportError, match="ZOTERO_EXACT_DIFF_VIOLATION"):
        adapter.mutate_item(_approved_command())


def test_managed_http_mutation_rejects_unmanaged_removal_before_any_write() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human", "#managed"]))
    adapter = _managed_adapter(fake, action="remove", ownership_mutation_id="a" * 64)

    forged = ManagedMutationProvenance(
        operation_id="a" * 64,
        idempotency_key="b" * 64,
        item_key="ITEM01",
        resource="tag",
        target="#managed",
        added_version=1,
    )

    with pytest.raises(PermissionError, match="ledger-derived"):
        adapter.mutate_item(
            replace(
                _approved_command(action="remove", ownership_mutation_id="a" * 64),
                provenance=forged,
            )
        )

    assert fake.writes == []


def test_managed_http_mutation_rejects_forged_provenance_not_present_in_audit_ledger(
    tmp_path: Path,
) -> None:
    """Fake HTTP must not receive a removal when the ledger has no ownership row."""
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human", "#managed"]))
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    adapter = _managed_adapter(
        fake, action="remove", ledger=ledger, ownership_mutation_id="a" * 64
    )
    forged = ManagedMutationProvenance(
        operation_id="a" * 64,
        idempotency_key="b" * 64,
        item_key="ITEM01",
        resource="tag",
        target="#managed",
        added_version=1,
    )

    with pytest.raises(PermissionError, match="ledger authorization"):
        adapter.mutate_item(
            replace(
                _approved_command(action="remove", ownership_mutation_id="a" * 64),
                provenance=forged,
            )
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

    with pytest.raises(PermissionError, match="complete approved operation"):
        adapter.mutate_item(
            ZoteroMutationCommand(
                operation_id="op-1", idempotency_key="id-1", item_key="ITEM0001",
                expected_version=1, resource="tag", action="add", target="#unreviewed",
                expected_present=False, desired_present=True,
            )
        )
    assert fake.writes == []


@pytest.mark.parametrize(
    "change",
    (
        lambda command: replace(command, item_key="ITEM02"),
        lambda command: replace(command, expected_version=2),
        lambda command: replace(
            command, action="remove", expected_present=True, desired_present=False
        ),
    ),
)
def test_managed_http_mutation_requires_the_complete_approved_identity(
    change: Callable[[ZoteroMutationCommand], ZoteroMutationCommand],
) -> None:
    """A reviewed global tag target cannot authorize a substituted command."""
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human"]))
    adapter = _managed_adapter(fake)
    approved = _approved_command()

    with pytest.raises(PermissionError, match="complete approved operation"):
        adapter.mutate_item(change(approved))

    assert fake.writes == []


def test_http_mutation_adapter_captures_complete_fresh_attempt_evidence() -> None:
    fake = InMemoryZoteroHttp(
        _item("ITEM01", version=7, tags=["#human", "#managed"], collections=["LOOKKEY"])
    )
    adapter = _managed_adapter(fake)
    command = _approved_command()

    evidence = adapter.capture_attempt_evidence(
        operation_id=command.operation_id,
        idempotency_key=command.idempotency_key,
        item_key=command.item_key,
        run_date=date(2026, 8, 11),
    )

    assert evidence.operation_id == command.operation_id
    assert evidence.idempotency_key == command.idempotency_key
    assert evidence.item_key == "ITEM01"
    assert evidence.item_version == 7
    assert evidence.tags == ("#human", "#managed")
    assert evidence.collection_keys == ("LOOKKEY",)
    assert set(evidence.preserved_field_hashes) == {"non_membership", "source"}
    assert len(evidence.preserved_field_hashes["non_membership"]) == 64
    expected_source = normalize_paper(
        adapter.read_items(ReadItemsRequest(("ITEM01",)))[0].normalization_mapping(),
        run_date=date(2026, 8, 11),
    ).source_fingerprint
    assert evidence.preserved_field_hashes["source"] == expected_source
    assert fake.writes == []


def test_http_fake_recovery_evidence_keeps_only_non_membership_hash_stable() -> None:
    """A successful tag write remains recoverable while unrelated fields stay locked."""
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human"], collections=["LOOKKEY"]))
    adapter = _managed_adapter(fake)
    command = _approved_command()
    before = adapter.capture_attempt_evidence(
        operation_id=command.operation_id,
        idempotency_key=command.idempotency_key,
        item_key=command.item_key,
        run_date=date(2026, 8, 11),
    )
    payload = dict(fake.row["data"])
    payload["tags"] = [{"tag": "#human"}, {"tag": "#managed"}]
    fake.write("https://api.zotero.org/users/123/items/ITEM01", {}, payload)

    after = adapter.capture_attempt_evidence(
        operation_id=command.operation_id,
        idempotency_key=command.idempotency_key,
        item_key=command.item_key,
        run_date=date(2026, 8, 11),
    )

    assert before.tags == ("#human",)
    assert after.tags == ("#human", "#managed")
    assert before.collection_keys == after.collection_keys == ("LOOKKEY",)
    assert before.preserved_field_hashes == after.preserved_field_hashes


def test_http_mutation_adapter_rejects_a_reread_for_the_wrong_item() -> None:
    fake = InMemoryZoteroHttp(_item("OTHER01"))
    adapter = _managed_adapter(fake)
    command = _approved_command()

    with pytest.raises(ZoteroTransportError, match="unexpected item"):
        adapter.capture_attempt_evidence(
            operation_id=command.operation_id,
            idempotency_key=command.idempotency_key,
            item_key=command.item_key,
            run_date=date(2026, 8, 11),
        )
    assert fake.writes == []


def test_managed_http_mutation_collection_target_must_be_from_snapshot_allowlist() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001", collections=[]))
    adapter = _managed_adapter(fake, resource="collection")
    command = ZoteroMutationCommand(
        operation_id="collection-1", idempotency_key="collection-id", item_key="ITEM0001",
        expected_version=1, resource="collection", action="add", target="OTHERKEY",
        expected_present=False, desired_present=True,
    )
    with pytest.raises(PermissionError, match="complete approved operation"):
        adapter.mutate_item(command)
    assert fake.writes == []


def test_mutation_adapter_rejects_serialized_or_hand_built_capabilities() -> None:
    fake = InMemoryZoteroHttp(_item("ITEM0001"))
    issued = _live_authorization()
    forged = ReleaseAuthorization.model_validate(issued.model_dump())

    with pytest.raises(PermissionError, match="issued, snapshot-bound"):
        ZoteroHttpMutationAdapter(
            ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
            forged,
            transport=fake.read,
            write_transport=fake.write,
        )
    assert fake.writes == []


def test_persisted_release_factory_rejects_write_without_durable_attempt(tmp_path: Path) -> None:
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human"]))
    preview, request, validation_evidence = _release_artifacts()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)

    adapter = ZoteroHttpMutationAdapter.from_persisted_release(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        ledger,
        preview.plan_hash,
        human_approved=True,
        validation_evidence=validation_evidence,
        transport=fake.read,
        write_transport=fake.write,
    )
    with pytest.raises(PermissionError, match="matching durable attempt evidence"):
        adapter.mutate_item(_approved_command())

    assert fake.writes == []


def test_persisted_release_factory_writes_only_after_matching_durable_attempt(
    tmp_path: Path,
) -> None:
    fake = InMemoryZoteroHttp(_item("ITEM01", tags=["#human"]))
    preview, request, validation_evidence = _release_artifacts()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)
    authorization_id = ledger.persist_preview_authorization(preview.plan_hash)
    command = _approved_command()
    ledger.record_attempt(
        authorization_id,
        AttemptEvidence(
            operation_id=command.operation_id,
            idempotency_key=command.idempotency_key,
            item_key=command.item_key,
            item_version=command.expected_version,
            tags=("#human",),
            collection_keys=("LOOKKEY",),
            preserved_field_hashes={"source": "a" * 64, "non_membership": "b" * 64},
        ),
    )
    adapter = ZoteroHttpMutationAdapter.from_persisted_release(
        ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
        ledger,
        preview.plan_hash,
        human_approved=True,
        validation_evidence=validation_evidence,
        transport=fake.read,
        write_transport=fake.write,
    )

    receipt = adapter.mutate_item(command)

    assert receipt.accepted_version == 2
    assert fake.writes


def test_persisted_release_factory_fails_closed_for_missing_plan(tmp_path: Path) -> None:
    preview, _request, validation_evidence = _release_artifacts()

    with pytest.raises(ValueError, match="not persisted"):
        ZoteroHttpMutationAdapter.from_persisted_release(
            ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
            AuditLedger(tmp_path / "audit.sqlite3"),
            preview.plan_hash,
            human_approved=True,
            validation_evidence=validation_evidence,
        )


def test_persisted_release_factory_requires_explicit_human_approval(tmp_path: Path) -> None:
    preview, request, validation_evidence = _release_artifacts()
    ledger = AuditLedger(tmp_path / "audit.sqlite3")
    ledger.persist_preview_request(preview, request)

    with pytest.raises(PermissionError, match="issued, snapshot-bound"):
        ZoteroHttpMutationAdapter.from_persisted_release(
            ZoteroReadConfig(library_type="users", library_id="123", api_key="token"),
            ledger,
            preview.plan_hash,
            human_approved=False,
            validation_evidence=validation_evidence,
        )
