"""Local release gate bound to an exact approved preview, never a bare boolean."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from .plans import ApplyRequest, PreviewPlan, PreviewVersion, canonical_sha256


class ReleaseMode(str, Enum):
    DRY_RUN = "dry_run"
    LIVE = "live"


class ValidationEvidence(BaseModel):
    """Hashable local validation evidence for one exact immutable plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    plan_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    checks: tuple[str, ...] = ()
    validation_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    # Legacy fields remain parseable but never authorize a live release.
    all_required_passed: bool | None = None
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=500)

    @classmethod
    def create(cls, *, plan_hash: str, checks: tuple[str, ...]) -> ValidationEvidence:
        return cls(
            plan_hash=plan_hash,
            checks=checks,
            validation_digest=canonical_sha256({"plan_hash": plan_hash, "checks": checks}),
        )

    def verifies(self) -> bool:
        return self.plan_hash is not None and self.validation_digest == canonical_sha256(
            {"plan_hash": self.plan_hash, "checks": self.checks}
        )


class ReleaseRequest(BaseModel):
    """All artifacts required to decide a release locally; no connector imports."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    mode: ReleaseMode = ReleaseMode.DRY_RUN
    human_approved: bool = False
    preview_plan: PreviewPlan | None = None
    apply_request: ApplyRequest | None = None
    validation_evidence: ValidationEvidence | None = None


class ApprovedMutation(BaseModel):
    """One complete mutation identity projected from the reviewed preview.

    A target is deliberately insufficient authority: the same tag or collection
    may occur on several items, and a caller must not be able to substitute an
    operation with a more convenient action or membership expectation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    operation_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    item_key: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")
    resource: str
    action: str
    target: str = Field(min_length=1)
    expected_present: bool
    desired_present: bool
    # Only a first operation has a fixed version in the preview.  Later
    # operations are bound to the verified result of their predecessor.
    expected_version: int | None = Field(default=None, ge=0)


class ReleaseAuthorization(BaseModel):
    """A process-local capability bound to one reviewed preview snapshot.

    The target allowlists are a projection of the exact plan whose approval and
    validation digests are present below.  They are intentionally not constructor
    arguments to the Zotero adapter: that would let a caller widen a review after
    approval.  ``authorize`` marks an instance as issued for the current process;
    deserialized or hand-built model values are data, not a live write capability.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    allowed: bool
    reason: str = Field(min_length=1)
    plan_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    approval_confirmation_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    validation_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    allowed_tag_targets: tuple[str, ...] = ()
    allowed_collection_keys: tuple[str, ...] = ()
    approved_mutations: tuple[ApprovedMutation, ...] = ()
    mutation_allowlist_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    _issue_marker: object | None = PrivateAttr(default=None)
    _MARKER: ClassVar[object] = object()

    @staticmethod
    def mutation_allowlist_digest_for(
        *,
        plan_hash: str,
        approval_confirmation_digest: str,
        validation_digest: str,
        allowed_tag_targets: tuple[str, ...],
        allowed_collection_keys: tuple[str, ...],
        approved_mutations: tuple[ApprovedMutation, ...],
    ) -> str:
        return canonical_sha256(
            {
                "plan_hash": plan_hash,
                "approval_confirmation_digest": approval_confirmation_digest,
                "validation_digest": validation_digest,
                "allowed_tag_targets": allowed_tag_targets,
                "allowed_collection_keys": allowed_collection_keys,
                "approved_mutations": [
                    mutation.model_dump(mode="json") for mutation in approved_mutations
                ],
            }
        )

    @property
    def is_bound(self) -> bool:
        if not self.allowed or not all(
            (self.plan_hash, self.approval_confirmation_digest, self.validation_digest)
        ):
            return False
        if (
            self.allowed_tag_targets != tuple(sorted(set(self.allowed_tag_targets)))
            or self.allowed_collection_keys != tuple(sorted(set(self.allowed_collection_keys)))
            or self.mutation_allowlist_digest is None
            or self.approved_mutations != tuple(
                sorted(self.approved_mutations, key=_approved_mutation_sort_key)
            )
            or len(set(self.approved_mutations)) != len(self.approved_mutations)
        ):
            return False
        plan_hash = self.plan_hash
        approval_digest = self.approval_confirmation_digest
        validation_digest = self.validation_digest
        if plan_hash is None or approval_digest is None or validation_digest is None:
            return False
        return self.mutation_allowlist_digest == self.mutation_allowlist_digest_for(
            plan_hash=plan_hash,
            approval_confirmation_digest=approval_digest,
            validation_digest=validation_digest,
            allowed_tag_targets=self.allowed_tag_targets,
            allowed_collection_keys=self.allowed_collection_keys,
            approved_mutations=self.approved_mutations,
        )

    @property
    def is_issued(self) -> bool:
        """Whether this was produced by the local release gate in this process."""
        return self.is_bound and self._issue_marker is self._MARKER

    def permits_target(self, resource: str, target: str) -> bool:
        if not self.is_issued:
            return False
        return target in (
            self.allowed_tag_targets if resource == "tag" else self.allowed_collection_keys
        )

    def permits_operation(
        self,
        *,
        operation_id: str,
        idempotency_key: str,
        item_key: str,
        expected_version: int,
        resource: str,
        action: str,
        target: str,
        expected_present: bool,
        desired_present: bool,
    ) -> bool:
        """Check the complete reviewed identity, never a global target alone."""
        if not self.is_issued:
            return False
        try:
            candidate = ApprovedMutation(
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                item_key=item_key,
                resource=resource,
                action=action,
                target=target,
                expected_present=expected_present,
                desired_present=desired_present,
            )
        except ValidationError:
            return False
        for approved in self.approved_mutations:
            if candidate.model_copy(update={"expected_version": approved.expected_version}) != approved:
                continue
            return approved.expected_version is None or approved.expected_version == expected_version
        return False

    @classmethod
    def _issue(cls, **fields: object) -> ReleaseAuthorization:
        authorization = cls.model_validate(fields)
        authorization._issue_marker = cls._MARKER
        return authorization


def _approved_mutation_sort_key(mutation: ApprovedMutation) -> tuple[str, str]:
    return mutation.item_key, mutation.operation_id


def _snapshot_allowlists(
    plan: PreviewPlan,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[ApprovedMutation, ...]]:
    """Project only reviewed mutation targets from the immutable plan snapshot."""
    tags = tuple(
        sorted(
            {
                operation.target
                for item in plan.items
                for operation in item.operations
                if operation.resource_type == "tag"
            }
        )
    )
    collections = tuple(
        sorted(
            {
                operation.target
                for item in plan.items
                for operation in item.operations
                if operation.resource_type == "collection"
            }
        )
    )
    mutations = tuple(
        sorted(
            (
                ApprovedMutation(
                    operation_id=operation.operation_id,
                    idempotency_key=hashlib.sha256(
                        f"{plan.plan_hash}:{operation.operation_id}".encode()
                    ).hexdigest(),
                    item_key=item.item_key,
                    resource=operation.resource_type,
                    action=operation.action,
                    target=operation.target,
                    expected_present=operation.before_present,
                    desired_present=operation.after_present,
                    expected_version=(
                        operation.version_precondition.version
                        if isinstance(operation.version_precondition, PreviewVersion)
                        else None
                    ),
                )
                for item in plan.items
                for operation in item.operations
            ),
            key=_approved_mutation_sort_key,
        )
    )
    return tags, collections, mutations


def authorize(request: ReleaseRequest) -> ReleaseAuthorization:
    """Fail closed until approval, plan, validation, and snapshot targets all bind."""
    if request.mode is ReleaseMode.DRY_RUN:
        return ReleaseAuthorization(allowed=False, reason="dry-run mode does not authorize live Zotero access")
    if request.preview_plan is None or request.apply_request is None:
        return ReleaseAuthorization(allowed=False, reason="live Zotero access requires an approved preview plan")
    if request.validation_evidence is None:
        return ReleaseAuthorization(allowed=False, reason="live Zotero access requires validation evidence")
    if not request.human_approved:
        return ReleaseAuthorization(allowed=False, reason="live Zotero access requires explicit human approval")
    try:
        request.apply_request.validates(request.preview_plan)
    except ValueError:
        return ReleaseAuthorization(allowed=False, reason="live Zotero access requires matching plan approval")
    if (
        request.validation_evidence.plan_hash != request.preview_plan.plan_hash
        or not request.validation_evidence.verifies()
    ):
        return ReleaseAuthorization(allowed=False, reason="live Zotero access requires matching validation evidence")
    tags, collections, mutations = _snapshot_allowlists(request.preview_plan)
    validation_digest = request.validation_evidence.validation_digest
    assert validation_digest is not None  # guaranteed by verifies() above
    digest = ReleaseAuthorization.mutation_allowlist_digest_for(
        plan_hash=request.preview_plan.plan_hash,
        approval_confirmation_digest=request.apply_request.approval.confirmation_digest,
        validation_digest=validation_digest,
        allowed_tag_targets=tags,
        allowed_collection_keys=collections,
        approved_mutations=mutations,
    )
    return ReleaseAuthorization._issue(
        allowed=True,
        reason="live Zotero access bound to approved plan, validation evidence, and snapshot allowlists",
        plan_hash=request.preview_plan.plan_hash,
        approval_confirmation_digest=request.apply_request.approval.confirmation_digest,
        validation_digest=validation_digest,
        allowed_tag_targets=tags,
        allowed_collection_keys=collections,
        approved_mutations=mutations,
        mutation_allowlist_digest=digest,
    )
