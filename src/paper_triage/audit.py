"""Local-only mutation preview, approval, and auditable application contracts."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .plans import ApplyRequest, PreviewPlan


class Mutation(BaseModel):
    """One proposed local mutation; it carries data, never connector credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["tag", "collection"]
    target: str = Field(min_length=1)
    action: Literal["add"]


class DiffEntry(BaseModel):
    """The exact observable change expected from one approved mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["tag", "collection"]
    target: str = Field(min_length=1)
    action: Literal["add"]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class MutationPlan(BaseModel):
    """JSON-serializable preview of changes to exactly one local item."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"] = "1.0"
    library_id: str = Field(min_length=1)
    item_key: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_version: int = Field(default=0, ge=0)
    mutations: tuple[Mutation, ...] = Field(min_length=1)

    @property
    def expected_diff(self) -> tuple[DiffEntry, ...]:
        return tuple(
            DiffEntry(kind=mutation.kind, target=mutation.target, action=mutation.action)
            for mutation in sorted(
                self.mutations, key=lambda item: (item.kind, item.target, item.action)
            )
        )

    @property
    def plan_hash(self) -> str:
        return canonical_plan_hash(self)

    @property
    def operation_ids(self) -> tuple[str, ...]:
        """Stable identities distinguish identical operations by their canonical ordinal."""

        return tuple(
            hashlib.sha256(
                _canonical_json({"ordinal": ordinal, **entry.model_dump(mode="json")}).encode(
                    "utf-8"
                )
            ).hexdigest()
            for ordinal, entry in enumerate(self.expected_diff)
        )


def canonical_plan_hash(plan: MutationPlan) -> str:
    """Hash the semantic plan, independent of insertion order or derived fields."""

    payload = plan.model_dump(exclude={"plan_hash"}, mode="json")
    payload["mutations"] = sorted(
        payload["mutations"], key=lambda item: (item["kind"], item["target"], item["action"])
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def canonical_reviewed_diff_hash(plan: MutationPlan) -> str:
    """Hash the complete, ordered rows a reviewer approves before application."""

    return hashlib.sha256(
        _canonical_json(
            [
                {
                    "item_key": plan.item_key,
                    "operation_id": operation_id,
                    **entry.model_dump(mode="json"),
                }
                for entry, operation_id in zip(plan.expected_diff, plan.operation_ids, strict=True)
            ]
        ).encode("utf-8")
    ).hexdigest()


class Approval(BaseModel):
    """Local approval that binds a human decision to an immutable preview hash."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_by: str = Field(min_length=1, max_length=240)


class ApplyAuthorization(BaseModel):
    """Immutable, digest-bound authority for applying one persisted preview."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"] = "1.0"
    authorization_id: str = Field(min_length=1, max_length=240)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_diff_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_item_keys: tuple[str, ...] = Field(min_length=1)
    approved_operation_ids: tuple[str, ...] = Field(min_length=1)
    confirmation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_method: Literal["local_interactive"] = "local_interactive"

    @staticmethod
    def confirmation_digest_for(
        *,
        plan_hash: str,
        reviewed_diff_hash: str,
        approved_item_keys: Sequence[str],
        approved_operation_ids: Sequence[str],
    ) -> str:
        payload = "APPLY\n" + plan_hash + "\n" + reviewed_diff_hash + "\n"
        payload += "\n".join(approved_item_keys) + "\n" + "\n".join(approved_operation_ids)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def for_plan(cls, mutation_plan: MutationPlan, *, authorization_id: str) -> ApplyAuthorization:
        operation_ids = mutation_plan.operation_ids
        reviewed_diff_hash = canonical_reviewed_diff_hash(mutation_plan)
        item_keys = (mutation_plan.item_key,)
        return cls(
            authorization_id=authorization_id,
            plan_hash=mutation_plan.plan_hash,
            reviewed_diff_hash=reviewed_diff_hash,
            approved_item_keys=item_keys,
            approved_operation_ids=operation_ids,
            confirmation_digest=cls.confirmation_digest_for(
                plan_hash=mutation_plan.plan_hash,
                reviewed_diff_hash=reviewed_diff_hash,
                approved_item_keys=item_keys,
                approved_operation_ids=operation_ids,
            ),
        )

    @model_validator(mode="after")
    def _validate_digest_and_canonical_sets(self) -> ApplyAuthorization:
        if tuple(sorted(set(self.approved_item_keys))) != self.approved_item_keys:
            raise ValueError("approved item keys must be sorted and unique")
        if len(set(self.approved_operation_ids)) != len(self.approved_operation_ids):
            raise ValueError("approved operation ids must be unique")
        expected_digest = self.confirmation_digest_for(
            plan_hash=self.plan_hash,
            reviewed_diff_hash=self.reviewed_diff_hash,
            approved_item_keys=self.approved_item_keys,
            approved_operation_ids=self.approved_operation_ids,
        )
        if self.confirmation_digest != expected_digest:
            raise ValueError("confirmation digest does not bind the approved content")
        return self


class AttemptEvidence(BaseModel):
    """Canonical safe snapshot that must be durable before an external attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    operation_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    item_key: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")
    item_version: int = Field(ge=0)
    tags: tuple[str, ...]
    collection_keys: tuple[str, ...]
    preserved_field_hashes: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_safe_snapshot(self) -> AttemptEvidence:
        if self.tags != tuple(sorted(set(self.tags))):
            raise ValueError("attempt tags must be sorted and unique")
        if self.collection_keys != tuple(sorted(set(self.collection_keys))):
            raise ValueError("attempt collection keys must be sorted and unique")
        if any(len(value) != 64 or set(value) - set("0123456789abcdef") for value in self.preserved_field_hashes.values()):
            raise ValueError("attempt evidence requires SHA-256 preserved-field hashes")
        return self


class MutationPort(Protocol):
    """Narrow local port; implementations must return their observed diff."""

    def apply(self, mutation_plan: MutationPlan) -> Sequence[DiffEntry]: ...


class ExactDiffMismatch(RuntimeError):
    """Raised when a port's observed mutation result is not precisely the preview."""


class UncertainApplyError(RuntimeError):
    """A prior write may have happened, but its outcome has not been read back."""


@dataclass(frozen=True)
class LedgerEntry:
    state: Literal["planned", "attempted", "verified"]
    plan_hash: str


class AuditLedger:
    """SQLite WAL append-only ledger for local mutation progress."""

    def __init__(self, path: Path) -> None:
        path = path.expanduser()
        if path.name in {"", ".", ".."} or path.is_symlink() or path.parent.is_symlink():
            raise ValueError("audit artifact path must not use symlinks")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        self._connection = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS canonical_preview "
            "(plan_hash TEXT PRIMARY KEY, preview_id TEXT NOT NULL UNIQUE, plan_json TEXT NOT NULL, "
            "apply_request_json TEXT NOT NULL, approval_digest TEXT NOT NULL UNIQUE)"
        )
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS canonical_preview_no_update "
            "BEFORE UPDATE ON canonical_preview BEGIN SELECT RAISE(ABORT, 'immutable preview'); END"
        )
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS canonical_preview_no_delete "
            "BEFORE DELETE ON canonical_preview BEGIN SELECT RAISE(ABORT, 'immutable preview'); END"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS apply_authorization "
            "(authorization_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL UNIQUE, "
            "reviewed_diff_hash TEXT NOT NULL, approved_item_keys_json TEXT NOT NULL, "
            "approved_operation_ids_json TEXT NOT NULL, confirmation_digest TEXT NOT NULL UNIQUE, "
            "approval_method TEXT NOT NULL CHECK(approval_method = 'local_interactive'))"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS operation_ledger "
            "(sequence INTEGER PRIMARY KEY, authorization_id TEXT NOT NULL "
            "REFERENCES apply_authorization(authorization_id), operation_id TEXT NOT NULL, "
            "state TEXT NOT NULL CHECK(state IN "
            "('planned', 'attempted', 'verified', 'skipped_stale', 'aborted')), "
            "expected_version INTEGER NOT NULL, observed_version INTEGER, "
            "UNIQUE(authorization_id, operation_id, state))"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS mutation_ledger "
            "(sequence INTEGER PRIMARY KEY, plan_hash TEXT NOT NULL, authorization_id TEXT NOT NULL "
            "REFERENCES apply_authorization(authorization_id), state TEXT NOT NULL "
            "CHECK(state IN ('planned', 'attempted', 'verified')))"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS attempt_evidence "
            "(sequence INTEGER PRIMARY KEY, authorization_id TEXT NOT NULL REFERENCES apply_authorization(authorization_id), "
            "operation_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, item_key TEXT NOT NULL, item_version INTEGER NOT NULL, "
            "tags_json TEXT NOT NULL, collection_keys_json TEXT NOT NULL, preserved_hashes_json TEXT NOT NULL, "
            "UNIQUE(authorization_id, operation_id))"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS managed_provenance "
            "(operation_id TEXT PRIMARY KEY, authorization_id TEXT NOT NULL REFERENCES apply_authorization(authorization_id), "
            "item_key TEXT NOT NULL, resource TEXT NOT NULL, target TEXT NOT NULL, verified_version INTEGER NOT NULL)"
        )
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS apply_authorization_no_update "
            "BEFORE UPDATE ON apply_authorization BEGIN SELECT RAISE(ABORT, 'immutable authorization'); END"
        )
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS apply_authorization_no_delete "
            "BEFORE DELETE ON apply_authorization BEGIN SELECT RAISE(ABORT, 'immutable authorization'); END"
        )
        self._connection.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the local connection for narrow integrity assertions in tests."""

        return self._connection

    @property
    def journal_mode(self) -> str:
        return str(self._connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def persist_preview_request(self, plan: PreviewPlan, request: ApplyRequest) -> bool:
        """Durably bind an exact ten-item preview to its immutable apply request.

        This boundary is intentionally separate from the legacy single-item
        ``MutationPlan`` ledger. A later batch executor must load this persisted
        pair rather than trusting an in-memory preview or approval.
        """
        request.validates(plan)
        row = (
            plan.plan_hash,
            plan.preview_id,
            plan.model_dump_json(),
            request.model_dump_json(),
            request.approval.confirmation_digest,
        )
        existing = self._connection.execute(
            "SELECT plan_hash, preview_id, plan_json, apply_request_json, approval_digest "
            "FROM canonical_preview WHERE plan_hash = ?",
            (plan.plan_hash,),
        ).fetchone()
        if existing is not None:
            if existing != row:
                raise ValueError("persisted preview conflicts with immutable approval")
            return False
        with self._connection:
            self._connection.execute(
                "INSERT INTO canonical_preview(plan_hash, preview_id, plan_json, apply_request_json, approval_digest) "
                "VALUES (?, ?, ?, ?, ?)",
                row,
            )
        return True

    def load_preview_request(self, plan_hash: str) -> tuple[PreviewPlan, ApplyRequest]:
        """Load and revalidate the durable authority pair before a batch apply."""
        row = self._connection.execute(
            "SELECT plan_json, apply_request_json FROM canonical_preview WHERE plan_hash = ?",
            (plan_hash,),
        ).fetchone()
        if row is None:
            raise ValueError("canonical preview is not persisted")
        plan = PreviewPlan.model_validate_json(row[0])
        request = ApplyRequest.model_validate_json(row[1])
        request.validates(plan)
        if plan.plan_hash != plan_hash:
            raise ValueError("persisted preview hash is inconsistent")
        return plan, request

    def persist_authorization_and_plan(
        self, authorization: ApplyAuthorization, mutation_plan: MutationPlan
    ) -> bool:
        """Atomically persist immutable authority and its first planned ledger row.

        Returns whether new durable state was inserted.  An identical reapply is a
        read-only replay; any disagreement with the immutable row is fatal.
        """

        expected = ApplyAuthorization.for_plan(
            mutation_plan, authorization_id=authorization.authorization_id
        )
        if authorization != expected:
            raise ValueError("authorization does not exactly match preview plan")
        existing = self._connection.execute(
            "SELECT plan_hash, reviewed_diff_hash, approved_item_keys_json, "
            "approved_operation_ids_json, confirmation_digest, approval_method "
            "FROM apply_authorization WHERE authorization_id = ?",
            (authorization.authorization_id,),
        ).fetchone()
        expected_row = (
            authorization.plan_hash,
            authorization.reviewed_diff_hash,
            _canonical_json(authorization.approved_item_keys),
            _canonical_json(authorization.approved_operation_ids),
            authorization.confirmation_digest,
            authorization.approval_method,
        )
        if existing is not None:
            if existing != expected_row:
                raise ValueError("authorization conflicts with immutable persisted authority")
            return False
        with self._connection:
            self._connection.execute(
                "INSERT INTO apply_authorization "
                "(authorization_id, plan_hash, reviewed_diff_hash, approved_item_keys_json, "
                "approved_operation_ids_json, confirmation_digest, approval_method) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    authorization.authorization_id,
                    authorization.plan_hash,
                    authorization.reviewed_diff_hash,
                    _canonical_json(authorization.approved_item_keys),
                    _canonical_json(authorization.approved_operation_ids),
                    authorization.confirmation_digest,
                    authorization.approval_method,
                ),
            )
            self.record(
                authorization.plan_hash, authorization.authorization_id, "planned", commit=False
            )
        return True

    def record(
        self,
        plan_hash: str,
        authorization_id: str,
        state: Literal["planned", "attempted", "verified"],
        *,
        commit: bool = True,
    ) -> None:
        self._connection.execute(
            "INSERT INTO mutation_ledger(plan_hash, authorization_id, state) VALUES (?, ?, ?)",
            (plan_hash, authorization_id, state),
        )
        if commit:
            self._connection.commit()

    def entries_for(self, plan_hash: str) -> tuple[LedgerEntry, ...]:
        rows = self._connection.execute(
            "SELECT state, plan_hash FROM mutation_ledger WHERE plan_hash = ? ORDER BY sequence",
            (plan_hash,),
        )
        return tuple(LedgerEntry(state=row[0], plan_hash=row[1]) for row in rows)

    def record_operation(
        self,
        authorization_id: str,
        operation_id: str,
        state: Literal["planned", "attempted", "verified", "skipped_stale", "aborted"],
        expected_version: int,
        observed_version: int | None = None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO operation_ledger "
            "(authorization_id, operation_id, state, expected_version, observed_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (authorization_id, operation_id, state, expected_version, observed_version),
        )
        self._connection.commit()

    def operation_entries_for(self, authorization_id: str) -> tuple[OperationLedgerEntry, ...]:
        rows = self._connection.execute(
            "SELECT operation_id, state, expected_version, observed_version FROM operation_ledger "
            "WHERE authorization_id = ? ORDER BY sequence",
            (authorization_id,),
        )
        return tuple(
            OperationLedgerEntry(
                operation_id=row[0], state=row[1], expected_version=row[2], observed_version=row[3]
            )
            for row in rows
        )

    def record_attempt(self, authorization_id: str, evidence: AttemptEvidence) -> None:
        """Commit the evidence and ``planned -> attempted`` event as one transaction."""
        row = self._connection.execute(
            "SELECT state, expected_version FROM operation_ledger WHERE authorization_id = ? AND operation_id = ? "
            "ORDER BY sequence DESC LIMIT 1", (authorization_id, evidence.operation_id)
        ).fetchone()
        if row is None or row[0] != "planned" or row[1] != evidence.item_version:
            raise ValueError("attempt requires matching durably planned operation")
        with self._connection:
            self._connection.execute(
                "INSERT INTO attempt_evidence(authorization_id, operation_id, idempotency_key, item_key, item_version, tags_json, collection_keys_json, preserved_hashes_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (authorization_id, evidence.operation_id, evidence.idempotency_key, evidence.item_key, evidence.item_version,
                 _canonical_json(evidence.tags), _canonical_json(evidence.collection_keys), _canonical_json(evidence.preserved_field_hashes)),
            )
            self._connection.execute(
                "INSERT INTO operation_ledger(authorization_id, operation_id, state, expected_version, observed_version) VALUES (?, ?, 'attempted', ?, NULL)",
                (authorization_id, evidence.operation_id, evidence.item_version),
            )

    def attempt_evidence_for(self, authorization_id: str, operation_id: str) -> AttemptEvidence | None:
        row = self._connection.execute(
            "SELECT operation_id, idempotency_key, item_key, item_version, tags_json, collection_keys_json, preserved_hashes_json FROM attempt_evidence WHERE authorization_id = ? AND operation_id = ?",
            (authorization_id, operation_id),
        ).fetchone()
        if row is None:
            return None
        return AttemptEvidence(operation_id=row[0], idempotency_key=row[1], item_key=row[2], item_version=row[3], tags=tuple(json.loads(row[4])), collection_keys=tuple(json.loads(row[5])), preserved_field_hashes=json.loads(row[6]))

    def record_managed_provenance(self, authorization_id: str, evidence: AttemptEvidence, *, resource: Literal["tag", "collection"], target: str, verified_version: int) -> None:
        """Record removal ownership only after a verified app-owned add."""
        state = self._connection.execute(
            "SELECT state FROM operation_ledger WHERE authorization_id = ? AND operation_id = ? ORDER BY sequence DESC LIMIT 1",
            (authorization_id, evidence.operation_id),
        ).fetchone()
        if state is None or state[0] != "verified":
            raise ValueError("managed provenance requires verified operation")
        with self._connection:
            self._connection.execute(
                "INSERT INTO managed_provenance(operation_id, authorization_id, item_key, resource, target, verified_version) VALUES (?, ?, ?, ?, ?, ?)",
                (evidence.operation_id, authorization_id, evidence.item_key, resource, target, verified_version),
            )

    def managed_removal_is_authorized(self, operation_id: str, *, item_key: str, resource: Literal["tag", "collection"], target: str, expected_version: int) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM managed_provenance WHERE operation_id = ? AND item_key = ? AND resource = ? AND target = ? AND verified_version = ?",
            (operation_id, item_key, resource, target, expected_version),
        ).fetchone() is not None

    def recover_authorized_plan(
        self, authorization: ApplyAuthorization, mutation_plan: MutationPlan
    ) -> RecoveryReport:
        """Reconcile durable terminal state using SQLite authority alone.

        Recovery accepts neither an unpersisted approval nor a merely matching plan
        hash.  It requires the complete immutable authorization row, then reports
        terminal evidence without calling a mutation port or writing new rows.
        """

        expected = ApplyAuthorization.for_plan(
            mutation_plan, authorization_id=authorization.authorization_id
        )
        if authorization != expected:
            raise ValueError("authorization does not exactly match preview plan")
        row = self._connection.execute(
            "SELECT plan_hash, reviewed_diff_hash, approved_item_keys_json, "
            "approved_operation_ids_json, confirmation_digest, approval_method "
            "FROM apply_authorization WHERE authorization_id = ?",
            (authorization.authorization_id,),
        ).fetchone()
        persisted = (
            authorization.plan_hash,
            authorization.reviewed_diff_hash,
            _canonical_json(authorization.approved_item_keys),
            _canonical_json(authorization.approved_operation_ids),
            authorization.confirmation_digest,
            authorization.approval_method,
        )
        if row != persisted:
            raise ValueError("recovery requires exact persisted immutable authorization")

        entries = self.operation_entries_for(authorization.authorization_id)
        latest: dict[str, OperationLedgerEntry] = {}
        for entry in entries:
            latest[entry.operation_id] = entry
        counts = {
            state: sum(entry.state == state for entry in latest.values())
            for state in ("planned", "attempted", "verified", "skipped_stale", "aborted")
        }
        if counts["skipped_stale"]:
            state: Literal["ready", "verified", "skipped_stale", "aborted"] = "skipped_stale"
        elif counts["aborted"] or counts["attempted"]:
            state = "aborted"
        elif latest and counts["verified"] == len(authorization.approved_operation_ids):
            state = "verified"
        else:
            state = "ready"
        return RecoveryReport(state=state, entries=entries, counts=counts)

    def close(self) -> None:
        self._connection.close()


class InMemoryMutationPort:
    """Test-only local fake that never performs I/O outside process memory."""

    def apply(self, mutation_plan: MutationPlan) -> tuple[DiffEntry, ...]:
        return mutation_plan.expected_diff


class VersionedMutationPort(Protocol):
    """Local-only port used to prove version chaining without connector access."""

    def read_version(self, mutation_plan: MutationPlan) -> int: ...

    def apply_operation(
        self, mutation: Mutation, *, expected_version: int, operation_id: str
    ) -> tuple[DiffEntry, int]: ...

    def read_operation(
        self, mutation: Mutation, *, expected_version: int, operation_id: str
    ) -> tuple[DiffEntry, int] | None:
        """Read back an operation's exact observable result, if it was applied."""


@dataclass(frozen=True)
class OperationLedgerEntry:
    operation_id: str
    state: Literal["planned", "attempted", "verified", "skipped_stale", "aborted"]
    expected_version: int
    observed_version: int | None


@dataclass(frozen=True)
class VersionedApplyResult:
    terminal_state: Literal["verified", "skipped_stale", "aborted"]
    entries: tuple[OperationLedgerEntry, ...]


@dataclass(frozen=True)
class RecoveryReport:
    """SQLite-only restart view; it deliberately contains no mutation port."""

    state: Literal["ready", "verified", "skipped_stale", "aborted"]
    entries: tuple[OperationLedgerEntry, ...]
    counts: dict[str, int]


class ApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actual_diff: tuple[DiffEntry, ...]


def apply_approved_plan(
    mutation_plan: MutationPlan,
    approval: Approval | ApplyAuthorization,
    port: MutationPort,
    ledger: AuditLedger,
) -> ApplyResult:
    """Apply only an approved preview and verify an exact postcondition diff."""

    if approval.plan_hash != mutation_plan.plan_hash:
        raise ValueError("approval does not match preview plan")
    authorization = (
        approval
        if isinstance(approval, ApplyAuthorization)
        else ApplyAuthorization.for_plan(mutation_plan, authorization_id=approval.approved_by)
    )
    if not ledger.persist_authorization_and_plan(authorization, mutation_plan):
        entries = ledger.entries_for(mutation_plan.plan_hash)
        if entries and entries[-1].state == "verified":
            return ApplyResult(
                plan_hash=mutation_plan.plan_hash, actual_diff=mutation_plan.expected_diff
            )
        raise UncertainApplyError("previous approved apply requires explicit read-back")
    ledger.record(mutation_plan.plan_hash, authorization.authorization_id, "attempted")
    actual_diff = tuple(port.apply(mutation_plan))
    if actual_diff != mutation_plan.expected_diff:
        raise ExactDiffMismatch("observed diff does not exactly match approved preview")
    ledger.record(mutation_plan.plan_hash, authorization.authorization_id, "verified")
    return ApplyResult(plan_hash=mutation_plan.plan_hash, actual_diff=actual_diff)


def apply_versioned_plan(
    mutation_plan: MutationPlan,
    authorization: ApplyAuthorization,
    port: VersionedMutationPort,
    ledger: AuditLedger,
) -> VersionedApplyResult:
    """Apply locally one operation at a time, chaining only durable verified versions."""

    if authorization != ApplyAuthorization.for_plan(
        mutation_plan, authorization_id=authorization.authorization_id
    ):
        raise ValueError("authorization does not exactly match preview plan")
    if not ledger.persist_authorization_and_plan(authorization, mutation_plan):
        return _reconcile_persisted_versioned_plan(mutation_plan, authorization, port, ledger)
    expected_version = mutation_plan.source_version
    operations = tuple(
        zip(
            mutation_plan.operation_ids,
            sorted(mutation_plan.mutations, key=lambda item: (item.kind, item.target, item.action)),
            strict=True,
        )
    )
    if port.read_version(mutation_plan) != expected_version:
        for index, (operation_id, _) in enumerate(operations):
            ledger.record_operation(
                authorization.authorization_id,
                operation_id,
                "skipped_stale" if index == 0 else "aborted",
                expected_version,
            )
        return VersionedApplyResult(
            "skipped_stale", ledger.operation_entries_for(authorization.authorization_id)
        )

    for index, (operation_id, mutation) in enumerate(operations):
        ledger.record_operation(
            authorization.authorization_id, operation_id, "planned", expected_version
        )
        ledger.record_operation(
            authorization.authorization_id, operation_id, "attempted", expected_version
        )
        port.apply_operation(mutation, expected_version=expected_version, operation_id=operation_id)
        observed = port.read_operation(
            mutation, expected_version=expected_version, operation_id=operation_id
        )
        if observed is None:
            actual_diff, observed_version = None, None
        else:
            actual_diff, observed_version = observed
        expected_diff = DiffEntry(
            kind=mutation.kind, target=mutation.target, action=mutation.action
        )
        if (
            actual_diff != expected_diff
            or observed_version is None
            or observed_version <= expected_version
        ):
            ledger.record_operation(
                authorization.authorization_id,
                operation_id,
                "aborted",
                expected_version,
                observed_version,
            )
            for remaining_id, _ in operations[index + 1 :]:
                ledger.record_operation(
                    authorization.authorization_id, remaining_id, "aborted", expected_version
                )
            return VersionedApplyResult(
                "aborted", ledger.operation_entries_for(authorization.authorization_id)
            )
        ledger.record_operation(
            authorization.authorization_id,
            operation_id,
            "verified",
            expected_version,
            observed_version,
        )
        expected_version = observed_version
    return VersionedApplyResult(
        "verified", ledger.operation_entries_for(authorization.authorization_id)
    )


def _reconcile_persisted_versioned_plan(
    mutation_plan: MutationPlan,
    authorization: ApplyAuthorization,
    port: VersionedMutationPort,
    ledger: AuditLedger,
) -> VersionedApplyResult:
    """Resolve an interrupted write by read-back only; never replay it."""

    entries = ledger.operation_entries_for(authorization.authorization_id)
    latest = {entry.operation_id: entry for entry in entries}
    operations = tuple(
        zip(
            mutation_plan.operation_ids,
            sorted(mutation_plan.mutations, key=lambda item: (item.kind, item.target, item.action)),
            strict=True,
        )
    )
    if any(entry.state == "skipped_stale" for entry in latest.values()):
        return VersionedApplyResult("skipped_stale", entries)
    if all(
        latest.get(operation_id, None) is not None and latest[operation_id].state == "verified"
        for operation_id, _ in operations
    ):
        return VersionedApplyResult("verified", entries)
    if any(entry.state == "aborted" for entry in latest.values()):
        return VersionedApplyResult("aborted", entries)

    for index, (operation_id, mutation) in enumerate(operations):
        prior = latest.get(operation_id)
        if prior is not None and prior.state == "verified":
            continue
        expected_version = (
            prior.expected_version if prior is not None else mutation_plan.source_version
        )
        observed = (
            port.read_operation(
                mutation, expected_version=expected_version, operation_id=operation_id
            )
            if prior is not None and prior.state == "attempted"
            else None
        )
        if observed is not None:
            actual_diff, observed_version = observed
            expected_diff = DiffEntry(
                kind=mutation.kind, target=mutation.target, action=mutation.action
            )
            if actual_diff == expected_diff and observed_version > expected_version:
                ledger.record_operation(
                    authorization.authorization_id,
                    operation_id,
                    "verified",
                    expected_version,
                    observed_version,
                )
                continue
        ledger.record_operation(
            authorization.authorization_id, operation_id, "aborted", expected_version
        )
        for remaining_id, _ in operations[index + 1 :]:
            if remaining_id not in latest:
                ledger.record_operation(
                    authorization.authorization_id, remaining_id, "aborted", expected_version
                )
        return VersionedApplyResult(
            "aborted", ledger.operation_entries_for(authorization.authorization_id)
        )
    return VersionedApplyResult(
        "verified", ledger.operation_entries_for(authorization.authorization_id)
    )
