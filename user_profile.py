# user_profile.py
# ─────────────────────────────────────────────────────────────
# User financial profile — stored in session memory so every
# query is automatically personalised without the user repeating
# themselves.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from pathlib import Path


@dataclass
class UserProfile:
    # Demographics
    name:               str   = "User"
    age:                int   = 30
    city:               str   = "India"

    # Financials
    monthly_income_inr: float = 0.0
    monthly_expense_inr: float = 0.0
    existing_savings_inr: float = 0.0
    existing_investments_inr: float = 0.0
    emi_obligations_inr: float = 0.0

    # Profile
    risk_appetite:      str   = "moderate"      # conservative | moderate | aggressive
    experience_level:   str   = "beginner"      # beginner | intermediate | advanced
    investment_horizon_years: int = 10

    # Goals (free text, e.g. ["Retirement in 25 years", "Child education in 10 years"])
    goals: List[str] = field(default_factory=list)

    # Insurance
    has_term_insurance: bool  = False
    has_health_insurance: bool = False

    # Derived (auto-computed)
    @property
    def monthly_surplus_inr(self) -> float:
        return max(0, self.monthly_income_inr - self.monthly_expense_inr - self.emi_obligations_inr)

    @property
    def emergency_fund_target_inr(self) -> float:
        return self.monthly_expense_inr * 6

    @property
    def emergency_fund_gap_inr(self) -> float:
        return max(0, self.emergency_fund_target_inr - self.existing_savings_inr)

    @property
    def recommended_equity_pct(self) -> int:
        base = 100 - self.age
        if self.risk_appetite == "aggressive":
            return min(90, base + 10)
        if self.risk_appetite == "conservative":
            return max(10, base - 20)
        return max(20, base)

    @property
    def recommended_debt_pct(self) -> int:
        return 100 - self.recommended_equity_pct

    def to_prompt_str(self) -> str:
        """Human-readable summary injected into the system prompt."""
        return f"""
Name: {self.name} | Age: {self.age} | City: {self.city}
Monthly Income:     ₹{self.monthly_income_inr:,.0f}
Monthly Expenses:   ₹{self.monthly_expense_inr:,.0f}
EMI Obligations:    ₹{self.emi_obligations_inr:,.0f}
Monthly Surplus:    ₹{self.monthly_surplus_inr:,.0f}
Existing Savings:   ₹{self.existing_savings_inr:,.0f}
Existing Investments: ₹{self.existing_investments_inr:,.0f}
Risk Appetite:      {self.risk_appetite.title()}
Experience Level:   {self.experience_level.title()}
Horizon:            {self.investment_horizon_years} years
Goals:              {', '.join(self.goals) or 'Not specified'}
Term Insurance:     {'Yes' if self.has_term_insurance else 'No ⚠️'}
Health Insurance:   {'Yes' if self.has_health_insurance else 'No ⚠️'}
Emergency Fund Gap: ₹{self.emergency_fund_gap_inr:,.0f}
Suggested Allocation: {self.recommended_equity_pct}% Equity / {self.recommended_debt_pct}% Debt
""".strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["monthly_surplus_inr"]      = self.monthly_surplus_inr
        d["emergency_fund_target_inr"] = self.emergency_fund_target_inr
        d["emergency_fund_gap_inr"]   = self.emergency_fund_gap_inr
        d["recommended_equity_pct"]   = self.recommended_equity_pct
        d["recommended_debt_pct"]     = self.recommended_debt_pct
        return d

    def save(self, path: str = "user_profile.json"):
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str = "user_profile.json") -> "UserProfile":
        if not Path(path).exists():
            return cls()
        data = json.loads(Path(path).read_text())
        data.pop("monthly_surplus_inr", None)     # remove computed fields
        data.pop("emergency_fund_target_inr", None)
        data.pop("emergency_fund_gap_inr", None)
        data.pop("recommended_equity_pct", None)
        data.pop("recommended_debt_pct", None)
        return cls(**data)


# ── Interactive Profile Builder ───────────────────────────────

def build_profile_interactively() -> UserProfile:
    """CLI wizard to build a UserProfile from user input."""
    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    console.print(Panel(
        "[bold cyan]Finance RAG — User Profile Setup[/bold cyan]\n"
        "Press Enter to keep defaults shown in [dim](brackets)[/dim].",
        expand=False,
    ))

    def ask(prompt: str, default, cast=str):
        val = console.input(f"  {prompt} [dim]({default})[/dim]: ").strip()
        if not val:
            return default
        try:
            return cast(val)
        except Exception:
            console.print(f"    [red]Invalid input, using default: {default}[/red]")
            return default

    p = UserProfile()
    p.name               = ask("Your name",                  "User")
    p.age                = ask("Your age",                   30,   int)
    p.city               = ask("Your city",                  "India")
    p.monthly_income_inr = ask("Monthly income (₹)",         50000, float)
    p.monthly_expense_inr = ask("Monthly expenses (₹)",      30000, float)
    p.emi_obligations_inr = ask("EMI / loan obligations (₹)", 0,   float)
    p.existing_savings_inr = ask("Existing savings (₹)",     0,    float)
    p.existing_investments_inr = ask("Existing investments (₹)", 0, float)

    risk = ask("Risk appetite (conservative/moderate/aggressive)", "moderate")
    p.risk_appetite = risk if risk in ("conservative","moderate","aggressive") else "moderate"

    exp = ask("Experience (beginner/intermediate/advanced)", "beginner")
    p.experience_level = exp if exp in ("beginner","intermediate","advanced") else "beginner"

    p.investment_horizon_years = ask("Investment horizon (years)", 10, int)

    goals_raw = ask("Your top financial goals (comma-separated)", "Retirement")
    p.goals = [g.strip() for g in goals_raw.split(",") if g.strip()]

    p.has_term_insurance   = ask("Do you have term insurance? (y/n)", "n").lower() == "y"
    p.has_health_insurance = ask("Do you have health insurance? (y/n)", "n").lower() == "y"

    console.print("\n[bold green]Profile saved![/bold green]")
    console.print(p.to_prompt_str())
    return p
