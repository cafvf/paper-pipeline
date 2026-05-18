from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

from .contracts import PipelineError
from .registry import load_jsonl
from .schema_validation import validate_instance


UTILITY_PRIORITY = {
    "essential": 0,
    "implementable": 1,
    "formulational": 2,
    "methodological": 3,
    "case_study": 4,
    "review": 5,
    "counterpoint": 6,
    "peripheral": 7,
    "irrelevant_now": 8,
}
ACTION_PRIORITY = {
    "read_now": 0,
    "extract_equations": 1,
    "reproduce_code": 2,
    "link_to_project": 3,
    "read_later": 4,
    "summarize_only": 5,
    "ignore_for_now": 6,
}
HIGH_UTILITY = {"essential", "methodological", "formulational", "implementable"}
CONTEXTUAL = {"case_study", "review", "counterpoint", "peripheral"}
SECTION_TITLES = {
    "high_utility": "High-utility papers",
    "contextual": "Contextual papers",
    "no_use": "No-use papers",
}


class ExportReviewError(PipelineError):
    """Raised when review export input or rendering is unusable."""


@dataclass(frozen=True)
class ReviewExportResult:
    output_path: Path
    review_items: int
    review_id: str
    review_date: str


def default_review_date() -> str:
    return date.today().isoformat()


def default_review_output_path(review_date: str) -> str:
    return f"data/review-project-papers-{review_date}.md"


def default_review_id(review_date: str) -> str:
    return f"review_{review_date}_initial_triage"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paper_pipeline.export_review")
    parser.add_argument("--classifications", default="data/classifications.jsonl")
    parser.add_argument("--output", default=None)
    parser.add_argument("--date", default=None)
    parser.add_argument("--review-id", default=None)
    return parser


def run_export_review_from_jsonl(
    *,
    classifications_path: str | Path,
    output_path: str | Path,
    review_id: str,
    review_date: str,
    artifact_root: str | Path | None = None,
) -> ReviewExportResult:
    rows, _warnings = load_jsonl(classifications_path, artifact_name="classifications")
    validated_rows = [
        validate_instance(row, "llm_classification.schema.json") for row in rows
    ]
    markdown = render_review_markdown(
        validated_rows,
        review_id=review_id,
        review_path=str(Path(output_path).as_posix()),
        review_date=review_date,
        artifact_root=artifact_root,
    )
    _write_text_atomic(Path(output_path), markdown)
    return ReviewExportResult(
        output_path=Path(output_path),
        review_items=len(_group_rows(validated_rows)),
        review_id=review_id,
        review_date=review_date,
    )


def render_review_markdown(
    classifications: list[dict[str, Any]],
    *,
    review_id: str,
    review_path: str,
    review_date: str | None = None,
    artifact_root: str | Path | None = None,
) -> str:
    root = Path("." if artifact_root is None else artifact_root)
    grouped = _group_rows(classifications)
    sections = {"high_utility": [], "contextual": [], "no_use": []}
    for item in grouped:
        sections[_section_for_item(item)].append(item)
    for key in sections:
        sections[key].sort(key=_item_sort_key)
    resolved_date = (
        review_date or _date_from_review_id(review_id) or default_review_date()
    )
    lines = [
        f"# Project Paper Review - {resolved_date}",
        "",
        "## Review contract",
        "",
        "Allowed paper review status:",
        "- `pending`",
        "- `decided`",
        "",
        "Allowed project decisions:",
        "- `pending`",
        "- `approved`",
        "- `rejected`",
        "- `deferred`",
        "",
        "Allowed actions:",
        "- `read_now`",
        "- `read_later`",
        "- `extract_equations`",
        "- `reproduce_code`",
        "- `summarize_only`",
        "- `link_to_project`",
        "- `ignore_for_now`",
        "",
        "Allowed Zotero stage decisions:",
        "- `pending`",
        "- `keep_current`",
        "- `move_to_revise`",
        "- `move_to_dig`",
        "- `move_to_expendable`",
        "- `manual_only`",
        "",
        "Default safety values:",
        "- `apply_zotero_tags: false`",
        "- `create_obsidian_note: false`",
        "",
    ]
    for section_key in ("high_utility", "contextual", "no_use"):
        items = sections[section_key]
        if not items:
            continue
        lines.extend([f"## {SECTION_TITLES[section_key]}", ""])
        for item in items:
            strongest = item["strongest"]
            title = _title_for_item(item, root)
            lines.extend(
                [
                    f"### {title}",
                    "",
                    f"- Citekey: `{item['citekey']}`",
                    f"- Current Zotero stage: `{strongest['current_zotero_stage']}`",
                    f"- Strongest utility: `{strongest['utility_class']}`",
                    f"- Recommended action: `{strongest['recommended_action']}`",
                    f"- Recommended Zotero stage: `{strongest['recommended_zotero_stage']}`",
                    f"- Confidence: `{strongest['confidence']}`",
                    f"- Summary: {_inline(strongest['reason'])}",
                ]
            )
            if strongest.get("possible_uses"):
                lines.append("- Possible uses:")
                lines.extend(
                    f"  - {_inline(value)}" for value in strongest["possible_uses"]
                )
            if strongest.get("limitations"):
                lines.append("- Limitations:")
                lines.extend(
                    f"  - {_inline(value)}" for value in strongest["limitations"]
                )
            lines.extend(["- Project matches:"])
            for row in item["rows"]:
                lines.extend(
                    [
                        f"  - `{row['project_id']}`: {row['utility_class']}, {row['recommended_action']}, recommended stage {row['recommended_zotero_stage']}",
                        f"    - Reason: {_inline(row['reason'])}",
                    ]
                )
            lines.extend(
                [
                    "- Decision: edit the YAML block below.",
                    "",
                    "```yaml",
                    _render_yaml_block(
                        _decision_block(
                            item, review_id=review_id, review_path=review_path
                        )
                    ),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _group_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        citekey = str(row.get("citekey") or "").strip()
        if not citekey:
            raise ExportReviewError("classification row missing citekey")
        grouped.setdefault(citekey, []).append(row)
    items = []
    for citekey, group_rows in grouped.items():
        sorted_rows = sorted(group_rows, key=_row_sort_key)
        items.append(
            {"citekey": citekey, "rows": sorted_rows, "strongest": sorted_rows[0]}
        )
    return items


def _section_for_item(item: dict[str, Any]) -> str:
    utility = item["strongest"]["utility_class"]
    if utility in HIGH_UTILITY:
        return "high_utility"
    if utility in CONTEXTUAL:
        return "contextual"
    return "no_use"


def _row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        UTILITY_PRIORITY.get(row["utility_class"], 99),
        ACTION_PRIORITY.get(row["recommended_action"], 99),
        -_score_total(row),
        str(row["project_id"]),
    )


def _item_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    strongest = item["strongest"]
    return (
        UTILITY_PRIORITY.get(strongest["utility_class"], 99),
        ACTION_PRIORITY.get(strongest["recommended_action"], 99),
        -_score_total(strongest),
        item["citekey"],
    )


def _score_total(row: dict[str, Any]) -> int:
    scores = row.get("scores", {})
    if not isinstance(scores, dict):
        return 0
    return sum(
        int(scores.get(key, 0) or 0)
        for key in (
            "topic_fit",
            "method_fit",
            "formulation_value",
            "implementation_value",
            "empirical_value",
            "gap_value",
        )
    ) - int(scores.get("reading_effort", 0) or 0)


def _title_for_item(item: dict[str, Any], root: Path) -> str:
    for row in item["rows"]:
        for product in row.get("input_products", []):
            title = _title_from_snapshot(root, product)
            if title:
                return title
    return item["citekey"]


def _title_from_snapshot(root: Path, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = (root / path).resolve()
    if not path.exists():
        return ""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(loaded, dict):
        return ""
    return _inline(str(loaded.get("title") or ""))


def _decision_block(
    item: dict[str, Any], *, review_id: str, review_path: str
) -> dict[str, Any]:
    strongest = item["strongest"]
    return {
        "review_id": review_id,
        "review_path": review_path,
        "review_item_id": item["citekey"],
        "citekey": item["citekey"],
        "decision": "pending",
        "human_reason": "",
        "approved_actions": _sorted_unique(
            row["recommended_action"] for row in item["rows"]
        ),
        "current_zotero_stage": strongest["current_zotero_stage"],
        "recommended_zotero_stage": strongest["recommended_zotero_stage"],
        "stage_recommendation_reason": strongest["stage_recommendation_reason"],
        "zotero_stage_decision": "pending",
        "manual_credibility": "unknown",
        "project_decisions": [
            {
                "project_id": row["project_id"],
                "decision": "pending",
                "approved_actions": [row["recommended_action"]],
                "human_reason": "",
            }
            for row in item["rows"]
        ],
        "apply_zotero_tags": False,
        "create_obsidian_note": False,
    }


def _sorted_unique(values):
    unique = sorted(
        {str(value) for value in values},
        key=lambda value: ACTION_PRIORITY.get(value, 99),
    )
    return unique


def _render_yaml_block(payload: dict[str, Any]) -> str:
    return "\n".join(_yaml_lines(payload))


def _yaml_lines(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                if isinstance(item, list) and not item:
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}:")
                    lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                if isinstance(item, list) and not item:
                    lines.append(f"{prefix}- []")
                else:
                    nested = _yaml_lines(item, indent + 2)
                    first, *rest = nested
                    lines.append(f"{prefix}- {first.strip()}")
                    lines.extend(rest)
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


def _yaml_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _inline(text: str) -> str:
    return " ".join(str(text).split())


def _date_from_review_id(review_id: str) -> str | None:
    parts = review_id.split("_")
    if len(parts) >= 2:
        try:
            datetime.strptime(parts[1], "%Y-%m-%d")
        except ValueError:
            return None
        return parts[1]
    return None


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    print(f"review_items={result.review_items} output={result.output_path}")
    return 0


__all__ = [
    "ExportReviewError",
    "ReviewExportResult",
    "build_parser",
    "default_review_date",
    "default_review_id",
    "default_review_output_path",
    "main",
    "render_review_markdown",
    "run_export_review_from_jsonl",
]


if __name__ == "__main__":
    raise SystemExit(main())
