from pathlib import Path

from paper_pipeline.contracts import CollectionAction, Stage
from paper_pipeline.zotero_api import ZoteroApiAdapter, derive_citekey, extract_citekey, local_pdf_path
from paper_pipeline.zotero_plan import ZoteroActionPlan


class Response:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.put_payload = None
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        if url.endswith("/collections"):
            return Response(
                [
                    {"key": "CLOOK", "data": {"name": ".ToLook", "parentCollection": False}},
                    {"key": "CREV", "data": {"name": ".To Revise", "parentCollection": False}},
                    {"key": "CDIG", "data": {"name": ".ToDig", "parentCollection": False}},
                    {"key": "CBOOK", "data": {"name": "Books", "parentCollection": False}},
                ]
            )
        if url.endswith("/items/top") and "/collections/" not in url:
            return Response(
                [
                    {
                        "key": "ITEM1",
                        "meta": {"numChildren": 1},
                        "data": {
                            "key": "ITEM1",
                            "title": "Bayesian CPT",
                            "abstractNote": "soil uncertainty",
                            "date": "2025",
                            "DOI": "10.1000/test",
                            "extra": "Citation Key: smith2025",
                            "tags": [{"tag": "@look"}],
                            "collections": ["CLOOK", "CBOOK"],
                            "creators": [{"firstName": "A", "lastName": "Smith"}],
                            "publicationTitle": "Journal",
                            "itemType": "journalArticle",
                            "version": 7,
                        },
                    },
                    {
                        "key": "ITEM2",
                        "meta": {"numChildren": 0},
                        "data": {
                            "key": "ITEM2",
                            "title": "Library-only book",
                            "date": "2024",
                            "extra": "Citation Key: book2024",
                            "tags": [{"tag": "background"}],
                            "collections": ["CBOOK"],
                            "creators": [{"name": "Research Group"}],
                            "itemType": "book",
                        },
                    },
                ]
            )
        if url.endswith("/collections/CLOOK/items/top"):
            return Response(
                [
                    {
                        "key": "ITEM1",
                        "meta": {"numChildren": 1},
                        "data": {
                            "key": "ITEM1",
                            "title": "Bayesian CPT",
                            "abstractNote": "soil uncertainty",
                            "date": "2025",
                            "DOI": "10.1000/test",
                            "extra": "Citation Key: smith2025",
                            "tags": [{"tag": "@look"}],
                            "collections": ["CLOOK", "CBOOK"],
                            "creators": [{"firstName": "A", "lastName": "Smith"}],
                            "publicationTitle": "Journal",
                            "itemType": "journalArticle",
                            "version": 7,
                        },
                    }
                ]
            )
        if url.endswith("/collections/CREV/items/top") or url.endswith("/collections/CDIG/items/top"):
            return Response([])
        if url.endswith("/items/ITEM1/children"):
            return Response(
                [
                    {
                        "key": "ATT1",
                        "data": {
                            "itemType": "attachment",
                            "contentType": "application/pdf",
                            "linkMode": "imported_file",
                            "path": "storage:paper.pdf",
                            "filename": "paper.pdf",
                        },
                    }
                ]
            )
        if url.endswith("/items/ITEM1"):
            return Response(
                {
                    "key": "ITEM1",
                    "data": {
                        "key": "ITEM1",
                        "version": 7,
                        "collections": ["CLOOK", "CBOOK"],
                        "tags": [{"tag": "@look"}],
                    },
                }
            )
        raise AssertionError(url)

    def put(self, url, json=None, headers=None):
        self.put_payload = {"url": url, "json": json, "headers": headers}
        return Response({"successful": {"0": {"key": "ITEM1"}}})


class EmptyBodyResponse(Response):
    text = ""

    def json(self):
        raise ValueError("empty response")


class EmptyPutSession(FakeSession):
    def put(self, url, json=None, headers=None):
        self.put_payload = {"url": url, "json": json, "headers": headers}
        return EmptyBodyResponse(None)


def test_extract_citekey_from_extra_variants():
    assert extract_citekey({"extra": "Citation Key: smith2025"}) == "smith2025"
    assert extract_citekey({"extra": "tex.ids: foo2024"}) == "foo2024"


def test_derive_citekey_when_bbt_key_is_missing():
    assert (
        derive_citekey(
            {
                "title": "Active learning Kriging with spherical low-discrepancy sampling",
                "date": "2026-03",
                "creators": [{"lastName": "Liao"}, {"lastName": "Sun"}],
            }
        )
        == "liaoActiveLearningKriging2026"
    )


def test_local_pdf_path_resolves_imported_storage_attachment(tmp_path: Path):
    assert local_pdf_path(tmp_path, "ATT1", {"path": "storage:paper.pdf", "filename": "paper.pdf"}) == str(
        tmp_path / "storage" / "ATT1" / "paper.pdf"
    )
    assert local_pdf_path(tmp_path, "ATT1", {"filename": "paper.pdf"}) == str(tmp_path / "storage" / "ATT1" / "paper.pdf")


def test_api_adapter_lists_candidates_with_pdf_paths(tmp_path: Path):
    pdf = tmp_path / "storage" / "ATT1" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_text("pdf", encoding="utf-8")
    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", data_dir=str(tmp_path), session=FakeSession())
    candidates = adapter.list_candidates()
    assert len(candidates) == 1
    assert candidates[0].citekey == "smith2025"
    assert candidates[0].stage == Stage.TO_LOOK
    assert candidates[0].pdf_paths == [str(pdf.resolve())]
    assert candidates[0].authors == ["A Smith"]


def test_api_adapter_lists_neutral_paper_items_without_zotero_writes(tmp_path: Path):
    pdf = tmp_path / "storage" / "ATT1" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_text("pdf", encoding="utf-8")
    session = FakeSession()
    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", data_dir=str(tmp_path), session=session)

    items = adapter.list_paper_items()

    assert [item.citekey for item in items] == ["smith2025", "book2024"]
    assert items[0].collections == [".ToLook", "Books"]
    assert items[0].pdf_paths == [str(pdf.resolve())]
    assert items[1].collections == ["Books"]
    assert items[1].authors == ["Research Group"]
    assert session.put_payload is None


def test_api_adapter_apply_plan_uses_final_collections_and_tags():
    session = FakeSession()
    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", data_dir="C:/Zotero", session=session)
    plan = ZoteroActionPlan(
        item_key="ITEM1",
        current_stage=Stage.TO_LOOK,
        target_stage=Stage.TO_REVISE,
        collection_action=CollectionAction.MOVE_TO_REVISE,
        collections_to_set=["CREV", "CBOOK"],
        tags_to_add=["@review"],
        tags_to_remove=["@look"],
        final_tags=["@review"],
        status="planned",
    )
    result = adapter.apply_plan(plan)
    assert result["status"] == "applied"
    assert session.put_payload["json"]["collections"] == ["CREV", "CBOOK"]
    assert session.put_payload["json"]["tags"] == [{"tag": "@review"}]
    assert session.put_payload["headers"]["If-Unmodified-Since-Version"] == "7"


def test_api_adapter_apply_plan_accepts_successful_empty_response():
    session = EmptyPutSession()
    adapter = ZoteroApiAdapter(api_key="secret", user_id="123", data_dir="C:/Zotero", session=session)
    plan = ZoteroActionPlan(
        item_key="ITEM1",
        current_stage=Stage.TO_LOOK,
        target_stage=Stage.TO_REVISE,
        collection_action=CollectionAction.MOVE_TO_REVISE,
        collections_to_set=["CREV"],
        tags_to_add=["@review"],
        tags_to_remove=[],
        final_tags=["@review"],
        status="planned",
    )

    result = adapter.apply_plan(plan)

    assert result == {"status": "applied", "response": None}
