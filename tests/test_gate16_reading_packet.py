from paper_pipeline.contracts import Stage
from paper_pipeline.reading_packet import build_reading_packet
from paper_pipeline.selection import CandidatePaper


def test_build_reading_packet_extracts_stage_sections_and_keeps_context_budget():
    converted = {
        "pages": [
            {
                "page": 1,
                "text": "Abstract\nA soil Bayesian CPT study.\nKeywords: cpt; uncertainty\nIntroduction\nThe gap is offshore soil.",
            },
            {"page": 2, "text": "Methods\nLong method.\nResults\nStrong validation.\nConclusion\nUseful for reliability."},
        ]
    }
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="Paper", abstract="metadata abstract"),
        converted_documents=[converted],
        max_chars=700,
    )
    assert packet["stage"] == ".To Revise"
    assert "abstract_keywords" in packet["sections"]
    assert "results" in packet["sections"]
    assert "method_topics" in packet["sections"]
    assert "method_formulation" not in packet["sections"]
    assert len(packet["full_context"]) <= 700


def test_torevise_method_topics_extracts_between_introduction_and_case_or_results():
    converted = {
        "pages": [
            {
                "page": 1,
                "text": (
                    "Abstract\nA geological trend paper.\n"
                    "1 Introduction\nThe introduction frames the research gap.\n"
                    "2 Geological trend modelling under uncertainty\n"
                    "The formulation defines radius optimized moving averages and proportion constraints.\n"
                    "Equations describe categorical proportions.\n"
                    "3 Case Study\nCase details should not enter method topics.\n"
                    "4 Results\nResults should not enter method topics."
                ),
            }
        ]
    }
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="Paper"),
        converted_documents=[converted],
        max_chars=1200,
    )

    method_topics = packet["sections"]["method_topics"]
    assert "Geological trend modelling under uncertainty" in method_topics
    assert "radius optimized moving averages" in method_topics
    assert "The introduction frames" not in method_topics
    assert "Case details" not in method_topics
    assert "Results should not enter" not in method_topics


def test_todig_method_formulation_uses_same_interval_when_method_heading_is_custom():
    converted = {
        "pages": [
            {
                "page": 1,
                "text": (
                    "Abstract\nA CPT paper.\n"
                    "1 Introduction\nThe introduction motivates the method.\n"
                    "2 Bayesian sparse CPT stratification\n"
                    "The formulation defines joint sparse representation and Bayesian inference.\n"
                    "The equations couple Qt and FR.\n"
                    "3 Results\nBenchmark results should not enter method formulation.\n"
                    "4 Conclusion\nThe conclusion should not enter method formulation."
                ),
            }
        ]
    }
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_DIG, title="Paper"),
        converted_documents=[converted],
        max_chars=1200,
    )

    method_formulation = packet["sections"]["method_formulation"]
    assert "Bayesian sparse CPT stratification" in method_formulation
    assert "joint sparse representation" in method_formulation
    assert "The introduction motivates" not in method_formulation
    assert "Benchmark results" not in method_formulation
    assert "The conclusion should not enter" not in method_formulation


def test_build_reading_packet_prefers_numbered_section_headings_over_pdf_front_matter():
    converted = {
        "pages": [
            {
                "page": 1,
                "text": (
                    "Title\n"
                    "Abstract\nThis abstract says the introduction motivates CPT reliability.\n"
                    "Table of contents\nIntroduction 1\nConclusion 9\n"
                    "1 Introduction\nThe real introduction gap is offshore uncertainty.\n"
                    "2 Methods\nMethod details.\n"
                ),
            },
            {"page": 2, "text": "5 Conclusion\nThe real conclusion is actionable."},
        ]
    }
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="Paper"),
        converted_documents=[converted],
        max_chars=600,
    )
    assert packet["sections"]["introduction"].startswith("1 Introduction")
    assert "real introduction gap" in packet["sections"]["introduction"]
    assert "Title\nAbstract" not in packet["sections"]["introduction"]
    assert packet["sections"]["conclusion"].startswith("5 Conclusion")


def test_tolook_packet_sends_only_title_abstract_intro_and_conclusion_sections():
    converted = {
        "pages": [
            {
                "page": 1,
                "text": (
                    "Abstract\nA geological trend paper.\n"
                    "Keywords: facies; uncertainty\n"
                    "1 Introduction\nThe introduction frames the triage question.\n"
                    "2 Methods\nDetailed method should not be a ToLook section.\n"
                    "3 Results\nDetailed results should not be a ToLook section.\n"
                    "4 Conclusion\nThe conclusion states the contribution."
                ),
            }
        ]
    }
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="Paper", abstract="metadata abstract"),
        converted_documents=[converted],
        max_chars=1000,
    )

    assert packet["title"] == "Paper"
    assert packet["metadata_abstract"] == "metadata abstract"
    assert set(packet["sections"]) == {"abstract_keywords", "introduction", "conclusion"}
    assert "whole_paper_scan" not in packet["sections"]
    assert "results" not in packet["sections"]
    assert "method_formulation" not in packet["sections"]


def test_todig_packet_records_figures_when_present():
    converted = {"pages": [{"page": 1, "text": "Figure 1. Workflow.\nMethod\nEquation y = ax.\nConclusion\nOK."}]}
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_DIG, title="Paper", abstract="soil"),
        converted_documents=[converted],
    )
    assert packet["figures"] == [{"page": 1, "caption": "Figure 1. Workflow."}]


def test_build_reading_packet_flattens_marker_block_tree():
    marker_json = [
        {
            "id": "page-1",
            "block_type": "Page",
            "children": [
                {"block_type": "SectionHeader", "html": "Abstract"},
                {"block_type": "Text", "html": "A probabilistic CPT study."},
                {"block_type": "SectionHeader", "html": "Introduction"},
                {"block_type": "Text", "html": "The real introduction appears in Marker blocks."},
                {"block_type": "SectionHeader", "html": "Conclusion"},
                {"block_type": "Text", "html": "Useful for reliability screening."},
            ],
        }
    ]
    packet = build_reading_packet(
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="Paper"),
        converted_documents=[marker_json],
        max_chars=1000,
    )
    assert "A probabilistic CPT study." in packet["sections"]["abstract_keywords"]
    assert "real introduction appears" in packet["sections"]["introduction"]
    assert "Useful for reliability screening" in packet["sections"]["conclusion"]
