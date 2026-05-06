# Modules

## Current Modules

| Module | Responsibility | Inputs | Outputs | Side effects | Related files |
| --- | --- | --- | --- | --- | --- |
| configuration | Resolve vault/runtime paths and LM Studio settings. | YAML config, CLI overrides. | `RuntimeConfig`. | None except path resolution. | `paper_pipeline/config.py`, `config.example.yaml` |
| CLI | Expose current operational commands. | CLI args. | Exit code and console summary. | May run API reads or pipeline writes depending on command. | `paper_pipeline/cli.py`, `cli.py` |
| Zotero API | Read items/collections and apply plans. | Env vars, Zotero API, data dir. | `CandidatePaper`, collection maps, apply result. | `apply_plan` writes Zotero through PUT. | `paper_pipeline/zotero_api.py` |
| Zotero memory adapter | Test-safe adapter. | In-memory `ZoteroItem` records. | `CandidatePaper`, apply result. | Mutates in-memory data only. | `paper_pipeline/zotero_adapter.py` |
| Vault index | Index selected Markdown context. | Vault root. | Lexical JSON index. | Optional index file write via `write_index`. | `paper_pipeline/vault_index.py` |
| Selection | Score and choose paper batches. | Candidates, lexical index. | Selected and missing-PDF lists. | None. | `paper_pipeline/selection.py` |
| Embeddings | Optional LM Studio embedding client/status. | Texts, LM Studio config. | Vectors or degraded status. | Network call to local LM Studio if configured. | `paper_pipeline/embeddings.py` |
| LLM assessment | Validate reading-stage JSON output. | LLM text, stage schema. | `LLMAssessment`. | None. | `paper_pipeline/llm_schema.py`, `paper_pipeline/lmstudio_chat.py` |
| PDF ingest | Convert PDFs and cache conversion artifacts. | PDF path. | Manifest, conversion report, extracted text/JSON. | Writes runtime artifacts under paper root. | `paper_pipeline/pdf_ingest.py` |
| Reading packets | Build stage-specific LLM context from converted PDFs. | Candidate and converted docs. | Packet dict. | None. | `paper_pipeline/reading_packet.py`, `paper_pipeline/reading_plan.py` |
| Assessment notes | Render human decision notes. | `LLMAssessment`, candidate metadata. | Markdown text. | None by itself. | `paper_pipeline/assessment_notes.py`, `paper_pipeline/decision_notes.py` |
| Decision application | Parse approved notes and apply allowed actions. | Decision note, artifact store, optional Zotero applier. | Application result. | Can delete inbox note, write logs, write Zotero, create knowledge drafts. | `paper_pipeline/decision_applier.py` |
| Knowledge application | Create or patch local knowledge drafts after approval. | Assessment artifact, decision, vault root. | Draft/patch actions. | Writes configured vault paths. | `paper_pipeline/knowledge_application.py`, `paper_pipeline/note_patcher.py` |
| Artifacts | Store runtime JSON/history/logs. | Paper root and citekey. | File paths. | Writes under `papers_root`. | `paper_pipeline/artifacts.py` |
| Runner | Orchestrate current pipeline. | Config, Zotero source, lexical index, analyzer. | `NightlyRunResult`. | Writes inbox notes/artifacts; may apply decisions. | `paper_pipeline/runner.py` |

## Planned Project-Paper Modules

### `obsidian_inventory`

Responsibility: read active project notes and emit `ProjectProfile`.

Inputs: vault root, include/exclude globs, frontmatter, tags, links.

Outputs: project profiles and content hashes.

Side effects: none in scan mode.

Tests expected: frontmatter parsing, `#projeto` detection, inactive-note exclusion, path safety, malformed YAML tolerance.

Current related files: `paper_pipeline/vault_index.py`.

Future suggested files: `paper_pipeline/obsidian_inventory.py`, `tests/test_obsidian_inventory.py`.

### `zotero_inventory`

Responsibility: read Zotero metadata into neutral `PaperProfile` records.

Inputs: Zotero API/export, Better BibTeX citekeys, collections, tags, title, abstract, year, DOI, authors.

Outputs: `papers.jsonl` and/or registry rows.

Side effects: API read only; no library writes.

Tests expected: fake session pagination, citekey extraction, metadata normalization, no secret logging.

Current related files: `paper_pipeline/zotero_api.py`, `paper_pipeline/zotero_adapter.py`.

Future suggested files: `paper_pipeline/zotero_inventory.py`, `tests/test_zotero_inventory.py`.

### `registry`

Responsibility: store projects, papers, candidates, classifications, human decisions, processing runs, and hashes.

Inputs: profiles, candidate rows, classifications, reviews.

Outputs: SQLite rows and query results.

Side effects: writes local DB only.

Tests expected: migrations, idempotent upserts, hash-based skip logic.

Current related files: `paper_pipeline/artifacts.py`.

Future suggested files: `paper_pipeline/registry.py`, `migrations/`, `tests/test_registry.py`.

### `matching`

Responsibility: reduce project-paper candidate space before LLM calls.

Inputs: `ProjectProfile`, `PaperProfile`, lexical rules, optional embeddings.

Outputs: `ProjectPaperCandidate` with score and evidence.

Side effects: none, except optional cache writes through registry.

Tests expected: deterministic lexical ranking, top-N limits, evidence generation, embedding fallback.

Current related files: `paper_pipeline/selection.py`, `paper_pipeline/embeddings.py`.

Future suggested files: `paper_pipeline/matching.py`, `tests/test_matching.py`.

### `classification`

Responsibility: classify utility of a candidate paper for one specific project.

Inputs: project profile, paper profile, candidate evidence, taxonomy, prompt.

Outputs: validated `LLMClassification`.

Side effects: LLM call and registry/artifact write.

Tests expected: JSON Schema validation, invalid class rejection, prompt hash tracking, no prose outside JSON.

Current related files: `paper_pipeline/llm_schema.py`, `paper_pipeline/lmstudio_chat.py`.

Future suggested files: `paper_pipeline/project_paper_classification.py`, `schemas/llm_classification.schema.json`.

### `review_export`

Responsibility: render grouped Markdown review reports for human approval.

Inputs: classifications grouped by project and utility class.

Outputs: review Markdown with editable decisions.

Side effects: writes a review report to a configured output/inbox path only.

Tests expected: grouping, escaping, stable ordering, parseable decision blocks.

Current related files: `paper_pipeline/decision_notes.py`, `paper_pipeline/assessment_notes.py`.

Future suggested files: `paper_pipeline/review_export.py`, `tests/test_review_export.py`.

### `zotero_sync`

Responsibility: apply additive Zotero tags after approval.

Inputs: approved human reviews, tag policy, paper identifiers.

Outputs: Zotero API apply results.

Side effects: writes Zotero tags/collections; must be approval-gated.

Tests expected: dry-run plan, additive tags, no metadata overwrite, no removal by default.

Current related files: `paper_pipeline/zotero_plan.py`, `paper_pipeline/decision_applier.py`.

Future suggested files: `paper_pipeline/zotero_sync.py`.

### `pdf_analysis`

Responsibility: deep analysis of approved relevant PDFs.

Inputs: approved paper/project pair and local PDF.

Outputs: structured technical analysis.

Side effects: reads PDF, writes artifacts.

Tests expected: conversion fallback, no invented equations in schema, missing-PDF behavior.

Current related files: `paper_pipeline/pdf_ingest.py`, `paper_pipeline/reading_packet.py`, `paper_pipeline/analysis_engine.py`.

Future suggested files: reuse current modules after adding approval gates.

