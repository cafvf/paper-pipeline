from __future__ import annotations

from dataclasses import dataclass

from .contracts import Stage


@dataclass(frozen=True)
class ReadingStep:
    name: str
    purpose: str
    sections: list[str]


@dataclass(frozen=True)
class ReadingPlan:
    stage: Stage
    max_attempts: int
    register_figures: bool
    steps: list[ReadingStep]


def build_reading_plan(stage: Stage) -> ReadingPlan:
    steps = [
        ReadingStep("abstract_keywords", "avaliar sinal tematico inicial", ["abstract", "keywords"]),
        ReadingStep("introduction", "identificar problema, gap e aderencia aos Efforts", ["introduction"]),
        ReadingStep("conclusion", "avaliar contribuicao e limites declarados", ["conclusion"]),
    ]
    max_attempts = 2
    register_figures = False
    if stage in {Stage.TO_REVISE, Stage.TO_DIG}:
        steps.insert(0, ReadingStep("whole_paper_scan", "preservar contexto geral", ["all"]))
        steps.append(ReadingStep("results", "avaliar conhecimento aproveitavel", ["results", "discussion"]))
        max_attempts = 4
    if stage == Stage.TO_REVISE:
        results_index = next(index for index, step in enumerate(steps) if step.name == "results")
        steps.insert(
            results_index,
            ReadingStep("method_topics", "identificar formulacoes e assuntos entre introducao e estudos/resultados", ["method_topics"]),
        )
    if stage == Stage.TO_DIG:
        steps.extend(
            [
                ReadingStep("method_formulation", "extrair formulacao, algoritmo e suposicoes", ["method", "methodology", "formulation"]),
                ReadingStep("results_validation", "avaliar testes, validacao e reprodutibilidade", ["validation", "results"]),
                ReadingStep(
                    "limitations_insights_conclusion",
                    "registrar limites, insights e encaixe conceitual",
                    ["limitations", "insights", "conclusion"],
                ),
            ]
        )
        max_attempts = 6
        register_figures = True
    return ReadingPlan(stage=stage, max_attempts=max_attempts, register_figures=register_figures, steps=steps)
