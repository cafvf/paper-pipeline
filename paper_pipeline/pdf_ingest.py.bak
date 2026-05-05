from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from .contracts import Stage


@dataclass(frozen=True)
class PdfManifest:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class PdfConversionPlan:
    converters: list[PdfConverter]
    stop_after_first_success: bool = False
    required_converter_names: list[str] | None = None


class PdfConverter(Protocol):
    name: str

    def convert(self, pdf_path: Path) -> str | dict: ...


def build_pdf_manifest(pdf_path: str | Path) -> PdfManifest:
    path = Path(pdf_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return PdfManifest(path=str(path), sha256=digest, size_bytes=path.stat().st_size)


def run_converters_with_cache(
    *,
    pdf_path: str | Path,
    paper_root: str | Path,
    converters: list[PdfConverter],
    stop_after_first_success: bool = False,
    required_converter_names: list[str] | None = None,
) -> dict:
    manifest = build_pdf_manifest(pdf_path)
    conversion_root = Path(paper_root) / "pdf" / "conversions" / manifest.sha256
    conversion_root.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(paper_root) / "pdf" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, manifest.__dict__)

    report = {
        "pdf_hash": manifest.sha256,
        "converters": {},
    }
    has_success = False
    for converter in converters:
        if stop_after_first_success and has_success:
            report["converters"][converter.name] = {"status": "skipped", "reason": "previous_converter_succeeded"}
            continue
        output_path = conversion_root / _output_name(converter.name)
        if output_path.exists():
            report["converters"][converter.name] = {"status": "cached", "output_path": str(output_path)}
            has_success = True
            continue
        try:
            output = converter.convert(Path(pdf_path))
            if not _has_output_content(output):
                raise RuntimeError("converter produced empty output")
            if isinstance(output, dict):
                _write_json(output_path, output)
            else:
                output_path.write_text(str(output), encoding="utf-8")
            report["converters"][converter.name] = {"status": "converted", "output_path": str(output_path)}
            has_success = True
        except Exception as exc:
            report["converters"][converter.name] = {"status": "error", "error": str(exc)}
    required = required_converter_names or []
    missing_required = [
        name
        for name in required
        if report["converters"].get(name, {}).get("status") not in {"converted", "cached"}
    ]
    report["required_converter_names"] = required
    report["missing_required_converters"] = missing_required
    report["usable"] = not missing_required and any(
        item.get("status") in {"converted", "cached"} for item in report["converters"].values()
    )

    report_path = conversion_root / "conversion_report.json"
    _write_json(report_path, report)
    return {"manifest": manifest.__dict__, "conversion_report": report, "conversion_report_path": str(report_path)}


def build_stage_conversion_plan(stage: Stage) -> PdfConversionPlan:
    if stage == Stage.TO_LOOK:
        return PdfConversionPlan(
            converters=[
                PyMuPdfTextConverter(),
                MarkerJsonConverter(),
                MarkItDownMarkdownConverter(),
                NougatMarkdownConverter(),
                OcrLastResortConverter(),
            ],
            stop_after_first_success=True,
            required_converter_names=[],
        )
    if stage == Stage.TO_REVISE:
        return PdfConversionPlan(
            converters=[PyMuPdfTextConverter(), MarkerJsonConverter(), MarkItDownMarkdownConverter()],
            stop_after_first_success=False,
            required_converter_names=["marker"],
        )
    if stage == Stage.TO_DIG:
        return PdfConversionPlan(
            converters=[PyMuPdfTextConverter(), MarkerJsonConverter(), NougatMarkdownConverter()],
            stop_after_first_success=False,
            required_converter_names=["marker", "nougat"],
        )
    return PdfConversionPlan(converters=[PyMuPdfTextConverter()], stop_after_first_success=True, required_converter_names=[])


class PyMuPdfTextConverter:
    name = "pymupdf"

    def convert(self, pdf_path: Path) -> dict:
        import fitz  # type: ignore

        pages = []
        with fitz.open(str(pdf_path)) as doc:
            for index, page in enumerate(doc):
                pages.append({"page": index + 1, "text": page.get_text("text")})
        return {"converter": self.name, "pages": pages}


class MarkerJsonConverter:
    name = "marker"

    def __init__(
        self,
        *,
        timeout_seconds: int = 1800,
        page_range: str | None = None,
        disable_ocr: bool = True,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.page_range = page_range
        self.disable_ocr = disable_ocr

    def convert(self, pdf_path: Path) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            safe_input = Path(tmp) / "input.pdf"
            shutil.copy2(pdf_path, safe_input)
            command = ["marker_single", str(safe_input), "--output_format", "json", "--output_dir", tmp]
            if self.page_range:
                command.extend(["--page_range", self.page_range])
            if self.disable_ocr:
                command.append("--disable_ocr")
            try:
                completed = subprocess.run(command, capture_output=True, check=True, text=True, timeout=self.timeout_seconds)
            except FileNotFoundError as exc:
                raise RuntimeError("marker is not installed; install the pdf-robust extra or configure marker_single") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"marker timed out after {self.timeout_seconds} seconds") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or "").strip()
                raise RuntimeError(f"marker failed: {detail}") from exc
            outputs = sorted(Path(tmp).rglob("*.json"))
            if outputs:
                return json.loads(outputs[0].read_text(encoding="utf-8"))
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("marker did not produce JSON output") from exc


class MarkItDownMarkdownConverter:
    name = "markitdown"

    def convert(self, pdf_path: Path) -> str:
        try:
            from markitdown import MarkItDown  # type: ignore
        except ImportError as exc:
            raise RuntimeError("markitdown is not installed; install the pdf-basic or pdf-robust extra") from exc
        result = MarkItDown().convert(str(pdf_path))
        return str(result.text_content)


class NougatMarkdownConverter:
    name = "nougat"

    def __init__(
        self,
        *,
        timeout_seconds: int = 1800,
        pages: str | None = None,
        full_precision: bool = True,
        isolated_uvx: bool = True,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.pages = pages
        self.full_precision = full_precision
        self.isolated_uvx = isolated_uvx

    def convert(self, pdf_path: Path) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            command = _nougat_command(self.isolated_uvx)
            command.extend([str(pdf_path), "-o", tmp, "--markdown"])
            if self.pages:
                command.extend(["--pages", self.pages])
            if self.full_precision:
                command.append("--full-precision")
            env = os.environ.copy()
            env.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
            try:
                subprocess.run(
                    command,
                    capture_output=True,
                    check=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("nougat is not installed; install the experimental-nougat extra") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"nougat timed out after {self.timeout_seconds} seconds") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or "").strip()
                raise RuntimeError(f"nougat failed: {detail}") from exc
            outputs = sorted(Path(tmp).glob("*.mmd"))
            if not outputs:
                raise RuntimeError("nougat did not produce an .mmd output")
            return outputs[0].read_text(encoding="utf-8", errors="replace")


class OcrLastResortConverter:
    name = "ocr_last_resort"

    def convert(self, pdf_path: Path) -> str:
        raise RuntimeError("OCR last-resort conversion is not configured yet")


class PlainTextFallbackConverter:
    name = "plain_text_fallback"

    def convert(self, pdf_path: Path) -> str:
        return pdf_path.read_text(encoding="utf-8", errors="replace")


def _output_name(name: str) -> str:
    if name in {"pymupdf", "docling", "marker"}:
        return f"{name}.json"
    return f"{name}.md"


def _nougat_command(isolated_uvx: bool) -> list[str]:
    if not isolated_uvx:
        return ["nougat"]
    return [
        "uvx",
        "--from",
        "nougat-ocr==0.1.17",
        "--with",
        "transformers<4.38",
        "--with",
        "albumentations<2",
        "--with",
        "pypdfium2==4.0.0",
        "nougat",
    ]


def _has_output_content(output: str | dict) -> bool:
    if isinstance(output, str):
        return bool(output.strip())
    if not output:
        return False
    raw_pages = output.get("pages")
    if isinstance(raw_pages, list):
        return any(_has_output_content(page) for page in raw_pages if isinstance(page, dict))
    raw_children = output.get("children")
    if isinstance(raw_children, list):
        return any(_has_output_content(child) for child in raw_children if isinstance(child, dict))
    for key in ("text", "html", "markdown", "content"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return True


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
