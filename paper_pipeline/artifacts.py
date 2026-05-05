from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .contracts import ensure_inside, normalize_citekey


class PaperArtifactStore:
    def __init__(self, papers_root: str | Path, citekey: str) -> None:
        self.papers_root = Path(papers_root)
        self.citekey = normalize_citekey(citekey)
        self.root = ensure_inside(self.papers_root, self.papers_root / self.citekey)

    def ensure_layout(self) -> None:
        for rel in [
            "zotero",
            "pdf/conversions",
            "reading_packets/history",
            "passes",
            "assessments/history",
            "patch_plans",
            "decisions",
            "logs",
        ]:
            (self.root / rel).mkdir(parents=True, exist_ok=True)

    def write_latest_and_history(self, group: str, stage: str, payload: dict[str, Any]) -> dict[str, str]:
        self.ensure_layout()
        timestamp = _timestamp()
        group_root = self.root / group
        history_root = group_root / "history"
        history_root.mkdir(parents=True, exist_ok=True)
        latest_path = group_root / f"{stage}_latest.json"
        history_path = history_root / f"{stage}_{timestamp}.json"
        _write_json(latest_path, payload)
        _write_json(history_path, payload)
        return {"latest": str(latest_path), "history": str(history_path)}

    def write_passes(self, stage: str, run_id: str, passes: dict[str, dict[str, Any]]) -> dict[str, str]:
        self.ensure_layout()
        base = self.root / "passes" / stage
        latest_root = base / "latest"
        history_root = base / "history" / run_id
        latest_root.mkdir(parents=True, exist_ok=True)
        history_root.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}
        for name, payload in passes.items():
            latest_path = latest_root / f"{name}.json"
            history_path = history_root / f"{name}.json"
            _write_json(latest_path, payload)
            _write_json(history_path, payload)
            written[name] = str(latest_path)
        return written

    def write_zotero_snapshot(self, payload: dict[str, Any]) -> str:
        self.ensure_layout()
        path = self.root / "zotero" / "item_latest.json"
        _write_json(path, payload)
        return str(path)

    def append_log(self, event: dict[str, Any]) -> str:
        self.ensure_layout()
        path = self.root / "logs" / "run_events.jsonl"
        enriched = {"timestamp": datetime.now().isoformat(), **event}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(enriched, ensure_ascii=False, sort_keys=True) + "\n")
        return str(path)

    def main_artifact_links(self, stage: str, pdf_hash: str | None = None, patch_plan_id: str | None = None) -> dict[str, str]:
        links = {
            "assessment": _artifact_link(self.root / "assessments" / f"{stage}_latest.json", self.papers_root),
            "reading_packet": _artifact_link(self.root / "reading_packets" / f"{stage}_latest.json", self.papers_root),
        }
        if pdf_hash:
            links["conversion_report"] = _artifact_link(
                self.root / "pdf" / "conversions" / pdf_hash / "conversion_report.json",
                self.papers_root,
            )
        if patch_plan_id:
            links["patch_plan"] = _artifact_link(self.root / "patch_plans" / f"{patch_plan_id}.json", self.papers_root)
        return links


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _artifact_link(path: Path, papers_root: Path) -> str:
    text = str(path).replace("\\", "/")
    marker = "/x/LLM/"
    if marker in text:
        return "x/LLM/" + text.split(marker, 1)[1]
    try:
        rel = path.resolve().relative_to(papers_root.resolve().parent)
        return rel.as_posix()
    except ValueError:
        pass
    return text
