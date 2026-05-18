# Roadmap

This roadmap is the implementation-status snapshot for the modular Obsidian + Zotero assistant. The target workflow contract is still frozen in `docs/workflow_spec.md` (spec freeze date: 2026-05-06), while this page tracks what is already true in the repository as of **2026-05-18**.

Status vocabulary:

- ready: implemented and covered enough for the stated future contract;
- partial: useful implementation exists, but the project-specific contract is incomplete;
- not started: no direct implementation found;
- exists but needs refactor: implementation exists, but the current shape does not match the desired boundary;
- out of current scope: intentionally later.

| # | Project | Current status | Evidence found | Main gap | Next action |
| --- | --- | --- | --- | --- | --- |
| 1 | Semantic foundation and contracts | ready | `schemas/project_profile.schema.json`, `schemas/paper_profile.schema.json`, `schemas/project_paper_match.schema.json`, `schemas/llm_classification.schema.json`, `configs/utility_taxonomy.yaml`, `tests/test_project1_contracts.py`. | Contracts exist, but later runtime commands still need to honor them end to end. | Keep schemas/configs stable while implementing missing commands. |
| 2 | Obsidian inventory | partial | `paper_pipeline/obsidian_inventory.py`, CLI `scan-obsidian`, `tests/test_obsidian_inventory.py`. | Implemented as a standalone scanner, but not yet part of a finished end-to-end project-paper triage command. | Preserve as independent app and wire it into the future thin orchestrator. |
| 3 | Zotero inventory | partial | `paper_pipeline/zotero_inventory.py`, CLI `scan-zotero`, `tests/test_zotero_inventory.py`, `paper_pipeline/zotero_api.py`, `paper_pipeline/zotero_adapter.py`. | Read-only inventory exists, but end-to-end project-paper flow is still incomplete. | Preserve as independent app and keep read-only behavior explicit. |
| 4 | Local registry, cache, history | partial | `paper_pipeline/registry.py`, CLI `sync-registry`, `tests/test_registry.py`, pair-skip checks in `tests/test_project_paper_matching.py`. | Registry schema/sync exist, but runtime write-through for completed match/classification/review phases is not wired into the new flow. | Add post-success write-through and atomic completion/hash recording. |
| 5 | Project-paper matching engine | partial | `paper_pipeline/project_paper_matching.py`, CLI `match`, `tests/test_project_paper_matching.py`. | Lexical MVP exists, but it still lacks production write-through and an evaluation harness beyond deterministic fixtures. | Keep lexical base, then add safe registry integration and later optional evaluation/embeddings improvements. |
| 6 | Article utility classifier | partial | `paper_pipeline/project_paper_classification.py`, `schemas/llm_classification.schema.json`, `tests/test_project1_contracts.py`. | Parser/schema exist, but there is no runnable `classify` command yet. | Implement `classify` as the next independent command. |
| 7 | Human review bench in Obsidian | partial | Legacy decision-note infrastructure exists in `paper_pipeline/decision_notes.py`, `paper_pipeline/assessment_notes.py`, and `paper_pipeline/decision_applier.py`; grouped project-paper review contract is documented in `docs/workflow_spec.md`. | No grouped `export-review` implementation yet for the new project-paper workflow. | Implement grouped citekey-level review export as the next output phase after `classify`. |
| 8 | Zotero tag synchronizer | exists but needs refactor | `paper_pipeline/zotero_plan.py`, `paper_pipeline/decision_applier.py`, `paper_pipeline/zotero_api.py`. | Current path is legacy-oriented and does not yet enforce the future `plan_hash`-verified apply contract. | Defer until the read-only MVP chain is complete, then harden the apply path. |
| 9A | PDF product extraction | partial | `paper_pipeline/pdf_ingest.py`, `paper_pipeline/reading_packet.py`, `paper_pipeline/analysis_engine.py`. | Existing PDF work is still tied to the legacy reading pipeline, not a standalone layer-1/2/3 product module. | Split extraction from deep analysis after the read-only MVP chain is complete. |
| 9C | Reference mining | not started | The workflow contract exists in `docs/workflow_spec.md` and `docs/modules.md`, but there is no `reference_mining.py` yet. | No implemented reference index/mining pipeline. | Start only after reference extraction products exist. |
| 9B | Deep PDF analyzer | partial | `paper_pipeline/analysis_engine.py`, `paper_pipeline/llm_schema.py`. | Existing analyzer is reading-stage oriented and should later consume extracted products rather than raw PDFs by default. | Reuse only after PDF products and approval boundaries are in place. |
| 10 | Technical notes and links in Obsidian | exists but needs refactor | `paper_pipeline/knowledge_application.py`, `paper_pipeline/note_patcher.py`, tests around note patching/application. | Current path is legacy draft/patch behavior, not the future project-paper note-planning contract. | Defer until after read-only MVP and apply planning are stable. |
| 11 | Reading, study, and reproduction planner | partial | `paper_pipeline/reading_plan.py`, `paper_pipeline/run_summary.py`. | Current planning is paper-stage oriented, not yet project-paper utility/study planning. | Build after approved classifications exist in the new flow. |
| 12 | Gap, redundancy, and maturity auditor | not started | No direct module found. | No project-level coverage or redundancy auditor yet. | Defer until registry/history contains enough approved project-paper evidence. |
| 13 | General orchestrator | partial | CLI already exposes independent commands for `scan-obsidian`, `scan-zotero`, `sync-registry`, and `match`; legacy orchestration still lives in `paper_pipeline/runner.py`. | The new thin `triage` orchestrator does not exist yet, and legacy `run`/`pilot-run` must not become its substitute. | Implement the new sequencing-only orchestrator after `classify` and `export-review` exist. |

## Recommended Order

### Immediate priority: close the read-only MVP chain

1. Implement `classify`.
2. Implement grouped `export-review`.
3. Add safe registry write-through and completion/hash recording.
4. Introduce the thin `triage` orchestrator that sequences only the independent commands.

This is the current shortest path to a coherent project-paper MVP:

```text
scan-obsidian -> scan-zotero -> match -> classify -> export-review
```

### After the read-only MVP is stable

5. Harden approval-gated apply paths for Zotero and Obsidian.
6. Split PDF product extraction from deep interpretation.
7. Add reference mining, note planning, deep analysis, and higher-level planners/auditors.

## MVP 0.1 Acceptance

- Uses fixtures or explicit safe paths.
- Produces `ProjectProfile` rows for 3 to 5 active notes.
- Produces `PaperProfile` rows for 100 to 300 Zotero metadata items.
- Produces top 20 candidates per project before LLM.
- Classifies top 10 per project with valid JSON.
- Exports one Markdown review report.
- Does not write Zotero, does not create permanent Obsidian notes, and does not read full PDFs.
