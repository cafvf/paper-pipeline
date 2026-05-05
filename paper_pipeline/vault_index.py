from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any


EFFORT_WEIGHTS = {
    "On": 35,
    "Ongoing": 25,
    "Simmering": 15,
}

ATLAS_DIRS = {"Concepts", "Dots", "Maps", "Literature"}


@dataclass(frozen=True)
class IndexedNote:
    path: str
    family: str
    weight: int
    title: str
    aliases: list[str]
    tags: list[str]
    links: list[str]
    headings: list[str]
    text: str
    content_hash: str


def build_lexical_index(vault_root: str | Path) -> dict[str, Any]:
    root = Path(vault_root)
    notes: list[IndexedNote] = []
    notes.extend(_index_efforts(root))
    notes.extend(_index_atlas(root))
    return {
        "schema_version": 1,
        "notes": [asdict(note) for note in notes],
    }


def write_index(index_root: str | Path, index: dict[str, Any]) -> Path:
    path = Path(index_root) / "lexical_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def search_lexical(index: dict[str, Any], query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for note in index.get("notes", []):
        haystack = " ".join(
            [
                str(note.get("title", "")),
                " ".join(note.get("aliases", [])),
                " ".join(note.get("tags", [])),
                " ".join(note.get("headings", [])),
                str(note.get("text", "")),
            ]
        )
        overlap = len(tokens & _tokens(haystack))
        if overlap:
            scored.append((overlap + int(note.get("weight", 0) or 0), note))
    return [note for _score, note in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def _index_efforts(root: Path) -> list[IndexedNote]:
    notes: list[IndexedNote] = []
    efforts_root = root / "Efforts"
    for folder, weight in EFFORT_WEIGHTS.items():
        for path in (efforts_root / folder).glob("*.md"):
            notes.append(_index_note(path, root, f"effort/{folder}", weight))
    return notes


def _index_atlas(root: Path) -> list[IndexedNote]:
    notes: list[IndexedNote] = []
    atlas_root = root / "Atlas"
    for folder in ATLAS_DIRS:
        for path in (atlas_root / folder).glob("*.md"):
            if folder == "Literature" and path.parent.name == "Zotero":
                continue
            notes.append(_index_note(path, root, f"atlas/{folder}", 10))
    for path in (atlas_root / "Papers").glob("*.md"):
        notes.append(_index_note(path, root, "atlas/Papers", 5))
    return notes


def _index_note(path: Path, root: Path, family: str, weight: int) -> IndexedNote:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _split_frontmatter(text)
    title = frontmatter.get("title") or path.stem
    return IndexedNote(
        path=str(path.relative_to(root)).replace("\\", "/"),
        family=family,
        weight=weight,
        title=str(title),
        aliases=_as_list(frontmatter.get("aliases", [])),
        tags=_as_list(frontmatter.get("tags", [])),
        links=sorted(set(re.findall(r"\[\[([^\]]+)\]\]", body))),
        headings=re.findall(r"(?m)^#{1,6}\s+(.+)$", body),
        text=" ".join(body.split())[:3000],
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw) or {}
        return parsed if isinstance(parsed, dict) else {}, body
    except Exception:
        return {}, body


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", text.lower())}
