#!/usr/bin/env bash
# render-build.sh
# ─────────────────────────────────────────────────────────────
# Render Build Command:
#   chmod +x render-build.sh && ./render-build.sh
#
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

echo "==> Installing crewai's missing runtime deps explicitly …"
pip install \
    appdirs==1.4.4 \
    setuptools \
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
    opentelemetry-instrumentation==0.61b0 \
    opentelemetry-instrumentation-asgi==0.61b0 \
    opentelemetry-semantic-conventions==0.61b0 \
    opentelemetry-util-http==0.61b0 \
    opentelemetry-exporter-otlp-proto-common==1.40.0 \
    "auth0-python>=4.7.1" \
    "instructor>=1.3.3" \
    "jsonref>=1.1.0" \
    "openpyxl>=3.1.5" \
    "tomli-w>=1.1.0"

echo "==> Force-pinning conflicting packages to correct versions …"
# protobuf keeps getting pulled up to 6.x by transitive deps.
# google-ai-generativelanguage==0.6.6 hard-requires protobuf<5.0.0
# so we force it back down AFTER everything else is installed.
# opentelemetry-exporter-otlp-proto-grpc 1.15.0 conflicts with
# opentelemetry-proto 1.40.0 so we align them all to 1.40.0.
pip install --force-reinstall \
    "protobuf==4.25.8" \
    "opentelemetry-proto==1.40.0" \
    "opentelemetry-exporter-otlp-proto-grpc==1.40.0" \
    "opentelemetry-exporter-otlp-proto-common==1.40.0"

echo "==> Setting up frontend directory …"
mkdir -p frontend
[ -f index.html ] && cp index.html frontend/index.html
[ -f app.js ]     && cp app.js     frontend/app.js

echo "==> Build complete!"
