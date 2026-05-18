# Workflow Specification

This document is the top-down contract for the modular Obsidian + Zotero research assistant. It supersedes any earlier assumption that the system is one monolithic pipeline.

## MVP 0.1 Spec Freeze

Status: frozen for implementation planning.

Date: 2026-05-06.

Scope:

- project-paper triage without Zotero or permanent Obsidian writes by default;
- independent mini-projects with explicit input/output artifacts;
- one Obsidian human-review inbox configured through `.env`;
- repository-local runtime artifacts under `data/`, `papers/`, and `data/registry/`;
- local LLM first, using bounded metadata/products instead of raw PDFs;
- human approval before stage changes, Zotero writes, note drafts, and equation verification;
- reference mining and acquisition recommendations without automatic Zotero item creation.

Open questions: none blocking MVP 0.1. Implementation details such as `.env` loading, config migration, and current-test adaptation belong to mini-project 1.

## Architectural Principle

Each smaller project must be independently executable, independently testable, and responsible for its own outputs.

The orchestrator must not own domain logic. It only sequences commands, checks inputs/outputs, applies scheduling policy, records runs, and resumes work.

## Artifact Policy

Use a small number of global files when an artifact naturally describes many projects or many papers. Do not create folders that exist only to hold one file.

Use per-paper folders only for products that are specific to one paper and may grow over time.

Use a separate folder for SQLite state.

Recommended layout:

```text
data/
  projects.jsonl
  papers.jsonl
  candidates.jsonl
  classifications.jsonl
  reference_index.jsonl
  reference_match_review.jsonl
  reference_match_review.md
  review.md
  human_reviews.jsonl
  zotero_tag_plan.jsonl
  zotero_apply_plan.jsonl
  zotero_apply_report.jsonl
  obsidian_note_plan.jsonl
  obsidian_note_report.jsonl
  portfolio_audit.md

data/registry/
  registry.sqlite

papers/{citekey}/
  metadata_snapshot.json
  extracted_overview.json
  references.json
  section_products.json
  technical_products.json
  deep_analysis.json
```

Rules:

- `data/*.jsonl` and `data/*.md` are global workflow artifacts.
- `data/registry/registry.sqlite` is local state/cache/history.
- `papers/{citekey}/...` stores per-paper products extracted from metadata or PDF.
- `projects.jsonl` is a single canonical file and may be updated in place.
- `papers.jsonl` is a single canonical inventory file and may be updated in place.
- `reference_index.jsonl` is a global index of references extracted from reviewed/deep papers.
- Run history belongs in SQLite unless a module explicitly needs an exported report.

## Project Status Categories

`projects.jsonl` must include active and inactive research context. The scanner should categorize projects rather than emit only active ones.

Project state maps directly to the existing Obsidian `Efforts` structure. Tags may be useful as supplemental hints, but they are not the source of truth for state.

Allowed `project_state` values and default source mapping:

- `on`: notes under `Efforts/On`;
- `ongoing`: notes under `Efforts/Ongoing`;
- `simmering`: notes under `Efforts/Simmering`;
- `terminated`: notes under `Efforts/Terminated`.

Only `on` and `ongoing` should be matched/classified by default. `simmering` can be included through an explicit option. `terminated` is normally excluded from downstream automation but remains useful for context, redundancy, and history. `terminated` does not distinguish completed from abandoned projects because that distinction is not needed for workflow management.

`projects.jsonl` should contain extracted fields and `content_hash`, not the full note body. The system should not duplicate note contents unless a later module explicitly needs a bounded excerpt.

## Command Map

### `scan-obsidian`

Input: vault root and scan rules.

Output: `data/projects.jsonl`.

Role: read Obsidian as the intention layer and produce `ProjectProfile` rows for projects across all allowed states.

Side effects: writes only the local output file.

Independent MVP: fixture vault in, deterministic `projects.jsonl` out.

### `scan-zotero`

Input: Zotero API/export or fixture.

Outputs:

- `data/papers.jsonl`;
- `papers/{citekey}/metadata_snapshot.json` for each discovered paper.

Role: read Zotero as the evidence layer and produce `PaperProfile` rows plus per-paper metadata snapshots.

The metadata snapshot is a single complementable file. It may be updated when Zotero metadata is enriched, but updates must merge/preserve existing useful fields rather than erase previously stored content.

Side effects: read-only Zotero access; no tags, collection moves, or metadata writes.

Independent MVP: fake Zotero session or fixture in, deterministic `papers.jsonl` and metadata snapshots out.

### `extract-paper-products`

Input: `data/papers.jsonl` and local PDF paths.

Outputs:

- `papers/{citekey}/extracted_overview.json`;
- `papers/{citekey}/references.json`;
- `papers/{citekey}/section_products.json`;
- `papers/{citekey}/technical_products.json`.
- `papers/{citekey}/equations/*.png`.

Role: extract layer 1/2/3 products and references from PDFs without asking the LLM to reason deeply over raw PDFs.

Default scope:

- metadata and layer 1 overview products: all papers with available metadata/PDF;
- references: all papers in `.To Revise` and `.ToDig` where extraction is feasible;
- layer 2 section products: only after human decision or explicit selection;
- layer 3 technical products: only after human decision or explicit selection.

Layer extraction contract:

- layer 1 `overview`: metadata cross-check, abstract, keywords, headings, first/last-page signals, conclusion snippets, figure/table inventory, coarse document type;
- layer 2 `sections`: introduction/background, methods, data/case study, results, discussion, limitations, conclusions, and reference-section text where available;
- layer 3 `technical`: equation candidates in Obsidian-readable block LaTeX, source locations, PDF crop/image evidence paths, `equation_verified: false` by default, variables/symbols, assumptions, algorithms/workflows, validation evidence, datasets, implementation hooks, reproducibility signals, methodological caveats;
- `references`: bibliography entries with raw text, author or institution, year, title, DOI when available, and document type.

Because PDFs are not expected to change, extracted products may be maintained as single current files per paper. Updates must avoid data loss and should be driven by changed extraction code, missing fields, or explicit refresh.

Equation extraction is provisional. Technical JSON should store only the LaTeX body without `$$` delimiters. Markdown renderers should wrap the body in `$$` for Obsidian. Human verification is required before equations are used as confirmed formulas in notes, implementations, or deep analysis. Each equation candidate should include an image crop from the PDF region so the Markdown review can compare extracted LaTeX against visual evidence. PNG is the default crop format, with JPG or another raster format allowed as fallback.

Side effects: reads local PDFs and writes per-paper products.

Independent MVP: fixture PDF/text in, extracted overview and section products out.

### `mine-review-references`

Input: `papers/{citekey}/references.json`, `data/papers.jsonl`, and optional Zotero inventory.

Output: `data/reference_index.jsonl`.

Role: aggregate reference lists from `.To Revise` and `.ToDig` papers, identify frequently cited references, detect references not yet present in Zotero inventory, route uncertain non-DOI/fuzzy matches to a separate match-review report, and support later human capture decisions.

The global index should represent distinct referenced works and include all source papers that cited each reference. References cited by at least 5 source papers and missing from Zotero should be recommended for acquisition in a capture plan/report. The threshold `5` is initial and can be tuned later.

The reference index should preserve both simple citation count and weighted capture score. Initial weights are `.ToLook = 1.0`, `.To Revise = 1.5`, `.ToDig = 2.0`, and `Expendable = 1.0`; they must not change the simple count.

References may be articles, books, standards, reports, monographs, dissertations, theses, or unknown document types. Missing DOI is not an error. If no local PDF is known for the reference, recommend `attach_or_find_pdf`; when the item is absent from Zotero, this can accompany `acquire_new`.

Uncertain non-DOI/fuzzy matches should be written to `data/reference_match_review.jsonl` and a human-oriented `data/reference_match_review.md` rendering.

`data/reference_match_review.md` should use a Markdown table with an editable plain-text `decision` column. The allowed decision terms should be explained in the Markdown: `same_work`, `different_work`, `acquire_new`, `ignore`, and `attach_or_find_pdf`. For non-DOI references, the MVP comparison key is author + year + title.

Acquisition recommendations are advisory. The system does not insert new Zotero items from this project; the human adds the work to the `.ToLook` inbox/stage collection. Until the work appears in Zotero inventory, it remains in the recommendation plan. Once inventory confirms the item in `.ToLook`, remove it immediately from acquisition recommendations and route it through the standard paper workflow.

Side effects: writes only local reference-index artifacts. It does not import new Zotero items automatically.

Independent MVP: fixture reference lists in, ranked reference index out.

### `match`

Input: `data/projects.jsonl`, `data/papers.jsonl`, optional per-paper metadata/products.

Output: `data/candidates.jsonl`.

Role: reduce project-paper search space before LLM classification.

Default scope: `project_state in ["on", "ongoing"]`.

Keyword sources:

- extracted project fields from Obsidian;
- protocol taxonomy tags beginning with `#` and `%`;
- optional monitored sources/keywords configuration.

Side effects: writes only the local output file.

Operational filters:

- `--top-n`: cap candidates per project;
- `--max-candidates-total`: cap candidates across the whole run;
- `--paper-stages`: restrict candidate generation to papers currently in selected Zotero reading stages such as `.ToLook`, `.To Revise`, or `.ToDig`.

Independent MVP: fixture projects/papers in, deterministic top-N candidates out.

### `classify`

Input: projects, papers, candidates, taxonomy, prompt.

Output: `data/classifications.jsonl`.

Role: classify utility for each project-paper candidate using local LLM by default.

Default input layer: metadata only.

Side effects: local LLM call and local output write. No Zotero or Obsidian writes.

Operational filters:

- `--max-candidates`: safety cap on how many candidate rows are sent to the LLM from the current candidate file;
- `--paper-stages`: restrict the current classification run to candidates whose paper currently belongs to selected Zotero reading stages in `data/papers.jsonl`.

Independent MVP: fake LLM or recorded local response in, validated classifications out.

### `export-review`

Input: `data/classifications.jsonl`.

Output: `data/review-project-papers-YYYY-MM-DD.md`.

Role: create one Markdown review file per round. This remains true for MVP and final design.

Decision principle: there is no primary project. A paper must be assessed against all eligible projects before it is reported for human decision. If it has utility for any eligible project, it should not be treated as expendable by default. If it fits no eligible project well, it may be marked for discard/expendable handling later.

The review should aggregate all classifications for the same paper into one paper-level item. Inside that item, each project-paper match remains visible with its own utility class, score, reason, and recommended action.

Recommended grouping order for review readability:

1. papers with at least one `essential`, `methodological`, `formulational`, or `implementable` project match;
2. papers with only `case_study`, `review`, `counterpoint`, or `peripheral` matches;
3. papers with no useful project match, candidates for later expendable handling.

Within each group, sort by strongest project-paper score and then citekey/title for stability. This is only a display strategy; it must not collapse project-level decisions into a single primary-project decision.

Side effects: writes only the review Markdown file.

Independent MVP: fixture classifications in, parseable Markdown with YAML decision blocks out.

Current MVP implementation writes review Markdown locally by default using stable filenames under `data/`. A later phase may add an explicit export mode or orchestrator policy that copies those review artifacts into the configured Obsidian inbox. `VAULT_ROOT` should be absolute, and `OBSIDIAN_HUMAN_REVIEW_INBOX_DIR` remains the intended future destination for human-review files once the inbox handoff phase is implemented.

Review Markdown files and any supporting copied images should eventually be placeable directly in that inbox, without per-paper subfolders. Generated paper-note drafts also go to that inbox in later phases; the user manually moves them to the final Obsidian location.

Supporting image filenames copied to the inbox should be citekey-prefixed, for example `{citekey}-eq-001.png`, to avoid collisions in the flat inbox.

Use stable report filenames:

- `review-project-papers-YYYY-MM-DD.md`;
- `review-reference-matches-YYYY-MM-DD.md`;
- `review-equations-{citekey}-YYYY-MM-DD.md`.

These generated review files and paper-note drafts do not require frontmatter.

### `parse-review`

Input: `data/review-project-papers-YYYY-MM-DD.md`.

Output: `data/human_reviews.jsonl`.

Role: parse the edited Markdown review into structured `HumanReview` rows.

Side effects: writes only the local output file.

Independent MVP: edited fixture Markdown in, deterministic human review rows out.

### `apply-zotero-tags`

Input: `data/human_reviews.jsonl`, `data/papers.jsonl`, tag policy.

Outputs:

- `data/zotero_tag_plan.jsonl`;
- `data/zotero_apply_plan.jsonl`;
- `data/zotero_apply_report.jsonl`.

Role: plan and optionally apply Zotero tags for approved decisions.

Side effects: Zotero writes only when explicitly run without dry-run and only for approved decisions.

Independent MVP: dry-run plan only.

Safe apply contract: every real apply must be preceded by a dry-run plan and should apply that reviewed plan, not recalculate unseen mutations at write time. The dry-run plan must have a `plan_hash`; apply must receive or verify that exact hash before mutating Zotero.

The plan record should also include the hashes of the source review, source Zotero inventory, and source config/policy used to generate the plan.

For `Expendable`, the plan should verify whether a root-level Zotero collection exists. If it does not exist, the plan may include collection creation at the library root before item movement. An approved move to `Expendable` should remove the item from stage/triage collections such as `.ToLook`, `.To Revise`, and `.ToDig`, move it to `Expendable`, add `!discarded`, and remove mutually exclusive stage tags such as `@look`, `@review`, and `@dig`. Topic, project, paper, and other non-stage collections should be preserved.

### `generate-notes`

Input: human reviews, classifications, per-paper products, vault root.

Outputs:

- `data/obsidian_note_plan.jsonl`;
- `data/obsidian_note_report.jsonl`.

Role: plan and optionally create/update permanent Obsidian notes after approval.

Side effects: Obsidian writes only when explicitly run without dry-run, only for approved decisions, and only for papers in `.To Revise` or `.ToDig` that have a PDF plus extracted metadata and layer 1/2/3 products.

Independent MVP: dry-run note plan only.

### `deep-analyze-paper`

Input: approved reviews and per-paper products from `extract-paper-products`.

Output: `papers/{citekey}/deep_analysis.json`.

Role: perform deeper technical interpretation using the extracted products. It should not duplicate low-level extraction.

Side effects: local LLM call and per-paper artifact write.

Independent MVP: one approved paper fixture in, deep analysis JSON out.

### `generate-study-plan`

Input: human reviews, classifications, deep analyses.

Output: `data/study_plan.md` or a project-specific Markdown file if explicitly requested.

Role: convert approved evidence into reading, study, and reproduction plans.

Side effects: local report write.

Independent MVP: fixture approved reviews/classifications in, one Markdown plan out.

### `audit-portfolio`

Input: projects, papers, classifications, reviews, analyses.

Output: `data/portfolio_audit.md`.

Role: report gaps, redundancy, and maturity across the research portfolio.

Side effects: local report write.

Independent MVP: fixture portfolio in, stable Markdown audit out.

### `run triage`

Input: config and scheduling policy.

Outputs: outputs from the commands it invokes plus optional run/progress metadata.

Role: orchestrate safe triage by sequencing independent modules. It must not contain matching, classification, Zotero, or Obsidian business logic.

Planned nightly policy:

```text
nightly triage
  -> budget: max 10 papers total
  -> layers: .ToLook, .To Revise, .ToDig
  -> skip papers already evaluated in their current layer
  -> each layer uses its own analysis depth
```

Current stage contracts for that orchestrator:

- `.ToLook`: metadata-only triage;
- `.To Revise`: deeper structured review using richer extracted products once they exist;
- `.ToDig`: deepest technical/formulation/implementation review once richer products exist.

Current runnable sequence owned by independent commands:

```text
scan-obsidian
scan-zotero
match
classify
export-review
```

Selection rules that belong to the orchestrator layer rather than the business-logic commands:

- enforce one global nightly budget;
- divide that budget across configured Zotero reading stages;
- skip papers already evaluated in their current stage/layer;
- stop cleanly when the nightly budget or deadline is reached.

Side effects: only those of the invoked commands. The default triage sequence does not write Zotero and does not create permanent Obsidian notes.

## Review Contract

There is one review Markdown file per round. Each item must include a YAML decision block. Allowed values should be documented in Markdown near the review section instead of embedded as `allowed_*` keys inside every YAML block.

Review status:

- `decision: pending` means at least one required human decision is still incomplete;
- `decision: decided` means all required project-level decisions for the paper have been completed.

Project decision values:

- `pending`: not decided for this project yet;
- `approved`: useful for this project;
- `rejected`: not useful for this project;
- `deferred`: postpone this project-paper decision.

Paper-level `decision` is a completion marker, not the approval/rejection itself. The actual utility decisions live under `project_decisions`.

Minimum item block:

```yaml
review_id: review_2026-05-06_initial_triage
review_item_id: robertson1990soilclassification
citekey: robertson1990soilclassification
decision: pending
human_reason: ""
approved_actions:
  - read_now
apply_zotero_tags: false
create_obsidian_note: false
recommended_zotero_stage: ".To Revise"
stage_recommendation_reason: "approved project utility and Gate 2 score 4/6"
zotero_stage_decision: pending
manual_credibility: unknown
project_decisions:
  - project_id: cptu_bayesian_classification
    decision: pending
    approved_actions:
      - read_now
```

Allowed actions:

- `read_now`;
- `read_later`;
- `extract_equations`;
- `reproduce_code`;
- `summarize_only`;
- `link_to_project`;
- `ignore_for_now`.

Allowed Zotero stage decisions:

- `pending`: not decided yet;
- `keep_current`: do not move the item;
- `move_to_revise`: move from `.ToLook` to `.To Revise`;
- `move_to_dig`: move to `.ToDig`;
- `move_to_expendable`: move to `Expendable`;
- `manual_only`: handled outside automation.

Allowed `recommended_zotero_stage` values:

- `.ToLook`;
- `.To Revise`;
- `.ToDig`;
- `Expendable`.

Project-level decisions preserve the project-paper relationship. If any project-level decision is `approved`, the paper serves at least one project and should not be moved to `Expendable`. If any project-level decision is still `pending`, the paper-level `decision` must remain `pending` and the review item should remain open.

Zotero stage recommendation is related but separate. Papers already exist in `.ToLook`, `.To Revise`, or `.ToDig`; the system recommends stage changes, and the human review chooses the final `zotero_stage_decision`.

Reading stages are mutually exclusive. A paper should be in exactly one of `.ToLook`, `.To Revise`, `.ToDig`, or `Expendable` at a time. Each stage preserves earlier products and adds deeper analysis rather than duplicating the same work.

A paper with any approved project utility should generally move from `.ToLook` to `.To Revise` for layer 2/3 extraction. A paper with max project-paper adherence at least `0.80`, or a positive ToDig protocol gate, may be recommended for `.ToDig`.

If all project-level decisions are `rejected`, the system may recommend `Expendable`, but final movement remains human-approved.

An approved move to `Expendable` requires explicit human stage decision, should add `!discarded`, remove mutually exclusive stage tags such as `@look`, `@review`, and `@dig`, remove the item from stage/triage collections such as `.ToLook`, `.To Revise`, and `.ToDig`, and move it to root-level `Expendable`.

Moving a paper to `Expendable` must not delete local products under `papers/{citekey}/`. Local products are preserved for audit, future recovery, and to avoid losing already-paid extraction work.

Local products for `Expendable` papers remain eligible inputs for future reference mining.

Automatic runs should only use already extracted `Expendable` products. They should not spend new extraction work on `Expendable` papers unless a manual/explicit run requests it.

The reading protocol/gates in `docs/reading_protocol_criteria.md` are secondary evidence for `recommended_zotero_stage`, while project utility remains evaluated project by project.

Phase 1 metadata-only classification must still reject semantically incoherent combinations. In particular, useful/approved-looking classifications must not recommend `Expendable`, `extract_equations`/`reproduce_code` require `.ToDig`, and the classifier must not demote papers already in `.To Revise` or `.ToDig`.

Stage tags beginning with `@` must stay coherent with the final Zotero stage decision. `$` tags indicate concrete uses the paper brings, such as background citation, method citation, discussion value, extension value, or paper-specific use.

## LLM Input Layers

Local LLM is the default target. API-based LLMs may be supported later, but contracts should assume local compute constraints.

The classifier must receive bounded products, not raw PDFs.

Input layers:

- `metadata`: title, abstract, authors, year, DOI, tags, collections, citekey;
- `overview`: extracted overview, headings, selected first/last pages, conclusion snippets, captions;
- `sections`: introduction, methods, results, limitations, conclusion;
- `technical`: block LaTeX equation candidates, equation crop/image evidence, variable candidates, assumptions, algorithm steps, validation evidence, and human-verification status;
- `pdf_fallback`: raw PDF or full-page payloads only with explicit authorization.

Initial classification uses `metadata`. Reclassification may use higher layers after products are extracted.

## Nightly Execution

Some modules should run more frequently than others.

Recommended scheduling policy:

```yaml
scan_obsidian:
  frequency: nightly
scan_zotero:
  frequency: nightly
triage:
  frequency: nightly
  max_papers_total: 10
  layers:
    - stage: .ToLook
      target_items: 4
      input_layer: metadata
      only_if_not_evaluated_in_current_layer: true
    - stage: .To Revise
      target_items: 3
      input_layer: sections_or_best_available_products
      only_if_not_evaluated_in_current_layer: true
    - stage: .ToDig
      target_items: 3
      input_layer: technical_or_best_available_products
      only_if_not_evaluated_in_current_layer: true
match:
  frequency: nightly_or_on_inventory_change
  supports_stage_filters: true
classify:
  frequency: nightly_for_selected_candidates
  supports_stage_filters: true
  supports_max_candidates: true
extract_paper_products_deeper_layers:
  frequency: approved_or_selected_only
  max_items_per_run: 10
deep_analyze_paper:
  frequency: approved_only
  max_items_per_run: 5
apply_zotero_tags:
  frequency: manual_only
generate_notes:
  frequency: manual_only
```

The orchestrator should stop by both criteria:

- maximum wall-clock runtime;
- maximum item count per task/run.

When a wall-clock deadline is reached, the orchestrator should finish the currently running item/task safely, persist progress, and then stop before starting another item. For overnight use, a run can be configured to work until a deadline such as `06:00`.

Task-level timeouts are project-specific and should be defined by each module's own execution contract. The orchestrator owns deadline enforcement and sequencing, but individual projects own their safe timeout defaults.
