import json

from paper_pipeline.artifacts import PaperArtifactStore


def test_artifact_store_creates_layout(tmp_path):
    store = PaperArtifactStore(tmp_path, "paper2026")
    store.ensure_layout()
    assert (tmp_path / "paper2026" / "zotero").is_dir()
    assert (tmp_path / "paper2026" / "reading_packets" / "history").is_dir()
    assert (tmp_path / "paper2026" / "logs").is_dir()


def test_latest_and_history_are_written(tmp_path):
    store = PaperArtifactStore(tmp_path, "paper2026")
    paths = store.write_latest_and_history("reading_packets", "look", {"stage": "look"})
    assert paths["latest"].endswith("look_latest.json")
    assert "history" in paths["history"]
    assert json.loads((tmp_path / "paper2026" / "reading_packets" / "look_latest.json").read_text())["stage"] == "look"


def test_passes_write_latest_and_history(tmp_path):
    store = PaperArtifactStore(tmp_path, "paper2026")
    paths = store.write_passes("review", "run1", {"pass_01_global": {"ok": True}})
    assert paths["pass_01_global"].endswith("passes\\review\\latest\\pass_01_global.json") or paths["pass_01_global"].endswith("passes/review/latest/pass_01_global.json")
    assert (tmp_path / "paper2026" / "passes" / "review" / "history" / "run1" / "pass_01_global.json").exists()


def test_append_log_is_jsonl(tmp_path):
    store = PaperArtifactStore(tmp_path, "paper2026")
    path = store.append_log({"event": "started"})
    lines = (tmp_path / "paper2026" / "logs" / "run_events.jsonl").read_text().splitlines()
    assert path.endswith("run_events.jsonl")
    assert json.loads(lines[0])["event"] == "started"


def test_main_artifact_links_are_runtime_relative():
    store = PaperArtifactStore("papers", "paper2026")
    links = store.main_artifact_links("look", pdf_hash="abc", patch_plan_id="p1")
    assert links["assessment"].startswith("papers/")
    assert "conversion_report.json" in links["conversion_report"]
