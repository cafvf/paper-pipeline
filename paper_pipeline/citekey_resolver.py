from __future__ import annotations

from pathlib import Path
import re


def resolve_citekey_from_vault(vault_root: str | Path, *, doi: str, title: str) -> str:
    literature = Path(vault_root) / "Atlas" / "Literature" / "Zotero"
    if not literature.exists():
        return ""
    doi_norm = _norm_doi(doi)
    title_norm = _norm_text(title)
    for path in literature.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        citekey = _frontmatter_value(text, "citekey") or _filename_citekey(path)
        if doi_norm and doi_norm == _norm_doi(_frontmatter_value(text, "doi")):
            return citekey
        note_title = _frontmatter_value(text, "title")
        if title_norm and _norm_text(note_title) == title_norm:
            return citekey
    return ""


def _frontmatter_value(text: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*[\"']?(.*?)[\"']?\s*$", text)
    return match.group(1).strip() if match else ""


def _filename_citekey(path: Path) -> str:
    stem = path.stem.removesuffix(" - Literature")
    return stem


def _norm_doi(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.removeprefix("https://doi.org/")
    lowered = lowered.removeprefix("http://doi.org/")
    return lowered


def _norm_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())
