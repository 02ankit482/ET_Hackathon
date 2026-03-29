# tools/financial_calculator.py
# ─────────────────────────────────────────────────────────────
# Deterministic financial calculation tool for CrewAI agents.
# All math runs HERE, not in the LLM.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import math
from typing import Type, Dict, Any
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FINANCIAL_CONSTANTS as FC


# Simplified input schemas - one for each calculation type
# LLMs work better with flat, explicit parameters than nested dicts

class MonthlySurplusInput(BaseModel):
    """Input for monthly surplus calculation."""
    monthly_income: float = Field(description="Monthly income in INR (annual_income / 12)")
    monthly_expenses: float = Field(description="Monthly expenses in INR")
    emi_total: float = Field(default=0, description="Total EMI (home_loan_emi + car_loan_emi + other_emi)")


class DebtToIncomeInput(BaseModel):
    """Input for debt-to-income ratio calculation."""
    total_emi: float = Field(description="Total monthly EMI payments")
    monthly_income: float = Field(description="Monthly income in INR")


class EmergencyFundInput(BaseModel):
    """Input for emergency fund gap calculation."""
    monthly_expenses: float = Field(description="Monthly expenses in INR")
    existing_savings: float = Field(default=0, description="Current savings/emergency fund")
    months: int = Field(default=6, description="Target months of expenses (default 6)")


class NetWorthInput(BaseModel):
    """Input for net worth calculation."""
    existing_mf: float = Field(default=0, description="Mutual fund value")
    existing_ppf: float = Field(default=0, description="PPF balance")
    existing_epf: float = Field(default=0, description="EPF balance")
    existing_fd: float = Field(default=0, description="Fixed deposit value")
    existing_nps: float = Field(default=0, description="NPS balance")
    existing_savings: float = Field(default=0, description="Savings account balance")


class AssetAllocationInput(BaseModel):
    """Input for asset allocation recommendation."""
    age: int = Field(description="User's age in years")
    risk_appetite: str = Field(default="moderate", description="Risk appetite: conservative, moderate, or aggressive")


class RetirementCorpusInput(BaseModel):
    """Input for retirement corpus calculation."""
    monthly_draw_today: float = Field(description="Desired monthly income at retirement in today's value")
    years_to_retire: int = Field(description="Years until retirement")
    inflation_pct: float = Field(default=6.5, description="Expected inflation rate")
    swr_pct: float = Field(default=4.0, description="Safe withdrawal rate")


class SIPRequiredInput(BaseModel):
    """Input for SIP required calculation."""
    target_amount: float = Field(description="Target corpus amount")
    rate_pct: float = Field(default=12, description="Expected annual return rate")
    years: int = Field(description="Investment horizon in years")


class InsuranceGapInput(BaseModel):
    """Input for insurance gap calculation."""
    annual_income: float = Field(description="Annual income in INR")
    existing_cover: float = Field(default=0, description="Existing term insurance cover")
    multiplier: int = Field(default=10, description="Income multiplier for coverage (default 10x)")


# ═══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL TOOL CLASSES - Simpler for LLMs to use
# ═══════════════════════════════════════════════════════════════════════════════

class MonthlySurplusTool(BaseTool):
    name: str = "calculate_monthly_surplus"
    description: str = "Calculates investable surplus after expenses and EMIs. Returns surplus amount and savings rate."
    args_schema: Type[BaseModel] = MonthlySurplusInput

    def _run(self, monthly_income: float, monthly_expenses: float, emi_total: float = 0) -> str:
        surplus = max(0, monthly_income - monthly_expenses - emi_total)
        savings_rate = (surplus / monthly_income * 100) if monthly_income > 0 else 0
        assessment = (
            "Excellent (>40%)" if savings_rate > 40 else
            "Good (25-40%)" if savings_rate > 25 else
            "Fair (10-25%)" if savings_rate > 10 else
            "Low (<10%)"
        )
        return json.dumps({
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "emi_total": emi_total,
            "monthly_surplus": round(surplus, 2),
            "savings_rate_pct": round(savings_rate, 1),
            "assessment": assessment,
        }, indent=2)


class DebtToIncomeTool(BaseTool):
    name: str = "calculate_debt_to_income"
    description: str = "Calculates debt-to-income ratio. Returns DTI percentage and risk assessment."
    args_schema: Type[BaseModel] = DebtToIncomeInput

    def _run(self, total_emi: float, monthly_income: float) -> str:
        dti = (total_emi / monthly_income * 100) if monthly_income > 0 else 0
        assessment = (
            "Healthy (<30%)" if dti < 30 else
            "Moderate (30-40%)" if dti < 40 else
            "High (40-50%)" if dti < 50 else
            "Critical (>50%)"
        )
        return json.dumps({
            "total_emi": total_emi,
            "monthly_income": monthly_income,
            "dti_pct": round(dti, 1),
            "assessment": assessment,
        }, indent=2)


class EmergencyFundTool(BaseTool):
    name: str = "calculate_emergency_fund"
    description: str = "Calculates emergency fund gap. Returns target amount and gap to fill."
    args_schema: Type[BaseModel] = EmergencyFundInput

    def _run(self, monthly_expenses: float, existing_savings: float = 0, months: int = 6) -> str:
        target = monthly_expenses * months
        gap = max(0, target - existing_savings)
        return json.dumps({
            "monthly_expenses": monthly_expenses,
            "months": months,
            "target": round(target, 2),
            "existing_savings": existing_savings,
            "gap": round(gap, 2),
            "adequate": gap == 0,
        }, indent=2)


class NetWorthTool(BaseTool):
    name: str = "calculate_net_worth"
    description: str = "Calculates total net worth from assets. Pass each asset value separately."
    args_schema: Type[BaseModel] = NetWorthInput

    def _run(self, existing_mf: float = 0, existing_ppf: float = 0, existing_epf: float = 0,
             existing_fd: float = 0, existing_nps: float = 0, existing_savings: float = 0) -> str:
        assets = {
            "mutual_funds": existing_mf,
            "ppf": existing_ppf,
            "epf": existing_epf,
            "fixed_deposits": existing_fd,
            "nps": existing_nps,
            "savings": existing_savings,
        }
        total = sum(assets.values())
        return json.dumps({
            "asset_breakdown": assets,
            "total_assets": round(total, 2),
            "net_worth": round(total, 2),
        }, indent=2)


class AssetAllocationTool(BaseTool):
    name: str = "calculate_asset_allocation"
    description: str = "Recommends equity/debt/gold allocation based on age and risk appetite."
    args_schema: Type[BaseModel] = AssetAllocationInput

    def _run(self, age: int, risk_appetite: str = "moderate") -> str:
        risk = risk_appetite.lower()
        base_equity = 100 - age
        
        if risk == "aggressive":
            equity = min(90, base_equity + 15)
        elif risk == "conservative":
            equity = max(10, base_equity - 20)
        else:
            equity = max(20, base_equity)
        
        remaining = 100 - equity
        gold = min(15, remaining // 3)
        debt = remaining - gold
        
        return json.dumps({
            "age": age,
            "risk_appetite": risk,
            "equity_pct": equity,
            "debt_pct": debt,
            "gold_pct": gold,
            "rationale": f"Base equity = 100 - {age} = {100-age}%, adjusted for {risk} risk",
        }, indent=2)


class RetirementCorpusTool(BaseTool):
    name: str = "calculate_retirement_corpus"
    description: str = "Calculates required retirement corpus based on desired monthly income."
    args_schema: Type[BaseModel] = RetirementCorpusInput

    def _run(self, monthly_draw_today: float, years_to_retire: int, 
             inflation_pct: float = 6.5, swr_pct: float = 4.0) -> str:
        inflation_rate = inflation_pct / 100
        swr_rate = swr_pct / 100
        
        monthly_draw_future = monthly_draw_today * ((1 + inflation_rate) ** years_to_retire)
        annual_draw_future = monthly_draw_future * 12
        corpus_needed = annual_draw_future / swr_rate
        
        return json.dumps({
            "monthly_draw_today": monthly_draw_today,
            "years_to_retire": years_to_retire,
            "inflation_pct": inflation_pct,
            "swr_pct": swr_pct,
            "monthly_draw_at_retirement": round(monthly_draw_future, 2),
            "corpus_needed": round(corpus_needed, 2),
        }, indent=2)


class SIPRequiredTool(BaseTool):
    name: str = "calculate_sip_required"
    description: str = "Calculates monthly SIP needed to reach target corpus."
    args_schema: Type[BaseModel] = SIPRequiredInput

    def _run(self, target_amount: float, rate_pct: float = 12, years: int = 10) -> str:
        r = rate_pct / 100 / 12
        n = years * 12
        
        if r == 0:
            sip = target_amount / n
        else:
            sip = target_amount * r / (((1 + r) ** n) - 1)
        
        total_invested = sip * n
        wealth_gain = target_amount - total_invested
        
        return json.dumps({
            "target_amount": target_amount,
            "rate_pct": rate_pct,
            "years": years,
            "monthly_sip": round(sip, 2),
            "total_invested": round(total_invested, 2),
            "wealth_gain": round(wealth_gain, 2),
        }, indent=2)


class InsuranceGapTool(BaseTool):
    name: str = "calculate_insurance_gap"
    description: str = "Calculates term insurance gap based on income multiplier."
    args_schema: Type[BaseModel] = InsuranceGapInput

    def _run(self, annual_income: float, existing_cover: float = 0, multiplier: int = 10) -> str:
        ideal = annual_income * multiplier
        gap = max(0, ideal - existing_cover)
        return json.dumps({
            "annual_income": annual_income,
            "multiplier": multiplier,
            "ideal_cover": round(ideal, 2),
            "existing_cover": existing_cover,
            "gap": round(gap, 2),
            "adequate": gap == 0,
        }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY COMBINED TOOL - Keep for backward compatibility but prefer individual tools
# ═══════════════════════════════════════════════════════════════════════════════

class FinancialCalcInput(BaseModel):
    """Legacy input schema for combined calculator."""
    calculation: str = Field(description="Calculation type")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters dict")


class FinancialCalculatorTool(BaseTool):
    name: str = "financial_calculator"
    description: str = """Performs deterministic financial calculations. Never estimate — always use this tool.

IMPORTANT: You MUST extract values from the user profile and pass them in the 'params' dict.
The params dict CANNOT be empty — you must include all required values.

Available calculations and their required params (with example values):

1. monthly_surplus: 
   params: {"monthly_income": 75000, "monthly_expenses": 30000, "emi_total": 10000}
   → From profile: monthly_income = annual_income/12, monthly_expenses, emi_total = home_loan_emi + car_loan_emi + other_emi

2. debt_to_income: 
   params: {"total_emi": 10000, "monthly_income": 75000}
   → From profile: total_emi = home_loan_emi + car_loan_emi + other_emi, monthly_income = annual_income/12

3. emergency_fund: 
   params: {"monthly_expenses": 30000, "existing_savings": 200000, "months": 6}
   → From profile: monthly_expenses, existing_savings

4. net_worth: 
   params: {"assets": {"mf": 100000, "ppf": 100000, "fd": 100000}, "liabilities": {"home_loan": 0}}
   → From profile: existing_mf, existing_ppf, existing_epf, existing_fd, existing_nps, existing_savings

5. asset_allocation: 
   params: {"age": 30, "risk_appetite": "moderate"}
   → From profile: age, risk_appetite

6. future_value: 
   params: {"present_value": 100000, "rate_pct": 12, "years": 10}

7. sip_required: 
   params: {"target_amount": 10000000, "rate_pct": 12, "years": 20}

8. retirement_corpus: 
   params: {"monthly_draw_today": 100000, "years_to_retire": 30, "inflation_pct": 6, "swr_pct": 4}
   → From profile: target_monthly_draw, target_retirement_age - age

9. insurance_gap: 
   params: {"annual_income": 900000, "existing_cover": 0, "multiplier": 10}
   → From profile: annual_income, term_cover_amount

10. education_cost: 
    params: {"current_cost": 2000000, "years": 15, "inflation_pct": 10}

11. glidepath: 
    params: {"current_equity_pct": 70, "target_equity_pct": 40, "years": 20, "interval_months": 12}
"""
    args_schema: Type[BaseModel] = FinancialCalcInput

    def _run(self, calculation: str, params: dict) -> str:
        try:
            if isinstance(params, str):
                params = json.loads(params)

            calc_map = {
                "future_value": self._future_value,
                "sip_required": self._sip_required,
                "retirement_corpus": self._retirement_corpus,
                "insurance_gap": self._insurance_gap,
                "emergency_fund": self._emergency_fund,
                "asset_allocation": self._asset_allocation,
                "glidepath": self._glidepath,
                "education_cost": self._education_cost,
                "monthly_surplus": self._monthly_surplus,
                "debt_to_income": self._debt_to_income,
                "net_worth": self._net_worth,
            }

            if calculation not in calc_map:
                return json.dumps({"error": f"Unknown calculation: {calculation}. Available: {list(calc_map.keys())}"})

            result = calc_map[calculation](params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _future_value(self, p: dict) -> dict:
        """FV = PV × (1 + r)^n"""
        pv = float(p["present_value"])
        r = float(p["rate_pct"]) / 100
        n = float(p["years"])
        fv = pv * (1 + r) ** n
        return {
            "calculation": "future_value",
            "present_value": pv,
            "rate_pct": p["rate_pct"],
            "years": n,
            "future_value": round(fv, 2),
            "formula": f"{pv:,.0f} × (1 + {r:.4f})^{n:.0f} = {fv:,.0f}",
        }

    def _sip_required(self, p: dict) -> dict:
        """Monthly SIP = FV × r / ((1+r)^n - 1), where r = monthly rate"""
        target = float(p["target_amount"])
        annual_rate = float(p["rate_pct"]) / 100
        years = float(p["years"])
        r = annual_rate / 12
        n = years * 12
        if r == 0:
            sip = target / n
        else:
            sip = target * r / ((1 + r) ** n - 1)
        return {
            "calculation": "sip_required",
            "target_amount": target,
            "annual_rate_pct": p["rate_pct"],
            "years": years,
            "monthly_sip": round(sip, 2),
            "total_invested": round(sip * n, 2),
            "wealth_gain": round(target - sip * n, 2),
        }

    def _retirement_corpus(self, p: dict) -> dict:
        """Corpus = (Monthly draw × 12 / SWR), inflation-adjusted to retirement year"""
        monthly_draw_today = float(p["monthly_draw_today"])
        years = float(p["years_to_retire"])
        inflation = float(p.get("inflation_pct", FC["inflation_rate_pct"])) / 100
        swr = float(p.get("swr_pct", FC["safe_withdrawal_rate_pct"])) / 100

        # Future monthly draw (inflation-adjusted)
        future_monthly = monthly_draw_today * (1 + inflation) ** years
        future_annual = future_monthly * 12
        corpus = future_annual / swr

        return {
            "calculation": "retirement_corpus",
            "monthly_draw_today": monthly_draw_today,
            "years_to_retire": years,
            "inflation_pct": inflation * 100,
            "swr_pct": swr * 100,
            "future_monthly_draw": round(future_monthly, 2),
            "future_annual_draw": round(future_annual, 2),
            "required_corpus": round(corpus, 2),
        }

    def _insurance_gap(self, p: dict) -> dict:
        """Gap = (multiplier × annual_income) - existing_cover"""
        income = float(p["annual_income"])
        existing = float(p.get("existing_cover", 0))
        mult = float(p.get("multiplier", FC["life_insurance_multiplier"]))

        recommended = income * mult
        gap = max(0, recommended - existing)
        return {
            "calculation": "insurance_gap",
            "annual_income": income,
            "multiplier": mult,
            "recommended_cover": round(recommended, 2),
            "existing_cover": existing,
            "gap": round(gap, 2),
            "adequate": gap == 0,
        }

    def _emergency_fund(self, p: dict) -> dict:
        """Gap = (months × monthly_expenses) - existing_savings"""
        expenses = float(p["monthly_expenses"])
        savings = float(p.get("existing_savings", 0))
        months = int(p.get("months", FC["emergency_fund_months"]))

        target = expenses * months
        gap = max(0, target - savings)
        return {
            "calculation": "emergency_fund",
            "monthly_expenses": expenses,
            "months": months,
            "target": round(target, 2),
            "existing_savings": savings,
            "gap": round(gap, 2),
            "adequate": gap == 0,
        }

    def _asset_allocation(self, p: dict) -> dict:
        """Age-based allocation adjusted for risk appetite."""
        age = int(p["age"])
        risk = p.get("risk_appetite", "moderate").lower()

        # Base equity = 100 - age
        base_equity = 100 - age

        if risk == "aggressive":
            equity = min(90, base_equity + 15)
        elif risk == "conservative":
            equity = max(10, base_equity - 20)
        else:
            equity = max(20, base_equity)

        # Split debt and gold
        remaining = 100 - equity
        gold = min(15, remaining // 3)  # Max 15% gold
        debt = remaining - gold

        return {
            "calculation": "asset_allocation",
            "age": age,
            "risk_appetite": risk,
            "equity_pct": equity,
            "debt_pct": debt,
            "gold_pct": gold,
            "rationale": f"Base equity = 100 - {age} = {100-age}%, adjusted for {risk} risk",
        }

    def _glidepath(self, p: dict) -> dict:
        """Generate equity% reduction schedule over investment horizon."""
        current_eq = float(p["current_equity_pct"])
        target_eq = float(p["target_equity_pct"])
        years = float(p["years"])
        interval = int(p.get("interval_months", 12))  # default annual

        total_months = int(years * 12)
        steps = total_months // interval
        if steps <= 0:
            steps = 1

        reduction_per_step = (current_eq - target_eq) / steps

        schedule = []
        for i in range(steps + 1):
            month_offset = i * interval
            eq = round(current_eq - (reduction_per_step * i), 1)
            schedule.append({
                "month_offset": month_offset,
                "equity_pct": max(target_eq, eq),
                "debt_pct": round(100 - max(target_eq, eq), 1),
            })

        return {
            "calculation": "glidepath",
            "current_equity_pct": current_eq,
            "target_equity_pct": target_eq,
            "years": years,
            "interval_months": interval,
            "schedule": schedule,
        }

    def _education_cost(self, p: dict) -> dict:
        """Project education cost with education-specific inflation (typically 10%)."""
        current_cost = float(p["current_cost"])
        years = float(p["years"])
        inflation = float(p.get("inflation_pct", FC["education_inflation_pct"])) / 100

        future_cost = current_cost * (1 + inflation) ** years
        return {
            "calculation": "education_cost",
            "current_cost": current_cost,
            "years": years,
            "inflation_pct": inflation * 100,
            "projected_cost": round(future_cost, 2),
            "formula": f"{current_cost:,.0f} × (1 + {inflation:.2f})^{years:.0f} = {future_cost:,.0f}",
        }

    def _monthly_surplus(self, p: dict) -> dict:
        """Investable surplus after expenses and EMIs."""
        income = float(p["monthly_income"])
        expenses = float(p["monthly_expenses"])
        emi = float(p.get("emi_total", 0))

        surplus = max(0, income - expenses - emi)
        savings_rate = (surplus / income * 100) if income > 0 else 0
        return {
            "calculation": "monthly_surplus",
            "monthly_income": income,
            "monthly_expenses": expenses,
            "emi_total": emi,
            "monthly_surplus": round(surplus, 2),
            "savings_rate_pct": round(savings_rate, 1),
            "assessment": (
                "Excellent (>40%)" if savings_rate > 40 else
                "Good (25-40%)" if savings_rate > 25 else
                "Fair (10-25%)" if savings_rate > 10 else
                "Low (<10%) — reduce expenses or increase income"
            ),
        }

    def _debt_to_income(self, p: dict) -> dict:
        """DTI ratio assessment."""
        emi = float(p["total_emi"])
        income = float(p["monthly_income"])

        dti = (emi / income * 100) if income > 0 else 0
        return {
            "calculation": "debt_to_income",
            "total_emi": emi,
            "monthly_income": income,
            "dti_pct": round(dti, 1),
            "assessment": (
                "Healthy (<30%)" if dti < 30 else
                "Concerning (30-50%)" if dti < 50 else
                "Dangerous (>50%) — prioritise debt repayment"
            ),
        }

    def _net_worth(self, p: dict) -> dict:
        """Net worth = total assets - total liabilities."""
        assets = p.get("assets", {})
        liabilities = p.get("liabilities", {})

        total_assets = sum(float(v) for v in assets.values())
        total_liabilities = sum(float(v) for v in liabilities.values())
        net = total_assets - total_liabilities

        return {
            "calculation": "net_worth",
            "total_assets": round(total_assets, 2),
            "asset_breakdown": assets,
            "total_liabilities": round(total_liabilities, 2),
            "liability_breakdown": liabilities,
            "net_worth": round(net, 2),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MUTUAL FUND RECOMMENDER TOOL
# ═══════════════════════════════════════════════════════════════════════════════

class MutualFundRecommenderInput(BaseModel):
    """Input for mutual fund recommendations."""
    category: str = Field(
        description="Fund category: large_cap, mid_cap, small_cap, debt, gold"
    )
    top_n: int = Field(
        default=5,
        description="Number of fund recommendations to return (default 5)"
    )


class MutualFundRecommenderTool(BaseTool):
    name: str = "recommend_mutual_funds"
    description: str = """Returns top mutual fund recommendations for a given category.
    
Available categories:
- large_cap: Nifty 50 / large-cap equity funds (moderate risk)
- mid_cap: Nifty Midcap 150 / mid-cap funds (high risk)
- small_cap: Nifty Smallcap 250 / small-cap funds (very high risk)
- debt: Debt/bond funds (low risk)
- gold: Gold funds (moderate risk)

Returns top 5 funds with: name, ISIN, AMC, risk level, expense ratio, 
1Y/3Y/5Y returns, expected returns for planning.

NOTE: These are EDUCATIONAL recommendations. Users should verify current 
performance from official AMC websites before investing."""
    args_schema: Type[BaseModel] = MutualFundRecommenderInput

    def _run(self, category: str, top_n: int = 5) -> str:
        try:
            from tools.mutual_fund_data import (
                get_funds_by_category,
                get_expected_return,
                get_data_freshness,
            )
            
            funds = get_funds_by_category(category, top_n)
            if not funds:
                return json.dumps({
                    "error": f"Unknown category: {category}",
                    "available_categories": ["large_cap", "mid_cap", "small_cap", "debt", "gold"]
                })
            
            expected_return = get_expected_return(category, "expected")
            freshness = get_data_freshness()
            
            fund_list = []
            for f in funds:
                fund_list.append({
                    "name": f.name,
                    "isin": f.isin,
                    "category": f.category,
                    "sub_category": f.sub_category,
                    "amc": f.amc,
                    "risk_level": f.risk_level,
                    "expense_ratio_pct": f.expense_ratio_pct,
                    "aum_cr": f.aum_cr,
                    "returns_1y_pct": f.returns_1y_pct,
                    "returns_3y_pct": f.returns_3y_pct,
                    "returns_5y_pct": f.returns_5y_pct,
                    "expected_return_pct": expected_return,
                    "min_sip_amount": f.min_sip_amount,
                    "rating": f.rating,
                })
            
            return json.dumps({
                "category": category,
                "fund_count": len(fund_list),
                "expected_return_pct": expected_return,
                "funds": fund_list,
                "data_freshness": freshness,
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})


class AllFundRecommendationsInput(BaseModel):
    """Input for getting all fund recommendations at once."""
    pass


class AllFundRecommendationsTool(BaseTool):
    name: str = "get_all_fund_recommendations"
    description: str = """Returns top 5 mutual fund recommendations for ALL categories at once.
    
Returns funds for: large_cap, mid_cap, small_cap, debt, gold

Use this tool to get fund options for the month-by-month plan.
Each category includes: name, ISIN, AMC, risk level, expense ratio, returns, etc."""
    args_schema: Type[BaseModel] = AllFundRecommendationsInput

    def _run(self) -> str:
        try:
            from tools.mutual_fund_data import (
                get_funds_by_category,
                get_expected_return,
                get_data_freshness,
                get_all_categories,
            )
            
            result = {}
            for category in get_all_categories():
                funds = get_funds_by_category(category, 5)
                expected_return = get_expected_return(category, "expected")
                
                fund_list = []
                for f in funds:
                    fund_list.append({
                        "name": f.name,
                        "isin": f.isin,
                        "category": f.category,
                        "amc": f.amc,
                        "risk_level": f.risk_level,
                        "expense_ratio_pct": f.expense_ratio_pct,
                        "returns_1y_pct": f.returns_1y_pct,
                        "returns_3y_pct": f.returns_3y_pct,
                        "returns_5y_pct": f.returns_5y_pct,
                        "expected_return_pct": expected_return,
                        "min_sip_amount": f.min_sip_amount,
                        "rating": f.rating,
                    })
                
                result[category] = {
                    "expected_return_pct": expected_return,
                    "funds": fund_list,
                }
            
            result["data_freshness"] = get_data_freshness()
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
