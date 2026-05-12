from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .contracts import PipelineError
from .schema_validation import validate_instance


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class UpsertReport:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PairProcessingDecision:
    should_process: bool
    reason: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RegistrySyncReport:
    projects: UpsertReport
    papers: UpsertReport
    warnings: list[str] = field(default_factory=list)


def initialize_registry(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if path.exists() and path.is_dir():
        raise PipelineError(f"registry database path is a directory: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("pragma foreign_keys = on")
        _create_schema(conn)
    except sqlite3.Error as exc:
        raise PipelineError(f"registry database is not usable: {path}: {exc}") from exc
    except OSError as exc:
        raise PipelineError(f"registry database path is not usable: {path}: {exc}") from exc
    return conn


def load_jsonl(path: str | Path, *, artifact_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    source = Path(path)
    if not source.exists():
        raise PipelineError(f"{artifact_name} JSONL not found: {source}")
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            warnings.append(f"{artifact_name} JSONL contains blank line at {line_number}")
            continue
        try:
            loaded = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"{artifact_name} JSONL invalid JSON at line {line_number}: {exc.msg}") from exc
        if not isinstance(loaded, dict):
            raise PipelineError(f"{artifact_name} JSONL line {line_number} must be a JSON object")
        rows.append(loaded)
    return rows, warnings


def sync_registry_from_jsonl(
    db_path: str | Path,
    *,
    projects_path: str | Path,
    papers_path: str | Path,
) -> RegistrySyncReport:
    project_rows, project_warnings = _load_optional_jsonl(projects_path, artifact_name="projects")
    paper_rows, paper_warnings = _load_optional_jsonl(papers_path, artifact_name="papers")
    conn = initialize_registry(db_path)
    try:
        conn.execute("begin")
        project_report = upsert_projects(conn, project_rows, manage_transaction=False)
        paper_report = upsert_papers(conn, paper_rows, manage_transaction=False)
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    warnings = [
        *project_warnings,
        *paper_warnings,
        *project_report.warnings,
        *paper_report.warnings,
    ]
    return RegistrySyncReport(projects=project_report, papers=paper_report, warnings=warnings)


def _load_optional_jsonl(path: str | Path, *, artifact_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    source = Path(path)
    if not source.exists():
        return [], [f"{artifact_name} JSONL not found, skipping: {source}"]
    return load_jsonl(source, artifact_name=artifact_name)


def upsert_projects(
    conn: sqlite3.Connection,
    projects: Iterable[dict[str, Any]],
    *,
    manage_transaction: bool = True,
) -> UpsertReport:
    rows = list(projects)
    for project in rows:
        validate_instance(project, "project_profile.schema.json")
    warnings = _duplicate_hash_warnings(rows, key_field="project_id", hash_field="content_hash")
    inserted = updated = unchanged = 0
    context = conn if manage_transaction else _null_transaction()
    with context:
        for project in rows:
            existing = conn.execute(
                "select content_hash from projects where project_id = ?",
                (project["project_id"],),
            ).fetchone()
            if existing is None:
                inserted += 1
            elif existing[0] == project["content_hash"]:
                unchanged += 1
            else:
                updated += 1
            conn.execute(
                """
                insert into projects (
                  project_id, title, source_path, project_state, state_source,
                  priority, content_hash, payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(project_id) do update set
                  title = excluded.title,
                  source_path = excluded.source_path,
                  project_state = excluded.project_state,
                  state_source = excluded.state_source,
                  priority = excluded.priority,
                  content_hash = excluded.content_hash,
                  payload_json = excluded.payload_json,
                  updated_at = datetime('now')
                """,
                (
                    project["project_id"],
                    project["title"],
                    project["source_path"],
                    project["project_state"],
                    project["state_source"],
                    project["priority"],
                    project["content_hash"],
                    _json(project),
                ),
            )
    return UpsertReport(inserted=inserted, updated=updated, unchanged=unchanged, warnings=warnings)


def upsert_papers(
    conn: sqlite3.Connection,
    papers: Iterable[dict[str, Any]],
    *,
    manage_transaction: bool = True,
) -> UpsertReport:
    rows = list(papers)
    for paper in rows:
        validate_instance(paper, "paper_profile.schema.json")
    warnings = _duplicate_hash_warnings(rows, key_field="citekey", hash_field="paper_hash")
    inserted = updated = unchanged = 0
    context = conn if manage_transaction else _null_transaction()
    with context:
        for paper in rows:
            existing = conn.execute(
                "select paper_hash from papers where citekey = ?",
                (paper["citekey"],),
            ).fetchone()
            if existing is None:
                inserted += 1
            elif existing[0] == paper["paper_hash"]:
                unchanged += 1
            else:
                updated += 1
            conn.execute(
                """
                insert into papers (
                  citekey, zotero_key, title, year, doi, has_pdf,
                  paper_hash, metadata_snapshot_path, payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(citekey) do update set
                  zotero_key = excluded.zotero_key,
                  title = excluded.title,
                  year = excluded.year,
                  doi = excluded.doi,
                  has_pdf = excluded.has_pdf,
                  paper_hash = excluded.paper_hash,
                  metadata_snapshot_path = excluded.metadata_snapshot_path,
                  payload_json = excluded.payload_json,
                  updated_at = datetime('now')
                """,
                (
                    paper["citekey"],
                    paper["zotero_key"],
                    paper["title"],
                    paper.get("year"),
                    paper.get("doi"),
                    1 if paper["has_pdf"] else 0,
                    paper["paper_hash"],
                    paper["metadata_snapshot_path"],
                    _json(paper),
                ),
            )
    return UpsertReport(inserted=inserted, updated=updated, unchanged=unchanged, warnings=warnings)


def should_process_pair(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    citekey: str,
    project_hash: str,
    paper_hash: str,
    prompt_hash: str,
) -> PairProcessingDecision:
    warnings = _missing_row_warnings(conn, project_id=project_id, citekey=citekey)
    if warnings:
        return PairProcessingDecision(should_process=True, reason="missing_registry_row", warnings=warnings)
    existing = conn.execute(
        """
        select project_hash, paper_hash, prompt_hash
        from hashes
        where project_id = ? and citekey = ? and hash_kind = 'project_paper_prompt'
        """,
        (project_id, citekey),
    ).fetchone()
    if existing is None:
        return PairProcessingDecision(should_process=True, reason="new_pair")
    if existing == (project_hash, paper_hash, prompt_hash):
        return PairProcessingDecision(should_process=False, reason="unchanged")
    return PairProcessingDecision(should_process=True, reason="hash_changed")


def record_pair_hash(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    citekey: str,
    project_hash: str,
    paper_hash: str,
    prompt_hash: str,
) -> None:
    with conn:
        conn.execute(
            """
            insert into hashes (
              hash_kind, project_id, citekey, project_hash, paper_hash, prompt_hash
            )
            values ('project_paper_prompt', ?, ?, ?, ?, ?)
            on conflict(hash_kind, project_id, citekey) do update set
              project_hash = excluded.project_hash,
              paper_hash = excluded.paper_hash,
              prompt_hash = excluded.prompt_hash,
              updated_at = datetime('now')
            """,
            (project_id, citekey, project_hash, paper_hash, prompt_hash),
        )


def _create_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(
            """
            create table if not exists schema_migrations (
              version integer primary key,
              applied_at text not null default (datetime('now'))
            );

            create table if not exists projects (
              project_id text primary key,
              title text not null,
              source_path text not null,
              project_state text not null,
              state_source text not null,
              priority text not null,
              content_hash text not null,
              payload_json text not null,
              updated_at text not null default (datetime('now'))
            );

            create table if not exists papers (
              citekey text primary key,
              zotero_key text not null,
              title text not null,
              year integer,
              doi text,
              has_pdf integer not null,
              paper_hash text not null,
              metadata_snapshot_path text not null,
              payload_json text not null,
              updated_at text not null default (datetime('now'))
            );

            create table if not exists project_paper_candidates (
              project_id text not null references projects(project_id) on delete cascade,
              citekey text not null references papers(citekey) on delete cascade,
              candidate_score real not null,
              rank integer not null,
              evidence_json text not null,
              method text not null,
              created_at text not null,
              primary key (project_id, citekey, method)
            );

            create table if not exists llm_classifications (
              project_id text not null references projects(project_id) on delete cascade,
              citekey text not null references papers(citekey) on delete cascade,
              prompt_hash text not null,
              payload_json text not null,
              created_at text not null default (datetime('now')),
              primary key (project_id, citekey, prompt_hash)
            );

            create table if not exists human_reviews (
              review_id text not null,
              review_item_id text not null,
              project_id text,
              citekey text not null references papers(citekey) on delete cascade,
              payload_json text not null,
              created_at text not null default (datetime('now')),
              primary key (review_id, review_item_id, project_id)
            );

            create table if not exists processing_runs (
              run_id text primary key,
              command text not null,
              status text not null,
              payload_json text not null default '{}',
              started_at text not null default (datetime('now')),
              finished_at text
            );

            create table if not exists hashes (
              hash_kind text not null,
              project_id text not null references projects(project_id) on delete cascade,
              citekey text not null references papers(citekey) on delete cascade,
              project_hash text not null,
              paper_hash text not null,
              prompt_hash text not null,
              updated_at text not null default (datetime('now')),
              primary key (hash_kind, project_id, citekey)
            );
            """
        )
        conn.execute(
            "insert or ignore into schema_migrations(version) values (?)",
            (SCHEMA_VERSION,),
        )


def _duplicate_hash_warnings(rows: list[dict[str, Any]], *, key_field: str, hash_field: str) -> list[str]:
    seen: dict[str, str] = {}
    warnings = []
    label = "project_id" if key_field == "project_id" else "citekey"
    for row in rows:
        key = str(row[key_field])
        hash_value = str(row[hash_field])
        if key in seen and seen[key] != hash_value:
            warnings.append(f"duplicate {label} in batch with different {hash_field}: {key}")
        seen[key] = hash_value
    return list(dict.fromkeys(warnings))


def _missing_row_warnings(conn: sqlite3.Connection, *, project_id: str, citekey: str) -> list[str]:
    warnings = []
    if conn.execute("select 1 from projects where project_id = ?", (project_id,)).fetchone() is None:
        warnings.append(f"project missing from registry: {project_id}")
    if conn.execute("select 1 from papers where citekey = ?", (citekey,)).fetchone() is None:
        warnings.append(f"paper missing from registry: {citekey}")
    return warnings


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class _null_transaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False
