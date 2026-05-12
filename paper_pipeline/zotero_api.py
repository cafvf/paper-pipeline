from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any

import requests

from .contracts import PipelineError, Stage
from .selection import CandidatePaper
from .zotero_adapter import ZoteroItem
from .zotero_plan import ZoteroActionPlan


class ZoteroApiError(PipelineError):
    """Raised when Zotero API configuration or responses are unusable."""


@dataclass(frozen=True)
class ZoteroApiConfig:
    api_key: str
    user_id: str
    data_dir: str = ""
    base_url: str = "https://api.zotero.org"

    @classmethod
    def from_env(cls) -> "ZoteroApiConfig":
        api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
        user_id = os.environ.get("ZOTERO_USER_ID", "").strip()
        data_dir = os.environ.get("ZOTERO_DATA_DIR", "").strip()
        if not api_key:
            raise ZoteroApiError("ZOTERO_API_KEY is not set")
        if not user_id:
            raise ZoteroApiError("ZOTERO_USER_ID is not set")
        return cls(api_key=api_key, user_id=user_id, data_dir=data_dir)


class ZoteroApiAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        user_id: str,
        data_dir: str = "",
        base_url: str = "https://api.zotero.org",
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.user_id = user_id
        self.data_dir = data_dir
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        if hasattr(self.session, "headers"):
            self.session.headers.update(
                {
                    "Zotero-API-Key": self.api_key,
                    "Zotero-API-Version": "3",
                }
            )

    @classmethod
    def from_env(cls) -> "ZoteroApiAdapter":
        cfg = ZoteroApiConfig.from_env()
        return cls(api_key=cfg.api_key, user_id=cfg.user_id, data_dir=cfg.data_dir, base_url=cfg.base_url)

    def list_candidates(self) -> list[CandidatePaper]:
        collections = self._collections_by_name()
        candidates: list[CandidatePaper] = []
        for stage in [Stage.TO_DIG, Stage.TO_REVISE, Stage.TO_LOOK]:
            collection_key = collections.get(stage.value)
            if not collection_key:
                continue
            for item in self._get_all(f"/collections/{collection_key}/items/top"):
                data = item.get("data", {})
                citekey = extract_citekey(data) or derive_citekey(data) or data.get("key") or item.get("key", "")
                children = self._children(item.get("key", data.get("key", "")), item)
                pdf_paths = [
                    path
                    for child in children
                    if _is_pdf_attachment(child.get("data", {}))
                    for path in [local_pdf_path(self.data_dir, child.get("key", ""), child.get("data", {}))]
                    if path and Path(path).exists()
                ]
                candidates.append(
                    CandidatePaper(
                        citekey=str(citekey),
                        stage=stage,
                        title=str(data.get("title", "") or "(untitled)"),
                        abstract=str(data.get("abstractNote", "") or ""),
                        tags=[str(tag.get("tag", "")) for tag in data.get("tags", []) if tag.get("tag")],
                        publication_year=publication_year(data.get("date", "")),
                        has_pdf=bool(pdf_paths),
                        pdf_paths=pdf_paths,
                        doi=str(data.get("DOI", "") or ""),
                        source_type=str(data.get("itemType", "") or ""),
                        journal=str(data.get("publicationTitle", "") or data.get("proceedingsTitle", "") or ""),
                        authors=creator_names(data.get("creators", [])),
                        zotero_item_key=str(data.get("key") or item.get("key", "")),
                        collection_keys=[str(key) for key in data.get("collections", [])],
                    )
                )
        return candidates

    def list_paper_items(self) -> list[ZoteroItem]:
        collections_by_key = {key: name for name, key in self._collections_by_name().items()}
        items: list[ZoteroItem] = []
        for item in self._get_all("/items/top"):
            data = item.get("data", {})
            if data.get("itemType") in {"attachment", "note"}:
                continue
            item_key = str(data.get("key") or item.get("key", ""))
            citekey = extract_citekey(data) or derive_citekey(data) or item_key
            children = self._children(item_key, item)
            pdf_paths = [
                path
                for child in children
                if _is_pdf_attachment(child.get("data", {}))
                for path in [local_pdf_path(self.data_dir, child.get("key", ""), child.get("data", {}))]
                if path and Path(path).exists()
            ]
            items.append(
                ZoteroItem(
                    key=item_key,
                    citekey=str(citekey),
                    title=str(data.get("title", "") or "(untitled)"),
                    abstract=str(data.get("abstractNote", "") or ""),
                    collections=[
                        collections_by_key.get(str(key), str(key))
                        for key in data.get("collections", [])
                        if str(key)
                    ],
                    tags=[str(tag.get("tag", "")) for tag in data.get("tags", []) if tag.get("tag")],
                    publication_year=publication_year(data.get("date", "")),
                    pdf_paths=pdf_paths,
                    doi=str(data.get("DOI", "") or ""),
                    source_type=str(data.get("itemType", "") or ""),
                    journal=str(data.get("publicationTitle", "") or data.get("proceedingsTitle", "") or ""),
                    authors=creator_names(data.get("creators", [])),
                )
            )
        return items

    def apply_plan(self, plan: ZoteroActionPlan) -> dict:
        if plan.status == "blocked":
            return {"status": "blocked", "reason": plan.reason}
        if plan.status == "noop":
            return {"status": "noop"}
        item = self._get(f"/items/{plan.item_key}")
        data = dict(item.get("data", item))
        version = data.get("version") or item.get("version")
        data["collections"] = list(plan.collections_to_set)
        data["tags"] = [{"tag": tag} for tag in plan.final_tags]
        headers = {"If-Unmodified-Since-Version": str(version)} if version is not None else {}
        response = self.session.put(self._url(f"/items/{plan.item_key}"), json=data, headers=headers)
        self._raise_for_status(response, f"/items/{plan.item_key}")
        return {"status": "applied", "response": _json_or_none(response)}

    def collection_name_to_key(self) -> dict[str, str]:
        return self._collections_by_name()

    def list_collections(self) -> list[dict]:
        return self._get_all("/collections")

    def ensure_collection(self, name: str, parent_collection: str | None = None) -> str:
        existing = self._collections_by_name()
        if name in existing:
            return existing[name]
        response = self.session.post(
            self._url("/collections"),
            json=[{"name": name, "parentCollection": parent_collection or False}],
        )
        self._raise_for_status(response, "/collections")
        data = response.json()
        successful = data.get("successful", {}) if isinstance(data, dict) else {}
        first = next(iter(successful.values()), {})
        key = first.get("key") or first.get("data", {}).get("key")
        if not key:
            raise ZoteroApiError(f"collection creation did not return a key for {name}")
        return str(key)

    def create_collection(self, name: str, parent_collection: str | None = None) -> dict:
        key = self.ensure_collection(name, parent_collection=parent_collection)
        return {"key": key, "data": {"name": name}}

    def _children(self, item_key: str, item: dict[str, Any]) -> list[dict[str, Any]]:
        if not item_key:
            return []
        if int(item.get("meta", {}).get("numChildren", 0) or 0) <= 0:
            return []
        return self._get_all(f"/items/{item_key}/children")

    def _collections_by_name(self) -> dict[str, str]:
        return {item.get("data", {}).get("name", ""): item.get("key", "") for item in self._get_all("/collections")}

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(self._url(endpoint), params=params)
        self._raise_for_status(response, endpoint)
        return response.json()

    def _get_all(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("limit", 100)
        start = int(params.get("start", 0) or 0)
        items: list[dict[str, Any]] = []
        while True:
            params["start"] = start
            response = self.session.get(self._url(endpoint), params=params)
            self._raise_for_status(response, endpoint)
            page = response.json()
            if not isinstance(page, list):
                raise ZoteroApiError(f"expected list response from {endpoint}")
            items.extend(page)
            if len(page) < int(params["limit"]):
                break
            start += int(params["limit"])
        return items

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/users/{self.user_id}{endpoint}"

    def _raise_for_status(self, response: Any, endpoint: str) -> None:
        status = int(getattr(response, "status_code", 200) or 200)
        if status < 400:
            return
        retry_after = getattr(response, "headers", {}).get("Retry-After")
        detail = f"Zotero API error {status} at {endpoint}"
        if retry_after:
            detail += f" (Retry-After: {retry_after})"
        text = getattr(response, "text", "")
        if text:
            detail += f": {text[:300]}"
        raise ZoteroApiError(detail)


def extract_citekey(data: dict[str, Any]) -> str:
    extra = str(data.get("extra", "") or "")
    for pattern in [
        r"(?im)^\s*Citation Key\s*:\s*(?P<key>\S+)\s*$",
        r"(?im)^\s*tex\.ids\s*:\s*(?P<key>\S+)\s*$",
        r"(?im)^\s*citekey\s*:\s*(?P<key>\S+)\s*$",
    ]:
        match = re.search(pattern, extra)
        if match:
            return match.group("key").strip()
    return ""


def derive_citekey(data: dict[str, Any]) -> str:
    creators = data.get("creators", [])
    first_author = "item"
    if creators:
        first = creators[0]
        first_author = str(first.get("lastName") or first.get("name") or "item").split()[-1]
    title_words = [
        word
        for word in re.findall(r"[A-Za-z0-9]+", str(data.get("title", "")))
        if word.lower() not in {"a", "an", "the", "of", "with", "and", "for", "in", "on", "to", "by"}
    ][:3]
    year = publication_year(data.get("date", "")) or ""
    pieces = [first_author.lower()]
    if title_words:
        pieces.append(title_words[0].capitalize() + "".join(word.capitalize() for word in title_words[1:]))
    if year:
        pieces.append(str(year))
    return _clean_citekey("".join(pieces))


def _clean_citekey(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", value)


def publication_year(value: Any) -> int | None:
    match = re.search(r"(18|19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def creator_names(creators: list[dict[str, Any]]) -> list[str]:
    names = []
    for creator in creators:
        if creator.get("name"):
            names.append(str(creator["name"]))
        else:
            names.append(" ".join(part for part in [creator.get("firstName", ""), creator.get("lastName", "")] if part).strip())
    return [name for name in names if name]


def local_pdf_path(data_dir: str | Path, attachment_key: str, data: dict[str, Any]) -> str:
    raw_path = str(data.get("path", "") or "")
    filename = str(data.get("filename", "") or "")
    if raw_path.startswith("storage:"):
        name = raw_path.split(":", 1)[1] or filename
        if not data_dir:
            return ""
        return str((Path(data_dir) / "storage" / attachment_key / name).resolve())
    if filename and attachment_key and data_dir and data.get("linkMode") in {"imported_file", None}:
        return str((Path(data_dir) / "storage" / attachment_key / filename).resolve())
    if raw_path and Path(raw_path).is_absolute():
        return raw_path
    return ""


def _is_pdf_attachment(data: dict[str, Any]) -> bool:
    return data.get("itemType") == "attachment" and (
        data.get("contentType") == "application/pdf" or str(data.get("filename", "")).lower().endswith(".pdf")
    )


def _json_or_none(response: Any) -> Any:
    text = str(getattr(response, "text", "") or "")
    if not text.strip():
        return None
    try:
        return response.json()
    except ValueError:
        return None
