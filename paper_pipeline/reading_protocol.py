from __future__ import annotations

from dataclasses import dataclass

from .contracts import Stage


@dataclass(frozen=True)
class ProtocolCriterion:
    id: str
    label: str


TO_REVIEW_CRITERIA = [
    ProtocolCriterion("direct_relevance", "Relevancia direta ao trabalho atual"),
    ProtocolCriterion("comparable_methodology", "Metodologia identificavel e comparavel"),
    ProtocolCriterion("recent_or_seminal", "Recencia ou valor seminal/classico"),
    ProtocolCriterion("author_credibility", "Credibilidade dos autores ou venue"),
    ProtocolCriterion("explorable_gap", "Sinaliza gap exploravel"),
    ProtocolCriterion("citation_sentence_ready", "Permite escrever frase de citacao"),
]

TO_DIG_ORIGINAL_CRITERIA = [
    ProtocolCriterion("new_method_for_toolkit", "Metodo novo ainda ausente do toolkit"),
    ProtocolCriterion("reproducible_equations_and_parameters", "Equacoes, parametros e condicoes reproduziveis"),
    ProtocolCriterion("validated_results", "Resultados validados contra analitico, experimento ou campo"),
    ProtocolCriterion("domain_applicability", "Aplicavel ao dominio sem grande readaptacao conceitual"),
    ProtocolCriterion("paper_section_value", "Implementacao ou critica gera secao de paper"),
]

TO_DIG_REVIEW_CRITERIA = [
    ProtocolCriterion("defines_state_of_art", "Define estado da arte de subtopico ativo"),
    ProtocolCriterion("identifies_actionable_gaps", "Identifica gaps explicitos e acionaveis"),
    ProtocolCriterion("selective_and_transparent_review", "Selecao de papers criteriosa e transparente"),
    ProtocolCriterion("reference_mining_value", "Permite minerar referencias para ToLook"),
    ProtocolCriterion("positions_extension_or_rebuttal", "Posiciona extensao, recorte ou refutacao"),
]


def criteria_for_stage(stage: Stage) -> list[ProtocolCriterion]:
    if stage == Stage.TO_LOOK:
        return TO_REVIEW_CRITERIA
    return [*TO_DIG_ORIGINAL_CRITERIA, *TO_DIG_REVIEW_CRITERIA]


def protocol_gate_label(stage: Stage) -> str:
    if stage == Stage.TO_LOOK:
        return "Gate To Review: score >= 3/6"
    return "Gate To Dig: todos os 5 criterios do subtipo devem ser verdadeiros"
