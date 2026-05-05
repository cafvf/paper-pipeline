from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re
from typing import Any

from .contracts import (
    CollectionAction,
    DecisionState,
    FullDecision,
    KnowledgeAction,
    KnowledgeActions,
    KnowledgeSuggestionDecision,
    MissingPdfAction,
    MissingPdfDecision,
    PartialAnalysisAction,
    PartialAnalysisDecision,
    ValidationError,
    coerce_str_list,
    normalize_citekey,
)


FRONTMATTER_RE = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
HUMAN_DECISION_RE = re.compile(r"```yaml\n(?P<yaml>.*?)\n```", re.DOTALL)


def decision_note_path(inbox_dir: str | Path, citekey: str) -> Path:
    return Path(inbox_dir) / f"{normalize_citekey(citekey)} - LLM Paper Decision.md"


def render_full_decision_note(
    *,
    citekey: str,
    title: str,
    current_collection: str,
    recommended_collection: str,
    recommended_tags_add: list[str],
    recommended_tags_remove: list[str] | None = None,
    body_sections: list[str] | None = None,
    existing_decision: FullDecision | None = None,
) -> str:
    decision = existing_decision or FullDecision()
    frontmatter = _frontmatter(
        citekey=citekey,
        title=title,
        status="pending",
        analysis_status="complete",
    )
    sections = [
        f"# {title}",
        "",
        "## Resumo",
        f"- Citekey: `{citekey}`",
        f"- Colecao atual: `{current_collection}`",
        f"- Recomendacao: `{recommended_collection}`",
        "",
        "## Tags recomendadas",
        "- Adicionar: " + (", ".join(f"`{tag}`" for tag in recommended_tags_add) or "nenhuma"),
        "- Remover: " + (", ".join(f"`{tag}`" for tag in (recommended_tags_remove or [])) or "nenhuma"),
        "",
        *_clean_sections(body_sections or []),
        "## Guia de decisao",
        *_full_decision_guide_lines(),
        "",
        "## Decisao humana",
        "```yaml",
        _dump_yaml(_full_decision_to_mapping(decision)),
        "```",
        "",
    ]
    return _render_note(frontmatter, "\n".join(sections))


def render_missing_pdf_note(*, citekey: str, title: str, current_collection: str, existing: MissingPdfDecision | None = None) -> str:
    decision = existing or MissingPdfDecision()
    frontmatter = _frontmatter(citekey=citekey, title=title, status="pending", analysis_status="missing_pdf")
    body = "\n".join(
        [
            f"# {title}",
            "",
            "## PDF ausente",
            f"- Citekey: `{citekey}`",
            f"- Colecao atual: `{current_collection}`",
            "- O item foi selecionado pela prioridade, mas nao tem PDF disponivel.",
            "",
            "## Guia de decisao",
            *_missing_pdf_decision_guide_lines(),
            "",
            "## Decisao humana",
            "```yaml",
            _dump_yaml(
                {
                    "decision_state": decision.decision_state.value,
                    "missing_pdf_action": decision.missing_pdf_action.value,
                    "manual_notes": decision.manual_notes,
                }
            ),
            "```",
            "",
        ]
    )
    return _render_note(frontmatter, body)


def render_partial_analysis_note(*, citekey: str, title: str, reason: str, existing: PartialAnalysisDecision | None = None) -> str:
    decision = existing or PartialAnalysisDecision()
    frontmatter = _frontmatter(citekey=citekey, title=title, status="pending", analysis_status="partial")
    body = "\n".join(
        [
            f"# {title}",
            "",
            "## Analise parcial",
            f"- Citekey: `{citekey}`",
            f"- Motivo: {reason}",
            "- Esta nota nao autoriza promocao/descarte automatico baseado na LLM.",
            "",
            "## Guia de decisao",
            *_partial_analysis_decision_guide_lines(),
            "",
            "## Decisao humana",
            "```yaml",
            _dump_yaml(
                {
                    "decision_state": decision.decision_state.value,
                    "partial_analysis_action": decision.partial_analysis_action.value,
                    "manual_notes": decision.manual_notes,
                }
            ),
            "```",
            "",
        ]
    )
    return _render_note(frontmatter, body)


def parse_decision_from_text(text: str) -> FullDecision | MissingPdfDecision | PartialAnalysisDecision:
    match = HUMAN_DECISION_RE.search(text)
    if not match:
        raise ValidationError("decision YAML block not found")
    raw = _load_yaml(match.group("yaml"))
    if "missing_pdf_action" in raw:
        decision = MissingPdfDecision(
            decision_state=DecisionState(raw.get("decision_state", "pending")),
            missing_pdf_action=MissingPdfAction(raw.get("missing_pdf_action", "attach_pdf")),
            manual_notes=str(raw.get("manual_notes", "") or ""),
        )
        return decision
    if "partial_analysis_action" in raw:
        decision = PartialAnalysisDecision(
            decision_state=DecisionState(raw.get("decision_state", "pending")),
            partial_analysis_action=PartialAnalysisAction(raw.get("partial_analysis_action", "retry_next_run")),
            manual_notes=str(raw.get("manual_notes", "") or ""),
        )
        return decision
    suggestions = []
    knowledge_raw = dict(raw.get("knowledge_actions", {}) or {})
    for item in list(knowledge_raw.get("suggestions", []) or []):
        suggestions.append(
            KnowledgeSuggestionDecision(
                id=str(item.get("id", "")),
                action=KnowledgeAction(item.get("action", "defer")),
                target_note=str(item.get("target_note", "") or ""),
                notes=str(item.get("notes", "") or ""),
            )
        )
    decision = FullDecision(
        decision_state=DecisionState(raw.get("decision_state", "pending")),
        apply_zotero_actions=bool(raw.get("apply_zotero_actions", True)),
        collection_action=CollectionAction(raw.get("collection_action", "accept_recommendation")),
        override_collection=str(raw.get("override_collection", "") or ""),
        apply_recommended_tags=bool(raw.get("apply_recommended_tags", True)),
        tag_overrides_add=coerce_str_list(raw.get("tag_overrides_add", [])),
        tag_overrides_remove=coerce_str_list(raw.get("tag_overrides_remove", [])),
        apply_knowledge_actions=bool(raw.get("apply_knowledge_actions", False)),
        knowledge_actions=KnowledgeActions(
            literature_note=KnowledgeAction(knowledge_raw.get("literature_note", {}).get("action", "defer"))
            if isinstance(knowledge_raw.get("literature_note"), dict)
            else KnowledgeAction.DEFER,
            suggestions=suggestions,
        ),
        manual_notes=str(raw.get("manual_notes", "") or ""),
    )
    validate_full_decision(decision)
    return decision


def validate_full_decision(decision: FullDecision) -> None:
    if decision.decision_state == DecisionState.REJECTED and decision.collection_action == CollectionAction.ACCEPT_RECOMMENDATION:
        raise ValidationError("rejected decisions require a collection_action other than accept_recommendation")


def _frontmatter(*, citekey: str, title: str, status: str, analysis_status: str) -> dict[str, Any]:
    return {
        "type": "inbox",
        "inbox_kind": "llm_paper_decision",
        "citekey": normalize_citekey(citekey),
        "title": title,
        "decision_status": status,
        "analysis_status": analysis_status,
        "tags": ["inbox", "zotero", "llm-paper-decision"],
        "aliases": [],
    }


def _render_note(frontmatter: dict[str, Any], body: str) -> str:
    return "---\n" + _dump_yaml(frontmatter) + "---\n" + body


def _dump_yaml(mapping: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in mapping.items():
        lines.extend(_yaml_lines(key, value, 0))
    return "\n".join(lines) + "\n"


def _yaml_lines(key: str, value: Any, indent: int) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines = [f"{prefix}{key}:"]
        for sub_key, sub_value in value.items():
            lines.extend(_yaml_lines(str(sub_key), sub_value, indent + 2))
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}{key}: []"]
        lines = [f"{prefix}{key}:"]
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}  -")
                for sub_key, sub_value in item.items():
                    lines.extend(_yaml_lines(str(sub_key), sub_value, indent + 4))
            else:
                lines.append(f"{prefix}  - {item!r}" if _needs_quote(str(item)) else f"{prefix}  - {item}")
        return lines
    scalar = str(value).lower() if isinstance(value, bool) else str(value)
    if value == "":
        scalar = '""'
    elif _needs_quote(scalar):
        scalar = repr(scalar)
    return [f"{prefix}{key}: {scalar}"]


def _needs_quote(value: str) -> bool:
    return value == "" or value.startswith(("@", "!", "#")) or ": " in value


def _load_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text) or {}
    except ImportError:
        loaded = _simple_yaml_parse(text)
    if not isinstance(loaded, dict):
        raise ValidationError("decision YAML must be a mapping")
    return loaded


def _simple_yaml_parse(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("-"):
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _full_decision_to_mapping(decision: FullDecision) -> dict[str, Any]:
    data = asdict(decision)
    data["decision_state"] = decision.decision_state.value
    data["collection_action"] = decision.collection_action.value
    data["knowledge_actions"] = {
        "literature_note": {"action": decision.knowledge_actions.literature_note.value},
        "suggestions": [
            {
                "id": item.id,
                "action": item.action.value,
                "target_note": item.target_note,
                "notes": item.notes,
            }
            for item in decision.knowledge_actions.suggestions
        ],
    }
    return data


def _clean_sections(sections: list[str]) -> list[str]:
    cleaned = []
    for section in sections:
        if section.strip():
            cleaned.extend([section.rstrip(), ""])
    return cleaned


def _full_decision_guide_lines() -> list[str]:
    return [
        "- `decision_state`: `pending`, `approved`, `rejected`, `deferred`, `manual_only`.",
        "- `apply_zotero_actions`: `true` aplica Zotero; `false` nao aplica colecao/tags.",
        "- `collection_action`: `accept_recommendation`, `keep_current`, `move_to_tolook`, `move_to_revise`, `move_to_dig`, `move_to_expendable`, `no_collection_change`, `manual_only`.",
        "- `override_collection`: texto livre reservado para anotacao manual; o aplicador automatico ainda usa `collection_action`.",
        "- `apply_recommended_tags`: `true` aplica tags recomendadas; `false` ignora tags recomendadas.",
        "- `tag_overrides_add`: lista YAML de tags extras, ex. [`@review`].",
        "- `tag_overrides_remove`: lista YAML de tags para remover.",
        "- `apply_knowledge_actions`: `false` nao aplica conhecimento; `true` aplica a camada local em Atlas/Literature, notas Atlas relacionadas e MOC de integracao.",
        "- `knowledge_actions.literature_note.action`: `create_new`, `update_existing`, `link_existing`, `reject`, `defer`.",
        "- `knowledge_actions.suggestions`: opcional; sem itens, `apply_knowledge_actions: true` aplica todas as sugestoes estruturadas da LLM.",
        "- `manual_notes`: texto livre para justificar sua decisao.",
        "- Regra: `rejected` exige `collection_action` diferente de `accept_recommendation`.",
        "- Efeito: `manual_only` registra decisao externa e remove esta nota do inbox.",
    ]


def _missing_pdf_decision_guide_lines() -> list[str]:
    return [
        "- `decision_state`: `pending`, `approved`, `rejected`, `deferred`, `manual_only`.",
        "- `missing_pdf_action`: `attach_pdf`, `defer`, `move_to_expendable`, `manual_only`.",
        "- `manual_notes`: texto livre para explicar a decisao.",
        "- Efeito: `move_to_expendable` so aplica descarte se houver plano Zotero para Expendable.",
        "- Efeito: `manual_only` registra decisao externa e remove esta nota do inbox.",
    ]


def _partial_analysis_decision_guide_lines() -> list[str]:
    return [
        "- `decision_state`: `pending`, `approved`, `rejected`, `deferred`, `manual_only`.",
        "- `partial_analysis_action`: `retry_next_run`, `defer`, `move_to_expendable`, `manual_only`.",
        "- `manual_notes`: texto livre para explicar a decisao.",
        "- Efeito: `approved` + `retry_next_run` remove esta nota e libera nova tentativa no proximo run.",
        "- Efeito: `move_to_expendable` so aplica descarte se houver plano Zotero para Expendable.",
        "- Efeito: `manual_only` registra decisao externa e remove esta nota do inbox.",
    ]
