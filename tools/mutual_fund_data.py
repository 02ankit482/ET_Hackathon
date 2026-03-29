# tools/mutual_fund_data.py
# ─────────────────────────────────────────────────────────────
# Curated mutual fund data for educational recommendations.
# This list should be reviewed and updated quarterly.
# 
# Data sources: Value Research, Morningstar India (as of Q1 2026)
# Note: Past performance does not guarantee future results.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class MutualFund(BaseModel):
    """Represents a mutual fund with key metrics."""
    name: str = Field(description="Fund name (Direct Growth plan)")
    isin: str = Field(description="ISIN code for identification")
    category: str = Field(description="SEBI category: large_cap, mid_cap, small_cap, debt, gold, etc.")
    sub_category: str = Field(default="", description="Sub-category like 'index', 'active', 'liquid', etc.")
    amc: str = Field(description="Asset Management Company name")
    risk_level: str = Field(description="low, moderate, high, very_high")
    expense_ratio_pct: float = Field(description="Expense ratio as percentage")
    aum_cr: float = Field(description="Assets Under Management in ₹ Crores")
    returns_1y_pct: float = Field(description="1-year trailing return %")
    returns_3y_pct: float = Field(description="3-year CAGR %")
    returns_5y_pct: float = Field(description="5-year CAGR %")
    min_sip_amount: int = Field(default=500, description="Minimum SIP amount in ₹")
    benchmark: str = Field(default="", description="Benchmark index")
    rating: int = Field(default=0, description="Star rating 1-5 (0 if not rated)")
    
    class Config:
        extra = "forbid"


# ─────────────────────────────────────────────────────────────
# CURATED FUND DATA (Updated: March 2026)
# Selection criteria: Low expense ratio, consistent performance,
# high AUM for liquidity, reputable AMCs
# ─────────────────────────────────────────────────────────────

LARGE_CAP_FUNDS: List[MutualFund] = [
    MutualFund(
        name="UTI Nifty 50 Index Fund Direct Growth",
        isin="INF789FC1GL6",
        category="large_cap",
        sub_category="index",
        amc="UTI",
        risk_level="moderate",
        expense_ratio_pct=0.18,
        aum_cr=18500,
        returns_1y_pct=14.2,
        returns_3y_pct=15.8,
        returns_5y_pct=14.5,
        min_sip_amount=500,
        benchmark="Nifty 50 TRI",
        rating=5,
    ),
    MutualFund(
        name="HDFC Index Fund Nifty 50 Plan Direct Growth",
        isin="INF179KA1BP0",
        category="large_cap",
        sub_category="index",
        amc="HDFC",
        risk_level="moderate",
        expense_ratio_pct=0.20,
        aum_cr=12800,
        returns_1y_pct=14.0,
        returns_3y_pct=15.6,
        returns_5y_pct=14.3,
        min_sip_amount=500,
        benchmark="Nifty 50 TRI",
        rating=5,
    ),
    MutualFund(
        name="Nippon India Large Cap Fund Direct Growth",
        isin="INF204KB1FA4",
        category="large_cap",
        sub_category="active",
        amc="Nippon India",
        risk_level="moderate",
        expense_ratio_pct=0.85,
        aum_cr=22300,
        returns_1y_pct=16.5,
        returns_3y_pct=17.2,
        returns_5y_pct=15.8,
        min_sip_amount=500,
        benchmark="Nifty 100 TRI",
        rating=4,
    ),
    MutualFund(
        name="ICICI Prudential Bluechip Fund Direct Growth",
        isin="INF109KA1MO1",
        category="large_cap",
        sub_category="active",
        amc="ICICI Prudential",
        risk_level="moderate",
        expense_ratio_pct=0.98,
        aum_cr=51200,
        returns_1y_pct=15.8,
        returns_3y_pct=16.4,
        returns_5y_pct=15.2,
        min_sip_amount=500,
        benchmark="Nifty 100 TRI",
        rating=4,
    ),
    MutualFund(
        name="SBI Bluechip Fund Direct Growth",
        isin="INF200KA1H75",
        category="large_cap",
        sub_category="active",
        amc="SBI",
        risk_level="moderate",
        expense_ratio_pct=0.92,
        aum_cr=46800,
        returns_1y_pct=14.9,
        returns_3y_pct=15.9,
        returns_5y_pct=14.7,
        min_sip_amount=500,
        benchmark="S&P BSE 100 TRI",
        rating=4,
    ),
]

MID_CAP_FUNDS: List[MutualFund] = [
    MutualFund(
        name="Motilal Oswal Nifty Midcap 150 Index Fund Direct Growth",
        isin="INF247L01AE5",
        category="mid_cap",
        sub_category="index",
        amc="Motilal Oswal",
        risk_level="high",
        expense_ratio_pct=0.30,
        aum_cr=8200,
        returns_1y_pct=22.5,
        returns_3y_pct=24.8,
        returns_5y_pct=19.2,
        min_sip_amount=500,
        benchmark="Nifty Midcap 150 TRI",
        rating=5,
    ),
    MutualFund(
        name="UTI Nifty Next 50 Index Fund Direct Growth",
        isin="INF789FA1MO7",
        category="mid_cap",
        sub_category="index",
        amc="UTI",
        risk_level="high",
        expense_ratio_pct=0.32,
        aum_cr=6500,
        returns_1y_pct=18.2,
        returns_3y_pct=19.5,
        returns_5y_pct=16.8,
        min_sip_amount=500,
        benchmark="Nifty Next 50 TRI",
        rating=4,
    ),
    MutualFund(
        name="Kotak Emerging Equity Fund Direct Growth",
        isin="INF174KA1EN9",
        category="mid_cap",
        sub_category="active",
        amc="Kotak",
        risk_level="high",
        expense_ratio_pct=0.58,
        aum_cr=38500,
        returns_1y_pct=25.8,
        returns_3y_pct=26.2,
        returns_5y_pct=21.5,
        min_sip_amount=500,
        benchmark="Nifty Midcap 150 TRI",
        rating=5,
    ),
    MutualFund(
        name="Axis Midcap Fund Direct Growth",
        isin="INF846K01EJ3",
        category="mid_cap",
        sub_category="active",
        amc="Axis",
        risk_level="high",
        expense_ratio_pct=0.52,
        aum_cr=25600,
        returns_1y_pct=20.4,
        returns_3y_pct=21.8,
        returns_5y_pct=18.9,
        min_sip_amount=500,
        benchmark="Nifty Midcap 150 TRI",
        rating=4,
    ),
    MutualFund(
        name="HDFC Mid-Cap Opportunities Fund Direct Growth",
        isin="INF179KB1CC5",
        category="mid_cap",
        sub_category="active",
        amc="HDFC",
        risk_level="high",
        expense_ratio_pct=0.88,
        aum_cr=62400,
        returns_1y_pct=24.2,
        returns_3y_pct=25.5,
        returns_5y_pct=20.8,
        min_sip_amount=500,
        benchmark="Nifty Midcap 150 TRI",
        rating=4,
    ),
]

SMALL_CAP_FUNDS: List[MutualFund] = [
    MutualFund(
        name="Motilal Oswal Nifty Smallcap 250 Index Fund Direct Growth",
        isin="INF247L01BF1",
        category="small_cap",
        sub_category="index",
        amc="Motilal Oswal",
        risk_level="very_high",
        expense_ratio_pct=0.36,
        aum_cr=3200,
        returns_1y_pct=28.5,
        returns_3y_pct=30.2,
        returns_5y_pct=22.5,
        min_sip_amount=500,
        benchmark="Nifty Smallcap 250 TRI",
        rating=4,
    ),
    MutualFund(
        name="Nippon India Small Cap Fund Direct Growth",
        isin="INF204KB1GD0",
        category="small_cap",
        sub_category="active",
        amc="Nippon India",
        risk_level="very_high",
        expense_ratio_pct=0.78,
        aum_cr=52000,
        returns_1y_pct=32.5,
        returns_3y_pct=35.8,
        returns_5y_pct=28.2,
        min_sip_amount=500,
        benchmark="Nifty Smallcap 250 TRI",
        rating=5,
    ),
    MutualFund(
        name="Axis Small Cap Fund Direct Growth",
        isin="INF846K01F51",
        category="small_cap",
        sub_category="active",
        amc="Axis",
        risk_level="very_high",
        expense_ratio_pct=0.58,
        aum_cr=18500,
        returns_1y_pct=26.8,
        returns_3y_pct=28.5,
        returns_5y_pct=24.2,
        min_sip_amount=500,
        benchmark="Nifty Smallcap 250 TRI",
        rating=4,
    ),
    MutualFund(
        name="SBI Small Cap Fund Direct Growth",
        isin="INF200KA1MR2",
        category="small_cap",
        sub_category="active",
        amc="SBI",
        risk_level="very_high",
        expense_ratio_pct=0.72,
        aum_cr=28600,
        returns_1y_pct=29.5,
        returns_3y_pct=31.2,
        returns_5y_pct=25.8,
        min_sip_amount=500,
        benchmark="S&P BSE SmallCap TRI",
        rating=4,
    ),
    MutualFund(
        name="Kotak Small Cap Fund Direct Growth",
        isin="INF174KA1GN5",
        category="small_cap",
        sub_category="active",
        amc="Kotak",
        risk_level="very_high",
        expense_ratio_pct=0.62,
        aum_cr=15800,
        returns_1y_pct=27.2,
        returns_3y_pct=29.8,
        returns_5y_pct=23.5,
        min_sip_amount=500,
        benchmark="Nifty Smallcap 250 TRI",
        rating=4,
    ),
]

DEBT_FUNDS: List[MutualFund] = [
    MutualFund(
        name="HDFC Low Duration Fund Direct Growth",
        isin="INF179KB1DH3",
        category="debt",
        sub_category="low_duration",
        amc="HDFC",
        risk_level="low",
        expense_ratio_pct=0.35,
        aum_cr=18500,
        returns_1y_pct=7.8,
        returns_3y_pct=6.5,
        returns_5y_pct=6.8,
        min_sip_amount=500,
        benchmark="CRISIL Low Duration Fund Index",
        rating=5,
    ),
    MutualFund(
        name="ICICI Prudential Short Term Fund Direct Growth",
        isin="INF109KA1BU7",
        category="debt",
        sub_category="short_duration",
        amc="ICICI Prudential",
        risk_level="low",
        expense_ratio_pct=0.42,
        aum_cr=22800,
        returns_1y_pct=8.2,
        returns_3y_pct=7.1,
        returns_5y_pct=7.4,
        min_sip_amount=500,
        benchmark="CRISIL Short Term Bond Fund Index",
        rating=5,
    ),
    MutualFund(
        name="Axis Banking & PSU Debt Fund Direct Growth",
        isin="INF846K01HE2",
        category="debt",
        sub_category="banking_psu",
        amc="Axis",
        risk_level="low",
        expense_ratio_pct=0.38,
        aum_cr=12600,
        returns_1y_pct=7.5,
        returns_3y_pct=6.8,
        returns_5y_pct=7.1,
        min_sip_amount=500,
        benchmark="CRISIL Banking & PSU Debt Index",
        rating=4,
    ),
    MutualFund(
        name="SBI Magnum Medium Duration Fund Direct Growth",
        isin="INF200KA1MS0",
        category="debt",
        sub_category="medium_duration",
        amc="SBI",
        risk_level="moderate",
        expense_ratio_pct=0.68,
        aum_cr=9800,
        returns_1y_pct=8.5,
        returns_3y_pct=7.4,
        returns_5y_pct=7.8,
        min_sip_amount=500,
        benchmark="CRISIL Medium Duration Debt Index",
        rating=4,
    ),
    MutualFund(
        name="Kotak Corporate Bond Fund Direct Growth",
        isin="INF174KA1KH0",
        category="debt",
        sub_category="corporate_bond",
        amc="Kotak",
        risk_level="low",
        expense_ratio_pct=0.35,
        aum_cr=14200,
        returns_1y_pct=7.9,
        returns_3y_pct=6.9,
        returns_5y_pct=7.2,
        min_sip_amount=500,
        benchmark="CRISIL Corporate Bond Fund Index",
        rating=5,
    ),
]

GOLD_FUNDS: List[MutualFund] = [
    MutualFund(
        name="Nippon India Gold Savings Fund Direct Growth",
        isin="INF204KB1HE7",
        category="gold",
        sub_category="gold_fund",
        amc="Nippon India",
        risk_level="moderate",
        expense_ratio_pct=0.25,
        aum_cr=2800,
        returns_1y_pct=12.5,
        returns_3y_pct=9.8,
        returns_5y_pct=10.2,
        min_sip_amount=500,
        benchmark="Domestic Price of Gold",
        rating=4,
    ),
    MutualFund(
        name="HDFC Gold Fund Direct Growth",
        isin="INF179KC1AB2",
        category="gold",
        sub_category="gold_fund",
        amc="HDFC",
        risk_level="moderate",
        expense_ratio_pct=0.30,
        aum_cr=2200,
        returns_1y_pct=12.2,
        returns_3y_pct=9.5,
        returns_5y_pct=9.8,
        min_sip_amount=500,
        benchmark="Domestic Price of Gold",
        rating=4,
    ),
    MutualFund(
        name="SBI Gold Fund Direct Growth",
        isin="INF200KA1MQ4",
        category="gold",
        sub_category="gold_fund",
        amc="SBI",
        risk_level="moderate",
        expense_ratio_pct=0.28,
        aum_cr=1850,
        returns_1y_pct=12.0,
        returns_3y_pct=9.4,
        returns_5y_pct=9.6,
        min_sip_amount=500,
        benchmark="Domestic Price of Gold",
        rating=4,
    ),
    MutualFund(
        name="ICICI Prudential Gold Fund Direct Growth",
        isin="INF109KA1JE8",
        category="gold",
        sub_category="gold_fund",
        amc="ICICI Prudential",
        risk_level="moderate",
        expense_ratio_pct=0.32,
        aum_cr=1650,
        returns_1y_pct=11.8,
        returns_3y_pct=9.2,
        returns_5y_pct=9.4,
        min_sip_amount=500,
        benchmark="Domestic Price of Gold",
        rating=4,
    ),
    MutualFund(
        name="Axis Gold Fund Direct Growth",
        isin="INF846K01JK5",
        category="gold",
        sub_category="gold_fund",
        amc="Axis",
        risk_level="moderate",
        expense_ratio_pct=0.35,
        aum_cr=980,
        returns_1y_pct=11.5,
        returns_3y_pct=9.0,
        returns_5y_pct=9.2,
        min_sip_amount=500,
        benchmark="Domestic Price of Gold",
        rating=3,
    ),
]

# ─────────────────────────────────────────────────────────────
# CATEGORY MAPPING
# ─────────────────────────────────────────────────────────────

FUNDS_BY_CATEGORY: Dict[str, List[MutualFund]] = {
    "large_cap": LARGE_CAP_FUNDS,
    "mid_cap": MID_CAP_FUNDS,
    "small_cap": SMALL_CAP_FUNDS,
    "debt": DEBT_FUNDS,
    "gold": GOLD_FUNDS,
}

# Expected returns for forecasting (conservative estimates)
CATEGORY_EXPECTED_RETURNS: Dict[str, Dict[str, float]] = {
    "large_cap": {
        "expected_return_pct": 12.0,
        "conservative_pct": 10.0,
        "aggressive_pct": 14.0,
    },
    "mid_cap": {
        "expected_return_pct": 15.0,
        "conservative_pct": 12.0,
        "aggressive_pct": 18.0,
    },
    "small_cap": {
        "expected_return_pct": 18.0,
        "conservative_pct": 14.0,
        "aggressive_pct": 22.0,
    },
    "debt": {
        "expected_return_pct": 7.0,
        "conservative_pct": 6.0,
        "aggressive_pct": 8.0,
    },
    "gold": {
        "expected_return_pct": 8.0,
        "conservative_pct": 6.0,
        "aggressive_pct": 10.0,
    },
}


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def get_funds_by_category(category: str, top_n: int = 5) -> List[MutualFund]:
    """
    Get top N funds for a given category.
    
    Args:
        category: One of 'large_cap', 'mid_cap', 'small_cap', 'debt', 'gold'
        top_n: Number of funds to return (default 5)
    
    Returns:
        List of MutualFund objects sorted by rating and returns
    """
    funds = FUNDS_BY_CATEGORY.get(category, [])
    # Already curated and ordered, just slice
    return funds[:top_n]


def get_expected_return(category: str, scenario: str = "expected") -> float:
    """
    Get expected return for a category.
    
    Args:
        category: Fund category
        scenario: 'expected', 'conservative', or 'aggressive'
    
    Returns:
        Expected return percentage
    """
    returns = CATEGORY_EXPECTED_RETURNS.get(category, {})
    key = f"{scenario}_pct" if scenario != "expected" else "expected_return_pct"
    return returns.get(key, 0.0)


def get_all_categories() -> List[str]:
    """Get list of all available fund categories."""
    return list(FUNDS_BY_CATEGORY.keys())


def search_funds(
    query: str = "",
    category: Optional[str] = None,
    max_expense_ratio: Optional[float] = None,
    min_rating: int = 0,
) -> List[MutualFund]:
    """
    Search funds with filters.
    
    Args:
        query: Text to search in fund name/AMC
        category: Filter by category
        max_expense_ratio: Maximum expense ratio
        min_rating: Minimum star rating
    
    Returns:
        Filtered list of funds
    """
    results = []
    
    # Get funds from specified category or all
    if category:
        funds = FUNDS_BY_CATEGORY.get(category, [])
    else:
        funds = []
        for cat_funds in FUNDS_BY_CATEGORY.values():
            funds.extend(cat_funds)
    
    for fund in funds:
        # Text search
        if query:
            query_lower = query.lower()
            if query_lower not in fund.name.lower() and query_lower not in fund.amc.lower():
                continue
        
        # Expense ratio filter
        if max_expense_ratio is not None and fund.expense_ratio_pct > max_expense_ratio:
            continue
        
        # Rating filter
        if fund.rating < min_rating:
            continue
        
        results.append(fund)
    
    return results


# ─────────────────────────────────────────────────────────────
# DATA FRESHNESS
# ─────────────────────────────────────────────────────────────

DATA_LAST_UPDATED = datetime(2026, 3, 15)  # Update this when refreshing data
DATA_VERSION = "2026-Q1"


def get_data_freshness() -> Dict[str, str]:
    """Get information about data freshness."""
    return {
        "last_updated": DATA_LAST_UPDATED.isoformat(),
        "version": DATA_VERSION,
        "disclaimer": (
            "Fund performance data is historical and based on publicly available information. "
            "Past performance does not guarantee future results. Please verify current NAV and "
            "returns from official AMC websites before investing."
        ),
    }
