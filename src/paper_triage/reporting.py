"""Minimal sanitized local run-report contract."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import Issue


class RunCounters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    operations_planned: int = Field(ge=0)
    operations_attempted: int = Field(ge=0)
    operations_verified: int = Field(ge=0)
    operations_failed: int = Field(ge=0)
    operations_uncertain: int = Field(ge=0)
    operations_skipped_stale: int = Field(ge=0)
    operations_aborted: int = Field(ge=0)

    @model_validator(mode="after")
    def reconcile(self) -> RunCounters:
        terminal = self.operations_verified + self.operations_failed + self.operations_uncertain + self.operations_skipped_stale + self.operations_aborted
        if self.operations_attempted < terminal or self.operations_planned < self.operations_attempted:
            raise ValueError("run operation counters are inconsistent")
        return self

class ItemRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    item_key: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    issues: tuple[Issue, ...] = ()

class RunReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID = Field(default_factory=uuid4)
    mode: Literal["preview", "apply", "reclassify"]
    status: Literal["success", "partial", "failed"]
    started_at: datetime
    finished_at: datetime
    ruleset_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    plan_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    selected_item_count: int = Field(ge=0)
    item_results: tuple[ItemRunResult, ...] = ()
    counters: RunCounters
    issues: tuple[Issue, ...] = ()
    redaction_summary: dict[str, int] = {}

    @model_validator(mode="after")
    def valid_times_and_count(self) -> RunReport:
        if self.finished_at < self.started_at:
            raise ValueError("report timestamps must be monotonic")
        if len({item.item_key for item in self.item_results}) != len(self.item_results):
            raise ValueError("report item keys must be unique")
        if self.selected_item_count != len(self.item_results):
            raise ValueError("report item count must match item results")
        if self.mode != "preview" and self.plan_hash is None:
            raise ValueError("apply and reclassify reports require plan hash")
        return self
