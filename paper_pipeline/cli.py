from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis_engine import LocalPaperAnalyzer
from .citekey_resolver import resolve_citekey_from_vault
from .config import load_config, load_env
from .contracts import PipelineError, Stage
from .export_review import (
    default_review_date,
    default_review_id,
    default_review_output_path,
    run_export_review_from_jsonl,
)
from .lmstudio_chat import LMStudioChatClient
from .obsidian_inventory import main as obsidian_inventory_main
from .project_paper_classification import run_classify_from_jsonl
from .project_paper_matching import run_match_from_jsonl
from .registry import sync_registry_from_jsonl
from .runner import run_once
from .selection import select_batch
from .vault_index import build_lexical_index
from .zotero_api import ZoteroApiAdapter, ZoteroApiError
from .zotero_collections import resolve_operational_collections
from .zotero_inventory import main as zotero_inventory_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--vault-root", default=None)
    run.add_argument("--config", default=None)
    run.add_argument("--max-total", type=int, default=10)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--packet-max-chars", type=int, default=20000)
    run.add_argument("--max-attempts", type=int, default=1)
    run.add_argument("--lm-timeout-seconds", type=int, default=None)
    run.add_argument("--max-output-tokens", type=int, default=None)
    run.add_argument("--save-llm-payloads", action="store_true")
    run.add_argument("--stage", choices=["tolook", "torevise", "todig"], default=None)
    run.add_argument("--citekey", default=None)
    zotero = sub.add_parser("zotero-dry-run")
    zotero.add_argument("--max-total", type=int, default=10)
    scan_obsidian = sub.add_parser("scan-obsidian")
    scan_obsidian.add_argument("--vault-root", default=None)
    scan_obsidian.add_argument("--output", default="data/projects.jsonl")
    scan_zotero = sub.add_parser("scan-zotero")
    scan_zotero.add_argument("--offline-fixture", default=None)
    scan_zotero.add_argument("--output", default="data/papers.jsonl")
    scan_zotero.add_argument("--papers-root", default="papers")
    sync_registry = sub.add_parser("sync-registry")
    sync_registry.add_argument("--db", default="data/registry/registry.sqlite")
    sync_registry.add_argument("--projects", default="data/projects.jsonl")
    sync_registry.add_argument("--papers", default="data/papers.jsonl")
    match = sub.add_parser("match")
    match.add_argument("--projects", default="data/projects.jsonl")
    match.add_argument("--papers", default="data/papers.jsonl")
    match.add_argument("--output", default="data/candidates.jsonl")
    match.add_argument("--top-n", type=int, default=20)
    match.add_argument("--max-candidates-total", type=int, default=None)
    match.add_argument("--paper-stages", default=None)
    match.add_argument("--include-states", default="on,ongoing")
    match.add_argument("--registry-db", default=None)
    classify = sub.add_parser("classify")
    classify.add_argument("--vault-root", default=None)
    classify.add_argument("--config", default=None)
    classify.add_argument("--candidates", default="data/candidates.jsonl")
    classify.add_argument("--projects", default="data/projects.jsonl")
    classify.add_argument("--papers", default="data/papers.jsonl")
    classify.add_argument("--output", default="data/classifications.jsonl")
    classify.add_argument("--max-candidates", type=int, default=None)
    classify.add_argument("--paper-stages", default=None)
    classify.add_argument("--max-attempts", type=int, default=2)
    classify.add_argument("--lm-timeout-seconds", type=int, default=None)
    classify.add_argument("--max-output-tokens", type=int, default=None)
    classify.add_argument("--save-llm-payloads", action="store_true")
    export_review = sub.add_parser("export-review")
    export_review.add_argument(
        "--classifications", default="data/classifications.jsonl"
    )
    export_review.add_argument("--output", default=None)
    export_review.add_argument("--date", default=None)
    export_review.add_argument("--review-id", default=None)
    pilot = sub.add_parser("pilot-run")
    pilot.add_argument("--vault-root", default=None)
    pilot.add_argument("--config", default=None)
    pilot.add_argument("--max-total", type=int, default=1)
    pilot.add_argument("--packet-max-chars", type=int, default=20000)
    pilot.add_argument("--max-attempts", type=int, default=1)
    pilot.add_argument("--lm-timeout-seconds", type=int, default=None)
    pilot.add_argument("--max-output-tokens", type=int, default=None)
    pilot.add_argument("--save-llm-payloads", action="store_true")
    pilot.add_argument("--stage", choices=["tolook", "torevise", "todig"], default=None)
    pilot.add_argument("--citekey", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _run_cycle(args)
    if args.command == "zotero-dry-run":
        adapter = ZoteroApiAdapter.from_env()
        candidates = adapter.list_candidates()
        batch = select_batch(candidates, {"notes": []}, max_total=args.max_total)
        _safe_print(
            f"candidates={len(candidates)} selected={len(batch['selected'])} blocked_missing_pdf={len(batch['blocked_missing_pdf'])}"
        )
        for entry in batch["selected"]:
            candidate = entry["candidate"]
            _safe_print(
                f"SELECT {candidate.stage.value} {candidate.citekey} pdf={candidate.has_pdf} score={entry['score']} title={candidate.title}"
            )
        for entry in batch["blocked_missing_pdf"]:
            candidate = entry["candidate"]
            _safe_print(
                f"BLOCKED_MISSING_PDF {candidate.stage.value} {candidate.citekey} title={candidate.title}"
            )
        return 0
    if args.command == "scan-obsidian":
        try:
            vault_root = _scan_obsidian_vault_root(args.vault_root)
        except PipelineError as exc:
            print(f"scan-obsidian error: {exc}", file=sys.stderr)
            return 2
        return obsidian_inventory_main(
            ["--vault-root", str(vault_root), "--output", args.output]
        )
    if args.command == "scan-zotero":
        inventory_args = ["--output", args.output, "--papers-root", args.papers_root]
        if args.offline_fixture:
            inventory_args.extend(["--offline-fixture", args.offline_fixture])
        return zotero_inventory_main(inventory_args)
    if args.command == "sync-registry":
        try:
            report = sync_registry_from_jsonl(
                args.db, projects_path=args.projects, papers_path=args.papers
            )
        except PipelineError as exc:
            print(f"sync-registry error: {exc}", file=sys.stderr)
            return 2
        _safe_print(
            "projects "
            f"inserted={report.projects.inserted} updated={report.projects.updated} unchanged={report.projects.unchanged}"
        )
        _safe_print(
            "papers "
            f"inserted={report.papers.inserted} updated={report.papers.updated} unchanged={report.papers.unchanged}"
        )
        for warning in report.warnings:
            _safe_print(f"WARNING {warning}")
        return 0
    if args.command == "match":
        try:
            candidates, report = run_match_from_jsonl(
                projects_path=args.projects,
                papers_path=args.papers,
                output_path=args.output,
                include_states=_split_csv(args.include_states),
                paper_stages=_split_stage_csv(args.paper_stages),
                top_n=args.top_n,
                max_candidates_total=args.max_candidates_total,
                registry_db=args.registry_db,
            )
        except PipelineError as exc:
            print(_match_error_message(str(exc)), file=sys.stderr)
            return 2
        _safe_print(
            f"candidates={len(candidates)} skipped_pairs={report.skipped_pairs} output={args.output}"
        )
        for warning in report.warnings:
            _safe_print(f"WARNING {warning}")
        return 0
    if args.command == "classify":
        try:
            config = _load_cli_config(args.config, args.vault_root)
            if args.lm_timeout_seconds is not None:
                config = _with_lm_timeout(config, args.lm_timeout_seconds)
            if args.max_output_tokens is not None:
                config = _with_max_output_tokens(config, args.max_output_tokens)
            if args.save_llm_payloads:
                config = _with_save_lm_payloads(config)
            classifications = run_classify_from_jsonl(
                candidates_path=args.candidates,
                projects_path=args.projects,
                papers_path=args.papers,
                output_path=args.output,
                client=LMStudioChatClient(config.lmstudio),
                max_attempts=args.max_attempts,
                paper_stages=_split_stage_csv(args.paper_stages),
                max_candidates=args.max_candidates,
                progress_callback=_report_classify_progress,
            )
        except PipelineError as exc:
            print(_classify_error_message(str(exc)), file=sys.stderr)
            return 2
        _safe_print(f"classifications={len(classifications)} output={args.output}")
        return 0
    if args.command == "export-review":
        review_date = args.date or default_review_date()
        review_id = args.review_id or default_review_id(review_date)
        output_path = args.output or default_review_output_path(review_date)
        try:
            result = run_export_review_from_jsonl(
                classifications_path=args.classifications,
                output_path=output_path,
                review_id=review_id,
                review_date=review_date,
            )
        except PipelineError as exc:
            print(f"export-review error: {exc}", file=sys.stderr)
            return 2
        _safe_print(f"review_items={result.review_items} output={result.output_path}")
        return 0
    if args.command == "pilot-run":
        return _run_cycle(args)
    return 2


class _NoopSource:
    def list_candidates(self):
        return []


class _StageFilteredSource:
    def __init__(self, source, stage):
        self.source = source
        self.stage = stage

    def list_candidates(self):
        candidates = self.source.list_candidates()
        if self.stage is None:
            return candidates
        return [candidate for candidate in candidates if candidate.stage == self.stage]


class _VaultCitekeySource:
    def __init__(self, source, vault_root):
        self.source = source
        self.vault_root = vault_root

    def list_candidates(self):
        candidates = self.source.list_candidates()
        for candidate in candidates:
            resolved = resolve_citekey_from_vault(
                self.vault_root, doi=candidate.doi, title=candidate.title
            )
            if resolved:
                object.__setattr__(candidate, "citekey", resolved)
        return candidates


class _CitekeyFilteredSource:
    def __init__(self, source, citekey: str | None):
        self.source = source
        self.citekey = citekey

    def list_candidates(self):
        candidates = self.source.list_candidates()
        if not self.citekey:
            return candidates
        return [
            candidate for candidate in candidates if candidate.citekey == self.citekey
        ]


def _run_cycle(args) -> int:
    config = _load_cli_config(args.config, args.vault_root)
    if args.lm_timeout_seconds is not None:
        config = _with_lm_timeout(config, args.lm_timeout_seconds)
    if args.max_output_tokens is not None:
        config = _with_max_output_tokens(config, args.max_output_tokens)
    if getattr(args, "save_llm_payloads", False):
        config = _with_save_lm_payloads(config)
    try:
        adapter = ZoteroApiAdapter.from_env()
    except ZoteroApiError:
        if not getattr(args, "dry_run", False):
            raise
        adapter = _NoopSource()
    source = _CitekeyFilteredSource(
        _VaultCitekeySource(
            _StageFilteredSource(adapter, _stage_from_cli(args.stage)),
            config.paths.vault_root,
        ),
        getattr(args, "citekey", None),
    )
    lexical_index = build_lexical_index(config.paths.vault_root)
    if getattr(args, "dry_run", False):
        candidates = source.list_candidates()
        batch = select_batch(candidates, lexical_index, max_total=args.max_total)
        _safe_print(
            f"dry-run candidates={len(candidates)} selected={len(batch['selected'])} blocked_missing_pdf={len(batch['blocked_missing_pdf'])}"
        )
        for entry in batch["selected"]:
            candidate = entry["candidate"]
            _safe_print(
                f"SELECT {candidate.stage.value} {candidate.citekey} pdf={candidate.has_pdf} score={entry['score']} title={candidate.title}"
            )
        return 0
    analyzer = LocalPaperAnalyzer(
        client=LMStudioChatClient(config.lmstudio),
        max_attempts=args.max_attempts,
        packet_max_chars=args.packet_max_chars,
    )
    operational = resolve_operational_collections(
        adapter, config.operational_collections
    )
    result = run_once(
        config=config,
        zotero_source=source,
        lexical_index=lexical_index,
        max_total=args.max_total,
        analyzer=analyzer,
        apply_existing_decisions=True,
        zotero_applier=adapter,
        operational_collections=operational,
    )
    _safe_print(
        f"applied_decisions={len(result.applied_decisions)} selected={len(result.selected)} "
        f"blocked_missing_pdf={len(result.blocked_missing_pdf)} notes_written={len(result.notes_written)}"
    )
    for decision in result.applied_decisions:
        _safe_print(
            f"APPLIED {decision['citekey']} status={decision['status']} errors={decision['errors']}"
        )
    for note in result.notes_written:
        _safe_print(f"NOTE {note}")
    return 0


def _load_cli_config(config_path: str | None, vault_root: str | None):
    if vault_root is None:
        return load_config(config_path)
    return load_config(config_path, vault_root=vault_root)


def _scan_obsidian_vault_root(cli_vault_root: str | None) -> Path:
    if cli_vault_root is not None:
        return Path(cli_vault_root).resolve()
    env_mapping = load_env()
    if "VAULT_ROOT" not in env_mapping:
        raise PipelineError("VAULT_ROOT is required when --vault-root is not provided")
    return load_config(None).paths.vault_root


def _stage_from_cli(value: str | None):
    return {
        "tolook": Stage.TO_LOOK,
        "torevise": Stage.TO_REVISE,
        "todig": Stage.TO_DIG,
        None: None,
    }[value]


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            return


def _safe_print(text: str) -> None:
    print(text)


def _report_classify_progress(
    completed: int, total: int, classification: dict[str, object]
) -> None:
    _safe_print(
        "classified="
        f"{completed}/{total} "
        f"{classification.get('project_id')} -> {classification.get('citekey')}"
    )


def _split_csv(value: str):
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _split_stage_csv(value: str | None):
    if value is None:
        return None
    raw = _split_csv(value)
    if not raw:
        return None
    aliases = {
        "tolook": ".ToLook",
        ".tolook": ".ToLook",
        "look": ".ToLook",
        "torevise": ".To Revise",
        ".torevise": ".To Revise",
        "revise": ".To Revise",
        "todig": ".ToDig",
        ".todig": ".ToDig",
        "dig": ".ToDig",
        "expendable": "Expendable",
    }
    normalized = []
    for item in raw:
        key = item.replace(" ", "").lower()
        normalized.append(aliases.get(key, item))
    return tuple(normalized)


def _match_error_message(error: str) -> str:
    if "projects JSONL not found" in error or "papers JSONL not found" in error:
        return (
            f"match error: {error}\n"
            "Generate the missing inventories first:\n"
            "  uv run paper-pipeline scan-obsidian --vault-root /path/to/vault --output data/projects.jsonl\n"
            "  uv run paper-pipeline scan-zotero --output data/papers.jsonl --papers-root papers"
        )
    return f"match error: {error}"


def _classify_error_message(error: str) -> str:
    if "candidates JSONL not found" in error:
        return (
            f"classify error: {error}\n"
            "Generate the candidates first:\n"
            "  uv run paper-pipeline match --projects data/projects.jsonl --papers data/papers.jsonl --output data/candidates.jsonl"
        )
    if "projects JSONL not found" in error or "papers JSONL not found" in error:
        return (
            f"classify error: {error}\n"
            "Generate the missing inventories first:\n"
            "  uv run paper-pipeline scan-obsidian --vault-root /path/to/vault --output data/projects.jsonl\n"
            "  uv run paper-pipeline scan-zotero --output data/papers.jsonl --papers-root papers"
        )
    return f"classify error: {error}"


def _with_lm_timeout(config, timeout_seconds: int):
    from dataclasses import replace

    return replace(
        config,
        lmstudio=replace(
            config.lmstudio,
            timeout_seconds=timeout_seconds,
            tolook_timeout_seconds=timeout_seconds,
            deep_stage_timeout_seconds=timeout_seconds,
        ),
    )


def _with_max_output_tokens(config, max_output_tokens: int):
    from dataclasses import replace

    return replace(
        config,
        lmstudio=replace(
            config.lmstudio,
            max_output_tokens=max_output_tokens,
            tolook_max_output_tokens=max_output_tokens,
            deep_stage_max_output_tokens=max_output_tokens,
        ),
    )


def _with_save_lm_payloads(config):
    from dataclasses import replace

    return replace(config, lmstudio=replace(config.lmstudio, save_payloads=True))


if __name__ == "__main__":
    raise SystemExit(main())
