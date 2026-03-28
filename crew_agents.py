# crew_agents.py
# ─────────────────────────────────────────────────────────────
# CrewAI-powered multi-agent finance system.
# Agents:
#   1. ProfileBuilderAgent  — conversational profile extraction
#   2. FinancialPlannerAgent — timeline / milestone plan
#   3. FinancialAdvisorAgent — RAG-backed actionable advice
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import os
import re
from typing import Optional

from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool

from config import GEMINI_MODEL, FINANCIAL_CONSTANTS
from retriever import HybridRetriever
from user_profile import UserProfile


# ══════════════════════════════════════════════════════════════
# LLM CONFIG
# CrewAI uses LiteLLM — Gemini needs GEMINI_API_KEY env var
# ══════════════════════════════════════════════════════════════

os.environ.setdefault("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
CREW_LLM = f"gemini/{GEMINI_MODEL}"

# Slim financial constants — only the numbers agents actually need
# (avoids dumping the full JSON into every prompt = ~800 token saving)
SLIM_CONSTANTS = {
    "inflation_rate_pct":        FINANCIAL_CONSTANTS["inflation_rate_pct"],
    "avg_equity_return_pct":     FINANCIAL_CONSTANTS["avg_equity_return_pct"],
    "avg_debt_return_pct":       FINANCIAL_CONSTANTS["avg_debt_return_pct"],
    "avg_fd_rate_pct":           FINANCIAL_CONSTANTS["avg_fd_rate_pct"],
    "ppf_annual_limit_inr":      FINANCIAL_CONSTANTS["ppf_annual_limit_inr"],
    "nps_80ccd_1b_limit_inr":    FINANCIAL_CONSTANTS["nps_80ccd_1b_limit_inr"],
    "emergency_fund_months":     FINANCIAL_CONSTANTS["emergency_fund_months"],
    "life_insurance_multiplier": FINANCIAL_CONSTANTS["life_insurance_multiplier"],
    "ltcg_equity_pct":           FINANCIAL_CONSTANTS["ltcg_equity_pct"],
    "epf_employee_rate_pct":     FINANCIAL_CONSTANTS["epf_employee_rate_pct"],
}
SLIM_CONSTANTS_STR = json.dumps(SLIM_CONSTANTS, indent=2)


# ══════════════════════════════════════════════════════════════
# CUSTOM TOOLS
# ══════════════════════════════════════════════════════════════

class RAGRetrievalTool(BaseTool):
    name: str = "rag_retrieval"
    description: str = (
        "Search the finance knowledge base. "
        "Input: a short natural language query (max 20 words). "
        "Returns: relevant document chunks."
    )
    _retriever: Optional[HybridRetriever] = None

    def __init__(self, retriever: HybridRetriever, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_retriever", retriever)

    def _run(self, query: str) -> str:
        retriever = object.__getattribute__(self, "_retriever")
        hits = retriever.retrieve(query)
        # Return only top 3 hits, truncated, to save tokens
        parts = []
        for i, h in enumerate(hits[:3], 1):
            text = h["text"].strip()[:600]
            src  = h["metadata"].get("source_file", "?")
            parts.append(f"[{i}] {src}:\n{text}")
        return "\n\n".join(parts) if parts else "No relevant documents found."


class FinancialConstantsTool(BaseTool):
    name: str = "financial_constants"
    description: str = (
        "Returns key Indian financial constants: returns, limits, rates. "
        "Call this when you need specific numbers for calculations."
    )

    def _run(self, _: str = "") -> str:
        return SLIM_CONSTANTS_STR


# ══════════════════════════════════════════════════════════════
# AGENT DEFINITIONS
# Kept concise — long backstories eat tokens on every LLM call
# ══════════════════════════════════════════════════════════════

def build_profile_builder_agent() -> Agent:
    return Agent(
        role="Financial Profile Specialist",
        goal=(
            "Collect the user's financial profile through friendly conversation. "
            "Ask for: name, age, city, monthly income, expenses, EMI, savings, "
            "investments, risk appetite, experience level, investment horizon, "
            "goals, term insurance, health insurance. "
            "When all fields are collected, output a ```profile_json``` block."
        ),
        backstory=(
            "You are a certified Indian financial planner. "
            "You ask focused, non-judgmental questions and never overwhelm the user. "
            "You ask 2-3 questions at a time maximum."
        ),
        llm=CREW_LLM,
        tools=[],          # No tools needed — pure conversation
        verbose=True,
        allow_delegation=False,
        max_iter=2,        # Low — just converse, don't loop
        max_rpm=5,         # Throttle to avoid token-rate limits
    )


def build_planner_agent() -> Agent:
    return Agent(
        role="Financial Planning Strategist",
        goal=(
            "Create a phase-wise financial plan with specific ₹ targets and timelines "
            "based on the user's profile and query. "
            "Use the financial_constants tool for accurate return rates."
        ),
        backstory=(
            "You are a SEBI-registered advisor. You build phase-wise plans: "
            "emergency fund first, then insurance, then debt, then wealth building. "
            "You always give specific rupee amounts based on the user's real numbers."
        ),
        llm=CREW_LLM,
        tools=[FinancialConstantsTool()],
        verbose=True,
        allow_delegation=False,
        max_iter=2,
        max_rpm=5,
    )


def build_advisor_agent(retriever: HybridRetriever) -> Agent:
    return Agent(
        role="Personal Finance Advisor",
        goal=(
            "Give step-by-step actionable advice on HOW to achieve the financial plan. "
            "Use rag_retrieval to find relevant knowledge. "
            "Cover: what product, where to get it, how to set it up, why it fits the user."
        ),
        backstory=(
            "You are an empathetic Indian finance advisor. "
            "You explain things simply for beginners and go deeper for advanced users. "
            "You never recommend specific stocks or crypto — only asset classes."
        ),
        llm=CREW_LLM,
        tools=[RAGRetrievalTool(retriever=retriever), FinancialConstantsTool()],
        verbose=True,
        allow_delegation=False,
        max_iter=3,
        max_rpm=5,
    )


# ══════════════════════════════════════════════════════════════
# TASK DEFINITIONS
# Short, focused descriptions — long descriptions = token waste
# ══════════════════════════════════════════════════════════════

def build_profile_extraction_task(agent: Agent, conversation_so_far: str) -> Task:
    # Truncate conversation to last 2000 chars to avoid token overflow
    convo = conversation_so_far[-2000:] if len(conversation_so_far) > 2000 else conversation_so_far

    return Task(
        description=(
            f"Conversation so far:\n{convo}\n\n"
            "Identify missing profile fields and ask for them (2-3 questions max). "
            "Required fields: name, age, city, monthly_income_inr, monthly_expense_inr, "
            "emi_obligations_inr, existing_savings_inr, existing_investments_inr, "
            "risk_appetite (conservative/moderate/aggressive), "
            "experience_level (beginner/intermediate/advanced), "
            "investment_horizon_years, goals (list), "
            "has_term_insurance (true/false), has_health_insurance (true/false). "
            "When ALL fields are known, output ONLY:\n"
            "```profile_json\n{...json...}\n```"
        ),
        expected_output=(
            "Either 2-3 friendly questions for missing fields, "
            "OR a complete ```profile_json``` block when all fields are collected."
        ),
        agent=agent,
    )


def build_planning_task(agent: Agent, profile: UserProfile, user_query: str) -> Task:
    # Compact profile string to save tokens
    p = profile
    profile_compact = (
        f"Name:{p.name} Age:{p.age} City:{p.city} "
        f"Income:₹{p.monthly_income_inr:,.0f}/mo Expenses:₹{p.monthly_expense_inr:,.0f}/mo "
        f"EMI:₹{p.emi_obligations_inr:,.0f} Surplus:₹{p.monthly_surplus_inr:,.0f} "
        f"Savings:₹{p.existing_savings_inr:,.0f} Investments:₹{p.existing_investments_inr:,.0f} "
        f"Risk:{p.risk_appetite} Experience:{p.experience_level} "
        f"Horizon:{p.investment_horizon_years}yrs Goals:{', '.join(p.goals)} "
        f"TermIns:{'Yes' if p.has_term_insurance else 'No'} "
        f"HealthIns:{'Yes' if p.has_health_insurance else 'No'} "
        f"EmergencyFundGap:₹{p.emergency_fund_gap_inr:,.0f}"
    )

    return Task(
        description=(
            f"User Profile: {profile_compact}\n\n"
            f"User Query: {user_query}\n\n"
            "Create a financial plan with these sections:\n"
            "1. Goals Summary (each goal, target amount, timeline)\n"
            "2. Phase-wise Timeline:\n"
            "   - Phase 1: 0-6 months (action items with ₹ amounts)\n"
            "   - Phase 2: 6-12 months\n"
            "   - Phase 3: 1-3 years\n"
            "   - Phase 4: 3-10 years\n"
            "3. Monthly Budget Split (how to allocate the ₹"
            f"{p.monthly_surplus_inr:,.0f} surplus)\n"
            "4. Corpus Targets (emergency fund, retirement, goals)\n"
            "5. Priority Flags (urgent gaps: insurance, debt, emergency fund)\n"
            "Use financial_constants tool for return rates. Be specific with ₹ numbers."
        ),
        expected_output=(
            "A structured markdown financial plan with goals, phase timeline, "
            "monthly allocation, corpus targets, and priority flags."
        ),
        agent=agent,
    )


def build_advice_task(
    agent: Agent,
    profile: UserProfile,
    user_query: str,
    plan_summary: str,
) -> Task:
    # Truncate plan to avoid sending too many tokens to advisor
    plan_short = plan_summary[:1500] if len(plan_summary) > 1500 else plan_summary
    p = profile

    return Task(
        description=(
            f"User: {p.name}, {p.age}yo, {p.experience_level}, {p.risk_appetite} risk\n"
            f"Query: {user_query}\n"
            f"Plan summary:\n{plan_short}\n\n"
            "Provide HOW-TO advice structured as:\n"
            "1. Situation Assessment (2-3 lines)\n"
            "2. Step-by-Step Guide: for each plan phase — what product, "
            "   where to get it, how to set it up, why it suits this user\n"
            "3. Quick Wins (3 things to do this week)\n"
            "4. Common Mistakes to Avoid (2-3 relevant ones)\n\n"
            "Use rag_retrieval tool to find relevant knowledge before answering. "
            f"Explain at {p.experience_level} level."
        ),
        expected_output=(
            "Structured how-to advice with situation assessment, step-by-step guide, "
            "quick wins, and mistakes to avoid."
        ),
        agent=agent,
    )


# ══════════════════════════════════════════════════════════════
# CREW FINANCE SYSTEM
# ══════════════════════════════════════════════════════════════

class CrewFinanceSystem:

    def __init__(self):
        self.retriever = HybridRetriever()
        self.profile_agent  = build_profile_builder_agent()
        self.planner_agent  = build_planner_agent()
        self.advisor_agent  = build_advisor_agent(self.retriever)
        self.profile: Optional[UserProfile] = None
        self.profile_conversation: list[dict] = []
        self.profile_complete: bool = False

    # ── Phase 1: Profile Building ──────────────────────────────

    def chat_profile(self, user_message: str) -> tuple[str, bool]:
        self.profile_conversation.append({"role": "user", "content": user_message})

        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in self.profile_conversation
        )

        task = build_profile_extraction_task(self.profile_agent, transcript)
        crew = Crew(
            agents=[self.profile_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        response_text = str(result)
        self.profile_conversation.append({"role": "assistant", "content": response_text})

        # Check for completed profile JSON
        profile_match = re.search(
            r"```profile_json\s*(\{.*?\})\s*```",
            response_text,
            re.DOTALL,
        )

        if profile_match:
            try:
                raw = json.loads(profile_match.group(1))
                for key in [
                    "monthly_surplus_inr", "emergency_fund_target_inr",
                    "emergency_fund_gap_inr", "recommended_equity_pct",
                    "recommended_debt_pct"
                ]:
                    raw.pop(key, None)
                valid_fields = set(UserProfile.__dataclass_fields__.keys())
                filtered = {k: v for k, v in raw.items() if k in valid_fields}
                self.profile = UserProfile(**filtered)
                self.profile_complete = True

                clean = re.sub(r"```profile_json.*?```", "", response_text, flags=re.DOTALL).strip()
                if not clean:
                    clean = (
                        f"✅ Got your profile, {self.profile.name}! "
                        "What financial goal would you like help with?"
                    )
                return clean, True
            except Exception as e:
                return response_text + f"\n\n_(profile parse error: {e})_", False

        return response_text, False

    # ── Phase 2 & 3: Plan + Advice ────────────────────────────

    def run_finance_crew(self, user_query: str) -> dict:
        if not self.profile:
            raise ValueError("Profile not set.")

        # Run planner
        plan_task = build_planning_task(self.planner_agent, self.profile, user_query)
        plan_crew = Crew(
            agents=[self.planner_agent],
            tasks=[plan_task],
            process=Process.sequential,
            verbose=False,
        )
        plan_result = str(plan_crew.kickoff())

        # Run advisor
        advice_task = build_advice_task(
            self.advisor_agent, self.profile, user_query, plan_result
        )
        advice_crew = Crew(
            agents=[self.advisor_agent],
            tasks=[advice_task],
            process=Process.sequential,
            verbose=False,
        )
        advice_result = str(advice_crew.kickoff())

        return {
            "plan": plan_result,
            "advice": advice_result,
            "profile": self.profile.to_dict(),
        }

    def set_profile(self, profile: UserProfile):
        self.profile = profile
        self.profile_complete = True

    def reset(self):
        self.profile = None
        self.profile_conversation = []
        self.profile_complete = False


# ══════════════════════════════════════════════════════════════
# STANDALONE CLI
# ══════════════════════════════════════════════════════════════

def cli_main():
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    system = CrewFinanceSystem()

    console.print(Panel(
        "[bold green]💹 Finance Advisor — CrewAI[/bold green]",
        expand=False,
    ))

    console.print("\n[bold cyan]Agent:[/bold cyan] Hello! Let's build your financial profile. "
                  "What's your name, age, and city?")

    while not system.profile_complete:
        try:
            user_input = console.input("\n[bold yellow]You:[/bold yellow] ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if user_input.lower() in ("quit", "exit"):
            return
        with console.status("[dim]Thinking…[/dim]"):
            response, complete = system.chat_profile(user_input)
        console.print(f"\n[bold cyan]Agent:[/bold cyan]")
        console.print(Markdown(response))
        if complete:
            console.print(Panel(system.profile.to_prompt_str(), title="✅ Profile", border_style="green"))

    console.print("\n[bold cyan]Agent:[/bold cyan] Profile complete! What's your financial goal?")

    while True:
        try:
            query = console.input("\n[bold yellow]You:[/bold yellow] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in ("quit", "exit"):
            break
        if not query:
            continue
        with console.status("[dim]Running agents…[/dim]"):
            try:
                results = system.run_finance_crew(query)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue

        console.print("\n[bold green]📅 FINANCIAL PLAN[/bold green]")
        console.print(Markdown(results["plan"]))
        console.print("\n[bold blue]💡 FINANCIAL ADVICE[/bold blue]")
        console.print(Markdown(results["advice"]))


if __name__ == "__main__":
    cli_main()