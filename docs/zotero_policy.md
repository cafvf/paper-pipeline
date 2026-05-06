# Zotero Policy

## Current Behavior

Current Zotero integration lives mainly in `paper_pipeline/zotero_api.py`, `paper_pipeline/zotero_adapter.py`, and `paper_pipeline/zotero_plan.py`.

Observed behavior:

- credentials are read from environment variables: `ZOTERO_API_KEY`, `ZOTERO_USER_ID`, and optional `ZOTERO_DATA_DIR`;
- Better BibTeX citekeys are extracted from `Extra` fields matching `Citation Key:`, `tex.ids:`, or `citekey:`;
- candidates are currently listed from operational collections such as `.ToLook`, `.To Revise`, and `.ToDig`;
- metadata includes title, abstract, tags, year, DOI, item type, journal/proceedings title, creators, collection keys, and local PDF paths when present;
- `apply_plan` can write collections and tags through Zotero API `PUT`.

No real Zotero API call was made during this documentation pass.

## Read Policy

The future inventory module should read:

- Zotero key;
- Better BibTeX citekey;
- title;
- abstract;
- authors;
- year/date;
- DOI;
- item type;
- publication venue;
- collections;
- tags;
- whether a local PDF exists.

MVP 0.1 should not read full PDF content and should not require annotations.

## Write Policy

Writing to Zotero is not allowed during scan, match, classify, or export-review steps.

Zotero writes are allowed only when all are true:

- the user has reviewed a Markdown report;
- the item decision is `approved`;
- the planned change is shown in a dry-run or auditable plan;
- credentials are available through environment variables;
- the command is an explicit sync/apply command.

Tags should be additive by default. Existing user tags must not be removed automatically.

## Future Tags

Suggested tags:

```text
ai/status/approved
ai/status/reviewed
ai/utility/essential
ai/utility/methodological
ai/utility/formulational
ai/action/read-now
ai/action/extract-equations
project/cptu-bayesian-classification
```

The current repository uses reading-protocol tags such as `@look`, `@review`, `@dig`, `@looked_by_llm`, `@reviewed_by_llm`, and `@dug_by_llm`. Those should remain separate from future project-utility tags unless a migration is explicitly designed.

## Credential Policy

- Never hardcode Zotero credentials.
- Never commit `.env`, `config.yaml`, local Zotero DBs, request payload dumps, or user IDs.
- Avoid logging API keys, complete request headers, or sensitive response bodies.
- `save_payloads` should remain `false` by default because LLM payloads may contain private note or paper content.

## Safe Testing

Use fake sessions and `MemoryZoteroAdapter` for tests. The current suite already includes fake-session coverage in `tests/test_gate26_zotero_api_adapter.py`.

For future commands, prefer:

- `scan-zotero --offline-fixture`;
- `scan-zotero --dry-run`;
- `apply-zotero-tags --dry-run`;
- explicit confirmation or config flag before real writes.

