import json

from paper_pipeline.config import LMStudioConfig
from paper_pipeline.contracts import Stage
from paper_pipeline.lmstudio_chat import (
    LLMCompletion,
    LLMRunResult,
    LMStudioChatClient,
    run_assessment_with_retry,
    run_partitioned_assessment_with_retry,
)
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
        subject_tags = ["#soil-classification"]
    else:
        criteria_ids = ORIGINAL_DIG_CRITERIA
        statuses = ["yes", "yes", "yes", "yes", "yes"]
        action = "keep_in_dig"
        collection = Stage.TO_DIG
        gate = "pass"
        tags = ["@dig"]
        subject_tags = ["#soil-classification", "%machine-learning", "$methods-cite"]
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
            "summary": "good",
            "evidence": ["abstract"],
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


class FlakyClient:
    def __init__(self):
        self.calls = 0

    def complete_json(self, messages, schema):
        self.calls += 1
        if self.calls == 1:
            return "not json"
        return final_assessment(Stage.TO_LOOK)


class AlwaysBrokenClient:
    def complete_json(self, messages, schema):
        return "not json"


class TimeoutClient:
    def complete_json(self, messages, schema):
        raise TimeoutError("too slow")


def test_run_assessment_retries_and_returns_complete_assessment():
    result = run_assessment_with_retry(
        client=FlakyClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {}},
        max_attempts=2,
    )
    assert isinstance(result, LLMRunResult)
    assert result.status == "complete"
    assert result.assessment is not None


def test_run_assessment_returns_partial_after_retries_fail():
    result = run_assessment_with_retry(
        client=AlwaysBrokenClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {}},
        max_attempts=2,
    )
    assert result.status == "partial"
    assert len(result.errors) == 2
    assert result.raw_outputs == ["not json", "not json"]


def test_run_assessment_returns_partial_when_client_raises():
    result = run_assessment_with_retry(
        client=TimeoutClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {}},
        max_attempts=1,
    )
    assert result.status == "partial"
    assert result.raw_outputs == []
    assert "too slow" in result.errors[0]


def test_lmstudio_client_uses_json_schema_response_format(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "{}", "reasoning_content": "private reasoning"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            }

    def fake_post(url, json, timeout):
        captured["payload"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", fake_post)
    output = LMStudioChatClient(LMStudioConfig()).complete_json([], {"type": "object"})
    assert captured["payload"]["response_format"]["type"] == "json_schema"
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert captured["payload"]["max_tokens"] == 8192
    assert captured["payload"]["top_k"] == 20
    assert "chat_template_kwargs" not in captured["payload"]
    assert captured["timeout"] == 1200
    assert output == "{}"
    assert output.reasoning_content == "private reasoning"
    assert output.usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_lmstudio_client_does_not_use_reasoning_content_as_final_json(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "", "reasoning_content": "{}"}}]}

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", lambda url, json, timeout: Response())
    output = LMStudioChatClient(LMStudioConfig()).complete_json([], {"type": "object"})
    assert output == ""
    assert output.reasoning_content == "{}"


def test_lmstudio_client_can_attach_sanitized_diagnostic_payload(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", lambda url, json, timeout: Response())
    output = LMStudioChatClient(LMStudioConfig(save_payloads=True)).complete_json(
        [{"role": "user", "content": "hello"}],
        {"type": "object"},
    )
    assert output.request_payload is not None
    assert output.request_payload["messages"][0]["content"] == "hello"
    assert output.request_payload["response_format"]["json_schema"]["schema"] == {"type": "object"}


def test_assessment_messages_do_not_embed_full_schema_in_prompt():
    captured = {}

    class CapturingClient:
        def complete_json(self, messages, schema):
            captured["messages"] = messages
            return final_assessment(Stage.TO_LOOK)

    result = run_assessment_with_retry(
        client=CapturingClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )
    assert result.status == "complete"
    user_message = captured["messages"][1]["content"]
    assert "Schema:" not in user_message
    assert "additionalProperties" not in user_message
    assert "Protocol criteria:" in user_message
    assert "Output token budget" not in user_message
    assert "/no_think" not in captured["messages"][0]["content"]
    assert "/nothink" not in captured["messages"][0]["content"]
    assert "/no_think" not in user_message
    assert "/nothink" not in user_message
    assert "Concepts, Dots, MOCs" in captured["messages"][0]["content"]
    assert "Cada item deve conter knowledge_claim" not in captured["messages"][0]["content"]
    assert "Subject tag options for this stage: []" not in user_message
    assert "knowledge_suggestions must be []" in user_message
    assert "If weighted criteria score >= 3/6, recommendation_action must be move_to_revise" in user_message
    assert "If weighted criteria score < 3/6, recommendation_action must be move_to_expendable" in user_message
    assert "ToLook may recommend protocol subject tags" in user_message
    assert "recommendation_action" in user_message
    assert "gate_result" in user_message
    assert "Every protocol_criteria item must include evidence and rationale." in user_message
    assert "Return only the fields required by the response_format schema." in user_message
    assert "Subject tag options" not in user_message


def test_assessment_messages_include_subject_tag_options_for_dig():
    captured = {}

    class CapturingClient:
        def complete_json(self, messages, schema):
            captured["messages"] = messages
            return final_assessment(Stage.TO_DIG)

    result = run_assessment_with_retry(
        client=CapturingClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_DIG, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )
    assert result.status == "complete"
    user_message = captured["messages"][1]["content"]
    assert "#soil-classification" in user_message
    assert "%machine-learning" in user_message
    assert "$methods-cite" in user_message
    assert "Default article_type is original" in user_message
    assert "Use review criteria only when article_type is review with high confidence" in user_message
    assert "original articles use only the five original-paper ToDig criteria" in user_message
    assert "review articles use only the five review-paper ToDig criteria" in user_message
    assert "Knowledge suggestions allowed: yes" in user_message
    assert "never use action-only wording" in user_message
    assert "Cada item deve conter knowledge_claim" in captured["messages"][0]["content"]


def test_lmstudio_client_honors_max_response_tokens_override(monkeypatch):
    captured = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    def fake_post(url, json, timeout):
        captured.append(json)
        return Response()

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", fake_post)
    client = LMStudioChatClient(LMStudioConfig(max_output_tokens=4096))
    client.complete_json([], {"type": "object"})
    assert captured[0]["max_tokens"] == 4096


def test_lmstudio_client_sends_default_max_tokens_for_tolook_and_torevise(monkeypatch):
    payloads = []
    timeouts = []

    class Response:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    def fake_post(url, json, timeout):
        payloads.append(json)
        timeouts.append(timeout)
        if "partition" in json["response_format"]["json_schema"]["schema"].get("properties", {}):
            return Response(
                '{"partition":"triage_context","summary":"partial","evidence":["e"],'
                '"criteria_notes":["c"],"tag_hints":["#soil-classification"],"knowledge_hints":["k"]}'
            )
        stage = Stage(json["messages"][1]["content"].split("Stage: ", 1)[1].splitlines()[0])
        return Response(final_assessment(stage))

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", fake_post)
    client = LMStudioChatClient(LMStudioConfig())

    look = run_assessment_with_retry(
        client=client,
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )
    assert look.status == "complete"
    assert payloads[-1]["max_tokens"] == 2048
    assert timeouts[-1] == 1200

    payloads.clear()
    timeouts.clear()

    def fake_post_revise(url, json, timeout):
        payloads.append(json)
        timeouts.append(timeout)
        if "partition" in json["response_format"]["json_schema"]["schema"].get("properties", {}):
            partition = json["messages"][1]["content"].split("Partition: ", 1)[1].splitlines()[0]
            return Response(
                '{"partition":"'
                + partition
                + '","summary":"partial","evidence":["e"],'
                '"criteria_notes":["c"],"tag_hints":["#soil-classification"],"knowledge_hints":["k"]}'
            )
        return Response(final_assessment(Stage.TO_REVISE))

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", fake_post_revise)
    revise = run_partitioned_assessment_with_retry(
        client=client,
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short", "results": "result"}, "full_context": "ctx"},
        max_attempts=1,
    )
    assert revise.status == "complete"
    assert len(payloads) == 4
    assert {payload["max_tokens"] for payload in payloads} == {8192}
    assert set(timeouts) == {2400}


def test_lmstudio_client_sends_deep_timeout_for_todig(monkeypatch):
    payloads = []
    timeouts = []

    class Response:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    def fake_post(url, json, timeout):
        payloads.append(json)
        timeouts.append(timeout)
        if "partition" in json["response_format"]["json_schema"]["schema"].get("properties", {}):
            partition = json["messages"][1]["content"].split("Partition: ", 1)[1].splitlines()[0]
            if "equations" in json["response_format"]["json_schema"]["schema"]["properties"]:
                return Response(
                    '{"partition":"equations_formulation","summary":"math","equations":['
                    '{"label":"limit_state","latex":"g(x)=R-S","plain_language":"limit state",'
                    '"variables":[{"symbol":"R","meaning":"resistance","units":""},'
                    '{"symbol":"S","meaning":"load","units":""}],"where_used":"failure probability"}],'
                    '"parameters":[],"assumptions":["independent variables"],'
                    '"reproducibility_notes":["Use the symbols as defined in the method section."]}'
                )
            return Response(
                '{"partition":"'
                + partition
                + '","summary":"partial","evidence":["e"],'
                '"criteria_notes":["c"],"tag_hints":["#soil-classification"],"knowledge_hints":["k"]}'
            )
        return Response(final_assessment(Stage.TO_DIG))

    monkeypatch.setattr("paper_pipeline.lmstudio_chat.requests.post", fake_post)
    result = run_partitioned_assessment_with_retry(
        client=LMStudioChatClient(LMStudioConfig()),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_DIG, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short", "results": "result"}, "full_context": "ctx"},
        max_attempts=1,
    )

    assert result.status == "complete"
    assert len(payloads) == 7
    assert {payload["max_tokens"] for payload in payloads} == {8192}
    assert set(timeouts) == {2400}
    equations_payload = next(
        payload for payload in payloads if "Partition: equations_formulation" in payload["messages"][1]["content"]
    )
    equations_schema = equations_payload["response_format"]["json_schema"]["schema"]
    assert "equations" in equations_schema["properties"]
    assert "latex" in equations_schema["properties"]["equations"]["items"]["properties"]
    assert "variables" in equations_schema["properties"]["equations"]["items"]["properties"]


def test_run_assessment_preserves_usage_reasoning_and_diagnostic_payload():
    class RichClient:
        def complete_json(self, messages, schema):
            return LLMCompletion(
                final_assessment(Stage.TO_LOOK),
                reasoning_content="thinking trace",
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                request_payload={"messages": messages, "schema": schema},
            )

    result = run_assessment_with_retry(
        client=RichClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )
    assert result.status == "complete"
    assert result.usage == [{"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}]
    assert result.reasoning_outputs == ["thinking trace"]
    assert result.request_payloads[0]["schema"]["type"] == "object"


def test_run_assessment_accepts_valid_reasoning_json_when_content_is_empty():
    class ReasoningJsonClient:
        def complete_json(self, messages, schema):
            return LLMCompletion(
                "",
                reasoning_content=(
                    final_assessment(Stage.TO_LOOK)
                ),
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            )

    result = run_assessment_with_retry(
        client=ReasoningJsonClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )

    assert result.status == "complete"
    assert result.assessment is not None
    assert result.assessment.citekey == "a"
    assert result.raw_outputs[0].startswith('{"citekey":"a"')
    assert result.reasoning_outputs[0].startswith('{"citekey":"a"')
    assert result.accepted_channels == ["reasoning_content"]


def test_run_assessment_accepts_single_json_object_embedded_in_reasoning():
    class EmbeddedReasoningJsonClient:
        def complete_json(self, messages, schema):
            return LLMCompletion(
                "",
                reasoning_content=("Thinking Process:\n" + final_assessment(Stage.TO_LOOK)),
            )

    result = run_assessment_with_retry(
        client=EmbeddedReasoningJsonClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )

    assert result.status == "complete"
    assert result.assessment is not None
    assert result.accepted_channels == ["reasoning_content"]


def test_run_assessment_rejects_ambiguous_reasoning_json():
    class AmbiguousReasoningJsonClient:
        def complete_json(self, messages, schema):
            return LLMCompletion(
                "",
                reasoning_content=(final_assessment(Stage.TO_LOOK) + '{"citekey":"b"}'),
            )

    result = run_assessment_with_retry(
        client=AmbiguousReasoningJsonClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_LOOK, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short"}},
        max_attempts=1,
    )

    assert result.status == "partial"
    assert result.assessment is None
    assert result.accepted_channels == ["none"]
    assert "reasoning_content" in result.errors[0]


def test_partitioned_assessment_accepts_reasoning_json_for_partition_outputs():
    class PartitionReasoningClient:
        def __init__(self):
            self.calls = 0

        def complete_json(self, messages, schema):
            self.calls += 1
            if "partition" in schema.get("properties", {}):
                partition = messages[1]["content"].split("Partition: ", 1)[1].splitlines()[0]
                return LLMCompletion(
                    "",
                    reasoning_content=(
                        '{"partition":"'
                        + partition
                        + '","summary":"partial","evidence":["e"],'
                        '"criteria_notes":["c"],"tag_hints":["#soil-classification"],"knowledge_hints":["k"]}'
                    ),
                )
            return LLMCompletion(
                final_assessment(Stage.TO_REVISE)
            )

    result = run_partitioned_assessment_with_retry(
        client=PartitionReasoningClient(),
        candidate=CandidatePaper(citekey="a", stage=Stage.TO_REVISE, title="A"),
        reading_packet={"sections": {"abstract_keywords": "short", "results": "result"}, "full_context": "ctx"},
        max_attempts=1,
    )

    assert result.status == "complete"
    assert [item["partition"] for item in result.partition_outputs] == [
        "triage_context",
        "results_signal",
        "knowledge_suggestions",
    ]
    assert result.accepted_channels[:3] == ["reasoning_content", "reasoning_content", "reasoning_content"]
