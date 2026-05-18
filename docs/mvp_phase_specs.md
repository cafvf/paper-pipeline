# MVP Phase Specifications

This document turns the current migration plan into executable phase specs.

It complements, but does not replace:

- `docs/architecture.md` — current-vs-target architecture and boundaries
- `docs/workflow_spec.md` — canonical target command/artifact contract
- `docs/development_plan.md` — implementation order and delivery priorities
- `docs/human_review_workflow.md` — review/export semantics and decision meanings

Use this file when the question is: **what exactly must one migration phase do, own, produce, and prove before the next phase starts?**

## Phase-by-Phase Flow Map

```text
PHASE 0 — Boundary freeze
  defines:
    - legacy vs target ownership
    - thin orchestrator rule
    - explicit artifact rule
    - canonical command roster
  enables:
    -> Phase 1 classify
    -> Phase 2 export-review
    -> Phase 3 registry write-through
    -> Phase 4 triage orchestrator
```

```text
PHASE 1 — classify
  input:
    data/candidates.jsonl
  output:
    data/classifications.jsonl
  depends on:
    scan-obsidian -> scan-zotero -> match
  enables:
    -> Phase 2 export-review
    -> later registry completion recording
```

```text
PHASE 2 — export-review
  input:
    data/classifications.jsonl
  output:
    data/review-project-papers-YYYY-MM-DD.md
  depends on:
    Phase 1 classify
  enables:
    -> complete read-only human review chain
```

```text
PHASE 3 — registry write-through
  input:
    successful outputs from match / classify / export-review
  output:
    registry rows + trusted hash/completion state
  depends on:
    stable contracts from Phases 1–2
  enables:
    -> trustworthy skip/reprocess logic
    -> safer orchestration later
```

```text
PHASE 4 — thin triage orchestrator
  sequence only:
    scan-obsidian
      -> scan-zotero
      -> match
      -> classify
      -> export-review
  depends on:
    Phases 0–3
  output:
    end-to-end read-only run
  rule:
    no domain logic inside orchestrator
```

```text
PHASE 5 — controlled cutover
  shifts repo posture:
    new project-paper path becomes preferred
    legacy runner remains isolated
  depends on:
    Phase 4
```

```text
PHASE 6 — post-MVP expansion
  later modules:
    apply planning
    pdf products
    reference mining
    note generation
    deep analysis
    planners/auditors
  depends on:
    stable read-only MVP from Phases 0–5
```

## Cross-Phase Invariants

The following rules apply to every MVP phase:

1. `runner.py` remains legacy paper-stage orchestration unless explicitly redefined later.
2. The project-paper target path is command-oriented and artifact-oriented.
3. The orchestrator owns sequencing only; domain behavior remains in the phase owner.
4. File artifacts are the canonical interchange; registry is local cache/history.
5. A phase is not promotable without an independently runnable surface, explicit outputs, and targeted tests.

---

# Phase 0 — Boundary Freeze

## Purpose

Freeze the architectural boundaries for the migration before new behavior lands, so the repository stops mixing the legacy paper-stage path with the target project-paper path.

## Goal

Define and document the target architecture clearly enough that subsequent implementation work can proceed without ownership confusion.

Phase 0 must establish that:

- `paper_pipeline/runner.py` remains legacy paper-stage orchestration
- the target project-paper workflow is composed of independent applications/commands
- the future orchestrator is thin and owns sequencing only
- explicit file artifacts are the canonical handoff between phases
- registry state is supporting cache/history, not the primary interchange contract

## Position In The Flow

Phase 0 is a control phase, not a runtime processing phase.

It gates every later migration phase:

```text
Phase 0 boundary freeze
  -> Phase 1 classify
  -> Phase 2 export-review
  -> Phase 3 registry write-through
  -> Phase 4 thin triage orchestrator
  -> Phase 5 controlled cutover
  -> Phase 6 post-MVP expansion
```

## Ownership Boundary

### Phase 0 owns
- documenting the legacy-vs-target split
- documenting the thin-orchestrator rule
- documenting the explicit-artifact rule
- documenting the canonical command roster for the target path
- documenting what later phases may and may not own

### Phase 0 does **not** own
- implementing `classify`
- implementing `export-review`
- implementing registry write-through behavior
- implementing orchestration/sequencing behavior
- changing Zotero or Obsidian write rules

## Documentation Contract

Phase 0 documentation must make the following repository-level rules explicit.

### Legacy owner set
The legacy paper-stage path includes:
- `paper-pipeline run`
- `paper-pipeline pilot-run`
- `paper_pipeline/runner.py`

### Target owner set
The target project-paper path includes:
- `scan-obsidian`
- `scan-zotero`
- `match`
- future `classify`
- future `export-review`
- future `triage`

### Orchestrator rule
The orchestrator may:
- call independent commands
- sequence the target chain
- coordinate artifact locations and phase completion

The orchestrator must **not** own:
- matching logic
- classification logic
- Zotero mutation rules
- Obsidian note-generation rules
- PDF extraction or analysis rules

### Artifact rule
The canonical handoff between migration phases is explicit file artifacts such as:
- `data/projects.jsonl`
- `data/papers.jsonl`
- `data/candidates.jsonl`
- `data/classifications.jsonl`
- `data/review-project-papers-YYYY-MM-DD.md`

Registry state may mirror or cache phase completion, but it does not replace artifact contracts during MVP migration.

## Behavioral Rules

### 1. Documentation coherence rule
Repository documents that describe architecture, execution order, or module ownership must tell one consistent story about the migration target.

### 2. Legacy containment rule
New project-paper MVP behavior must not be routed through legacy `run` / `pilot-run` by convenience.

### 3. Independent-app rule
Each new target phase must be implementable as an independently runnable application with explicit inputs and outputs.

### 4. Sequencing-only orchestrator rule
No later triage/orchestration phase may absorb domain logic that belongs to an independent application.

### 5. Coexist-until-proven rule
The legacy path and target path may coexist until the new path is proven phase-by-phase with runnable surfaces and tests.

## Non-goals For Phase 0

Phase 0 does **not** need to solve:
- command implementation for `classify`
- command implementation for `export-review`
- exact registry write-through mechanics
- exact triage CLI behavior
- cutover timing
- post-MVP feature design

## Acceptance Criteria

Phase 0 is complete when all are true:

1. repository docs clearly distinguish the legacy paper-stage flow from the target project-paper flow
2. docs state `runner.py` is legacy paper-stage orchestration
3. docs state the target path is composed of independent commands
4. docs state the orchestrator is sequencing-only
5. docs state file artifacts are canonical and registry is supporting cache/history
6. docs state later phases should replace ownership phase-by-phase only after runnable proof
7. contributors can tell what belongs to Phases 1, 2, and 4 without architectural ambiguity

## Required Checks

Phase 0 is documentation-only, so proof comes from coherence and validation:
- docs cross-reference the same target path and boundaries
- repository documentation map points readers to the phase spec document
- formatting/lint checks remain green
- existing automated tests remain green after documentation updates

## Failure Modes To Guard Against

1. **Legacy/target blending**
   - contributors extend `runner.py` to host new project-paper behavior

2. **Orchestrator logic creep**
   - the future `triage` command starts absorbing matching/classification/review semantics

3. **Registry-as-contract drift**
   - later work treats registry rows as the primary contract before artifact interfaces are stable

4. **Phase confusion**
   - contributors implement Phase 4 orchestration before Phases 1 and 2 exist as independent commands

## Promotion Proof

Phase 0 is promotable only when:
- the repository documentation tells one consistent migration story
- the owner/boundary rules are explicit enough to guide implementation
- later implementation can proceed without reopening basic ownership questions

## Definition Of Done

Phase 0 is done when the repository has:
- a documented phase map
- an explicit legacy-vs-target boundary
- a documented thin-orchestrator rule
- a documented explicit-artifact rule
- clear prerequisites for implementing Phases 1 and 2

# Phase 1 — `classify` as an Independent Application

## Purpose

Turn project-paper classification from a parser/schema foundation into a real standalone command.

## Goal

Create a runnable `classify` command that:

- reads candidate rows from `data/candidates.jsonl`
- classifies each `project_id + citekey` pair
- validates one JSON object per classification
- writes `data/classifications.jsonl`
- performs no Zotero writes
- performs no permanent Obsidian writes
- stays independent from the future orchestrator

## Position In The Flow

```text
scan-obsidian
  -> data/projects.jsonl

scan-zotero
  -> data/papers.jsonl
  -> papers/{citekey}/metadata_snapshot.json

match
  -> data/candidates.jsonl

classify
  -> data/classifications.jsonl
```

### Upstream dependency
- `match`

### Downstream consumer
- `export-review`

## Ownership Boundary

### `classify` owns
- loading candidate inputs
- resolving the minimum required project/paper context
- building the classification prompt/input payload
- calling the local LLM
- enforcing “single JSON object” output
- schema validation
- writing canonical classification artifacts
- reporting classification failures clearly

### `classify` does **not** own
- candidate generation logic
- human review rendering
- Zotero mutation rules
- Obsidian note-generation rules
- orchestration/scheduling policy
- PDF extraction/deep analysis rules

## Command Contract

### Command name
```bash
uv run paper-pipeline classify
```

### Minimum input contract
- `data/candidates.jsonl`
- enough project metadata to identify project context
- enough paper metadata to identify paper context

### Preferred explicit inputs
- `--candidates` default `data/candidates.jsonl`
- `--projects` default `data/projects.jsonl`
- `--papers` default `data/papers.jsonl`
- `--output` default `data/classifications.jsonl`

### Optional execution controls
- `--max-candidates` safety cap for the current LLM run
- `--paper-stages` to restrict the current run to candidate papers already in selected Zotero stages
- model/prompt options
- fake/fixture mode for tests
- registry db path for future write-through, but not required for the first correct implementation

## Inputs

### Required artifact
`data/candidates.jsonl`

Each row must already represent a validated project-paper candidate.

### Required supporting data
`projects.jsonl` and `papers.jsonl` must provide enough context to classify:
- project title/objectives/methods/gaps/outputs/priority
- paper title/abstract/year/authors/tags/collections/doi
- candidate evidence

### First-phase LLM input layer
**metadata only**

No raw PDF input.  
No deep extracted products.  
No fallback to broader paper analysis unless explicitly designed later.

## Output Contract

### Canonical output file
`data/classifications.jsonl`

### Auxiliary progress artifacts
- `data/classifications.progress.json`
- `data/classifications/*.json`

### Each row must be a validated `LLMClassification`
At minimum it must include:
- `project_id`
- `citekey`
- `utility_class`
- `recommended_action`
- `confidence`
- `recommended_zotero_stage`
- `input_layer`

Plus artifact metadata needed for auditability.

### Required behavior
- one JSON object per line
- deterministic key ordering in persisted JSON
- atomic file write for full-run output
- one validated per-candidate JSON artifact written atomically after each successful classification
- progress manifest updated after each successful classification and on terminal failure/completion
- no partial corrupt artifact on invalid result

## Behavioral Rules

### 1. Candidate loading
- load all candidate rows from JSONL
- reject malformed JSONL early
- reject non-object rows
- reject schema-invalid candidates

### 2. Context assembly
For each candidate:
- find matching project row by `project_id`
- find matching paper row by `citekey`
- build bounded classification input from:
  - project profile
  - paper profile
  - candidate evidence

If referenced project or paper is missing:
- fail clearly
- do not silently classify incomplete context

### 3. Prompt boundary
Prompt must ask:
- how useful this paper is for this project

Prompt must **not** drift into:
- full reading-stage assessment
- deep paper interpretation
- PDF reasoning
- note drafting
- curation/apply decisions beyond allowed classification fields

### 4. LLM output boundary
The LLM response must be:
- exactly one JSON object
- no prose before or after
- schema-valid

If not:
- reject the output
- return failure for that command run or structured failure behavior, depending on final design

### 5. Validation
Every classification row must pass:
- single-object parse validation
- schema validation against `llm_classification.schema.json`
- semantic coherence validation between:
  - `utility_class`
  - `recommended_action`
  - `recommended_zotero_stage`
  - `current_zotero_stage`

At minimum, Phase 1 must reject contradictions such as:
- useful/approved-looking classifications paired with `Expendable`
- `read_now` paired with `Expendable`
- `extract_equations` or `reproduce_code` outside `.ToDig`
- metadata-only demotion of papers already in `.To Revise` or `.ToDig`
- `irrelevant_now` paired with non-ignore actions

### 6. Persistence
- write only validated rows
- output write should be atomic
- write one validated per-candidate file for each completed candidate
- keep progress visible through a manifest and the per-candidate artifact count
- invalid output must not leave a half-written artifact

## Error-Handling Rules

### Hard failures
The command must fail with non-zero exit when:
- candidates file is missing
- candidates JSONL is malformed
- project/paper lookup data is missing
- LLM output is invalid JSON
- LLM output contains prose around JSON
- LLM output contains multiple JSON objects
- schema validation fails
- output file cannot be written

### Required error quality
Errors should:
- be concise
- avoid traceback noise for expected contract failures
- tell the operator which artifact or row type failed

## Non-goals For Phase 1

Phase 1 does **not** need to solve:
- grouped Markdown review export
- registry write-through completion semantics
- skip/reprocess optimization
- orchestrator sequencing
- PDF-backed reclassification
- approval-gated write actions

## Acceptance Criteria

Phase 1 is complete when all are true:

1. `paper-pipeline classify` exists as a standalone command
2. it reads candidate fixture input successfully
3. it writes `data/classifications.jsonl`
4. every output row validates against `llm_classification.schema.json`
5. invalid enum values fail tests
6. prose-wrapped JSON fails tests
7. multi-object output fails tests
8. no Zotero writes occur
9. no permanent Obsidian writes occur
10. incoherent stage/action/utility combinations fail validation and do not persist
11. the command is usable independently of the future orchestrator

## Required Tests

### Unit tests
- parse single valid JSON object
- reject prose before JSON
- reject trailing prose
- reject multiple JSON objects
- reject invalid `utility_class`
- reject invalid `recommended_action`
- reject invalid `confidence`
- reject invalid `input_layer`
- reject useful/approved-looking classifications paired with `Expendable`
- reject `irrelevant_now` paired with active reading actions
- reject `extract_equations` or `reproduce_code` outside `.ToDig`
- reject metadata-only demotion from `.To Revise` or `.ToDig`

### Integration tests
- load fixture candidates/projects/papers
- emit deterministic `classifications.jsonl`
- fake/recorded LLM path works
- missing referenced project fails clearly
- missing referenced paper fails clearly
- persist one candidate artifact per successful completed candidate
- mark progress failed without writing partial final JSONL when a later candidate fails
- invalid LLM response does not persist partial output
- atomic output behavior

### CLI tests
- `classify` command is registered
- default paths work
- explicit path overrides work
- non-zero exit on invalid input/output contract failures

## Failure Modes To Guard Against

1. **Prompt drift**
   - classifier starts acting like deep paper analyzer

2. **Hidden orchestration**
   - command begins assuming future `triage` behavior

3. **Silent context loss**
   - missing project/paper rows produce degraded classification instead of failure

4. **Artifact corruption**
   - invalid output leaves partial JSONL

5. **Semantic contradiction**
   - utility/action/stage recommendation combinations contradict the reading policy

6. **Schema bypass**
   - raw model output gets written without validation

## Promotion Proof

Phase 1 is promotable only when:
- the command runs independently
- targeted tests pass
- the output artifact is explicit and stable
- downstream `export-review` can consume `data/classifications.jsonl`
- no domain logic leaked into orchestration

## Definition Of Done

Phase 1 is done when the repository has:
- a runnable `classify` command
- validated classification JSONL output
- targeted tests
- no dependency on legacy `runner.py`
- no dependency on future `triage`

---

# Phase 2 — `export-review` as an Independent Application

## Purpose

Convert validated project-paper classifications into a grouped, human-editable Markdown review artifact that completes the read-only MVP chain.

## Goal

Create a runnable `export-review` command that:

- reads validated classification rows from `data/classifications.jsonl`
- groups all classifications for the same paper into one paper-level review item
- preserves each project-paper decision inside that paper item
- writes one Markdown review file for the round
- uses editable decision blocks that can later be parsed safely
- performs no Zotero writes
- performs no permanent Obsidian note writes
- stays independent from the future orchestrator

## Position In The Flow

```text
scan-obsidian
  -> data/projects.jsonl

scan-zotero
  -> data/papers.jsonl

match
  -> data/candidates.jsonl

classify
  -> data/classifications.jsonl

export-review
  -> data/review-project-papers-YYYY-MM-DD.md
```

### Upstream dependency
- `classify`

### Downstream consumers
- human review in Obsidian or local review artifact inspection
- later review parsing / approval-gated apply phases

## Ownership Boundary

### `export-review` owns
- loading validated classification rows
- grouping rows by paper/citekey
- deciding display grouping and ordering for readability
- rendering the review Markdown structure
- rendering one parseable decision block per paper-level review item
- documenting allowed review values in Markdown near the review content
- writing the canonical review artifact

### `export-review` does **not** own
- candidate generation
- utility classification logic
- Zotero mutation rules
- Obsidian note-generation rules
- review parsing/apply execution
- orchestration/scheduling policy

## Command Contract

### Command name
```bash
uv run paper-pipeline export-review
```

### Minimum input contract
- `data/classifications.jsonl`

### Preferred explicit inputs
- `--classifications` default `data/classifications.jsonl`
- `--output` default `data/review-project-papers-YYYY-MM-DD.md`
- optional `--date` or `--review-id` override for deterministic tests / stable filenames
- optional configured inbox/output path support consistent with `docs/workflow_spec.md`

### Output naming policy
For the first independent implementation, the canonical local output defaults to `data/review-project-papers-YYYY-MM-DD.md`.

When the configured inbox/output policy is enabled, filenames should follow the workflow contract:
- `review-project-papers-YYYY-MM-DD.md`

## Inputs

### Required artifact
`data/classifications.jsonl`

Each row must already be a validated project-paper classification.

### Supporting context
The exporter may also require paper metadata already present in the classification rows or available from upstream artifacts if needed for display. The exporter should not recompute utility or candidate logic.

## Output Contract

### Canonical output file
`data/review-project-papers-YYYY-MM-DD.md` for the standalone local default.

### Output semantics
The output must be:
- one Markdown review file per round
- grouped by paper/citekey, not one file per paper
- readable by a human
- stable enough for deterministic tests
- parseable enough for later review-ingestion work

### Required structure
At minimum each paper-level review item must preserve:
- citekey
- paper title or stable identifier
- strongest visible utility grouping for readability
- all project-level matches for that paper
- one editable decision block for the paper item

### Decision-block minimum fields
Each YAML decision block must include at least:
- `review_id`
- `review_item_id`
- `citekey`
- one paper-level completion status / decision field
- one Zotero-stage decision field
- project-level decisions for each included `project_id`

Allowed values should be shown in Markdown near the review section, not repeated redundantly inside every YAML block.

## Behavioral Rules

### 1. Classification loading
- load all classification rows from JSONL
- reject malformed JSONL early
- reject non-object rows
- reject rows that do not satisfy expected classification shape

### 2. Grouping rule
For every citekey:
- gather all classification rows with that citekey
- render **one** paper-level review item
- keep all project-paper matches visible inside that item

There is no primary project. A paper relevant to multiple projects must remain one paper item containing multiple project-level entries.

### 3. Readability grouping rule
Review output should group papers by their strongest useful class, following the human review workflow and workflow spec:

1. papers with at least one `essential`, `methodological`, `formulational`, or `implementable` match
2. papers with only `case_study`, `review`, `counterpoint`, or `peripheral` matches
3. papers with no useful project match

This grouping is for readability only. It must not collapse project-level decisions into one project winner.

### 4. Ordering rule
Within each readability group:
- sort by strongest project-paper score first
- then by citekey/title for stability

The exact stable tie-break rules must be deterministic and testable.

### 5. Decision-block rule
Every paper-level review item must include one editable YAML decision block.

The block must:
- start in a safe pending/incomplete state
- preserve per-project decision placeholders
- preserve paper-level and stage-level decision placeholders
- avoid embedding executable or hidden logic in Markdown prose

### 6. Safety defaults
Rendered decision blocks must default to safe non-apply posture, including:
- no automatic Zotero apply
- no automatic permanent Obsidian note generation

### 7. Rendering boundary
`export-review` may summarize or present classification information, but it must not:
- re-score utility
- rewrite classification semantics
- infer final approved decisions
- invoke apply logic

### 8. Persistence
- write exactly one canonical review artifact for the round
- write atomically
- do not leave a truncated Markdown file on failure

## Error-Handling Rules

### Hard failures
The command must fail with non-zero exit when:
- classifications file is missing
- classifications JSONL is malformed
- classification rows are unusable for grouping
- required identifiers such as citekey are missing
- output file cannot be written

### Required error quality
Errors should:
- be concise
- avoid traceback noise for expected contract failures
- identify whether loading, grouping, rendering, or writing failed

## Non-goals For Phase 2

Phase 2 does **not** need to solve:
- review parsing back into machine state
- Zotero apply planning
- Obsidian note generation
- registry write-through semantics
- orchestration/sequencing
- PDF/deep-analysis review surfaces

## Acceptance Criteria

Phase 2 is complete when all are true:

1. `paper-pipeline export-review` exists as a standalone command
2. it reads fixture `classifications.jsonl`
3. it emits one Markdown review artifact for the round
4. all classifications for the same citekey are grouped into one paper-level review item
5. every paper item preserves all project-level matches
6. the output ordering is deterministic
7. the decision blocks are parseable and contain `review_id`, `review_item_id`, and project-level decision state
8. allowed values are documented in Markdown near the review content
9. no Zotero writes occur
10. no permanent Obsidian note writes occur

## Required Tests

### Unit tests
- grouping by citekey
- strongest-utility readability grouping selection
- stable ordering / tie-break behavior
- Markdown escaping/formatting behavior
- YAML decision block rendering

### Integration tests
- load fixture classifications and emit deterministic Markdown
- preserve multi-project matches inside one paper-level item
- verify one review block per paper item
- verify allowed values documentation appears in the rendered output
- atomic output behavior on rendering failure

### Round-trip / parser-oriented tests
Even if full parsing is implemented later, Phase 2 should already prove that exported blocks are structured enough for round-trip ingestion by:
- asserting required keys exist in each YAML block
- asserting one paper-level block corresponds to one citekey item
- asserting project-level decisions remain nested and uncollapsed

### CLI tests
- `export-review` command is registered
- default path works
- explicit output override works
- non-zero exit on malformed input or missing identifiers

## Failure Modes To Guard Against

1. **Legacy one-paper note regression**
   - exporter reuses the old one-paper-per-note pattern and loses grouped review semantics

2. **Primary-project collapse**
   - exporter picks one project as “the” project and hides the others

3. **Unstable ordering**
   - output changes order nondeterministically between runs

4. **Unreadable or unparsable review blocks**
   - human review becomes brittle and later apply phases cannot ingest decisions safely

5. **Hidden business logic drift**
   - exporter starts making approval decisions instead of rendering them

## Promotion Proof

Phase 2 is promotable only when:
- the command runs independently
- targeted tests pass
- one review artifact is emitted deterministically from fixture classifications
- all project-level matches remain visible per paper
- the output is ready for later parser/apply work without structural redesign

## Definition Of Done

Phase 2 is done when the repository has:
- a runnable `export-review` command
- deterministic grouped Markdown output
- paper-level review items with preserved project-level decisions
- parseable decision blocks with required identifiers
- no dependency on legacy `runner.py`
- no dependency on future `triage`
