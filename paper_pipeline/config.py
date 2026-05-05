from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import PipelineError


class ConfigError(PipelineError):
    """Raised when v2 runtime configuration is invalid."""


@dataclass(frozen=True)
class PathsConfig:
    vault_root: Path
    llm_root: Path
    papers_root: Path
    index_root: Path
    inbox_dir: Path
    templates_dir: Path


@dataclass(frozen=True)
class LMStudioConfig:
    chat_endpoint: str = "http://127.0.0.1:1234/v1/chat/completions"
    embeddings_endpoint: str = "http://127.0.0.1:1234/v1/embeddings"
    analysis_model: str = "qwen/qwen3.5-9b"
    embedding_model: str = ""
    timeout_seconds: int = 1200
    embedding_timeout_seconds: int = 60
    embeddings_enabled: bool = True
    fallback_to_lexical: bool = True
    max_output_tokens: int = 8192
    tolook_max_output_tokens: int = 2048
    tolook_timeout_seconds: int = 1200
    deep_stage_max_output_tokens: int = 8192
    deep_stage_timeout_seconds: int = 2400
    save_payloads: bool = False


@dataclass(frozen=True)
class OperationalCollectionsConfig:
    tolook: list[str] = field(default_factory=lambda: [".ToLook"])
    torevise: list[str] = field(default_factory=lambda: [".To Revise"])
    todig: list[str] = field(default_factory=lambda: [".ToDig", ".To Dig"])
    expendable: list[str] = field(default_factory=lambda: ["Expendable", ".Expendable"])


@dataclass(frozen=True)
class RuntimeConfig:
    paths: PathsConfig
    lmstudio: LMStudioConfig = field(default_factory=LMStudioConfig)
    operational_collections: OperationalCollectionsConfig = field(default_factory=OperationalCollectionsConfig)


def default_config(vault_root: str | Path = ".") -> RuntimeConfig:
    root = Path(vault_root).resolve()
    llm = root / "x" / "LLM"
    return RuntimeConfig(
        paths=PathsConfig(
            vault_root=root,
            llm_root=llm,
            papers_root=llm / "papers",
            index_root=llm / "index",
            inbox_dir=root / "+",
            templates_dir=root / "x" / "Templates",
        )
    )


def load_config(path: str | Path | None = None, *, vault_root: str | Path = ".") -> RuntimeConfig:
    cfg = default_config(vault_root)
    if path is None:
        return cfg
    raw_path = Path(path)
    raw = _load_mapping(raw_path)
    root = _resolve_config_root(raw_path, raw.get("vault_root", cfg.paths.vault_root))
    llm = root / "x" / "LLM"
    paths_raw = dict(raw.get("paths", {}))
    lmstudio_raw = dict(raw.get("lmstudio", {}))
    collections_raw = dict(raw.get("operational_collections", {}))
    return RuntimeConfig(
        paths=PathsConfig(
            vault_root=root,
            llm_root=_resolve(root, paths_raw.get("llm_root", llm)),
            papers_root=_resolve(root, paths_raw.get("papers_root", llm / "papers")),
            index_root=_resolve(root, paths_raw.get("index_root", llm / "index")),
            inbox_dir=_resolve(root, paths_raw.get("inbox_dir", root / "+")),
            templates_dir=_resolve(root, paths_raw.get("templates_dir", root / "x" / "Templates")),
        ),
        lmstudio=LMStudioConfig(**lmstudio_raw),
        operational_collections=OperationalCollectionsConfig(**collections_raw),
    )


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _resolve_config_root(config_path: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (config_path.parent / path).resolve()


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise ConfigError("configuration root must be a mapping")
        return loaded
    except ImportError as exc:
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ConfigError("configuration root must be a mapping") from exc
        return loaded
