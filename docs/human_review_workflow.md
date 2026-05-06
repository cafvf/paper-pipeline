# Human Review Workflow

The system recommends; the user decides; write modules apply only approved decisions.

```text
scan -> match -> classify -> export review -> human edits -> apply approved decisions
```

## Current Pattern

The current pipeline already renders one decision note per paper. Human-editable YAML is parsed by `paper_pipeline/decision_notes.py` and applied by `paper_pipeline/decision_applier.py`.

The future project-paper workflow should reuse the same principle but change the review surface to a grouped project report.

## Future Review Report

There should be one Markdown review file per review round in both MVP and final design. The report may group items by paper, utility, or review priority, but each paper must be evaluated against all eligible projects before it is presented for human decision. If a paper does not fit any eligible project well, it may be marked for discard/expendable handling later.

There is no primary project. When a paper is relevant to multiple projects, the review should present one paper-level item containing all project-paper matches.

Recommended filenames:

- `review-project-papers-YYYY-MM-DD.md`;
- `review-reference-matches-YYYY-MM-DD.md`;
- `review-equations-{citekey}-YYYY-MM-DD.md`.

Generated review files do not require frontmatter.

Suggested grouping:

1. high-utility papers: any `essential`, `methodological`, `formulational`, or `implementable` match;
2. contextual papers: only `case_study`, `review`, `counterpoint`, or `peripheral` matches;
3. no-use papers: no useful match, possible `Expendable` candidates after all project decisions are complete.

This grouping is only for readability. The decision remains project by project inside each paper item.

Example:

```text
# Initial Paper Triage - 2026-05-06

## Paper: Robertson 1990 - Soil classification using CPT

### Essential
```

- [ ] Robertson 1990 - Soil classification using CPT
  - Citekey: `robertson1990soilclassification`
  - Review status: `pending`
  - Action: `read_now`
  - Recommended Zotero stage: `.To Revise`
  - Confidence: `high`
  - Project matches:
    - `cptu_bayesian_classification`: essential, read_now, score 0.91
      - Reason: defines the deterministic reference framework.
    - `jetted_conductors`: methodological, extract_equations, score 0.62
      - Reason: useful as a methodological comparison.
  - Decision: edit the YAML block below.

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
    human_reason: ""
  - project_id: jetted_conductors
    decision: pending
    approved_actions:
      - extract_equations
    human_reason: ""
```

### Methodological

- [ ] Paper X
  - Citekey: `paperx2024`
  - Utility: `methodological`
  - Action: `extract_equations`
  - Reason: Presents a reproducible algorithm.
  - Confidence: `medium`
  - Decision: edit the YAML block below.

Allowed values should be shown in Markdown near the review section, not repeated inside every YAML block.

Generated blocks start with `decision: pending`. `pending` means the review item is incomplete. The item becomes `decision: decided` only when all project-level decisions and any required Zotero-stage decision are complete.

## Decision Meanings

Paper-level review status:

- `pending`: at least one required decision is incomplete.
- `decided`: all required decisions for this paper item were made.

Project-level decision values:

- `pending`: not decided for this project yet.
- `approved`: useful for this project.
- `rejected`: not useful for this project.
- `deferred`: postpone this project-paper decision.

Zotero stage decision values:

- `pending`: not decided yet.
- `keep_current`: keep the current Zotero collection.
- `move_to_revise`: move from `.ToLook` to `.To Revise`.
- `move_to_dig`: move to `.ToDig`.
- `move_to_expendable`: move to `Expendable`.
- `manual_only`: handled outside automation.

Action values:

- `read_now`;
- `read_later`;
- `extract_equations`;
- `reproduce_code`;
- `summarize_only`;
- `link_to_project`;
- `ignore_for_now`.

Default safety values:

- `apply_zotero_tags: false`;
- `create_obsidian_note: false`.

The review remains open while any project decision is still `pending`. A paper should not be discarded if any project-level decision is `approved`.

Manual credibility values:

- `unknown`;
- `credible`;
- `not_credible`;
- `seminal_or_classic`.

This field covers manual evidence such as h-index > 15 in geomechanics, ISRM/SPE relevance, known author credibility, or trusted venue status.

`manual_credibility` is paper-level, not project-level.

## Zotero Reading Stages

Project utility and reading-stage evolution are related but not identical.

- `.ToLook`: initial screening.
- `.To Revise`: deeper study, layer 2/3 extraction, and methodological review.
- `.ToDig`: deep formulation, implementation, insights, and applications.
- `Expendable`: not useful for any eligible project after review.

If a paper is approved for one or more projects, it normally leaves `.ToLook` and moves to `.To Revise`. If project utility is high and reading-protocol gates support deeper work, it may move to `.ToDig`.

The user's reading protocol criteria in `docs/reading_protocol_criteria.md` can be used as secondary evidence for stage recommendations. It should not replace project-by-project utility decisions.

Initial ToDig recommendation rule:

- max project-paper adherence score is at least `0.80`; or
- ToDig protocol gate passes for the detected article type.

If all project decisions are `rejected`, the system may recommend `move_to_expendable`, but the final decision is human.

Stage tags and use tags:

- `@look`, `@review`, and `@dig` should remain coherent with the final stage decision;
- `$` tags capture concrete paper uses, such as background, gap signal, methods citation, discussion, extension, or manuscript-specific use;
- `$` tags should be suggested at paper level as the union of approved project-level uses.

## Reference Review Reports

Reference mining may produce a separate review report for references without DOI or with fuzzy Zotero matches. This report should not be mixed with project-paper utility review, because it answers a different question: whether the referenced work is already represented in Zotero.

The reference match review should have both machine-readable JSONL and a human-oriented Markdown report. The Markdown should use a decision table with an editable plain-text `decision` column, explanatory language, comparison evidence, citing source papers, and clear decision options without requiring the user to infer YAML values from memory.

Allowed reference match decisions:

- `same_work`: the candidate Zotero item represents the referenced work;
- `different_work`: the candidate Zotero item is not the same work;
- `acquire_new`: the reference should be captured manually as a new Zotero item;
- `ignore`: do not act on this reference now;
- `attach_or_find_pdf`: the item exists, but a PDF should be attached or found.

If the system recommends acquisition or PDF follow-up, the human-facing row should always show:

- `citation_count_in_corpus`;
- `capture_recommendation_score`;
- `capture_priority`;
- `recommended_followup_action`, when present;
- source papers that cited the reference.

References may be articles, books, standards, reports, monographs, dissertations, theses, or unknown document types. Missing DOI should not hide the reference from review. For non-DOI matching, the minimum comparison key is author + year + title.

Institutions may be used as authors for standards, reports, manuals, and institutional documents.

Acquisition recommendations are advisory. The human is responsible for adding the paper or document to Zotero, normally into `.ToLook`; until a later inventory confirms the item exists, it remains in the recommendation plan. Once confirmed in `.ToLook`, it should disappear from the acquisition recommendation report and proceed through the standard paper review flow.

## Equation Review

Equation verification should happen in a dedicated Obsidian Markdown file per paper. The review should show each extracted equation as block LaTeX, include the PDF crop/image evidence for visual comparison, and expose a human-editable verification field.

Equation review files should be written to the single Obsidian human-review inbox configured by `.env` or environment/configuration, for example `OBSIDIAN_HUMAN_REVIEW_INBOX_DIR`. The technical JSON stores only the LaTeX body; the Markdown renderer wraps it in `$$`.

Equation evidence images should be saved both under `papers/{citekey}/equations/` and copied next to the Obsidian equation-review Markdown file in the single inbox, without creating a per-paper subfolder, so Obsidian can render local relative image links reliably.

Use citekey-prefixed image filenames in the inbox, for example `{citekey}-eq-001.png`, to avoid collisions.

Suggested decisions for each equation:

- `pending`: not reviewed yet;
- `verified`: LaTeX matches the PDF and can be used;
- `needs_correction`: LaTeX is useful but requires editing;
- `rejected`: extraction is wrong or not useful.

## Apply Phase

The apply phase should parse only approved rows and produce an auditable plan:

- Zotero tags to add;
- Obsidian notes to create or update;
- registry rows to mark reviewed;
- errors or skipped items.

Every apply plan should include a `plan_hash` plus source review, inventory, and config/policy hashes. Real apply commands should verify the plan hash and refuse changed plan content.

For MVP 0.1 there is no apply phase. The output is only a review report.

## Review Identity

Every parsed decision must retain:

- `review_id`;
- `review_path`;
- `review_item_id`;
- `citekey`.

This keeps human decisions auditable and links each decision to the exact review round where it was made.

Project-level decisions inside the paper item must retain their `project_id` values. A paper should not be discarded if any project-level decision is approved.

## Safety Rules

- A classification alone never authorizes Zotero writes.
- A checked Markdown item alone should not be enough if the decision text remains `pending`.
- Rejected project-level decisions should not remove existing Zotero tags.
- The apply command must be preceded by a dry-run plan and should apply the reviewed plan artifact.
- Review reports should not contain secrets, raw API payloads, or unnecessary private note text.
