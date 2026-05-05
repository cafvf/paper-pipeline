from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .contracts import ValidationError, ensure_inside, normalize_citekey


PLACEHOLDER = "<!-- LLM:knowledge -->"
PATCH_MARKER = "<!-- llm_patch_id: {patch_id} -->"
LIMITS = {"concept": 1000, "dot": 1000, "moc": 2000, "literature": 2000}


@dataclass(frozen=True)
class KnowledgePatch:
    patch_id: str
    heading: str
    content: str
    source_citekey: str


@dataclass(frozen=True)
class PatchBlock:
    heading: str
    content: str


@dataclass(frozen=True)
class NotePatchPlan:
    note_path: Path
    patch_id: str
    blocks: list[PatchBlock] = field(default_factory=list)
    mode: str = "append_or_placeholder"


def find_literature_note(vault_root: str | Path, citekey: str) -> Path | None:
    root = Path(vault_root)
    safe = normalize_citekey(citekey)
    literature_root = root / "Atlas" / "Literature"
    preferred = literature_root / f"{safe} - Literature.md"
    if preferred.exists():
        return preferred
    matches = sorted(path for path in literature_root.glob(f"{safe}*.md") if "Zotero" not in path.parts)
    return matches[0] if matches else None


def plan_note_patch(*, note_path: str | Path, patch: KnowledgePatch, note_kind: str = "literature") -> NotePatchPlan:
    path = Path(note_path)
    limit = LIMITS.get(note_kind, 2000)
    blocks = [
        PatchBlock(
            heading=patch.heading if index == 0 else f"{patch.heading} ({index + 1})",
            content=chunk,
        )
        for index, chunk in enumerate(_split_text(patch.content, limit))
    ]
    return NotePatchPlan(note_path=path, patch_id=patch.patch_id, blocks=blocks)


def apply_patch_plan(plan: NotePatchPlan) -> dict:
    path = plan.note_path
    _ensure_not_zotero_source(path)
    text = path.read_text(encoding="utf-8")
    marker = PATCH_MARKER.format(patch_id=plan.patch_id)
    if marker in text:
        return {"status": "noop", "reason": "patch already applied"}
    block_text = "\n\n".join(_render_block(plan.patch_id, block) for block in plan.blocks)
    if PLACEHOLDER in text:
        updated = text.replace(PLACEHOLDER, f"{PLACEHOLDER}\n\n{block_text}", 1)
    else:
        updated = text.rstrip() + "\n\n" + block_text + "\n"
    path.write_text(updated, encoding="utf-8")
    return {"status": "applied", "path": str(path)}


def safe_target_path(vault_root: str | Path, target_note: str | Path) -> Path:
    root = Path(vault_root)
    return ensure_inside(root, root / target_note)


def _render_block(patch_id: str, block: PatchBlock) -> str:
    return f"{PATCH_MARKER.format(patch_id=patch_id)}\n### {block.heading}\n\n{block.content.rstrip()}"


def _split_text(text: str, limit: int) -> list[str]:
    stripped = text.strip()
    if len(stripped) <= limit:
        return [stripped]
    return [stripped[index : index + limit] for index in range(0, len(stripped), limit)]


def _ensure_not_zotero_source(path: Path) -> None:
    parts = set(path.parts)
    if "Atlas" in parts and "Literature" in parts and "Zotero" in parts:
        raise ValidationError("refusing to patch Zotero source note")
