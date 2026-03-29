# tools/tax_calculator.py
# ─────────────────────────────────────────────────────────────
# Tax calculation tool: compares Old vs New regime (FY 2025-26).
# Deterministic — all computations are exact, not LLM-estimated.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from typing import Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import FINANCIAL_CONSTANTS as FC


class TaxCalcInput(BaseModel):
    """Input for tax calculation."""
    annual_income: float = Field(description="Gross annual income (₹)")
    epf_contribution: float = Field(default=0, description="Annual EPF employee contribution (₹)")
    ppf_contribution: float = Field(default=0, description="Annual PPF contribution (₹)")
    elss_investment: float = Field(default=0, description="Annual ELSS investment (₹)")
    nps_contribution: float = Field(default=0, description="Annual NPS contribution under 80CCD(1B) (₹)")
    employer_nps: float = Field(default=0, description="Annual employer NPS contribution under 80CCD(2) (₹)")
    lic_premium: float = Field(default=0, description="Annual LIC/life insurance premium (₹)")
    health_insurance_self: float = Field(default=0, description="Health insurance premium (self + family) (₹)")
    health_insurance_parents: float = Field(default=0, description="Health insurance premium (parents) (₹)")
    parents_are_senior: bool = Field(default=False, description="Whether parents are senior citizens (60+)")
    home_loan_interest: float = Field(default=0, description="Annual home loan interest paid (₹)")
    hra_received: float = Field(default=0, description="Annual HRA received from employer (₹)")
    rent_paid: float = Field(default=0, description="Annual rent paid (₹)")
    is_metro: bool = Field(default=True, description="Whether city is a metro (Delhi/Mumbai/Kolkata/Chennai)")
    other_80c: float = Field(default=0, description="Other 80C investments (tuition, home loan principal) (₹)")


class TaxCalculatorTool(BaseTool):
    name: str = "tax_calculator"
    description: str = """Calculates income tax under BOTH Old and New regimes for FY 2025-26.
Returns a side-by-side comparison with:
- Tax payable under each regime
- Which regime is better and savings amount
- Detailed deduction utilization map
- Specific advice on which deductions matter

Provide: annual_income (mandatory), plus any applicable deductions.
Important: Section 80CCD(2) employer NPS is allowed in BOTH regimes.
Standard deduction: ₹75,000 (new) / ₹50,000 (old)."""
    args_schema: Type[BaseModel] = TaxCalcInput

    def _run(self, **kwargs) -> str:
        try:
            p = TaxCalcInput(**kwargs)
            result = self._compare_regimes(p)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _compute_tax_on_slabs(self, taxable: float, slabs: list) -> float:
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

    def _apply_cess(self, tax: float) -> float:
        """4% Health and Education Cess."""
        return tax * 1.04

    def _hra_exemption(self, p: TaxCalcInput) -> float:
        """Calculate HRA exemption under old regime."""
        if p.hra_received <= 0 or p.rent_paid <= 0:
            return 0

        basic = p.annual_income * 0.4  # Approximate basic as 40% of CTC
        metro_pct = FC["hra_exemption_metro_pct"] if p.is_metro else FC["hra_exemption_nonmetro_pct"]

        # HRA exemption = min of:
        # 1. Actual HRA received
        # 2. 50%/40% of basic (metro/non-metro)
        # 3. Rent paid - 10% of basic
        option1 = p.hra_received
        option2 = basic * metro_pct / 100
        option3 = max(0, p.rent_paid - 0.10 * basic)

        return min(option1, option2, option3)

    def _compare_regimes(self, p: TaxCalcInput) -> dict:
        income = p.annual_income

        # ══════════════════════════════════════════════════════
        # OLD REGIME
        # ══════════════════════════════════════════════════════
        old_deductions = {}

        # Standard deduction
        old_std = FC["old_regime_standard_deduction"]
        old_deductions["standard_deduction"] = old_std

        # Section 80C (capped at ₹1.5L)
        total_80c = min(
            FC["section_80c_limit"],
            p.epf_contribution + p.ppf_contribution + p.elss_investment +
            p.lic_premium + p.other_80c
        )
        old_deductions["80C"] = total_80c

        # Section 80CCD(1B) — NPS additional (capped ₹50K)
        nps_1b = min(FC["section_80ccd_1b_limit"], p.nps_contribution)
        old_deductions["80CCD(1B)"] = nps_1b

        # Section 80CCD(2) — Employer NPS (10% of basic, ~4% of CTC)
        employer_nps_limit = p.annual_income * FC["section_80ccd_2_limit_pct"] / 100
        employer_nps_deduction = min(employer_nps_limit, p.employer_nps)
        old_deductions["80CCD(2)_employer"] = employer_nps_deduction

        # Section 80D — Health insurance
        health_self = min(FC["section_80d_self_limit"], p.health_insurance_self)
        parent_limit = (FC["section_80d_parents_senior_limit"]
                        if p.parents_are_senior
                        else FC["section_80d_parents_limit"])
        health_parents = min(parent_limit, p.health_insurance_parents)
        old_deductions["80D_self"] = health_self
        old_deductions["80D_parents"] = health_parents

        # Section 24 — Home loan interest (max ₹2L)
        sec_24 = min(FC["section_24_home_loan_limit"], p.home_loan_interest)
        old_deductions["section_24_home_loan"] = sec_24

        # HRA exemption
        hra_exempt = self._hra_exemption(p)
        old_deductions["HRA_exemption"] = hra_exempt

        total_old_deductions = sum(old_deductions.values())
        old_taxable = max(0, income - total_old_deductions)

        old_tax = self._compute_tax_on_slabs(
            old_taxable, FC["tax_slabs_old_regime_fy2526"]
        )

        # Section 87A rebate (old regime)
        if old_taxable <= FC["old_regime_87a_income_limit"]:
            old_tax = max(0, old_tax - FC["old_regime_87a_rebate_limit"])

        old_tax_with_cess = self._apply_cess(old_tax)

        # ══════════════════════════════════════════════════════
        # NEW REGIME
        # ══════════════════════════════════════════════════════
        new_deductions = {}

        # Standard deduction (₹75K in new regime)
        new_std = FC["new_regime_standard_deduction"]
        new_deductions["standard_deduction"] = new_std

        # Only 80CCD(2) employer NPS is allowed in new regime
        new_deductions["80CCD(2)_employer"] = employer_nps_deduction

        total_new_deductions = sum(new_deductions.values())
        new_taxable = max(0, income - total_new_deductions)

        new_tax = self._compute_tax_on_slabs(
            new_taxable, FC["tax_slabs_new_regime_fy2526"]
        )

        # Section 87A rebate (new regime — up to ₹60K for income ≤ ₹12L)
        if new_taxable <= FC["new_regime_87a_income_limit"]:
            new_tax = max(0, new_tax - FC["new_regime_87a_rebate_limit"])

        new_tax_with_cess = self._apply_cess(new_tax)

        # ══════════════════════════════════════════════════════
        # COMPARISON
        # ══════════════════════════════════════════════════════
        savings = abs(old_tax_with_cess - new_tax_with_cess)
        recommended = "old" if old_tax_with_cess < new_tax_with_cess else "new"

        # Deductions wasted if choosing new regime
        wasted = {k: v for k, v in old_deductions.items()
                  if k not in new_deductions and v > 0}

        # Build explanation
        if recommended == "old":
            explanation = (
                f"The Old Regime saves ₹{savings:,.0f} because your total deductions "
                f"(₹{total_old_deductions:,.0f}) significantly reduce your taxable income. "
                f"Key deductions: 80C=₹{total_80c:,.0f}, HRA=₹{hra_exempt:,.0f}, "
                f"Home Loan=₹{sec_24:,.0f}."
            )
        else:
            explanation = (
                f"The New Regime saves ₹{savings:,.0f} because its lower slab rates "
                f"outweigh the deductions you can claim (₹{total_old_deductions:,.0f}). "
                f"The crossover typically happens when total deductions are below ~₹3.75L."
            )

        return {
            "calculation": "tax_regime_comparison",
            "financial_year": "FY 2025-26",
            "gross_income": income,

            "old_regime": {
                "deductions": old_deductions,
                "total_deductions": round(total_old_deductions, 2),
                "taxable_income": round(old_taxable, 2),
                "tax_before_cess": round(old_tax, 2),
                "tax_with_cess": round(old_tax_with_cess, 2),
            },

            "new_regime": {
                "deductions": new_deductions,
                "total_deductions": round(total_new_deductions, 2),
                "taxable_income": round(new_taxable, 2),
                "tax_before_cess": round(new_tax, 2),
                "tax_with_cess": round(new_tax_with_cess, 2),
            },

            "comparison": {
                "recommended_regime": recommended,
                "savings": round(savings, 2),
                "deductions_wasted_in_new_regime": wasted,
                "explanation": explanation,
            },
        }
