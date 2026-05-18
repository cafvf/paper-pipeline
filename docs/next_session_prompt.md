# Next Session Prompt

Continue development of `paper-pipeline` from the current post-Phase-2 state.

## Current implemented state

- Phase 0 boundary freeze is in effect: `runner.py` / `run` / `pilot-run` remain legacy paper-stage flow.
- Phase 1 is implemented:
  - `scan-obsidian`
  - `scan-zotero`
  - `match`
  - `classify`
- Phase 2 is implemented:
  - `export-review`
- `match` now supports `--paper-stages` and `--max-candidates-total`.
- `classify` now supports `--paper-stages` and `--max-candidates`.
- `classify` also has semantic coherence checks and retry feedback when the LLM produces stage/action contradictions.
- `export-review` produces grouped Markdown review files at `data/review-project-papers-YYYY-MM-DD.md`.

## Assume this command chain has already finished

```bash
uv run paper-pipeline scan-obsidian --output data/projects.jsonl
uv run paper-pipeline scan-zotero --output data/papers.jsonl --papers-root papers
uv run paper-pipeline match \
  --projects data/projects.jsonl \
  --papers data/papers.jsonl \
  --output data/candidates.jsonl \
  --paper-stages ".ToLook" \
  --max-candidates-total 8
uv run paper-pipeline classify \
  --candidates data/candidates.jsonl \
  --projects data/projects.jsonl \
  --papers data/papers.jsonl \
  --output data/classifications.jsonl \
  --paper-stages ".ToLook" \
  --max-candidates 8
uv run paper-pipeline export-review \
  --classifications data/classifications.jsonl
```

## Immediate next goal

Implement the **thin nightly orchestrator** for the project-paper flow.

## Orchestrator requirements already decided

- It must be a **thin orchestrator over independent commands**.
- It must not absorb matching logic, classification logic, Zotero rules, Obsidian note rules, or PDF/deep-analysis logic.
- It should run on a **nightly basis**.
- It should analyze a **maximum of 10 papers total per run**.
- It should divide the nightly budget across:
  - `.ToLook`
  - `.To Revise`
  - `.ToDig`
- It should only select papers **not yet evaluated in their current layer**.
- Each later layer must account for **deeper analysis and stricter criteria** than the previous one.

## Expected next work items

1. Define the orchestrator command surface (`triage` or `run-triage`).
2. Define how per-layer selection state is recorded:
   - citekey
   - current layer/stage
   - evaluation completion
   - prompt/input hash or equivalent rerun key
3. Decide how the orchestrator queries pending papers per layer without pushing business logic into the orchestrator.
4. Add tests for:
   - nightly budget <= 10 total
   - per-layer allocation/rollover
   - skip already-evaluated-in-current-layer behavior
   - sequencing-only orchestration boundary
5. Keep the output artifacts canonical; registry remains cache/history.

## Guardrails

- Do not route new project-paper behavior through `runner.py`.
- Do not start PDF/deep-analysis/apply work yet.
- Keep all changes test-driven and spec-driven.
- Preserve the existing Phase 1 and Phase 2 command contracts.

## Verification target

Before concluding the next session, run at least:

```bash
uv run ruff check
uv run pytest -q -o addopts=
```
