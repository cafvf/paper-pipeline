# Development Plan

This plan is the next-session implementation handoff. It has been revised after code review so the team addresses the real blockers first, not the longer-horizon modules.

The repository already has a useful safe base for the project-paper workflow, and the read-only chain now exists as independent commands:

`scan-obsidian -> scan-zotero -> match -> classify -> export-review`

The immediate goal is no longer to finish that chain. The immediate goal is to harden it and then wrap it in the planned thin nightly orchestrator. No new PDF/deep-analysis/note-generation work should start before the orchestrator boundary, registry write-through, and per-layer evaluation rules are explicit and tested.

## Current Status Snapshot

Validated on the current branch:

- `uv run ruff check` passes;
- `uv run pytest -q -o addopts=` passes (`291 passed` during the latest verification loop);
- the independent project-paper chain exists for:
  - project profiles (`scan-obsidian`);
  - paper profiles (`scan-zotero`);
  - lexical project-paper matching (`match`);
  - metadata-only classification with semantic coherence checks (`classify`);
  - grouped paper-level review export (`export-review`).

Known gaps from review:

1. the legacy `runner.py` still owns paper-stage orchestration and should not be reused as the new project-paper orchestrator;
2. registry skip logic exists, but candidate/classification/review/hash write-through is not yet wired into the runtime flow;
3. the new thin `triage` orchestrator does not exist yet;
4. the repository still lacks per-layer evaluation tracking, so nightly runs cannot yet skip papers already evaluated in their current Zotero layer;
5. legacy approval paths can still lead to direct Zotero writes without the future `plan_hash`-verified apply contract;
6. local security audit currently fails if `.env` with real secrets remains under the repo root.

## Engineering Guardrails

All cycles in this plan follow Test-Driven Development, Extreme Programming,
Clean Code, and Spec-Driven Development together.

- start from the governing spec, contract, schema, or roadmap item;
- add or update automated tests before treating behavior work as complete;
- implement the smallest change that satisfies the test and refactor with tests green;
- keep the project-paper path read-only by default until the explicit apply-planning cycles;
- do not route new project-paper work through legacy paper-stage orchestration by convenience.

See `docs/development_guidelines.md` for the repository-wide rule set.

## Phase 0: Resume Rules For The Next Session

Before changing behavior in the next session:

1. treat `paper_pipeline/runner.py` and current decision-note apply flow as **legacy paper-stage behavior**;
2. do not extend legacy `run` / `pilot-run` to simulate the new project-paper MVP;
3. keep all new project-paper work behind independent commands and artifacts;
4. keep Zotero and permanent Obsidian writes out of the new default triage flow;
5. if a task depends on the nightly orchestrator, keep the orchestrator sequencing-only and push domain logic back down into independent commands.

## Implemented Or Mostly Implemented Foundations

These items are no longer the first execution priority, but they remain part of the MVP base and must stay green while the next cycles land.

### Foundation A: Contracts And Fixtures

Status: implemented enough to use as the base.

Keep validated:

- `schemas/project_profile.schema.json`;
- `schemas/paper_profile.schema.json`;
- `schemas/project_paper_match.schema.json`;
- `schemas/llm_classification.schema.json`;
- `configs/utility_taxonomy.yaml`;
- `configs/zotero_tags.yaml`.

### Foundation B: Obsidian Project Inventory

Status: implemented enough for current planning.

Keep validated:

- read-only scanner;
- state mapping from `Efforts/On`, `Efforts/Ongoing`, `Efforts/Simmering`, and `Efforts/Terminated`;
- extracted fields only, no duplicated full note bodies.

### Foundation C: Zotero Metadata Inventory

Status: implemented enough for current planning.

Keep validated:

- neutral `PaperProfile` export;
- `papers.jsonl` output;
- `papers/{citekey}/metadata_snapshot.json` output;
- read-only inventory behavior.

### Foundation D: Registry Skeleton

Status: partially implemented.

What exists:

- SQLite schema for projects, papers, candidates, classifications, reviews, runs, and hashes;
- idempotent sync for projects and papers;
- pair-skip decision logic.

Main remaining gap:

- runtime write-through for candidates, classifications, reviews, and processed hashes.

### Foundation E: Matching MVP

Status: implemented as lexical safe base.

What exists:

- project text builder;
- paper text builder;
- lexical scoring;
- evidence strings;
- top-N matching.

Main remaining gap:

- no evaluation harness yet for quality at realistic corpus size.

## Phase 1: Problems To Address First

These cycles replace the previous generic ordering. Complete them in order unless a later review proves the sequence wrong.

Detailed executable specs for Cycle 1 and Cycles 2–3 now live in `docs/mvp_phase_specs.md`. Use this plan for ordering and scope; use the phase-spec document for command contracts, boundaries, failure modes, and promotion proof.

## Cycle 1: Freeze The Boundary Between Legacy And New Flow

Status:

Implemented on the current branch as the repository baseline. Preserve these boundaries while landing later cycles.

Purpose:

Make the project-paper path explicit and prevent accidental reuse of legacy paper-stage orchestration.

Tasks:

- document in code and docs that `runner.py` is legacy paper-stage orchestration;
- document that the new project-paper MVP path is command-sequenced and read-only by default;
- prevent next-session work from extending legacy `run` / `pilot-run` as the new MVP entrypoint;
- define the new orchestration target as a thin triage sequencer only after the independent commands are ready.

Acceptance:

- docs clearly distinguish legacy paper-stage flow from new project-paper flow;
- no new feature work for project-paper MVP is added to `runner.py` unless the task is explicitly legacy maintenance;
- the next cycles can proceed without architectural ambiguity about which path owns new behavior.

Risks:

- contributors extend the old path because it already exists.

Mitigation:

- require all new MVP work to land behind independent commands and explicit artifacts.

## Cycle 2: Utility Classification Execution MVP

Status:

Implemented on the current branch as a metadata-only standalone command. Preserve its independence from `runner.py` and use Cycle 3 as the next execution priority.

Purpose:

Convert the current classification schema/parser work into a real command that classifies project-paper candidates.

Tasks:

- add a project-paper `classify` command;
- load candidates from `data/candidates.jsonl`;
- call the local LLM using metadata-only inputs by default;
- validate one JSON object per classification;
- write `data/classifications.jsonl`;
- record prompt/model/input-layer metadata in the artifact payload;
- add fake or recorded-LLM tests for happy path and schema rejection;
- keep classification independent from review export and independent from legacy runner behavior.

Acceptance:

- `classify` runs from fixture inputs without Zotero or Obsidian writes;
- all output rows validate against `llm_classification.schema.json`;
- invalid confidence/action/utility/input-layer values fail tests;
- the command writes deterministic JSONL from deterministic fake/recorded inputs;
- tests prove the command rejects prose-wrapped or multi-object LLM output.

Risks:

- LLM prompt scope drifts toward reading-stage analysis instead of project utility.

Mitigation:

- keep prompt inputs bounded to the project-paper contract and record `input_layer` explicitly.

## Cycle 3: Grouped Review Export MVP

Status:

Implemented on the current branch as the current review surface. Preserve its grouped citekey-level contract while the orchestrator phase lands.

Purpose:

Close the human-review gap so the read-only MVP can reach its required output.

Tasks:

- implement `export-review` for grouped project-paper review;
- aggregate all classifications for the same citekey into one paper-level review item;
- preserve every project-paper match inside that paper item;
- render editable YAML decision blocks that follow the current contracts;
- document allowed values in Markdown, not repeated `allowed_*` YAML keys;
- use stable review filenames and inbox policy from `docs/workflow_spec.md` and `docs/human_review_workflow.md`;
- add parser/round-trip tests or update existing decision-parsing tests to cover grouped review blocks.

Acceptance:

- one Markdown review file is produced for a round;
- grouped output is stable and readable;
- every paper item preserves all project-level matches;
- exported review blocks are parseable and retain `review_id`, `review_item_id`, and project-level decision state;
- `export-review` performs no Zotero writes and no permanent Obsidian note writes.

Risks:

- accidentally reusing one-paper legacy decision-note structure.

Mitigation:

- enforce grouped citekey-level review fixtures from the start.

## Cycle 4: Registry Write-Through And Hash Closure

Purpose:

Make the registry useful in production, not only in tests.

Tasks:

- decide whether the registry is authoritative during MVP or advisory only;
- if authoritative, add runtime writes for:
  - matched candidates;
  - classifications;
  - processed project/paper/prompt hashes;
  - optional run records;
- ensure unchanged-pair skip logic only runs when the matching/classification completion state is actually recorded;
- add tests that prove a completed unchanged pair is skipped on re-run and a changed hash forces reprocessing;
- avoid partial state if a command fails after writing some but not all outputs.

Acceptance:

- `match` and/or `classify` either update registry state atomically or remain explicitly file-only without misleading skip behavior;
- processed hashes are recorded in production flow, not only in tests;
- unchanged pairs are skipped only when prior completion is real and reproducible;
- failure cases do not leave ambiguous partially processed registry state.

Risks:

- skip logic becomes incorrect if writes are not atomic.

Mitigation:

- prefer one explicit post-success write boundary per command.

## Cycle 5: Thin Nightly Orchestrator

Purpose:

Create the new thin orchestrator now that `classify` and `export-review` exist as independent commands.

Tasks:

- add a new project-paper triage command name such as `triage` or `run-triage`;
- sequence only the independent commands:
  - `scan-obsidian`;
  - `scan-zotero`;
  - `match`;
  - `classify`;
  - `export-review`;
- keep orchestration free of business logic;
- enforce one nightly global budget of at most 10 papers total;
- divide that budget across `.ToLook`, `.To Revise`, and `.ToDig` with configurable per-layer targets and rollover when one layer has fewer pending papers;
- skip papers already evaluated in their current layer;
- make the orchestrator responsible only for sequencing, budget control, deadline control, and per-layer selection policy;
- do not move legacy `run` behavior under this new command.

Acceptance:

- one command can execute the read-only project-paper MVP path end to end;
- the orchestrator enforces a global nightly paper budget instead of unconstrained batch size;
- the orchestrator can target `.ToLook`, `.To Revise`, and `.ToDig` separately without reimplementing matching/classification/review rules;
- papers already evaluated in their current layer are skipped by policy;
- the default triage run does not write Zotero or permanent Obsidian notes.

Risks:

- reintroducing monolithic orchestration;
- burying per-layer state rules inside the wrong module.

Mitigation:

- fail code review if domain logic starts moving into the new command;
- keep layer-completion tracking explicit in registry/run artifacts instead of implicit in the orchestrator.

## Phase 2: Safety Hardening Before Any Apply Work

Do not start real apply-path implementation until Phase 1 is complete.

## Cycle 6: Zotero Apply Planning Hardening

Purpose:

Replace legacy direct-apply assumptions with explicit, hash-verified plan/apply contracts.

Tasks:

- generate immutable dry-run plans with `plan_hash` plus source review, inventory, and config/policy hashes;
- require apply to receive the same plan path and expected hash;
- check whether the `Expendable` collection exists;
- include root-level collection creation in the dry-run plan if `Expendable` is missing;
- for approved Expendable movement, plan removal from stage/triage collections, movement to `Expendable`, addition of `!discarded`, and removal of mutually exclusive `@` stage tags;
- isolate or deprecate any legacy direct-apply path that bypasses the new plan verification rules.

Acceptance:

- apply refuses changed plan content;
- apply refuses direct mutation without a reviewed plan hash;
- dry-run shows collection creation before item movement when needed;
- Expendable movement removes stage/triage collection memberships in the plan while preserving topic/project/paper collections;
- no real Zotero write occurs in tests.

## Cycle 7: Obsidian Note Planning Hardening

Purpose:

Ensure future note generation follows the new inbox/product/stage safety rules rather than the legacy draft path.

Tasks:

- generate immutable dry-run note plans with `plan_hash`;
- require apply to receive the same plan path and expected hash;
- create note plans only for approved papers in `.To Revise` or `.ToDig` with available PDFs;
- require metadata plus layer 1/2/3 extracted products before note planning;
- use extracted products as the note source material;
- skip metadata-only items with a structured reason;
- isolate legacy knowledge-note behavior so it is not mistaken for the new project-paper note-generation path.

Acceptance:

- no note plan is generated for papers without PDFs, outside `.To Revise`/`.ToDig`, or without required extracted products;
- changed note plans are rejected by apply;
- duplicate citekey notes are detected;
- existing-note frontmatter and Obsidian wikilinks are preserved when patching;
- no real Obsidian write occurs in tests.

## Phase 3: Deeper Processing After The Safe Read-Only MVP

Only start these after the read-only project-paper chain and apply-planning boundaries are stable.

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
- report frequent missing references and citation counts;
- track which source papers cited each reference;
- preserve references without DOI as valid records;
- classify reference type when possible: article, book, standard, report, monograph, dissertation, thesis, or unknown;
- recommend missing references cited by at least 5 source papers for acquisition;
- write separate match-review rows for fuzzy or non-DOI cases that need manual inspection;
- render a human-oriented Markdown match-review report alongside JSONL;
- keep simple citation count separate from weighted capture recommendation score;
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

## Cycle 8C: Equation Review Export

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

## Cycle 10: Long-Horizon Orchestrator Hardening

This is later work, after the first nightly orchestrator exists.

Tasks:

- refine per-layer rollover and priority policy after real nightly runs;
- support max runtime and wall-clock deadlines such as `06:00`;
- finish the currently running item/task before stopping;
- persist progress and resume next run;
- support richer layer-specific analyzers once `.To Revise` and `.ToDig` products exist.

Acceptance:

- no domain logic lives in the orchestrator;
- individual command tests remain valid without orchestrator;
- deadline behavior finishes current task and does not start the next one;
- task-specific timeout behavior is configured by the invoked module, not hardcoded in the orchestrator;
- default triage run does not write Zotero or permanent Obsidian notes.

## Operational Note: Local Secret Scan

Current review evidence showed that `python3 tools/run_gitleaks.py` detects local secrets when a real `.env` is stored under the repository root.

Before treating the full local audit as green in a future session:

- keep `.env.example` placeholder-only;
- keep real `.env` values outside the repository when possible, or use a local workflow that does not place live secrets under the scanned root;
- do not relax tracked secret-scanning rules to make the audit pass.

This is an operational blocker for a clean local security audit, but it is not the first product-behavior implementation target.

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
