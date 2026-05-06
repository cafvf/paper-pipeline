# Human Review Workflow

The system recommends; the user decides; write modules apply only approved decisions.

```text
scan -> match -> classify -> export review -> human edits -> apply approved decisions
```

## Current Pattern

The current pipeline already renders one decision note per paper. Human-editable YAML is parsed by `paper_pipeline/decision_notes.py` and applied by `paper_pipeline/decision_applier.py`.

The future project-paper workflow should reuse the same principle but change the review surface to a grouped project report.

## Future Review Report

Example:

```markdown
# Initial Paper Triage - 2026-05-06

## Project: CPTu Bayesian Soil Classification

### Essential

- [ ] Robertson 1990 - Soil classification using CPT
  - Citekey: `robertson1990soilclassification`
  - Utility: `essential`
  - Action: `read_now`
  - Reason: Defines the deterministic reference framework.
  - Confidence: `high`
  - Decision: `pending`

### Methodological

- [ ] Paper X
  - Citekey: `paperx2024`
  - Utility: `methodological`
  - Action: `extract_equations`
  - Reason: Presents a reproducible algorithm.
  - Confidence: `medium`
  - Decision: `pending`
```

The user may edit:

```text
Decision: approved
```

or:

```text
Decision: rejected
Human reason: too general for the current project
```

## Decision Meanings

- `pending`: no action.
- `approved`: this project-paper relation is accepted.
- `rejected`: the recommendation is not accepted.
- `deferred`: postpone the decision.
- `manual_only`: the user handled it outside the pipeline.

## Apply Phase

The apply phase should parse only approved rows and produce an auditable plan:

- Zotero tags to add;
- Obsidian notes to create or update;
- registry rows to mark reviewed;
- errors or skipped items.

For MVP 0.1 there is no apply phase. The output is only a review report.

## Safety Rules

- A classification alone never authorizes Zotero writes.
- A checked Markdown item alone should not be enough if the decision text remains `pending`.
- Rejected decisions should not remove existing Zotero tags.
- The apply command should have a dry-run mode.
- Review reports should not contain secrets, raw API payloads, or unnecessary private note text.

