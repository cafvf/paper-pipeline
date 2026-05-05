from pathlib import Path

from paper_pipeline.contracts import Stage
from paper_pipeline.pdf_ingest import (
    MarkerJsonConverter,
    NougatMarkdownConverter,
    build_pdf_manifest,
    build_stage_conversion_plan,
    run_converters_with_cache,
)


class FakeConverter:
    def __init__(self, name, output, fail=False):
        self.name = name
        self.output = output
        self.fail = fail
        self.calls = 0

    def convert(self, pdf_path: Path):
        self.calls += 1
        if self.fail:
            raise RuntimeError("converter failed")
        return self.output


def test_pdf_manifest_hashes_file(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    manifest = build_pdf_manifest(pdf)
    assert manifest.size_bytes == 3
    assert len(manifest.sha256) == 64


def test_run_converters_writes_outputs_and_report(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    converter = FakeConverter("markitdown", "# Paper")
    result = run_converters_with_cache(pdf_path=pdf, paper_root=tmp_path / "paper", converters=[converter])
    assert converter.calls == 1
    assert result["conversion_report"]["converters"]["markitdown"]["status"] == "converted"
    assert Path(result["conversion_report_path"]).exists()


def test_converter_cache_skips_existing_output(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    converter = FakeConverter("markitdown", "# Paper")
    run_converters_with_cache(pdf_path=pdf, paper_root=tmp_path / "paper", converters=[converter])
    run_converters_with_cache(pdf_path=pdf, paper_root=tmp_path / "paper", converters=[converter])
    assert converter.calls == 1


def test_converter_failure_is_reported_without_blocking_others(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    result = run_converters_with_cache(
        pdf_path=pdf,
        paper_root=tmp_path / "paper",
        converters=[FakeConverter("bad", "", fail=True), FakeConverter("docling", {"ok": True})],
    )
    assert result["conversion_report"]["converters"]["bad"]["status"] == "error"
    assert result["conversion_report"]["converters"]["docling"]["status"] == "converted"


def test_empty_converter_output_is_reported_as_error(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    result = run_converters_with_cache(
        pdf_path=pdf,
        paper_root=tmp_path / "paper",
        converters=[FakeConverter("nougat", "")],
    )
    assert result["conversion_report"]["converters"]["nougat"]["status"] == "error"
    assert "empty output" in result["conversion_report"]["converters"]["nougat"]["error"]


def test_tolook_conversion_plan_uses_pymupdf_then_structured_fallbacks():
    plan = build_stage_conversion_plan(Stage.TO_LOOK)
    assert [converter.name for converter in plan.converters] == ["pymupdf", "marker", "markitdown", "nougat", "ocr_last_resort"]
    assert plan.stop_after_first_success is True
    assert plan.required_converter_names == []


def test_torevise_conversion_plan_requires_marker():
    plan = build_stage_conversion_plan(Stage.TO_REVISE)
    assert [converter.name for converter in plan.converters] == ["pymupdf", "marker", "markitdown"]
    assert plan.stop_after_first_success is False
    assert plan.required_converter_names == ["marker"]


def test_todig_conversion_plan_requires_marker_and_nougat_inputs():
    plan = build_stage_conversion_plan(Stage.TO_DIG)
    assert [converter.name for converter in plan.converters] == ["pymupdf", "marker", "nougat"]
    assert plan.stop_after_first_success is False
    assert plan.required_converter_names == ["marker", "nougat"]


def test_stage_conversion_plans_always_start_with_pymupdf():
    assert build_stage_conversion_plan(Stage.TO_LOOK).converters[0].name == "pymupdf"
    assert build_stage_conversion_plan(Stage.TO_REVISE).converters[0].name == "pymupdf"
    assert build_stage_conversion_plan(Stage.TO_DIG).converters[0].name == "pymupdf"


def test_first_success_policy_stops_before_expensive_fallbacks(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    first = FakeConverter("pymupdf", {"pages": [{"page": 1, "text": "ok"}]})
    fallback = FakeConverter("marker", {"pages": []})
    result = run_converters_with_cache(
        pdf_path=pdf,
        paper_root=tmp_path / "paper",
        converters=[first, fallback],
        stop_after_first_success=True,
    )
    assert first.calls == 1
    assert fallback.calls == 0
    assert result["conversion_report"]["converters"]["marker"]["status"] == "skipped"


def test_marker_converter_reads_json_from_output_dir(monkeypatch, tmp_path):
    pdf = tmp_path / "Paper with a very long name - and slash like title.pdf"
    pdf.write_bytes(b"abc")
    captured = {}

    def fake_run(command, capture_output, check, text, timeout):
        captured["command"] = command
        assert Path(command[1]).name == "input.pdf"
        output_dir = Path(command[command.index("--output_dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "paper.json").write_text('{"pages":[{"page":1,"text":"Abstract\\nOK"}]}', encoding="utf-8")

        class Completed:
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr("paper_pipeline.pdf_ingest.subprocess.run", fake_run)
    output = MarkerJsonConverter().convert(pdf)
    assert output["pages"][0]["text"] == "Abstract\nOK"
    assert captured["command"][0] == "marker_single"
    assert "--output_format" in captured["command"]
    assert "--output_dir" in captured["command"]
    assert "--disable_ocr" in captured["command"]


def test_marker_converter_supports_page_range_and_timeout(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    captured = {}

    def fake_run(command, capture_output, check, text, timeout):
        captured["command"] = command
        captured["timeout"] = timeout
        output_dir = Path(command[command.index("--output_dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "paper.json").write_text('{"pages":[{"text":"ok"}]}', encoding="utf-8")

        class Completed:
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr("paper_pipeline.pdf_ingest.subprocess.run", fake_run)
    MarkerJsonConverter(timeout_seconds=12, page_range="0").convert(pdf)
    assert captured["timeout"] == 12
    assert captured["command"][captured["command"].index("--page_range") + 1] == "0"


def test_nougat_converter_reads_mmd_from_output_dir(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")

    def fake_run(command, capture_output, check, text, timeout, env):
        output_dir = Path(command[command.index("-o") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "paper.mmd").write_text("# Paper\n\nAbstract\nOK", encoding="utf-8")
        assert env["NO_ALBUMENTATIONS_UPDATE"] == "1"

        class Completed:
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr("paper_pipeline.pdf_ingest.subprocess.run", fake_run)
    assert "Abstract\nOK" in NougatMarkdownConverter().convert(pdf)


def test_nougat_converter_supports_pages_timeout_and_full_precision(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"abc")
    captured = {}

    def fake_run(command, capture_output, check, text, timeout, env):
        captured["command"] = command
        captured["timeout"] = timeout
        output_dir = Path(command[command.index("-o") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "paper.mmd").write_text("# Paper", encoding="utf-8")

        class Completed:
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr("paper_pipeline.pdf_ingest.subprocess.run", fake_run)
    NougatMarkdownConverter(timeout_seconds=34, pages="1", full_precision=True).convert(pdf)
    assert captured["timeout"] == 34
    assert captured["command"][:8] == [
        "uvx",
        "--from",
        "nougat-ocr==0.1.17",
        "--with",
        "transformers<4.38",
        "--with",
        "albumentations<2",
        "--with",
    ]
    assert captured["command"][8:10] == [
        "pypdfium2==4.0.0",
        "nougat",
    ]
    assert captured["command"][captured["command"].index("--pages") + 1] == "1"
    assert "--full-precision" in captured["command"]
