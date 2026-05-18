# Documentation Map

Start here when you need to understand the repository without reconstructing the story from multiple stale documents.

## Current Repository Story

`paper-pipeline` currently has **two realities that must stay distinct**:

1. **Legacy paper-stage pipeline**
   - entrypoints: `paper-pipeline run`, `paper-pipeline pilot-run`
   - owner: `paper_pipeline/runner.py`
   - purpose: the original Zotero operational-collection workflow with decision notes, optional apply, and paper-level artifacts

2. **Project-paper migration path**
   - current independent commands: `scan-obsidian`, `scan-zotero`, `sync-registry`, `match`, `classify`, `export-review`
   - implemented foundations: `obsidian_inventory.py`, `zotero_inventory.py`, `registry.py`, `project_paper_matching.py`, `project_paper_classification.py`, `export_review.py`
   - current runnable read-only chain:

   ```text
   scan-obsidian -> scan-zotero -> match -> classify -> export-review
   ```

   - next missing owner: the thin nightly `triage` orchestrator that sequences those commands without absorbing their business logic

The most important documentation rule for this repository is: **do not mix the legacy paper-stage path with the new project-paper target path**.

## Recommended Reading Order

1. **`README.md`**
   - quickstart, repo layout, development commands, and operational safety basics
2. **`docs/vision.md`**
   - why the project exists and why Obsidian is the intention layer while Zotero is the evidence layer
3. **`docs/architecture.md`**
   - current flow vs target flow, orchestrator boundary, artifact boundary, and service-safety notes
4. **`docs/workflow_spec.md`**
   - canonical target command/artifact contract for MVP 0.1
5. **`docs/modules.md`**
   - module-by-module ownership, inputs, outputs, and side effects
6. **`docs/roadmap.md`**
   - implementation-status snapshot across the planned modules/projects
7. **`docs/development_plan.md`**
   - the current execution order for finishing the read-only MVP and then hardening apply/deeper stages
8. **`docs/mvp_phase_specs.md`**
   - detailed executable specifications for migration Phases 0, 1, and 2
9. **`docs/next_session_prompt.md`**
   - reusable handoff prompt for the next development session

## Which Document Is Authoritative For What?

### Product / intent
- `docs/vision.md`

### Current and target architecture
- `docs/architecture.md`
- `docs/workflow_spec.md`

### Module ownership and boundaries
- `docs/modules.md`

### Current implementation status
- `docs/roadmap.md`
- `docs/development_plan.md`
- `docs/mvp_phase_specs.md`

### Contracts and safety policy
- `docs/data_contracts.md`
- `docs/zotero_policy.md`
- `docs/obsidian_policy.md`
- `docs/human_review_workflow.md`
- `docs/reading_protocol_criteria.md`

### Contributor workflow
- `docs/development_guidelines.md`

## Current State Snapshot (2026-05-18)

Implemented enough to use as the current safe base:
- project-paper schemas and fixtures
- read-only Obsidian inventory
- read-only Zotero inventory
- registry schema and sync command
- lexical project-paper matching with stage filters and total candidate cap
- metadata-only project-paper `classify` command with schema-validated JSONL output, semantic coherence checks, and per-run safety caps
- grouped `export-review` command with one Markdown review file per round

Current next gaps for the active development phase:
- safe registry write-through for completed runtime phases
- thin nightly `triage` orchestrator command
- per-layer evaluation tracking so nightly runs skip papers already evaluated in their current Zotero layer

## Historical / situational docs

- `README-MIGRATION.md`: historical notes for extracting the project from a vault-local `x/LLM` layout. Useful only when doing that migration again.
- `docs/Research Reading Protocol.md`: user reading protocol reference used by some later-stage classification/planning decisions.

## Documentation maintenance rules

When updating docs, keep these invariants coherent across the repo:
- `runner.py` is legacy paper-stage orchestration unless explicitly redefined later
- the project-paper target uses independent apps with explicit artifacts
- the orchestrator is sequencing-only
- file artifacts are the canonical interchange; registry is local cache/history
- the read-only MVP chain must be finished before new apply/PDF/deep-analysis work becomes the priority
