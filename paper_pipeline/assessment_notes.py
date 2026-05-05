from __future__ import annotations

from .contracts import OPERATIONAL_LLM_TAGS, READING_PROTOCOL_LLM_TAGS
from .decision_notes import render_full_decision_note, render_partial_analysis_note
from .llm_schema import LLMAssessment
from .lmstudio_chat import LLMRunResult
from .selection import CandidatePaper


def render_note_from_assessment(
    *,
    assessment: LLMAssessment,
    title: str,
    current_collection: str,
    artifact_links: dict[str, str] | None = None,
) -> str:
    sections = [
        "## Contrato de decisao",
        f"- Acao recomendada: `{assessment.recommendation_action or 'nao informado'}`",
        f"- Resultado do gate: `{assessment.gate_result or 'nao informado'}`",
        f"- Tipo de artigo: `{assessment.article_type or 'nao informado'}`",
        f"- Subtipo revisional: `{assessment.review_type or 'none'}`",
        f"- Confianca no tipo: `{assessment.article_type_confidence:.2f}`",
        f"- Racional da recomendacao: {assessment.recommendation_rationale or 'Nao informado'}",
        "",
        "## Avaliacao LLM",
        f"- Confianca: `{assessment.confidence:.2f}`",
        *_format_metrics(assessment.metrics),
        f"- Resumo: {assessment.summary}",
        "",
        *_format_protocol_criteria(assessment.protocol_criteria),
        "## Evidencias",
        *(f"- {item}" for item in assessment.evidence),
        "",
    ]
    if assessment.recommended_subject_tags:
        sections.extend(
            [
                "## Tags de assunto sugeridas",
                *(f"- `{tag}`" for tag in assessment.recommended_subject_tags),
                "",
            ]
        )
    if assessment.knowledge_suggestions:
        sections.extend(["## Sugestoes de conhecimento"])
        for suggestion in assessment.knowledge_suggestions:
            sections.append(_format_knowledge_suggestion(suggestion))
        sections.append("")
    if artifact_links:
        sections.extend(["## Artefatos"])
        sections.extend(f"- {name}: `{path}`" for name, path in artifact_links.items())
        sections.append("")
    warnings = assessment.metrics.get("warnings", []) if assessment.metrics else []
    if warnings:
        sections.extend(["## Avisos"])
        sections.extend(f"- `{warning}`" for warning in warnings)
        sections.append("")
    return render_full_decision_note(
        citekey=assessment.citekey,
        title=title,
        current_collection=current_collection,
        recommended_collection=assessment.recommended_collection.value,
        recommended_tags_add=_recommended_tags(assessment),
        body_sections=["\n".join(sections)],
    )


def render_partial_note_from_llm_result(*, candidate: CandidatePaper, result: LLMRunResult) -> str:
    reason = "; ".join(result.errors) or "LLM output did not pass validation"
    body = [f"Ultimos outputs brutos: `{len(result.raw_outputs)}`", "", "Erros:", *(f"- {error}" for error in result.errors)]
    return render_partial_analysis_note(citekey=candidate.citekey, title=candidate.title, reason=reason, existing=None).replace(
        "## Decisao humana",
        "\n".join(body) + "\n\n## Decisao humana",
        1,
    )


def _recommended_tags(assessment: LLMAssessment) -> list[str]:
    tags = [tag for tag in assessment.recommended_tags_add if tag in READING_PROTOCOL_LLM_TAGS]
    operational = OPERATIONAL_LLM_TAGS.get(assessment.stage)
    if operational and operational not in tags:
        tags.insert(0, operational)
    return tags


def _format_knowledge_suggestion(suggestion: dict) -> str:
    identifier = str(suggestion.get("id", "") or "").strip()
    kind = str(suggestion.get("type", "") or suggestion.get("action", "") or "sugestao").strip()
    target = str(suggestion.get("target", "") or suggestion.get("target_note", "") or "").strip()
    content = str(
        suggestion.get("knowledge_claim", "")
        or suggestion.get("summary", "")
        or suggestion.get("content", "")
        or suggestion.get("notes", "")
        or ""
    ).strip()
    article_use = str(suggestion.get("article_use", "") or "").strip()
    applicability = str(suggestion.get("applicability", "") or "").strip()
    justification = str(suggestion.get("justification", "") or "").strip()
    parts = []
    if identifier:
        parts.append(f"ID: `{identifier}`")
    if kind:
        parts.append(f"Tipo: `{kind}`")
    if target:
        parts.append(f"Alvo: `{target}`")
    if content:
        parts.append(f"Conhecimento: {content}")
    if article_use:
        parts.append(f"Uso no artigo: {article_use}")
    if applicability:
        parts.append(f"Aplicabilidade: {applicability}")
    if justification:
        parts.append(f"Justificativa: {justification}")
    if not parts:
        return "- Sugestao sem conteudo estruturado."
    text = "; ".join(parts)
    return "- " + (text if text.endswith((".", "!", "?")) else text + ".")


def _format_metrics(metrics: dict) -> list[str]:
    if not metrics:
        return []
    lines = []
    if "criteria_met" in metrics and "criteria_total" in metrics:
        lines.append(f"- Criterios atendidos: `{metrics['criteria_met']}/{metrics['criteria_total']}`")
    if "criteria_score" in metrics:
        lines.append(f"- Score dos criterios: `{float(metrics['criteria_score']):.2f}`")
    if "evidence_coverage" in metrics:
        lines.append(f"- Cobertura de evidencias: `{float(metrics['evidence_coverage']):.2f}`")
    if metrics.get("decision_readiness"):
        lines.append(f"- Prontidao da decisao: `{metrics['decision_readiness']}`")
    if metrics.get("protocol_gate"):
        lines.append(f"- Gate do protocolo: {metrics['protocol_gate']}")
    return lines


def _format_protocol_criteria(criteria: list[dict]) -> list[str]:
    if not criteria:
        return []
    lines = [
        "## Criterios do protocolo",
        "| Criterio | Status | Evidencia | Racional |",
        "| --- | --- | --- | --- |",
    ]
    for criterion in criteria:
        label = str(criterion.get("criterion", "") or criterion.get("criterion_id", "")).strip()
        status = _format_status(str(criterion.get("status", "unknown")))
        evidence = _cell(str(criterion.get("evidence", "") or "Nao informado"))
        rationale = _cell(str(criterion.get("rationale", "") or "Nao informado"))
        lines.append(f"| {_cell(label)} | {status} | {evidence} | {rationale} |")
    lines.append("")
    return lines


def _format_status(status: str) -> str:
    labels = {
        "yes": "sim",
        "partial": "parcial",
        "no": "nao",
        "unknown": "incerto",
    }
    return f"`{labels.get(status, status)}`"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
