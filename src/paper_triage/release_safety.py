"""Local release gate bound to an exact approved preview, never a bare boolean."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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
    """A verifiable capability binding live access to one approved plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    allowed: bool
    reason: str = Field(min_length=1)
    plan_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    approval_confirmation_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    validation_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @property
    def is_bound(self) -> bool:
        return self.allowed and all(
            (self.plan_hash, self.approval_confirmation_digest, self.validation_digest)
        )


def authorize(request: ReleaseRequest) -> ReleaseAuthorization:
    """Fail closed until approval, plan, and validation all bind byte-for-byte."""
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
    return ReleaseAuthorization(
        allowed=True,
        reason="live Zotero access bound to approved plan and validation evidence",
        plan_hash=request.preview_plan.plan_hash,
        approval_confirmation_digest=request.apply_request.approval.confirmation_digest,
        validation_digest=request.validation_evidence.validation_digest,
    )
