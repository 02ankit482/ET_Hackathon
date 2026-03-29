# ─────────────────────────────────────────────────────────────
# Finance RAG + CrewAI — Docker Image
# Base: Python 3.10 slim (Debian Bookworm)
# ─────────────────────────────────────────────────────────────

FROM python:3.10-slim-bookworm

# ---------- system deps -------------------------------------------
# libmagic  → python-magic (unstructured)
# libgomp1  → OpenMP for torch / onnxruntime
# build-essential / rustc / cargo → needed by some Python wheel builds
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libmagic1 \
        libgomp1 \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---------- workdir -----------------------------------------------
WORKDIR /app

# ---------- copy requirements first (layer caching) ---------------
COPY requirements.txt .

# ---------- pip: upgrade toolchain, install deps ------------------
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# requirements.txt = pip freeze output with crewai line removed.
# Install everything first (all transitive deps are already pinned).
RUN pip install --no-cache-dir -r requirements.txt

# Install crewai separately with --no-deps so it cannot pull
# chromadb>=1.0 and break our 0.5.23 vector store.
# Change the version below if your freeze shows a different one.
RUN pip install --no-cache-dir "crewai==0.86.0" --no-deps

# ---------- copy project files ------------------------------------
COPY . .

# Create directories that the app needs at runtime
RUN mkdir -p documents frontend chroma_db

# Move static frontend files into the expected location
# (server.py mounts ./frontend as /static and serves index.html)
RUN if [ -f index.html ]; then cp index.html frontend/index.html; fi
RUN if [ -f app.js ];    then cp app.js    frontend/app.js;    fi

# ---------- runtime env defaults ----------------------------------
# Override GOOGLE_API_KEY at runtime via:  docker run -e GOOGLE_API_KEY=... 
ENV GOOGLE_API_KEY=""
ENV GEMINI_MAX_OUTPUT_TOKENS=5000
ENV GEMINI_CONTEXT_MAX_HIT_CHARS=2500
ENV GEMINI_CONTEXT_MAX_TOTAL_CHARS=9000
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ---------- expose port -------------------------------------------
EXPOSE 8000

# ---------- entrypoint -------------------------------------------
# Use shell form so $PORT expansion works
CMD uvicorn server:app --host 0.0.0.0 --port $PORT