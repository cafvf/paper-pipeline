from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Protocol

from .contracts import PipelineError
from .schema_validation import validate_instance
from .zotero_adapter import ZoteroItem
from .zotero_api import ZoteroApiAdapter


class ZoteroInventoryError(PipelineError):
    """Raised when Zotero inventory inputs or artifacts are unusable."""


class PaperInventorySource(Protocol):
    def list_paper_items(self) -> list[ZoteroItem]: ...


def paper_profile_from_item(item: ZoteroItem) -> dict[str, Any]:
    citekey = _clean_required(item.citekey, fallback=item.key)
    profile = {
        "citekey": citekey,
        "zotero_key": _clean_required(item.key, fallback=citekey),
        "title": _clean_required(item.title, fallback="(untitled)"),
        "year": item.publication_year,
        "authors": _dedupe(item.authors),
        "abstract": str(item.abstract or ""),
        "collections": _dedupe(item.collections),
        "tags": _dedupe(item.tags),
        "doi": str(item.doi or "") or None,
        "has_pdf": bool(item.pdf_paths),
        "pdf_paths": list(item.pdf_paths),
        "paper_hash": _paper_hash(item),
        "metadata_snapshot_path": f"papers/{citekey}/metadata_snapshot.json",
    }
    return validate_instance(profile, "paper_profile.schema.json")


def export_paper_inventory(
    items: Iterable[ZoteroItem],
    *,
    output_path: str | Path,
    papers_root: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = Path(papers_root)
    profiles = sorted((paper_profile_from_item(item) for item in items), key=lambda row: row["citekey"])
    with path.open("w", encoding="utf-8") as handle:
        for profile in profiles:
            handle.write(json.dumps(profile, ensure_ascii=False, sort_keys=True) + "\n")
            _write_metadata_snapshot(profile, root)
    return path


def load_fixture_items(path: str | Path) -> list[ZoteroItem]:
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise ZoteroInventoryError(f"offline fixture not found: {fixture_path}")
    try:
        loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ZoteroInventoryError(f"offline fixture is not valid JSON: {fixture_path}") from exc
    rows = loaded.get("items", []) if isinstance(loaded, dict) else loaded
    if not isinstance(rows, list):
        raise ZoteroInventoryError("offline fixture must be a list or an object with an items list")
    return [_item_from_mapping(row) for row in rows if isinstance(row, dict)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paper_pipeline.zotero_inventory")
    parser.add_argument("--offline-fixture", default=None, help="JSON fixture with Zotero item metadata for offline runs")
    parser.add_argument("--output", default="data/papers.jsonl")
    parser.add_argument("--papers-root", default="papers")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.offline_fixture:
            items = load_fixture_items(args.offline_fixture)
        else:
            items = ZoteroApiAdapter.from_dotenv().list_paper_items()
        output = export_paper_inventory(items, output_path=args.output, papers_root=args.papers_root)
    except PipelineError as exc:
        print(f"scan-zotero error: {exc}", file=sys.stderr)
        return 2
    print(f"papers={len(items)} output={output}")
    return 0


def _write_metadata_snapshot(profile: dict[str, Any], papers_root: Path) -> None:
    snapshot_path = papers_root / profile["citekey"] / "metadata_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_snapshot(snapshot_path)
    merged = {**existing, **profile}
    snapshot_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_existing_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _item_from_mapping(row: dict[str, Any]) -> ZoteroItem:
    return ZoteroItem(
        key=str(row.get("key") or row.get("zotero_key") or ""),
        citekey=str(row.get("citekey") or ""),
        title=str(row.get("title") or "(untitled)"),
        abstract=str(row.get("abstract") or row.get("abstractNote") or ""),
        collections=[str(value) for value in row.get("collections", []) if str(value)],
        tags=_tags_from_raw(row.get("tags", [])),
        publication_year=_int_or_none(row.get("publication_year", row.get("year"))),
        pdf_paths=[str(value) for value in row.get("pdf_paths", []) if str(value)],
        doi=str(row.get("doi") or row.get("DOI") or ""),
        source_type=str(row.get("source_type") or row.get("itemType") or ""),
        journal=str(row.get("journal") or row.get("publicationTitle") or row.get("proceedingsTitle") or ""),
        authors=[str(value) for value in row.get("authors", []) if str(value)],
    )


def _tags_from_raw(raw_tags: Any) -> list[str]:
    tags = []
    if not isinstance(raw_tags, list):
        return tags
    for tag in raw_tags:
        if isinstance(tag, dict):
            value = tag.get("tag")
        else:
            value = tag
        if str(value or ""):
            tags.append(str(value))
    return tags


def _paper_hash(item: ZoteroItem) -> str:
    payload = {
        "title": item.title,
        "abstract": item.abstract,
        "tags": sorted(_dedupe(item.tags)),
        "collections": sorted(_dedupe(item.collections)),
        "doi": item.doi,
        "year": item.publication_year,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean_required(value: str, *, fallback: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned or str(fallback or "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "PaperInventorySource",
    "ZoteroInventoryError",
    "export_paper_inventory",
    "load_fixture_items",
    "main",
    "paper_profile_from_item",
]
