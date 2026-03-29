#!/usr/bin/env bash
# render-build.sh
# ─────────────────────────────────────────────────────────────
# Render Build Command:
#   chmod +x render-build.sh && ./render-build.sh
# Render Environment Variable:
#   PYTHON_VERSION = 3.10.14
# ─────────────────────────────────────────────────────────────

set -e

echo "==> Upgrading pip / setuptools / wheel …"
pip install --upgrade pip setuptools wheel

echo "==> Installing main dependencies …"
pip install -r requirements.txt

echo "==> Installing crewai==0.86.0 (--no-deps to avoid chromadb>=1.0 conflict) …"
pip install "crewai==0.86.0" --no-deps

echo "==> Installing crewai's missing runtime deps …"
pip install \
    appdirs==1.4.4 \
    backoff==2.2.1 \
    click==8.3.1 \
    shellingham==1.5.4 \
    rich-toolkit==0.19.7 \
    deepdiff==8.6.2 \
    orderly-set==5.5.0 \
    pyvis==0.3.2 \
    jsonpath-python==1.1.5 \
    json_repair==0.58.7 \
    durationpy==0.10 \
    kubernetes==35.0.0 \
    websocket-client==1.9.0 \
    "auth0-python>=4.7.1" \
    "instructor>=1.3.3" \
    "jsonref>=1.1.0" \
    "openpyxl>=3.1.5" \
    "tomli-w>=1.1.0" \
    "pdfplumber>=0.11.4" \
    "uv>=0.4.25"

echo "==> Downgrading opentelemetry stack to 1.26.x (last protobuf-4.x compatible version) …"
pip install --force-reinstall --no-deps \
    "opentelemetry-proto==1.26.0" \
    "opentelemetry-exporter-otlp-proto-common==1.26.0" \
    "opentelemetry-exporter-otlp-proto-grpc==1.26.0" \
    "opentelemetry-exporter-otlp-proto-http==1.26.0" \
    "opentelemetry-api==1.26.0" \
    "opentelemetry-sdk==1.26.0" \
    "opentelemetry-semantic-conventions==0.47b0" \
    "opentelemetry-instrumentation==0.47b0" \
    "opentelemetry-instrumentation-asgi==0.47b0" \
    "opentelemetry-instrumentation-fastapi==0.47b0" \
    "opentelemetry-util-http==0.47b0"

echo "==> Force-pinning protobuf + fixing stragglers …"
# Must come AFTER all other installs so nothing pulls protobuf back up.
# setuptools reinstalled last so pkg_resources is always present.
# importlib-metadata pinned to <=8.0.0 as required by opentelemetry-api 1.26.0.
pip install --force-reinstall \
    "protobuf==4.25.8" \
    "Deprecated==1.3.1" \
    "importlib-metadata==8.0.0" \
    "setuptools"

echo "==> Setting up frontend directory …"
mkdir -p frontend
[ -f index.html ] && cp index.html frontend/index.html
[ -f app.js ]     && cp app.js     frontend/app.js

echo "==> Running document ingestion …"
# Builds the ChromaDB vector store from ./documents/ at deploy time.
# Make sure your PDF/TXT/DOCX files are committed to the repo under documents/
if [ -d "./documents" ] && [ "$(ls -A ./documents 2>/dev/null)" ]; then
    python ingest.py --docs_dir ./documents
    echo "==> Ingestion complete!"
else
    echo "==> WARNING: No documents found in ./documents — RAG will return no results."
    echo "==> Commit your PDF/TXT/DOCX files to the documents/ folder and redeploy."
fi

echo "==> Build complete!"
