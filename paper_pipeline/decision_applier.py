from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .artifacts import PaperArtifactStore
from .contracts import (
    CollectionAction,
    DecisionState,
    FullDecision,
    MissingPdfAction,
    MissingPdfDecision,
    PartialAnalysisAction,
    PartialAnalysisDecision,
    Stage,
    ValidationError,
)
from .decision_notes import parse_decision_from_text
from .knowledge_application import apply_article_knowledge
from .zotero_plan import ZoteroActionPlan


class ZoteroPlanApplier(Protocol):
    def apply_plan(self, plan: ZoteroActionPlan) -> dict: ...


@dataclass
class DecisionApplicationResult:
    citekey: str
    status: str
    actions: list[dict] = field(default_factory=list)
    delete_note: bool = False
    errors: list[str] = field(default_factory=list)


def scan_decision_notes(inbox_dir: str | Path) -> list[Path]:
    return sorted(Path(inbox_dir).glob("* - LLM Paper Decision.md"))


def apply_decision_note(
    *,
    note_path: str | Path,
    citekey: str,
    artifact_store: PaperArtifactStore,
    zotero_plan: ZoteroActionPlan | None = None,
    zotero_applier: ZoteroPlanApplier | None = None,
    vault_root: str | Path | None = None,
    lexical_index: dict[str, Any] | None = None,
) -> DecisionApplicationResult:
    path = Path(note_path)
    decision = parse_decision_from_text(path.read_text(encoding="utf-8"))
    if isinstance(decision, FullDecision):
        return _apply_full_decision(path, citekey, artifact_store, decision, zotero_plan, zotero_applier, vault_root, lexical_index)
    if isinstance(decision, MissingPdfDecision):
        return _apply_missing_pdf_decision(path, citekey, artifact_store, decision, zotero_plan, zotero_applier)
    if isinstance(decision, PartialAnalysisDecision):
        return _apply_partial_decision(path, citekey, artifact_store, decision, zotero_plan, zotero_applier)
    raise ValidationError("unsupported decision type")


def _apply_full_decision(
    path: Path,
    citekey: str,
    store: PaperArtifactStore,
    decision: FullDecision,
    zotero_plan: ZoteroActionPlan | None,
    zotero_applier: ZoteroPlanApplier | None,
    vault_root: str | Path | None,
    lexical_index: dict[str, Any] | None,
) -> DecisionApplicationResult:
    result = DecisionApplicationResult(citekey=citekey, status="pending")
    if decision.decision_state == DecisionState.PENDING:
        result.status = "pending"
        return result
    if decision.decision_state == DecisionState.DEFERRED:
        result.status = "deferred"
        return result
    if decision.decision_state == DecisionState.MANUAL_ONLY:
        store.append_log({"event": "manual_only", "note_path": str(path)})
        path.unlink(missing_ok=True)
        result.status = "manual_only"
        result.delete_note = True
        return result
    if decision.decision_state == DecisionState.REJECTED and decision.collection_action == CollectionAction.ACCEPT_RECOMMENDATION:
        result.status = "error"
        result.errors.append("rejected decision requires alternative collection_action")
        return result

    if decision.apply_zotero_actions:
        if zotero_plan is None or zotero_applier is None:
            result.status = "error"
            result.errors.append("zotero plan/applier required")
            return result
        apply_result = zotero_applier.apply_plan(zotero_plan)
        result.actions.append({"action": "apply_zotero", **apply_result})
        if apply_result.get("status") != "applied" and apply_result.get("status") != "noop":
            result.status = "error"
            result.errors.append(str(apply_result.get("error") or apply_result.get("status")))
            store.append_log({"event": "decision_error", "errors": result.errors})
            return result

    if decision.apply_knowledge_actions:
        if vault_root is None:
            result.status = "error"
            result.errors.append("vault_root required for knowledge application")
            return result
        knowledge = apply_article_knowledge(
            note_path=path,
            vault_root=vault_root,
            artifact_store=store,
            citekey=citekey,
            decision=decision,
            lexical_index=lexical_index,
        )
        result.actions.append({"action": "apply_knowledge", "status": knowledge.status, "actions": knowledge.actions})
        if knowledge.status != "applied":
            result.status = "error"
            result.errors.extend(knowledge.errors)
            store.append_log({"event": "knowledge_error", "errors": result.errors})
            return result

    store.append_log({"event": "decision_applied", "actions": result.actions})
    path.unlink(missing_ok=True)
    result.status = "applied"
    result.delete_note = True
    return result


def _apply_missing_pdf_decision(
    path: Path,
    citekey: str,
    store: PaperArtifactStore,
    decision: MissingPdfDecision,
    zotero_plan: ZoteroActionPlan | None,
    zotero_applier: ZoteroPlanApplier | None,
) -> DecisionApplicationResult:
    result = DecisionApplicationResult(citekey=citekey, status="pending")
    if decision.decision_state == DecisionState.MANUAL_ONLY or decision.missing_pdf_action == MissingPdfAction.MANUAL_ONLY:
        store.append_log({"event": "missing_pdf_manual_only"})
        path.unlink(missing_ok=True)
        result.status = "manual_only"
        result.delete_note = True
        return result
    if decision.missing_pdf_action == MissingPdfAction.MOVE_TO_EXPENDABLE:
        return _apply_reduced_discard(path, citekey, store, zotero_plan, zotero_applier)
    return result


def _apply_partial_decision(
    path: Path,
    citekey: str,
    store: PaperArtifactStore,
    decision: PartialAnalysisDecision,
    zotero_plan: ZoteroActionPlan | None,
    zotero_applier: ZoteroPlanApplier | None,
) -> DecisionApplicationResult:
    result = DecisionApplicationResult(citekey=citekey, status="pending")
    if decision.decision_state == DecisionState.MANUAL_ONLY or decision.partial_analysis_action == PartialAnalysisAction.MANUAL_ONLY:
        store.append_log({"event": "partial_manual_only"})
        path.unlink(missing_ok=True)
        result.status = "manual_only"
        result.delete_note = True
        return result
    if decision.decision_state == DecisionState.APPROVED and decision.partial_analysis_action == PartialAnalysisAction.RETRY_NEXT_RUN:
        store.append_log({"event": "partial_retry_queued", "note_path": str(path)})
        path.unlink(missing_ok=True)
        result.status = "retry_queued"
        result.delete_note = True
        return result
    if decision.partial_analysis_action == PartialAnalysisAction.MOVE_TO_EXPENDABLE:
        return _apply_reduced_discard(path, citekey, store, zotero_plan, zotero_applier)
    return result


def _apply_reduced_discard(
    path: Path,
    citekey: str,
    store: PaperArtifactStore,
    zotero_plan: ZoteroActionPlan | None,
    zotero_applier: ZoteroPlanApplier | None,
) -> DecisionApplicationResult:
    result = DecisionApplicationResult(citekey=citekey, status="pending")
    if zotero_plan is None or zotero_plan.target_stage != Stage.EXPENDABLE or zotero_applier is None:
        result.status = "error"
        result.errors.append("discard requires Expendable zotero plan")
        return result
    apply_result = zotero_applier.apply_plan(zotero_plan)
    result.actions.append({"action": "apply_zotero_discard", **apply_result})
    if apply_result.get("status") not in {"applied", "noop"}:
        result.status = "error"
        result.errors.append(str(apply_result.get("error") or apply_result.get("status")))
        return result
    store.append_log({"event": "discard_applied", "actions": result.actions})
    path.unlink(missing_ok=True)
    result.status = "applied"
    result.delete_note = True
    return result
