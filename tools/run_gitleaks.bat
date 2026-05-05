@echo off
:: Simple wrapper to run gitleaks on Windows for pre-commit
@where gitleaks >nul 2>&1
@if %ERRORLEVEL% NEQ 0 (
  echo gitleaks not found. Install from https://github.com/zricethezav/gitleaks/releases
  exit /b 1
)

gitleaks detect --source . --report-format json --report-path gitleaks-report.json
if %ERRORLEVEL% NEQ 0 (
  echo gitleaks detected potential secrets; see gitleaks-report.json
  type gitleaks-report.json
  exit /b 1
)

exit /b 0
