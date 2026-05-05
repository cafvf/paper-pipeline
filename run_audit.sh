#!/usr/bin/env bash
set -euo pipefail

# Run quick test baseline (ignore Zotero real-access test)
pytest --ignore=tests/test_zotero_api_real_access_regressions.py --maxfail=1 --durations=20

# Run security scanners (non-fatal)
pre-commit run --all-files || true
bash ./tools/run_gitleaks.sh || true
bandit -r paper_pipeline || true
safety check || true

echo "Audit completed"
