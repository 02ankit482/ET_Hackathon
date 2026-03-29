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
# Google Gemini API Key for CrewAI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # CrewAI expects GEMINI_API_KEY
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_MODEL   = "gemini-2.5-flash"  
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "5000"))

# Keep retrieved context from consuming the whole context window.
GEMINI_CONTEXT_MAX_HIT_CHARS = int(os.getenv("GEMINI_CONTEXT_MAX_HIT_CHARS", "2500"))
GEMINI_CONTEXT_MAX_TOTAL_CHARS = int(os.getenv("GEMINI_CONTEXT_MAX_TOTAL_CHARS", "9000"))

# ── MongoDB ───────────────────────────────────────────────────
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "everything_money")

# ── CrewAI LLM Config ────────────────────────────────────────
# Using DeepSeek via OpenRouter for structured output support
# DeepSeek has better rate limits than Gemini and handles Dict fields properly
PLANNING_LLM = "openrouter/deepseek/deepseek-chat"  # For all 6 planning agents
CHAT_LLM = "openrouter/deepseek/deepseek-chat"      # For chat agent

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
# FINANCIAL CONSTANTS (India-focused — FY 2025-26)
# ─────────────────────────────────────────────────────────────
FINANCIAL_CONSTANTS = {
    # ── Macro ─────────────────────────────────────────────────
    "inflation_rate_pct":           6.5,
    "education_inflation_pct":      10.0,   # Education CPI (higher)
    "repo_rate_pct":                6.5,
    "avg_equity_return_pct":        12.0,
    "avg_debt_return_pct":          7.0,
    "avg_gold_return_pct":          8.0,
    "avg_fd_rate_pct":              7.25,
    "safe_withdrawal_rate_pct":     4.0,    # SWR for retirement

    # ── Tax — NEW REGIME FY 2025-26 (default) ────────────────
    "tax_slabs_new_regime_fy2526": [
        {"upto": 400000,   "rate_pct": 0},
        {"upto": 800000,   "rate_pct": 5},
        {"upto": 1200000,  "rate_pct": 10},
        {"upto": 1600000,  "rate_pct": 15},
        {"upto": 2000000,  "rate_pct": 20},
        {"upto": 2400000,  "rate_pct": 25},
        {"upto": None,     "rate_pct": 30},
    ],
    "new_regime_standard_deduction":  75000,
    "new_regime_87a_rebate_limit":    60000,    # Max rebate amount
    "new_regime_87a_income_limit":    1200000,  # Income up to which rebate applies

    # ── Tax — OLD REGIME FY 2025-26 ──────────────────────────
    "tax_slabs_old_regime_fy2526": [
        {"upto": 250000,   "rate_pct": 0},
        {"upto": 500000,   "rate_pct": 5},
        {"upto": 1000000,  "rate_pct": 20},
        {"upto": None,     "rate_pct": 30},
    ],
    "old_regime_standard_deduction":  50000,
    "old_regime_87a_rebate_limit":    12500,
    "old_regime_87a_income_limit":    500000,

    # ── Deduction Limits ─────────────────────────────────────
    "section_80c_limit":              150000,   # PPF, ELSS, LIC, EPF, etc.
    "section_80ccd_1b_limit":         50000,    # NPS additional (old regime)
    "section_80ccd_2_limit_pct":      10,       # Employer NPS (BOTH regimes)
    "section_80d_self_limit":         25000,    # Health insurance (self/family)
    "section_80d_parents_limit":      25000,    # Parents (non-senior)
    "section_80d_parents_senior_limit": 50000,  # Parents (senior citizen)
    "section_24_home_loan_limit":     200000,   # Home loan interest deduction
    "hra_exemption_metro_pct":        50,       # HRA exemption (metro cities)
    "hra_exemption_nonmetro_pct":     40,       # HRA exemption (non-metro)

    # ── Capital Gains ────────────────────────────────────────
    "ltcg_equity_pct":              12.5,       # Above ₹1.25L
    "stcg_equity_pct":              20.0,
    "ltcg_debt_pct":                "slab",     # Taxed at income slab
    "ltcg_equity_exemption_inr":    125000,

    # ── Investment Limits ────────────────────────────────────
    "ppf_annual_limit_inr":         150000,
    "nps_80ccd_1b_limit_inr":       50000,
    "elss_80c_within_limit":        True,       # Part of 80C ₹1.5L
    "epf_employee_rate_pct":        12.0,
    "fd_tds_threshold_inr":         40000,

    # ── Insurance Rules of Thumb ─────────────────────────────
    "life_insurance_multiplier":    10,         # 10-15× annual income
    "health_insurance_min_metro":   1000000,    # ₹10L min in metros
    "health_insurance_min_nonmetro": 500000,    # ₹5L min
    "emergency_fund_months":        6,

    # ── SEBI MF Categorization ───────────────────────────────
    "sebi_mf_categories": [
        "large_cap", "mid_cap", "small_cap", "large_mid_cap",
        "multi_cap", "flexi_cap", "focused", "elss",
        "debt_short_duration", "debt_medium_duration", "debt_long_duration",
        "debt_liquid", "debt_gilt", "hybrid_aggressive", "hybrid_conservative",
        "index_fund", "gold_fund",
    ],
}

# ─────────────────────────────────────────────────────────────
# MANDATORY SEBI DISCLAIMER
# Must appear on every plan output and substantive chat response
# ─────────────────────────────────────────────────────────────
SEBI_DISCLAIMER = (
    "⚠️ IMPORTANT DISCLAIMER: This is AI-generated educational guidance, "
    "NOT licensed financial advice. This platform is NOT a SEBI-registered "
    "Investment Adviser (IA) under SEBI (Investment Advisers) Regulations, "
    "2013. The information provided is for educational and informational "
    "purposes only. AI tools are used in generating this guidance. Please "
    "consult a SEBI-registered Investment Adviser or a qualified financial "
    "planner before making investment decisions. Past performance does not "
    "guarantee future results. All investments carry risk including "
    "possible loss of principal."
)

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
- Never recommend specific stocks, mutual fund schemes, or ISINs; recommend asset classes and fund categories only.
- Keep language simple for beginners; use technical terms for advanced users.
- End every response with a 1-line "Next Step" the user can act on today.
- Always include a brief disclaimer that this is AI guidance, not licensed financial advice.

## Current Financial Constants (India, FY 2025-26)
{constants}

## User Profile
{user_profile}

## Retrieved Knowledge
{context}
"""
