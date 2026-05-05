from pathlib import Path

import pytest

from paper_pipeline.contracts import Stage
from paper_pipeline.zotero_api import ZoteroApiAdapter, ZoteroApiError


class Response:
    def __init__(self, payload, status_code=200, headers=None, text=""):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._payload


class PagingSession:
    def __init__(self):
        self.headers = {}
        self.posts = []

    def get(self, url, params=None):
        start = int((params or {}).get("start", 0))
        limit = int((params or {}).get("limit", 100))
        if url.endswith("/collections"):
            names = [".ToLook", ".To Revise", ".To Dig"] + [f"Other {i}" for i in range(100)]
            page = names[start : start + limit]
            return Response([{"key": f"C{start + i}", "data": {"name": name}} for i, name in enumerate(page)])
        if url.endswith("/collections/C2/items/top"):
            return Response([])
        if url.endswith("/collections/C1/items/top"):
            return Response([])
        if url.endswith("/collections/C0/items/top"):
            return Response([])
        raise AssertionError(url)

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return Response({"successful": {"0": {"key": "CEXP", "data": {"name": "Expendable"}}}})


def test_collection_lookup_supports_aliases_and_pagination():
    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", session=PagingSession())
    candidates = adapter.list_candidates()
    assert candidates == []
    mapping = adapter.collection_name_to_key()
    assert mapping[".To Dig"] == "C2"


def test_ensure_expendable_collection_creates_root_when_missing():
    session = PagingSession()
    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", session=session)
    created = adapter.ensure_collection("Expendable")
    assert created == "CEXP"
    assert session.posts[0]["json"] == [{"name": "Expendable", "parentCollection": False}]


def test_local_pdf_must_exist_to_mark_candidate_as_pdf_available(tmp_path: Path):
    class Session:
        headers = {}

        def get(self, url, params=None):
            if url.endswith("/collections"):
                return Response(
                    [
                        {"key": "CLOOK", "data": {"name": ".ToLook"}},
                        {"key": "CREV", "data": {"name": ".To Revise"}},
                        {"key": "CDIG", "data": {"name": ".ToDig"}},
                    ]
                )
            if url.endswith("/collections/CLOOK/items/top"):
                return Response(
                    [
                        {
                            "key": "ITEM",
                            "meta": {"numChildren": 1},
                            "data": {"key": "ITEM", "title": "Paper", "extra": "Citation Key: a"},
                        }
                    ]
                )
            if url.endswith("/collections/CREV/items/top") or url.endswith("/collections/CDIG/items/top"):
                return Response([])
            if url.endswith("/items/ITEM/children"):
                return Response(
                    [
                        {
                            "key": "ATT",
                            "data": {"itemType": "attachment", "contentType": "application/pdf", "filename": "missing.pdf"},
                        }
                    ]
                )
            raise AssertionError(url)

    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", data_dir=str(tmp_path), session=Session())
    candidate = adapter.list_candidates()[0]
    assert candidate.pdf_paths == []
    assert candidate.has_pdf is False


def test_rate_limit_error_mentions_retry_after():
    class Session:
        headers = {}

        def get(self, url, params=None):
            return Response({"error": "rate limited"}, status_code=429, headers={"Retry-After": "30"})

    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", session=Session())
    with pytest.raises(ZoteroApiError, match="Retry-After: 30"):
        adapter.list_candidates()
