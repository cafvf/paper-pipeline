from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from .config import LMStudioConfig
from .contracts import READING_PROTOCOL_SUBJECT_TAGS, Stage
from .llm_schema import LLMAssessment, parse_llm_assessment, render_schema_for_stage
from .reading_protocol import criteria_for_stage, protocol_gate_label
from .selection import CandidatePaper


class LLMCompletion(str):
    def __new__(
        cls,
        content: str,
        *,
        reasoning_content: str = "",
        usage: dict[str, Any] | None = None,
        request_payload: dict[str, Any] | None = None,
    ):
        obj = str.__new__(cls, content)
        obj.reasoning_content = reasoning_content
        obj.usage = usage
        obj.request_payload = request_payload
        return obj


class ChatJsonClient(Protocol):
    def complete_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str | LLMCompletion: ..


@dataclass
class LLMRunResult:
    status: str
    assessment: LLMAssessment | None = None
    raw_outputs: list[str] = field(default_factory=list)
    partition_outputs: list[dict[str, Any]] = field(default_factory=list)
    usage: list[dict[str, Any]] = field(default_factory=list)
    reasoning_outputs: list[str] = field(default_factory=list)
    request_payloads: list[dict[str, Any]] = field(default_factory=list)
    accepted_channels: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LMStudioChatClient:
    def __init__(self, config: LMStudioConfig) -> None:
        self.config = config

    def complete_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> LLMCompletion:
        budget = _budget_for_messages(messages, self.config)
        payload = {
            "model": self.config.analysis_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": budget["max_tokens"],
            "top_k": 20,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "paper_assessment", "strict": True, "schema": schema},
            },
        }
        response = requests.post(self.config.chat_endpoint, json=payload, timeout=budget["timeout_seconds"])
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        return LLMCompletion(
            str(message.get("content") or ""),
            reasoning_content=str(message.get("reasoning_content") or ""),
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
            request_payload=payload if self.config.save_payloads else None,
        )


def run_assessment_with_retry(
    *,
    client: ChatJsonClient,
    candidate: CandidatePaper,
    reading_packet: dict[str, Any],
    max_attempts: int,
) -> LLMRunResult:
    schema = render_schema_for_stage(candidate.stage)
    messages = _messages(candidate, reading_packet, schema)
    result = LLMRunResult(status="partial")
    for _ in range(max_attempts):
        completion = None
        try:
            completion = _normalize_completion(client.complete_json(messages, schema))
            accepted_text, channel = _accepted_json_from_completion(completion, parser=parse_llm_assessment)
            _record_completion(result, completion, accepted_text=accepted_text, accepted_channel=channel)
            result.assessment = parse_llm_assessment(accepted_text)
            result.status = "complete"
            return result
        except Exception as exc:
            if completion is not None:
                _record_completion(result, completion, accepted_text=str(completion), accepted_channel="none")
            result.errors.append(str(exc))
            messages.append({"role": "user", "content": "Retorne apenas um objeto JSON valido aderente ao schema. Sem prosa."})
    return result


def run_partitioned_assessment_with_retry(
    *,
    client: ChatJsonClient,
    candidate: CandidatePaper,
    reading_packet: dict[str, Any],
    max_attempts: int,
) -> LLMRunResult:
    if candidate.stage == Stage.TO_LOOK:
        return run_assessment_with_retry(
            client=client,
            candidate=candidate,
            reading_packet=reading_packet,
            max_attempts=max_attempts,
        )
    result = LLMRunResult(status="partial")
    partitions = _partitions_for_stage(candidate.stage)
    for partition in partitions:
        partition_schema = _partition_schema_for_partition(partition)
        section_packet = _packet_for_partition(reading_packet, partition)
        messages = _partition_messages(candidate, partition, section_packet)
        completion = None
        try:
            completion = _normalize_completion(client.complete_json(messages, partition_schema))
            accepted_text, channel = _accepted_json_from_completion(
                completion,
                parser=lambda text, partition=partition: _parse_partition_output(text, partition),
            )
            _record_completion(result, completion, accepted_text=accepted_text, accepted_channel=channel)
            parsed = _parse_partition_output(accepted_text, partition)
            result.partition_outputs.append(parsed)
        except Exception as exc:
            if completion is not None:
                _record_completion(result, completion, accepted_text=str(completion), accepted_channel="none")
            result.errors.append(f"{partition['name']}: {exc}")
            return result
    final_packet = _final_packet_from_partitions(candidate, reading_packet, result.partition_outputs)
    final = run_assessment_with_retry(
        client=client,
        candidate=candidate,
        reading_packet=final_packet,
        max_attempts=max_attempts,
    )
    result.raw_outputs.extend(final.raw_outputs)
    result.usage.extend(final.usage)
    result.reasoning_outputs.extend(final.reasoning_outputs)
    result.request_payloads.extend(final.request_payloads)
    result.accepted_channels.extend(final.accepted_channels)
    result.errors.extend(final.errors)
    result.assessment = final.assessment
    result.status = final.status
    return result


def _messages(candidate: CandidatePaper, reading_packet: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, str]]:
    criteria = [{"criterion_id": item.id, "criterion": item.label} for item in criteria_for_stage(candidate.stage)]
    packet_json = json.dumps(reading_packet, ensure_ascii=False, separators=(",", ":"))
    if candidate.stage == Stage.TO_LOOK:
        user_content = (
            f"Citekey: {candidate.citekey}\n"
            f"Stage: {candidate.stage.value}\n"
            f"Protocol gate: {protocol_gate_label(candidate.stage)}\n"
            f"Protocol criteria: {criteria}\n"
            "Return only the fields required by the response_format schema. "
            "Include article_type, review_type, article_type_confidence, gate_result, recommendation_action, "
            "recommended_collection and recommendation_rationale. "
            "ToLook is triage only: decide whether the paper deserves To Revise from title/abstract/available triage text. "
            "ToLook may recommend protocol subject tags, but knowledge_suggestions must be []. "
            "If weighted criteria score >= 3/6, recommendation_action must be move_to_revise, "
            "recommended_collection must be .To Revise and recommended_tags_add must include @review. "
            "If weighted criteria score < 3/6, recommendation_action must be move_to_expendable, "
            "recommended_collection must be Expendable and recommended_tags_add must include !discarded. "
            "Use max 6 evidence items. Every protocol_criteria item must include evidence and rationale.\n"
            f"Packet JSON: {packet_json}"
        )
    else:
        user_content = (
            f"Citekey: {candidate.citekey}\n"
            f"Stage: {candidate.stage.value}\n"
            f"Protocol gate: {protocol_gate_label(candidate.stage)}\n"
            f"Protocol criteria: {criteria}\n"
            "Return the JSON fields required by the response_format schema. "
            "Default article_type is original. Use review criteria only when article_type is review with high confidence. "
            "For To Revise and ToDig, original articles use only the five original-paper ToDig criteria, "
            "and review articles use only the five review-paper ToDig criteria. "
            "If all five criteria for the chosen article_type are yes, recommendation_action must be move_to_dig. "
            "If not all five are yes but the paper remains useful, recommendation_action must be keep_in_revise. "
            "Use move_to_expendable only when the paper lacks clear use; include !discarded then. "
            "Keep output compact: max 6 evidence items, one protocol_criteria object per criterion_id, "
            "short evidence/rationale strings, no duplicated tags or duplicated criteria. "
            "Every protocol_criteria item must include evidence and rationale. "
            f"{_knowledge_instruction(candidate.stage)} "
            f"Subject tag options for this stage: {_subject_tag_options(candidate.stage)}. "
            f"{_knowledge_quality_instruction(candidate.stage)}\n"
            f"Packet JSON: {packet_json}"
        )
    return [
        {
            "role": "system",
            "content": _system_message(candidate.stage),
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]


def _system_message(stage: Stage) -> str:
    base = (
        "Voce avalia artigos segundo o Reading Protocol do vault. "
        "Responda somente JSON valido. Comece diretamente com { e termine com }. "
        "Nao inclua markdown fences ou prosa no campo de resposta final. "
        "Preserve markdown/latex nas evidencias. "
        "Use recommended_tags_add apenas para tags operacionais do schema. "
        "Preencha protocol_criteria com cada criterio aplicavel, status yes, partial, no ou unknown, evidence e rationale. "
        "Calcule metrics a partir dos criterios e da qualidade das evidencias."
    )
    if stage == Stage.TO_LOOK:
        return (
            base
            + " ToLook e apenas triagem: knowledge_suggestions deve ser []. "
            "Nao extraia Concepts, Dots, MOCs ou tarefas de conhecimento em ToLook."
        )
    return (
        base
        + " Use recommended_subject_tags para tags de assunto/metodo/uso/qualidade do Research Reading Protocol. "
        "Em knowledge_suggestions, crie material para notas de conhecimento, nao tarefas. "
        "Cada item deve conter knowledge_claim, article_use, evidence, applicability, limitations, "
        "integration_notes, review_tasks e justification. "
        "Use review_tasks apenas para pendencias; o corpo principal deve explicar conhecimento extraido do artigo."
    )


def _partitions_for_stage(stage: Stage) -> list[dict[str, Any]]:
    partitions = [
        {
            "name": "triage_context",
            "purpose": "avaliar abstract, introducao, conclusao, aderencia e decisao preliminar",
            "sections": ["abstract_keywords", "introduction", "conclusion"],
        },
        {
            "name": "results_signal",
            "purpose": "avaliar resultados, evidencias aproveitaveis e utilidade para o protocolo",
            "sections": ["results"],
        },
    ]
    if stage == Stage.TO_REVISE:
        partitions.append(
            {
                "name": "knowledge_suggestions",
                "purpose": "propor sugestoes compactas de conhecimento com base na triagem e nos resultados",
                "sections": ["abstract_keywords", "method_topics", "results", "conclusion"],
            }
        )
    if stage == Stage.TO_DIG:
        partitions.extend(
            [
                {
                    "name": "method_formulation",
                    "purpose": "extrair metodo, formulacao, parametros, suposicoes e reprodutibilidade",
                    "sections": ["method_formulation"],
                },
                {
                    "name": "validation_limitations",
                    "purpose": "avaliar validacao, limitacoes, insights e potencial de implementacao",
                    "sections": ["results_validation", "limitations_insights_conclusion"],
                },
                {
                    "name": "equations_formulation",
                    "purpose": "extrair equacoes, variaveis, parametros e relacoes matematicas complementando metodo/formulacao",
                    "sections": ["method_formulation", "results_validation"],
                },
                {
                    "name": "deep_knowledge_suggestions",
                    "purpose": "gerar sugestoes profundas de Concepts, Dots e MOCs a partir da leitura completa",
                    "sections": [
                        "method_formulation",
                        "results_validation",
                        "limitations_insights_conclusion",
                    ],
                },
            ]
        )
    return partitions


def _partition_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["partition", "summary", "evidence", "criteria_notes", "tag_hints", "knowledge_hints"],
        "properties": {
            "partition": {"type": "string"},
            "summary": {"type": "string", "maxLength": 700},
            "evidence": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 300}},
            "criteria_notes": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 240}},
            "tag_hints": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 80}},
            "knowledge_hints": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 240}},
        },
        "additionalProperties": False,
    }


def _equations_partition_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["partition", "summary", "equations", "parameters", "assumptions", "reproducibility_notes"],
        "properties": {
            "partition": {"type": "string"},
            "summary": {"type": "string", "maxLength": 700},
            "equations": {
                "type": "array",
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "required": ["label", "latex", "plain_language", "variables", "where_used"],
                    "properties": {
                        "label": {"type": "string", "maxLength": 80},
                        "latex": {"type": "string", "maxLength": 500},
                        "plain_language": {"type": "string", "maxLength": 300},
                        "variables": {
                            "type": "array",
                            "maxItems": 12,
                            "items": {
                                "type": "object",
                                "required": ["symbol", "meaning", "units"],
                                "properties": {
                                    "symbol": {"type": "string", "maxLength": 40},
                                    "meaning": {"type": "string", "maxLength": 220},
                                    "units": {"type": "string", "maxLength": 80},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "where_used": {"type": "string", "maxLength": 240},
                    },
                    "additionalProperties": False,
                },
            },
            "parameters": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 180}},
            "assumptions": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 220}},
            "reproducibility_notes": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 240}},
        },
        "additionalProperties": False,
    }


def _partition_schema_for_partition(partition: dict[str, Any]) -> dict[str, Any]:
    if partition["name"] == "equations_formulation":
        return _equations_partition_schema()
    return _partition_schema()


def _partition_messages(candidate: CandidatePaper, partition: dict[str, Any], section_packet: dict[str, Any]) -> list[dict[str, str]]:
    if partition["name"] == "equations_formulation":
        instruction = (
            "Return equations in the equations array. Use LaTeX or close LaTeX in latex, "
            "define variables with symbol, meaning and units, and add parameters, assumptions "
            "and reproducibility_notes. If no explicit equation is present, return equations as []."
        )
    else:
        instruction = "Return compact evidence, criteria_notes, tag_hints and knowledge_hints."
    return [
        {
            "role": "system",
            "content": (
                "Voce analisa apenas uma parte de um artigo. "
                "Responda somente JSON valido no schema solicitado. "
                "Nao tome a decisao final; produza evidencias compactas para consolidacao posterior."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Citekey: {candidate.citekey}\n"
                f"Stage: {candidate.stage.value}\n"
                f"Partition: {partition['name']}\n"
                f"Purpose: {partition['purpose']}\n"
                f"Subject tag options for this stage: {_subject_tag_options(candidate.stage)}\n"
                f"{instruction}\n"
                f"Partition packet JSON: {json.dumps(section_packet, ensure_ascii=False, separators=(',', ':'))}"
            ),
        },
    ]


def _packet_for_partition(reading_packet: dict[str, Any], partition: dict[str, Any]) -> dict[str, Any]:
    sections = dict(reading_packet.get("sections", {}) or {})
    selected = {name: sections.get(name, "") for name in partition["sections"] if sections.get(name)}
    packet = {
        "title": reading_packet.get("title", ""),
        "metadata_abstract": reading_packet.get("metadata_abstract", ""),
        "partition": partition["name"],
        "sections": selected,
    }
    if partition.get("include_global_context"):
        packet["global_context"] = reading_packet.get("full_context", "")
    return packet


def _parse_partition_output(raw: str, partition: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("partition output must be a JSON object")
    payload.setdefault("partition", partition["name"])
    return payload


def _final_packet_from_partitions(
    candidate: CandidatePaper,
    reading_packet: dict[str, Any],
    partition_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "citekey": candidate.citekey,
        "stage": candidate.stage.value,
        "title": reading_packet.get("title", candidate.title),
        "metadata_abstract": reading_packet.get("metadata_abstract", ""),
        "partition_summaries": partition_outputs,
        "global_context": reading_packet.get("full_context", ""),
        "figures": reading_packet.get("figures", []),
    }


def _subject_tag_options(stage: Stage) -> list[str]:
    if stage == Stage.TO_LOOK:
        return []
    return list(READING_PROTOCOL_SUBJECT_TAGS)


def _knowledge_instruction(stage: Stage) -> str:
    if stage == Stage.TO_LOOK:
        return "Knowledge suggestions allowed: no; return knowledge_suggestions as an empty array."
    return "Knowledge suggestions allowed: yes."


def _knowledge_quality_instruction(stage: Stage) -> str:
    if stage == Stage.TO_LOOK:
        return ""
    return (
        "For knowledge_suggestions, never use action-only wording such as 'verify', 'validate' or "
        "'test' as the main content; put such wording only in review_tasks."
    )


def _normalize_completion(value: str | LLMCompletion) -> LLMCompletion:
    if isinstance(value, LLMCompletion):
        return value
    return LLMCompletion(str(value))


def _budget_for_messages(messages: list[dict[str, str]], config: LMStudioConfig) -> dict[str, int]:
    stage = _stage_from_messages(messages)
    if stage == Stage.TO_LOOK:
        return {"max_tokens": config.tolook_max_output_tokens, "timeout_seconds": config.tolook_timeout_seconds}
    if stage in {Stage.TO_REVISE, Stage.TO_DIG}:
        return {"max_tokens": config.deep_stage_max_output_tokens, "timeout_seconds": config.deep_stage_timeout_seconds}
    return {"max_tokens": config.max_output_tokens, "timeout_seconds": config.timeout_seconds}


def _stage_from_messages(messages: list[dict[str, str]]) -> Stage | None:
    for message in messages:
        for line in str(message.get("content", "")).splitlines():
            if not line.startswith("Stage: "):
                continue
            raw = line.split(": ", 1)[1].strip()
            try:
                return Stage(raw)
            except ValueError:
                return None
    return None


def _record_completion(
    result: LLMRunResult,
    completion: LLMCompletion,
    *,
    accepted_text: str,
    accepted_channel: str,
) -> None:
    result.raw_outputs.append(accepted_text)
    result.accepted_channels.append(accepted_channel)
    if completion.usage:
        result.usage.append(completion.usage)
    if completion.reasoning_content:
        result.reasoning_outputs.append(completion.reasoning_content)
    if completion.request_payload:
        result.request_payloads.append(completion.request_payload)


def _accepted_json_from_completion(completion: LLMCompletion, *, parser) -> tuple[str, str]:
    errors = []
    for channel, text in [("content", str(completion)), ("reasoning_content", completion.reasoning_content)]:
        candidate = _extract_single_json_object(text)
        if not candidate:
            errors.append(f"{channel}: no single JSON object")
            continue
        try:
            parser(candidate)
        except Exception as exc:
            errors.append(f"{channel}: {exc}")
            continue
        return candidate, channel
    raise ValueError("no valid JSON in content or reasoning_content; " + "; ".join(errors))


def _extract_single_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            pass
        else:
            return stripped
    start = stripped.find("{")
    if start < 0:
        return ""
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(stripped[start:])
    except json.JSONDecodeError:
        return ""
    candidate = stripped[start : start + end].strip()
    remaining = stripped[start + end :].strip()
    if "{" in remaining:
        return ""
    return candidate
