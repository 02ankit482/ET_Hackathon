#!/usr/bin/env bash
# render-build.sh — Custom build script for Render deployment
# Set this as your Build Command in Render dashboard:
#   chmod +x render-build.sh && ./render-build.sh

set -e  # exit immediately on any error

echo "==> Installing base requirements..."
pip install -r requirements.txt

echo "==> Installing CrewAI core (no-deps to avoid chromadb conflict)..."
pip install crewai==0.86.0 --no-deps

echo "==> Installing CrewAI runtime dependencies..."
pip install \
  litellm \
  opentelemetry-api \
  opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-http \
  json_repair \
  pydantic-settings

echo "==> Build complete!"
