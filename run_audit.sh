#!/usr/bin/env bash
set -euo pipefail

uv run ruff check
uv run pytest -q -o addopts=
uv run pre-commit run --all-files
python3 tools/run_gitleaks.py
uv run bandit -r paper_pipeline
uvx pip-audit

echo "Audit completed."
