# crews/planning_crew.py
# ─────────────────────────────────────────────────────────────
# Planning Crew: 6 sequential agents for financial plan generation.
# Uses GPT-4o-mini for all agents (accuracy > latency).
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from crewai import Agent, Task, Crew, Process, LLM

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PLANNING_LLM, FINANCIAL_CONSTANTS, SEBI_DISCLAIMER, OPENROUTER_API_KEY
from models import FinancialPlan

# Import individual tools (simpler for LLMs to use)
from tools.financial_calculator import (
    MonthlySurplusTool,
    DebtToIncomeTool,
    EmergencyFundTool,
    NetWorthTool,
    AssetAllocationTool,
    RetirementCorpusTool,
    SIPRequiredTool,
    InsuranceGapTool,
)
from tools.tax_calculator import TaxCalculatorTool
from tools.rag_tool import FinanceRAGTool
from tools.portfolio_overlap import PortfolioOverlapTool


# ── Shared Tool Instances ─────────────────────────────────────
# Individual calculation tools (preferred - simpler for LLMs)
surplus_tool = MonthlySurplusTool()
dti_tool = DebtToIncomeTool()
emergency_tool = EmergencyFundTool()
networth_tool = NetWorthTool()
allocation_tool = AssetAllocationTool()
corpus_tool = RetirementCorpusTool()
sip_tool = SIPRequiredTool()
insurance_tool = InsuranceGapTool()

# Other tools
tax_tool = TaxCalculatorTool()
rag_tool = FinanceRAGTool()
overlap_tool = PortfolioOverlapTool()

# ── LLM Configuration (DeepSeek via OpenRouter) ─────────────
# Using DeepSeek for better rate limits and structured output support
planning_llm = LLM(
    model=PLANNING_LLM,  # "openrouter/deepseek/deepseek-chat"
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    temperature=0.7,
    max_tokens=8192,  # Increased for complex FinancialPlan generation (24 months + full schema)
)


# ── Agent Definitions ─────────────────────────────────────────

def _agent_1_data_analyst() -> Agent:
    return Agent(
        role="Certified Financial Data Analyst",
        goal=(
            "Validate and analyze user financial data to compute base metrics: "
            "monthly surplus, debt-to-income ratio, savings rate, net worth, "
            "emergency fund adequacy. Flag any data inconsistencies."
        ),
        backstory=(
            "You are a meticulous financial data analyst who validates every number "
            "before it enters the planning pipeline. You catch errors like expenses "
            "exceeding income, unrealistic return expectations, or missing critical "
            "data points. You always use the calculation tools for all computations. "
            "Each tool takes simple numeric inputs - just pass the values directly."
        ),
        tools=[surplus_tool, dti_tool, emergency_tool, networth_tool, allocation_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_2_tax_comparator() -> Agent:
    return Agent(
        role="Indian Income Tax Specialist (FY 2025-26)",
        goal=(
            "Compare the user's tax liability under BOTH Old Regime and New Regime "
            "for FY 2025-26. Identify which regime is optimal. Map all eligible "
            "deductions (80C, 80CCD, 80D, HRA, Section 24). Calculate tax savings "
            "from recommended investments."
        ),
        backstory=(
            "You are an expert in Indian income tax with deep knowledge of both the "
            "Old and New tax regimes for FY 2025-26. You always compute tax under "
            "BOTH regimes using the tax_calculator tool, never estimate. You know "
            "that 80CCD(2) employer NPS contributions are allowed in BOTH regimes, "
            "and standard deduction is ₹75,000 in new regime vs ₹50,000 in old. "
            "Section 87A rebate is ₹60,000 for income up to ₹12L (new) and ₹12,500 "
            "for income up to ₹5L (old)."
        ),
        tools=[tax_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_3_insurance_analyst() -> Agent:
    return Agent(
        role="Insurance Gap Analysis Specialist",
        goal=(
            "Assess the user's insurance coverage gaps: term life (10-15x annual "
            "income using HLV method), health (₹10-25L family floater based on "
            "city/age), critical illness, and personal accident. Consider dependents "
            "and life stage."
        ),
        backstory=(
            "You are an insurance specialist who follows IRDAI guidelines. You assess "
            "coverage needs based on Human Life Value (HLV) method for term insurance "
            "and city-tier medical costs for health insurance. You never recommend "
            "specific insurance products or companies — only coverage types and amounts. "
            "For metro cities, minimum health cover is ₹10L. For non-metro, ₹5L."
        ),
        tools=[insurance_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_4_investment_strategist() -> Agent:
    return Agent(
        role="SEBI-Compliant Investment Strategist",
        goal=(
            "Design the optimal asset allocation and month-by-month SIP schedule. "
            "Apply age-based glidepath (equity reducing as retirement approaches). "
            "Detect portfolio overlap if CAS data is available. Recommend asset "
            "CATEGORIES (large cap, mid cap, debt, gold) — never specific funds or ISINs."
        ),
        backstory=(
            "You are a strategic investment planner who follows SEBI mutual fund "
            "categorization norms. You design portfolios using modern portfolio theory "
            "principles adapted for Indian markets. Use the calculation tools for "
            "SIP, CAGR, and corpus computations. When CAS data is available, "
            "check for portfolio overlap using the portfolio_overlap_detector tool. "
            "You NEVER recommend specific mutual fund schemes, stocks, or ISINs — only "
            "asset categories and allocation percentages as per SEBI categorization."
        ),
        tools=[allocation_tool, corpus_tool, sip_tool, overlap_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_5_compliance() -> Agent:
    return Agent(
        role="Financial Regulatory Compliance Officer",
        goal=(
            "Review the entire financial plan for regulatory compliance. Ensure: "
            "1. No specific fund/stock recommendations (SEBI IA violation). "
            "2. All calculations cite their methodology. "
            "3. Risk disclaimers are present. "
            "4. The plan distinguishes AI guidance from licensed financial advice. "
            "5. Investment limits (PPF ₹1.5L, NPS 80CCD(1B) ₹50K) are respected. "
            "6. Tax advice follows latest FY 2025-26 rules."
        ),
        backstory=(
            "You are a compliance officer ensuring this AI tool operates within "
            "Indian financial regulations. You know that SEBI (Investment Advisers) "
            "Regulations, 2013 require registration for providing investment advice. "
            "This platform is NOT a SEBI-registered Investment Adviser — it provides "
            "AI-generated educational guidance only. You enforce that every output "
            "includes the mandatory disclaimer and that no specific securities are "
            "recommended. You also verify that all tax computations use correct "
            "FY 2025-26 slabs and that investment limits are not exceeded."
        ),
        tools=[rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_6_synthesizer() -> Agent:
    return Agent(
        role="Financial Plan Compiler & Educator",
        goal=(
            "Synthesize outputs from all previous agents into a single, comprehensive, "
            "user-friendly FinancialPlan. The plan must be actionable — the user should "
            "NOT need to interpret raw numbers. Include 'why' explanations for each "
            "recommendation. Embed the compliance disclaimer. Generate a minimum of "
            "24 monthly plan entries."
        ),
        backstory=(
            "You are an expert at presenting complex financial data in a clear, "
            "actionable format. You compile month-by-month plans, visual-ready data, "
            "and prioritized action items. Every recommendation includes a 'why' that "
            "educates the user, not just a 'what'. You include the mandatory disclaimer "
            "at the beginning and end of every plan. You always output the plan in the "
            "exact JSON structure requested."
        ),
        tools=[rag_tool],
        llm=planning_llm,
        verbose=True,
    )


# ── Task Definitions ──────────────────────────────────────────

def build_planning_tasks(
    profile_data: dict,
    cas_data: dict | None = None,
) -> tuple[list[Agent], list[Task]]:
    """
    Build the 6-agent planning pipeline with tasks.

    Args:
        profile_data: User's financial profile dict
        cas_data: Parsed CAS mutual fund data (optional)

    Returns:
        (agents_list, tasks_list) ready to be passed to Crew
    """
    profile_str = json.dumps(profile_data, indent=2)
    cas_str = json.dumps(cas_data, indent=2) if cas_data else "No CAS data available."
    constants_str = json.dumps(FINANCIAL_CONSTANTS, indent=2, default=str)

    agents = [
        _agent_1_data_analyst(),
        _agent_2_tax_comparator(),
        _agent_3_insurance_analyst(),
        _agent_4_investment_strategist(),
        _agent_5_compliance(),
        _agent_6_synthesizer(),
    ]

    # ── Task 1: Data Analysis ─────────────────────────────────
    # Pre-compute values for the agent
    monthly_income = profile_data.get("annual_income", 0) / 12
    monthly_expenses = profile_data.get("monthly_expenses", 0)
    total_emi = (
        profile_data.get("home_loan_emi", 0) +
        profile_data.get("car_loan_emi", 0) +
        profile_data.get("other_emi", 0)
    )
    existing_savings = profile_data.get("existing_savings", 0)
    
    task_1 = Task(
        description=f"""Analyze the user's financial profile and compute base metrics.

USER PROFILE:
{profile_str}

Use the following tools to compute metrics. Each tool takes simple parameters - just pass the values shown:

1. calculate_monthly_surplus tool:
   - monthly_income: {monthly_income:.2f}
   - monthly_expenses: {monthly_expenses:.2f}
   - emi_total: {total_emi:.2f}

2. calculate_debt_to_income tool:
   - total_emi: {total_emi:.2f}
   - monthly_income: {monthly_income:.2f}

3. calculate_emergency_fund tool:
   - monthly_expenses: {monthly_expenses:.2f}
   - existing_savings: {existing_savings:.2f}
   - months: 6

4. calculate_net_worth tool:
   - existing_mf: {profile_data.get("existing_mf", 0)}
   - existing_ppf: {profile_data.get("existing_ppf", 0)}
   - existing_epf: {profile_data.get("existing_epf", 0)}
   - existing_fd: {profile_data.get("existing_fd", 0)}
   - existing_nps: {profile_data.get("existing_nps", 0)}
   - existing_savings: {existing_savings}

5. calculate_asset_allocation tool:
   - age: {profile_data.get("age", 30)}
   - risk_appetite: {profile_data.get("risk_appetite", "moderate")}

Flag any data inconsistencies (e.g., expenses > income).
Output a validated financial snapshot with all computed metrics.""",
        expected_output=(
            "A validated financial snapshot with: monthly surplus, DTI ratio, "
            "savings rate, emergency fund status, net worth, and any data flags."
        ),
        agent=agents[0],
    )

    # ── Task 2: Tax Comparison ────────────────────────────────
    tax_inputs = {
        "annual_income": profile_data.get("annual_income", 0),
        "ppf_contribution": min(profile_data.get("existing_ppf", 0), 150000),
        "nps_contribution": min(profile_data.get("existing_nps", 0), 50000),
        "home_loan_interest": profile_data.get("home_loan_interest_annually", 0),
        "hra_received": profile_data.get("annual_hra_received", 0),
        "rent_paid": profile_data.get("annual_rent_paid", 0),
        "is_metro": profile_data.get("is_metro_city", True),
        "health_insurance_self": 25000 if profile_data.get("has_health_insurance") else 0,
    }

    task_2 = Task(
        description=f"""Compare the user's tax liability under Old and New regimes for FY 2025-26.

USER PROFILE:
{profile_str}

Use the tax_calculator tool with these inputs:
{json.dumps(tax_inputs, indent=2)}

Based on the results:
1. Clearly state which regime is better and by how much
2. List all deductions utilized vs wasted
3. Recommend tax-saving investments if applicable (categories only, no specific products)
4. If the user has both home loan + HRA, analyze the interaction""",
        expected_output=(
            "Complete tax comparison: old vs new regime tax amounts, "
            "recommended regime, savings, deduction map, and tax-saving advice."
        ),
        agent=agents[1],
        context=[task_1],
    )

    # ── Task 3: Insurance Analysis ────────────────────────────
    task_3 = Task(
        description=f"""Assess the user's insurance coverage gaps.

USER PROFILE:
{profile_str}

Use the calculate_insurance_gap tool with these parameters:
- annual_income: {profile_data.get("annual_income", 0)}
- existing_cover: {profile_data.get("term_cover_amount", 0)}
- multiplier: 10

Health insurance analysis:
- Current cover: {profile_data.get("health_cover_amount", 0)}
- Recommended minimum: {"₹10L" if profile_data.get("is_metro_city", True) else "₹5L"} for {"metro" if profile_data.get("is_metro_city", True) else "non-metro"} city

Consider:
- Number of dependents: {profile_data.get('dependents', 0)}
- City: {profile_data.get('city', 'India')}
- Age: {profile_data.get('age', 30)}

Provide specific coverage amount recommendations, NOT specific products.""",
        expected_output=(
            "Insurance gap analysis: term cover gap, health cover gap, "
            "recommended amounts, and prioritized action items."
        ),
        agent=agents[2],
        context=[task_1],
    )

    # ── Task 4: Investment Strategy ───────────────────────────
    cas_instruction = ""
    if cas_data:
        cas_instruction = f"""
The user has provided CAS (Consolidated Account Statement) data:
{cas_str}

IMPORTANT: Also run the portfolio_overlap_detector tool with the funds from CAS data.
Pass the funds as a JSON string in the funds_json parameter.
Provide consolidation advice if overlap > 25%."""

    # Pre-compute investment-related values
    years_to_retire = profile_data.get("target_retirement_age", 60) - profile_data.get("age", 30)
    target_monthly_draw = profile_data.get("target_monthly_draw", 100000)
    
    task_4 = Task(
        description=f"""Design the investment strategy and month-by-month SIP schedule.

USER PROFILE:
{profile_str}

Use the following tools with the specified parameters:

1. calculate_asset_allocation tool:
   - age: {profile_data.get("age", 30)}
   - risk_appetite: {profile_data.get("risk_appetite", "moderate")}

2. calculate_retirement_corpus tool:
   - monthly_draw_today: {target_monthly_draw}
   - years_to_retire: {years_to_retire}
   - inflation_pct: 6.5
   - swr_pct: 4.0

3. calculate_sip_required tool (use corpus result from above):
   - target_amount: <corpus_from_retirement_corpus_result>
   - rate_pct: 12
   - years: {profile_data.get("investment_horizon_years", 10)}
{cas_instruction}

Then create a month-by-month SIP allocation table for at least 24 months.
Split SIP across: large_cap, mid_cap, small_cap, debt, gold, PPF, NPS.

CRITICAL RULES:
- PPF contribution MUST NOT exceed ₹12,500/month (₹1,50,000/year limit)
- NPS 80CCD(1B) MUST NOT exceed ₹50,000/year
- Recommend CATEGORIES only — no specific fund names, schemes, or ISINs""",
        expected_output=(
            "Complete investment strategy: target corpus, monthly SIP total, "
            "asset allocation, 24-month SIP schedule, and portfolio overlap "
            "analysis if CAS data was available."
        ),
        agent=agents[3],
        context=[task_1, task_2, task_3],
    )

    # ── Task 5: Compliance Review ─────────────────────────────
    task_5 = Task(
        description=f"""Review ALL previous agent outputs for regulatory compliance.

Check each of the following:
1. ❌ Are there any specific mutual fund scheme names, ISINs, or stock tickers?
   → If yes, flag them for removal. Only SEBI categories are allowed.
2. ❌ Are PPF contributions exceeding ₹1.5L/year or NPS exceeding ₹50K/year?
   → If yes, flag for correction.
3. ❌ Do tax calculations use correct FY 2025-26 slabs?
4. ✅ Does the plan include the SEBI disclaimer? The required text is:
   "{SEBI_DISCLAIMER}"
5. ✅ Does every recommendation explain WHY (educational value)?

If ANY violations are found, clearly list corrections needed.
If all checks pass, confirm compliance and output the disclaimer text.""",
        expected_output=(
            "Compliance review: PASS/FAIL with specific violations listed, "
            "corrections needed, and the mandatory SEBI disclaimer text."
        ),
        agent=agents[4],
        context=[task_1, task_2, task_3, task_4],
    )

    # ── Task 6: Plan Synthesis ────────────────────────────────
    task_6 = Task(
        description=f"""Synthesize ALL previous agent outputs into a single FinancialPlan JSON.

Combine:
- Financial snapshot from Agent 1
- Tax comparison from Agent 2
- Insurance gaps from Agent 3
- Investment strategy + monthly SIP schedule from Agent 4
- Compliance review + disclaimer from Agent 5

The output MUST follow the FinancialPlan schema exactly.

IMPORTANT:
- Include at least 24 MonthlyPlanEntry items
- Include the SEBI disclaimer: "{SEBI_DISCLAIMER}"
- Include educational_notes explaining WHY for each recommendation
- Set scenario_type to the appropriate value
- Include confidence_notes listing assumptions and limitations
- Include assumptions dict with return rates, inflation, SWR used

Every numerical value must come from the calculator tools — do not invent numbers.""",
        expected_output="A complete FinancialPlan JSON matching the Pydantic schema.",
        agent=agents[5],
        context=[task_1, task_2, task_3, task_4, task_5],
        output_pydantic=FinancialPlan,
        guardrail=(
            "Verify SEBI compliance: 1) Must include text about 'not a SEBI-registered' or 'educational'; "
            "2) Must NOT contain specific ISIN codes (INF followed by alphanumerics); "
            "3) Must NOT recommend specific mutual fund scheme names or stock tickers."
        ),
    )

    return agents, [task_1, task_2, task_3, task_4, task_5, task_6]


def create_planning_crew(
    profile_data: dict,
    cas_data: dict | None = None,
) -> Crew:
    """Create and return the configured Planning Crew."""
    agents, tasks = build_planning_tasks(profile_data, cas_data)

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
