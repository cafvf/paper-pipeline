# Context Snapshot — Zotero/Obsidian Paper Triage

- **Slug:** `zotero-obsidian-paper-triage`
- **Captured at (UTC):** `2026-08-09T13:44:12Z`
- **Planning mode:** `$ralplan --deliberate`
- **Repository state:** greenfield; no application code exists. The only prior artifacts are `.omx/interviews/zotero-obsidian-mvp.md` and `.omx/specs/deep-interview-zotero-obsidian-mvp.md`.
- **Ambiguity after deep interview:** 1.5% (recorded target: <=2%).

## Task statement

Plan, but do not implement, a local-first application that classifies a real Zotero library and later uses Obsidian projects discovered under `Efforts` as an additional relevance signal. The MVP must execute against an explicitly selected batch of exactly 10 real papers while preserving Zotero data outside a narrow, auditable mutation boundary.

## Desired outcome

A Spec-Driven Design (SDD) and Test-Driven Development (TDD) handoff that an execution team can implement without inventing product rules. The plan must define:

1. deterministic paper normalization and triage;
2. explicit confidence and fallback behavior;
3. safe Zotero reads/writes with idempotency and targeted reversibility;
4. structured records for decisions, mutations, and run reports;
5. read-only Obsidian `Efforts` discovery as a future-compatible adapter;
6. real-batch acceptance criteria for 10 papers.

## Closed product decisions

### Mutation boundary

- Automatic Zotero changes require `confidence >= 0.85`.
- Below `0.85`, preserve the current stage/collection placement and add `@needs-reread` only.
- Managed metadata may include:
  - subject tags beginning with `#`;
  - method tags beginning with `%`;
  - stage tags beginning with `@`;
  - existing root collections `Look`, `Review`, `Dig`;
  - zero or more already-existing `BySubject` subcollections, including multiple matches.
- Reclassification removes only mutations recorded by this application as managed.
- The application must not create a missing `BySubject` subcollection; it reports the missing target.
- The application never modifies Obsidian notes, PDFs, highlights, Zotero notes, Concepts/MOCs, or ideas.

### Classification protocol

- `Look`: assign when at least one configured trigger is present.
- `Review`: assign when the paper scores at least `3/6`, one point for each:
  1. relevant to a known subject or project;
  2. useful/credible method;
  3. published within the last 10 years relative to the run date **or** identified as seminal;
  4. credible authors/venue evidence;
  5. explicit gap signal;
  6. a concrete, citable sentence or claim is identifiable from allowed metadata.
- `Dig`: assign only when all five type-specific criteria are satisfied. The implementation spec must encode two named deterministic checklists rather than a free-form score:
  - **Original research:** clear research question/gap; reproducible method; accessible evidence/results; direct relevance/extension potential; limitations or boundary conditions identifiable.
  - **Review paper:** explicit scope/question; transparent search/selection method; synthesis beyond enumeration; gap/consensus/conflict map; direct relevance/citable utility.
- Low confidence never moves a paper between stages or collections.

### Canonical taxonomy

| Namespace | Canonical values |
|---|---|
| Subjects (`#`) | `#rock-mechanics`, `#bayesian-inference`, `#PINNs-geomech`, `#soil-classification`, `#structural-reliability`, `#wellbore-stability`, `#sand-production`, `#structural-analysis` |
| Methods (`%`) | `%FEM`, `%FDM`, `%DEM`, `%BEM`, `%experimental`, `%field-data`, `%machine-learning`, `%narrative-review`, `%systematic-review`, `%python-sci` |
| Project/use signals (`$`) | `$background`, `$gap-signal`, `$methods-cite`, `$discussion`, `$extend`, `$paper-01`, `$paper-02` |
| Quality/evidence (`!`) | `!seminal`, `!high-impact`, `!weak-methods`, `!conflicting`, `!data-available` |
| Workflow stage (`@`) | `@look`, `@review`, `@dig`, `@annotated`, `@code-tested`, `@needs-reread` |

### Technology constraints

- Local application; deterministic rules are authoritative in the MVP.
- A local LLM may be introduced later only behind an optional classification interface. It must never directly write to Zotero and must not weaken deterministic validation or confidence gating.
- Use Pydantic models and JSON-serializable contracts as the canonical application boundary.
- Secrets, tokens, credentials, raw PDFs, and sensitive connector payloads must never be logged.

## Evidence available

- `.omx/interviews/zotero-obsidian-mvp.md`
- `.omx/specs/deep-interview-zotero-obsidian-mvp.md`
- User-supplied canonical taxonomy and stage protocol in the planning request.

## Assumptions made explicit

1. Zotero API/library identifiers and credentials are supplied through environment/configuration outside persisted run artifacts.
2. The MVP can select 10 item keys explicitly; it must not silently take an arbitrary first 10 from the entire library.
3. Existing `BySubject` collections are mapped by configured aliases to canonical subject tags, because display names may not equal tag spelling.
4. `@look`, `@review`, and `@dig` are mutually exclusive managed stage tags. `@annotated`, `@code-tested`, and `@needs-reread` are status flags and are not removed merely because stage changes.
5. Existing human-created tags or collection memberships remain user-owned unless a prior successful run recorded that exact mutation as application-managed.
6. The current planning artifacts deliberately do not select a Zotero client library or packaging tool; implementation should prefer a thin port so the domain and safety tests do not depend on a specific SDK.

## Open questions deferred without blocking the MVP plan

- Exact Zotero connector choice (Web API client vs local database/read API) should be resolved at implementation kickoff using official documentation and a dependency review.
- Exact Obsidian vault path and `Efforts` metadata/frontmatter convention remain deployment configuration. The MVP adapter may return zero project profiles without failing classification.
- The supplied phrase “Look if there is a trigger” requires a versioned trigger catalog. The plan defines the configuration contract and test fixtures; the initial synonym phrases must be reviewed before the first real apply.
- Author/venue credibility must come from deterministic allowlists or explicit metadata flags in the MVP; no network reputation lookup is assumed.

## Likely implementation touchpoints (proposed, not created here)

```text
pyproject.toml
src/paper_pipeline/
  domain/{models.py,taxonomy.py,errors.py}
  normalization/{paper.py,text.py}
  classification/{rules.py,scoring.py,confidence.py}
  ports/{zotero.py,projects.py,mutation_store.py}
  adapters/{zotero_client.py,obsidian_efforts.py,jsonl_mutation_store.py}
  application/{plan_run.py,apply_run.py,reclassify.py,reporting.py}
  cli.py
tests/{unit,integration,e2e,fixtures}/
```

## Planning stop condition

Planning is complete when the PRD and test specification define the domain contracts, safety invariants, staged work plan, acceptance checks, RALPLAN-DR/ADR reasoning, and execution handoff. No source implementation or live Zotero mutation is part of this planning session.
