#!/usr/bin/env bash
# render-build.sh
# Build Command in Render: chmod +x render-build.sh && ./render-build.sh

set -e

echo "==> Installing all dependencies..."
pip install -r requirements.txt

echo "==> Installing CrewAI core (--no-deps avoids chromadb version conflict)..."
pip install crewai==0.86.0 --no-deps

echo "==> Build complete!"
