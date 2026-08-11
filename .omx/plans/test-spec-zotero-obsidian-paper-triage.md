# Test Specification — Local Zotero/Obsidian Paper Triage

**Status:** normative TDD companion, consensus iteration 4
**PRD:** `.omx/plans/prd-zotero-obsidian-paper-triage.md`
**Test philosophy:** prove mutation authority, hash/approval binding, crash recovery, and preservation before convenience.

## 1. Quality claims to prove

1. Identical versioned inputs yield byte-identical hashable projections and identical deterministic operation ids/digests/plan hash; trace/presentation artifacts are excluded from this claim.
2. Automatic tag writes are strictly limited to canonical `#`, `%`, and `@`; `$` and `!` always remain advisory `keep|skip`, including at confidence `1.0000`.
3. Full mutation requires confidence `>=0.8500`; below it only an absent `@needs-reread` may be added.
4. Apply executes only the exact persisted plan bound to an immutable SQLite `apply_authorization`; authorization validation commits before any `planned` row, and every included field is tamper-evident.
5. Static validation precedes durable `authorization -> planned`; dynamic item validation then chooses call-free terminal `skipped_stale|aborted` or `atomic(AttemptEvidence + attempted) -> Zotero write -> reread -> verified`. Crashes reconcile from SQLite alone without blind retry or invented ownership.
6. Each operation uses a hash-bound symbolic `PreviewVersion(v)` or `VerifiedVersionOf(operation_id)` precondition; only the runtime command carries a numeric expected version.
7. No removal lacks exact active verified managed ownership with an unbroken app-verified version lineage; any external advance or human re-add protects the target and is reported; reapply is a no-op.
8. Zotero fields, human tags/collections, excluded resources, Obsidian, secrets, and paths outside configured roots remain unchanged or undisclosed.
9. Exactly 10 explicitly selected real items can pass preview, approval, apply, verify, and reapply; an 11th is never authorized.

## 2. Mandatory gates

| Gate | Evidence | Live apply blocked until pass |
|---|---|---:|
| S1 schemas/goldens | every normative JSON Schema, round-trip, per-field tamper, canonical ordering | yes |
| S2 pure domain | taxonomy, rules cross-product, confidence vectors, mutation properties | yes |
| S3 store/port contracts | SQLite crash matrix, exact DTO/diff/version contract | yes |
| S4 simulated E2E/security | approval binding, partial recovery, canaries, permissions/paths | yes |
| S5 real batch | reviewed 10-item plan and post-apply verification | final |

## 3. Schema and canonicalization tests

### 3.1 Pydantic schema matrix

| ID | Case | Expected |
|---|---|---|
| `U-SCHEMA-001` | valid minimal `Paper`, including nullable venue | strict canonical round-trip |
| `U-SCHEMA-002` | unknown field in any persisted model | rejected (`extra=forbid`) |
| `U-SCHEMA-003` | blank title / invalid timezone / invalid item key | rejected with stable validation issue |
| `U-SCHEMA-004` | malformed DOI or year outside 1000..run_year+1 | normalized null + stable warning |
| `U-SCHEMA-005` | `paper_kind=original`, Dig stage without Look pass | rejected |
| `U-SCHEMA-006` | `paper_kind=review` from `%systematic-review`, Look pass, Review 2/6, applicable review Dig 5/5 | rejected |
| `U-SCHEMA-007` | `paper_kind=original`, Look pass, Review 3/6, applicable original Dig 5/5 | accepted |
| `U-SCHEMA-008` | `TagDecision.remove` without ownership id | rejected |
| `U-SCHEMA-009` | `$background` or `!seminal` with `add` or `remove` | rejected at `0.8499`, `0.8500`, and `1.0000` |
| `U-SCHEMA-010` | `$`/`!` with `keep` if present or `skip` if absent | accepted, `managed=false` |
| `U-SCHEMA-011` | collection creation or missing-key write | rejected |
| `U-SCHEMA-012` | `PlannedOperation` cross-item dependency / duplicate sequence | rejected |
| `U-SCHEMA-013` | stage tag op while root absent has no matching prior root add, or while root was preview-present lacks the hash-bound symbolic precondition | rejected; preview-present root needs no add/ownership |
| `U-SCHEMA-014` | remove operation without active verified add reference | rejected |
| `U-SCHEMA-015` | `ApplyRequest` with extra selector/reclassification/config field | rejected |
| `U-SCHEMA-016` | approval item/operation list differs from plan | rejected |
| `U-SCHEMA-017` | counter/report reconciliation mismatch | finalization rejected |
| `U-SCHEMA-018` | absolute, parent-escaping, or symlinked project/store path | rejected |
| `U-SCHEMA-019` | first operation lacks `PreviewVersion(v)`, or later operation uses it / references anything except immediately preceding verified operation | rejected |
| `U-SCHEMA-020` | persisted operation contains numeric predicted `expected_item_version` | rejected as unknown/forbidden field |
| `U-SCHEMA-021` | `project_profile_snapshot` absent, digest absent, or empty-profile snapshot omitted | rejected |
| `U-SCHEMA-022` | `paper_kind=ambiguous` with Dig profile/stage | rejected |
| `U-SCHEMA-023` | `ReviewedDiffProjection` row has missing/extra schema fields or diverges from derived operations/order | rejected |
| `U-SCHEMA-024` | `AttemptEvidence` lacks version, full tags, full collections, or any required preserved-field hash | rejected; transaction cannot enter attempted |
| `U-SCHEMA-025` | `managed_mutation`/`planned` lacks immutable `apply_authorization`, or authorization hashes/approved sets/digest mismatch | rejected; zero gateway calls |
| `U-SCHEMA-026` | positive evidence has unknown/unweighted `match_kind`, or passing rule lacks weighted underlying evidence | rejected |
| `U-SCHEMA-027` | Look/Review/Dig root keys contain a duplicate, or any root key equals any flattened BySubject destination key | reject complete config with `CONFIG_COLLECTION_ROLE_COLLISION`; no plan/authorization/call |
| `U-SCHEMA-028` | mutation event uses an undeclared transition, or `skipped_stale|aborted` has AttemptEvidence/a successor | rejected; terminal pre-call states remain call-free |

### 3.2 Golden plan/apply corpus

Maintain one reviewed canonical golden for each of `PreviewPlan`, `MutationPlan`, `PlannedItem`, `PlannedOperation`, `ApplyRequest`, `ApprovalEvidence`, and `ApplyAuthorization`, plus a full 10-item plan.

| ID | Mutation | Expected |
|---|---|---|
| `G-PLAN-001` | parse -> dump -> parse every schema | byte-identical canonical JSON and semantic equality |
| `G-PLAN-002` | independently recompute every snapshot digest, operation id, confirmation digest, plan hash | exact known lowercase SHA-256 values |
| `G-PLAN-003` | mutate each hash-included scalar/list/map field one at a time, including nested config/collection/project-profile/ruleset/taxonomy fields | digest/hash mismatch and apply refusal |
| `G-PLAN-004` | delete each required included field one at a time | schema failure |
| `G-PLAN-005` | mutate `plan_hash`, operation id, approval hash, reviewed operation ids, or approved item keys | `PLAN_TAMPERED`/`APPROVAL_MISMATCH`, zero writes |
| `G-PLAN-006` | vary only excluded preview id, creation time, decision id, presentation text, or non-blocking issue | same plan hash |
| `G-PLAN-007` | reorder object keys, input sets, items, decisions, aliases, collection snapshot entries | canonical bytes/hash unchanged |
| `G-PLAN-008` | reorder semantic operation sequence or dependency array | rejected or different hash; never silently normalized to a different execution meaning |
| `G-PLAN-009` | serialize float instead of fixed four-decimal string, non-NFC string, duplicate set member, or noncanonical number | rejected before hashing |
| `G-PLAN-010` | snapshot digest correct but value absent, or value changed with stale digest | fatal tamper |
| `G-PLAN-011` | rendered structured diff hash absent/changed, approval created before complete diff, or confirmation formula differs by one byte | apply refused |
| `G-PLAN-012` | identical approved plan reapplied | zero gateway mutations; existing verified evidence retained |
| `G-PLAN-013` | zero discovered profiles represented as `profiles: []`; omit it, change its digest, or inject a profile after preview | valid unchanged hash for exact empty snapshot; otherwise tamper and zero writes |
| `G-PLAN-014` | replace `PreviewVersion(v)` / `VerifiedVersionOf(id)`, alter referenced id, or add a predicted numeric version | operation id/plan hash mismatch or schema refusal |
| `G-PLAN-015` | independently derive `ReviewedDiffProjection` and JCS digest from operations | exact projection equality, fixed field set/order, and known digest |
| `G-PLAN-016` | persist validated approval as `apply_authorization`, then attempt update/delete or mutate an approved set/hash/digest | exact canonical columns/FKs; update/delete rejected; mismatch never reaches `planned` |

The per-field tamper generator must traverse every JSON Schema property recursively; coverage asserts no hash-included leaf is unmutated.

## 4. Normalization, taxonomy, and frozen rule tests

### 4.1 Normalization

- NFC, entity/markup removal, whitespace collapse, DOI URL/prefix/trailing punctuation, venue normalization, author/ORCID validation, stable creator order, tag/collection set sorting.
- Missing authors/year/DOI/abstract/venue remains a valid Paper with explicit warning and exact coverage component.
- Connector differences outside classification/preservation DTO fields do not change source fingerprint.
- Attachment DTO contains reference metadata only; bytes/path are never read or represented.
- Non-null duplicate DOI blocks every sharing item with non-retryable `PAPER_DUPLICATE_IDENTITY`; duplicate citekey is warning-only and item keys remain independent.
- `item_type_class`/`paper_kind` matrix is exact: each raw original-paper type `journalArticle|conferencePaper|preprint|thesis|report` -> `item_type_class=original_candidate`, then without review tags -> `paper_kind=original` and with either `%narrative-review` or `%systematic-review` -> `paper_kind=review`; every enumerated support/non-paper type -> `item_type_class=support_or_nonpaper` and `paper_kind=ambiguous`, including when a review tag is present; every unknown future type -> `item_type_class=unknown` and `paper_kind=ambiguous`, including when a review tag is present; child `attachment|note|annotation` -> rejected before `Paper`; title/abstract wording cannot resolve ambiguity.

### 4.2 Exact taxonomy/alias matrix

Parameterize every canonical value and every frozen alias in PRD section 9. Assert canonical spelling, whole-token match, longest match, source allowlist, and the total `match_kind`/specificity table (`existing_canonical_tag=1.0000`, `exact_rule_phrase=0.9500`, `venue_allowlist_exact=0.9000`, `author_allowlist_exact=0.9000`, `zotero_type_allowlist_exact=0.9000`, `frozen_alias=0.8500`, `recency_window=0.8000`, `project_profile_exact=0.7500`). Explicit negatives:

- `%DEM` does not match arbitrary substrings; `ml` does not match longer tokens.
- `no|not|without` within exactly three prior tokens produces conflict; at four tokens it does not negate.
- equal-length alias collision yields conflict and no selection.
- unknown or fuzzy/regex-like text yields no canonical value.
- `$`/`!` signals may affect Classification/criteria but generate only `keep|skip` decisions and zero PlannedOperations.
- any taxonomy, alias, credible venue, credible author, threshold, or rule edit changes a snapshot digest and plan hash.

### 4.3 Look/Review/Dig cross-product

| ID | Look | Review passes | Dig profile/results | Expected stage |
|---|---:|---:|---|---|
| `U-RULE-001` | false | 0..6 | none or 0..5 | null |
| `U-RULE-002` | true | 0..2 | 0..4 | look |
| `U-RULE-003` | true | 3..6 | 0..4 / unknown / conflict | review |
| `U-RULE-004` | false | 3..6 | exact 5/5 | null (Dig cannot bypass Look) |
| `U-RULE-005` | true | 2 | exact 5/5 | look (Dig cannot bypass Review) |
| `U-RULE-006` | true | 3 | original type, applicable original checklist 5/5 | dig |
| `U-RULE-007` | true | 6 | `%systematic-review`, but only original checklist is 5/5 | review; wrong checklist cannot authorize Dig |
| `U-RULE-008` | true | 6 | support/non-paper Zotero type, no applicable profile | review; `PAPER_KIND_AMBIGUOUS` |
| `U-RULE-009` | true | 3..6 | `paper_kind=ambiguous`, apparent 5/5 | review; `PAPER_KIND_AMBIGUOUS`; Dig blocked |

Generate the complete boolean/count cross-product for Look `{F,T}`, Review `0..6`, Dig passes `0..5`, `paper_kind {original,review,ambiguous}`, and unknown/conflict injection. Also test every frozen trigger, all six Review criteria boundaries, both five-item Dig checklists, exact 10-year boundary, and the deterministic metadata/tag kind derivation.

### 4.4 Credibility rules

- A syntactically valid but unlisted ORCID does not pass; an exact normalized name tuple or exact ORCID passes only when explicitly present in the snapshotted `credible_authors` allowlist.
- Exact normalized venue in snapshotted `credible_venues` passes; substring/unsnapshotted venue does not.
- Existing advisory `!seminal` or `!high-impact` passes but produces no tag write.
- Only positive credibility plus `!weak-methods` yields conflict.
- No network/citation lookup is invoked; zero evidence yields unknown.
- Every passing recency/author/venue/type path emits its exact weighted `match_kind`; generic/default weighting is impossible.

### 4.5 Exact confidence vectors

For each vector, assert `C`, `S`, `A`, `K`, weighted sum, ROUND_HALF_UP result, and decision outcome. Required vectors: all complete/exact/no-conflict; all missing/no evidence; each single missing coverage field; each of the eight specificity kinds individually and in mixed means; recency-, venue-, author-, and type-only passing Review/Dig evidence; 0..4 distinct conflicts; Dig profile included/excluded from K; duplicate evidence id counted once; rounding ties; exactly `0.8499`, `0.8500`, and `1.0000`. An LLM proposal cannot change any component.

## 5. Mutation, ownership, dependency, and property tests

| ID | State | Expected |
|---|---|---|
| `U-MUT-001` | desired writable tag absent, high confidence | managed add |
| `U-MUT-002` | desired human-present tag, no ledger | keep, no ownership claim |
| `U-MUT-003` | undesired human tag/collection | keep; no removal |
| `U-MUT-004` | undesired target has active verified app add | remove with exact ownership id |
| `U-MUT-005` | ownership only planned/attempted/failed/uncertain | removal rejected |
| `U-MUT-006` | low confidence | only absent `@needs-reread` add; no collection/stage/#/% change |
| `U-MUT-007` | `$`/`!` signal absent/present at confidence 1.0000 | skip/keep, no operation |
| `U-MUT-008` | initial stage root resolved but absent | root add precedes and is dependency of `@stage` add |
| `U-MUT-009` | target stage root already present, human or unmanaged | no root add and no collection ownership claim; hash-bound precondition permits direct `@stage` add |
| `U-MUT-010` | target root missing/ambiguous/changed | neither root nor stage tag operation exists |
| `U-MUT-011` | app-owned stage transition | target root -> target tag -> old tag remove -> old root remove |
| `U-MUT-012` | human-owned conflicting stage | no stage movement; conflict warning |
| `U-MUT-013` | multiple BySubject keys, one missing | all resolved safe ops retained; missing reported, no create |
| `U-MUT-014` | human/app-owned needs-reread | human preserved; verified app-owned removable only after high-confidence plan |
| `U-MUT-015` | verified app add, then any external item-version advance before planned removal; target still present | no removal; `MANAGED_OWNERSHIP_SUPERSEDED`; target preserved |
| `U-MUT-016` | app added target, human removes and re-adds it | ownership lineage broken; re-added target is human-protected and reported |

Property tests:

1. every removal references compatible active verified ownership;
2. every PlannedOperation target is `#|%|@` or an existing snapshotted collection key;
3. arbitrary `$`/`!` classifications never produce operations;
4. plan permutation invariance and canonical byte/hash determinism;
5. after verified apply, replanning is a fixed point;
6. arbitrary external version insertion aborts remaining item operations and invalidates every automatic removal derived from the prior app-verified snapshot, regardless of target presence;
7. dependency graph is acyclic, contiguous, same-item, and canonical;
8. arbitrary human fields/tags/collections outside the exact target remain equal;
9. arbitrary path/secrets canaries never escape containment/redaction.

## 6. Integration and contract tests

### 6.1 Zotero port conformance suite

Fake and chosen real adapter must pass the identical suite for `ReadItemsRequest`, `ZoteroItemSnapshot`, `ReadCollectionTreeRequest`, `CollectionTreeSnapshot`, `ZoteroMutationCommand`, and `ZoteroMutationReceipt`:

- preview makes zero mutation calls; forbidden resource/create methods do not exist;
- persisted operations require symbolic version preconditions; command requires the runtime-resolved numeric expected version, operation/idempotency ids, one allowlisted resource/action/target, and exact before/after presence;
- stale expected version produces stable non-retryable item abort;
- after every accepted write, reread supplies the next version;
- exact-diff compares all DTO fields and full tag/collection sets: only target membership plus connector-controlled version/modified metadata may differ;
- inject connector mutation of title, creator, venue, arbitrary human tag, unrelated collection, note/attachment hash: each yields `ZOTERO_EXACT_DIFF_VIOLATION` and item abort;
- receipt alone never yields verified; raw headers/body/request payload never escape adapter;
- auth/write rejection is non-retryable; rate-limit uses max three Retry-After delays capped 30s; reads use 0.5/1/2s+jitter; uncertain writes reread before any retry.

### 6.2 SQLite WAL/store suite, AttemptEvidence, and crash matrix

Assert WAL, FULL synchronous, foreign keys, busy timeout, `0700/0600`, unique idempotency, compare-and-set transitions, restart durability, corruption detection, and inability to delete active ownership evidence through retention purge. Assert the exact immutable `apply_authorization` schema/unique constraints/update-delete triggers; mandatory mutation foreign key; exact JCS item/operation arrays; and atomic insertion of authorization, mutations, and their first `planned` events only after all approval/hash/set/digest validation. For every call, assert a single committed transaction contains both the `attempted` transition and `AttemptEvidence` with operation/idempotency ids, prior version, complete sorted tags, complete sorted collection keys, and every preserved-field hash. Inject failure between the two SQL writes and prove rollback plus zero gateway calls.

Fault-inject at every boundary:

1. before `apply_authorization` transaction commit: rollback leaves no authorization, mutation, or `planned`; zero calls and recovery refuses to invent authority;
2. after atomic authorization+mutations+`planned` commit/before first attempt: hard-kill/restart resumes only by exact authorization join/membership; zero prior calls;
3. corrupt/delete/mismatch authorization on restart: FK/immutability blocks ordinary mutation, deliberate corruption detection stops recovery and all calls;
4. before atomic AttemptEvidence/attempted commit: zero calls; normal safe resume from authorized `planned`;
5. after atomic AttemptEvidence/attempted commit/before call: unchanged reread permits same-idempotency retry;
6. during call/timeout: uncertain, reread first, no blind retry;
7. after Zotero write/before reread: desired exact diff reconciles to verified;
8. after reread/before verified commit: repeat reread then verify;
9. after verified commit/before next op: resume with stored chained version;
10. store failure before call: zero external call and fatal stop;
11. store failure after write/reread: uncertain and no next operation;
12. external edit at every gap: abort item, preserve other items, require new preview;
13. desired target present but unrelated diff/version unexplained: uncertain, never ownership;
14. persist attempt, hard-kill the process, discard all in-memory/session preview state, restart, and reconcile using `apply_authorization` plus linked SQLite mutation/evidence rows as the exclusive authority and a fresh gateway reread; result matches the no-crash oracle and performs no blind duplicate write;
15. after a verified app add, inject a human remove/re-add or unrelated external version advance before removal; even with target present, removal is refused and `MANAGED_OWNERSHIP_SUPERSEDED` is durable/reported.
16. after authorization+`planned` commit but before an item's first call, inject a version/fingerprint/root-precondition mismatch: first pending operation becomes `skipped_stale`, all later operations become `aborted`, no AttemptEvidence exists, and the gateway mutation-call count remains zero; restart and identical reapply preserve those terminal events and remain zero-call.

### 6.3 Plan/approval application suite

- Persisted canonical preview reload and rehash succeeds.
- No `planned` row exists before complete validation; successful validation atomically persists immutable authorization plus linked mutations/`planned`, and recovery accepts only those exact approved item/operation memberships.
- Tamper any included field/snapshot/operation/dependency/order and observe zero writes.
- Approval must bind exact plan hash, hash of the canonical `ReviewedDiffProjection`, all 10 sorted keys, every operation id, and fixed confirmation digest after rendering.
- Missing/extra/reordered semantic operation, changed approval hash, or apply-time recomputation is refused.
- Static validation failure creates no authorization/planned rows. Dynamic stale validation occurs after authorization+`planned`: the first pending item operation becomes terminal `skipped_stale` with `ZOTERO_ITEM_STALE`, its dependents become terminal `aborted` with `DEPENDENCY_ABORTED`, approval scope is unchanged, and no 11th item/new operation/call is admitted.
- Restart reruns dynamic validation only for authorized `planned`; it never retries `skipped_stale|aborted`. Identical reapply preserves their event trails and makes zero calls; only a fresh preview/hash/approval can reconsider them.
- The review UI receives only `ReviewedDiffProjection`, renders every field/value exactly and in canonical row order, and its hash oracle equals `SHA256(JCS(projection))`; hidden, summarized, inserted, or recomputed rows fail snapshot/approval tests.

### 6.4 Collection and Obsidian suites

- Root keys resolve uniquely from snapshot; missing/ambiguous/changed root blocks root and matching stage tag. A root already present on the item, including human-added, needs no add/ownership claim; unchanged hash-bound precondition permits the tag operation, while removal/change after preview makes it stale and blocks the tag.
- BySubject mappings use configured existing keys only, support multiple keys, never create/guess.
- Configuration schema and preflight reject each pairwise-equal Look/Review/Dig root combination and every root collision with any BySubject destination (including a destination reused under multiple subjects) as `CONFIG_COLLECTION_ROLE_COLLISION`; preview/apply fail before authorization and all gateway calls. Distinct roots and BySubject destinations remain valid even when display names collide.
- Obsidian opens read-only under configured Efforts; missing root gives a mandatory snapshotted `profiles: []` plus valid digest; malformed profile isolates warning.
- Changing, removing, or injecting any profile after preview changes the project-profile digest/plan hash and refuses apply; canonical set/input ordering alone does not.
- Absolute/`..`/mixed separator/symlink/hardlink/device/non-owner-writable-parent attacks are rejected; no file write exists.

### 6.5 Connector/store security suite

- Secret values resolve only from environment/keyring reference at construction and are absent from config snapshots, hashes, CLI argv, SQLite, reports, logs, exceptions, and fixtures.
- Reject HTTP, unallowlisted host, cross-host redirect, non-loopback local connector, excessive/delete/file/note/create scope, and transport ambiguity.
- Enforce connect/read timeout 5s/15s and exact retry catalog.
- Artifacts/store permissions are `0600`, dirs `0700`; no-follow/exclusive create and same-directory atomic rename are exercised.
- Retention removes eligible >30-day preview/report files, never active provenance, and emits sanitized audit evidence.

## 7. Simulated E2E scenarios

1. `E2E-001 Preview`: 10 diverse fixtures, zero writes, complete snapshots, valid canonical plan/hash.
2. `E2E-002 Approve/apply/reapply`: canonical ReviewedDiffProjection approval atomically creates immutable authorization plus planned mutations; every op persists complete AttemptEvidence before call and verifies after reread; reapply is zero writes.
3. `E2E-003 Advisory boundary`: many `$`/`!` signals at confidence 1.0000, Classification populated, zero advisory operations.
4. `E2E-004 Low confidence`: no #/%/stage/collection movement; only needs-reread.
5. `E2E-005 Managed reclassification`: remove only verified app-owned targets; human state exact.
6. `E2E-006 Stale/external modification`: abort affected item, other items continue, partial report.
7. `E2E-007 Stage transition crash matrix`: fault at each four-operation dependency boundary; reconcile safely.
8. `E2E-008 Missing root`: both root and stage tag absent from plan; BySubject cannot substitute authorization.
9. `E2E-009 Exact-diff violation`: adapter alters unrelated state; item aborts and no next op begins.
10. `E2E-010 Plan/approval tamper`: mutate every schema leaf through generator; zero gateway writes.
11. `E2E-011 Duplicate DOI`: all sharing items blocked; unrelated selected items may preview/apply.
12. `E2E-012 Store/secret/path hostile`: fail closed with no leakage or outside-root mutation.
13. `E2E-013 Kill/restart SQLite-only reconcile`: hard-kill after durable attempt and after external write, restart without in-memory artifacts, reconcile from immutable `apply_authorization` plus linked SQLite rows and reread, and match the expected terminal trail without blind retry.
14. `E2E-014 Ownership superseded`: external advance and human remove/re-add both preserve the present target, block automatic removal, and appear in report/UI.
15. `E2E-015 Profile/diff tamper`: zero-profile digest, populated profile mutation, and ReviewedDiffProjection/UI divergence each cause zero writes.
16. `E2E-016 Authorization crash/root-present`: hard-kill immediately before and after authorization commit proves no unauthorized recovery; a human-present target root produces only the hash-bound stage-tag add and no collection ownership.
17. `E2E-017 Dynamic stale/reapply`: mutate one item after authorization+planned but before its first call; it records one `skipped_stale` plus dependent `aborted` states, performs zero calls for that item, survives restart unchanged, and identical reapply remains zero-write while unaffected items proceed.
18. `E2E-018 Collection-role collision`: exercise all three root/root pairs and each root/BySubject collision; preview and apply fail with `CONFIG_COLLECTION_ROLE_COLLISION`, create no authorization/events, and make zero gateway calls.

## 8. Observability assertions

Counters include selected/read/normalized/classified; confidence outcomes; decisions by namespace/action; planned/attempted/verified/failed/uncertain/skipped-stale/aborted/no-op; missing/ambiguous/stale/external-modification/exact-diff; retry/rate-limit; redaction. Latest-state reconciliation counts each authorized operation exactly once and proves `planned = attempted_nonterminal + verified + failed + uncertain + skipped_stale + aborted`, where `attempted_nonterminal` means the latest durable state is `attempted`; item counters separately reconcile `items_skipped_stale` and `items_aborted`. Static rejection has zero planned/attempted/calls; a dynamically stale item has zero attempted/verified/failed/uncertain/calls and only skipped-stale/aborted terminals.

Canaries placed in token, reference resolution error, connector headers/body, abstract, notes/highlights, PDF bytes/path, vault/store absolute path, and exception internals must be absent from stdout/stderr, structured logs, reports, SQLite text/blob cells, snapshots, and test diagnostics. Metrics contain no title, DOI, citekey, author, abstract, path, token, or payload label.

Every gateway write maps to one immutable matching `apply_authorization`, one authorized `planned`, and one prior atomic complete AttemptEvidence+attempted commit and one eventual verified/failed/uncertain trail. Every removal has unbroken ownership/version-lineage evidence. Every skip has a stable Issue. The review UI is an exact rendering of `ReviewedDiffProjection`; other human-readable reports are projections only.

## 9. Real Zotero batch-of-10 protocol

### Preconditions

All gates S1–S4 pass; chosen connector behavior is checked against current official documentation; recovery export exists; secret/endpoint/scope/permission preflight passes; exactly 10 unique regular-item keys are selected; collection/config/ruleset/taxonomy snapshots are persisted.

### Preview and approval

- Exactly 10 outcomes; zero writes and unchanged versions.
- Rules, aliases, credibility, confidence, stage cross-product, decisions, dependencies, snapshots, and complete exact diff are visible.
- `$`/`!` have no add/remove; every writable tag is `#|%|@`; every collection exists.
- Missing critical root means neither stage root nor tag operation.
- Every removal references verified ownership; first run expects none.
- Human confirms the canonical prompt bound to plan hash, complete rendered-diff hash, all keys, and all operation ids; generated ApprovalEvidence revalidates.

### Apply/post-apply

- Rehash preview and validate approval before connector access; atomically persist the immutable authorization and linked planned mutations before the first attempt, and recover only through that authorization.
- Each item's first operation resolves `PreviewVersion(v)`; later operations resolve `VerifiedVersionOf(operation_id)` from SQLite, materialize the integer only in the command, durably persist AttemptEvidence+attempted, write, reread exact diff, and verify.
- Stale/external/diff failure aborts only affected item and never blind-retries a write.
- Final counters match Zotero snapshots and SQLite events; excluded state and Obsidian hashes remain unchanged.
- Reapply performs zero writes; fresh preview shows fixed point and no unowned removal.

### Stop rule

Stop after verified processing outcomes for these 10 keys. Never admit an 11th key or whole-library processing under this approval. Any remediation requires a new preview/hash/approval.

## 10. Static and execution verification

Implementation selects the repository-standard Python runner, but must execute schema/golden, unit/property, integration/fault-injection, simulated E2E, observability/security, typecheck, lint/format, and build checks. The real connector suite is separately marked and never runs in ordinary CI or without explicit local configuration. No real token or personal raw payload enters fixtures.

## 11. Traceability

| Requirement | Primary evidence |
|---|---|
| writable tags only `#/%/@`; `$`/`!` advisory | `U-SCHEMA-009/010`, alias negatives, `U-MUT-007`, `E2E-003` |
| normative plan/apply schemas + canonical hash/approval | section 3 goldens, 6.3, `E2E-010` |
| frozen rules/aliases/credibility/confidence | sections 4.2–4.5 |
| Dig requires Look + Review + 5/5 | section 4.3 full cross-product |
| immutable apply authorization before planned; SQLite atomic AttemptEvidence+attempted-write-reread-verified and authorization-only recovery | `U-SCHEMA-025`, `G-PLAN-016`, section 6.2 crash matrix, `E2E-007/013/016` |
| symbolic version chain/external modification abort | `U-SCHEMA-019/020`, property 6, port/store suites, `E2E-006` |
| stage root/tag dependency, root-already-present no-op/ownership rule, and missing-root block | `U-MUT-008..011`, collection suite, `E2E-008/016` |
| Zotero DTO exact diff/human preservation | section 6.1, property 8, `E2E-009` |
| duplicate DOI policy and closed error retries | normalization, port tests, `E2E-011` |
| secrets/endpoint/scope/timeouts/permissions/retention/path safety | sections 6.5, 8, `E2E-012` |
| managed-only removal/idempotency | mutation properties, `E2E-002/005`, real post-apply |
| exact 10-item bound | plan schemas, approval suite, real stop rule |
| project-profile snapshot/digest including zero profiles | `U-SCHEMA-021`, `G-PLAN-013`, collection/Obsidian suite, `E2E-015` |
| deterministic paper kind from enumerated Zotero types and `%narrative-review`/`%systematic-review`; ambiguity blocks Dig | normalization kind matrix, `U-SCHEMA-022`, `U-RULE-007..009` |
| total match-kind/S weights and explicit credibility allowlists | `U-SCHEMA-026`, sections 4.2, 4.4, 4.5 |
| ReviewedDiffProjection exact UI/hash oracle | `U-SCHEMA-023`, `G-PLAN-015`, approval suite, `E2E-015` |
| external advance/human re-add supersedes removal ownership | `U-MUT-015/016`, crash case 15, `E2E-014` |
| static versus dynamic validation; terminal call-free stale/abort recovery and counters | `U-SCHEMA-028`, crash case 16, section 6.3, `E2E-017`, observability assertions |
| pairwise-distinct stage roots disjoint from BySubject destinations | `U-SCHEMA-027`, collection suite, `E2E-018` |

## 12. Implementation handoff exit criteria

- Every normative schema and snapshot has generated JSON Schema plus reviewed golden.
- Per-field tamper traversal reports 100% included-leaf coverage.
- Full rule cross-product and exact confidence vectors are fixtures before classifier implementation.
- Zotero fake and real adapter share one contract suite; SQLite crash tests run with real process termination, not only mocked exceptions, and restart reconciliation uses the immutable `apply_authorization` plus linked SQLite rows as the exclusive persisted authority.
- No live apply occurs until independent verifier confirms plan hash, ApprovalEvidence, security preflight, and S1–S4 evidence.
- Any skipped check is a blocker, not a conditional oracle.

## 13. Consensus improvement record

### Iteration 2 — Architect rereview integrated

- Added atomic complete `AttemptEvidence` and hard-kill/restart reconciliation tests grounded exclusively in SQLite persistence.
- Replaced predicted future versions with hash-bound symbolic preconditions and runtime-only numeric command versions.
- Added ownership-lineage invalidation for every external version advance and explicit human re-add protection/reporting.
- Added mandatory project-profile snapshot/digest coverage for both zero and populated profiles.
- Added deterministic `paper_kind` tests with Dig blocked on ambiguity.
- Made `ReviewedDiffProjection` the exact schema, UI-rendering, and approval-hash oracle.
- Narrowed byte-identity claims to hashable projections/deterministic ids and aligned confidence fixtures with decimal-string schemas.

### Iteration 3 — Architect final P0/P1 closure

- Added schema, golden, FK/trigger, tamper, and hard-kill tests for immutable `apply_authorization`; proved `planned` cannot predate validation and recovery cannot proceed without exact authorization membership.
- Replaced legacy generic review-tag fixtures with `%narrative-review`/`%systematic-review`, enumerated original versus support/non-paper Zotero types, and corrected Dig cases to name the applicable checklist.
- Totalized all eight `match_kind` weights, added recency/venue/author/type confidence vectors, and made generic valid ORCID non-credible unless explicitly author-allowlisted.
- Added the human-present stage-root case: no redundant add or ownership claim, direct tag add only under unchanged hash-bound precondition.
- Removed duplicate headings and aligned test identifiers, E2E numbering, traceability, and crash boundaries.

### Iteration 4 — Critic state/preflight closure

- Added schema, store, restart, reapply, counter, and E2E coverage for static validation versus dynamic item validation and terminal pre-call `skipped_stale|aborted` states with zero external calls.
- Added exhaustive root/root and root/BySubject collision tests with stable `CONFIG_COLLECTION_ROLE_COLLISION`, fail-closed preview/apply behavior, and zero authorization/events/calls.


## 14. Terminal Ralplan consensus handoff

**Terminal status:** `complete` — planning only; this artifact does not authorize implementation.

**Required review order and evidence:**
1. Architect review completed after Planner revisions: **APPROVE**.
2. Critic gate completed after the approving Architect review: **APPROVE**.
3. The deliberate-mode pre-mortem and expanded unit, integration, E2E, crash/recovery, observability, and 10-paper real-lot validation plan remain required acceptance evidence.

**Execution boundary:** begin only through an explicit subsequent execution workflow. The recommended durable path is `$ultragoal` with `$team` where parallel delivery is warranted; `$ralph` remains an explicit single-owner fallback only.

### Deployment-binding regression cases

- The configured display paths `.ToLook`, `.ToRevise`, and `.ToDig` resolve to distinct snapshot keys; the planner maps `look/review/dig` only to those keys plus `@look/@review/@dig`, respectively.
- Explicit user selection accepts exactly ten sorted keys only when each is a regular paper in `.ToLook` with publication year `2026`, and excludes children and duplicate-DOI candidates; eleven eligible candidates never trigger an automatic or first-ten selection.
- Any other collection membership remains unchanged unless it is an explicitly configured existing `BySubject` destination.
