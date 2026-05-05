from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Protocol

from .artifacts import PaperArtifactStore
from .assessment_notes import render_note_from_assessment, render_partial_note_from_llm_result
from .config import RuntimeConfig
from .contracts import DecisionState, FullDecision, MissingPdfDecision, PartialAnalysisAction, PartialAnalysisDecision, PipelineError, Stage
from .decision_applier import apply_decision_note, scan_decision_notes
from .decision_notes import decision_note_path, parse_decision_from_text, render_full_decision_note, render_missing_pdf_note
from .llm_schema import LLMAssessment
from .selection import CandidatePaper, select_batch
from .zotero_collections import CollectionResolution
from .zotero_plan import ZoteroActionPlan, ZoteroItemState, build_zotero_action_plan


class CandidateSource(Protocol):
    def list_candidates(self) -> list[CandidatePaper]: ..


class PaperAnalyzer(Protocol):
    def analyze(self, candidate: CandidatePaper, artifact_store: PaperArtifactStore) -> LLMAssessment | None: ..


class ZoteroPlanApplier(Protocol):
    def apply_plan(self, plan: ZoteroActionPlan) -> dict: ..


@dataclass
class NightlyRunResult:
    applied_decisions: list[dict] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    blocked_missing_pdf: list[str] = field(default_factory=list)
    notes_written: list[str] = field(default_factory=list)


def run_once(
    *,
    config: RuntimeConfig,
    zotero_source: CandidateSource,
    lexical_index: dict,
    max_total: int = 10,
    analyzer: PaperAnalyzer | None = None,
    apply_existing_decisions: bool = True,
    zotero_applier: ZoteroPlanApplier | None = None,
    operational_collections: dict[Stage, CollectionResolution] | None = None,
) -> NightlyRunResult:
    config.paths.inbox_dir.mkdir(parents=True, exist_ok=True)
    config.paths.papers_root.mkdir(parents=True, exist_ok=True)
    result = NightlyRunResult()
    pending_citekeys: set[str] = set()
    resolved_citekeys: set[str] = set()
    candidates = zotero_source.list_candidates()
    candidates_by_citekey = {candidate.citekey: candidate for candidate in candidates}
    for note_path in scan_decision_notes(config.paths.inbox_dir):
        citekey = note_path.name.removesuffix(" - LLM Paper Decision.md")
        if apply_existing_decisions:
            store = PaperArtifactStore(config.paths.papers_root, citekey)
            try:
                note_text = note_path.read_text(encoding="utf-8")
                decision = parse_decision_from_text(note_text)
                zotero_plan = _plan_for_decision(
                    decision=decision,
                    candidate=candidates_by_citekey.get(citekey),
                    operational_collections=operational_collections,
                    recommended_stage=_recommended_stage_from_note(note_text),
                )
                applied = apply_decision_note(
                    note_path=note_path,
                    citekey=citekey,
                    artifact_store=store,
                    zotero_plan=zotero_plan,
                    zotero_applier=zotero_applier,
                    vault_root=config.paths.vault_root,
                    lexical_index=lexical_index,
                )
                result.applied_decisions.append({"citekey": citekey, "status": applied.status, "errors": applied.errors})
                if applied.delete_note:
                    resolved_citekeys.add(citekey)
            except PipelineError as exc:
                store.append_log({"event": "decision_parse_error", "error": str(exc), "note_path": str(note_path)})
                result.applied_decisions.append({"citekey": citekey, "status": "error", "errors": [str(exc)]})
        else:
            _consume_approved_partial_retry(note_path, citekey, PaperArtifactStore(config.paths.papers_root, citekey), result)
        if note_path.exists():
            pending_citekeys.add(citekey)

    candidates = [candidate for candidate in candidates if candidate.citekey not in pending_citekeys and candidate.citekey not in resolved_citekeys]
    batch = select_batch(candidates, lexical_index, max_total=max_total)
    for entry in batch["selected"]:
        candidate = entry["candidate"]
        path = decision_note_path(config.paths.inbox_dir, candidate.citekey)
        if path.exists():
            continue
        store = PaperArtifactStore(config.paths.papers_root, candidate.citekey)
        text = _render_selected_note(candidate, entry["score"], store, analyzer)
        path.write_text(text, encoding="utf-8")
        result.selected.append(candidate.citekey)
        result.notes_written.append(str(path))

    for entry in batch["blocked_missing_pdf"]:
        candidate = entry["candidate"]
        path = decision_note_path(config.paths.inbox_dir, candidate.citekey)
        if path.exists():
            continue
        path.write_text(
            render_missing_pdf_note(citekey=candidate.citekey, title=candidate.title, current_collection=candidate.stage.value),
            encoding="utf-8",
        )
        result.blocked_missing_pdf.append(candidate.citekey)
        result.notes_written.append(str(path))
    return result


def _plan_for_decision(
    *,
    decision,
    candidate: CandidatePaper | None,
    operational_collections: dict[Stage, CollectionResolution] | None,
    recommended_stage: Stage | None = None,
) -> ZoteroActionPlan | None:
    if not isinstance(decision, (FullDecision, MissingPdfDecision, PartialAnalysisDecision)):
        return None
    if candidate is None or operational_collections is None:
        return None
    action = getattr(decision, "collection_action", None)
    if action is None:
        if isinstance(decision, MissingPdfDecision) and getattr(decision, "missing_pdf_action", None).value == "move_to_expendable":
            from .contracts import CollectionAction

            action = CollectionAction.MOVE_TO_EXPENDABLE
        elif isinstance(decision, PartialAnalysisDecision) and getattr(decision, "partial_analysis_action", None).value == "move_to_expendable":
            from .contracts import CollectionAction

            action = CollectionAction.MOVE_TO_EXPENDABLE
        else:
            return None
    return build_zotero_action_plan(
        item=ZoteroItemState(
            item_key=candidate.zotero_item_key or candidate.citekey,
            current_stage=candidate.stage,
            collection_keys=candidate.collection_keys or [candidate.stage.value],
            tags=candidate.tags,
        ),
        collection_action=action,
        recommended_stage=recommended_stage,
        operational_collections=operational_collections,
        analysis_stage=candidate.stage,
        analysis_complete=True,
        recommended_tags_add=getattr(decision, "tag_overrides_add", []),
        recommended_tags_remove=getattr(decision, "tag_overrides_remove", []),
    )


def _recommended_stage_from_note(text: str) -> Stage | None:
    match = re.search(r"- Recomendacao:\s*`([^`]+)`", text)
    if not match:
        return None
    try:
        return Stage(match.group(1))
    except ValueError:
        return None


def _default_recommendation(candidate: CandidatePaper) -> str:
    return candidate.stage.value


def _consume_approved_partial_retry(note_path, citekey: str, store: PaperArtifactStore, result: NightlyRunResult) -> None:
    try:
        decision = parse_decision_from_text(note_path.read_text(encoding="utf-8"))
        if not (
            isinstance(decision, PartialAnalysisDecision)
            and decision.decision_state == DecisionState.APPROVED
            and decision.partial_analysis_action == PartialAnalysisAction.RETRY_NEXT_RUN
        ):
            return
        applied = apply_decision_note(note_path=note_path, citekey=citekey, artifact_store=store)
    except PipelineError:
        return
    if applied.status == "retry_queued":
        result.applied_decisions.append({"citekey": citekey, "status": applied.status, "errors": applied.errors})


def _render_selected_note(
    candidate: CandidatePaper,
    score: int,
    store: PaperArtifactStore,
    analyzer: PaperAnalyzer | None,
) -> str:
    if analyzer is not None:
        assessment = analyzer.analyze(candidate, store)
        if assessment is not None:
            links = store.write_latest_and_history("assessments", _stage_slug(candidate.stage), assessment.__dict__)
            return render_note_from_assessment(
                assessment=assessment,
                title=candidate.title,
                current_collection=candidate.stage.value,
                artifact_links={"assessment": links["latest"]},
            )
        result = getattr(analyzer, "last_result", None)
        if result is not None and getattr(result, "status", "") == "partial":
            return render_partial_note_from_llm_result(candidate=candidate, result=result)
    return render_full_decision_note(
        citekey=candidate.citekey,
        title=candidate.title,
        current_collection=candidate.stage.value,
        recommended_collection=_default_recommendation(candidate),
        recommended_tags_add=[],
        body_sections=[f"## Score inicial\n- Score: `{score}`"],
    )


def _stage_slug(stage) -> str:
    mapping = {
        ".ToLook": "to_look",
        ".To Revise": "to_revise",
        ".ToDig": "to_dig",
    }
    return mapping.get(stage.value, stage.value.strip(".").lower().replace(" ", "_"))
