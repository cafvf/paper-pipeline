from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if shutil.which("gitleaks") is None:
        print("gitleaks not installed. Install from https://github.com/gitleaks/gitleaks/releases")
        return 1

    report = Path(tempfile.gettempdir()) / "paper-pipeline-gitleaks-report.json"
    if report.exists():
        report.unlink()

    command = [
        "gitleaks",
        "dir",
        ".",
        "--config",
        ".gitleaks.toml",
        "--redact",
        "--report-format",
        "json",
        "--report-path",
        str(report),
    ]
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode == 0:
        return 0

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if report.exists() and report.stat().st_size:
        print(report.read_text(encoding="utf-8", errors="replace"))
    print("gitleaks detected potential secrets; aborting.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
