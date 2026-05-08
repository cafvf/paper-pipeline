from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from .contracts import PipelineError


_DEFAULT_VAULT_ROOT = object()


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
    return RuntimeConfig(
        paths=PathsConfig(
            vault_root=root,
            llm_root=root,
            papers_root=root / "papers",
            index_root=root / "index",
            inbox_dir=root / "+",
            templates_dir=root / "templates",
        )
    )


def load_config(
    path: str | Path | None = None,
    *,
    vault_root: str | Path | object = _DEFAULT_VAULT_ROOT,
    env: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    env_mapping = load_env() if env is None else env
    if path is None:
        cfg = default_config("." if vault_root is _DEFAULT_VAULT_ROOT else vault_root)  # type: ignore[arg-type]
        fallback = None if vault_root is _DEFAULT_VAULT_ROOT else cfg.paths.vault_root
        if "VAULT_ROOT" not in env_mapping and "OBSIDIAN_HUMAN_REVIEW_INBOX_DIR" not in env_mapping:
            return cfg
        root, inbox = _obsidian_paths_from_env(env_mapping, fallback_vault_root=fallback)
        return replace(cfg, paths=replace(cfg.paths, vault_root=root, inbox_dir=inbox, templates_dir=root / "templates"))
    cfg = default_config("." if vault_root is _DEFAULT_VAULT_ROOT else vault_root)  # type: ignore[arg-type]
    raw_path = Path(path)
    raw = _load_mapping(raw_path)
    _reject_legacy_obsidian_config(raw)
    config_root = raw_path.parent.resolve()
    paths_raw = dict(raw.get("paths", {}))
    llm = _resolve(config_root, paths_raw.get("llm_root", config_root))
    fallback = None if vault_root is _DEFAULT_VAULT_ROOT else cfg.paths.vault_root
    root, inbox = _obsidian_paths_from_env(env_mapping, fallback_vault_root=fallback)
    lmstudio_raw = dict(raw.get("lmstudio", {}))
    collections_raw = dict(raw.get("operational_collections", {}))
    return RuntimeConfig(
        paths=PathsConfig(
            vault_root=root,
            llm_root=llm,
            papers_root=_resolve(config_root, paths_raw.get("papers_root", llm / "papers")),
            index_root=_resolve(config_root, paths_raw.get("index_root", llm / "index")),
            inbox_dir=inbox,
            templates_dir=_resolve(root, paths_raw.get("templates_dir", root / "templates")),
        ),
        lmstudio=LMStudioConfig(**lmstudio_raw),
        operational_collections=OperationalCollectionsConfig(**collections_raw),
    )


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def load_env(path: str | Path = ".env", *, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    values = _read_env_file(Path(path))
    values.update(dict(os.environ if base_env is None else base_env))
    return values


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise ConfigError(f"invalid .env line without '=': {raw!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError("invalid .env line with empty key")
        values[key] = _clean_env_value(value.strip())
    return values


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _obsidian_paths_from_env(env: Mapping[str, str], *, fallback_vault_root: Path | None = None) -> tuple[Path, Path]:
    raw_vault_root = env.get("VAULT_ROOT")
    if raw_vault_root:
        vault_root = Path(raw_vault_root)
        if not vault_root.is_absolute():
            raise ConfigError("VAULT_ROOT must be an absolute path")
        vault_root = vault_root.resolve()
    elif fallback_vault_root is not None:
        vault_root = Path(fallback_vault_root).resolve()
    else:
        raise ConfigError("VAULT_ROOT is required")

    raw_inbox = env.get("OBSIDIAN_HUMAN_REVIEW_INBOX_DIR")
    if raw_inbox:
        inbox = Path(raw_inbox)
        inbox = inbox.resolve() if inbox.is_absolute() else (vault_root / inbox).resolve()
    else:
        inbox = vault_root / "+"
    return vault_root, inbox


def _reject_legacy_obsidian_config(raw: dict[str, Any]) -> None:
    if "vault_root" in raw:
        raise ConfigError("vault_root belongs in VAULT_ROOT, not config YAML")
    if "PAPERS_DIR" in raw:
        raise ConfigError("PAPERS_DIR is not a supported config field")
    paths_raw = raw.get("paths", {})
    if not isinstance(paths_raw, dict):
        raise ConfigError("paths must be a mapping")
    for key in ("inbox_dir", "templates_dir"):
        if key in paths_raw:
            raise ConfigError(f"paths.{key} belongs in environment/Obsidian policy, not config YAML")


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
