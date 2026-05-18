# Architecture

## Current Repository Shape

The repository is a Python package named `paper_pipeline`, with an executable CLI `paper-pipeline`. It currently implements a standalone Zotero-driven paper triage pipeline:

- configuration: `paper_pipeline/config.py`, `config.example.yaml`;
- CLI: `paper_pipeline/cli.py`, compatibility `cli.py`;
- Zotero API and in-memory adapter: `paper_pipeline/zotero_api.py`, `paper_pipeline/zotero_adapter.py`;
- Zotero collection/tag planning: `paper_pipeline/zotero_collections.py`, `paper_pipeline/zotero_plan.py`;
- Obsidian/vault lexical index: `paper_pipeline/vault_index.py`;
- candidate selection: `paper_pipeline/selection.py`;
- embeddings client/status: `paper_pipeline/embeddings.py`;
- local LLM client and JSON validation: `paper_pipeline/lmstudio_chat.py`, `paper_pipeline/llm_schema.py`;
- PDF ingestion and reading packets: `paper_pipeline/pdf_ingest.py`, `paper_pipeline/reading_packet.py`;
- decision notes and application: `paper_pipeline/decision_notes.py`, `paper_pipeline/decision_applier.py`;
- Obsidian knowledge-note draft application: `paper_pipeline/knowledge_application.py`, `paper_pipeline/note_patcher.py`;
- runtime artifacts: `paper_pipeline/artifacts.py`;
- orchestration: `paper_pipeline/runner.py`.

## Current Flow

```text
Zotero operational collections
  -> CandidatePaper list
  -> vault lexical index
  -> selection score and quotas
  -> optional PDF conversion
  -> reading packet
  -> LM Studio assessment
  -> schema validation
  -> Obsidian inbox decision note
  -> human YAML decision
  -> optional Zotero collection/tag plan
  -> optional local knowledge drafts
  -> paper artifacts and logs
```

The current unit of work is mostly an article in an operational collection such as `.ToLook`, `.To Revise`, or `.ToDig`.

## Target Project-Paper Flow

```text
Obsidian project notes
  -> ProjectProfile records

Zotero metadata
  -> PaperProfile records

ProjectProfile + PaperProfile
  -> ProjectPaperCandidate records
  -> LLMClassification records
  -> HumanReview Markdown report
  -> approved decisions only
  -> optional Zotero tags and permanent Obsidian paper notes
```

The target unit of work is the pair `project_id + citekey`.

## Independence Principle

The target system is not a monolithic pipeline. Each smaller project must be able to run by itself, accept explicit inputs, produce explicit outputs, and be tested independently.

The orchestrator is a sequencing layer only. It must not contain matching rules, prompt logic, Zotero mutation logic, Obsidian note-generation rules, or PDF extraction logic. Those responsibilities stay in the individual projects.

See `docs/workflow_spec.md` for the command and artifact contract.

## Artifact Boundaries

Global artifacts that summarize many projects or many papers should stay as named files under `data/`.

Per-paper products should stay under `papers/{citekey}/` because they naturally grow over time and belong to one paper.

SQLite state should stay under `data/registry/`.

Recommended rule:

```text
data/*.jsonl or data/*.md      -> global workflow artifacts
papers/{citekey}/*.json        -> per-paper products
data/registry/registry.sqlite  -> cache, hashes, run history
```

## Module Boundaries

Read-only modules:

- Obsidian inventory: scans notes and frontmatter;
- Zotero inventory: reads metadata and attachments;
- matching: computes candidates;
- classification: calls LLM and validates JSON;
- review export: writes only review reports to a configured output/inbox path.

Stateful local modules:

- registry/cache: stores SQLite rows, hashes, run metadata, and classification history;
- artifacts: stores non-secret runtime JSON and logs under configured runtime directories.

Approval-gated write modules:

- Zotero sync: applies additive tags only after human approval;
- Obsidian note generation: creates or patches permanent notes only after human approval, only for papers in `.To Revise` or `.ToDig`, and only after PDF-backed metadata plus layer 1/2/3 products exist.

Deep-analysis modules:

- PDF product extraction: extracts bounded layer 1/2/3 products from PDFs;
- deep paper analysis: interprets extracted products after relevance is approved;
- study planner and audit: consume approved classifications and analyses.

## LLM Boundary

LLM calls should receive only the minimum needed context for the current step. For MVP 0.1 this means:

- project title, objectives, methods, gaps, outputs, priority;
- paper title, abstract, year, authors, tags, collections, DOI;
- candidate evidence;
- utility taxonomy and allowed actions.

The output must be a single JSON object validated before storage or rendering.

Current evidence: `paper_pipeline/llm_schema.py` already renders JSON Schema and validates LLM assessment output, but the schema is for reading-stage assessment rather than project-paper utility.

The local LLM should receive bounded text or structured products, not raw PDFs. Raw PDF/full-page fallback should require explicit authorization. The initial project-paper classifier uses metadata only; later reclassification may use overview, section, or technical products extracted by a separate module.

## Embeddings Boundary

Embeddings should reduce candidate space before classification. Current evidence: `paper_pipeline/embeddings.py` has an LM Studio embeddings client and degraded/lexical fallback status, while `paper_pipeline/selection.py` currently scores using lexical overlap and heuristics.

For the project-paper roadmap, embeddings should compare:

- project text: title + objectives + methods + gaps;
- paper text: title + abstract + tags + collections.

Project state should come from the existing `Efforts` layout rather than example tags. `projects.jsonl` should store extracted fields and `content_hash`, not full note bodies.

## SQLite And Cache Boundary

The repository now has a SQLite registry implementation in `paper_pipeline/registry.py` with tables for:

- `projects`;
- `papers`;
- `project_paper_candidates`;
- `llm_classifications`;
- `human_reviews`;
- `processing_runs`;
- `hashes`.

Current evidence: `sync-registry` is exposed in `paper_pipeline/cli.py`, the schema exists in `paper_pipeline/registry.py`, and tests cover registry initialization, sync, rollback, and pair-level hash checks in `tests/test_registry.py`.

Current remaining gap: the registry is already real, but runtime write-through for candidates, classifications, reviews, and completed hash state is not yet wired into the end-to-end project-paper command flow. Until that exists, file artifacts should remain the canonical interchange and registry skip behavior should only be trusted where completion is explicitly recorded.

## External-Service Safety

Zotero API credentials are read from environment variables in `paper_pipeline/zotero_api.py`; no `.env` values were inspected for this audit. `run --dry-run` falls back to a no-op source if credentials are missing. `zotero-dry-run` currently calls `ZoteroApiAdapter.from_env()` and lists candidates, so it is not a fully offline command.

No real Zotero API call or real Obsidian vault write was performed during this documentation pass.
