from paper_pipeline.contracts import Stage
from paper_pipeline.reading_plan import build_reading_plan


def test_tolook_plan_reads_shallow_required_sections():
    plan = build_reading_plan(Stage.TO_LOOK)
    assert [step.name for step in plan.steps] == ["abstract_keywords", "introduction", "conclusion"]
    assert plan.max_attempts == 2


def test_torevise_plan_adds_results_and_more_passes():
    plan = build_reading_plan(Stage.TO_REVISE)
    assert [step.name for step in plan.steps] == [
        "whole_paper_scan",
        "abstract_keywords",
        "introduction",
        "conclusion",
        "method_topics",
        "results",
    ]
    assert plan.max_attempts == 4


def test_todig_plan_includes_formulation_validation_limitations_and_figures():
    plan = build_reading_plan(Stage.TO_DIG)
    names = [step.name for step in plan.steps]
    assert "method_formulation" in names
    assert "results_validation" in names
    assert "limitations_insights_conclusion" in names
    assert plan.register_figures is True
    assert plan.max_attempts == 6
