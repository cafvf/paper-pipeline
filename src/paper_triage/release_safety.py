"""Local release gate bound to an exact approved preview, never a bare boolean."""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .plans import ApplyRequest, PreviewPlan, canonical_sha256


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
    ) -> str:
        return canonical_sha256(
            {
                "plan_hash": plan_hash,
                "approval_confirmation_digest": approval_confirmation_digest,
                "validation_digest": validation_digest,
                "allowed_tag_targets": allowed_tag_targets,
                "allowed_collection_keys": allowed_collection_keys,
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

    @classmethod
    def _issue(cls, **fields: object) -> ReleaseAuthorization:
        authorization = cls.model_validate(fields)
        authorization._issue_marker = cls._MARKER
        return authorization


def _snapshot_allowlists(plan: PreviewPlan) -> tuple[tuple[str, ...], tuple[str, ...]]:
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
    return tags, collections


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
    tags, collections = _snapshot_allowlists(request.preview_plan)
    validation_digest = request.validation_evidence.validation_digest
    assert validation_digest is not None  # guaranteed by verifies() above
    digest = ReleaseAuthorization.mutation_allowlist_digest_for(
        plan_hash=request.preview_plan.plan_hash,
        approval_confirmation_digest=request.apply_request.approval.confirmation_digest,
        validation_digest=validation_digest,
        allowed_tag_targets=tags,
        allowed_collection_keys=collections,
    )
    return ReleaseAuthorization._issue(
        allowed=True,
        reason="live Zotero access bound to approved plan, validation evidence, and snapshot allowlists",
        plan_hash=request.preview_plan.plan_hash,
        approval_confirmation_digest=request.apply_request.approval.confirmation_digest,
        validation_digest=validation_digest,
        allowed_tag_targets=tags,
        allowed_collection_keys=collections,
        mutation_allowlist_digest=digest,
    )
