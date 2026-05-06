# Obsidian Policy

## Current Behavior

Current vault integration is split across:

- `paper_pipeline/vault_index.py`: reads selected Markdown notes from `Efforts/*` and `Atlas/*`;
- `paper_pipeline/decision_notes.py`: renders inbox decision notes;
- `paper_pipeline/decision_applier.py`: parses human decisions and can delete resolved inbox notes;
- `paper_pipeline/knowledge_application.py` and `paper_pipeline/note_patcher.py`: can create or patch local knowledge drafts after approval.

The target configuration uses `.env`/environment variables for Obsidian paths, while runtime artifacts default to repository-local `papers/` and `index/`.

No real Obsidian vault write was made during this documentation pass.

## Path Configuration

Human-decision files for Obsidian should be written only to a configured Obsidian inbox path. These paths should come from `.env` or environment variables, never hardcoded local paths.

Suggested environment variables:

- `VAULT_ROOT`: absolute Obsidian vault root;
- `OBSIDIAN_HUMAN_REVIEW_INBOX_DIR`: single inbox for all human-decision reports, including paper promotion, reference matching/acquisition, equation verification, and generated notes awaiting manual filing.

`VAULT_ROOT` should be absolute. Other Obsidian paths may be absolute or relative to `VAULT_ROOT`.

All human-decision Markdown surfaces should use the single configured inbox, including project-paper review reports, reference match/acquisition review tables, per-paper equation review files, and generated notes awaiting manual filing. The user moves accepted notes to their final Obsidian folders manually.

Equation-review Markdown files and their copied evidence images should be placed directly in the inbox, without creating a per-paper subfolder.

Generated plans may resolve these paths, but documentation and logs should avoid exposing private absolute paths unless explicitly requested for local debugging.

## Project Identification

MVP project inventory should map project state from the existing `Efforts` structure:

- `Efforts/On` -> `on`;
- `Efforts/Ongoing` -> `ongoing`;
- `Efforts/Simmering` -> `simmering`;
- `Efforts/Terminated` -> `terminated`.

Tags and frontmatter may supplement extraction, but they are not the source of truth for project state.

Recommended fields:

- title;
- objectives;
- methods;
- knowledge gaps;
- expected outputs;
- priority;
- tags;
- links;
- source path;
- content hash.

Terminated and unrelated notes should be ignored by default by downstream matching/classification, while the inventory may still record terminated projects for context.

## Review Reports

Review reports are temporary human-review surfaces, not permanent literature notes.

Review reports do not require frontmatter. Use stable filenames instead:

```text
review-project-papers-YYYY-MM-DD.md
review-reference-matches-YYYY-MM-DD.md
review-equations-{citekey}-YYYY-MM-DD.md
```

Reports may be written to a configured inbox/output directory. For the project-paper workflow, each review item should aggregate by paper while showing all useful project-paper matches for that paper. This avoids forcing a single primary project.

## Permanent Notes

Paper-note drafts should only be generated after human approval and only when the paper is in `.To Revise` or `.ToDig`, has an available PDF, and has metadata plus layer 1/2/3 extracted products available. A metadata-only Zotero item may appear in review and matching reports, but it should not receive a paper-note draft until the PDF and all required extracted products exist.

Papers already in `.To Revise` or `.ToDig` may need notes even before the new project-paper workflow created them. The note-generation project should therefore be able to plan drafts for existing `.To Revise` and `.ToDig` items after human review, not only for newly promoted papers, but still only when the PDF and required layer 1/2/3 products are available. The note should be generated from those extracted products and placed in the single Obsidian inbox for manual filing.

Paper-note drafts do not require frontmatter. They should use clear headings and sections, because the user will move and adapt them manually.

```markdown
# Robertson 1990 - Soil classification using CPT

## Why It Matters

...

## Relevant Formulations

...

## Assumptions

...

## Limitations

...

## Relationship With Projects

- [[CPTu Bayesian Soil Classification]]
```

## Link Preservation

Internal links should be preserved as Obsidian wikilinks. Automated patches should:

- write to configured safe paths only;
- avoid replacing whole files unless necessary;
- preserve existing frontmatter and user sections;
- add generated sections with clear source markers;
- avoid duplicate notes for the same citekey.

## Anti-Sprawl Rules

- Do not create permanent notes for every candidate.
- Do not create notes for `irrelevant_now` papers.
- Prefer grouped review reports before permanent notes.
- Require approval for project links and paper notes.
- Keep generated drafts in the single Obsidian inbox until manually filed.
