# ingest.py
# ─────────────────────────────────────────────────────────────
# Loads PDFs / TXTs / DOCXs from a folder, chunks them by
# concept, tags metadata, and upserts into ChromaDB.
#
# Usage:
#   python ingest.py --docs_dir ./my_documents
# ─────────────────────────────────────────────────────────────

import os
import re
import json
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rich.console import Console
from rich.progress import track

from config import (
    CHROMA_DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL,
    CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK_LENGTH,
    VALID_TOPICS, VALID_ASSET_CLASSES, VALID_RISK_LEVELS, VALID_USER_TYPES,
    FINANCIAL_CONSTANTS,
)

console = Console()


# ── Document Loaders ─────────────────────────────────────────

def load_pdf(path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_txt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def load_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


LOADERS = {".pdf": load_pdf, ".txt": load_txt, ".docx": load_docx}


def load_document(path: str) -> str:
    """Load any supported document type into raw text."""
    ext = Path(path).suffix.lower()
    loader = LOADERS.get(ext)
    if not loader:
        raise ValueError(f"Unsupported file type: {ext}")
    return loader(path)


# ── Concept-Based Chunking ────────────────────────────────────
# Financial documents are chunked by concept boundaries
# (section headers, double newlines) before falling back to
# size-based splitting. This keeps definitions and formulas
# together in a single chunk.

CONCEPT_BOUNDARY = re.compile(
    r"(?m)^(?:#{1,3}\s.+|[A-Z][A-Z\s]{4,}:|"  # Markdown headers / ALL CAPS labels
    r"\d+\.\s+[A-Z].{5,}|"                      # Numbered sections
    r"(?:Chapter|Section|Part)\s+\d+)",          # Chapter/Section markers
)


def concept_split(text: str) -> List[str]:
    """
    Primary splitter: break on section/concept boundaries.
    Falls back to LangChain RecursiveCharacterTextSplitter for
    oversized sections.
    """
    boundaries = [m.start() for m in CONCEPT_BOUNDARY.finditer(text)]

    if not boundaries:
        # No headers found — use size-based splitter directly
        return size_split(text)

    sections = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        sections.append(text[start:end])

    # Further split any section still too large
    chunks = []
    for section in sections:
        if len(section.split()) > CHUNK_SIZE * 1.5:
            chunks.extend(size_split(section))
        else:
            chunks.append(section)
    return chunks


def size_split(text: str) -> List[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


# ── Metadata Auto-Tagger ─────────────────────────────────────
# Assigns metadata tags based on keyword presence in the chunk.
# You can extend KEYWORD_MAP to improve accuracy.

KEYWORD_MAP: Dict[str, Dict[str, List[str]]] = {
    "topic": {
        "mutual_funds":        ["mutual fund", "sip", "nfo", "nav", "elss", "amc"],
        "stocks":              ["stock", "equity share", "nse", "bse", "ipo", "dividend"],
        "bonds":               ["bond", "debenture", "gilt", "coupon", "maturity"],
        "etf":                 ["etf", "exchange traded fund", "index fund", "nifty 50"],
        "real_estate":         ["real estate", "reit", "property", "land", "rental income"],
        "insurance":           ["insurance", "term plan", "ulip", "premium", "sum assured"],
        "tax_planning":        ["tax", "80c", "80d", "ltcg", "stcg", "itr", "tds", "hra"],
        "retirement":          ["retirement", "ppf", "nps", "pension", "epf", "corpus"],
        "emergency_fund":      ["emergency fund", "liquid fund", "contingency"],
        "goal_planning":       ["goal", "target", "time horizon", "sip calculator", "cagr"],
        "behavioral_finance":  ["bias", "loss aversion", "herding", "psychology", "emotion"],
        "macroeconomics":      ["inflation", "repo rate", "gdp", "rbi", "monetary policy"],
        "fixed_income":        ["fd", "fixed deposit", "recurring deposit", "rd", "post office"],
    },
    "asset_class": {
        "equity":              ["equity", "stock", "share", "nifty", "sensex"],
        "debt":                ["debt", "bond", "fd", "fixed income", "gilt"],
        "hybrid":              ["hybrid", "balanced", "multi asset", "aggressive hybrid"],
        "gold":                ["gold", "sovereign gold bond", "sgb", "gold etf"],
        "real_estate":         ["real estate", "reit", "property"],
        "cash_equivalents":    ["liquid fund", "overnight fund", "money market", "savings"],
    },
    "risk_level": {
        "low":                 ["low risk", "capital protection", "guaranteed", "liquid"],
        "moderate":            ["moderate risk", "balanced", "hybrid", "debt"],
        "high":                ["high risk", "equity", "volatile", "small cap", "mid cap"],
        "very_high":           ["very high risk", "derivatives", "futures", "options", "crypto"],
    },
    "user_type": {
        "beginner":            ["basics", "introduction", "beginner", "what is", "simple"],
        "intermediate":        ["strategy", "allocation", "portfolio", "rebalancing"],
        "advanced":            ["valuation", "pe ratio", "dcf", "options", "derivatives"],
    },
}


def auto_tag(chunk: str, filename: str) -> Dict[str, str]:
    """Keyword-based metadata tagger. Falls back to 'general' / first valid value."""
    lower = chunk.lower()
    tags: Dict[str, str] = {}

    for meta_key, category_map in KEYWORD_MAP.items():
        best = None
        best_count = 0
        for category, keywords in category_map.items():
            count = sum(1 for kw in keywords if kw in lower)
            if count > best_count:
                best_count = count
                best = category
        tags[meta_key] = best if best else {
            "topic": "general",
            "asset_class": "multi_asset",
            "risk_level": "moderate",
            "user_type": "beginner",
        }[meta_key]

    tags["source_file"] = Path(filename).name
    return tags


# ── Financial Constants Chunk ─────────────────────────────────

def constants_as_chunk() -> Dict[str, Any]:
    """Serialize FINANCIAL_CONSTANTS as a special always-fresh chunk."""
    text = "FINANCIAL CONSTANTS (India, FY 2024-25):\n"
    for k, v in FINANCIAL_CONSTANTS.items():
        text += f"  {k}: {json.dumps(v)}\n"
    return {
        "text": text,
        "metadata": {
            "topic": "tax_planning",
            "asset_class": "multi_asset",
            "risk_level": "low",
            "user_type": "beginner",
            "source_file": "financial_constants",
        },
    }


# ── ChromaDB Upsert ───────────────────────────────────────────

def get_collection():
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_id(text: str, filename: str, chunk_index: int) -> str:
    """
    Stable, deterministic ID so re-runs upsert, not duplicate.

    Includes a hash of the full chunk text + an index to avoid collisions
    when multiple chunks share the same prefix.
    """
    h = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
    return f"{filename}::{chunk_index}::{h}"


def ingest_documents(docs_dir: str):
    collection = get_collection()
    docs_path  = Path(docs_dir)
    files      = [f for f in docs_path.iterdir() if f.suffix.lower() in LOADERS]

    if not files:
        console.print(f"[red]No supported files found in {docs_dir}[/red]")
        return

    all_chunks, all_ids, all_meta = [], [], []

    # Always include the financial constants chunk
    c = constants_as_chunk()
    cid = chunk_id(c["text"], "financial_constants", 0)
    all_chunks.append(c["text"])
    all_ids.append(cid)
    all_meta.append(c["metadata"])

    for file in track(files, description="[cyan]Ingesting documents…"):
        try:
            raw_text = load_document(str(file))
        except Exception as e:
            console.print(f"[red]  ✗ {file.name}: {e}[/red]")
            continue

        chunks = concept_split(raw_text)
        good   = [c for c in chunks if len(c.strip()) >= MIN_CHUNK_LENGTH]
        console.print(f"  [green]✓ {file.name}[/green] → {len(good)} chunks")

        for idx, chunk in enumerate(good):
            cid  = chunk_id(chunk, file.name, idx)
            meta = auto_tag(chunk, file.name)
            all_chunks.append(chunk)
            all_ids.append(cid)
            all_meta.append(meta)

    # Batch upsert
    BATCH = 100
    for i in range(0, len(all_chunks), BATCH):
        collection.upsert(
            documents=all_chunks[i:i+BATCH],
            ids=all_ids[i:i+BATCH],
            metadatas=all_meta[i:i+BATCH],
        )

    console.print(f"\n[bold green]✅ Ingested {len(all_chunks)} chunks into '{COLLECTION_NAME}'[/bold green]")


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Finance RAG — Document Ingestion")
    parser.add_argument("--docs_dir", default="./documents",
                        help="Folder containing PDF/TXT/DOCX files")
    args = parser.parse_args()
    ingest_documents(args.docs_dir)





#uvicorn server:app --reload --host 127.0.0.1 --port 800