"""Read-only, path-contained discovery of Obsidian Efforts project profiles."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    profile_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    display_name: str = Field(min_length=1, max_length=240)
    source_relative_path: str = Field(min_length=1)
    status: Literal["active", "paused", "archived", "unknown"] = "unknown"
    subject_tags: tuple[str, ...] = ()
    method_tags: tuple[str, ...] = ()
    use_tags: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    research_questions: tuple[str, ...] = ()
    modified_at: datetime | None = None
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("source_relative_path")
    @classmethod
    def contained_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("profile path must be relative and contained")
        return value


class EffortsSource(Protocol):
    def discover(self) -> tuple[ProjectProfile, ...]: ...


class ReadOnlyEfforts:
    """Discover markdown files beneath ``root`` without any write capability."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        if not self._root.is_dir() or self._root.is_symlink():
            raise ValueError("Efforts root must be a real directory")

    def discover(self) -> tuple[ProjectProfile, ...]:
        profiles: list[ProjectProfile] = []
        for path in sorted(self._root.rglob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if self._root not in resolved.parents:
                raise ValueError("Efforts file escapes configured root")
            relative = path.relative_to(self._root).as_posix()
            content = path.read_text(encoding="utf-8")
            profiles.append(
                ProjectProfile(
                    profile_id=hashlib.sha256(relative.encode()).hexdigest(),
                    display_name=path.stem,
                    source_relative_path=relative,
                    content_fingerprint=hashlib.sha256(content.encode()).hexdigest(),
                    modified_at=datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
                )
            )
        return tuple(profiles)
