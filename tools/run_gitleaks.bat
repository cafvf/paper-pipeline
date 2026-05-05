@echo off
:: Simple wrapper to run gitleaks on Windows for pre-commit
@where gitleaks >nul 2>&1
@if %ERRORLEVEL% NEQ 0 (
  echo gitleaks not found. Install from https://github.com/gitleaks/gitleaks/releases
  exit /b 1
)

set REPORT=%TEMP%\paper-pipeline-gitleaks-report.json
if exist "%REPORT%" del "%REPORT%"

gitleaks dir . --config .gitleaks.toml --redact --report-format json --report-path "%REPORT%"
if %ERRORLEVEL% NEQ 0 (
  echo gitleaks detected potential secrets; see %REPORT%
  type "%REPORT%"
  exit /b 1
)

exit /b 0
