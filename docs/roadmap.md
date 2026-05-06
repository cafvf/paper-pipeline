# Roadmap

Status vocabulary:

- ready: implemented and covered enough for the stated future contract;
- partial: useful implementation exists, but the project-specific contract is incomplete;
- not started: no direct implementation found;
- exists but needs refactor: implementation exists, but the current shape does not match the desired boundary;
- out of current scope: intentionally later.

| # | Project | Current status | Evidence found | Main gap | Next action |
| --- | --- | --- | --- | --- | --- |
| 1 | Semantic foundation and contracts | partial | `contracts.py`, `llm_schema.py`, `reading_protocol.py` define reading stages, decisions, tags, and LLM schema validation. | No `ProjectProfile`, `PaperProfile`, `ProjectPaperMatch`, or project-paper utility taxonomy files. | Add schemas/configs for project-paper contracts before new behavior. |
| 2 | Obsidian inventory | partial | `vault_index.py` indexes `Efforts/*` and selected `Atlas/*` Markdown with frontmatter, tags, links, headings, hashes. | Does not extract active project profiles from `#projeto` or `type: project`/`status: active`. | Add read-only `ProjectProfile` scanner with fixture tests. |
| 3 | Zotero inventory | partial | `zotero_api.py` reads collections, item metadata, citekeys, tags, years, DOI, authors, and local PDF paths; `zotero_adapter.py` has memory adapter. | Inventory is tied to operational collections and returns `CandidatePaper`, not a neutral `PaperProfile` export/JSONL. | Add read-only metadata export command using mockable adapter. |
| 4 | Local registry, cache, history | partial | `artifacts.py` writes per-paper JSON history and logs; `pdf_ingest.py` hashes PDFs. | No SQLite registry, no project/paper/prompt hashes, no pair-level reprocessing guard. | Design SQLite schema and add migration tests. |
| 5 | Project-paper matching engine | partial | `selection.py` scores candidates with vault lexical context; `embeddings.py` can call LM Studio embeddings. | Matching is paper-stage oriented, not per active project; no top-N candidates per project. | Implement lexical MVP first, then optional embeddings. |
| 6 | Article utility classifier | exists but needs refactor | `analysis_engine.py`, `lmstudio_chat.py`, and `llm_schema.py` classify papers with validated JSON. | Prompt/schema answer reading-stage questions, not "how does this paper help this project?". | Add new `LLMClassification` schema and prompt, keep existing analyzer separate. |
| 7 | Human review bench in Obsidian | partial | `decision_notes.py`, `assessment_notes.py`, and `runner.py` render inbox decision notes with human YAML blocks. | Current note is one paper per decision, not grouped by project and utility class. | Add Markdown review report export that is read-only with respect to Zotero. |
| 8 | Zotero tag synchronizer | exists but needs refactor | `zotero_plan.py`, `decision_applier.py`, `zotero_api.py` can plan and PUT collection/tag changes after decisions. | Current tags are reading-protocol tags; future tags must be additive project/utility/action tags after approval only. | Document tag policy, then implement dry-run plan output for approved rows. |
| 9 | Deep PDF analyzer | partial | `pdf_ingest.py`, `reading_packet.py`, and `analysis_engine.py` convert PDFs and analyze stage-specific packets. | Already deeper than MVP 0.1; not gated by project-paper approval in the new roadmap. | Keep out of MVP 0.1; later reuse after approved relevance. |
| 10 | Technical notes and links in Obsidian | exists but needs refactor | `knowledge_application.py` and `note_patcher.py` create drafts/patches under configured vault paths after decisions. | Current outputs are literature/knowledge drafts, not project-paper permanent notes with the proposed frontmatter. | Document future note format and approval boundary. |
| 11 | Reading, study, and reproduction planner | partial | `reading_plan.py` defines stage-specific reading steps; `run_summary.py` writes run summaries. | No project-level study plan with read-now/read-later/implement blocks. | Build from approved classifications after MVP 0.1. |
| 12 | Gap, redundancy, and maturity auditor | not started | No direct module found. | No project-level coverage model or redundancy detector. | Defer until registry contains enough approved classifications. |
| 13 | General orchestrator | partial | `cli.py` exposes `run`, `pilot-run`, `zotero-dry-run`; `runner.py` orchestrates current pipeline. | Future command set (`scan`, `match`, `classify`, `export-review`) does not exist and CLI still contains current operational workflow. | Add new read-only subcommands without breaking current CLI. |

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

## MVP 0.1 Acceptance

- Uses fixtures or explicit safe paths.
- Produces `ProjectProfile` rows for 3 to 5 active notes.
- Produces `PaperProfile` rows for 100 to 300 Zotero metadata items.
- Produces top 20 candidates per project before LLM.
- Classifies top 10 per project with valid JSON.
- Exports one Markdown review report.
- Does not write Zotero, does not create permanent Obsidian notes, and does not read full PDFs.

