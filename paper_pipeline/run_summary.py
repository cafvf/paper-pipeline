from __future__ import annotations

from pathlib import Path

from .runner import NightlyRunResult


def write_run_summary(inbox_dir: str | Path, result: NightlyRunResult, *, run_id: str) -> Path:
    path = Path(inbox_dir) / f"LLM Paper Pipeline Run {run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: inbox",
        "area: LLM",
        "review: true",
        "tags:",
        "  - inbox",
        "  - llm-paper-run",
        "---",
        f"# LLM Paper Pipeline Run {run_id}",
        "",
        "## Decisoes existentes",
        *[f"- `{item.get('citekey')}`: {item.get('status')}" for item in result.applied_decisions],
        "",
        "## Selecionados",
        *[f"- `{citekey}`" for citekey in result.selected],
        "",
        "## Bloqueados por falta de PDF",
        *[f"- `{citekey}`" for citekey in result.blocked_missing_pdf],
        "",
        "## Notas escritas",
        *[f"- `{path}`" for path in result.notes_written],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
