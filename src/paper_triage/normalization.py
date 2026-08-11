"""Pure normalization; it never reads a connector or local files."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from typing import Any

from .errors import Issue, IssueCode, TriageError
from .models import Author, ItemTypeClass, Paper, PaperKind

_SPACE = re.compile(r"\s+")
_MARKUP = re.compile(r"<[^>]*>")
_DOI = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.IGNORECASE)
_ORIGINAL = {"journalArticle", "conferencePaper", "preprint", "thesis", "report"}
_CHILDREN = {"attachment", "note", "annotation"}
_SUPPORT = {
    "book",
    "bookSection",
    "document",
    "encyclopediaArticle",
    "dictionaryEntry",
    "magazineArticle",
    "newspaperArticle",
    "manuscript",
    "presentation",
    "webpage",
    "blogPost",
    "forumPost",
    "interview",
    "letter",
    "email",
    "instantMessage",
    "podcast",
    "radioBroadcast",
    "tvBroadcast",
    "videoRecording",
    "audioRecording",
    "film",
    "artwork",
    "map",
    "case",
    "statute",
    "bill",
    "hearing",
    "patent",
    "standard",
    "computerProgram",
    "dataset",
}


def normalize_text(value: str | None, *, strip_markup: bool = False) -> str | None:
    if value is None:
        return None
    text = html.unescape(value)
    if strip_markup:
        text = _MARKUP.sub(" ", text)
    text = _SPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()
    return text or None


def normalize_doi(value: str | None) -> str | None:
    value = normalize_text(value)
    if not value:
        return None
    value = (
        re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.IGNORECASE)
        .rstrip(".,;:)")
        .lower()
    )
    return value if _DOI.fullmatch(value) else None


def _kind(raw_item_type: str, tags: frozenset[str]) -> tuple[ItemTypeClass, PaperKind]:
    if raw_item_type in _CHILDREN:
        raise TriageError(IssueCode.PAPER_KIND_AMBIGUOUS, "child Zotero items cannot be triaged")
    if raw_item_type in _ORIGINAL:
        return ItemTypeClass.ORIGINAL_CANDIDATE, (
            PaperKind.REVIEW
            if {"%narrative-review", "%systematic-review"} & tags
            else PaperKind.ORIGINAL
        )
    if raw_item_type in _SUPPORT:
        return ItemTypeClass.SUPPORT_OR_NONPAPER, PaperKind.AMBIGUOUS
    return ItemTypeClass.UNKNOWN, PaperKind.AMBIGUOUS


def normalize_paper(raw: Mapping[str, Any], *, run_date: date) -> Paper:
    """Convert an already-read safe metadata mapping into an immutable Paper."""
    title = normalize_text(raw.get("title"), strip_markup=True)
    if not title:
        raise TriageError(IssueCode.PAPER_TITLE_REQUIRED, "paper title is required")
    warnings: list[Issue] = []
    citekey = normalize_text(raw.get("citekey"))
    if citekey is None:
        warnings.append(Issue(code=IssueCode.CITEKEY_MISSING, message="citekey is absent"))
    authors = tuple(Author(**author) for author in raw.get("authors", ()))
    if not authors:
        warnings.append(Issue(code=IssueCode.AUTHOR_MISSING, message="authors are absent"))
    year = raw.get("year")
    if not isinstance(year, int) or not 1000 <= year <= run_date.year + 1:
        if year is not None:
            warnings.append(
                Issue(code=IssueCode.YEAR_INVALID, message="publication year is invalid")
            )
        year = None
    supplied_doi = raw.get("doi")
    doi = normalize_doi(supplied_doi)
    if supplied_doi and doi is None:
        warnings.append(Issue(code=IssueCode.DOI_INVALID, message="DOI is invalid"))
    tags = frozenset(filter(None, (normalize_text(tag) for tag in raw.get("tags", ()))))
    raw_type = str(raw.get("raw_item_type", "unknown"))
    item_type_class, paper_kind = _kind(raw_type, tags)
    fields = {
        "title": title,
        "authors": [author.model_dump(mode="json") for author in authors],
        "year": year,
        "doi": doi,
        "venue": normalize_text(raw.get("venue")),
        "abstract": normalize_text(raw.get("abstract"), strip_markup=True),
        "tags": sorted(tags),
        "collections": sorted(set(raw.get("collections", ()))),
        "raw_item_type": raw_type,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return Paper(
        library_id=str(raw["library_id"]),
        item_key=str(raw["item_key"]),
        item_version=int(raw["item_version"]),
        raw_item_type=raw_type,
        item_type_class=item_type_class,
        paper_kind=paper_kind,
        citekey=citekey,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        venue=normalize_text(raw.get("venue")),
        abstract=normalize_text(raw.get("abstract"), strip_markup=True),
        collections=frozenset(raw.get("collections", ())),
        tags=tags,
        pdf_attachments=tuple(raw.get("pdf_attachments", ())),
        source_fingerprint=fingerprint,
        normalization_warnings=tuple(warnings),
    )
