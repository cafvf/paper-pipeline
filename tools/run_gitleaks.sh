#!/usr/bin/env bash
set -euo pipefail
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed. Install from https://github.com/gitleaks/gitleaks/releases"
  exit 1
fi

report="${TMPDIR:-/tmp}/paper-pipeline-gitleaks-report.json"
rm -f "$report"

gitleaks dir . --config .gitleaks.toml --redact --report-format json --report-path "$report" || true
if [ -s "$report" ]; then
  cat "$report"
  echo "gitleaks detected potential secrets; aborting."
  exit 1
fi

exit 0
