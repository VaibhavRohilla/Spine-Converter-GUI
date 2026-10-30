#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy
.venv/bin/python -m build
npm run typecheck
npm run lint
npm run build
npm test
git diff --check
# Optional real Qt smoke: install .[qt-smoke] and supply a fresh output directory.
# .venv/bin/python viewer/scripts/qt_smoke.py /tmp/fnx-b4-qt-new
