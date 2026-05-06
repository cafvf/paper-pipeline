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

Each planned module must have an independent MVP and tests. Integration defects found later should be fixed in the owning module, while the orchestrator remains a thin sequencing layer.

Each module should define its own task-level timeout defaults when execution risk requires it. The orchestrator should honor those module contracts instead of hardcoding every timeout centrally.

### `obsidian_inventory`

Responsibility: read active project notes and emit `ProjectProfile`.

Inputs: vault root, include/exclude globs, frontmatter, tags, links.

Outputs: project profiles and content hashes.

Side effects: none in scan mode.

Tests expected: frontmatter parsing, project-state categorization from `Efforts`, path safety, malformed YAML tolerance, no full note body in output.

Current related files: `paper_pipeline/vault_index.py`.

Future suggested files: `paper_pipeline/obsidian_inventory.py`, `tests/test_obsidian_inventory.py`.

Output artifact: `data/projects.jsonl`.

Allowed project states: `on`, `ongoing`, `simmering`, `terminated`, mapped from the existing `Efforts` structure.

### `zotero_inventory`

Responsibility: read Zotero metadata into neutral `PaperProfile` records.

Inputs: Zotero API/export, Better BibTeX citekeys, collections, tags, title, abstract, year, DOI, authors.

Outputs: `papers.jsonl`, complementable per-paper metadata snapshots, and/or registry rows.

Side effects: API read only; no library writes.

Tests expected: fake session pagination, citekey extraction, metadata normalization, metadata update without data loss, no secret logging.

Current related files: `paper_pipeline/zotero_api.py`, `paper_pipeline/zotero_adapter.py`.

Future suggested files: `paper_pipeline/zotero_inventory.py`, `tests/test_zotero_inventory.py`.

Output artifacts: `data/papers.jsonl` and `papers/{citekey}/metadata_snapshot.json`.

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

LLM input policy: local LLM by default; metadata-only for the first classifier; overview/section/technical products only after extraction; raw PDF only as explicit fallback.

Classification output may include a recommended Zotero reading stage, but that recommendation is distinct from project-level utility decisions.

Stage recommendation should use `docs/reading_protocol_criteria.md` as secondary criteria and should record gate evidence.

### `review_export`

Responsibility: render grouped Markdown review reports for human approval.

Inputs: classifications grouped by citekey/paper, with project-paper matches preserved inside each paper item.

Outputs: one review Markdown per round with editable YAML decision blocks.

Side effects: writes a review report to a configured output/inbox path only.

Tests expected: grouping, escaping, stable ordering, parseable decision blocks.

Current related files: `paper_pipeline/decision_notes.py`, `paper_pipeline/assessment_notes.py`.

Future suggested files: `paper_pipeline/review_export.py`, `tests/test_review_export.py`.

Output artifact: `data/review.md`.

Each YAML block must include `review_id`, `review_item_id`, one paper-level completion status, one Zotero-stage decision, and project-level decisions for each project-paper match. Allowed values should be shown in Markdown, not repeated as `allowed_*` YAML keys.

### `zotero_sync`

Responsibility: apply additive Zotero tags after approval.

Inputs: approved human reviews, tag policy, paper identifiers.

Outputs: Zotero API apply results.

Side effects: writes Zotero tags/collections; must be approval-gated.

Tests expected: dry-run plan, `plan_hash` verification plus source hashes, additive tags, no metadata overwrite, no removal by default, explicit removal of stage tags during stage movement, root-level Expendable collection check/create planning, and removal from stage/triage collections when Expendable movement is approved.

Current related files: `paper_pipeline/zotero_plan.py`, `paper_pipeline/decision_applier.py`.

Future suggested files: `paper_pipeline/zotero_sync.py`.

### `pdf_product_extraction`

Responsibility: extract bounded products from PDFs for later LLM use.

Inputs: paper profile and local PDF.

Outputs: overview, references, section, and technical products.

Side effects: reads PDF, writes per-paper artifacts.

Tests expected: conversion fallback, layer-specific output fields, missing-PDF behavior, all extracted products saved, product refresh without data loss.

Current related files: `paper_pipeline/pdf_ingest.py`, `paper_pipeline/reading_packet.py`, `paper_pipeline/analysis_engine.py`.

Future suggested files: `paper_pipeline/pdf_products.py`, `tests/test_pdf_products.py`.

Output artifacts: `papers/{citekey}/extracted_overview.json`, `papers/{citekey}/references.json`, `papers/{citekey}/section_products.json`, `papers/{citekey}/technical_products.json`, and equation crop images under `papers/{citekey}/equations/`.

Default scope: overview for all papers with PDFs where feasible; sections and technical products only after human decision or explicit selection.

References should also be extracted for `.To Revise` and `.ToDig` papers when feasible.

Layer contents:

- layer 1 `overview`: metadata cross-check, abstract, keywords, headings, first/last-page signals, conclusion snippets, figure/table inventory, coarse document type;
- layer 2 `sections`: introduction/background, methods, data/case study, results, discussion, limitations, conclusions, reference-section text;
- layer 3 `technical`: equation candidates in Obsidian-readable block LaTeX, source locations, PDF crop/image evidence paths, `equation_verified: false` by default, variables/symbols, assumptions, algorithms/workflows, validation evidence, datasets, implementation hooks, reproducibility signals, methodological caveats;
- `references`: bibliography entries with raw text, author or institution, year, title, DOI when available, and document type.

Technical JSON stores only the equation body, without `$$` delimiters. Markdown review renderers add the `$$` delimiters for Obsidian. Equation evidence images should default to PNG, with JPG or another raster format as fallback. Evidence images should be saved in `papers/{citekey}/equations/` and copied beside the Obsidian equation-review Markdown report for reliable relative links.

### `reference_mining`

Responsibility: aggregate extracted references, build citation statistics, and identify important missing or frequent references.

Inputs: per-paper `references.json`, Zotero paper inventory.

Outputs: ranked reference index and optional capture recommendations.

Side effects: writes local artifacts only; no Zotero imports.

Tests expected: reference normalization, duplicate detection, DOI-first matching, author/year/title fallback for non-DOI references, non-DOI document types, conservative Zotero-presence matching, separate match-review report for fuzzy/non-DOI cases, cited-by tracking, simple citation count, weighted capture score, capture recommendation for missing references cited by 5+ source papers, attach/find-PDF recommendation for matched Zotero items without PDFs.

Future suggested files: `paper_pipeline/reference_mining.py`, `tests/test_reference_mining.py`.

Output artifacts: `data/reference_index.jsonl`, and when needed, `data/reference_match_review.jsonl` plus `data/reference_match_review.md`.

Reference index rows should represent a distinct referenced work and list all source papers that cited it.

The module should keep both `citation_count_in_corpus` and `capture_recommendation_score`. Initial score weights are `.ToLook = 1.0`, `.To Revise = 1.5`, `.ToDig = 2.0`, and `Expendable = 1.0`, while the simple count remains unchanged. `capture_priority` should be derived from the weighted score and the simple `5+` citation threshold without hiding either input.

References without a known local PDF should be listed with an `attach_or_find_pdf` follow-up action. If they are already matched in Zotero, they should not be recommended for acquisition; if absent from Zotero, acquisition and PDF follow-up can both be recommended.

Missing DOI is expected for books, standards, reports, monographs, dissertations, and theses. Those records should remain in the reference index and be routed to match review when automatic Zotero presence cannot be confirmed confidently.

Reference match review decisions should support `same_work`, `different_work`, `acquire_new`, `ignore`, and `attach_or_find_pdf`.

Acquisition is advisory only. The module should keep recommending absent references until the human has added them to Zotero, normally in `.ToLook`, and a later Zotero inventory confirms their presence. Confirmed `.ToLook` items should disappear immediately from acquisition recommendations and enter the standard paper workflow.

For `Expendable` papers, reference mining may consume products that already exist, but it should not trigger new extraction work unless explicitly requested by a manual run.

### `note_generation`

Responsibility: create or update permanent Obsidian literature notes for approved papers.

Inputs: human review, classifications, per-paper products, vault root.

Outputs: Obsidian note plan and note report.

Side effects: Obsidian writes only after explicit apply.

Tests expected: dry-run plan, no note for papers without PDFs, no note for papers outside `.To Revise`/`.ToDig`, no note before metadata plus layer 1/2/3 products exist, no duplicate citekey notes, existing-note frontmatter preservation when patching, project-link preservation, `plan_hash` verification before apply.

Current related files: `paper_pipeline/knowledge_application.py`, `paper_pipeline/note_patcher.py`.

Future suggested files: `paper_pipeline/note_generation.py`, `tests/test_note_generation.py`.

Output artifacts: `data/obsidian_note_plan.jsonl` and `data/obsidian_note_report.jsonl`.

### `deep_analysis`

Responsibility: interpret approved papers using extracted products.

Inputs: approved human review, classification, and per-paper products.

Outputs: structured deep analysis.

Side effects: local LLM call and per-paper artifact write.

Tests expected: consumes products instead of raw PDF by default, rejects unsupported fallback without explicit option, validates analysis schema.

Current related files: `paper_pipeline/analysis_engine.py`, `paper_pipeline/llm_schema.py`.

Future suggested files: `paper_pipeline/deep_analysis.py`, `tests/test_deep_analysis.py`.

Output artifact: `papers/{citekey}/deep_analysis.json`.
