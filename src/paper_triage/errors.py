"""Stable, sanitized domain errors and issues."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IssueCode(StrEnum):
    PAPER_TITLE_REQUIRED = "PAPER_TITLE_REQUIRED"
    PAPER_DUPLICATE_IDENTITY = "PAPER_DUPLICATE_IDENTITY"
    PAPER_KIND_AMBIGUOUS = "PAPER_KIND_AMBIGUOUS"
    CONFIDENCE_BELOW_THRESHOLD = "CONFIDENCE_BELOW_THRESHOLD"
    CONFIG_COLLECTION_ROLE_COLLISION = "CONFIG_COLLECTION_ROLE_COLLISION"
    DOI_INVALID = "DOI_INVALID"
    YEAR_INVALID = "YEAR_INVALID"
    AUTHOR_MISSING = "AUTHOR_MISSING"
    CITEKEY_MISSING = "CITEKEY_MISSING"
    CLASSIFICATION_CONFLICT = "CLASSIFICATION_CONFLICT"


class Issue(BaseModel):
    """A stable issue that deliberately excludes raw metadata and secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: IssueCode | str
    message: str = Field(min_length=1, max_length=240)
    context: dict[str, str] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def safe_context(cls, value: dict[str, str]) -> dict[str, str]:
        forbidden = {"token", "secret", "password", "authorization", "api-key", "api_key", "abstract", "payload", "path"}
        if any(key.casefold() in forbidden for key in value):
            raise ValueError("issue context contains a sensitive key")
        return value


class TriageError(ValueError):
    """Base error whose public string is safe to report."""

    def __init__(self, code: IssueCode | str, message: str) -> None:
        self.code = str(code)
        super().__init__(f"{self.code}: {message}")


def redacted_context(**values: Any) -> dict[str, str]:
    """Return only safe scalar diagnostic context, replacing sensitive values."""

    return {key: "[REDACTED]" for key in values}
