from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any

from .contracts import ensure_inside
from .schema_validation import validate_instance


STATE_MAP = {
    "On": ("on", "Efforts/On"),
    "Ongoing": ("ongoing", "Efforts/Ongoing"),
    "Simmering": ("simmering", "Efforts/Simmering"),
    "Terminated": ("terminated", "Efforts/Terminated"),
}

FIELD_ALIASES = {
    "objectives": ("objectives", "objective", "goals"),
    "methods": ("methods", "methodology", "approach"),
    "knowledge_gaps": ("knowledge_gaps", "gaps", "open_questions"),
    "expected_outputs": ("expected_outputs", "outputs", "deliverables"),
}

SECTION_ALIASES = {
    "objectives": {
        "objective",
        "objectives",
        "goal",
        "goals",
        "objetivo",
        "objetivos",
        "proposito",
        "proposito geral",
        "finalidade do documento",
        "pergunta central",
        "pergunta central do portfolio",
        "papel estrategico",
    },
    "methods": {
        "method",
        "methods",
        "methodology",
        "approach",
        "approaches",
        "como fazer",
        "metodo",
        "metodos",
        "metodologia",
        "abordagem",
        "eixos metodologicos recorrentes",
    },
    "knowledge_gaps": {
        "knowledge gap",
        "knowledge gaps",
        "gap",
        "gaps",
        "open question",
        "open questions",
        "lacuna",
        "lacunas",
        "sinais de alerta",
        "sinais de alerta desta versao",
        "bloqueios dependencias",
        "bloqueios",
        "proxima decisao",
    },
    "expected_outputs": {
        "expected output",
        "expected outputs",
        "output",
        "outputs",
        "deliverable",
        "deliverables",
        "entregas",
        "entregas outputs",
        "outcome",
        "outcome macro",
    },
}
GENERIC_H1_TITLES = {
    "objetivo",
    "objetivos",
    "atividades",
    "outcome",
    "outputs",
    "entregas",
    "deliverables",
    "como fazer",
}

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
HEADING_RE = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")
H1_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")


def scan_obsidian_projects(vault_root: str | Path) -> list[dict[str, Any]]:
    root = Path(vault_root).resolve()
    projects: list[dict[str, Any]] = []
    efforts_root = root / "Efforts"
    for folder, (project_state, state_source) in STATE_MAP.items():
        state_root = efforts_root / folder
        for path in sorted(state_root.rglob("*.md")):
            project = _build_project_profile(path, root, project_state=project_state, state_source=state_source)
            validate_instance(project, "project_profile.schema.json")
            projects.append(project)
    return sorted(projects, key=lambda item: item["source_path"])


def write_projects_jsonl(output_path: str | Path, projects: list[dict[str, Any]]) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    validated = sorted((validate_instance(project, "project_profile.schema.json") for project in projects), key=_sort_key)
    with path.open("w", encoding="utf-8") as handle:
        for project in validated:
            handle.write(json.dumps(project, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paper_pipeline.obsidian_inventory")
    parser.add_argument("--vault-root", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    projects = scan_obsidian_projects(args.vault_root)
    path = write_projects_jsonl(args.output, projects)
    print(f"projects={len(projects)} output={path}")
    return 0


def _build_project_profile(path: Path, vault_root: Path, *, project_state: str, state_source: str) -> dict[str, Any]:
    safe_path = ensure_inside(vault_root, path)
    text = safe_path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _split_frontmatter(text)
    sections = _extract_sections(body)
    title = _resolve_title(frontmatter, body, safe_path.stem)
    relative_path = str(safe_path.relative_to(vault_root)).replace("\\", "/")
    links = sorted(dict.fromkeys(match.strip() for match in WIKILINK_RE.findall(body) if match.strip()))
    project = {
        "project_id": _project_id(frontmatter.get("project_id"), title, safe_path.stem),
        "title": title,
        "source_path": relative_path,
        "objectives": _field_values(frontmatter, sections, "objectives"),
        "methods": _field_values(frontmatter, sections, "methods"),
        "knowledge_gaps": _field_values(frontmatter, sections, "knowledge_gaps"),
        "expected_outputs": _field_values(frontmatter, sections, "expected_outputs"),
        "priority": _normalize_priority(frontmatter.get("priority")),
        "project_state": project_state,
        "state_source": state_source,
        "tags": _dedupe(_as_list(frontmatter.get("tags"))),
        "links": links,
        "content_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    return project


def _field_values(frontmatter: dict[str, Any], sections: dict[str, list[str]], key: str) -> list[str]:
    for alias in FIELD_ALIASES[key]:
        values = _dedupe(_as_list(frontmatter.get(alias)))
        if values:
            return values
    return _dedupe(sections.get(key, []))


def _project_id(raw_value: Any, title: str, fallback: str) -> str:
    candidate = str(raw_value or "").strip()
    if candidate and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", candidate):
        return candidate
    return _slugify(title) or _slugify(fallback) or "project"


def _normalize_priority(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    if normalized in {"a", "p0", "p1"}:
        return "high"
    if normalized in {"b", "p2"}:
        return "medium"
    if normalized in {"c", "p3"}:
        return "low"
    if normalized in {"1", "p1"}:
        return "high"
    if normalized in {"2", "p2"}:
        return "medium"
    if normalized in {"3", "p3"}:
        return "low"
    return "medium"


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

        loaded = yaml.safe_load(raw) or {}
    except Exception:
        return {}, body
    if not isinstance(loaded, dict):
        return {}, body
    return loaded, body


def _extract_title_from_body(body: str) -> str:
    candidates = [match.group(1).strip() for match in H1_RE.finditer(body) if match.group(1).strip()]
    meaningful = [candidate for candidate in candidates if _normalized_heading(candidate) not in GENERIC_H1_TITLES]
    if meaningful:
        return meaningful[0]
    return candidates[0] if candidates else ""


def _extract_sections(body: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
    bullet_sections: dict[str, list[tuple[int, str]]] = {key: [] for key in SECTION_ALIASES}
    prose_sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
    current_key: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading_match:
            current_key = _section_key(heading_match.group(1))
            continue
        if current_key is None:
            continue
        kind, item, indent = _section_item(line)
        if not item:
            continue
        if kind == "bullet":
            bullet_sections[current_key].append((indent, item))
        elif kind == "prose":
            prose_sections[current_key].append(item)
    for key in sections:
        if bullet_sections[key]:
            top_level = [item for indent, item in bullet_sections[key] if indent == 0]
            sections[key] = top_level or [item for _indent, item in bullet_sections[key]]
        else:
            sections[key] = prose_sections[key]
    return sections


def _section_key(heading: str) -> str | None:
    normalized = _normalized_heading(heading)
    for key, aliases in SECTION_ALIASES.items():
        if normalized in aliases or any(alias in normalized for alias in aliases):
            return key
    return None


def _section_item(line: str) -> tuple[str, str, int]:
    stripped = line.strip()
    if not stripped:
        return ("", "", 0)
    bullet_match = re.match(r"^(?P<indent>\s*)(?:[-*+]\s+|\d+\.\s+)(?P<item>.+)$", line)
    if bullet_match:
        indent = len(bullet_match.group("indent") or "")
        return ("bullet", bullet_match.group("item").strip(), indent)
    if stripped.startswith("[[") and stripped.endswith("]]"):
        return ("", "", 0)
    return ("prose", stripped, 0)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean_value(str(item)))]
    cleaned = _clean_value(str(value))
    return [cleaned] if cleaned else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(cleaned for value in values if (cleaned := _clean_value(value))))


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_").lower()
    return re.sub(r"_+", "_", slug)


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _sort_key(project: dict[str, Any]) -> tuple[str, str]:
    return (str(project.get("source_path", "")), str(project.get("project_id", "")))


def _resolve_title(frontmatter: dict[str, Any], body: str, fallback_stem: str) -> str:
    fm_title = str(frontmatter.get("title", "")).strip()
    if fm_title:
        return fm_title
    body_title = _extract_title_from_body(body)
    if body_title and _normalized_heading(body_title) not in GENERIC_H1_TITLES:
        return body_title
    return fallback_stem


def _normalized_heading(value: str) -> str:
    lowered = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    lowered = lowered.replace("/", " ")
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _clean_value(value: str) -> str:
    stripped = value.strip()
    if stripped in {"", "-", "—", "–"}:
        return ""
    lowered = stripped.lower()
    if lowered in {"none", "n/a", "na"}:
        return ""
    return stripped


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
