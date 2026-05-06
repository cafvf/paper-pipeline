# Development Plan

This plan keeps the next cycles small and reversible. It assumes no real Zotero or permanent Obsidian writes until the safe base is working.

## Cycle 1: Contracts And Fixtures

Tasks:

- add `schemas/project_profile.schema.json`;
- add `schemas/paper_profile.schema.json`;
- add `schemas/project_paper_match.schema.json`;
- add `schemas/llm_classification.schema.json`;
- add `configs/utility_taxonomy.yaml`;
- add `configs/zotero_tags.yaml`;
- add `configs/prompts.yaml`;
- add tests that validate example JSON against schemas.

Acceptance:

- `uv run ruff check`;
- `uv run pytest -q -o addopts=`;
- invalid LLM utility classes are rejected.

Risks:

- over-designing schemas too early.

Mitigation:

- keep required fields minimal for MVP 0.1.

## Cycle 2: Obsidian Project Inventory

Tasks:

- implement read-only project scanner;
- support `#projeto`;
- support `type: project` and `status: active`;
- extract title, objectives, methods, gaps, outputs, priority, tags, links, hash;
- add fixture vault tests.

Acceptance:

- scanner returns a table/list of active projects;
- inactive notes are ignored;
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

Acceptance:

- no Zotero writes;
- exports one article per line;
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

- create project-paper prompt using taxonomy;
- validate single-object JSON;
- classify top 10 candidates per project;
- store prompt/model/run metadata.

Acceptance:

- all outputs validate against schema;
- invalid confidence/action/utility values fail tests;
- classifications include reason, possible uses, limitations, and review requirement.

Risks:

- LLM hallucination or overconfidence.

Mitigation:

- require evidence-limited reasons and `requires_human_review: true`.

## Cycle 7: Review Export MVP

Tasks:

- generate grouped Markdown report;
- group by project and utility class;
- include editable decisions;
- parse decisions in tests if an apply phase is introduced.

Acceptance:

- review report is stable and readable;
- no Zotero writes;
- no permanent Obsidian notes.

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

