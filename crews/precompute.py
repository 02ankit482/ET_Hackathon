# crews/precompute.py
# ─────────────────────────────────────────────────────────────
# Pre-computation module for financial metrics.
# All deterministic calculations run HERE in Python, not via LLM.
# This reduces token usage by ~20-30% by eliminating tool calls.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import FINANCIAL_CONSTANTS as FC
from tools.mutual_fund_data import (
    get_funds_by_category,
    get_data_freshness,
    CATEGORY_EXPECTED_RETURNS,
    MutualFund,
)


@dataclass
class PrecomputedMetrics:
    """All deterministic financial metrics pre-computed in Python."""
    
    # Basic financial snapshot
    monthly_income: float
    monthly_expenses: float
    total_emi: float
    monthly_surplus: float
    savings_rate_pct: float
    savings_assessment: str
    
    # Debt analysis
    dti_pct: float
    dti_assessment: str
    
    # Emergency fund
    emergency_fund_target: float
    emergency_fund_existing: float
    emergency_fund_gap: float
    emergency_fund_adequate: bool
    
    # Net worth
    net_worth: float
    asset_breakdown: Dict[str, float]
    
    # Asset allocation (age-based)
    equity_pct: float
    debt_pct: float
    gold_pct: float
    allocation_rationale: str
    
    # Retirement corpus
    years_to_retire: int
    target_monthly_draw_today: float
    target_monthly_draw_at_retirement: float
    corpus_needed: float
    
    # SIP required
    monthly_sip_required: float
    total_to_invest: float
    expected_wealth_gain: float
    
    # Insurance gaps
    term_insurance_recommended: float
    term_insurance_existing: float
    term_insurance_gap: float
    term_insurance_adequate: bool
    health_insurance_recommended: float
    health_insurance_existing: float
    health_insurance_gap: float
    health_insurance_adequate: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_compact_json(self, max_chars: int = 2000) -> str:
        """Return compact JSON string for prompt injection."""
        data = self.to_dict()
        raw = json.dumps(data, indent=2)
        if len(raw) <= max_chars:
            return raw
        # Compact format without indentation
        return json.dumps(data, separators=(',', ':'))


def compute_metrics(profile_data: Dict[str, Any]) -> PrecomputedMetrics:
    """
    Compute all deterministic financial metrics from user profile.
    
    This replaces the need for Agent 1 (Data Analyst) to call calculation tools,
    saving 5-6 tool calls worth of tokens per request.
    
    Args:
        profile_data: User's financial profile dict
        
    Returns:
        PrecomputedMetrics with all calculated values
    """
    # Extract base values
    annual_income = profile_data.get("annual_income", 0)
    monthly_income = annual_income / 12
    monthly_expenses = profile_data.get("monthly_expenses", 0)
    
    home_loan_emi = profile_data.get("home_loan_emi", 0)
    car_loan_emi = profile_data.get("car_loan_emi", 0)
    other_emi = profile_data.get("other_emi", 0)
    total_emi = home_loan_emi + car_loan_emi + other_emi
    
    # ── Monthly Surplus ───────────────────────────────────────
    monthly_surplus = max(0, monthly_income - monthly_expenses - total_emi)
    savings_rate_pct = (monthly_surplus / monthly_income * 100) if monthly_income > 0 else 0
    savings_assessment = (
        "Excellent (>40%)" if savings_rate_pct > 40 else
        "Good (25-40%)" if savings_rate_pct > 25 else
        "Fair (10-25%)" if savings_rate_pct > 10 else
        "Low (<10%)"
    )
    
    # ── Debt-to-Income Ratio ──────────────────────────────────
    dti_pct = (total_emi / monthly_income * 100) if monthly_income > 0 else 0
    dti_assessment = (
        "Healthy (<30%)" if dti_pct < 30 else
        "Moderate (30-40%)" if dti_pct < 40 else
        "High (40-50%)" if dti_pct < 50 else
        "Critical (>50%)"
    )
    
    # ── Emergency Fund ────────────────────────────────────────
    existing_savings = profile_data.get("existing_savings", 0)
    emergency_months = 6
    emergency_fund_target = monthly_expenses * emergency_months
    emergency_fund_gap = max(0, emergency_fund_target - existing_savings)
    emergency_fund_adequate = emergency_fund_gap == 0
    
    # ── Net Worth ─────────────────────────────────────────────
    existing_mf = profile_data.get("existing_mf", 0)
    existing_ppf = profile_data.get("existing_ppf", 0)
    existing_epf = profile_data.get("existing_epf", 0)
    existing_fd = profile_data.get("existing_fd", 0)
    existing_nps = profile_data.get("existing_nps", 0)
    
    asset_breakdown = {
        "mutual_funds": existing_mf,
        "ppf": existing_ppf,
        "epf": existing_epf,
        "fixed_deposits": existing_fd,
        "nps": existing_nps,
        "savings": existing_savings,
    }
    net_worth = sum(asset_breakdown.values())
    
    # ── Asset Allocation (Age-Based) ──────────────────────────
    age = profile_data.get("age", 30)
    risk_appetite = profile_data.get("risk_appetite", "moderate").lower()
    
    base_equity = 100 - age
    if risk_appetite == "aggressive":
        equity_pct = min(90, base_equity + 15)
    elif risk_appetite == "conservative":
        equity_pct = max(10, base_equity - 20)
    else:
        equity_pct = max(20, base_equity)
    
    remaining = 100 - equity_pct
    gold_pct = min(15, remaining // 3)
    debt_pct = remaining - gold_pct
    
    allocation_rationale = f"Base equity = 100 - {age} = {100-age}%, adjusted for {risk_appetite} risk"
    
    # ── Retirement Corpus ─────────────────────────────────────
    target_retirement_age = profile_data.get("target_retirement_age", 60)
    years_to_retire = max(1, target_retirement_age - age)  # At least 1 year
    target_monthly_draw_today = profile_data.get("target_monthly_draw", 100000)
    
    inflation_rate = FC.get("inflation_rate_pct", 6.5) / 100
    swr_rate = FC.get("safe_withdrawal_rate_pct", 4.0) / 100
    
    # Future monthly draw (inflation-adjusted)
    target_monthly_draw_at_retirement = target_monthly_draw_today * ((1 + inflation_rate) ** years_to_retire)
    annual_draw_at_retirement = target_monthly_draw_at_retirement * 12
    corpus_needed = annual_draw_at_retirement / swr_rate
    
    # ── SIP Required ──────────────────────────────────────────
    investment_horizon = profile_data.get("investment_horizon_years", years_to_retire)
    expected_return_pct = FC.get("avg_equity_return_pct", 12.0)
    
    r = expected_return_pct / 100 / 12  # Monthly rate
    n = investment_horizon * 12  # Total months
    
    if r == 0:
        monthly_sip_required = corpus_needed / n
    else:
        monthly_sip_required = corpus_needed * r / (((1 + r) ** n) - 1)
    
    total_to_invest = monthly_sip_required * n
    expected_wealth_gain = corpus_needed - total_to_invest
    
    # ── Insurance Gaps ────────────────────────────────────────
    # Term insurance (10x income rule)
    term_multiplier = FC.get("life_insurance_multiplier", 10)
    term_insurance_recommended = annual_income * term_multiplier
    term_insurance_existing = profile_data.get("term_cover_amount", 0)
    term_insurance_gap = max(0, term_insurance_recommended - term_insurance_existing)
    term_insurance_adequate = term_insurance_gap == 0
    
    # Health insurance
    is_metro = profile_data.get("is_metro_city", True)
    health_insurance_recommended = (
        FC.get("health_insurance_min_metro", 1000000) if is_metro 
        else FC.get("health_insurance_min_nonmetro", 500000)
    )
    health_insurance_existing = profile_data.get("health_cover_amount", 0)
    health_insurance_gap = max(0, health_insurance_recommended - health_insurance_existing)
    health_insurance_adequate = health_insurance_gap == 0
    
    return PrecomputedMetrics(
        # Basic snapshot
        monthly_income=round(monthly_income, 2),
        monthly_expenses=monthly_expenses,
        total_emi=total_emi,
        monthly_surplus=round(monthly_surplus, 2),
        savings_rate_pct=round(savings_rate_pct, 1),
        savings_assessment=savings_assessment,
        
        # Debt
        dti_pct=round(dti_pct, 1),
        dti_assessment=dti_assessment,
        
        # Emergency fund
        emergency_fund_target=round(emergency_fund_target, 2),
        emergency_fund_existing=existing_savings,
        emergency_fund_gap=round(emergency_fund_gap, 2),
        emergency_fund_adequate=emergency_fund_adequate,
        
        # Net worth
        net_worth=round(net_worth, 2),
        asset_breakdown=asset_breakdown,
        
        # Asset allocation
        equity_pct=equity_pct,
        debt_pct=debt_pct,
        gold_pct=gold_pct,
        allocation_rationale=allocation_rationale,
        
        # Retirement
        years_to_retire=years_to_retire,
        target_monthly_draw_today=target_monthly_draw_today,
        target_monthly_draw_at_retirement=round(target_monthly_draw_at_retirement, 2),
        corpus_needed=round(corpus_needed, 2),
        
        # SIP
        monthly_sip_required=round(monthly_sip_required, 2),
        total_to_invest=round(total_to_invest, 2),
        expected_wealth_gain=round(expected_wealth_gain, 2),
        
        # Insurance
        term_insurance_recommended=round(term_insurance_recommended, 2),
        term_insurance_existing=term_insurance_existing,
        term_insurance_gap=round(term_insurance_gap, 2),
        term_insurance_adequate=term_insurance_adequate,
        health_insurance_recommended=health_insurance_recommended,
        health_insurance_existing=health_insurance_existing,
        health_insurance_gap=round(health_insurance_gap, 2),
        health_insurance_adequate=health_insurance_adequate,
    )


def compute_tax_comparison(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute tax comparison between Old and New regime for FY 2025-26.
    
    This is deterministic and doesn't need LLM reasoning.
    """
    income = profile_data.get("annual_income", 0)
    
    # Get deduction inputs
    epf_contribution = profile_data.get("epf_contribution", 0)
    ppf_contribution = min(profile_data.get("existing_ppf", 0), 150000)
    elss_investment = profile_data.get("elss_investment", 0)
    nps_contribution = min(profile_data.get("existing_nps", 0), 50000)
    employer_nps = profile_data.get("employer_nps", 0)
    lic_premium = profile_data.get("lic_premium", 0)
    health_insurance_self = 25000 if profile_data.get("has_health_insurance") else 0
    health_insurance_parents = profile_data.get("health_insurance_parents", 0)
    parents_are_senior = profile_data.get("parents_are_senior", False)
    home_loan_interest = profile_data.get("home_loan_interest_annually", 0)
    hra_received = profile_data.get("annual_hra_received", 0)
    rent_paid = profile_data.get("annual_rent_paid", 0)
    is_metro = profile_data.get("is_metro_city", True)
    other_80c = profile_data.get("other_80c", 0)
    
    # ══════════════════════════════════════════════════════
    # OLD REGIME CALCULATION
    # ══════════════════════════════════════════════════════
    old_deductions = {}
    
    # Standard deduction
    old_std = FC["old_regime_standard_deduction"]
    old_deductions["standard_deduction"] = old_std
    
    # Section 80C (capped at ₹1.5L)
    total_80c = min(
        FC["section_80c_limit"],
        epf_contribution + ppf_contribution + elss_investment + lic_premium + other_80c
    )
    old_deductions["80C"] = total_80c
    
    # Section 80CCD(1B) — NPS additional (capped ₹50K)
    nps_1b = min(FC["section_80ccd_1b_limit"], nps_contribution)
    old_deductions["80CCD(1B)"] = nps_1b
    
    # Section 80CCD(2) — Employer NPS
    employer_nps_limit = income * FC["section_80ccd_2_limit_pct"] / 100
    employer_nps_deduction = min(employer_nps_limit, employer_nps)
    old_deductions["80CCD(2)_employer"] = employer_nps_deduction
    
    # Section 80D — Health insurance
    health_self = min(FC["section_80d_self_limit"], health_insurance_self)
    parent_limit = (
        FC["section_80d_parents_senior_limit"] if parents_are_senior
        else FC["section_80d_parents_limit"]
    )
    health_parents = min(parent_limit, health_insurance_parents)
    old_deductions["80D_self"] = health_self
    old_deductions["80D_parents"] = health_parents
    
    # Section 24 — Home loan interest
    sec_24 = min(FC["section_24_home_loan_limit"], home_loan_interest)
    old_deductions["section_24_home_loan"] = sec_24
    
    # HRA exemption
    hra_exempt = 0
    if hra_received > 0 and rent_paid > 0:
        basic = income * 0.4  # Approximate basic as 40% of CTC
        metro_pct = FC["hra_exemption_metro_pct"] if is_metro else FC["hra_exemption_nonmetro_pct"]
        hra_exempt = min(
            hra_received,
            basic * metro_pct / 100,
            max(0, rent_paid - 0.10 * basic)
        )
    old_deductions["HRA_exemption"] = hra_exempt
    
    total_old_deductions = sum(old_deductions.values())
    old_taxable = max(0, income - total_old_deductions)
    
    # Calculate old regime tax
    old_tax = _compute_tax_on_slabs(old_taxable, FC["tax_slabs_old_regime_fy2526"])
    
    # Section 87A rebate
    if old_taxable <= FC["old_regime_87a_income_limit"]:
        old_tax = max(0, old_tax - FC["old_regime_87a_rebate_limit"])
    
    old_tax_with_cess = old_tax * 1.04  # 4% cess
    
    # ══════════════════════════════════════════════════════
    # NEW REGIME CALCULATION
    # ══════════════════════════════════════════════════════
    new_deductions = {}
    
    # Standard deduction (₹75K in new regime)
    new_std = FC["new_regime_standard_deduction"]
    new_deductions["standard_deduction"] = new_std
    
    # Only 80CCD(2) employer NPS is allowed
    new_deductions["80CCD(2)_employer"] = employer_nps_deduction
    
    total_new_deductions = sum(new_deductions.values())
    new_taxable = max(0, income - total_new_deductions)
    
    # Calculate new regime tax
    new_tax = _compute_tax_on_slabs(new_taxable, FC["tax_slabs_new_regime_fy2526"])
    
    # Section 87A rebate
    if new_taxable <= FC["new_regime_87a_income_limit"]:
        new_tax = max(0, new_tax - FC["new_regime_87a_rebate_limit"])
    
    new_tax_with_cess = new_tax * 1.04  # 4% cess
    
    # ══════════════════════════════════════════════════════
    # COMPARISON
    # ══════════════════════════════════════════════════════
    savings = abs(old_tax_with_cess - new_tax_with_cess)
    recommended = "old" if old_tax_with_cess < new_tax_with_cess else "new"
    
    # Deductions wasted in new regime
    wasted = {k: v for k, v in old_deductions.items()
              if k not in new_deductions and v > 0}
    
    if recommended == "old":
        explanation = (
            f"Old Regime saves ₹{savings:,.0f} because total deductions "
            f"(₹{total_old_deductions:,.0f}) significantly reduce taxable income."
        )
    else:
        explanation = (
            f"New Regime saves ₹{savings:,.0f} because lower slab rates "
            f"outweigh available deductions (₹{total_old_deductions:,.0f})."
        )
    
    return {
        "gross_income": income,
        "old_regime_tax": round(old_tax_with_cess, 2),
        "new_regime_tax": round(new_tax_with_cess, 2),
        "recommended_regime": recommended,
        "savings_amount": round(savings, 2),
        "deductions_utilized": {k: v for k, v in old_deductions.items() if v > 0},
        "deductions_wasted_in_new": wasted,
        "explanation": explanation,
    }


def _compute_tax_on_slabs(taxable: float, slabs: list) -> float:
    """Compute tax using progressive slab structure."""
    tax = 0
    prev_limit = 0
    for slab in slabs:
        upper = slab["upto"] if slab["upto"] is not None else float("inf")
        rate = slab["rate_pct"] / 100
        if taxable <= prev_limit:
            break
        bracket = min(taxable, upper) - prev_limit
        if bracket > 0:
            tax += bracket * rate
        prev_limit = upper
    return tax


# ─────────────────────────────────────────────────────────────
# FUND DATA CACHING
# ─────────────────────────────────────────────────────────────

_CACHED_FUNDS: Optional[Dict[str, list]] = None


def get_cached_fund_recommendations(top_n: int = 5) -> Dict[str, Any]:
    """
    Get all fund recommendations from cache.
    
    This is called ONCE at the start of planning, not by each agent.
    Saves ~2 tool calls worth of tokens.
    """
    global _CACHED_FUNDS
    
    if _CACHED_FUNDS is None:
        _CACHED_FUNDS = {}
        for category in ["large_cap", "mid_cap", "small_cap", "debt", "gold"]:
            funds = get_funds_by_category(category, top_n)
            _CACHED_FUNDS[category] = [
                {
                    "name": f.name,
                    "isin": f.isin,
                    "category": f.category,
                    "amc": f.amc,
                    "risk_level": f.risk_level,
                    "expense_ratio_pct": f.expense_ratio_pct,
                    "returns_1y_pct": f.returns_1y_pct,
                    "returns_3y_pct": f.returns_3y_pct,
                    "returns_5y_pct": f.returns_5y_pct,
                    "expected_return_pct": CATEGORY_EXPECTED_RETURNS.get(
                        category, {}
                    ).get("expected_return_pct", 10.0),
                    "min_sip_amount": f.min_sip_amount,
                    "rating": f.rating,
                }
                for f in funds
            ]
    
    return {
        **_CACHED_FUNDS,
        "data_freshness": get_data_freshness(),
    }


def format_metrics_for_prompt(metrics: PrecomputedMetrics) -> str:
    """
    Format pre-computed metrics as a concise summary for agent prompts.
    
    This is much smaller than having agents call tools individually.
    """
    return f"""
PRE-COMPUTED FINANCIAL METRICS (verified calculations):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monthly Income: ₹{metrics.monthly_income:,.0f}
Monthly Expenses: ₹{metrics.monthly_expenses:,.0f}
Total EMI: ₹{metrics.total_emi:,.0f}
Monthly Surplus: ₹{metrics.monthly_surplus:,.0f} ({metrics.savings_rate_pct}% - {metrics.savings_assessment})

Debt-to-Income Ratio: {metrics.dti_pct}% ({metrics.dti_assessment})

Emergency Fund: Target ₹{metrics.emergency_fund_target:,.0f}, Gap ₹{metrics.emergency_fund_gap:,.0f}
  Status: {"✅ Adequate" if metrics.emergency_fund_adequate else "⚠️ Needs attention"}

Net Worth: ₹{metrics.net_worth:,.0f}

Asset Allocation (Age-Based):
  Equity: {metrics.equity_pct}%, Debt: {metrics.debt_pct}%, Gold: {metrics.gold_pct}%
  Rationale: {metrics.allocation_rationale}

Retirement Planning:
  Years to Retire: {metrics.years_to_retire}
  Target Monthly Draw (Today): ₹{metrics.target_monthly_draw_today:,.0f}
  Target at Retirement (Inflation-Adjusted): ₹{metrics.target_monthly_draw_at_retirement:,.0f}
  Corpus Needed: ₹{metrics.corpus_needed:,.0f}
  Monthly SIP Required: ₹{metrics.monthly_sip_required:,.0f}

Insurance Gaps:
  Term: Recommended ₹{metrics.term_insurance_recommended:,.0f}, Gap ₹{metrics.term_insurance_gap:,.0f}
  Health: Recommended ₹{metrics.health_insurance_recommended:,.0f}, Gap ₹{metrics.health_insurance_gap:,.0f}
"""


def format_tax_for_prompt(tax_comparison: Dict[str, Any]) -> str:
    """Format tax comparison as a concise summary for agent prompts."""
    return f"""
TAX COMPARISON (FY 2025-26):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gross Income: ₹{tax_comparison['gross_income']:,.0f}
Old Regime Tax: ₹{tax_comparison['old_regime_tax']:,.0f}
New Regime Tax: ₹{tax_comparison['new_regime_tax']:,.0f}
Recommended: {tax_comparison['recommended_regime'].upper()} REGIME
Savings: ₹{tax_comparison['savings_amount']:,.0f}
{tax_comparison['explanation']}
"""
