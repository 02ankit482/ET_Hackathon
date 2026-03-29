# crews/planning_crew.py
# ─────────────────────────────────────────────────────────────
# Planning Crew: 6 sequential agents for financial plan generation.
# Uses GPT-4o-mini for all agents (accuracy > latency).
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, Process, LLM

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    PLANNING_LLM,
    FINANCIAL_CONSTANTS,
    SEBI_DISCLAIMER,
    OPENROUTER_API_KEY,
    OPENAI_API_BASE,
    PLANNING_MAX_TOKENS_DEFAULT,
)
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
    MutualFundRecommenderTool,
    AllFundRecommendationsTool,
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

# Mutual fund recommender tools
mf_recommender_tool = MutualFundRecommenderTool()
all_funds_tool = AllFundRecommendationsTool()

# Other tools
tax_tool = TaxCalculatorTool()
rag_tool = FinanceRAGTool()
overlap_tool = PortfolioOverlapTool()

def _build_planning_llm(max_tokens: int | None = None) -> LLM:
    llm_max_tokens = (
        max_tokens if max_tokens is not None else PLANNING_MAX_TOKENS_DEFAULT
    )
    return LLM(
        model=PLANNING_LLM,  # "openrouter/deepseek/deepseek-chat"
        base_url=OPENAI_API_BASE,
        api_key=OPENROUTER_API_KEY,
        temperature=0.7,
        max_tokens=llm_max_tokens,
    )


# ── Helper Functions ──────────────────────────────────────────

def get_plan_months(num_months: int = 6) -> list[str]:
    """
    Generate list of month strings starting from next month.
    
    Args:
        num_months: Number of months to generate (default 6 = 2 quarters)
    
    Returns:
        List of month strings in YYYY-MM format
    """
    today = datetime.now()
    # Start from next month
    if today.month == 12:
        start_date = datetime(today.year + 1, 1, 1)
    else:
        start_date = datetime(today.year, today.month + 1, 1)
    
    months = []
    current = start_date
    for _ in range(num_months):
        months.append(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)
    
    return months


def _compact_json_for_prompt(data: dict | None, max_chars: int = 3500) -> str:
    if not data:
        return "{}"
    raw = json.dumps(data, indent=2, default=str)
    if len(raw) <= max_chars:
        return raw
    truncated = raw[:max_chars]
    return (
        f"{truncated}\n... [truncated for prompt size; original JSON length={len(raw)} chars]"
    )


def _summarize_cas_for_prompt(cas_data: dict | None) -> str:
    if not cas_data:
        return "No CAS data available."
    summary = {
        "total_mf_value": cas_data.get("total_mf_value"),
        "fund_count": cas_data.get("fund_count"),
        "amc_count": cas_data.get("amc_count"),
    }
    funds = cas_data.get("funds") if isinstance(cas_data, dict) else None
    if isinstance(funds, list):
        summary["sample_funds"] = funds[:10]
    return _compact_json_for_prompt(summary, max_chars=2500)


def validate_financial_plan(result):
    """
    Functional guardrail to validate FinancialPlan output.
    
    Returns:
        (True, result) if valid
        (False, error_message) if invalid with feedback for retry
    """
    import re
    
    plan = None
    
    # Case 1: result is already a FinancialPlan object
    if isinstance(result, FinancialPlan):
        plan = result
    # Case 2: result has pydantic attribute with FinancialPlan
    elif hasattr(result, 'pydantic') and result.pydantic is not None:
        if isinstance(result.pydantic, FinancialPlan):
            plan = result.pydantic
        else:
            # Try to validate as dict
            try:
                plan = FinancialPlan.model_validate(result.pydantic)
            except Exception:
                pass
    
    # Case 3: Try to parse from raw output
    if plan is None and hasattr(result, 'raw') and result.raw:
        raw = result.raw
        
        # Extract JSON from markdown code blocks if present
        # Match ```json ... ``` or ``` ... ```
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
        if json_match:
            raw = json_match.group(1).strip()
        
        if raw:
            try:
                plan_data = json.loads(raw)
                plan = FinancialPlan.model_validate(plan_data)
            except json.JSONDecodeError as e:
                return (False, f"Failed to parse plan JSON: {e}. Ensure output is valid JSON (no markdown code blocks).")
            except Exception as e:
                return (False, f"Plan validation failed: {e}. Ensure output matches FinancialPlan schema.")
    
    # Case 4: Check if result itself can be converted (string representation)
    if plan is None:
        result_str = str(result) if result else ""
        # Try extracting JSON from the string
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_str)
        if json_match:
            try:
                plan_data = json.loads(json_match.group(1).strip())
                plan = FinancialPlan.model_validate(plan_data)
            except Exception:
                pass
    
    if plan is None:
        return (False, "No valid plan found. Return a complete FinancialPlan JSON without markdown code blocks.")
    
    errors = []
    
    # Check 1: Disclaimer must contain SEBI-related text
    disclaimer = getattr(plan, 'disclaimer', '') or ''
    if not disclaimer:
        errors.append("Missing disclaimer field. Include the SEBI disclaimer text.")
    elif 'sebi' not in disclaimer.lower() and 'educational' not in disclaimer.lower():
        errors.append("Disclaimer must mention SEBI or educational guidance.")
    
    # Check 2: Monthly plan should have 6 entries
    monthly_plan = getattr(plan, 'monthly_plan', []) or []
    if len(monthly_plan) != 6:
        errors.append(f"monthly_plan has {len(monthly_plan)} entries, must have exactly 6.")
    
    # Check 3: fund_options should exist with at least some recommendations
    fund_options = getattr(plan, 'fund_options', None)
    if fund_options is None:
        errors.append("fund_options is missing. Include fund recommendations at the plan level.")
    else:
        # Check at least one category has funds
        has_funds = any([
            getattr(fund_options, 'large_cap_funds', []),
            getattr(fund_options, 'mid_cap_funds', []),
            getattr(fund_options, 'small_cap_funds', []),
            getattr(fund_options, 'debt_funds', []),
            getattr(fund_options, 'gold_funds', []),
        ])
        if not has_funds:
            errors.append("fund_options has no fund recommendations. Include at least some funds.")
    
    # Check 4: Required fields
    if not getattr(plan, 'summary', ''):
        errors.append("Missing summary field.")
    if not getattr(plan, 'target_corpus', 0):
        errors.append("Missing or zero target_corpus.")
    
    if errors:
        return (False, "Plan validation failed: " + "; ".join(errors))
    
    return (True, result)


# ── Agent Definitions ─────────────────────────────────────────

def _agent_1_data_analyst(planning_llm: LLM) -> Agent:
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


def _agent_2_tax_insurance_specialist(planning_llm: LLM) -> Agent:
    return Agent(
        role="Indian Tax and Insurance Specialist (FY 2025-26)",
        goal=(
            "Deliver a combined tax and insurance assessment. Compare tax liability "
            "under BOTH old and new regimes for FY 2025-26, identify optimal regime, "
            "map deductions, and assess insurance coverage gaps (term + health) with "
            "recommended coverage amounts."
        ),
        backstory=(
            "You are a dual-domain specialist in Indian taxation and insurance. "
            "You compute tax outcomes using the tax_calculator tool and insurance "
            "coverage gaps using the calculate_insurance_gap tool. You never estimate "
            "numerical results manually. You do not recommend specific products; only "
            "coverage amounts and category-level actions."
        ),
        tools=[tax_tool, insurance_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_4_investment_strategist(planning_llm: LLM) -> Agent:
    return Agent(
        role="SEBI-Compliant Investment Strategist",
        goal=(
            "Design the optimal asset allocation and month-by-month SIP schedule. "
            "Apply age-based glidepath (equity reducing as retirement approaches). "
            "Detect portfolio overlap if CAS data is available. For each allocation "
            "category, use the mutual fund recommender tools to get top 5 fund options "
            "with their performance data, expense ratios, and risk levels. The plan "
            "should include fund OPTIONS for user to choose from — presented as "
            "educational information, not specific investment advice."
        ),
        backstory=(
            "You are a strategic investment planner who follows SEBI mutual fund "
            "categorization norms. You design portfolios using modern portfolio theory "
            "principles adapted for Indian markets. Use the calculation tools for "
            "SIP, CAGR, and corpus computations. When CAS data is available, "
            "check for portfolio overlap using the portfolio_overlap_detector tool. "
            "For each asset category in the plan, use the get_all_fund_recommendations "
            "tool to retrieve top 5 fund options that the user can consider. These are "
            "presented as educational options with performance data — the user makes "
            "the final investment decision."
        ),
        tools=[allocation_tool, corpus_tool, sip_tool, overlap_tool, all_funds_tool, mf_recommender_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_5_compliance(planning_llm: LLM) -> Agent:
    return Agent(
        role="Financial Regulatory Compliance Officer",
        goal=(
            "Review the entire financial plan for regulatory compliance. Ensure: "
            "1. Fund recommendations are presented as EDUCATIONAL OPTIONS, not advice. "
            "2. All calculations cite their methodology. "
            "3. Risk disclaimers are present. "
            "4. The plan distinguishes AI guidance from licensed financial advice. "
            "5. Investment limits (PPF ₹1.5L, NPS 80CCD(1B) ₹50K) are respected. "
            "6. Tax advice follows latest FY 2025-26 rules. "
            "7. Fund recommendations include disclaimers about past performance."
        ),
        backstory=(
            "You are a compliance officer ensuring this AI tool operates within "
            "Indian financial regulations. You know that SEBI (Investment Advisers) "
            "Regulations, 2013 require registration for providing investment advice. "
            "This platform is NOT a SEBI-registered Investment Adviser — it provides "
            "AI-generated educational guidance only. Fund options shown are for "
            "educational purposes with historical performance data. Users must verify "
            "current NAVs and performance from official AMC websites. You enforce that "
            "every output includes the mandatory disclaimer."
        ),
        tools=[rag_tool],
        llm=planning_llm,
        verbose=True,
    )


def _agent_6_synthesizer(planning_llm: LLM) -> Agent:
    return Agent(
        role="Financial Plan Compiler & Educator",
        goal=(
            "Synthesize outputs from all previous agents into a single, comprehensive, "
            "user-friendly FinancialPlan. The plan must be actionable — the user should "
            "NOT need to interpret raw numbers. Include 'why' explanations for each "
            "recommendation. Embed the compliance disclaimer. Generate exactly 6 monthly "
            "plan entries (2 quarters) starting from next month. Each month must include "
            "the top 5 fund options per category from the investment strategist's output."
        ),
        backstory=(
            "You are an expert at presenting complex financial data in a clear, "
            "actionable format. You compile month-by-month plans, visual-ready data, "
            "and prioritized action items. Every recommendation includes a 'why' that "
            "educates the user, not just a 'what'. You include the mandatory disclaimer "
            "at the beginning and end of every plan. For each month, you include the "
            "mutual fund options with their performance data so users can make informed "
            "choices. You always output the plan in the exact JSON structure requested."
        ),
        tools=[all_funds_tool, rag_tool],
        llm=planning_llm,
        verbose=True,
    )


# ── Task Definitions ──────────────────────────────────────────

def build_planning_tasks(
    profile_data: dict,
    cas_data: dict | None = None,
    max_tokens: int | None = None,
    compact_output: bool = False,
) -> tuple[list[Agent], list[Task]]:
    """
    Build the 5-agent planning pipeline with tasks.

    Args:
        profile_data: User's financial profile dict
        cas_data: Parsed CAS mutual fund data (optional)

    Returns:
        (agents_list, tasks_list) ready to be passed to Crew
    """
    compact_profile = {
        "name": profile_data.get("name"),
        "age": profile_data.get("age"),
        "city": profile_data.get("city"),
        "annual_income": profile_data.get("annual_income"),
        "monthly_expenses": profile_data.get("monthly_expenses"),
        "home_loan_emi": profile_data.get("home_loan_emi"),
        "car_loan_emi": profile_data.get("car_loan_emi"),
        "other_emi": profile_data.get("other_emi"),
        "existing_mf": profile_data.get("existing_mf"),
        "existing_ppf": profile_data.get("existing_ppf"),
        "existing_nps": profile_data.get("existing_nps"),
        "existing_epf": profile_data.get("existing_epf"),
        "existing_fd": profile_data.get("existing_fd"),
        "existing_savings": profile_data.get("existing_savings"),
        "current_sip": profile_data.get("current_sip"),
        "primary_goal": profile_data.get("primary_goal"),
        "target_retirement_age": profile_data.get("target_retirement_age"),
        "target_monthly_draw": profile_data.get("target_monthly_draw"),
        "risk_appetite": profile_data.get("risk_appetite"),
        "investment_horizon_years": profile_data.get("investment_horizon_years"),
        "has_term_insurance": profile_data.get("has_term_insurance"),
        "term_cover_amount": profile_data.get("term_cover_amount"),
        "has_health_insurance": profile_data.get("has_health_insurance"),
        "health_cover_amount": profile_data.get("health_cover_amount"),
        "is_metro_city": profile_data.get("is_metro_city"),
        "dependents": profile_data.get("dependents"),
    }
    compact_profile_str = _compact_json_for_prompt(compact_profile, max_chars=2500)
    cas_summary_str = _summarize_cas_for_prompt(cas_data)
    
    # Generate the 6 months for the plan (current month + 1 onwards)
    plan_months = get_plan_months(6)
    plan_months_str = ", ".join(plan_months)
    current_timestamp = datetime.now().isoformat()

    planning_llm = _build_planning_llm(max_tokens=max_tokens)
    agents = [
        _agent_1_data_analyst(planning_llm),
        _agent_2_tax_insurance_specialist(planning_llm),
        _agent_4_investment_strategist(planning_llm),
        _agent_5_compliance(planning_llm),
        _agent_6_synthesizer(planning_llm),
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
{compact_profile_str}

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

    # ── Task 2: Tax + Insurance Analysis ──────────────────────
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
        description=f"""Perform a combined tax and insurance assessment for the user.

USER PROFILE:
{compact_profile_str}

Part A — Tax:
Use the tax_calculator tool with these inputs:
{json.dumps(tax_inputs, indent=2)}

Tax output requirements:
1. Clearly state which regime is better and by how much
2. List all deductions utilized vs wasted
3. Recommend tax-saving investments if applicable (categories only, no specific products)
4. If the user has both home loan + HRA, analyze the interaction

Part B — Insurance:
Use the calculate_insurance_gap tool with these parameters:
- annual_income: {profile_data.get("annual_income", 0)}
- existing_cover: {profile_data.get("term_cover_amount", 0)}
- multiplier: 10

Health insurance checks:
- Current cover: {profile_data.get("health_cover_amount", 0)}
- Recommended minimum: {"₹10L" if profile_data.get("is_metro_city", True) else "₹5L"} for {"metro" if profile_data.get("is_metro_city", True) else "non-metro"} city

Consider:
- Number of dependents: {profile_data.get('dependents', 0)}
- City: {profile_data.get('city', 'India')}
- Age: {profile_data.get('age', 30)}

Provide specific coverage amount recommendations, NOT specific products.""",
        expected_output=(
            "Combined report containing: tax comparison (old vs new, recommended regime, "
            "deduction map) and insurance gap analysis (term and health recommended amounts, gaps, "
            "and prioritized actions)."
        ),
        agent=agents[1],
        context=[task_1],
    )

    # ── Task 3: Investment Strategy ───────────────────────────
    cas_instruction = ""
    if cas_data:
        cas_instruction = f"""
The user has provided CAS (Consolidated Account Statement) data:
{cas_summary_str}

IMPORTANT: Also run the portfolio_overlap_detector tool with the funds from CAS data.
Pass the funds as a JSON string in the funds_json parameter.
Provide consolidation advice if overlap > 25%."""

    # Pre-compute investment-related values
    years_to_retire = profile_data.get("target_retirement_age", 60) - profile_data.get("age", 30)
    target_monthly_draw = profile_data.get("target_monthly_draw", 100000)
    fund_count_instruction = (
        "top 2 mutual fund options for each category"
        if compact_output
        else "top 5 mutual fund options for each category"
    )
    monthly_fund_instruction = (
        "To keep output compact, include detailed fund arrays only in the first month entry; "
        "for months 2-6, keep fund arrays empty unless absolutely needed."
        if compact_output
        else "Include fund arrays in each month entry."
    )
    
    task_3 = Task(
        description=f"""Design the investment strategy and month-by-month SIP schedule.

PLAN MONTHS: {plan_months_str}
(Generate plan for exactly these 6 months - next 2 quarters starting from next month)

USER PROFILE:
{compact_profile_str}

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

4. get_all_fund_recommendations tool:
   - Call this to get {fund_count_instruction}
   - These will be included in the monthly plan entries
{cas_instruction}

Then create a month-by-month SIP allocation table for exactly 6 months: {plan_months_str}
Split SIP across: large_cap, mid_cap, small_cap, debt, gold, PPF, NPS.

IMPORTANT TO REDUCE CONTEXT SIZE:
- In this Task 4 output, include ONE shared "fund_options_by_category" block (top 5 each).
- Do NOT repeat full fund option lists for every month in Task 4 output.
- These are educational options showing historical performance; user decides what to invest in.
- {monthly_fund_instruction}

CRITICAL RULES:
- PPF contribution MUST NOT exceed ₹12,500/month (₹1,50,000/year limit)
- NPS 80CCD(1B) MUST NOT exceed ₹50,000/year
- Fund options are EDUCATIONAL - include disclaimer about past performance""",
        expected_output=(
            "Complete investment strategy: target corpus, monthly SIP total, "
            "asset allocation, 6-month SIP schedule, and ONE shared fund_options_by_category "
            "block (large/mid/small/debt/gold), "
            "and portfolio overlap analysis if CAS data was available."
        ),
        agent=agents[2],
        context=[task_1, task_2],
    )

    # ── Task 4: Compliance Review ─────────────────────────────
    task_4 = Task(
        description=f"""Review ALL previous agent outputs for regulatory compliance.

Check each of the following:
1. ✅ Fund recommendations are presented as EDUCATIONAL OPTIONS with historical data
   → Verify they include disclaimers about past performance
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
        agent=agents[3],
        context=[task_1, task_2, task_3],
    )

    # ── Task 5: Plan Synthesis ────────────────────────────────
    task_5 = Task(
        description=f"""Synthesize ALL previous agent outputs into a single FinancialPlan JSON.

PLAN MONTHS: {plan_months_str}
CURRENT TIMESTAMP: {current_timestamp}

Combine:
- Financial snapshot from Agent 1
- Combined tax + insurance analysis from Agent 2
- Investment strategy + monthly SIP schedule + shared FUND OPTIONS from Agent 3
- Compliance review + disclaimer from Agent 4

The output MUST follow the FinancialPlan schema exactly.

CRITICAL REQUIREMENTS:
1. Include exactly 6 MonthlyPlanEntry items for months: {plan_months_str}
   Each MonthlyPlanEntry contains: month, sip amounts, ppf/nps contributions, equity_pct, debt_pct, notes
   
2. Include fund_options at the PLAN LEVEL (not per month) with:
   - large_cap_funds: 3 educational options
   - mid_cap_funds: 3 educational options
   - small_cap_funds: 3 educational options  
   - debt_funds: 3 educational options
   - gold_funds: 3 educational options
   
   Use the get_all_fund_recommendations tool to get these fund options.
   Each fund recommendation must include all required schema fields.

3. Set plan_start_month to "{plan_months[0]}"
4. Set plan_generated_at to "{current_timestamp}"
5. Include the SEBI disclaimer: "{SEBI_DISCLAIMER}"
6. Include educational_notes explaining WHY for each recommendation
7. Set scenario_type to the appropriate value
8. Include confidence_notes listing assumptions and limitations
9. Include assumptions dict with return rates, inflation, SWR used

OUTPUT SIZE: Keep the JSON concise. Fund options are shared once at plan level.

Before returning final JSON, self-check and fix failures:
- It contains "not a SEBI-registered" OR "educational guidance" in disclaimer text.
- Fund recommendations are in fund_options (not repeated per month).
- monthly_plan has exactly 6 entries for months: {plan_months_str}.

Every numerical value must come from the calculator tools — do not invent numbers.""",
        expected_output="A complete FinancialPlan JSON matching the Pydantic schema with fund_options.",
        agent=agents[4],
        context=[task_1, task_2, task_3, task_4],
        output_pydantic=FinancialPlan,
        guardrail=validate_financial_plan,  # Functional guardrail - more reliable than string
    )

    return agents, [task_1, task_2, task_3, task_4, task_5]


def create_planning_crew(
    profile_data: dict,
    cas_data: dict | None = None,
    max_tokens: int | None = None,
    compact_output: bool = False,
) -> Crew:
    """Create and return the configured Planning Crew."""
    agents, tasks = build_planning_tasks(
        profile_data,
        cas_data,
        max_tokens=max_tokens,
        compact_output=compact_output,
    )

    return Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
