# models.py
# ─────────────────────────────────────────────────────────────
# Pydantic models for structured CrewAI outputs and API
# request/response schemas.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from typing import Optional, Dict
from pydantic import BaseModel, Field


# ── Monthly Plan Entry ────────────────────────────────────────

class MonthlyPlanEntry(BaseModel):
    """One month's allocation in the financial plan."""
    month: str = Field(description="Month in YYYY-MM format, e.g. '2026-04'")
    sip_large_cap: float = Field(default=0, description="SIP in large-cap equity category (₹)")
    sip_mid_cap: float = Field(default=0, description="SIP in mid-cap equity category (₹)")
    sip_small_cap: float = Field(default=0, description="SIP in small-cap equity category (₹)")
    sip_debt: float = Field(default=0, description="SIP in debt fund category (₹)")
    sip_gold: float = Field(default=0, description="SIP in gold/gold fund category (₹)")
    ppf_contribution: float = Field(default=0, description="PPF monthly contribution (₹)")
    nps_contribution: float = Field(default=0, description="NPS monthly contribution (₹)")
    emergency_fund_contribution: float = Field(default=0, description="Towards emergency fund (₹)")
    equity_pct: float = Field(description="Target equity allocation % for this month (glidepath)")
    debt_pct: float = Field(description="Target debt allocation % for this month")
    notes: str = Field(default="", description="Any special notes for this month")
    
    class Config:
        extra = "forbid"


# ── Tax Comparison ────────────────────────────────────────────

class TaxComparison(BaseModel):
    """Side-by-side old vs new regime tax analysis."""
    old_regime_tax: float = Field(description="Total tax payable under old regime (₹)")
    new_regime_tax: float = Field(description="Total tax payable under new regime (₹)")
    recommended_regime: str = Field(description="'old' or 'new' — whichever saves more")
    savings_amount: float = Field(description="₹ saved by choosing recommended regime")
    deductions_utilized: Dict[str, float] = Field(
        default_factory=dict,
        description="Deductions used in old regime: {'80C': 150000, '80CCD': 50000, ...}"
    )
    deductions_wasted_in_new: Dict[str, float] = Field(
        default_factory=dict,
        description="Deductions you lose by choosing new regime"
    )
    explanation: str = Field(description="Why this regime is better for this user")
    
    class Config:
        extra = "forbid"


# ── Insurance Gap ─────────────────────────────────────────────

class InsuranceGap(BaseModel):
    """Insurance coverage gap analysis."""
    has_term: bool = Field(description="Whether user has term life insurance")
    recommended_term_cover: float = Field(description="Recommended term cover (₹)")
    current_term_cover: float = Field(default=0, description="Current term cover (₹)")
    term_gap: float = Field(description="Term insurance gap (₹)")

    has_health: bool = Field(description="Whether user has health insurance")
    recommended_health_cover: float = Field(description="Recommended health cover (₹)")
    current_health_cover: float = Field(default=0, description="Current health cover (₹)")
    health_gap: float = Field(description="Health insurance gap (₹)")

    recommendations: list[str] = Field(
        default_factory=list,
        description="Specific insurance action items"
    )
    
    class Config:
        extra = "forbid"


# ── Portfolio Overlap ─────────────────────────────────────────

class OverlapPair(BaseModel):
    """A pair of schemes with overlap."""
    fund_1: str = Field(description="First fund name")
    fund_2: str = Field(description="Second fund name")
    overlap_pct: float = Field(description="Overlap percentage between these two funds")
    common_stocks: list[str] = Field(
        default_factory=list,
        description="List of common stocks between the two funds"
    )
    
    class Config:
        extra = "forbid"  # Ensures additionalProperties: false


class PortfolioOverlap(BaseModel):
    """Portfolio overlap analysis from CAS data."""
    overlap_score: float = Field(description="Overall overlap score 0-100%")
    overlapping_stocks: list[str] = Field(
        default_factory=list,
        description="Top stocks appearing across multiple schemes"
    )
    schemes_with_overlap: list[OverlapPair] = Field(
        default_factory=list,
        description="Pairs of schemes with significant overlap"
    )
    consolidation_advice: str = Field(
        description="Advice on reducing overlap, e.g. 'Reduce from 8 to 4 schemes'"
    )
    
    class Config:
        extra = "forbid"  # Ensures additionalProperties: false


# ── Full Financial Plan ──────────────────────────────────────

class FinancialPlan(BaseModel):
    """Complete financial plan output from the Planning Crew."""
    summary: str = Field(description="Executive summary of the plan")
    target_corpus: float = Field(description="Target corpus needed (₹)")
    estimated_retirement_date: str = Field(description="Estimated date/year of goal achievement")
    monthly_sip_total: float = Field(description="Total monthly SIP recommended (₹)")

    monthly_plan: list[MonthlyPlanEntry] = Field(
        default_factory=list,
        description="Month-by-month allocation plan (first 24 months minimum)"
    )

    tax_comparison: TaxComparison = Field(description="Old vs New regime analysis")
    insurance_gap: InsuranceGap = Field(description="Insurance coverage gaps")
    portfolio_overlap: Optional[PortfolioOverlap] = Field(
        default=None,
        description="Portfolio overlap analysis (only if CAS data available)"
    )

    asset_allocation_current: Dict[str, float] = Field(
        default_factory=dict,
        description="Current asset allocation: {'equity': 60, 'debt': 30, 'gold': 10}"
    )
    asset_allocation_target: Dict[str, float] = Field(
        default_factory=dict,
        description="Target asset allocation based on age and risk"
    )

    key_recommendations: list[str] = Field(
        default_factory=list,
        description="Prioritized action items with 'why' explanations"
    )
    educational_notes: list[str] = Field(
        default_factory=list,
        description="Financial literacy explanations (the 'why' behind each recommendation)"
    )

    assumptions: Dict[str, float] = Field(
        default_factory=dict,
        description="Assumptions used: inflation, returns, SWR, etc."
    )
    confidence_notes: list[str] = Field(
        default_factory=list,
        description="Limitations and caveats of this plan"
    )
    scenario_type: str = Field(
        default="creative",
        description="'FIRE' | 'child_education' | 'home_purchase' | 'custom'"
    )

    disclaimer: str = Field(description="Mandatory SEBI disclaimer text")
    
    class Config:
        extra = "forbid"


# ── Chat Response ─────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Response from the Chat Crew."""
    reply: str = Field(description="The advisor's reply to the user")
    needs_replan: bool = Field(
        default=False,
        description="True if the chat implies a profile change requiring plan regeneration"
    )
    profile_updates: Dict[str, float] = Field(
        default_factory=dict,
        description="Profile fields that changed, e.g. {'target_retirement_age': 55}"
    )


# ── API Request/Response Schemas ──────────────────────────────

class OnboardingRequest(BaseModel):
    """Request body for creating a new advisor session."""
    clerk_user_id: str
    name: str
    age: int
    city: str = "India"
    dependents: int = 0

    annual_income: float
    monthly_expenses: float
    home_loan_emi: float = 0
    car_loan_emi: float = 0
    other_emi: float = 0

    existing_mf: float = 0
    existing_ppf: float = 0
    existing_nps: float = 0
    existing_epf: float = 0
    existing_fd: float = 0
    existing_savings: float = 0
    current_sip: float = 0

    primary_goal: str = "FIRE"
    target_retirement_age: int = 60
    target_monthly_draw: float = 0
    risk_appetite: str = "moderate"
    investment_horizon_years: int = 10

    has_term_insurance: bool = False
    term_cover_amount: float = 0
    has_health_insurance: bool = False
    health_cover_amount: float = 0

    # HRA / home loan for tax comparison
    annual_hra_received: float = 0
    annual_rent_paid: float = 0
    is_metro_city: bool = True
    home_loan_interest_annually: float = 0

    # Data source fields from frontend
    asset_tab: Optional[str] = None  # "setu" | "cas" | "manual"
    setu_data: Optional[list] = None  # Raw Setu account aggregator response
    cas_data: Optional[dict] = None   # Parsed CAS PDF data


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    user_id: str
    message: str


class InitUserRequest(BaseModel):
    """Request body for initializing user from Clerk."""
    clerk_user_id: str
    email: str = ""
    first_name: str = ""
    last_name: str = ""
