# PRD and Software Design — Local Zotero/Obsidian Paper Triage

**Status:** Ralplan terminal — consensus approved; planning complete; no implementation authorized
**Mode:** `$ralplan --deliberate`
**Context:** `.omx/context/zotero-obsidian-paper-triage-20260809T134412Z.md`
**Companion test spec:** `.omx/plans/test-spec-zotero-obsidian-paper-triage.md`

## 1. Executive outcome

Build a local-first, deterministic paper-triage application that reads normalized metadata for an explicitly selected real batch of 10 Zotero papers, produces a reviewable dry-run plan, and applies only high-confidence, allowlisted tags and collection memberships. Every applied change is recorded as a managed mutation so reruns are idempotent and reclassification can undo only the application's own prior work.

The MVP must be useful without Obsidian project data. A read-only `Efforts` adapter and `ProjectProfile` contract preserve the future integration boundary, but no Obsidian file is modified.

## 2. Product constitution (non-negotiable invariants)

1. **Human data sovereignty.** Never remove or overwrite metadata unless the exact prior mutation is recorded as application-managed.
2. **Plan before apply.** Every live write is derived from a persisted dry-run plan with item version evidence; no classifier calls the Zotero adapter directly.
3. **Confidence before automation.** Full automated mutation requires `confidence >= 0.85`. Lower confidence preserves stage/collections and can add only `@needs-reread`. Automatic tag writes are limited, without exception, to canonical `#`, `%`, and `@` tags; `$` and `!` are classification-only signals and can never produce `add`/`remove`, even at confidence `1.0`.
4. **Determinism and auditability.** Identical normalized input, taxonomy/rule version, project-profile snapshot, and run date produce byte-identical hashable projections and deterministic identifiers/hashes. Trace and presentation fields need not be byte-identical.
5. **Least privilege and data minimization.** Read only required Zotero fields, write only allowlisted tags/collections, keep Obsidian read-only, and never log secrets, raw PDFs, highlights, note bodies, or raw connector payloads.
6. **Safe failure.** Ambiguity, missing collection mappings, stale item versions, partial writes, or validation errors fail closed for the affected item and appear in a structured report.

## 3. Scope

### 3.1 MVP in scope

- Explicit selection and validation of exactly 10 Zotero regular-item papers.
- Metadata normalization for citekey, title, authors, year, DOI, abstract, collection memberships, tags, and PDF attachment presence/reference metadata.
- Deterministic subject, method, evidence, project-use, and stage classification; `$` project-use and `!` quality/evidence outputs are advisory only.
- Dry-run preview of all additions/removals and safety blockers.
- High-confidence application of managed tags, root stage collection, and all matching existing `BySubject` subcollections.
- Low-confidence addition of `@needs-reread` without moving stage/collections.
- Durable mutation manifest with before/after evidence and per-operation status.
- Idempotent rerun and managed-only reclassification.
- Structured run report and redacted logs.
- Read-only `ProjectProfile` discovery interface for Obsidian `Efforts`; zero profiles is a valid MVP state.

### 3.2 Explicit non-scope

- Creating collections or `BySubject` subcollections.
- Editing/creating Zotero notes, Obsidian notes, highlights, PDFs, Concepts, MOCs, Zettelkasten, or ideas.
- Uploading content to a remote LLM or service.
- Parsing raw PDF text for the MVP.
- General bibliometric reputation lookup or web enrichment.
- Automatic processing of the whole Zotero library.
- Free-form LLM decisions or direct LLM-to-Zotero writes.

## 4. Users and primary workflows

### 4.1 Primary user

A researcher who owns the Zotero library and Obsidian vault, wants reproducible triage, and expects human-authored organization to remain authoritative.

### 4.2 Workflow A — preview

1. User supplies an explicit list of 10 Zotero item keys and configuration.
2. System validates credentials without displaying them and reads only required metadata.
3. System normalizes each item and snapshots the Zotero item version.
4. System loads the versioned taxonomy/rules and optional project profiles.
5. System emits `Classification`, desired tag/collection decisions, warnings, and a mutation plan.
6. System persists a sanitized `RunReport` and preview artifact; Zotero remains unchanged.

### 4.3 Workflow B — apply approved plan

1. User invokes apply using the exact preview/run identifier.
2. System statically verifies plan/schema hashes, configuration/rule snapshots, item and operation sets, rendered diff hash, dependency/order integrity, collection-role topology, and confirmation digest without performing item mutation calls.
3. Only after static validation, one SQLite transaction durably inserts immutable `apply_authorization`, all linked `managed_mutation` identities, and their initial `planned` events. A crash before commit leaves none; a crash after commit recovers only through this row.
4. Immediately before an item's first external call, dynamic validation rereads its current Zotero version/fingerprint and collection prerequisites. A stale/mismatched item records terminal `skipped_stale` for its first pending operation and `aborted` for dependents; the rest may proceed independently and the stale item makes zero mutation calls.
5. For each operation, one SQLite transaction durably persists the complete pre-call `AttemptEvidence` and transitions `planned -> attempted` before the Zotero call.
6. System writes through the narrow Zotero port, rereads the entire allowed item snapshot, verifies the exact diff and chained item version, then durably records `verified` before starting the dependent operation.

### 4.4 Workflow C — reclassify

1. System reads current data plus prior successful managed mutations for the item.
2. It computes the new desired state.
3. It may remove only active managed additions that are no longer desired.
4. It never removes equivalent human metadata that predates management or a user-added membership not linked to a managed mutation.
5. Missing target collections produce warnings and no collection creation.

## 5. RALPLAN-DR — deliberate decision record

### 5.1 Principles

1. Preserve human-owned state by default.
2. Separate pure classification from side-effectful mutation.
3. Make every mutation attributable, replay-safe, and reversible.
4. Prefer deterministic, versioned rules over opaque inference.
5. Fail closed at trust boundaries and expose actionable evidence.

### 5.2 Top decision drivers

1. **Zotero safety:** a defect must not silently destroy or overwrite library organization.
2. **Auditability/reproducibility:** every classification and mutation must be explainable from versioned inputs.
3. **MVP delivery:** the architecture must support a real 10-paper run without requiring PDF parsing, remote services, or a full Obsidian integration.

### 5.3 Options considered

#### Option A — Direct read/classify/write pipeline

**Approach:** process each item and immediately write the resulting tags/collections.

**Pros**
- Lowest implementation effort and shortest command path.
- Fewer persisted artifacts.

**Cons**
- Classification bugs immediately become data mutations.
- Hard to review the complete batch before writes.
- Partial failures make rollback and provenance ambiguous.
- Weak separation between pure rules and connector behavior.

**Disposition:** rejected because it violates “plan before apply” and makes safe real-library acceptance difficult.

#### Option B — Two-phase plan/apply with managed mutation ledger (recommended)

**Approach:** generate an immutable, hashed dry-run plan from normalized/versioned items; apply through a separate command that verifies optimistic concurrency and records each mutation.

**Pros**
- Reviewable before any live write.
- Enables exact managed-only reversibility and idempotency.
- Supports stale-version detection and partial-failure recovery.
- Keeps deterministic domain tests independent of Zotero.

**Cons**
- More contracts and state transitions.
- Requires local artifact retention and corruption handling.
- Apply must reconcile plans with current item versions.

**Recommendation:** choose this option; its additional machinery directly addresses the dominant safety driver.

#### Option C — Shadow tags only; no collection mutation in MVP

**Approach:** write classification tags but report desired collections for manual action.

**Pros**
- Smaller write surface.
- Simplest rollback semantics.

**Cons**
- Does not meet the closed requirement to manage configured stage collections `.ToLook`/`.ToRevise`/`.ToDig` and existing `BySubject` collections.
- Leaves the principal workflow half-manual and weakens the real-batch proof.

**Disposition:** not viable for the requested MVP, but retained as an emergency degradation mode if collection writes cannot be safely verified.

### 5.4 Architectural antithesis and synthesis

**Strongest counterargument:** for ten papers, the mutation ledger and two-phase protocol may be more complex than manual tagging, while optimistic concurrency cannot make a multi-item Zotero run truly transactional.

**Tradeoff tension:** safety/audit depth increases local state and operational complexity; simplicity reduces the evidence needed to trust a run against a real library.

**Synthesis:** use an append-only SQLite WAL event ledger, scope atomicity to each durable transition and item rather than pretending Zotero provides batch transactions, and make dry-run the default. The MVP avoids a general workflow engine while retaining crash-testable provenance.

## 6. Modular architecture

```text
CLI / local entrypoint
  -> Application services (preview, apply, reclassify, report)
      -> Normalization (pure)
      -> Classification policy (pure, deterministic)
      -> Mutation planner (pure diff + ownership rules)
      -> Ports
          -> Zotero gateway (read/write allowlist)
          -> Project profile source (read-only)
          -> Mutation/report store (local durable state)
      -> Adapters
          -> Zotero connector
          -> Obsidian Efforts reader (optional/read-only)
          -> SQLite WAL mutation store + canonical JSON preview/report store
```

### 6.1 Modules and responsibilities

| Proposed module | Responsibility | Forbidden responsibility |
|---|---|---|
| `domain/models.py` | Pydantic contracts and invariants | connector calls |
| `domain/taxonomy.py` | canonical tags, aliases, namespace validation, versions | fuzzy side effects |
| `normalization/paper.py` | connector DTO -> canonical `Paper` | classification |
| `classification/rules.py` | subject/method/evidence signals and reasons | Zotero writes |
| `classification/scoring.py` | Look/Review/Dig gates | confidence fabrication |
| `classification/confidence.py` | evidence coverage/conflict confidence | stage mutation |
| `application/plan_run.py` | orchestrate reads and create immutable plan | live writes |
| `application/apply_run.py` | verify plan, enforce policy, invoke gateway, verify writes | reclassify from raw payload |
| `application/reclassify.py` | managed-only diff against ledger | remove unmanaged state |
| `ports/zotero.py` | narrow read/write protocol | domain policy |
| `ports/projects.py` | `ProjectProfile` discovery protocol | note modification |
| `ports/mutation_store.py` | append/query managed mutation state | secret storage |
| `adapters/obsidian_efforts.py` | safe, read-only parse under configured Efforts root | file writes or traversal outside root |
| `application/reporting.py` | redacted structured reports and counters | raw payload logging |

### 6.2 State machines and external-write boundary

Run state is `PREVIEWED -> APPLYING -> {APPLIED, PARTIAL, FAILED}`. Batch atomicity is not promised; each item is an independently aborted unit.

Validation has two explicit phases. **Static plan/approval validation** runs before durable authorization and proves schema validity, all hashes/digests, exact approved sets, dependency/order integrity, configuration invariants, and collection-role topology; failure creates no `apply_authorization`, mutation, or event and makes zero Zotero mutation calls. **Dynamic item validation** runs only after the immutable authorization plus its linked `planned` events commit and immediately before the first external call for each item; it rereads the item and collection snapshot prerequisites and resolves the first symbolic version precondition. A version/fingerprint/root-membership mismatch transitions that item's first pending operation `planned -> skipped_stale`; every later dependency-blocked operation transitions `planned -> aborted`. Both are terminal, carry stable issues (`ZOTERO_ITEM_STALE` or the more specific mismatch plus `DEPENDENCY_ABORTED`), and guarantee zero Zotero mutation calls for that item.

Operation state is append-only and exact: `planned -> attempted|skipped_stale|aborted`, `attempted -> verified|failed|uncertain`, and `uncertain -> verified|failed` only through reconciliation. There is no durable `applied` state because a successful connector response is not proof of state; only reread plus exact-diff validation yields `verified`. No `managed_mutation` row or `planned` event may exist until static plan/approval validation succeeds and the same transaction durably commits its matching immutable `apply_authorization`. Every later transition and every recovery query must join the mutation to that authorization; a preview, approval object, or in-memory session alone is never recovery authority. Startup recovery reruns dynamic validation for authorized `planned` operations, never calls Zotero for terminal `skipped_stale|aborted`, and never promotes either terminal state. Identical reapply preserves verified and skipped/aborted event trails and performs zero writes; retrying a stale/aborted item requires a fresh preview, plan hash, and approval.

For each item, operations form a dependency DAG and execute in the canonical order defined by `PlannedOperation.sequence`. Before every external call, one `BEGIN IMMEDIATE` transaction persists `AttemptEvidence` and commits `attempted`. `AttemptEvidence` contains the operation/idempotency ids and the complete safe pre-call `ZoteroItemSnapshot`: item version, full tag set, full collection-key set, and hashes of every preserved field (including bibliographic, creator, note-metadata, and attachment-metadata projections); raw sensitive bodies remain forbidden. After the call the gateway rereads the same full snapshot projection, checks the symbolic version chain and exact allowed diff, and only then commits `verified`. Any version advance not directly accounted for by the immediately preceding app-verified operation invalidates the item; the remaining operations are aborted and require a new preview.

For an initial stage assignment, an absent configured root collection is added before its matching `@` tag. If the target root is already present, including when placed there by a human, the plan emits no root add and claims no collection ownership; the hash-bound item snapshot and the stage-tag operation's symbolic version precondition are sufficient to require that root membership still be present at execution, so the matching `@` tag may be added directly. For a stage transition, the closed dependency chain is: add target root -> add target `@` tag -> remove prior app-owned `@` tag -> remove prior app-owned root. This deliberately prefers a temporary duplicate stage over a temporary loss of all stage evidence. Any failure stops the chain and reconciliation resumes only from reread state. If the target root is missing, ambiguous, or changed since preview, both the root operation and matching stage-tag operation are absent from the plan and `COLLECTION_ROOT_BLOCKS_STAGE` is emitted. BySubject operations never authorize a stage operation.

## 7. Canonical contracts (Pydantic/JSON design)

### 7.1 Common conventions

- Pydantic v2, `extra="forbid"`, strict validation, UTC RFC3339 timestamps, Unicode NFC, and explicit enum strings.
- Persisted models carry `schema_version`, `taxonomy_version`, `ruleset_version`, and `config_snapshot_hash` where applicable.
- Decimal confidence values serialize as fixed four-decimal strings; floating-point JSON numbers are forbidden in hashable artifacts.
- Persisted sets are sorted unique arrays; nulls are retained unless explicitly hash-excluded.
- Persist only normalized/derived data, never connector payloads, secrets, PDF bytes, note/highlight bodies, or absolute vault paths.
- `PreviewPlan`, `MutationPlan`, `PlannedItem`, `PlannedOperation`, `ApplyRequest`, and `ApprovalEvidence` below are normative apply-boundary schemas, not suggestions.

### 7.2 `Paper`

Canonical, immutable classification input.

| Field | Type | Required | Invariant |
|---|---|---:|---|
| `schema_version` | literal `"1.0"` | yes | exact |
| `library_id` | constrained string | yes | redacted identifier allowed in reports |
| `item_key` | string | yes | Zotero key pattern, non-secret |
| `item_version` | int >= 0 | yes | optimistic concurrency token |
| `raw_item_type` | closed enum from section 10.1 plus `unknown` | yes | exact Zotero item-type discriminator retained for deterministic kind derivation |
| `item_type_class` | enum `original_candidate|support_or_nonpaper|unknown` | yes | child `attachment|note|annotation` never reach `Paper` |
| `paper_kind` | enum `original|review|ambiguous` | yes | deterministic raw Zotero type plus `%narrative-review`/`%systematic-review` tag derivation below; `ambiguous` blocks Dig |
| `citekey` | string/null | yes | trimmed; canonical ASCII comparison form stored separately if needed |
| `title` | string, 1..1000 | yes | NFC, collapsed whitespace |
| `authors` | list[`Author`] | yes | stable input order; may be empty with warning |
| `year` | int/null | yes | 1000..run_year+1 or null |
| `doi` | string/null | yes | lowercase, strips `doi:`/URL, validated shape |
| `venue` | string/null | yes | NFC/collapsed; normalized comparison form used for credibility allowlist |
| `abstract` | string/null | yes | normalized; max persisted size configured; never PDF-derived in MVP |
| `collections` | set[string] | yes | Zotero collection keys, not display names |
| `tags` | set[string] | yes | exact current tags after NFC/trim; preserve display case |
| `pdf_attachments` | list[`AttachmentRef`] | yes | key/title/content-type/link-mode only; no path/bytes/log body |
| `source_fingerprint` | SHA-256 string | yes | hash of classification-relevant normalized fields |
| `normalization_warnings` | list[`Issue`] | yes | stable codes, sanitized context |

Nested `Author`: `family`, `given`, `literal`, `orcid` (all nullable except at least one name representation).
Nested `AttachmentRef`: `attachment_key`, `content_type`, `link_mode`, `available: bool`; no filesystem path in reports.

### 7.3 `Classification`

| Field | Type | Invariant |
|---|---|---|
| `decision_id` | UUID | trace-only; excluded from plan hash |
| `paper_key` | string | equals input item key |
| `ruleset_version` / `taxonomy_version` | string | exact snapshot versions |
| `run_date` | ISO date | fixes recency boundary |
| `subjects` / `methods` | sorted canonical `#` / `%` | catalog members only |
| `project_uses` / `quality_flags` | sorted canonical `$` / `!` | advisory; never writable |
| `proposed_stage` | `look|review|dig|null` | Dig requires Look + Review >=3/6 + profile 5/5 |
| `look_triggers` | list[`CriterionResult`] | frozen trigger ids in section 9 |
| `review_criteria` | exactly 6 results | frozen definitions in section 10 |
| `dig_profile` / `dig_criteria` | profile/null + 5 results/empty | all five pass for Dig |
| `confidence` | fixed decimal string | exact formula in section 10.2 |
| `confidence_components` | coverage/specificity/agreement/completeness | fixed decimals |
| `evidence` / `warnings` | lists | sanitized, stable ids/codes |
| `outcome` | `high_confidence|needs_reread|unclassifiable` | threshold-derived |

`CriterionResult` = `criterion_id`, `status: pass|fail|unknown|conflict`, `reason_code`, sorted `evidence_refs`. `EvidenceRef` = `evidence_id`, `source_field`, closed `match_kind`, bounded `normalized_excerpt`, `value_hash`. `match_kind` is exactly `existing_canonical_tag|exact_rule_phrase|frozen_alias|project_profile_exact|recency_window|venue_allowlist_exact|author_allowlist_exact|zotero_type_allowlist_exact`; every positive evidence reference used by a selected subject/method or a passing Look/Review/Dig result must use one of these values, and synthetic criterion-to-criterion references are forbidden (reuse the underlying evidence ids instead). A required unknown/conflict or `paper_kind=ambiguous` prevents Dig. `$` and `!` values can support classification but cannot cross the mutation boundary.

### 7.4 `TagDecision`

| Field | Type | Invariant |
|---|---|---|
| `tag` / `namespace` | string / enum | canonical and prefix-consistent |
| `action` | `add|remove|keep|skip` | `$`/`!` permit only `keep|skip` |
| `managed` | bool | true only for writable `#|%|@` add/remove |
| `confidence` | fixed decimal | inherited or decision-specific |
| `reason_codes` / `evidence_refs` | sorted lists | stable and traceable |
| `managed_mutation_id` | UUID/null | mandatory for remove |
| `blocked_by` | issues | required for safety skip |

Normative policy:

1. The only writable tag namespaces are `#`, `%`, and `@`.
2. `$` and `!` are advisory. Their action is `keep` when present or `skip` when absent; `add`/`remove` are schema-invalid at every confidence, including `1.0000`.
3. At `confidence >=0.8500`, desired canonical `#`, `%`, and eligible `@` tags may be added; removal requires an active verified managed addition.
4. Below threshold, only absent `@needs-reread` may be added; all other tags and all collections remain `keep|skip`.
5. Human-preexisting canonical tags remain human-owned.

### 7.5 `CollectionDecision`

| Field | Type | Invariant |
|---|---|---|
| `collection_key` | string/null | null only when expected target is missing |
| `collection_path` | list[string] | sanitized display path |
| `role` | `stage|by_subject` | only writable roles |
| `subject_tag` | canonical `#`/null | mandatory for `by_subject` |
| `action` | `add|remove|keep|skip|missing` | `missing` never writes |
| `confidence` | decimal [0,1] | threshold enforced |
| `managed_mutation_id` | UUID/null | mandatory for remove |
| `reason_codes` | non-empty list[string] | stable |
| `blocked_by` | list[`Issue`] | missing/stale/low-confidence details |

All matching existing `BySubject` subcollections are added; mapping is one canonical subject to zero or more collection keys. A zero match yields `COLLECTION_BY_SUBJECT_MISSING`, not creation.

### 7.6 `ManagedMutation`, normative plan schemas, and hashing

SQLite is mandatory for MVP; JSONL is not an alternative. Initialization sets `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=FULL`, `PRAGMA foreign_keys=ON`, and a configured busy timeout. The database directory/file must be owner-only (`0700`/`0600`) and pass path/symlink containment checks.

`apply_authorization` is an immutable SQLite authority table. Its normative columns are:

| Column | SQLite type/constraint | Meaning |
|---|---|---|
| `authorization_id` | `TEXT PRIMARY KEY` | approval id; immutable identity |
| `schema_version` | `TEXT NOT NULL` | exact authorization schema version |
| `preview_id` | `TEXT NOT NULL` | trace link to the rendered preview |
| `plan_hash` | `TEXT NOT NULL UNIQUE`, lowercase SHA-256 check | exact validated mutation plan |
| `reviewed_diff_hash` | `TEXT NOT NULL`, lowercase SHA-256 check | exact rendered canonical diff |
| `approved_item_keys_json` | `TEXT NOT NULL`, `json_valid` | JCS canonical sorted unique array; exact approved item set |
| `approved_operation_ids_json` | `TEXT NOT NULL`, `json_valid` | JCS canonical execution-ordered unique array; exact approved operation set |
| `confirmation_digest` | `TEXT NOT NULL UNIQUE`, lowercase SHA-256 check | exact formula from `ApprovalEvidence` |
| `approval_method` | `TEXT NOT NULL CHECK (... = 'local_interactive')` | closed method |
| `approved_at` | `TEXT NOT NULL` | validated UTC RFC3339 approval time |

The store validates canonical JSON bytes, uniqueness, exact set equality, and digest syntax before insertion; SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers always abort. The row is inserted only after static schema validation, complete canonical diff rendering, recomputation of all snapshot/operation/diff/plan digests, exact approved-set equality, collection-role topology validation, and confirmation-digest validation. Current-item versions/fingerprints and runtime collection prerequisites are deliberately excluded from this static phase and are checked dynamically after `planned` persistence and before the affected item's first call. A single `BEGIN IMMEDIATE` transaction inserts the authorization row plus the authorized `managed_mutation` identities and their initial `planned` events; therefore neither a mutation nor `planned` can predate validated durable authorization. Identical reapply resolves the existing row; any field disagreement is fatal.

`managed_mutation` stores immutable identity: `mutation_id`, deterministic `idempotency_key`, `run_id`, mandatory `authorization_id` foreign key, `plan_hash`, `operation_id`, item/resource/action/target, ownership basis, before/desired presence, and symbolic version precondition. `mutation_event` appends `event_id`, mutation id, exact from/to status, observed version, timestamp, and sanitized error. `attempt_evidence` stores, per attempt, the operation/idempotency ids and the complete safe pre-call snapshot (version, all tags, all collection keys, and preserved-field hashes). Unique idempotency and compare-and-set transitions prevent duplicates. Legal transitions are exactly `planned -> attempted|skipped_stale|aborted`, `attempted -> verified|failed|uncertain`, and `uncertain -> verified|failed`; `skipped_stale|aborted` are terminal and can never have `AttemptEvidence`. Only verified app additions with an unbroken app-verified version lineage establish removal ownership.

Before a Zotero call, a `BEGIN IMMEDIATE` transaction atomically inserts `AttemptEvidence` and appends `attempted`; failure of either write rolls back both and guarantees zero Zotero calls. After reread/exact-diff verification, a second transaction appends `verified` with `item_version_after`; no dependent operation starts before that commit. Startup recovery rejects any mutation lacking a matching immutable authorization whose hashes and approved item/operation membership agree exactly; it never reconstructs authority from an unpersisted `ApplyRequest` or preview alone.

#### Normative plan/apply schemas

`PreviewPlan` contains `schema_version`, trace-only `preview_id` and `created_at`, `run_date`, exactly 10 sorted `selected_item_keys`, `library_scope`, `config_snapshot`, `collection_snapshot`, `project_profile_snapshot`, `ruleset_snapshot`, `taxonomy_snapshot`, sorted `items: list[PlannedItem]`, `reviewed_diff_projection`, `plan_hash`, and sanitized issues. `project_profile_snapshot` is always present, contains a sorted list of normalized `ProjectProfile` values (including the valid empty list for zero profiles), and carries a digest over that list. `MutationPlan` is the hash-bound mutation-bearing projection of `PreviewPlan`: every hash-included field, no approval or runtime state.

`PlannedItem` contains `item_key`, source fingerprint, preview item version, hashable classification projection, sorted decisions, ordered operations, and blockers. `PlannedOperation` contains deterministic `operation_id`, integer `sequence`, sorted `depends_on`, `resource_type: tag|collection`, `action: add|remove`, target, expected/desired presence, `version_precondition`, removal ownership id, and reason/evidence refs. `version_precondition` is a discriminated symbolic union: only the first operation may use `PreviewVersion(version=<PlannedItem.preview_item_version>)`; every subsequent operation must use `VerifiedVersionOf(operation_id=<immediately preceding operation>)`. A future numeric expected version is forbidden in the persisted preview; only `ZoteroMutationCommand.expected_version` is materialized at runtime from the satisfied symbolic precondition. Writes to `$`/`!`, collection creation, unowned removal, or cross-item dependencies are schema-invalid.

`ReviewedDiffProjection` is the sole approval/UI diff oracle. It is a canonical ordered array derived without free text by sorting items by `item_key` and retaining operations in canonical execution order. Each row has exactly these fields in this schema order: `item_key`, `operation_id`, `sequence`, `resource_type`, `action`, `target`, `before_present`, `after_present`, `ownership_mutation_id`, `reason_codes`, `evidence_refs`, `version_precondition`. Arrays inside a row use their schema-defined canonical order; nullable ownership is retained. The review UI must render every row and every value from this projection exactly, with no hidden, inserted, summarized, or recomputed operation. `reviewed_diff_hash = SHA256(JCS(ReviewedDiffProjection))`; UI snapshot tests use that digest as the oracle.

`ApplyRequest` contains only `schema_version`, `preview_id`, `plan_hash`, and `approval: ApprovalEvidence`. `ApprovalEvidence` contains `approval_id`, `approved_plan_hash`, `approved_at`, `approval_method: local_interactive`, exactly the plan's sorted 10 `approved_item_keys`, every `reviewed_operation_id` in canonical order, `reviewed_diff_hash = SHA256(JCS(ReviewedDiffProjection))`, and `confirmation_digest = SHA256(UTF8("APPLY\n" + approved_plan_hash + "\n" + reviewed_diff_hash + "\n" + join(approved_item_keys,"\n") + "\n" + join(reviewed_operation_ids,"\n")))`. It contains no identity claim, token, or secret.

Apply is authorized only when the persisted preview passes static validation; all snapshot digests, operation ids, and plan hash recompute; `ApplyRequest.plan_hash == ApprovalEvidence.approved_plan_hash == PreviewPlan.plan_hash`; and approved item/operation sets equal exactly. Approval follows rendering the complete canonical diff. It authorizes no recomputation, extra operation, target substitution, collection creation, or namespace expansion. Dynamic stale detection occurs after authorized `planned` persistence and before an item call, producing terminal `skipped_stale|aborted` events rather than silently shrinking approval scope. Reapply of the identical approval is a zero-write report replay for all terminal operations; a fresh preview/approval is required to reconsider skipped/aborted work.

#### Canonical hash recipe

1. Validate `PreviewPlan`; form `MutationPlan` by recursively excluding exactly `plan_hash`, `preview_id`, `created_at`, every `decision_id`, human-readable report text, approval evidence, runtime counters/status/events/timestamps, secret values/references, and non-blocking presentation-only issues. Nothing else is auto-excluded.
2. Include sanitized effective config by value (library scope, writable namespaces, threshold, timeout/retry values, collection keys, credible venues and credible authors), the complete selected collection key/path/version tree, the complete project-profile snapshot even when its profile list is empty, complete ruleset, and complete taxonomy/aliases. Each snapshot includes a SHA-256 digest that must match its value.
3. Serialize RFC 8785 JCS-compatible UTF-8 JSON: NFC strings, lexicographic object keys, no whitespace, fixed decimal strings, and arrays sorted by schema key (`item_key`; namespace+tag; sequence+operation id; collection key/path; canonical+alias). Dependency arrays retain declared canonical order.
4. `operation_id = SHA256(JCS(operation fields excluding only operation_id and runtime state))`; the symbolic `version_precondition` is included. After inserting ids, derive `ReviewedDiffProjection`, compute its digest, then compute `plan_hash = SHA256(JCS(MutationPlan))`, lowercase hex.
5. Recompute at load and immediately before apply. Any changed included field, missing snapshot, digest mismatch, or id mismatch is fatal tampering; merely different noncanonical input ordering canonicalizes to the same hash.

#### Canonical operation order

Items sort by item key. Within each item: obsolete owned `#/%` removals; `#/%` additions; BySubject removals then additions by key; stage dependency chain from section 6.2; eligible `@needs-reread` change. All operations serialize per item for an unambiguous version chain; each operation depends on the preceding operation plus its semantic dependencies.

### 7.7 `RunReport`

| Field | Type | Invariant |
|---|---|---|
| `schema_version` | literal `"1.0"` | exact |
| `run_id` | UUID | unique |
| `mode` | `preview|apply|reclassify` | explicit |
| `status` | `success|partial|failed` | counter-derived |
| `started_at` / `finished_at` | UTC timestamp | monotonic |
| `ruleset_version` / `taxonomy_version` | string | mandatory |
| `plan_hash` | SHA-256/null | required for apply/reclassify |
| `selected_item_count` | int | exactly 10 for MVP acceptance run |
| `item_results` | list[`ItemRunResult`] | exactly one per unique selected key |
| `counters` | `RunCounters` | reconciles with item/operation results |
| `issues` | list[`Issue`] | no sensitive fields |
| `redaction_summary` | map[string,int] | counts categories, not values |

`ItemRunResult` includes `item_key`, source/version/fingerprint, classification summary, decisions, mutation ids, outcome, and stable issues. It excludes full abstract by default; evidence excerpts are bounded.

`RunCounters` separately records `operations_planned`, `operations_attempted`, `operations_verified`, `operations_failed`, `operations_uncertain`, `operations_skipped_stale`, and `operations_aborted`. The terminal reconciliation invariant is `operations_planned = attempted_nonterminal + verified + failed + uncertain + skipped_stale + aborted`, where `attempted_nonterminal` is the count whose latest durable state is `attempted` and every operation is counted exactly once by its latest durable state; item counters separately include `items_skipped_stale` and `items_aborted`. Static validation failure reports zero operations and zero gateway calls. Dynamic validation failure reports the authorized planned population partitioned into `skipped_stale|aborted`, with `attempted=verified=failed=uncertain=0` for the affected item.

### 7.8 `ProjectProfile`

Read-only normalized projection of one Obsidian `Efforts` project.

| Field | Type | Invariant |
|---|---|---|
| `profile_id` | stable SHA-256/UUID | derived without leaking full path |
| `display_name` | string | normalized |
| `source_relative_path` | relative POSIX path | must remain under configured Efforts root |
| `status` | `active|paused|archived|unknown` | active included by default |
| `subject_tags` | set[canonical `#`] | catalog validated |
| `method_tags` | set[canonical `%`] | catalog validated |
| `use_tags` | set[`$`] | catalog/config validated |
| `keywords` | set[string] | normalized, bounded |
| `research_questions` | list[string] | bounded excerpts only |
| `modified_at` | timestamp/null | read evidence |
| `content_fingerprint` | SHA-256 | supports deterministic rerun |
| `warnings` | list[`Issue`] | malformed metadata does not authorize writes |

The adapter opens files read-only, rejects symlink/path escape, never follows paths outside `Efforts`, and never writes back.

### 7.9 Example sanitized classification JSON

```json
{
  "decision_id": "018f-example",
  "paper_key": "ABCD1234",
  "ruleset_version": "1.0.0",
  "taxonomy_version": "1.0.0",
  "run_date": "2026-08-09",
  "subjects": ["#rock-mechanics", "#wellbore-stability"],
  "methods": ["%FEM"],
  "project_uses": ["$methods-cite"],
  "quality_flags": ["!data-available"],
  "proposed_stage": "review",
  "look_triggers": [{"criterion_id":"look.subject_match","status":"pass","reason_code":"SUBJECT_KEYWORD_EXACT","evidence_refs":["ev-1"]}],
  "review_criteria": [
    {"criterion_id":"review.relevance","status":"pass","reason_code":"SUBJECT_MATCH","evidence_refs":["ev-1"]},
    {"criterion_id":"review.method","status":"pass","reason_code":"METHOD_MATCH","evidence_refs":["ev-2"]},
    {"criterion_id":"review.recency_or_seminal","status":"pass","reason_code":"RECENT_WITHIN_10_YEARS","evidence_refs":["ev-3"]},
    {"criterion_id":"review.author_credibility","status":"unknown","reason_code":"NO_CREDIBILITY_EVIDENCE","evidence_refs":[]},
    {"criterion_id":"review.gap","status":"fail","reason_code":"NO_GAP_SIGNAL","evidence_refs":[]},
    {"criterion_id":"review.citable_phrase","status":"unknown","reason_code":"NO_CITABLE_METADATA_PHRASE","evidence_refs":[]}
  ],
  "dig_profile": "original",
  "dig_criteria": [],
  "confidence": "0.8800",
  "confidence_components": {"coverage":"0.9300","specificity":"0.9000","agreement":"0.8500","completeness":"0.9500"},
  "evidence": [],
  "warnings": [],
  "outcome": "high_confidence"
}
```

## 8. Normalization specification

| Field | Rules | Warning/error behavior |
|---|---|---|
| Citekey | trim, NFC, preserve display; compare case-insensitively; choose configured Zotero field source deterministically | missing -> warning, not fatal |
| Title | strip markup, decode entities, NFC, collapse whitespace | missing/blank -> `PAPER_TITLE_REQUIRED`, skip item |
| Authors | normalize creator types; family/given or literal; collapse whitespace; preserve order; de-duplicate exact normalized duplicates | empty -> warning and lower evidence coverage |
| Year | prefer issued date year per configured source order; reject implausible; freeze relative recency to `run_date` | invalid -> null + warning |
| DOI | strip `https://doi.org/`, `http://dx.doi.org/`, `doi:`; lowercase; remove trailing punctuation; validate `10.` form | invalid -> null + warning; never query network implicitly |
| Abstract | strip markup, normalize whitespace/NFC, bounded persistence/excerpts; no PDF extraction | missing lowers confidence and makes some criteria unknown |
| Collections | convert connector objects to collection-key set; separately resolve sanitized paths via catalog snapshot | unresolved key -> warning, never remove |
| Tags | trim/NFC, remove empty duplicates while preserving exact display value; canonical matching via alias map | namespace lookalikes not in catalog remain unmanaged |
| PDFs | record safe attachment ref/presence only; do not read/log bytes or absolute paths | inaccessible -> warning only |

Duplicate non-null normalized DOI within the selected batch is `PAPER_DUPLICATE_IDENTITY` and blocks every item sharing it. Duplicate citekey is a warning only because item keys remain authoritative targets; the exact keys continue independently.

## 9. Frozen MVP taxonomy, signals, and mappings

`taxonomy_version=1.0.0` is frozen for MVP. Canonical values are exactly those in the context snapshot. Automatic tag writes remain limited to the eight `#` subjects, ten `%` methods, and six `@` tags. Seven `$` project-use and five `!` quality values are advisory only.

### 9.1 Exact aliases and matching

Matching input is NFC + Unicode casefold + punctuation/hyphen-to-single-space + collapsed whitespace. Existing canonical Zotero tags match exactly before normalization. Allowed free-text sources are title, abstract, venue, and normalized ProjectProfile fields; PDF/note/highlight text is excluded. A phrase matches whole normalized tokens only. No regex or fuzzy matching is allowed in v1.

The only non-canonical aliases are:

- subjects: `rock mechanics`; `bayesian inference`, `bayesian methods`; `pinn`, `pinns`, `physics informed neural network`, `physics informed neural networks`; `soil classification`; `structural reliability`; `wellbore stability`, `borehole stability`; `sand production`, `sanding`; `structural analysis`;
- methods: `finite element method`, `finite element analysis`, `fem`; `finite difference method`, `fdm`; `discrete element method`, `dem`; `boundary element method`, `bem`; `experimental`, `experiment`, `laboratory test`; `field data`, `field measurement`; `machine learning`, `ml`; `narrative review`; `systematic review`, `prisma`; `python`, `scipy`;
- `$`: canonical spelling without `$` only; `methods citation` additionally maps to `$methods-cite`;
- `!`: canonical spelling without `!` only; `seminal paper` maps to `!seminal`, `high impact` to `!high-impact`, `weak methods` to `!weak-methods`, `conflicting evidence` to `!conflicting`, `data available` to `!data-available`.

An alias preceded within the prior three tokens by exactly `no`, `not`, or `without` yields conflict, not a positive match. Overlapping aliases use longest-token match; equal-length mappings to different canonicals yield `CLASSIFICATION_CONFLICT` and neither is selected. Unknown text never creates taxonomy. Changes require taxonomy version bump, new preview, golden update, and approval.

### 9.1.1 Deployment binding — confirmed stage collections

The configured stage-root display paths for this deployment are exactly `.ToLook` (stage `look`), `.ToRevise` (stage `review`), and `.ToDig` (stage `dig`). The configuration resolves and stores their Zotero **collection keys** during the read-only inventory; keys, not display names, are mutation targets. They replace any earlier illustrative `Look`/`Review`/`Dig` collection labels. The user supplies exactly ten sorted item keys; the batch validation requires every key to identify a regular item that is a direct or inherited member of `.ToLook` with publication year `2026`, and excludes attachment/note/annotation children and non-null duplicate DOI candidates. There is no automatic candidate selection, fallback, or first-ten choice. Other collection memberships (subject, reading-status, document-type, or unknown) are preserved as read-only context unless they are existing configured `BySubject` destinations.

### 9.2 Frozen Look triggers

Look passes if at least one of these exact triggers passes: `look.subject` (canonical subject tag or subject alias), `look.method` (canonical method tag or method alias), `look.project` (canonical `$` signal already on the item or a ProjectProfile exact keyword/tag match), `look.gap` (exact phrase `research gap`, `open problem`, `remains unclear`, `future work`, or `$gap-signal`), or `look.seminal` (existing `!seminal`). Advisory `$`/`!` can trigger classification but never mutation.

### 9.3 Collection mapping

Preview snapshots the complete selected collection tree. Root Look/Review/Dig keys and subject-to-BySubject keys are explicit configuration values; display names are evidence only. Schema and preflight require the three configured stage-root keys to be pairwise distinct and require none of them to equal any destination key in the flattened subject-to-BySubject mapping. Any duplicate root or root/BySubject collision rejects the configuration with stable `CONFIG_COLLECTION_ROLE_COLLISION`, fails the entire preview/apply closed before plan authorization, and makes zero Zotero mutation calls; display paths or names cannot disambiguate a reused key. Missing/ambiguous target root blocks both stage tag and stage collection. Missing one BySubject target reports it but does not block other resolved BySubject or tag operations. Collections are never created.

### 9.4 Credibility evidence

`review.author_venue_credibility` passes iff at least one normalized author identity exactly equals an entry in the frozen `credible_authors` configuration snapshot, the normalized venue exactly equals an entry in frozen `credible_venues`, or the item already has advisory `!seminal`/`!high-impact`. `credible_authors` entries are explicit normalized name tuples and/or explicit ORCIDs; an ORCID contributes only when that exact identifier is allowlisted, while generic syntactic ORCID validity contributes no credibility. The result is `unknown` when none is available and `conflict` when `!weak-methods` coexists with the only positive credibility evidence. No network lookup, citation count, inferred prestige, or runtime-editable unsnapshotted allowlist is allowed.

## 10. Frozen stage, confidence, and fallback policy

### 10.1 Exact stage cross-product

Evaluate Look, all six Review criteria, and the applicable Dig checklist independently, then choose stage by this exact rule:

`dig` iff `Look_pass` AND `Review_pass_count >= 3` AND exactly one Dig profile applies AND all five profile criteria are `pass`; else `review` iff `Look_pass` AND `Review_pass_count >= 3`; else `look` iff `Look_pass`; else null.

Thus Dig 5/5 never bypasses Look or Review. A 5/5 Dig result with Look false is null; with Look true but Review 2/6 is Look; with Look true and Review 3/6 is Dig. An unknown/conflict Dig profile or criterion prevents Dig.

Review criteria are frozen:

1. `review.relevance`: subject match or `$`/ProjectProfile exact project match.
2. `review.method`: canonical method match and no conflicting negation or `!weak-methods`.
3. `review.recency_or_seminal`: `year >= run_year-10` or existing `!seminal`.
4. `review.author_venue_credibility`: exact section 9.4 rule.
5. `review.gap`: exact gap trigger from section 9.2.
6. `review.citable_claim`: normalized abstract contains a sentence 40–300 characters long with one exact cue `we show`, `we find`, `results indicate`, `this study demonstrates`, `we conclude`, or `our results`; first matching sentence in source order is evidence.

Original Dig criteria are exactly: question/gap (Review gap passes); reproducible method (method match plus abstract phrase `method`, `model`, `experiment`, `algorithm`, or `procedure`); accessible results (`!data-available` or citable claim passes); direct relevance (Review relevance passes); limitation/boundary (abstract contains `limitation`, `boundary condition`, `valid for`, `restricted to`, or `future work`). Review-paper criteria are exactly: scope/question (`scope`, `review question`, or gap passes); transparent selection (`search strategy`, `selection criteria`, `inclusion criteria`, `database search`, or `%systematic-review`); synthesis (`synthesis`, `meta-analysis`, `taxonomy`, `framework`, `consensus`); gap/map (`gap`, `consensus`, `conflict`, `contradiction`); direct utility (relevance plus citable claim).

`paper_kind` is derived before Dig only from raw Zotero item type and existing canonical tags. The v1 original-paper type allowlist is exactly `journalArticle|conferencePaper|preprint|thesis|report`; with neither review tag these derive `original`. Presence of `%narrative-review` or `%systematic-review` on one of those paper types derives `review` (both tags still mean review and both remain visible evidence). The support/non-paper set is exactly `book|bookSection|document|encyclopediaArticle|dictionaryEntry|magazineArticle|newspaperArticle|manuscript|presentation|webpage|blogPost|forumPost|interview|letter|email|instantMessage|podcast|radioBroadcast|tvBroadcast|videoRecording|audioRecording|film|artwork|map|case|statute|bill|hearing|patent|standard|computerProgram|dataset`; each enumerated type maps to `item_type_class=support_or_nonpaper` and `paper_kind=ambiguous`. Zotero child/support types `attachment|note|annotation` are not selectable papers and are rejected before `Paper`. Any unknown future Zotero type maps to `item_type_class=unknown` and `paper_kind=ambiguous`. Review tags on a support/non-paper or unknown future type do not override ambiguity. No title/abstract inference resolves the kind. `review` selects the review checklist, `original` selects the original checklist, and `ambiguous` emits `PAPER_KIND_AMBIGUOUS`, evaluates no Dig checklist, and can reach at most Review.

### 10.2 Exact confidence formula

All arithmetic uses Decimal and ROUND_HALF_UP to four places at each component and final result.

- `C` coverage = available count / 6 for title, abstract, year, at least one author identity, venue, DOI.
- `S` specificity = arithmetic mean of every distinct positive underlying evidence reference used by a selected subject/method or a passing Look/Review/Dig result. The total `match_kind` table is: `existing_canonical_tag=1.0000`, `exact_rule_phrase=0.9500`, `venue_allowlist_exact=0.9000`, `author_allowlist_exact=0.9000`, `zotero_type_allowlist_exact=0.9000`, `frozen_alias=0.8500`, `recency_window=0.8000`, and `project_profile_exact=0.7500`. Thus recency and author/venue allowlist evidence that passes Review, and type evidence selecting a Dig profile, always enter `S`; no passing evidence has an implicit/default weight. Repeated underlying refs count once by `evidence_id`, and reused evidence across dependent criteria is not duplicated. If none, `0.0000`; an unknown `match_kind` or a passing result without weighted positive evidence is schema/ruleset-invalid.
- `A` agreement = `max(0, 1 - 0.2500 * distinct_conflict_count)` where conflicts are unique rule+source pairs.
- `K` completeness = determinate (`pass|fail`) criteria / evaluated criteria. Evaluated = five Look triggers + six Review criteria + five Dig criteria only when a Dig profile applies.
- `confidence = q4(0.3000*C + 0.3000*S + 0.2500*A + 0.1500*K)`.

`confidence >=0.8500` enables otherwise eligible full mutation; lower confidence permits only `@needs-reread`. No LLM confidence participates. Any rules, aliases, credibility list, formula, weight, quantization, or threshold change bumps ruleset/config digest and requires a new preview.

### 10.3 Stage ownership and fallback

Managed stage pairs are `@look`/`.ToLook`, `@review`/`.ToRevise`, and `@dig`/`.ToDig`. At most one desired pair exists. Human conflicting stage state yields `HUMAN_STAGE_CONFLICT` and no stage pair operation. `@annotated` and `@code-tested` are orthogonal. App-owned `@needs-reread` may be removed only after a verified high-confidence plan; human-owned remains.

## 11. Idempotency, exact-diff preservation, crash recovery, and Zotero port

### 11.1 Zotero port DTOs and conditions

The port exposes only `read_items(ReadItemsRequest)->list[ZoteroItemSnapshot]`, `read_collection_tree(ReadCollectionTreeRequest)->CollectionTreeSnapshot`, and `mutate_item(ZoteroMutationCommand)->ZoteroMutationReceipt`. No note, attachment-content, highlight, collection-create, or arbitrary patch method exists.

`ZoteroItemSnapshot` contains library scope, item key/version/type, normalized classification fields, full tag set, full collection-key set, and a hash of every preserved human field returned by the connector. `ZoteroMutationCommand` contains operation/idempotency ids, item key, `expected_version`, resource `tag|collection`, action `add|remove`, one target, and expected before/desired after presence. `ZoteroMutationReceipt` contains item key, accepted version, and sanitized request id; it is never verification.

Preconditions: exact plan/approval validation; the symbolic version precondition resolves to the latest app-verified snapshot; target namespace/collection allowlisted; remove ownership active with unbroken app-verified lineage; before-presence exact; dependency verified. Postcondition: reread version advances according to connector semantics and exact diff between before/after snapshots is only the target membership plus connector-controlled version/modified metadata. All other tags, collections, bibliographic fields, creators, notes/attachment metadata hashes, and human data must be identical. Any extra diff is `ZOTERO_EXACT_DIFF_VIOLATION`, item abort, no compensating guess.

### 11.2 Version chaining and item abort

The first operation resolves `PreviewVersion(v)` to `v`. Each later `VerifiedVersionOf(operation_id)` resolves only from that dependency's durable verified event; the resolved integer is copied into the runtime command and never persisted as a predicted future version. Any version advance since the last app-verified snapshot that is not the direct verified result of the preceding managed operation is external modification: mark the current operation failed/uncertain as applicable, abort all remaining item operations, and require a fresh preview. For a removal this invalidation applies even when the target is currently present: a human remove/re-add or any intervening external version advance breaks ownership lineage, protects the target from automatic removal, and emits `MANAGED_OWNERSHIP_SUPERSEDED`. Batch processing may continue with other independent items.

### 11.3 Crash/reconcile matrix

| Crash point | Durable evidence | Reconcile action |
|---|---|---|
| before authorization transaction commit | no `apply_authorization`, mutation, or `planned` row | zero calls; discard partial transaction and require/revalidate apply request |
| after authorization+planned commit, before first attempt | immutable authorization plus authorized `planned` rows | recover only by joining those rows and checking exact approved item/operation membership; zero calls occurred |
| before atomic attempt commit | authorized `planned` only; no `AttemptEvidence` | reread and execute normally; zero calls occurred |
| after atomic attempt commit, before call | attempted plus complete `AttemptEvidence`; target still before-state, version unchanged | retry same idempotency key once through normal path |
| call timeout/unknown response | attempted/uncertain | reread first; never blind retry |
| after write, before reread | attempted, target desired-state | exact-diff reread; mark verified if only target changed, else fail/abort |
| after reread, before verified commit | attempted, reread reproducible | repeat reread/exact-diff and commit verified |
| after verified commit, before next attempted | prior verified | continue with chained version |
| store commit failure before call | no durable attempted | no Zotero call; fail item |
| store commit failure after verified reread | attempted/uncertain | stop item; reconcile before any next operation |

Reconcile never reclassifies, broadens the approved plan, or infers ownership. After restart it reconstructs all authority and the last safe snapshot exclusively from persisted SQLite rows (`apply_authorization`, `managed_mutation`, `mutation_event`, and `attempt_evidence`), with no in-memory/session artifact required; it then compares the fresh gateway reread to that evidence. Desired state present with an unexplained version/diff is not sufficient for ownership; it yields `MUTATION_OUTCOME_UNCERTAIN`.

### 11.4 Idempotency and reversibility

Idempotency key is SHA-256 of plan hash + operation id. Reapply rereads and records no duplicate event when the verified desired state holds. Removal requires the same item/target active verified managed add with `previous_present=false` and no external version advance since the last app-verified snapshot. User removal/re-addition or any unexplained intervening version supersedes ownership, protects the present target, and is reported; whole-item rollback is forbidden.

## 12. Closed error, severity, and retry taxonomy

`Issue = {code, severity: info|warning|item_error|operation_error|fatal|security_error, retryable: bool, item_key?, operation_id?, safe_message, allowlisted_context}`. No adapter may override severity/retry.

| Code | Severity | Retry | Required behavior |
|---|---|---:|---|
| `CONFIG_INVALID`, `RULESET_INVALID` | fatal | no | stop before connector |
| `AUTH_MISSING`, `AUTH_REJECTED` | fatal | no | no credential echo |
| `BATCH_SIZE_INVALID` | fatal | no | exact 10 unique keys |
| `PAPER_NOT_FOUND`, `PAPER_TYPE_UNSUPPORTED`, `PAPER_TITLE_REQUIRED` | item_error | no | no item mutation |
| `PAPER_DUPLICATE_IDENTITY` | item_error | no | if non-null normalized DOI appears on >1 selected key, block mutation for every duplicate key; citekey duplicate is warning only |
| `NORMALIZATION_INVALID_VALUE`, `TAXONOMY_UNKNOWN_TAG`, `CLASSIFICATION_CONFLICT`, `PAPER_KIND_AMBIGUOUS` | warning | no | deterministic downgrade/preserve; ambiguous kind blocks Dig |
| `CONFIDENCE_BELOW_THRESHOLD` | info | no | only needs-reread eligible |
| `COLLECTION_ROOT_MISSING`, `COLLECTION_AMBIGUOUS`, `COLLECTION_ROOT_BLOCKS_STAGE` | item_error | no | no stage tag or root operation |
| `COLLECTION_BY_SUBJECT_MISSING`, `MUTATION_NOT_OWNED`, `MANAGED_OWNERSHIP_SUPERSEDED`, `HUMAN_STAGE_CONFLICT` | warning | no | preserve target |
| `PLAN_HASH_MISMATCH`, `PLAN_TAMPERED`, `APPROVAL_MISMATCH`, `PLAN_RULESET_MISMATCH` | fatal | no | refuse apply |
| `ZOTERO_ITEM_STALE`, `ZOTERO_ITEM_EXTERNALLY_MODIFIED`, `ZOTERO_EXACT_DIFF_VIOLATION` | item_error | no | abort item; new preview/manual inspection |
| `DEPENDENCY_ABORTED` | item_error | no | mark dependent operations terminal without a connector call |
| `ZOTERO_RATE_LIMITED` | operation_error | yes, max 3 | honor Retry-After, capped 30s; then partial |
| `ZOTERO_TRANSPORT_ERROR` | operation_error | yes, max 3 reads only | exponential 0.5/1/2s+jitter; uncertain writes reconcile first |
| `ZOTERO_WRITE_REJECTED` | operation_error | no | record failure, abort item |
| `ZOTERO_VERIFY_FAILED`, `MUTATION_OUTCOME_UNCERTAIN` | operation_error | no automatic retry | reconcile; abort item |
| `LEDGER_CORRUPT`, `LEDGER_WRITE_FAILED`, `STORE_PERMISSION_INVALID` | fatal | no | no further external writes |
| `CONNECTOR_ENDPOINT_FORBIDDEN`, `CONNECTOR_SCOPE_EXCESSIVE` | security_error | no | stop before network/local connector |
| `OBSIDIAN_ROOT_INVALID` | warning | no | zero profiles |
| `OBSIDIAN_PATH_ESCAPE`, `REDACTION_VIOLATION` | security_error | no | reject/fail secure |

## 13. Security and privacy gates and pre-mortem

### 13.1 Connector/store gate

- Secrets enter only through an environment-variable or OS-keyring reference supplied at connector construction. Neither reference locator nor value is serialized, snapshotted, hashed, logged, placed in exceptions/CLI arguments/reports/SQLite, or retained by tests; the snapshot records only `secret_source_type: environment|os_keyring`.
- HTTPS endpoints must match the explicit host allowlist snapshot; redirects to a different host/scheme are rejected. Plain HTTP, arbitrary proxy endpoints, and local database writes are forbidden. If a local Zotero connector is selected, transport is loopback-only and its exact port/path is allowlisted; implementation cannot support both transports implicitly.
- Token/library scope must be the single configured library and minimum item/tag/collection read-write permissions; delete, file, note, and collection-create scopes fail preflight.
- Connect/read timeout is 5s/15s; retry behavior is exactly section 12. Connector raw bodies/headers never escape the adapter.
- Preview/report artifacts are `0600`; parent directories `0700`; default retention is 30 days for previews/reports and indefinite for mutation provenance until explicit local purge. Purge never deletes active ownership evidence and is itself audited.
- Every configured output/database/Efforts path is resolved component-by-component with `lstat`; reject symlinks, `..`, non-owner-writable parents, device files, and resolved paths outside the configured root. Files are created with no-follow/exclusive semantics and atomic rename within the same directory.


### Scenario 1 — The classifier removes human organization

- **Failure chain:** existing canonical tags look app-generated -> reclassification treats them as owned -> removes user tag/collection.
- **Early indicators:** removal decision without a verified mutation id; `previous_present=true` on an app “add”; ownership inferred from prefix.
- **Prevention:** hard validation that every remove references an active verified managed addition with `previous_present=false`; property tests; apply-time ownership recheck.
- **Recovery:** stop affected item, retain exact report, restore only from explicit known mutation evidence; never blanket-restore a whole item.

### Scenario 2 — Sensitive Zotero/PDF content leaks into logs

- **Failure chain:** connector exception or debug logging serializes headers/raw payload/abstract/PDF path or bytes.
- **Early indicators:** log key names such as authorization/token/content/raw/pdf; unexpectedly large log events.
- **Prevention:** structured allowlist logger, exception adapters, secret canaries in tests, size limits, no raw DTO `repr`, secure defaults with debug payload logging absent.
- **Recovery:** fail run on redaction violation, rotate exposed credentials if any, delete affected local logs, and document the incident without repeating secrets.

### Scenario 3 — Partial or stale writes corrupt stage consistency

- **Failure chain:** preview becomes stale or network fails after tag update but before collection update -> contradictory stage remains -> blind retry compounds it.
- **Early indicators:** version mismatch, unverified mutation, tag/collection stage disagreement, `PARTIAL` report.
- **Prevention:** per-item optimistic concurrency, operation ledger before next mutation, post-write reread, retry through reconciliation rather than replay.
- **Recovery:** re-preview current state; compute only safe managed diffs; leave human state untouched and surface unresolved inconsistency.

## 14. Edge cases and required behavior

- Exactly confidence `0.8500` qualifies; `0.8499` does not.
- A paper published exactly 10 calendar years before `run_date` passes recency; older does not unless seminal.
- Missing year plus `!seminal` evidence passes the recency-or-seminal criterion.
- Review score `3/6` passes; `2/6` does not.
- Dig with 4/5 passes remains Review/Look according to lower gates.
- Original/review type ambiguity blocks Dig and lowers confidence.
- Multiple subject matches add all resolved existing BySubject memberships.
- Missing one of multiple BySubject targets does not block other safe additions; report the missing one.
- Duplicate collection display names require configured keys; no guessing.
- Existing human `@dig` conflicting with proposed `@review` causes a conflict and no stage movement.
- Low-confidence item already at a stage stays there and receives/keeps `@needs-reread`.
- Low-confidence item with no stage still receives `@needs-reread`, with no stage collection addition.
- Existing `@needs-reread` not owned by the app is preserved and never claimed.
- Missing abstract/DOI/authors does not automatically fail normalization, but makes evidence unavailable and lowers confidence.
- Malformed Obsidian frontmatter isolates that profile; classification can continue without it.
- Symlink from Efforts to outside the vault is rejected.
- Rate limiting yields bounded retry and resumable partial report.
- Ledger unavailable means preview may proceed, but apply/removal is disabled.

## 15. SDD + TDD delivery strategy

### 15.1 Spec-Driven Design gates

1. Treat this PRD, test spec, schema JSON snapshots, taxonomy catalog, and error catalog as normative artifacts.
2. Before adapter code, encode Pydantic schemas and golden JSON examples; schema review is Gate S1.
3. Before live writes, implement and test pure normalization/classification/mutation planning; domain verification is Gate S2.
4. Before real Zotero use, pass contract tests with a fake gateway and recorded sanitized fixtures; adapter verification is Gate S3.
5. Before apply on 10 papers, execute and human-review a dry-run report; safety review is Gate S4.
6. The real apply and idempotent rerun constitute Gate S5; no scope expansion to full library follows automatically.

### 15.2 TDD order

For each increment: add a failing test from the companion spec -> implement the smallest behavior -> refactor while green -> run targeted suite -> update schema/golden artifacts only through reviewed changes.

## 16. Incremental implementation plan

### Increment 0 — Project and safety skeleton

**Deliverables:** Python package/tooling; configuration schema; structured logging/redaction; stable `Issue` catalog; test fixture rules prohibiting secrets.
**Acceptance:** invalid config fails before I/O; secret canary tests show no raw value in logs/reports; no source adapter can write outside ports.

### Increment 1 — Domain contracts and taxonomy

**Deliverables:** Pydantic models for Paper, Classification, decisions, PreviewPlan/MutationPlan, PlannedItem, PlannedOperation, ApplyRequest/ApprovalEvidence, immutable ApplyAuthorization, ManagedMutation events, RunReport, and nested DTOs; JSON Schemas/goldens; frozen taxonomy/aliases.
**Acceptance:** extra fields fail; `$`/`!` add/remove fails; every persisted schema round-trips canonically; per-field tamper and ordering goldens prove hash binding.

### Increment 2 — Normalization and deterministic classification

**Deliverables:** pure normalizer; frozen Look/Review/Dig cross-product; exact alias/credibility rules; Decimal confidence formula; evidence/reasons.
**Acceptance:** full cross-product tests prove Dig never bypasses Look/Review; exact aliases, credibility, confidence component and threshold goldens pass.

### Increment 3 — Mutation planner and ledger

**Deliverables:** pure desired-vs-current diff; normative plan/apply schemas and canonical hash; SQLite WAL event store with immutable `apply_authorization`; ownership/reclassification planner.
**Acceptance:** property tests prove no unowned or `$`/`!` mutation; golden round-trip/tamper/order tests pass; no `planned` exists before validated authorization; every crash-matrix point reconciles only through authorization; corruption/permission failure disables apply.

### Increment 4 — Zotero adapter and two-phase application service

**Deliverables:** exact DTO Zotero port; collection snapshot; hash-and-approval-bound apply; version-chained authorization->planned->attempted->write->reread->verified protocol; exact-diff verification; closed retry taxonomy.
**Acceptance:** fake and real adapters pass the same contract; stale/external changes abort the item; non-target fields/tags/collections are byte-equivalent; crash matrix reconciles without blind write retry.

### Increment 5 — Obsidian Efforts read-only adapter

**Deliverables:** configuration-gated project discovery and `ProjectProfile` normalization; safe path handling.
**Acceptance:** no write-capable filesystem path exists; escape/symlink tests pass; malformed/unavailable vault degrades to zero profiles with warnings.

### Increment 6 — CLI, reports, and simulated E2E

**Deliverables:** `preview`, `apply --preview-id`, `reclassify`, and `report` entrypoints; exact-10 selection guard; human-readable diff plus JSON report.
**Acceptance:** fake/sandbox E2E passes all success/failure cases; preview is default; apply requires an existing matching plan identifier.

### Increment 7 — Real Zotero batch of 10

**Deliverables:** credential-safe preflight; collection mapping validation; persisted dry-run; human-reviewed apply; verification rerun.
**Acceptance:** all criteria in section 17 and the companion test spec pass. Stop after 10; do not expand automatically.

## 17. MVP acceptance criteria — real batch of 10

1. The selection contains exactly 10 unique, explicitly named Zotero item keys; the report has exactly 10 item results.
2. Preview performs zero Zotero writes, confirmed by gateway counters and unchanged item versions/state.
3. Each item has a valid normalized `Paper`, or a stable item-level error with zero mutations.
4. Every writable tag is canonical `#`, `%`, or `@`; all `$`/`!` decisions are advisory `keep|skip`, even at confidence `1.0000`; every collection write targets an existing snapshotted key.
5. Every item with `confidence <0.85` has no stage/collection movement and has at most the allowed `@needs-reread` addition.
6. Every full mutation belongs to an item with `confidence >=0.85`, has reason/evidence, and passes allowlist validation.
7. All matching existing BySubject mappings are considered; missing targets are reported and never created.
8. No Zotero/Obsidian notes, highlights, PDFs, Concepts/MOCs, or ideas are changed; Obsidian filesystem state is byte-for-byte unchanged.
9. Every successful write has a verified `ManagedMutation`; report counters reconcile with Zotero state.
10. A second apply of the same plan performs zero writes.
11. A fresh re-preview after apply yields no unmanaged removal proposal and no drift for successfully verified items.
12. A controlled reclassification fixture proves that only a previously verified managed tag/collection can be removed.
13. Logs/reports contain no credential/token, raw connector payload, PDF bytes/path, or unbounded abstract; secret canaries are absent.
14. Any partial/stale/error item is explicit; the overall report is `partial` rather than falsely `success`.
15. The exact PreviewPlan rehashes, ApprovalEvidence binds the complete rendered diff/items/operations, and no apply-time recomputation broadens it.
16. Every operation has a durable attempted event before the write, exact-diff reread, verified event, and chained version; the full crash matrix passes.
17. Test, typecheck, lint, schema validation, integration, simulated E2E, security, and store fault-injection gates are green before real apply.

## 18. ADR-001 — Safe two-phase Zotero mutation

### Decision

Use ports-and-adapters with frozen deterministic classification, normative hash-bound PreviewPlan/MutationPlan and ApprovalEvidence contracts, a separate apply phase, exact DTO/diff verification, per-operation version chaining, and an append-only SQLite WAL mutation-event ledger.

### Drivers

1. Prevent loss of human-authored Zotero organization.
2. Make real-library mutations explainable, idempotent, and narrowly reversible.
3. Deliver a useful 10-paper MVP without external AI/PDF processing.

### Alternatives considered

- Direct read/classify/write pipeline.
- Two-phase plan/apply with managed mutation ledger.
- Tags-only shadow mode with manual collections.

### Why chosen

Only the two-phase option satisfies the closed collection-management requirement while also producing adequate evidence and recovery behavior for real Zotero data.

### Consequences

- More schemas, canonical snapshots, approval evidence, SQLite transactions, and crash-state transitions must be implemented and tested.
- Batch atomicity is explicitly not promised; correctness is per-item and recoverable.
- Dry-run becomes the normal operating mode, and a plan identifier is required for apply.
- Connector/library replacement remains isolated behind ports.

### Follow-ups

- At implementation kickoff, validate the chosen Zotero SDK/API against official current documentation.
- Implement the fixed SQLite WAL protocol and preserve its port contract.
- Treat the v1 trigger/alias/credibility catalog as frozen; changes require a version bump, new goldens, and new preview approval.
- Consider a local LLM only after deterministic MVP acceptance, behind a proposal-only port with independent validation.

## 19. ADR-002 — Project awareness without Obsidian mutation

### Decision

Model project relevance through immutable `ProjectProfile` objects produced by a read-only `Efforts` adapter. Make the adapter optional and treat zero profiles as valid.

### Drivers

- Preserve future project-aware classification.
- Eliminate Obsidian write risk from the MVP.
- Keep classification reproducible through profile fingerprints.

### Alternatives considered

- Ignore Obsidian entirely (simpler, but creates a later domain rewrite).
- Directly edit project notes with triage results (out of scope and unsafe).
- Read-only profile projection (chosen).

### Why chosen

It retains the future relevance boundary without coupling Zotero triage to vault availability or granting write authority.

### Consequences and follow-ups

- Frontmatter conventions need deployment configuration and fixtures.
- Path/symlink security tests are mandatory.
- Any future write-back requires a separate ADR and explicit user authorization.

## 20. Risks and mitigations

| Risk | Mitigation | Proof |
|---|---|---|
| Taxonomy false positives | versioned bounded aliases, conflicts, preview evidence | golden/property tests + 10-paper review |
| Human metadata removal | ledger-backed ownership invariant | property + integration test |
| Zotero API/SDK drift | thin port, official-doc check, contract fixtures | adapter contract suite |
| Non-atomic partial writes | per-item status, append-before-next-op, reconciliation | fault injection E2E |
| Stale preview | item version/fingerprint checks | concurrency integration test |
| Missing/ambiguous collections | key-based mapping, no creation/guessing | catalog tests/report warning |
| Sensitive logging | structured allowlist, secret canaries, output limits | observability tests |
| Rule/result nondeterminism | fixed run date, versions, decimal quantization, sorted serialization | repeatability tests |
| Over-scoping into research assistant | enforce non-scope and ports | PR review checklist |

## 21. Verification and stop rules

### Required verification sequence

1. Validate Pydantic-generated JSON schemas and golden artifacts.
2. Run focused unit tests for changed modules.
3. Run full unit + property suite.
4. Run typecheck, lint/format check, and package/build check.
5. Run fake-gateway integration suite with fault injection.
6. Run simulated E2E preview/apply/reapply/reclassify.
7. Run credential/redaction and Obsidian read-only checks.
8. Generate real 10-paper preview and manually validate the complete diff.
9. Apply only that persisted plan, verify Zotero state, then rerun idempotency check.

### Stop conditions

- Stop before live apply if any plan hash/version/collection mapping/ledger/redaction gate fails.
- Stop the affected item on stale data, human-stage conflict, or unverified write; do not broaden scope to “fix” unrelated library state.
- Stop the MVP after the verified batch of 10. A whole-library rollout requires a separate reviewed plan and sampling strategy.

## 22. Execution handoff

### Available agent-type roster

`analyst`, `planner`, `architect`, `critic`, `scholastic`, `explore`, `researcher`, `dependency-expert`, `executor`, `test-engineer`, `debugger`, `verifier`, `code-reviewer`, `code-simplifier`, `designer`, `writer`, `git-master`, `vision`, `team-executor`.

### Recommended staffing

#### `$ultragoal` default durable follow-up

- **Goal owner / architect** — high/xhigh reasoning: preserve contracts, gates, ADR decisions, and sequence increments 0–7.
- **Executor** — medium/high: implement one increment at a time, never combine live Zotero acceptance with unfinished safety work.
- **Test engineer** — medium/high: own tests first and mutation-safety/fault-injection coverage.
- **Verifier** — high: independently validate each SDD gate and real-batch evidence.
- **Dependency expert/researcher** — high, bounded at Increment 4: choose/check Zotero connector using official current docs.

Recommended durable path: `$ultragoal` owns the ledger of increments and acceptance evidence; attach `$team` only for parallelizable implementation after schemas are frozen.

#### `$team` coordinated path

After Increment 1 contract freeze, use 3 lanes:

1. **Domain executor** (medium/high): normalization, rules, confidence, mutation planner.
2. **Adapter executor** (medium/high): Zotero/project/store ports and adapters, without changing domain policy.
3. **Test engineer/verifier** (high): tests first, fault injection, redaction, and independent gate evidence.

An architect reviews shared contracts before parallel work and a verifier integrates evidence before shutdown. Avoid parallel edits to `domain/models.py` and taxonomy schemas until contract freeze.

### Suggested launch hints

```bash
# Default durable sequential execution tracking
$ultragoal .omx/plans/prd-zotero-obsidian-paper-triage.md

# Coordinated implementation after contract freeze
omx team 3:executor "Implement the approved PRD and test spec incrementally; preserve the safety constitution; stop before real Zotero apply until verifier approval."

# Equivalent explicit workflow surface
$team 3:executor ".omx/plans/prd-zotero-obsidian-paper-triage.md + .omx/plans/test-spec-zotero-obsidian-paper-triage.md"
```

### Team verification path

Before Team shutdown it must return: changed-file inventory, schema/golden diff, targeted and full test outputs, typecheck/lint/build output, fault-injection results, redaction scan, fake E2E report, and unresolved risks. `$ultragoal` checkpoints that evidence at each SDD gate and retains ownership of the final real-batch acceptance decision. No worker independently authorizes live Zotero apply.

### Goal-mode follow-up suggestions

- **Recommended:** `$ultragoal` for durable implementation and completion tracking; pair with `$team` after contract freeze when parallel lanes are useful.
- `$autoresearch-goal` is not the implementation path here; use it only for a separate literature/reference research deliverable or evidence study.
- `$performance-goal` is not needed for the MVP; use it only if a later measurable throughput/latency objective is approved.
- `$ralph` is an explicit fallback only if the user deliberately wants one persistent single-owner implement/fix/verify loop; it does not supersede the recommended durable ledger and must use the same acceptance criteria.

## 23. Consensus improvement record

### Iteration 0 — initial draft

Established two-phase preview/apply, managed-only reversibility, real-batch limit, deliberate pre-mortem, and execution handoff.

### Iteration 1 — Architect `ITERATE` blockers integrated

- **P0 namespace boundary:** writes restricted to `#/%/@`; `$` and `!` are advisory-only with schema and negative-test requirements.
- **P0 plan authority:** added normative PreviewPlan/MutationPlan, PlannedItem/Operation, ApplyRequest/ApprovalEvidence, snapshot/hash/exclusion/order/dependency rules, and exact approval limits.
- **P0 deterministic classifier:** froze v1 taxonomy/aliases/triggers/credibility, exact Decimal confidence formula, and Dig = Look + Review>=3 + profile 5/5 cross-product.
- **P0 durability:** selected SQLite WAL/FULL and fixed planned->attempted->write->reread->verified, version chaining, stage dependency order, missing-root joint block, reconcile and crash matrix.
- **P1 ports/policy/security:** fixed Zotero DTO/exact-diff contract, duplicate DOI/error/retry taxonomy, and connector/secret/endpoint/scope/timeout/permission/retention/path gates.

**Consensus state:** revised for the next Architect review; no execution authorization is implied.

### Iteration 2 — Architect rereview blockers integrated

- **P0 crash evidence:** added atomic pre-call `AttemptEvidence` with the complete safe prior snapshot and restart reconciliation whose authority comes exclusively from SQLite persistence.
- **P0 symbolic concurrency:** replaced persisted predicted future versions with hash-bound `PreviewVersion(v)` / `VerifiedVersionOf(operation_id)` preconditions; numeric versions exist only in runtime commands.
- **P0 ownership lineage:** any unexplained external version advance supersedes removal authority even when the target is present; human re-additions are protected and reported.
- **P1 reproducibility:** made the project-profile snapshot/digest mandatory, including the zero-profile case, and included it in canonical hashing/tamper coverage.
- **P1 classification/review:** defined deterministic `paper_kind`, blocked Dig on ambiguity, and made `ReviewedDiffProjection` the exact schema/UI/hash oracle.
- **Consistency:** corrected confidence examples to fixed decimal strings, removed `conflict_penalty`, limited byte-identity claims to hashable projections/deterministic ids, and aligned CLI apply on `--preview-id`.

**Consensus state:** iteration 2 is ready for Architect verification; no execution authorization is implied.

### Iteration 3 — Architect final P0/P1 closure

- **P0 durable apply authority:** added immutable SQLite `apply_authorization`, atomic authorization+`planned` persistence, mandatory mutation foreign keys, authorization-only recovery, and crash boundaries before/after authorization commit.
- **P0 stage-root semantics:** allowed a hash-bound stage tag add when the configured root is already present, including human presence, without a redundant root add or ownership claim.
- **P1 paper kind:** replaced the legacy generic review tag with `%narrative-review`/`%systematic-review`, enumerated original-paper versus support/non-paper Zotero types, rejected child types, and kept ambiguity as a hard Dig block.
- **P1 total specificity/credibility:** closed the `match_kind` enum and weights for every positive Review/Dig evidence path, added explicit author/venue allowlists, and removed generic valid ORCID as credibility.
- **Consistency:** removed duplicate headings and aligned Dig examples, identifiers, schemas, traceability, and crash tests.

**Consensus state:** iteration 3 closes the requested Architect P0/P1 blockers and is ready for final verification; no execution authorization is implied.

### Iteration 4 — Critic state/preflight closure

- Split static plan/approval validation from dynamic per-item validation and added terminal pre-call `planned -> skipped_stale|aborted` transitions with zero-call, recovery, reapply, and RunReport reconciliation semantics.
- Added fail-closed schema/preflight validation that Look/Review/Dig roots are pairwise distinct and disjoint from every BySubject destination key, with stable `CONFIG_COLLECTION_ROLE_COLLISION`.
- Added unit, integration, simulated E2E, observability, and traceability requirements for both closures in the companion test specification.

**Consensus state:** iteration 4 addresses Critic iteration 1; no execution authorization is implied.


## 24. Terminal Ralplan consensus handoff

**Terminal status:** `complete` — planning only; this artifact does not authorize implementation.

**Required review order and evidence:**
1. Architect review completed after Planner revisions: **APPROVE**.
2. Critic gate completed after the approving Architect review: **APPROVE**.
3. The deliberate-mode pre-mortem and expanded unit, integration, E2E, crash/recovery, observability, and 10-paper real-lot validation plan remain required acceptance evidence.

**Execution boundary:** begin only through an explicit subsequent execution workflow. The recommended durable path is `$ultragoal` with `$team` where parallel delivery is warranted; `$ralph` remains an explicit single-owner fallback only.
