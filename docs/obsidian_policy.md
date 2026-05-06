# Obsidian Policy

## Current Behavior

Current vault integration is split across:

- `paper_pipeline/vault_index.py`: reads selected Markdown notes from `Efforts/*` and `Atlas/*`;
- `paper_pipeline/decision_notes.py`: renders inbox decision notes;
- `paper_pipeline/decision_applier.py`: parses human decisions and can delete resolved inbox notes;
- `paper_pipeline/knowledge_application.py` and `paper_pipeline/note_patcher.py`: can create or patch local knowledge drafts after approval.

The repository is configured so `vault_root` can point outside the repo, while runtime artifacts default to repository-local `papers/` and `index/`.

No real Obsidian vault write was made during this documentation pass.

## Project Identification

MVP project inventory should read only explicit project notes:

- notes tagged with `#projeto`; or
- frontmatter containing `type: project` and `status: active`.

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

Inactive, archived, and unrelated notes should be ignored by default.

## Review Reports

Review reports are temporary human-review surfaces, not permanent literature notes.

Suggested frontmatter:

```yaml
---
type: research-review
review_kind: project_paper_triage
status: pending
created: 2026-05-06
---
```

Reports may be written to a configured inbox/output directory. They should be grouped by project and utility class.

## Permanent Notes

Permanent paper notes should only be created after human approval.

Expected format:

```yaml
---
type: paper-note
citekey: robertson1990soilclassification
utility:
  - essential
projects:
  - CPTu Bayesian Soil Classification
status: reviewed
---
```

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
- Keep generated drafts in an inbox/draft area until reviewed.

