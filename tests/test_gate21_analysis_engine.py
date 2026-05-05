import json
from pathlib import Path

from paper_pipeline.analysis_engine import LocalPaperAnalyzer
from paper_pipeline.artifacts import PaperArtifactStore
from paper_pipeline.contracts import Stage
from paper_pipeline.lmstudio_chat import LLMCompletion
from paper_pipeline.pdf_ingest import PlainTextFallbackConverter
from paper_pipeline.selection import CandidatePaper

LOOK_CRITERIA = [
    "direct_relevance",
    "comparable_methodology",
    "recent_or_seminal",
    "author_credibility",
    "explorable_gap",
    "citation_sentence_ready",
]
ORIGINAL_DIG_CRITERIA = [
    "new_method_for_toolkit",
    "reproducible_equations_and_parameters",
    "validated_results",
    "domain_applicability",
    "paper_section_value",
]


def final_assessment(stage: Stage) -> str:
    if stage == Stage.TO_LOOK:
        criteria_ids = LOOK_CRITERIA
        statuses = ["yes", "yes", "yes", "no", "no", "no"]
        action = "move_to_revise"
        collection = Stage.TO_REVISE
        gate = "pass"
        tags = ["@review"]
        subject_tags = []
    elif stage == Stage.TO_REVISE:
        criteria_ids = ORIGINAL_DIG_CRITERIA
        statuses = ["yes", "yes", "yes", "yes", "partial"]
        action = "keep_in_revise"
        collection = Stage.TO_REVISE
        gate = "hold"
        tags = ["@review"]
        subject_tags = ["#soil-classification", "%machine-learning"]
    else:
        criteria_ids = ORIGINAL_DIG_CRITERIA
        statuses = ["yes", "yes", "yes", "yes", "yes"]
        action = "keep_in_dig"
        collection = Stage.TO_DIG
        gate = "pass"
        tags = ["@dig"]
        subject_tags = ["#soil-classification", "%machine-learning"]
    criteria = [
        {
            "criterion_id": criterion_id,
            "criterion": criterion_id.replace("_", " "),
            "status": status,
            "evidence": "evidence",
            "rationale": "fits",
        }
        for criterion_id, status in zip(criteria_ids, statuses, strict=True)
    ]
    weighted = sum({"yes": 1.0, "partial": 0.5, "no": 0.0, "unknown": 0.0}[status] for status in statuses)
    return json.dumps(
        {
            "citekey": "a",
            "stage": stage.value,
            "article_type": "original",
            "review_type": "none",
            "article_type_confidence": 0.9,
            "gate_result": gate,
            "recommendation_action": action,
            "recommended_collection": collection.value,
            "recommendation_rationale": "Gate decision follows the protocol.",
            "confidence": 0.8,
            "summary": "final",
            "evidence": ["partition evidence"],
            "recommended_tags_add": tags,
            "recommended_subject_tags": subject_tags,
            "knowledge_suggestions": [],
            "protocol_criteria": criteria,
            "metrics": {
                "criteria_met": statuses.count("yes"),
                "criteria_total": len(statuses),
                "criteria_score": weighted / len(statuses),
                "evidence_coverage": 0.5,
                "decision_readiness": "medium",
            },
        },
        separators=(",", ":"),
    )


class FakeClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, messages, schema):
        self.calls.append({"messages": messages, "schema": schema})
        return LLMCompletion(
            final_assessment(Stage.TO_LOOK),
            reasoning_content="private reasoning",
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            request_payload={"messages": messages, "schema": schema},
        )


class PartitioningClient:
    def __init__(self, *, final_stage: Stage):
        self.final_stage = final_stage
        self.calls = []

    def complete_json(self, messages, schema):
        self.calls.append({"messages": messages, "schema": schema})
        if "partition" in schema.get("properties", {}):
            partition = _message_value(messages, "Partition")
            if "equations" in schema.get("properties", {}):
                return (
                    '{"partition":"equations_formulation","summary":"math","equations":['
                    '{"label":"limit_state","latex":"g(x)=R-S","plain_language":"limit state",'
                    '"variables":[{"symbol":"R","meaning":"resistance","units":""}],'
                    '"where_used":"failure probability"}],"parameters":[],"assumptions":[],'
                    '"reproducibility_notes":["Use method definitions."]}'
                )
            return (
                '{"partition":"'
                + partition
                + '","summary":"partial summary","evidence":["section evidence"],'
                '"criteria_notes":["criterion note"],"tag_hints":["#soil-classification"],'
                '"knowledge_hints":["knowledge hint"]}'
            )
        return final_assessment(self.final_stage)


def test_local_analyzer_converts_pdf_builds_packet_and_persists_outputs(tmp_path: Path):
    pdf = tmp_path / "paper.txt"
    pdf.write_text("Abstract\nsoil cpt\nIntroduction\nBayesian soil\nConclusion\nuseful", encoding="utf-8")
    store = PaperArtifactStore(tmp_path / "papers", "a")
    client = FakeClient()
    analyzer = LocalPaperAnalyzer(client=client, converters=[PlainTextFallbackConverter()], max_attempts=1)
    assessment = analyzer.analyze(
        CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="Paper", has_pdf=True, pdf_paths=[str(pdf)]),
        store,
    )
    assert assessment is not None
    assert assessment.recommended_collection == Stage.TO_REVISE
    assert len(client.calls) == 1
    assert (store.root / "reading_packets" / "to_look_latest.json").exists()
    latest = store.root / "passes" / "to_look" / "latest" / "llm_result.json"
    assert latest.exists()
    llm_result = json.loads(latest.read_text(encoding="utf-8"))
    assert llm_result["usage"] == [{"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}]
    assert llm_result["reasoning_outputs"] == ["private reasoning"]
    assert llm_result["accepted_channels"] == ["content"]
    assert llm_result["request_payloads"][0]["schema"]["type"] == "object"


def test_torevise_analyzer_partitions_llm_calls_and_persists_partition_outputs(tmp_path: Path):
    pdf = tmp_path / "paper.txt"
    pdf.write_text(
        "Abstract\nsoil cpt\nIntroduction\nBayesian soil\nResults\nstrong evidence\nConclusion\nuseful",
        encoding="utf-8",
    )
    store = PaperArtifactStore(tmp_path / "papers", "a")
    client = PartitioningClient(final_stage=Stage.TO_REVISE)
    analyzer = LocalPaperAnalyzer(client=client, converters=[PlainTextFallbackConverter()], max_attempts=1, packet_max_chars=2000)

    assessment = analyzer.analyze(
        CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="Paper", has_pdf=True, pdf_paths=[str(pdf)]),
        store,
    )

    assert assessment is not None
    assert len(client.calls) == 4
    assert [call["messages"][1]["content"].split("Partition: ")[1].splitlines()[0] for call in client.calls[:3]] == [
        "triage_context",
        "results_signal",
        "knowledge_suggestions",
    ]
    final_prompt = client.calls[-1]["messages"][1]["content"]
    assert "partition_summaries" in final_prompt
    assert "global_context" in final_prompt
    knowledge_prompt = client.calls[2]["messages"][1]["content"]
    assert "abstract_keywords" in knowledge_prompt
    assert "method_topics" in knowledge_prompt
    assert "results" in knowledge_prompt
    assert "conclusion" in knowledge_prompt
    assert "introduction" not in knowledge_prompt
    latest = store.root / "passes" / "to_revise" / "latest" / "llm_result.json"
    text = latest.read_text(encoding="utf-8")
    assert "partition_outputs" in text
    assert "triage_context" in text
    assert "knowledge_suggestions" in text


def test_todig_analyzer_partitions_method_validation_and_final_llm_calls(tmp_path: Path):
    pdf = tmp_path / "paper.txt"
    pdf.write_text(
        "Abstract\nsoil cpt\nIntroduction\nBayesian soil\nMethod\nalgorithm\nResults\nstrong evidence\n"
        "Validation\nfield data\nLimitations\nlimited site\nConclusion\nuseful",
        encoding="utf-8",
    )
    store = PaperArtifactStore(tmp_path / "papers", "a")
    client = PartitioningClient(final_stage=Stage.TO_DIG)
    analyzer = LocalPaperAnalyzer(client=client, converters=[PlainTextFallbackConverter()], max_attempts=1, packet_max_chars=2000)

    assessment = analyzer.analyze(
        CandidatePaper(citekey="a", stage=Stage.TO_DIG, title="Paper", has_pdf=True, pdf_paths=[str(pdf)]),
        store,
    )

    assert assessment is not None
    assert len(client.calls) == 7
    partition_names = [call["messages"][1]["content"].split("Partition: ")[1].splitlines()[0] for call in client.calls[:6]]
    assert partition_names == [
        "triage_context",
        "results_signal",
        "method_formulation",
        "validation_limitations",
        "equations_formulation",
        "deep_knowledge_suggestions",
    ]
    equations_prompt = client.calls[4]["messages"][1]["content"]
    assert "Partition: equations_formulation" in equations_prompt
    assert "global_context" not in equations_prompt
    assert "method_formulation" in equations_prompt
    equations_schema = client.calls[4]["schema"]
    assert "equations" in equations_schema["properties"]
    assert "latex" in equations_schema["properties"]["equations"]["items"]["properties"]
    deep_prompt = client.calls[5]["messages"][1]["content"]
    assert "Partition: deep_knowledge_suggestions" in deep_prompt
    assert "whole_paper_scan" not in deep_prompt
    assert "global_context" not in deep_prompt
    final_prompt = client.calls[-1]["messages"][1]["content"]
    assert "partition_summaries" in final_prompt
    assert "global_context" in final_prompt
    assert "full_context" not in final_prompt
    latest = store.root / "passes" / "to_dig" / "latest" / "llm_result.json"
    llm_result = json.loads(latest.read_text(encoding="utf-8"))
    assert llm_result["partition_outputs"][4]["equations"][0]["latex"] == "g(x)=R-S"


class BrokenRequiredConverter:
    name = "marker"

    def convert(self, pdf_path: Path):
        raise RuntimeError("marker unavailable")


def test_local_analyzer_records_partial_when_required_converter_fails(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    store = PaperArtifactStore(tmp_path / "papers", "a")
    analyzer = LocalPaperAnalyzer(client=FakeClient(), converters=[BrokenRequiredConverter()], max_attempts=1)
    assessment = analyzer.analyze(
        CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="Paper", has_pdf=True, pdf_paths=[str(pdf)]),
        store,
    )
    assert assessment is None
    assert analyzer.last_result is not None
    assert analyzer.last_result.status == "partial"
    assert "required converters failed: marker" in analyzer.last_result.errors


def _message_value(messages, label: str) -> str:
    for line in messages[1]["content"].splitlines():
        if line.startswith(label + ": "):
            return line.split(": ", 1)[1]
    raise AssertionError(label)
