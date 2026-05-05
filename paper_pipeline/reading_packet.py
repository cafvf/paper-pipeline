from __future__ import annotations

import re
from typing import Any

from .reading_plan import build_reading_plan
from .selection import CandidatePaper


def build_reading_packet(
    *,
    candidate: CandidatePaper,
    converted_documents: list[str | dict[str, Any] | list[Any]],
    max_chars: int = 20000,
) -> dict[str, Any]:
    text_pages = _flatten_documents(converted_documents)
    full_text = "\n\n".join(page["text"] for page in text_pages if page["text"]).strip()
    plan = build_reading_plan(candidate.stage)
    sections = {}
    for step in plan.steps:
        if step.name == "whole_paper_scan":
            sections[step.name] = _clip(full_text, max_chars // 2)
        elif step.name in {"method_topics", "method_formulation"}:
            sections[step.name] = _extract_method_topics(full_text, max_chars // 4)
        else:
            sections[step.name] = _extract_section(full_text, step.sections, max_chars // 4)
    packet = {
        "citekey": candidate.citekey,
        "stage": candidate.stage.value,
        "title": candidate.title,
        "metadata_abstract": candidate.abstract,
        "full_context": _clip(full_text, max_chars),
        "sections": sections,
        "reading_steps": [step.__dict__ for step in plan.steps],
        "figures": _extract_figures(text_pages) if plan.register_figures else [],
    }
    return packet


def _flatten_documents(converted_documents: list[str | dict[str, Any] | list[Any]]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for document in converted_documents:
        if isinstance(document, str):
            pages.append({"page": None, "text": document})
            continue
        if isinstance(document, list):
            for index, page in enumerate(document, start=1):
                pages.append({"page": _page_number(page, index), "text": _block_text(page)})
            continue
        raw_pages = document.get("pages")
        if isinstance(raw_pages, list):
            for index, page in enumerate(raw_pages, start=1):
                pages.append({"page": _page_number(page, index), "text": _block_text(page)})
        else:
            pages.append({"page": None, "text": _block_text(document)})
    return pages


def _page_number(page: Any, fallback: int) -> int:
    if isinstance(page, dict):
        raw = page.get("page") or page.get("page_number")
        if isinstance(raw, int):
            return raw
    return fallback


def _block_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_block_text(item) for item in value if _block_text(item)).strip()
    if not isinstance(value, dict):
        return str(value)
    direct = value.get("text") or value.get("html") or value.get("markdown") or value.get("content")
    children = value.get("children") or value.get("blocks")
    parts = []
    if direct:
        parts.append(str(direct))
    if isinstance(children, list):
        parts.extend(_block_text(child) for child in children)
    return "\n".join(part for part in parts if part).strip()


def _extract_section(text: str, names: list[str], max_chars: int) -> str:
    matches = []
    for name in names:
        matches.extend(_iter_heading_matches(text, [name]))
    if not matches:
        return _clip(text, max_chars)
    current = min(matches, key=lambda match: match.start())
    start = current.start()
    next_heading = next(_iter_heading_matches(text[current.end() :], _SECTION_HEADINGS), None)
    end = current.end() + next_heading.start() if next_heading else min(len(text), start + max_chars)
    return _clip(text[start:end].strip(), max_chars)


def _extract_method_topics(text: str, max_chars: int) -> str:
    intro = next(_iter_heading_matches(text, ["introduction", "introducao", "introdução"]), None)
    if intro:
        after_intro = text[intro.end() :]
        first_heading = next(_iter_numbered_heading_matches(after_intro), None)
        start = intro.end() + first_heading.start() if first_heading else intro.end()
        tail = text[start:]
        stop = next(_iter_heading_matches(tail, _METHOD_TOPICS_STOP_HEADINGS), None)
        end = start + stop.start() if stop else min(len(text), start + max_chars)
        return _clip(text[start:end].strip(), max_chars)
    fallback = _extract_section(text, ["method", "methods", "methodology", "formulation"], max_chars)
    return fallback


_SECTION_HEADINGS = [
    "abstract",
    "keywords",
    "introduction",
    "method",
    "methods",
    "methodology",
    "formulation",
    "results",
    "discussion",
    "validation",
    "limitations",
    "insights",
    "conclusion",
    "conclusions",
    "case study",
    "case studies",
    "study case",
    "case example",
    "examples",
    "application",
    "applications",
    "estudo de caso",
    "estudos de caso",
    "estudos de casos",
    "aplicacao",
    "aplicação",
    "aplicacoes",
    "aplicações",
]

_METHOD_TOPICS_STOP_HEADINGS = [
    "case study",
    "case studies",
    "study case",
    "case example",
    "examples",
    "results",
    "discussion",
    "validation",
    "conclusion",
    "conclusions",
    "application",
    "applications",
    "estudo de caso",
    "estudos de caso",
    "estudos de casos",
    "resultados",
    "discussao",
    "discussão",
    "validacao",
    "validação",
    "conclusao",
    "conclusão",
    "conclusoes",
    "conclusões",
    "aplicacao",
    "aplicação",
    "aplicacoes",
    "aplicações",
]


def _iter_heading_matches(text: str, names: list[str]):
    escaped = "|".join(re.escape(name) for name in names)
    pattern = rf"(?im)^[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?(?:{escaped})[ \t]*:?[ \t]*$"
    return re.finditer(pattern, text)


def _iter_numbered_heading_matches(text: str):
    return re.finditer(r"(?im)^[ \t]*\d+(?:\.\d+)*\.?[ \t]+[^\n]{3,120}$", text)


def _extract_figures(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    figures = []
    for page in pages:
        for line in page["text"].splitlines():
            if re.match(r"\s*(fig\.|figure)\s+\d+", line, re.I):
                figures.append({"page": page.get("page"), "caption": line.strip()})
    return figures


def _clip(text: str, max_chars: int) -> str:
    return text[:max_chars].rstrip()
