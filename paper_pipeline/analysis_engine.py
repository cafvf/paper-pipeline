from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import PaperArtifactStore
from .lmstudio_chat import (
    ChatJsonClient,
    LLMRunResult,
    run_assessment_with_retry,
    run_partitioned_assessment_with_retry,
)
from .pdf_ingest import PdfConverter, build_stage_conversion_plan, run_converters_with_cache
from .reading_packet import build_reading_packet
from .runner import _stage_slug
from .selection import CandidatePaper


class LocalPaperAnalyzer:
    def __init__(
        self,
        *,
        client: ChatJsonClient,
        converters: list[PdfConverter] | None = None,
        max_attempts: int = 2,
        packet_max_chars: int = 20000,
    ) -> None:
        self.client = client
        self.converters = converters
        self.max_attempts = max_attempts
        self.packet_max_chars = packet_max_chars
        self.last_result = None

    def analyze(self, candidate: CandidatePaper, artifact_store: PaperArtifactStore):
        if not candidate.pdf_paths:
            artifact_store.append_log({"event": "analysis_skipped", "reason": "missing_pdf_path"})
            return None
        pdf_path = Path(candidate.pdf_paths[0])
        plan = build_stage_conversion_plan(candidate.stage)
        converters = self.converters if self.converters is not None else plan.converters
        required = _required_converter_names(candidate.stage, self.converters, plan.required_converter_names or [])
        conversion = run_converters_with_cache(
            pdf_path=pdf_path,
            paper_root=artifact_store.root,
            converters=converters,
            stop_after_first_success=plan.stop_after_first_success if self.converters is None else False,
            required_converter_names=required,
        )
        if not conversion["conversion_report"].get("usable", False):
            missing = conversion["conversion_report"].get("missing_required_converters", [])
            error = "required converters failed: " + ", ".join(missing) if missing else "no PDF converter produced usable output"
            artifact_store.append_log({"event": "analysis_skipped", "reason": "conversion_unusable", "error": error})
            self.last_result = LLMRunResult(status="partial", raw_outputs=[], errors=[error])
            return None
        documents = _read_conversion_outputs(conversion["conversion_report"])
        packet = build_reading_packet(candidate=candidate, converted_documents=documents, max_chars=self.packet_max_chars)
        stage = _stage_slug(candidate.stage)
        artifact_store.write_latest_and_history("reading_packets", stage, packet)
        runner = run_assessment_with_retry if candidate.stage.value == ".ToLook" else run_partitioned_assessment_with_retry
        result = runner(client=self.client, candidate=candidate, reading_packet=packet, max_attempts=self.max_attempts)
        self.last_result = result
        artifact_store.write_passes(
            stage,
            "latest",
            {
                "llm_result": {
                    "status": result.status,
                    "raw_outputs": result.raw_outputs,
                    "partition_outputs": result.partition_outputs,
                    "usage": result.usage,
                    "reasoning_outputs": result.reasoning_outputs,
                    "request_payloads": result.request_payloads,
                    "accepted_channels": result.accepted_channels,
                    "errors": result.errors,
                    "assessment": result.assessment.__dict__ if result.assessment else None,
                }
            },
        )
        return result.assessment


def _required_converter_names(stage, converters: list[PdfConverter] | None, default_required: list[str]) -> list[str]:
    if converters is None:
        return default_required
    names = {converter.name for converter in converters}
    if stage.value == ".To Revise" and "marker" in names:
        return ["marker"]
    if stage.value == ".ToDig":
        return [name for name in ("marker", "nougat") if name in names]
    return []


def _read_conversion_outputs(report: dict[str, Any]) -> list[str | dict[str, Any]]:
    documents: list[str | dict[str, Any]] = []
    for item in report.get("converters", {}).values():
        path = item.get("output_path")
        if not path:
            continue
        output = Path(path)
        if output.suffix == ".json":
            documents.append(json.loads(output.read_text(encoding="utf-8")))
        else:
            documents.append(output.read_text(encoding="utf-8", errors="replace"))
    return documents
