#!/usr/bin/env bash
# render-build.sh
# ─────────────────────────────────────────────────────────────
# Render Build Command:
#   chmod +x render-build.sh && ./render-build.sh
#
# Render Environment Variable to set:
#   PYTHON_VERSION = 3.10.14
# ─────────────────────────────────────────────────────────────

set -e

echo "==> Upgrading pip / setuptools / wheel …"
pip install --upgrade pip setuptools wheel

echo "==> Installing main dependencies …"
pip install -r requirements.txt

echo "==> Installing crewai==0.86.0 (--no-deps to avoid chromadb>=1.0 conflict) …"
pip install "crewai==0.86.0" --no-deps

echo "==> Setting up frontend directory …"
mkdir -p frontend
[ -f index.html ] && cp index.html frontend/index.html
[ -f app.js ]     && cp app.js     frontend/app.js

echo "==> Build complete!"