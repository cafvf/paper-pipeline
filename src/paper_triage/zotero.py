"""Narrow Zotero port contracts with explicit read and release-gated write adapters."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from http.client import HTTPMessage
from typing import IO, Any, Literal, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .normalization import normalize_paper
from .release_safety import ReleaseAuthorization
from .selection import select_first_real_lot

_API_ROOT = "https://api.zotero.org"
_LIBRARY_TYPES = frozenset({"users", "groups"})
_LIBRARY_ID = re.compile(r"^[0-9]+$")
_ZOTERO_KEY = re.compile(r"^[A-Za-z0-9]{1,32}$")
_READ_TIMEOUT_SECONDS = 15
_MAX_READ_ATTEMPTS = 3


class ZoteroConfigurationError(ValueError):
    """Raised for invalid runtime-only adapter configuration."""


class ZoteroTransportError(RuntimeError):
    """Sanitized connector failure that never includes headers or response bodies."""


@dataclass(frozen=True)
class ZoteroReadConfig:
    """Configuration supplied at construction, normally via process environment."""

    library_type: Literal["users", "groups"]
    library_id: str
    api_key: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.library_type not in _LIBRARY_TYPES
            or not _LIBRARY_ID.fullmatch(self.library_id)
            or not self.api_key
        ):
            raise ZoteroConfigurationError("Zotero read configuration is incomplete or invalid")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> ZoteroReadConfig:
        values = os.environ if environ is None else environ
        library_type = values.get("ZOTERO_LIBRARY_TYPE", "users")
        library_id = values.get("ZOTERO_LIBRARY_ID", "")
        api_key = values.get("ZOTERO_API_KEY", "")
        if library_type not in _LIBRARY_TYPES or not library_id or not api_key:
            raise ZoteroConfigurationError(
                "ZOTERO_LIBRARY_TYPE, ZOTERO_LIBRARY_ID, and ZOTERO_API_KEY are required"
            )
        return cls(
            library_type=cast(Literal["users", "groups"], library_type),
            library_id=library_id,
            api_key=api_key,
        )


@dataclass(frozen=True)
class ReadItemsRequest:
    item_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.item_keys or len(set(self.item_keys)) != len(self.item_keys):
            raise ValueError("item keys must be non-empty and unique")


@dataclass(frozen=True)
class ReadCollectionTreeRequest:
    """Read the complete collection tree in bounded, read-only pages."""

    page_size: int = 100

    def __post_init__(self) -> None:
        if self.page_size < 1 or self.page_size > 100:
            raise ValueError("collection tree page size must be between 1 and 100")


@dataclass(frozen=True)
class ReadCollectionItemsRequest:
    """Read one read-only page of items belonging to a resolved collection key."""

    collection_key: str
    start: int = 0
    limit: int = 100

    def __post_init__(self) -> None:
        if (
            not _ZOTERO_KEY.fullmatch(self.collection_key)
            or self.start < 0
            or self.limit < 1
            or self.limit > 100
        ):
            raise ValueError("collection item request is invalid")


@dataclass(frozen=True)
class CollectionTreeSnapshot:
    library_id: str
    collections: Mapping[str, str]


@dataclass(frozen=True)
class ZoteroItemSnapshot:
    library_id: str
    item_key: str
    item_version: int
    raw_item_type: str
    title: str
    creators: tuple[Mapping[str, Any], ...]
    year: int | None
    doi: str | None
    venue: str | None
    abstract: str | None
    tags: frozenset[str]
    collections: frozenset[str]
    preserved_fields_hash: str
    raw_data_json: str = field(repr=False)

    def normalization_mapping(self) -> dict[str, Any]:
        return {
            "library_id": self.library_id,
            "item_key": self.item_key,
            "item_version": self.item_version,
            "raw_item_type": self.raw_item_type,
            "title": self.title,
            "authors": tuple(
                {
                    "family": creator.get("lastName"),
                    "given": creator.get("firstName"),
                    "literal": creator.get("name"),
                }
                for creator in self.creators
            ),
            "year": self.year,
            "doi": self.doi,
            "venue": self.venue,
            "abstract": self.abstract,
            "collections": self.collections,
            "tags": self.tags,
        }


@dataclass(frozen=True)
class ZoteroMutationCommand:
    operation_id: str
    idempotency_key: str
    item_key: str
    expected_version: int
    resource: Literal["tag", "collection"]
    action: Literal["add", "remove"]
    target: str
    expected_present: bool
    desired_present: bool
    provenance: ManagedMutationProvenance | None = None


@dataclass(frozen=True)
class ManagedMutationProvenance:
    """Durable evidence required before this adapter will remove managed state.

    Callers persist this value in their mutation ledger after a verified add.
    Matching the last app-observed version prevents a later human/external edit
    from being mistaken for application-owned state.
    """

    operation_id: str
    idempotency_key: str
    item_key: str
    resource: Literal["tag", "collection"]
    target: str
    added_version: int


@dataclass(frozen=True)
class ZoteroMutationReceipt:
    item_key: str
    accepted_version: int
    request_id: str
    provenance: ManagedMutationProvenance | None = None


class ZoteroReadPort(Protocol):
    def read_items(self, request: ReadItemsRequest) -> list[ZoteroItemSnapshot]: ...

    def read_collection_tree(
        self, request: ReadCollectionTreeRequest
    ) -> CollectionTreeSnapshot: ...

    def read_collection_items(
        self, request: ReadCollectionItemsRequest
    ) -> list[ZoteroItemSnapshot]: ...


class ZoteroMutationPort(ZoteroReadPort, Protocol):
    def mutate_item(self, command: ZoteroMutationCommand) -> ZoteroMutationReceipt: ...


Transport = Callable[[str, dict[str, str]], list[dict[str, object]]]
WriteTransport = Callable[[str, dict[str, str], dict[str, object]], tuple[int, str]]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
        new_url: str,
    ) -> None:
        del request, response, code, message, headers, new_url


def _is_allowlisted_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.netloc == "api.zotero.org" and not parsed.username


def _http_get(url: str, headers: dict[str, str]) -> list[dict[str, object]]:
    if not _is_allowlisted_url(url):
        raise ZoteroTransportError("Zotero read URL is not allowlisted")
    request = Request(url, headers=headers, method="GET")
    try:
        # Redirects are errors: credentials must never be forwarded to another origin.
        with build_opener(_NoRedirect()).open(request, timeout=_READ_TIMEOUT_SECONDS) as response:
            decoded = json.load(response)
    except HTTPError as error:
        raise ZoteroTransportError(f"Zotero read failed with HTTP {error.code}") from None
    except (URLError, TimeoutError):
        raise ZoteroTransportError("Zotero read transport failed") from None
    if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
        raise ZoteroTransportError("Zotero read returned an unexpected response shape")
    return decoded


class ZoteroHttpReadAdapter:
    """Concrete GET-only Zotero Web API client; it deliberately has no write method."""

    def __init__(self, config: ZoteroReadConfig, *, transport: Transport = _http_get) -> None:
        self._config = config
        self._transport = transport

    @property
    def _base_url(self) -> str:
        return f"{_API_ROOT}/{self._config.library_type}/{self._config.library_id}"

    def _get(self, path: str, query: Mapping[str, str] | None = None) -> list[dict[str, object]]:
        suffix = f"?{urlencode(query)}" if query else ""
        url = f"{self._base_url}{path}{suffix}"
        if not _is_allowlisted_url(url):
            raise ZoteroTransportError("Zotero read URL is not allowlisted")
        headers = {"Zotero-API-Key": self._config.api_key, "Zotero-API-Version": "3"}
        for attempt in range(_MAX_READ_ATTEMPTS):
            try:
                return self._transport(url, headers)
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == _MAX_READ_ATTEMPTS - 1:
                    raise ZoteroTransportError(
                        f"Zotero read failed with HTTP {error.code}"
                    ) from None
            except (URLError, TimeoutError):
                if attempt == _MAX_READ_ATTEMPTS - 1:
                    raise ZoteroTransportError("Zotero read transport failed") from None
        raise AssertionError("bounded retry loop must return or raise")

    def read_items(self, request: ReadItemsRequest) -> list[ZoteroItemSnapshot]:
        response = self._get("/items", {"itemKey": ",".join(request.item_keys)})
        snapshots = [_snapshot_from_response(self._config.library_id, item) for item in response]
        wanted = set(request.item_keys)
        return [snapshot for snapshot in snapshots if snapshot.item_key in wanted]

    def read_collection_tree(self, request: ReadCollectionTreeRequest) -> CollectionTreeSnapshot:
        rows: list[dict[str, object]] = []
        start = 0
        while True:
            page = self._get("/collections", {"limit": str(request.page_size), "start": str(start)})
            rows.extend(page)
            if len(page) < request.page_size:
                break
            start += request.page_size
        collections: dict[str, str] = {}
        for row in rows:
            data = row.get("data")
            key = row.get("key")
            if (
                isinstance(data, dict)
                and isinstance(key, str)
                and isinstance(data.get("name"), str)
            ):
                collections[key] = data["name"]
        return CollectionTreeSnapshot(library_id=self._config.library_id, collections=collections)

    def read_collection_items(
        self, request: ReadCollectionItemsRequest
    ) -> list[ZoteroItemSnapshot]:
        response = self._get(
            f"/collections/{request.collection_key}/items",
            {"limit": str(request.limit), "start": str(request.start)},
        )
        return [_snapshot_from_response(self._config.library_id, item) for item in response]


def _http_put(
    url: str, headers: dict[str, str], payload: dict[str, object]
) -> tuple[int, str]:
    """Perform one allowlisted Zotero write without exposing response content."""

    if not _is_allowlisted_url(url):
        raise ZoteroTransportError("Zotero write URL is not allowlisted")
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=_READ_TIMEOUT_SECONDS) as response:
            return int(response.status), str(response.headers.get("Request-Id", ""))
    except HTTPError as error:
        raise ZoteroTransportError(f"Zotero write failed with HTTP {error.code}") from None
    except (URLError, TimeoutError):
        raise ZoteroTransportError("Zotero write transport failed") from None


class ZoteroHttpMutationAdapter(ZoteroHttpReadAdapter):
    """Release-gated, single-membership Zotero mutation adapter.

    It fetches immediately before and after each write, uses Zotero's optimistic
    version precondition, and accepts a write only when the complete DTO differs
    solely by the requested tag or existing collection membership.  The separate
    class intentionally keeps ``ZoteroHttpReadAdapter`` incapable of mutation.
    """

    def __init__(
        self,
        config: ZoteroReadConfig,
        authorization: ReleaseAuthorization,
        *,
        transport: Transport = _http_get,
        write_transport: WriteTransport = _http_put,
        allowed_collection_keys: frozenset[str] = frozenset(),
    ) -> None:
        if not authorization.allowed:
            raise PermissionError("ReleaseAuthorization does not permit Zotero mutation")
        super().__init__(config, transport=transport)
        self._write_transport = write_transport
        self._allowed_collection_keys = allowed_collection_keys

    def mutate_item(self, command: ZoteroMutationCommand) -> ZoteroMutationReceipt:
        self._validate_command(command)
        if (
            command.resource == "collection"
            and command.target not in self._allowed_collection_keys
        ):
            raise PermissionError("Zotero collection mutation target is not in the snapshot allowlist")
        before_row = self._read_single_raw_item(command.item_key)
        before = _snapshot_from_response(self._config.library_id, before_row)
        if before.item_version != command.expected_version:
            raise ZoteroTransportError("Zotero item is stale before mutation")
        before_membership = self._membership(before, command.resource)
        if (command.target in before_membership) != command.expected_present:
            raise ZoteroTransportError("Zotero item membership is stale before mutation")
        if command.action == "remove":
            self._validate_removal_provenance(command)

        data = before_row.get("data")
        if not isinstance(data, Mapping):
            raise ZoteroTransportError("Zotero item response is incomplete")
        payload = dict(data)
        self._set_membership(payload, command)
        headers = {
            "Zotero-API-Key": self._config.api_key,
            "Zotero-API-Version": "3",
            "If-Unmodified-Since-Version": str(command.expected_version),
            "Zotero-Write-Token": command.idempotency_key,
        }
        status, request_id = self._write_transport(
            f"{self._base_url}/items/{command.item_key}", headers, payload
        )
        if status not in {200, 204}:
            raise ZoteroTransportError(f"Zotero write failed with HTTP {status}")

        after = _snapshot_from_response(
            self._config.library_id, self._read_single_raw_item(command.item_key)
        )
        if not self._is_exact_membership_diff(before, after, command):
            raise ZoteroTransportError("ZOTERO_EXACT_DIFF_VIOLATION")
        provenance = (
            ManagedMutationProvenance(
                operation_id=command.operation_id,
                idempotency_key=command.idempotency_key,
                item_key=command.item_key,
                resource=command.resource,
                target=command.target,
                added_version=after.item_version,
            )
            if command.action == "add"
            else None
        )
        return ZoteroMutationReceipt(
            command.item_key, after.item_version, request_id, provenance=provenance
        )

    def _read_single_raw_item(self, item_key: str) -> dict[str, object]:
        # ``itemKey`` deliberately uses the list endpoint, whose response shape
        # is stable and shared with the read adapter (unlike an item-detail GET).
        rows = self._get("/items", {"itemKey": item_key})
        if len(rows) != 1:
            raise ZoteroTransportError("Zotero item reread did not return exactly one item")
        return rows[0]

    @staticmethod
    def _membership(item: ZoteroItemSnapshot, resource: str) -> frozenset[str]:
        return item.tags if resource == "tag" else item.collections

    @staticmethod
    def _validate_command(command: ZoteroMutationCommand) -> None:
        if (
            not command.operation_id
            or not command.idempotency_key
            or not _ZOTERO_KEY.fullmatch(command.item_key)
            or command.expected_version < 0
            or command.expected_present == command.desired_present
        ):
            raise ValueError("Zotero mutation command is invalid")
        if command.resource == "tag":
            if not command.target.startswith(("#", "%", "@")) or len(command.target) < 2:
                raise ValueError("Zotero mutations require canonical writable tag targets")
            if any(character in command.target for character in ("/", "\n", "\r")):
                raise ValueError("Zotero mutations require canonical writable tag targets")
        elif not _ZOTERO_KEY.fullmatch(command.target):
            raise ValueError("Zotero collection mutation target is invalid")
        if command.action == "add" and (command.expected_present or not command.desired_present):
            raise ValueError("Zotero add command has inconsistent membership expectation")
        if command.action == "remove" and (not command.expected_present or command.desired_present):
            raise ValueError("Zotero remove command has inconsistent membership expectation")

    @staticmethod
    def _validate_removal_provenance(command: ZoteroMutationCommand) -> None:
        provenance = command.provenance
        if provenance is None:
            raise PermissionError("Zotero removal requires verified managed provenance")
        if (
            provenance.item_key != command.item_key
            or provenance.resource != command.resource
            or provenance.target != command.target
            or provenance.added_version != command.expected_version
        ):
            raise ZoteroTransportError("managed provenance is superseded")

    @staticmethod
    def _set_membership(payload: dict[str, object], command: ZoteroMutationCommand) -> None:
        if command.resource == "tag":
            raw_tags = payload.get("tags", ())
            tags = raw_tags if isinstance(raw_tags, (list, tuple)) else ()
            current_tags = {
                tag["tag"]: dict(tag)
                for tag in tags
                if isinstance(tag, Mapping) and isinstance(tag.get("tag"), str)
            }
            if command.desired_present:
                current_tags[command.target] = {"tag": command.target}
            else:
                current_tags.pop(command.target, None)
            payload["tags"] = [current_tags[tag] for tag in sorted(current_tags)]
            return
        raw_collections = payload.get("collections", ())
        collections = raw_collections if isinstance(raw_collections, (list, tuple)) else ()
        current_collections = {key for key in collections if isinstance(key, str)}
        if command.desired_present:
            current_collections.add(command.target)
        else:
            current_collections.discard(command.target)
        payload["collections"] = sorted(current_collections)

    @classmethod
    def _is_exact_membership_diff(
        cls, before: ZoteroItemSnapshot, after: ZoteroItemSnapshot, command: ZoteroMutationCommand
    ) -> bool:
        if after.item_version <= before.item_version:
            return False
        if before.library_id != after.library_id or before.item_key != after.item_key:
            return False
        before_membership = cls._membership(before, command.resource)
        after_membership = cls._membership(after, command.resource)
        if after_membership != (
            before_membership | {command.target}
            if command.desired_present
            else before_membership - {command.target}
        ):
            return False
        if not cls._target_membership_is_exact(after, command):
            return False
        return cls._payload_without_target(before, command) == cls._payload_without_target(
            after, command
        )

    @staticmethod
    def _target_membership_is_exact(item: ZoteroItemSnapshot, command: ZoteroMutationCommand) -> bool:
        data = json.loads(item.raw_data_json)
        if command.resource == "tag":
            tags = data.get("tags", ())
            if not isinstance(tags, list):
                return False
            matching = [tag for tag in tags if isinstance(tag, dict) and tag.get("tag") == command.target]
            return matching == ([{"tag": command.target}] if command.desired_present else [])
        collections = data.get("collections", ())
        if not isinstance(collections, list):
            return False
        return collections.count(command.target) == int(command.desired_present)

    @staticmethod
    def _payload_without_target(item: ZoteroItemSnapshot, command: ZoteroMutationCommand) -> str:
        data = json.loads(item.raw_data_json)
        if command.resource == "tag":
            tags = data.get("tags", ())
            if not isinstance(tags, list):
                return ""
            data["tags"] = [
                tag
                for tag in tags
                if not (isinstance(tag, dict) and tag.get("tag") == command.target)
            ]
        else:
            collections = data.get("collections", ())
            if not isinstance(collections, list):
                return ""
            data["collections"] = [key for key in collections if key != command.target]
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_from_response(library_id: str, row: Mapping[str, object]) -> ZoteroItemSnapshot:
    data = row.get("data")
    key = row.get("key")
    version = row.get("version", 0)
    if not isinstance(data, Mapping) or not isinstance(key, str) or not isinstance(version, int):
        raise ZoteroTransportError("Zotero item response is incomplete")
    tags = frozenset(
        tag["tag"]
        for tag in data.get("tags", ())
        if isinstance(tag, Mapping) and isinstance(tag.get("tag"), str)
    )
    creators = tuple(
        creator for creator in data.get("creators", ()) if isinstance(creator, Mapping)
    )
    raw_date = data.get("date")
    year = int(str(raw_date)[:4]) if str(raw_date)[:4].isdigit() else None
    stable_raw = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return ZoteroItemSnapshot(
        library_id=library_id,
        item_key=key,
        item_version=version,
        raw_item_type=str(data.get("itemType", "unknown")),
        title=str(data.get("title", "")),
        creators=creators,
        year=year,
        doi=data.get("DOI") if isinstance(data.get("DOI"), str) else None,
        venue=data.get("publicationTitle")
        if isinstance(data.get("publicationTitle"), str)
        else None,
        abstract=data.get("abstractNote") if isinstance(data.get("abstractNote"), str) else None,
        tags=tags,
        collections=frozenset(
            str(value) for value in data.get("collections", ()) if isinstance(value, str)
        ),
        preserved_fields_hash=hashlib.sha256(stable_raw.encode("utf-8")).hexdigest(),
        raw_data_json=stable_raw,
    )


class FakeZoteroPort:
    """In-memory contract fake used to prove preview paths cannot mutate."""

    def __init__(
        self,
        items: Iterable[Mapping[str, object]],
        *,
        library_id: str = "test-library",
        collections: Mapping[str, str] | None = None,
    ) -> None:
        self._items = [_snapshot_from_response(library_id, item) for item in items]
        self._library_id = library_id
        self._collections = dict(collections or {})
        self.read_requests: list[ReadItemsRequest] = []
        self.collection_item_requests: list[ReadCollectionItemsRequest] = []
        self.mutation_calls = 0

    def read_items(self, request: ReadItemsRequest) -> list[ZoteroItemSnapshot]:
        self.read_requests.append(request)
        requested = set(request.item_keys)
        return [item for item in self._items if item.item_key in requested]

    def read_collection_tree(self, request: ReadCollectionTreeRequest) -> CollectionTreeSnapshot:
        del request
        return CollectionTreeSnapshot(library_id=self._library_id, collections=self._collections)

    def read_collection_items(
        self, request: ReadCollectionItemsRequest
    ) -> list[ZoteroItemSnapshot]:
        self.collection_item_requests.append(request)
        members = sorted(
            (item for item in self._items if request.collection_key in item.collections),
            key=lambda item: item.item_key,
        )
        return members[request.start : request.start + request.limit]

    def mutate_item(self, command: ZoteroMutationCommand) -> ZoteroMutationReceipt:
        self.mutation_calls += 1
        return ZoteroMutationReceipt(command.item_key, command.expected_version + 1, "fake-request")


@dataclass(frozen=True)
class DryRunResult:
    papers: tuple[Any, ...]


class DryRunBatch:
    """Read-only discovery and preflight for the first eligible 2026 `.ToLook` lot."""

    def __init__(self, port: ZoteroReadPort) -> None:
        self._port = port

    def run(self, *, run_date: date) -> DryRunResult:
        tolook_collection_key = self._resolve_tolook_collection_key()
        snapshots = self._read_all_collection_items(tolook_collection_key)
        papers = tuple(
            normalize_paper(snapshot.normalization_mapping(), run_date=run_date)
            for snapshot in snapshots
        )
        return DryRunResult(
            papers=select_first_real_lot(papers, tolook_collection_key=tolook_collection_key)
        )

    def _resolve_tolook_collection_key(self) -> str:
        tree = self._port.read_collection_tree(ReadCollectionTreeRequest())
        keys = sorted(key for key, name in tree.collections.items() if name == ".ToLook")
        if len(keys) != 1:
            raise ValueError("dry-run requires exactly one resolved .ToLook collection")
        return keys[0]

    def _read_all_collection_items(self, collection_key: str) -> list[ZoteroItemSnapshot]:
        page_size = 100
        snapshots_by_key: dict[str, ZoteroItemSnapshot] = {}
        start = 0
        while True:
            page = self._port.read_collection_items(
                ReadCollectionItemsRequest(
                    collection_key=collection_key, start=start, limit=page_size
                )
            )
            snapshots_by_key.update({snapshot.item_key: snapshot for snapshot in page})
            if len(page) < page_size:
                return list(snapshots_by_key.values())
            start += page_size
