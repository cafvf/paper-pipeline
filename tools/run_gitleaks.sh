#!/usr/bin/env bash
set -euo pipefail
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed. Install from https://github.com/zricethezav/gitleaks/releases"
  exit 1
fi

gitleaks detect --source . --report-format json --report-path gitleaks-report.json || true
if [ -s gitleaks-report.json ]; then
  cat gitleaks-report.json
  echo "gitleaks detected potential secrets; aborting."
  exit 1
fi

exit 0
