# config.py
# ─────────────────────────────────────────────────────────────
# Central config: financial constants, metadata taxonomy,
# chunking rules, and model settings.
# Update FINANCIAL_CONSTANTS quarterly.
# ─────────────────────────────────────────────────────────────

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory (so paths work from server/uvicorn too)
BASE_DIR = Path(__file__).resolve().parent

# Load env from this folder explicitly (works regardless of cwd)
load_dotenv(dotenv_path=BASE_DIR / ".env")

# ── API ───────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "5000"))

# Keep retrieved context from consuming the whole context window.
GEMINI_CONTEXT_MAX_HIT_CHARS = int(os.getenv("GEMINI_CONTEXT_MAX_HIT_CHARS", "2500"))
GEMINI_CONTEXT_MAX_TOTAL_CHARS = int(os.getenv("GEMINI_CONTEXT_MAX_TOTAL_CHARS", "9000"))

# ── Vector Store ──────────────────────────────────────────────
CHROMA_DB_PATH      = str(BASE_DIR / "chroma_db")
COLLECTION_NAME     = "finance_docs"
EMBEDDING_MODEL     = "all-MiniLM-L6-v2"   # fast & accurate

# ── Chunking ──────────────────────────────────────────────────
CHUNK_SIZE          = 600    # tokens per chunk
CHUNK_OVERLAP       = 100    # overlap to preserve context
MIN_CHUNK_LENGTH    = 80     # discard very short chunks

# ── Retrieval ─────────────────────────────────────────────────
TOP_K_SEMANTIC      = 6      # semantic results fetched
TOP_K_BM25          = 4      # keyword results fetched
TOP_K_FINAL         = 5      # final merged results sent to LLM
HYBRID_ALPHA        = 0.65   # 0 = pure BM25, 1 = pure semantic

# ─────────────────────────────────────────────────────────────
# FINANCIAL CONSTANTS (India-focused — update quarterly)
# ─────────────────────────────────────────────────────────────
FINANCIAL_CONSTANTS = {
    # Macro
    "inflation_rate_pct":           6.5,
    "repo_rate_pct":                6.5,
    "avg_equity_return_pct":        12.0,
    "avg_debt_return_pct":          7.0,
    "avg_fd_rate_pct":              7.25,

    # Tax – New Regime FY 2024-25
    "tax_slabs_new_regime": [
        {"upto": 300000,  "rate_pct": 0},
        {"upto": 700000,  "rate_pct": 5},
        {"upto": 1000000, "rate_pct": 10},
        {"upto": 1200000, "rate_pct": 15},
        {"upto": 1500000, "rate_pct": 20},
        {"upto": None,    "rate_pct": 30},
    ],
    "ltcg_equity_pct":              12.5,   # above ₹1.25 L
    "stcg_equity_pct":              20.0,
    "ltcg_debt_pct":                "slab", # taxed at income slab
    "ltcg_equity_exemption_inr":    125000,

    # Limits
    "ppf_annual_limit_inr":         150000,
    "nps_80ccd_1b_limit_inr":       50000,
    "elss_80c_limit_inr":           150000,
    "epf_employee_rate_pct":        12.0,
    "fd_tds_threshold_inr":         40000,

    # Rules of thumb
    "emergency_fund_months":        6,
    "life_insurance_multiplier":    10,     # 10× annual income
    "rule_of_72_desc":              "72 / annual_return_pct = years to double",
    "equity_allocation_formula":    "100 - age  (aggressive: 110 - age)",
}

# ─────────────────────────────────────────────────────────────
# METADATA TAXONOMY
# Every document chunk must have these metadata keys.
# ─────────────────────────────────────────────────────────────
VALID_TOPICS = [
    "mutual_funds", "stocks", "bonds", "etf", "real_estate",
    "insurance", "tax_planning", "retirement", "emergency_fund",
    "goal_planning", "behavioral_finance", "macroeconomics",
    "fixed_income", "derivatives", "crypto", "general",
]

VALID_ASSET_CLASSES = [
    "equity", "debt", "hybrid", "gold", "real_estate",
    "cash_equivalents", "alternative", "multi_asset",
]

VALID_RISK_LEVELS = ["low", "moderate", "high", "very_high"]

VALID_USER_TYPES = ["beginner", "intermediate", "advanced"]

# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT TEMPLATE (injected per query)
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a knowledgeable and empathetic financial advisor chatbot \
specialized in Indian personal finance and investing.

## Your behaviour
- Give specific, actionable advice grounded ONLY in the retrieved context below.
- Always tailor advice to the user's profile: age, income, risk appetite, goals.
- Quote financial constants (returns, tax rates, limits) precisely — never guess.
- If the context doesn't cover the question, say so clearly.
- Never recommend specific stocks or crypto; recommend asset classes and fund categories.
- Keep language simple for beginners; use technical terms for advanced users.
- End every response with a 1-line "Next Step" the user can act on today.

## Current Financial Constants (India, FY 2024-25)
{constants}

## User Profile
{user_profile}

## Retrieved Knowledge
{context}
"""
