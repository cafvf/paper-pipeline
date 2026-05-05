from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import Path
import re
from typing import Any

from .artifacts import PaperArtifactStore
from .contracts import FullDecision, KnowledgeAction, PipelineError, ensure_inside, normalize_citekey
from .llm_schema import LLMAssessment, parse_llm_assessment
from .note_patcher import KnowledgePatch, apply_patch_plan, find_literature_note, plan_note_patch, safe_target_path
from .vault_index import build_lexical_index, search_lexical


@dataclass
class KnowledgeApplicationResult:
    status: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def apply_article_knowledge(
    *,
    note_path: str | Path,
    vault_root: str | Path,
    artifact_store: PaperArtifactStore,
    citekey: str,
    decision: FullDecision,
    lexical_index: dict[str, Any] | None = None,
) -> KnowledgeApplicationResult:
    root = Path(vault_root)
    safe_citekey = normalize_citekey(citekey)
    assessment = _load_latest_assessment(artifact_store)
    if assessment is None:
        return KnowledgeApplicationResult(status="error", errors=["assessment artifact required for knowledge application"])
    index = lexical_index or build_lexical_index(root)
    title = _title_from_note(Path(note_path), fallback=safe_citekey)
    actions: list[dict[str, Any]] = []

    literature_note = _apply_literature_action(
        root=root,
        citekey=safe_citekey,
        title=title,
        assessment=assessment,
        action=decision.knowledge_actions.literature_note,
    )
    if literature_note is not None:
        actions.append(literature_note)

    related_notes: list[Path] = []
    atlas_links: list[dict[str, Any]] = []
    for index_number, suggestion in enumerate(assessment.knowledge_suggestions, start=1):
        action = _apply_suggestion(root, safe_citekey, assessment, suggestion, index_number, index)
        actions.append(action)
        if action.get("note_path"):
            related_notes.append(Path(str(action["note_path"])))
        atlas_links.extend(action.get("related_atlas", []))

    integration = _apply_integration_moc(
        root=root,
        citekey=safe_citekey,
        title=title,
        assessment=assessment,
        related_notes=related_notes,
        atlas_links=atlas_links,
    )
    actions.append(integration)
    artifact_store.append_log({"event": "knowledge_applied", "actions": actions})
    return KnowledgeApplicationResult(status="applied", actions=actions)


def _load_latest_assessment(store: PaperArtifactStore) -> LLMAssessment | None:
    assessment_root = store.root / "assessments"
    for path in sorted(assessment_root.glob("*_latest.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            return parse_llm_assessment(json.dumps(payload, ensure_ascii=False))
        except PipelineError:
            continue
    for path in sorted(store.root.glob("passes/*/latest/llm_result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_outputs = payload.get("raw_outputs") or []
        if raw_outputs:
            try:
                return parse_llm_assessment(str(raw_outputs[-1]))
            except PipelineError:
                continue
    return None


def _apply_literature_action(
    *,
    root: Path,
    citekey: str,
    title: str,
    assessment: LLMAssessment,
    action: KnowledgeAction,
) -> dict[str, Any] | None:
    if action in {KnowledgeAction.REJECT, KnowledgeAction.DEFER}:
        return None
    note = find_literature_note(root, citekey)
    if note is None and action in {KnowledgeAction.CREATE_NEW, KnowledgeAction.UPDATE_EXISTING, KnowledgeAction.LINK_EXISTING}:
        note = _create_literature_draft(root, citekey, title, assessment)
    if note is None:
        return None
    patch = KnowledgePatch(
        patch_id=f"{citekey}-literature-synthesis",
        heading="Sintese LLM da leitura",
        content=_literature_patch_content(assessment),
        source_citekey=citekey,
    )
    if _is_inbox_draft(root, note):
        result = {"status": "created"}
    else:
        result = apply_patch_plan(plan_note_patch(note_path=note, patch=patch, note_kind="literature"))
    return {"action": "knowledge_literature_note", "status": result["status"], "note_path": str(note)}


def _apply_suggestion(
    root: Path,
    citekey: str,
    assessment: LLMAssessment,
    suggestion: dict[str, Any],
    index_number: int,
    index: dict[str, Any],
) -> dict[str, Any]:
    note, note_kind, related = _resolve_suggestion_target(root, citekey, suggestion, index)
    if not note.exists():
        _create_suggestion_draft(root, note, note_kind, suggestion, assessment, related)
        result = {"status": "created"}
    else:
        result = {"status": "noop", "reason": "draft already exists"}
    return {
        "action": "knowledge_suggestion",
        "status": result["status"],
        "note_path": str(note),
        "target": str(suggestion.get("target", "") or ""),
        "related_atlas": _compact_related(related),
    }


def _resolve_suggestion_target(root: Path, citekey: str, suggestion: dict[str, Any], index: dict[str, Any]) -> tuple[Path, str, list[dict[str, Any]]]:
    target = str(suggestion.get("target", "") or "").strip()
    kind = str(suggestion.get("type", "") or "").strip()
    if target.endswith(".md"):
        path = safe_target_path(root, target)
        return path, _note_kind_from_path(path), []
    related = _related_notes(
        index,
        " ".join(
            [
                target,
                str(suggestion.get("knowledge_claim", "")),
                str(suggestion.get("article_use", "")),
                str(suggestion.get("applicability", "")),
                str(suggestion.get("integration_notes", "")),
                str(suggestion.get("content", "")),
                str(suggestion.get("justification", "")),
            ]
        ),
    )
    note_kind = _kind_from_suggestion(kind)
    return ensure_inside(root, root / "+" / f"{citekey} - {_safe_note_stem(target or kind or 'Knowledge suggestion')} Draft.md"), note_kind, related


def _related_notes(index: dict[str, Any], query: str) -> list[dict[str, Any]]:
    return [note for note in search_lexical(index, query, limit=5) if str(note.get("path", "")).startswith("Atlas/")]


def _compact_related(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": str(note.get("path", "")),
            "title": str(note.get("title", "")),
            "family": str(note.get("family", "")),
        }
        for note in notes
    ]


def _preferred_existing_note(related: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    wanted = {
        "concept": "atlas/Concepts",
        "method_check": "atlas/Concepts",
        "dot": "atlas/Dots",
        "moc": "atlas/Maps",
        "literature_note_update": "atlas/Literature",
    }.get(kind)
    if wanted:
        for note in related:
            if str(note.get("family", "")) == wanted:
                return note
    return related[0] if related else None


def _apply_integration_moc(
    *,
    root: Path,
    citekey: str,
    title: str,
    assessment: LLMAssessment,
    related_notes: list[Path],
    atlas_links: list[dict[str, Any]],
) -> dict[str, Any]:
    note = ensure_inside(root, root / "+" / f"{citekey} - Knowledge Integration Draft.md")
    if not note.exists():
        _create_integration_draft(note, title, citekey, assessment, related_notes, atlas_links, root)
        result = {"status": "created"}
    else:
        patch = KnowledgePatch(
            patch_id=f"{citekey}-integration",
            heading=f"Integracao da leitura {citekey}",
            content=_integration_content(root, citekey, assessment, related_notes, atlas_links),
            source_citekey=citekey,
        )
        result = apply_patch_plan(plan_note_patch(note_path=note, patch=patch, note_kind="moc"))
    return {"action": "knowledge_integration_moc", "status": result["status"], "note_path": str(note)}


def _literature_patch_content(assessment: LLMAssessment) -> str:
    evidence = "\n".join(f"- {item}" for item in assessment.evidence[:6])
    return "\n".join(
        [
            f"Resumo: {assessment.summary}",
            "",
            "Evidencias principais:",
            evidence or "- Nao informado.",
            "",
            f"Confianca: {assessment.confidence:.2f}",
        ]
    )


def _suggestion_patch_content(suggestion: dict[str, Any], assessment: LLMAssessment, related: list[dict[str, Any]]) -> str:
    note_kind = _kind_from_suggestion(str(suggestion.get("type", "") or ""))
    if note_kind == "dot":
        return _dot_suggestion_content(suggestion, assessment, related)
    if note_kind == "moc":
        return _moc_suggestion_content(suggestion, assessment, related)
    return _concept_suggestion_content(suggestion, assessment, related)


def _concept_suggestion_content(suggestion: dict[str, Any], assessment: LLMAssessment, related: list[dict[str, Any]]) -> str:
    related_links = [_wikilink(str(item.get("path", "")), str(item.get("title", ""))) for item in related[:5]]
    concept_dot_links = [
        _wikilink(str(item.get("path", "")), str(item.get("title", "")))
        for item in related
        if str(item.get("family", "")) in {"atlas/Concepts", "atlas/Dots"}
    ][:6]
    evidence = suggestion.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
    review_tasks = suggestion.get("review_tasks", [])
    if isinstance(review_tasks, str):
        review_tasks = [review_tasks]
    legacy_content = str(suggestion.get("content", "") or "").strip()
    lines = [
        f"Fonte: [[{assessment.citekey} - Literature|{assessment.citekey}]]",
        f"Tipo sugerido: {suggestion.get('type', 'sugestao')}",
        f"Alvo sugerido: {suggestion.get('target', '')}",
        "",
        "## Definicao formal",
        str(suggestion.get("knowledge_claim", "") or legacy_content or "Nao informado.").strip(),
        "",
        "**Equacao central (se aplicavel):**",
        "```text",
        "Nao extraida automaticamente.",
        "```",
        "",
        "## Intuicao fisica",
        str(suggestion.get("article_use", "") or "Nao informado.").strip(),
        "",
        "## Hipoteses e limites",
        f"- Assume: {suggestion.get('applicability', '') or 'Nao informado.'}",
        "- Ignora: Nao informado automaticamente.",
        f"- Quebra quando: {suggestion.get('limitations', '') or 'Nao informado.'}",
        "",
        "## Variantes e extensoes",
        f"- {suggestion.get('integration_notes', '') or 'Nao informado.'}",
        "",
        "## Como aparece na literatura",
        *(f"- {item}" for item in evidence[:3]),
        *(["- Nao informado."] if not evidence else []),
        "",
        "## Conexoes com meu trabalho",
        f"- Aplicacao direta: {suggestion.get('applicability', '') or 'Nao informado.'}",
        f"- Limitacao que quero enderecar: {suggestion.get('limitations', '') or 'Nao informado.'}",
        f"- Possivel extensao: {suggestion.get('integration_notes', '') or 'Nao informado.'}",
        "",
        f"Justificativa: {suggestion.get('justification', '')}",
        "",
        "## Links",
        "- Conceitos predecessores:",
        *(f"  - {link}" for link in concept_dot_links),
        *(["  - Nao identificado automaticamente."] if not concept_dot_links else []),
        "- Conceitos dependentes:",
        "- Literature notes:",
        f"  - [[{assessment.citekey} - Literature|{assessment.citekey}]]",
    ]
    if related_links:
        lines.extend(["", "Aderencia a notas atuais:", *(f"- {link}" for link in related_links)])
    if review_tasks:
        lines.extend(["", "Pendencias de revisao:", *(f"- {task}" for task in review_tasks[:3])])
    return "\n".join(lines).strip()


def _dot_suggestion_content(suggestion: dict[str, Any], assessment: LLMAssessment, related: list[dict[str, Any]]) -> str:
    related_links = [_wikilink(str(item.get("path", "")), str(item.get("title", ""))) for item in related[:5]]
    evidence = suggestion.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence]
    review_tasks = suggestion.get("review_tasks", [])
    if isinstance(review_tasks, str):
        review_tasks = [review_tasks]
    legacy_content = str(suggestion.get("content", "") or "").strip()
    lines = [
        f"Fonte: [[{assessment.citekey} - Literature|{assessment.citekey}]]",
        f"Alvo sugerido: {suggestion.get('target', '')}",
        "",
        "## Definicao",
        f"- {suggestion.get('knowledge_claim', '') or legacy_content or 'Nao informado.'}",
        "",
        "## Essencia",
        f"- {suggestion.get('article_use', '') or 'Nao informado.'}",
        "",
        "## Contexto",
        f"- {suggestion.get('applicability', '') or 'Nao informado.'}",
        f"- Limite: {suggestion.get('limitations', '') or 'Nao informado.'}",
        "",
        "## Relacoes",
        *(f"- {link}" for link in related_links),
        *(["- Nao identificado automaticamente."] if not related_links else []),
        "",
        "## Exemplos",
        *(f"- {item}" for item in evidence[:3]),
        *(["- Nao informado."] if not evidence else []),
        "",
        "## Referencias",
        f"- [[{assessment.citekey} - Literature|{assessment.citekey}]]",
        "",
        f"Justificativa: {suggestion.get('justification', '')}",
    ]
    if review_tasks:
        lines.extend(["", "Pendencias de revisao:", *(f"- {task}" for task in review_tasks[:3])])
    return "\n".join(lines).strip()


def _moc_suggestion_content(suggestion: dict[str, Any], assessment: LLMAssessment, related: list[dict[str, Any]]) -> str:
    related_links = [_wikilink(str(item.get("path", "")), str(item.get("title", ""))) for item in related[:8]]
    review_tasks = suggestion.get("review_tasks", [])
    if isinstance(review_tasks, str):
        review_tasks = [review_tasks]
    lines = [
        f"Fonte: [[{assessment.citekey} - Literature|{assessment.citekey}]]",
        f"Alvo sugerido: {suggestion.get('target', '')}",
        "",
        "## Visao geral",
        str(suggestion.get("knowledge_claim", "") or suggestion.get("content", "") or assessment.summary or "Nao informado.").strip(),
        "",
        "## Conceitos principais",
        *(f"- {link}" for link in related_links),
        f"- [[{assessment.citekey} - Literature|{assessment.citekey}]]",
        "",
        "## Fontes",
        f"- [[{assessment.citekey} - Literature|{assessment.citekey}]]",
        *(f"- {item}" for item in suggestion.get("evidence", [])[:3] if isinstance(suggestion.get("evidence", []), list)),
        "",
        "## Integracao sugerida",
        str(suggestion.get("integration_notes", "") or "Nao informado.").strip(),
        "",
        f"Justificativa: {suggestion.get('justification', '')}",
    ]
    if review_tasks:
        lines.extend(["", "Pendencias de revisao:", *(f"- {task}" for task in review_tasks[:3])])
    return "\n".join(lines).strip()


def _integration_content(root: Path, citekey: str, assessment: LLMAssessment, related_notes: list[Path], atlas_links: list[dict[str, Any]] | None = None) -> str:
    unique = []
    seen = set()
    for note in related_notes:
        rel = str(note.relative_to(root)).replace("\\", "/")
        if rel not in seen:
            seen.add(rel)
            unique.append(note)
    draft_links = [_wikilink(str(note.relative_to(root)).replace("\\", "/"), note.stem.replace(f"{citekey} - ", "").replace(" Draft", "")) for note in unique]
    atlas = []
    seen_atlas = set()
    for item in atlas_links or []:
        path = str(item.get("path", ""))
        if path and path not in seen_atlas:
            seen_atlas.add(path)
            atlas.append(_wikilink(path, str(item.get("title", ""))))
    suggestion_lines = [
        f"- {item.get('type', 'sugestao')}: {item.get('target', '')} - {item.get('knowledge_claim') or item.get('content', '')}"
        for item in assessment.knowledge_suggestions
    ]
    return "\n".join(
        [
            "## Visao geral",
            assessment.summary,
            "",
            "## Conceitos principais",
            *(f"- {link}" for link in draft_links),
            *(["- Nenhum rascunho conceitual gerado."] if not draft_links else []),
            "",
            "Notas Atlas relacionadas:",
            *(f"- {link}" for link in atlas),
            *(["- Nenhuma nota Atlas relacionada identificada automaticamente."] if not atlas else []),
            "",
            "## Fontes",
            f"- [[{citekey} - Literature|{citekey}]]",
            "",
            "## Complementacoes sugeridas",
            *(suggestion_lines or ["- Nao informado."]),
        ]
    )


def _create_literature_draft(root: Path, citekey: str, title: str, assessment: LLMAssessment) -> Path:
    path = ensure_inside(root, root / "+" / f"{citekey} - Literature Draft.md")
    if not path.exists():
        content = "\n".join(
            [
                _inbox_frontmatter(
                    title=title,
                    target_type="literature",
                    template_source="x/Templates/LiteratureProtocolTemplate.md",
                    citekey=citekey,
                ),
                f"# {title}",
                "",
                f"Fonte Zotero/protocolo sugerida: [[Atlas/Literature/Zotero/{citekey}]]",
                f"Destino sugerido: `Atlas/Literature/{citekey} - Literature.md`",
                "",
                "## Sintese inicial",
                _literature_patch_content(assessment),
                "",
            ]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return path


def _create_suggestion_draft(
    root: Path,
    path: Path,
    note_kind: str,
    suggestion: dict[str, Any],
    assessment: LLMAssessment,
    related: list[dict[str, Any]],
) -> None:
    title = _title_for_new_note(suggestion, path)
    content = "\n".join(
        [
            _inbox_frontmatter(
                title=title,
                target_type=note_kind,
                template_source=_template_source(note_kind),
                citekey=assessment.citekey,
            ),
            f"# {title}",
            "",
            f"Destino sugerido: `{_suggested_destination(note_kind, title)}`",
            "",
            _suggestion_patch_content(suggestion, assessment, related),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_integration_draft(
    note: Path,
    title: str,
    citekey: str,
    assessment: LLMAssessment,
    related_notes: list[Path],
    atlas_links: list[dict[str, Any]],
    root: Path,
) -> None:
    content = "\n".join(
        [
            _inbox_frontmatter(
                title=f"{title} - Knowledge Integration",
                target_type="moc",
                template_source="x/Templates/MOCTemplate.md",
                citekey=citekey,
            ),
            f"# {title} - Knowledge Integration",
            "",
            f"Destino sugerido: `Atlas/Maps/{citekey} - Knowledge Integration.md`",
            "",
            _integration_content(root, citekey, assessment, related_notes, atlas_links),
            "",
        ]
    )
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(content, encoding="utf-8")


def _inbox_frontmatter(*, title: str, target_type: str, template_source: str, citekey: str) -> str:
    today = date.today().isoformat()
    return (
        "---\n"
        "type: inbox\n"
        "inbox_kind: llm_knowledge_draft\n"
        f"target_type: {target_type}\n"
        f"template_source: {template_source}\n"
        f"citekey: {citekey}\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"created: {today}\n"
        f"changed: {today}\n"
        "area: research\n"
        "review: \"\"\n"
        "tags:\n"
        "  - inbox\n"
        "  - llm-knowledge-draft\n"
        "aliases: []\n"
        "---\n"
    )


def _title_from_note(path: Path, *, fallback: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    match = re.search(r"(?m)^title:\s*(.+)$", text)
    if match:
        return match.group(1).strip().strip('"')
    heading = re.search(r"(?m)^#\s+(.+)$", text)
    return heading.group(1).strip() if heading else fallback


def _kind_from_suggestion(kind: str) -> str:
    return {
        "concept": "concept",
        "method_check": "concept",
        "dot": "dot",
        "moc": "moc",
        "literature_note_update": "literature",
    }.get(kind, "concept")


def _note_kind_from_family(family: str) -> str:
    if family.endswith("Concepts"):
        return "concept"
    if family.endswith("Dots"):
        return "dot"
    if family.endswith("Maps"):
        return "moc"
    if family.endswith("Literature"):
        return "literature"
    return "concept"


def _note_kind_from_path(path: Path) -> str:
    parts = set(path.parts)
    if "Concepts" in parts:
        return "concept"
    if "Dots" in parts:
        return "dot"
    if "Maps" in parts:
        return "moc"
    if "Literature" in parts:
        return "literature"
    return "concept"


def _title_for_new_note(suggestion: dict[str, Any], path: Path) -> str:
    return str(suggestion.get("target", "") or path.stem).strip()


def _is_inbox_draft(root: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return rel.parts[:1] == ("+",)


def _template_source(note_kind: str) -> str:
    return {
        "concept": "x/Templates/ConceptTemplate.md",
        "dot": "x/Templates/DotTemplate.md",
        "moc": "x/Templates/MOCTemplate.md",
        "literature": "x/Templates/LiteratureProtocolTemplate.md",
    }.get(note_kind, "x/Templates/NoteTemplate.md")


def _suggested_destination(note_kind: str, title: str) -> str:
    folder = {
        "concept": "Atlas/Concepts",
        "dot": "Atlas/Dots",
        "moc": "Atlas/Maps",
        "literature": "Atlas/Literature",
    }.get(note_kind, "Atlas")
    return f"{folder}/{_safe_note_stem(title)}.md"


def _safe_note_stem(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "Knowledge suggestion")[:120]


def _wikilink(path: str, title: str) -> str:
    stem = path[:-3] if path.endswith(".md") else path
    return f"[[{stem}|{title or Path(stem).name}]]"
