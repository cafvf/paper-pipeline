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
- the paper-level review status is `decided`;
- every required project-level decision is complete;
- the planned change has first been generated and inspected as a dry-run/auditable plan;
- credentials are available through environment variables;
- the command is an explicit sync/apply command.

The apply workflow must be two-step: first generate a dry-run plan with a `plan_hash`, then run the explicit apply command against that exact reviewed plan and expected hash. A direct apply without a preceding dry-run is out of scope for the safe MVP.

Tags should be additive by default. Existing user tags must not be removed automatically.

Stage tags beginning with `@` are mirrors that help Zotero search and must remain coherent with the final collection/stage decision. The collection/stage decision is the source of truth.

When a stage change is approved, the Zotero tag plan should add the new coherent `@` stage tag and remove the previous `@` stage tag. This is the explicit exception to the default "do not remove tags" rule, and it applies only to mutually exclusive stage tags.

When a move to `Expendable` is approved by an explicit human stage decision, the Zotero tag plan should add `!discarded`, remove mutually exclusive stage tags such as `@look`, `@review`, and `@dig`, remove the item from stage/triage collections such as `.ToLook`, `.To Revise`, and `.ToDig`, and move it to `Expendable`. Topic, project, paper, and other non-stage collections should be preserved. `!discarded` is a curatorial stage marker, not a protocol-quality tag.

Moving an item to `Expendable` should not delete local products under `papers/{citekey}/`. Those products remain local audit and recovery artifacts.

Products for `Expendable` items remain eligible for future reference mining and count with the same capture-score weight as `.ToLook`.

Automatic reference-mining runs should consume only already extracted products for `Expendable` items. New extraction for `Expendable` requires explicit manual execution.

`Expendable` is currently a policy. The sync plan should check whether a real Zotero collection exists for it. If it does not exist, the dry-run plan may include creating the collection at the Zotero library root before moving items.

Official stage mapping:

- `.ToLook` -> `@look`;
- `.To Revise` -> `@review`;
- `.ToDig` -> `@dig`;
- `Expendable` -> `!discarded`.

Use tags beginning with `$` capture how a paper contributes, such as background, gap signal, methods citation, discussion, extension, or manuscript-specific use. `$` tags should be suggested at paper level as the union of approved project-level uses.

Tags should come from `docs/Research Reading Protocol.md` and its operational derivative `docs/reading_protocol_criteria.md`. The system should not invent new protocol tags unless the taxonomy is intentionally updated.

## Reading Stage Policy

The existing operational collections represent reading depth:

- `.ToLook`: initial screening.
- `.To Revise`: deeper study, layer 2/3 extraction, and methodological review.
- `.ToDig`: deep formulation, implementation, insights, and applications.
- `Expendable`: not useful for any eligible project after review.

These stages are mutually exclusive. Stage movement should preserve earlier local products while moving the Zotero item to exactly one current stage collection.

Project utility is evaluated project by project. If a paper is approved for any eligible project, it should normally leave `.ToLook` and move to `.To Revise`. If it has high utility and passes secondary reading-protocol gates, it may move to `.ToDig`.

Moving a paper to `Expendable` should be valid only after all eligible project decisions are complete and none is approved.

If all project decisions are `rejected`, the system may recommend `Expendable`, but the final movement remains human-approved.

The reading protocol/gates in `docs/reading_protocol_criteria.md` are secondary evidence for stage recommendation. They do not replace human project-level utility decisions.

Initial `.ToDig` recommendation threshold: max project-paper adherence score >= `0.80`, or ToDig protocol gate passed. This threshold can be tuned later.

Reference acquisition recommendations do not create Zotero items. The human manually inserts recommended works into Zotero, normally in `.ToLook`; subsequent inventory runs confirm whether the recommendation can be cleared. Confirmed `.ToLook` items leave the acquisition list and enter the normal scan/match/classify/review workflow.

## Future AI Tags

Suggested future AI/project tags:

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

The apply command should refuse to mutate Zotero unless it can identify the reviewed dry-run plan or an equivalent immutable plan artifact and verify its `plan_hash`. Plan records should also include the source review hash, source inventory hash, and source config/policy hash used to produce the plan.
