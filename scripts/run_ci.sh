#!/usr/bin/env bash
# Relance locale des mêmes contrôles que GitHub Actions (CI).
# Usage : bash scripts/run_ci.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Lint (erreurs critiques)"
python -m pip install -q flake8
flake8 src tests --count --select=E9,F63,F7,F82 --show-source --statistics

echo "==> Tests unitaires"
export PYTHONPATH=src
pytest tests/ -q --tb=short

echo "OK — CI locale verte"
