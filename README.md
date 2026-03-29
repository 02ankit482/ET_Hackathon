# Everything Money Main Backend

This hold the backend code for everything money containing agents, endpoints for accessing them, rag & vector db.

---

## ⚡ Quick Start

### 1. Install dependencies

```bash
conda create -n et python=3.11
conda activate et
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
```

### 3. Ingest documents

```bash
python ingest.py --docs_dir ./documents
```

### 4. Start the server

```bash
uvicorn server:app --reload --port 8001
```

---

## 🧪 Demo Web UI (Only for testing)

Run the web server:

```bash
uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

---

## 🔄 Updating Financial Constants

Edit the `FINANCIAL_CONSTANTS` dict in `config.py`.
Re-ingest documents to refresh the constants chunk:

```bash
python ingest.py --docs_dir ./documents
```

---

## 🛠️ Configuration (config.py)

| Setting          | Default | Description                      |
| ---------------- | ------- | -------------------------------- |
| `CHUNK_SIZE`     | 600     | Tokens per chunk                 |
| `CHUNK_OVERLAP`  | 100     | Overlap between chunks           |
| `TOP_K_SEMANTIC` | 6       | Semantic results fetched         |
| `TOP_K_BM25`     | 4       | BM25 keyword results fetched     |
| `TOP_K_FINAL`    | 5       | Final results sent to Claude     |
| `HYBRID_ALPHA`   | 0.65    | Weight of semantic vs BM25 (0→1) |
