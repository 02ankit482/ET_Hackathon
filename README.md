# 💹 Finance RAG Chatbot

A personal finance advisor chatbot powered by RAG (Retrieval-Augmented Generation),
Claude (Anthropic), hybrid search, and a user profile system.

---

## 🗂️ Project Structure

```
finance_rag/
│
├── config.py          # Financial constants, metadata taxonomy, system prompt
├── ingest.py          # Document ingestion pipeline (PDF/TXT/DOCX → ChromaDB)
├── retriever.py       # Hybrid retriever (Semantic + BM25 + RRF merge)
├── user_profile.py    # User financial profile dataclass + CLI wizard
├── chatbot.py         # Main chatbot loop (entry point)
├── requirements.txt
└── .env.example
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your API key
```bash
cp .env.example .env
# Edit .env and add your Gemini API key (GOOGLE_API_KEY)
```

### 3. Add your finance documents
```
mkdir documents
# Copy your PDF / TXT / DOCX files into documents/
```

Recommended sources:
- Zerodha Varsity PDFs (free at zerodha.com/varsity)
- SEBI investor education PDFs (sebi.gov.in)
- Any investing books converted to PDF/TXT

### 4. Ingest documents
```bash
python ingest.py --docs_dir ./documents
```

### 5. Start the chatbot
```bash
python chatbot.py
```

---

## 🧪 Demo Web UI (Frontend)

Run the web server:
```bash
uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

Open:
```text
http://127.0.0.1:8000
```

---

## 🧠 How It Works

```
User query
    │
    ▼
[HybridRetriever]
    ├── Semantic search (ChromaDB / sentence-transformers)
    ├── Keyword search  (BM25Okapi)
    └── Merge via RRF   (Reciprocal Rank Fusion)
    │
    ▼
[Context + User Profile + Financial Constants]
    │
    ▼
[Claude claude-sonnet-4-20250514 via Anthropic API]
    │
    ▼
Personalised advice
```

---

## 🏷️ Metadata Tags (auto-applied on ingest)

| Tag            | Values                                                    |
|----------------|-----------------------------------------------------------|
| `topic`        | mutual_funds, stocks, bonds, etf, tax_planning, retirement, … |
| `asset_class`  | equity, debt, hybrid, gold, real_estate, cash_equivalents |
| `risk_level`   | low, moderate, high, very_high                            |
| `user_type`    | beginner, intermediate, advanced                          |
| `source_file`  | original filename                                         |

---

## 💬 Chatbot Commands

| Command    | Description                        |
|------------|------------------------------------|
| `/profile` | Show your current financial profile |
| `/clear`   | Reset conversation history          |
| `/save`    | Save profile to `user_profile.json` |
| `/help`    | List all commands                   |
| `/quit`    | Exit the chatbot                    |

---

## 🔄 Updating Financial Constants

Edit the `FINANCIAL_CONSTANTS` dict in `config.py`.
Re-ingest documents to refresh the constants chunk:
```bash
python ingest.py --docs_dir ./documents
```

---

## 🛠️ Configuration (config.py)

| Setting          | Default | Description                              |
|------------------|---------|------------------------------------------|
| `CHUNK_SIZE`     | 600     | Tokens per chunk                         |
| `CHUNK_OVERLAP`  | 100     | Overlap between chunks                   |
| `TOP_K_SEMANTIC` | 6       | Semantic results fetched                 |
| `TOP_K_BM25`     | 4       | BM25 keyword results fetched             |
| `TOP_K_FINAL`    | 5       | Final results sent to Claude             |
| `HYBRID_ALPHA`   | 0.65    | Weight of semantic vs BM25 (0→1)        |
