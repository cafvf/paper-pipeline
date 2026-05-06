# Roadmap

This roadmap is frozen as the MVP 0.1 implementation contract as of 2026-05-06. Later changes should update the spec freeze note in `docs/workflow_spec.md`.

Status vocabulary:

- ready: implemented and covered enough for the stated future contract;
- partial: useful implementation exists, but the project-specific contract is incomplete;
- not started: no direct implementation found;
- exists but needs refactor: implementation exists, but the current shape does not match the desired boundary;
- out of current scope: intentionally later.

| # | Project | Current status | Evidence found | Main gap | Next action |
| --- | --- | --- | --- | --- | --- |
| 1 | Semantic foundation and contracts | partial | `contracts.py`, `llm_schema.py`, `reading_protocol.py` define reading stages, decisions, tags, and LLM schema validation. | No `ProjectProfile`, `PaperProfile`, `ProjectPaperMatch`, or project-paper utility taxonomy files. | Add schemas/configs for project-paper contracts before new behavior. |
| 2 | Obsidian inventory | partial | `vault_index.py` indexes `Efforts/*` and selected `Atlas/*` Markdown with frontmatter, tags, links, headings, hashes. | Does not emit canonical `ProjectProfile` rows mapped from `Efforts/On`, `Efforts/Ongoing`, `Efforts/Simmering`, and `Efforts/Terminated`. | Add read-only `ProjectProfile` scanner with fixture tests. |
| 3 | Zotero inventory | partial | `zotero_api.py` reads collections, item metadata, citekeys, tags, years, DOI, authors, and local PDF paths; `zotero_adapter.py` has memory adapter. | Inventory is tied to operational collections and returns `CandidatePaper`, not a neutral `PaperProfile` export/JSONL. | Add read-only metadata export command using mockable adapter. |
| 4 | Local registry, cache, history | partial | `artifacts.py` writes per-paper JSON history and logs; `pdf_ingest.py` hashes PDFs. | No SQLite registry, no project/paper/prompt hashes, no pair-level reprocessing guard. | Design SQLite schema and add migration tests. |
| 5 | Project-paper matching engine | partial | `selection.py` scores candidates with vault lexical context; `embeddings.py` can call LM Studio embeddings. | Matching is paper-stage oriented, not per active project; no top-N candidates per project. | Implement lexical MVP first, then optional embeddings. |
| 6 | Article utility classifier | exists but needs refactor | `analysis_engine.py`, `lmstudio_chat.py`, and `llm_schema.py` classify papers with validated JSON. | Prompt/schema answer reading-stage questions, not "how does this paper help this project?". | Add new `LLMClassification` schema and prompt, keep existing analyzer separate. |
| 7 | Human review bench in Obsidian | partial | `decision_notes.py`, `assessment_notes.py`, and `runner.py` render inbox decision notes with human YAML blocks. | Current note is one paper per decision; future review should aggregate one paper item with all project-paper decisions. | Add Markdown review report export that is read-only with respect to Zotero. |
| 8 | Zotero tag synchronizer | exists but needs refactor | `zotero_plan.py`, `decision_applier.py`, `zotero_api.py` can plan and PUT collection/tag changes after decisions. | Future sync needs immutable dry-run plans with `plan_hash`, Expendable root collection check/create, removal from stage/triage collections on discard, and conservative tag removal limited to mutually exclusive stage tags. | Implement dry-run plan output and hash-verified apply for approved rows. |
| 9A | PDF product extraction | partial | `pdf_ingest.py` and `reading_packet.py` can convert PDFs and build reading packets. | Needs independent layer 1/2/3 products under `papers/{citekey}/`; should not perform deep interpretation. | Split extraction from analysis and test it independently. |
| 9C | Reference mining | not started | Protocol calls for mining references from review/deep papers; no direct module found. | Needs reference extraction/indexing from `.To Revise` and `.ToDig` papers, duplicate detection, non-DOI document types, separate fuzzy/non-DOI match review, missing-in-Zotero reporting, and attach/find-PDF recommendations. | Add independent reference-mining project after reference extraction exists. |
| 9B | Deep PDF analyzer | partial | `analysis_engine.py` can analyze stage-specific packets with local LLM. | Should consume extracted products, not raw PDFs by default; must be approved/relevant-paper gated. | Reuse after PDF products exist and approval policy is clear. |
| 10 | Technical notes and links in Obsidian | exists but needs refactor | `knowledge_application.py` and `note_patcher.py` create drafts/patches under configured vault paths after decisions. | Current outputs are literature/knowledge drafts; future note drafts go to the single Obsidian inbox and must require `.To Revise`/`.ToDig`, an available PDF, and extracted layer 1/2/3 products. | Document future note format and approval/PDF/product boundary. |
| 11 | Reading, study, and reproduction planner | partial | `reading_plan.py` defines stage-specific reading steps; `run_summary.py` writes run summaries. | No project-level study plan with read-now/read-later/implement blocks. | Build from approved classifications after MVP 0.1. |
| 12 | Gap, redundancy, and maturity auditor | not started | No direct module found. | No project-level coverage model or redundancy detector. | Defer until registry contains enough approved classifications. |
| 13 | General orchestrator | partial | `cli.py` exposes `run`, `pilot-run`, `zotero-dry-run`; `runner.py` orchestrates current pipeline. | Future command set and scheduling policy do not exist; CLI still contains current operational workflow. | Implement after independent modules have stable outputs. |

## Recommended Order

### Block 1: Safe Base

1. Add semantic schemas/configs.
2. Add read-only Obsidian project inventory.
3. Add read-only Zotero paper inventory/export.
4. Add SQLite registry design and migrations.
5. Add project-paper matching.
6. Add utility classification.
7. Add grouped human-review Markdown export.

This block should answer: which Zotero papers are useful for which Obsidian projects, with justification and an initial reading queue, without changing Zotero or permanent Obsidian notes.

### Block 2: Controlled Curation

8. Apply Zotero tags only for approved decisions.
9. Generate permanent Obsidian article notes only after approval.

### Block 3: Deep Study And Strategy

10. Analyze PDFs only for approved relevant papers.
11. Generate study/reproduction plans.
12. Audit gaps, redundancy, and project maturity.
13. Unify commands in a small local CLI.

Project 13 is an integrator, not the owner of domain behavior. It should sequence independent commands, enforce scheduling/runtime limits, and resume nightly work.

## MVP 0.1 Acceptance

- Uses fixtures or explicit safe paths.
- Produces `ProjectProfile` rows for 3 to 5 active notes.
- Produces `PaperProfile` rows for 100 to 300 Zotero metadata items.
- Produces top 20 candidates per project before LLM.
- Classifies top 10 per project with valid JSON.
- Exports one Markdown review report.
- Does not write Zotero, does not create permanent Obsidian notes, and does not read full PDFs.
