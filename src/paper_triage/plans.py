"""Canonical, immutable ten-item preview and approval contracts.

These data-only contracts intentionally have no connector, credential, or I/O
capability.  Their hashes are the local authority boundary for later stages.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _normalise(value: object) -> object:
    """Return a deterministic JSON-compatible projection without mutating input."""
    if isinstance(value, BaseModel):
        return _normalise(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _normalise(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_normalise(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def canonical_json(value: object) -> str:
    """Compact stable JSON used by all local plan digests."""
    return json.dumps(_normalise(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Snapshot(BaseModel):
    """A complete by-value snapshot with its independently checkable digest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    value: object
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def digest_matches_value(self) -> Snapshot:
        if self.digest != canonical_sha256(self.value):
            raise ValueError("snapshot digest does not match its value")
        return self


class PreviewVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["preview_version"] = "preview_version"
    version: int = Field(ge=0)


class VerifiedVersionOf(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["verified_version_of"] = "verified_version_of"
    operation_id: str = Field(pattern=r"^[a-f0-9]{64}$")


VersionPrecondition = Annotated[PreviewVersion | VerifiedVersionOf, Field(discriminator="kind")]


class PlannedOperation(BaseModel):
    """One deterministic, item-local, symbolic mutation proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    operation_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    sequence: int = Field(ge=0)
    depends_on: tuple[str, ...] = ()
    resource_type: Literal["tag", "collection"]
    action: Literal["add", "remove"]
    target: str = Field(min_length=1)
    before_present: bool
    after_present: bool
    version_precondition: VersionPrecondition
    ownership_mutation_id: str | None = None
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    @classmethod
    def build(cls, **fields: object) -> PlannedOperation:
        payload = dict(fields)
        payload.setdefault("depends_on", ())
        payload.setdefault("ownership_mutation_id", None)
        payload.setdefault("reason_codes", ())
        payload.setdefault("evidence_refs", ())
        payload["operation_id"] = canonical_sha256(payload)
        return cls.model_validate(payload)

    @model_validator(mode="after")
    def valid_operation(self) -> PlannedOperation:
        if self.before_present == self.after_present:
            raise ValueError("operation must change target presence")
        if self.action == "add" and (self.before_present or not self.after_present):
            raise ValueError("add must change absent target to present")
        if self.action == "remove" and (not self.before_present or self.after_present):
            raise ValueError("remove must change present target to absent")
        if self.resource_type == "tag" and self.target.startswith(("$", "!")):
            raise ValueError("advisory tags are not writable")
        if self.action == "remove" and self.ownership_mutation_id is None:
            raise ValueError("remove requires managed ownership evidence")
        expected = canonical_sha256(self.hash_projection())
        if self.operation_id != expected:
            raise ValueError("operation id does not match canonical operation")
        return self

    def hash_projection(self) -> dict[str, object]:
        return self.model_dump(exclude={"operation_id"}, mode="json")


class PlannedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    item_key: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_item_version: int = Field(ge=0)
    classification_projection: dict[str, object]
    tag_decisions: tuple[object, ...] = ()
    collection_decisions: tuple[object, ...] = ()
    operations: tuple[PlannedOperation, ...] = Field(min_length=1)
    blockers: tuple[object, ...] = ()

    @model_validator(mode="after")
    def operations_are_canonical_item_local_chain(self) -> PlannedItem:
        ids = tuple(operation.operation_id for operation in self.operations)
        if len(set(ids)) != len(ids):
            raise ValueError("operation ids must be unique per item")
        for index, operation in enumerate(self.operations):
            if operation.sequence != index:
                raise ValueError("operations must use contiguous canonical sequence")
            if index == 0:
                if not isinstance(operation.version_precondition, PreviewVersion):
                    raise ValueError("first operation must use the preview version")
                if operation.version_precondition.version != self.preview_item_version:
                    raise ValueError("preview version must match item preview version")
                if operation.depends_on:
                    raise ValueError("first operation cannot depend on another operation")
            else:
                previous = self.operations[index - 1].operation_id
                if not isinstance(operation.version_precondition, VerifiedVersionOf) or (
                    operation.version_precondition.operation_id != previous
                ):
                    raise ValueError("operation must depend on immediately preceding verification")
                if operation.depends_on != (previous,):
                    raise ValueError("operation dependencies must be the preceding item operation")
        return self


class PreviewPlan(BaseModel):
    """The complete immutable preview; exactly ten selected items are authorized."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"] = "1.0"
    preview_id: str = Field(min_length=1)
    created_at: datetime
    run_date: date
    selected_item_keys: tuple[str, ...] = Field(min_length=10, max_length=10)
    library_scope: dict[str, object]
    config_snapshot: Snapshot
    collection_snapshot: Snapshot
    project_profile_snapshot: Snapshot
    ruleset_snapshot: Snapshot
    taxonomy_snapshot: Snapshot
    items: tuple[PlannedItem, ...] = Field(min_length=10, max_length=10)
    reviewed_diff_projection: tuple[dict[str, object], ...]
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    issues: tuple[object, ...] = ()

    @staticmethod
    def reviewed_diff_for(items: tuple[PlannedItem, ...]) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "item_key": item.item_key,
                "operation_id": operation.operation_id,
                "sequence": operation.sequence,
                "resource_type": operation.resource_type,
                "action": operation.action,
                "target": operation.target,
                "before_present": operation.before_present,
                "after_present": operation.after_present,
                "ownership_mutation_id": operation.ownership_mutation_id,
                "reason_codes": operation.reason_codes,
                "evidence_refs": operation.evidence_refs,
                "version_precondition": operation.version_precondition.model_dump(mode="json"),
            }
            for item in sorted(items, key=lambda value: value.item_key)
            for operation in item.operations
        )

    @property
    def reviewed_diff_hash(self) -> str:
        return canonical_sha256(self.reviewed_diff_projection)

    @classmethod
    def plan_hash_for(cls, **fields: object) -> str:
        payload = dict(fields)
        payload.pop("plan_hash", None)
        payload.pop("preview_id", None)
        payload.pop("created_at", None)
        payload.pop("issues", None)
        payload.setdefault("schema_version", "1.0")
        return canonical_sha256(payload)

    @model_validator(mode="after")
    def immutable_canonical_preview(self) -> PreviewPlan:
        item_keys = tuple(item.item_key for item in self.items)
        if self.selected_item_keys != tuple(sorted(self.selected_item_keys)):
            raise ValueError("selected item keys must be sorted")
        if len(set(self.selected_item_keys)) != 10 or self.selected_item_keys != item_keys:
            raise ValueError("selected item keys must exactly match the ten planned items")
        if item_keys != tuple(sorted(item_keys)):
            raise ValueError("planned items must be sorted by item key")
        if self.reviewed_diff_projection != self.reviewed_diff_for(self.items):
            raise ValueError("reviewed diff projection does not exactly match planned operations")
        expected = self.plan_hash_for(**self.model_dump(exclude={"plan_hash"}, mode="python"))
        if self.plan_hash != expected:
            raise ValueError("plan hash does not match canonical preview")
        return self


class ApprovalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    approval_id: str = Field(min_length=1)
    approved_plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_at: datetime
    approval_method: Literal["local_interactive"] = "local_interactive"
    approved_item_keys: tuple[str, ...] = Field(min_length=10, max_length=10)
    reviewed_operation_ids: tuple[str, ...] = Field(min_length=1)
    reviewed_diff_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @staticmethod
    def confirmation_digest_for(
        plan_hash: str, diff_hash: str, item_keys: tuple[str, ...], operation_ids: tuple[str, ...]
    ) -> str:
        message = "APPLY\n" + plan_hash + "\n" + diff_hash + "\n"
        message += "\n".join(item_keys) + "\n" + "\n".join(operation_ids)
        return hashlib.sha256(message.encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, **fields: object) -> ApprovalEvidence:
        payload = dict(fields)
        payload["confirmation_digest"] = cls.confirmation_digest_for(
            payload["approved_plan_hash"],  # type: ignore[arg-type]
            payload["reviewed_diff_hash"],  # type: ignore[arg-type]
            payload["approved_item_keys"],  # type: ignore[arg-type]
            payload["reviewed_operation_ids"],  # type: ignore[arg-type]
        )
        return cls.model_validate(payload)

    @model_validator(mode="after")
    def canonical_evidence(self) -> ApprovalEvidence:
        if self.approved_item_keys != tuple(sorted(set(self.approved_item_keys))):
            raise ValueError("approved item keys must be sorted and unique")
        if len(set(self.reviewed_operation_ids)) != len(self.reviewed_operation_ids):
            raise ValueError("reviewed operation ids must be unique")
        expected = self.confirmation_digest_for(
            self.approved_plan_hash,
            self.reviewed_diff_hash,
            self.approved_item_keys,
            self.reviewed_operation_ids,
        )
        if self.confirmation_digest != expected:
            raise ValueError("confirmation digest does not bind approval")
        return self


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"] = "1.0"
    preview_id: str = Field(min_length=1)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval: ApprovalEvidence

    def validates(self, plan: PreviewPlan) -> bool:
        operation_ids = tuple(
            operation.operation_id for item in plan.items for operation in item.operations
        )
        if self.preview_id != plan.preview_id or self.plan_hash != plan.plan_hash:
            raise ValueError("apply request does not match preview")
        if self.approval.approved_plan_hash != plan.plan_hash:
            raise ValueError("approval does not match plan hash")
        if self.approval.approved_item_keys != plan.selected_item_keys:
            raise ValueError("approval does not match selected items")
        if self.approval.reviewed_operation_ids != operation_ids:
            raise ValueError("approval does not match planned operations")
        if self.approval.reviewed_diff_hash != plan.reviewed_diff_hash:
            raise ValueError("approval does not match reviewed diff")
        return True
