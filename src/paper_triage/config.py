"""Validated, secret-free configuration snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import IssueCode, TriageError

CONFIDENCE_THRESHOLD = Decimal("0.8500")
STAGE_PATHS = {"look": ".ToLook", "review": ".ToRevise", "dig": ".ToDig"}


class StageCollections(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    look: str = Field(min_length=1)
    review: str = Field(min_length=1)
    dig: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct(self) -> StageCollections:
        if len({self.look, self.review, self.dig}) != 3:
            raise TriageError(
                IssueCode.CONFIG_COLLECTION_ROLE_COLLISION, "stage collection keys collide"
            )
        return self


class TriageConfig(BaseModel):
    """Configuration allowed to enter deterministic hashes; no credentials belong here."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: str = "1.0"
    taxonomy_version: str = "1.0.0"
    ruleset_version: str = "1.0.0"
    confidence_threshold: Decimal = CONFIDENCE_THRESHOLD
    stage_collections: StageCollections
    by_subject: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    credible_venues: tuple[str, ...] = ()
    credible_authors: tuple[str, ...] = ()

    @field_validator("confidence_threshold")
    @classmethod
    def threshold_is_fixed(cls, value: Decimal) -> Decimal:
        if value != CONFIDENCE_THRESHOLD:
            raise ValueError("confidence threshold must be 0.8500")
        return value

    @model_validator(mode="after")
    def collection_roles_do_not_collide(self) -> TriageConfig:
        roots = {
            self.stage_collections.look,
            self.stage_collections.review,
            self.stage_collections.dig,
        }
        destinations = [key for keys in self.by_subject.values() for key in keys]
        if roots.intersection(destinations):
            raise TriageError(
                IssueCode.CONFIG_COLLECTION_ROLE_COLLISION, "stage and BySubject keys collide"
            )
        return self
