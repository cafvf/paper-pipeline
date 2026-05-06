# Development Plan

This plan keeps the next cycles small and reversible. It assumes no real Zotero or permanent Obsidian writes until the safe base is working.

Each project below must be implemented and tested independently. Integration and sequencing belong to the orchestrator project, which should come after the smaller projects have stable command contracts and output artifacts.

## Cycle 1: Contracts And Fixtures

Tasks:

- migrate configuration contracts to `.env` for Obsidian paths and keep `config.example.yaml` focused on runtime/local pipeline settings;
- require absolute `VAULT_ROOT` and a single `OBSIDIAN_HUMAN_REVIEW_INBOX_DIR`;
- adapt existing tests that still exercise old internal `vault_root`/`inbox_dir` config fields while preserving compatibility where needed during migration;
- add `schemas/project_profile.schema.json`;
- add `schemas/paper_profile.schema.json`;
- add `schemas/project_paper_match.schema.json`;
- add `schemas/llm_classification.schema.json`;
- add `configs/utility_taxonomy.yaml`;
- add `configs/zotero_tags.yaml`;
- add `configs/prompts.yaml`;
- add `configs/monitored_sources.yaml`;
- add tests that validate example JSON against schemas.
- document command inputs/outputs from `docs/workflow_spec.md` in schema examples.

Acceptance:

- `uv run ruff check`;
- `uv run pytest -q -o addopts=`;
- configuration examples contain no legacy `vault_root`, `inbox_dir`, `templates_dir`, or `PAPERS_DIR` fields;
- `.env.example` contains placeholders only and no real local paths;
- invalid LLM utility classes are rejected.
- invalid review decisions and invalid input layers are rejected.
- `archived` is not an allowed project state.
- review YAML does not contain repeated `allowed_*` keys.
- paper-level review decisions are limited to `pending` and `decided`.

Risks:

- over-designing schemas too early.

Mitigation:

- keep required fields minimal for MVP 0.1.

## Cycle 2: Obsidian Project Inventory

Tasks:

- implement read-only project scanner;
- map project state from `Efforts/On`, `Efforts/Ongoing`, `Efforts/Simmering`, and `Efforts/Terminated`;
- extract title, objectives, methods, gaps, outputs, priority, tags, links, hash;
- categorize projects by the existing `Efforts` layout: `On`, `Ongoing`, `Simmering`, and `Terminated`;
- avoid writing full note bodies to `projects.jsonl`;
- add fixture vault tests.

Acceptance:

- scanner returns `projects.jsonl` with all supported project states and `content_hash`;
- downstream defaults can include only `on` and `ongoing`;
- output contains extracted fields only, not duplicated full note content;
- malformed frontmatter does not crash the run.

Risks:

- scanning too much private vault content.

Mitigation:

- require explicit vault path and include globs; show counts, not raw full text, by default.

## Cycle 3: Zotero Metadata Inventory

Tasks:

- implement neutral `PaperProfile` export;
- reuse citekey extraction from `zotero_api.py`;
- provide fake-session tests and optional fixture input;
- export `papers.jsonl` in a configured runtime path.
- write `papers/{citekey}/metadata_snapshot.json` for each paper.

Acceptance:

- no Zotero writes;
- exports one article per line;
- metadata snapshot is saved per paper;
- metadata snapshot updates preserve useful existing fields;
- no API keys or user IDs in output.

Risks:

- `zotero-dry-run` currently still reads the real API when credentials exist.

Mitigation:

- add an explicit offline fixture path for tests and demos.

## Cycle 4: Registry Skeleton

Tasks:

- add SQLite schema/migration for projects, papers, candidates, classifications, reviews, runs, hashes;
- add idempotent upserts;
- store project, paper, and prompt hashes;
- expose skip decision for unchanged project-paper pairs.

Acceptance:

- running the same fixture twice does not duplicate rows;
- unchanged pairs are skipped.

Risks:

- committing local DB files.

Mitigation:

- keep DB path ignored/runtime-only; commit migrations/tests, not data.

## Cycle 5: Matching MVP

Tasks:

- create project text and paper text builders;
- implement lexical scoring with evidence strings;
- return top 20 candidates per project;
- optionally use existing embedding client when configured.

Acceptance:

- deterministic fixture ranking;
- each candidate includes evidence;
- no LLM call in matching.

Risks:

- poor recall from lexical matching.

Mitigation:

- allow manual keywords and later embeddings.

## Cycle 6: Utility Classification MVP

Tasks:

- create project-paper prompt using taxonomy and metadata-layer inputs;
- validate single-object JSON;
- classify top 10 candidates per project;
- store prompt/model/run metadata.

Acceptance:

- all outputs validate against schema;
- invalid confidence/action/utility values fail tests;
- classifications include reason, possible uses, limitations, and review requirement.
- classifications record `input_layer` and `input_products`.
- classifications may recommend Zotero reading stage using project utility plus secondary reading-protocol evidence.
- ToDig recommendations use initial threshold `0.80` or a passed ToDig protocol gate.

Risks:

- LLM hallucination or overconfidence.

Mitigation:

- require evidence-limited reasons and `requires_human_review: true`.

## Cycle 7: Review Export MVP

Tasks:

- generate grouped Markdown report;
- group by project and utility class;
- include editable YAML decisions with allowed values for every editable key;
- include the recommended action prefilled in `approved_actions`;
- aggregate all project-paper matches for the same citekey into one paper-level review item;
- include project-level decisions for each project match;
- document allowed values in Markdown instead of repeating them inside YAML;
- include recommended Zotero stage and editable Zotero-stage decision;
- include stage recommendation reason and protocol gate evidence;
- parse decisions in tests.

Acceptance:

- review report is stable and readable;
- parsed decisions retain `review_id`, `review_path`, and `review_item_id`;
- parser treats paper-level `pending` as incomplete and `decided` as complete;
- parser requires every project-level decision to be non-pending before paper-level `decided`;
- parser prevents discard/expendable handling when any eligible project decision is approved;
- no Zotero writes;
- no permanent Obsidian notes.

## Cycle 8: PDF Product Extraction

Tasks:

- extract overview products for all papers with PDFs where feasible;
- extract reference lists for `.To Revise` and `.ToDig` papers where feasible;
- extract section and technical products only after human decision or explicit selection;
- define and test required fields for layer 1 overview, layer 2 sections, layer 3 technical products, and references;
- save every extracted product under `papers/{citekey}/`;
- avoid deep interpretation in this module;
- add tests with small fixture PDFs or text-based converter fakes.

Acceptance:

- outputs are deterministic for fixtures;
- all extracted products are saved;
- current product files can be refreshed without data loss;
- missing PDFs produce structured skipped/error records;
- layer outputs contain the required contract fields;
- technical products store equation candidates in Obsidian-readable block LaTeX with `equation_verified: false` until human review;
- technical products include PDF crop/image evidence paths for equation comparison;
- no LLM deep analysis is performed.

## Cycle 8B: Reference Mining

Tasks:

- aggregate `papers/{citekey}/references.json`;
- normalize references by DOI when available, otherwise by author/institution + year + title;
- compare against `papers.jsonl`;
- report frequent missing references and citation counts.
- track which source papers cited each reference;
- preserve references without DOI as valid records;
- classify reference type when possible: article, book, standard, report, monograph, dissertation, thesis, or unknown;
- recommend missing references cited by at least 5 source papers for acquisition.
- write separate match-review rows for fuzzy or non-DOI cases that need manual inspection;
- render a human-oriented Markdown match-review report alongside JSONL;
- keep simple citation count separate from weighted capture recommendation score.
- use initial capture weights `.ToLook = 1.0`, `.To Revise = 1.5`, `.ToDig = 2.0`, and `Expendable = 1.0`;
- recommend `attach_or_find_pdf` whenever no local PDF is known for the reference.

Acceptance:

- duplicate references collapse deterministically;
- references already in Zotero are matched when possible;
- DOI wins deduplication when available;
- fallback deduplication uses author + year + normalized title;
- books, standards, reports, monographs, dissertations, and theses without DOI are preserved;
- fuzzy matches are routed to review and do not set `in_zotero: true` automatically;
- match-review report is separate from capture recommendations;
- match-review report supports `same_work`, `different_work`, `acquire_new`, `ignore`, and `attach_or_find_pdf`;
- acquisition recommendations do not create Zotero items, persist until inventory confirms human capture in `.ToLook`, then disappear from acquisition reports and enter the standard workflow;
- each indexed reference lists all citing source papers;
- weighted capture score can prioritize `.ToDig` and `.To Revise` sources without changing simple citation count;
- `Expendable` products remain eligible for reference mining and count with the same weight as `.ToLook`;
- automatic runs use only already extracted `Expendable` products unless a manual run requests new extraction;
- `capture_priority` is derived from the documented score thresholds and the simple `5+` threshold;
- missing references cited by 5+ source papers are flagged for capture recommendation;
- matched Zotero references without local PDFs are flagged for attach/find PDF;
- no Zotero import or write occurs.

## Cycle 8C: Zotero Apply Planning

Tasks:

- generate immutable dry-run plans with `plan_hash` plus source review, inventory, and config/policy hashes;
- require apply to receive the same plan path and expected hash;
- check whether the `Expendable` collection exists;
- include root-level collection creation in the dry-run plan if `Expendable` is missing;
- for approved Expendable movement, plan removal from stage/triage collections, movement to `Expendable`, addition of `!discarded`, and removal of mutually exclusive `@` stage tags.

Acceptance:

- apply refuses changed plan content;
- apply refuses direct mutation without a reviewed plan hash;
- dry-run shows collection creation before item movement when needed;
- Expendable movement removes stage/triage collection memberships in the plan while preserving topic/project/paper collections;
- no real Zotero write occurs in tests.

## Cycle 8D: Obsidian Note Planning

Tasks:

- generate immutable dry-run note plans with `plan_hash`;
- require apply to receive the same plan path and expected hash;
- create note plans only for approved papers in `.To Revise` or `.ToDig` with available PDFs;
- require metadata plus layer 1/2/3 extracted products before note planning;
- use the extracted products as the source material for the literature note;
- skip metadata-only items with a structured reason;
- support existing `.To Revise` and `.ToDig` papers that already need literature notes.

Acceptance:

- no note plan is generated for papers without PDFs, outside `.To Revise`/`.ToDig`, or without required extracted products;
- changed note plans are rejected by apply;
- duplicate citekey notes are detected;
- existing-note frontmatter and Obsidian wikilinks are preserved when patching;
- no real Obsidian write occurs in tests.

## Cycle 8E: Equation Review Export

Tasks:

- generate one Obsidian Markdown equation-review file per paper;
- render equation candidates as block LaTeX;
- include PDF crop/image evidence for each equation;
- store only LaTeX body in JSON and add `$$` delimiters during Markdown rendering;
- default equation evidence images to PNG with JPG or another raster fallback;
- write review files to the single configured Obsidian human-review inbox from `.env` or environment/configuration;
- copy equation evidence images beside the Obsidian equation-review Markdown file in the single inbox, without per-paper subfolders, while preserving the canonical copy under `papers/{citekey}/equations/`;
- use citekey-prefixed image names in the inbox to avoid collisions;
- document allowed equation review decisions in the Markdown;
- parse `pending`, `verified`, `needs_correction`, and `rejected` decisions.

Acceptance:

- one review file is generated per paper;
- every equation row links to or embeds its evidence image;
- unverified equations remain `equation_verified: false`;
- verified equations can be marked without changing unrelated paper products;
- no permanent paper note treats unverified equations as confirmed.

## Cycle 9: Deep Analysis

Tasks:

- consume extracted paper products;
- use local LLM by default;
- validate deep-analysis JSON;
- require explicit fallback permission before raw PDF/full-page context is used.

Acceptance:

- analysis uses product files by default;
- raw PDF fallback is rejected unless explicitly enabled;
- output is written to `papers/{citekey}/deep_analysis.json`.

## Cycle 10: Orchestrator

Tasks:

- sequence independent commands;
- support nightly scheduling policy;
- enforce max runtime and max item budgets;
- stop before starting new work when either budget is reached;
- finish the currently running item/task before stopping;
- support a wall-clock deadline such as `06:00`;
- defer task-specific timeout defaults to each independent project;
- persist progress and resume next run.

Acceptance:

- no domain logic lives in the orchestrator;
- individual command tests remain valid without orchestrator;
- deadline behavior finishes current task and does not start the next one;
- task-specific timeout behavior is configured by the invoked module, not hardcoded in the orchestrator;
- default triage run does not write Zotero or permanent Obsidian notes.

## Validation Before Commit Or Push

For documentation-only changes:

```bash
uv run ruff check
uv run pytest -q -o addopts=
```

For future security/tooling changes:

```bash
uv run pre-commit run --all-files
python3 tools/run_gitleaks.py
uv run bandit -r paper_pipeline
```

For dependency/CI changes, run `uvx pip-audit` when network is available.
