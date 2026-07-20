# Relance locale des mêmes contrôles que GitHub Actions (CI).
# Usage : pwsh scripts/run_ci.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> Lint (erreurs critiques)" -ForegroundColor Cyan
python -m pip install -q flake8
flake8 src tests --count --select=E9,F63,F7,F82 --show-source --statistics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Tests unitaires" -ForegroundColor Cyan
$env:PYTHONPATH = "src"
pytest tests/ -q --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "OK — CI locale verte" -ForegroundColor Green
