# crews/planning_crew.py
# ─────────────────────────────────────────────────────────────
# Planning Crew: 5 sequential agents for financial plan generation.
# Uses DeepSeek for all agents (accuracy > latency).
#
# TOKEN OPTIMIZATION:
# - Deterministic metrics pre-computed in Python (not LLM tools)
# - Fund data cached at startup
# - Compressed context between agents
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

# Pre-computation module (eliminates need for many tool calls)
from crews.precompute import (
    compute_metrics,
    compute_tax_comparison,
    get_cached_fund_recommendations,
    format_metrics_for_prompt,
    format_tax_for_prompt,
    PrecomputedMetrics,
)

# Import tools (reduced set - most calculations now pre-computed)
from tools.financial_calculator import (
    AssetAllocationTool,
    RetirementCorpusTool,
    SIPRequiredTool,
    MutualFundRecommenderTool,
    AllFundRecommendationsTool,
)
from tools.tax_calculator import TaxCalculatorTool
from tools.rag_tool import FinanceRAGTool
from tools.portfolio_overlap import PortfolioOverlapTool


# ── Shared Tool Instances ─────────────────────────────────────
# Only tools that need LLM reasoning (not deterministic calculations)
allocation_tool = AssetAllocationTool()
corpus_tool = RetirementCorpusTool()
sip_tool = SIPRequiredTool()

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
    """
    Data Analyst agent - now uses pre-computed metrics.
    Only needs RAG tool for validation insights, not calculation tools.
    """
    return Agent(
        role="Certified Financial Data Analyst",
        goal=(
            "Validate the pre-computed financial metrics and provide insights. "
            "Review the monthly surplus, debt-to-income ratio, savings rate, net worth, "
            "and emergency fund adequacy. Flag any concerns based on the profile."
        ),
        backstory=(
            "You are a meticulous financial data analyst. The calculations have already "
            "been done for you — your job is to validate them against the user's profile "
            "and provide insights. Check for inconsistencies like expenses > income. "
            "Use the RAG tool only if you need additional financial planning context."
        ),
        tools=[rag_tool],  # Reduced from 6 tools - calculations pre-computed
        llm=planning_llm,
        verbose=True,
    )


def _agent_2_tax_insurance_specialist(planning_llm: LLM) -> Agent:
    """
    Tax & Insurance agent - now uses pre-computed tax comparison.
    Focuses on recommendations, not calculations.
    """
    return Agent(
        role="Indian Tax and Insurance Specialist (FY 2025-26)",
        goal=(
            "Review the pre-computed tax comparison and insurance gap analysis. "
            "Provide recommendations on tax regime choice and insurance coverage. "
            "Identify tax-saving investment opportunities within limits."
        ),
        backstory=(
            "You are a dual-domain specialist in Indian taxation and insurance. "
            "The tax calculations (both regimes) and insurance gaps have been pre-computed. "
            "Your job is to interpret the results and provide actionable recommendations. "
            "You never estimate numbers - use the pre-computed values. You recommend "
            "coverage amounts and category-level actions, NOT specific products."
        ),
        tools=[rag_tool],  # Reduced from 3 tools - calculations pre-computed
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

    TOKEN OPTIMIZATION:
    - Pre-compute deterministic metrics in Python (not via LLM tools)
    - Cache fund recommendations
    - Pass compressed summaries between agents

    Args:
        profile_data: User's financial profile dict
        cas_data: Parsed CAS mutual fund data (optional)

    Returns:
        (agents_list, tasks_list) ready to be passed to Crew
    """
    # ══════════════════════════════════════════════════════════════
    # PRE-COMPUTATION: Run all deterministic calculations in Python
    # This eliminates 5-6 tool calls per request, saving ~20-30% tokens
    # ══════════════════════════════════════════════════════════════
    precomputed_metrics = compute_metrics(profile_data)
    precomputed_tax = compute_tax_comparison(profile_data)
    cached_funds = get_cached_fund_recommendations(top_n=5 if not compact_output else 3)
    
    # Format for prompt injection (much smaller than full profile)
    metrics_prompt = format_metrics_for_prompt(precomputed_metrics)
    tax_prompt = format_tax_for_prompt(precomputed_tax)
    
    # Compact profile (only fields needed for context, not calculations)
    compact_profile = {
        "name": profile_data.get("name"),
        "age": profile_data.get("age"),
        "city": profile_data.get("city"),
        "primary_goal": profile_data.get("primary_goal"),
        "risk_appetite": profile_data.get("risk_appetite"),
        "is_metro_city": profile_data.get("is_metro_city"),
        "dependents": profile_data.get("dependents"),
    }
    compact_profile_str = _compact_json_for_prompt(compact_profile, max_chars=500)
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

    # ── Task 1: Data Analysis (uses pre-computed metrics) ─────
    task_1 = Task(
        description=f"""Review and validate the pre-computed financial metrics for the user.

USER PROFILE:
{compact_profile_str}

{metrics_prompt}

Your job is to:
1. Review the pre-computed metrics above (already calculated)
2. Flag any concerns (e.g., if savings rate is too low, emergency fund gap is large)
3. Provide insights based on the user's age, goals, and risk appetite
4. Suggest priority areas that need attention

DO NOT recalculate these values — they are verified. Focus on ANALYSIS and INSIGHTS.

Output a brief validated financial snapshot with key insights.""",
        expected_output=(
            "A validated financial snapshot with key insights: surplus assessment, "
            "DTI concerns, emergency fund priority, and action recommendations."
        ),
        agent=agents[0],
    )

    # ── Task 2: Tax + Insurance Analysis (uses pre-computed) ──
    task_2 = Task(
        description=f"""Review the pre-computed tax comparison and insurance gap analysis.

USER PROFILE:
{compact_profile_str}

{tax_prompt}

INSURANCE GAPS (pre-computed):
Term Insurance: Recommended ₹{precomputed_metrics.term_insurance_recommended:,.0f}, Gap ₹{precomputed_metrics.term_insurance_gap:,.0f}
Health Insurance: Recommended ₹{precomputed_metrics.health_insurance_recommended:,.0f}, Gap ₹{precomputed_metrics.health_insurance_gap:,.0f}
Dependents: {profile_data.get('dependents', 0)}
City: {profile_data.get('city', 'India')} ({"Metro" if profile_data.get('is_metro_city', True) else "Non-metro"})

Your job is to:
1. Explain WHY the recommended tax regime is better
2. List tax-saving investment CATEGORIES the user should consider (not specific products)
3. Prioritize insurance gaps (term > health typically)
4. Provide specific coverage amount recommendations

DO NOT recalculate — use the pre-computed values above.""",
        expected_output=(
            "Tax regime recommendation with explanation, tax-saving opportunities, "
            "and prioritized insurance coverage recommendations."
        ),
        agent=agents[1],
        context=[task_1],
    )

    # ── Task 3: Investment Strategy (uses pre-computed + cached funds) ───
    cas_instruction = ""
    if cas_data:
        cas_instruction = f"""
The user has provided CAS (Consolidated Account Statement) data:
{cas_summary_str}

IMPORTANT: Run the portfolio_overlap_detector tool with the funds from CAS data.
Pass the funds as a JSON string in the funds_json parameter.
Provide consolidation advice if overlap > 25%."""

    # Format cached fund data for the prompt (no need for tool call)
    fund_summary = f"""
CACHED FUND RECOMMENDATIONS (pre-loaded, no tool call needed):
Large Cap: {len(cached_funds.get('large_cap', []))} options available
Mid Cap: {len(cached_funds.get('mid_cap', []))} options available
Small Cap: {len(cached_funds.get('small_cap', []))} options available
Debt: {len(cached_funds.get('debt', []))} options available
Gold: {len(cached_funds.get('gold', []))} options available
"""
    
    task_3 = Task(
        description=f"""Design the investment strategy and month-by-month SIP schedule.

PLAN MONTHS: {plan_months_str}
(Generate plan for exactly these 6 months - next 2 quarters starting from next month)

USER PROFILE:
{compact_profile_str}

PRE-COMPUTED VALUES (use these directly, do not recalculate):
- Target Corpus: Rs {precomputed_metrics.corpus_needed:,.0f}
- Monthly SIP Required: Rs {precomputed_metrics.monthly_sip_required:,.0f}
- Asset Allocation: Equity {precomputed_metrics.equity_pct}%, Debt {precomputed_metrics.debt_pct}%, Gold {precomputed_metrics.gold_pct}%
- Years to Retire: {precomputed_metrics.years_to_retire}

{fund_summary}
{cas_instruction}

Create a month-by-month SIP allocation table for exactly 6 months: {plan_months_str}
Split the monthly SIP of Rs {precomputed_metrics.monthly_sip_required:,.0f} across:
- Large Cap: {precomputed_metrics.equity_pct * 0.4:.0f}% of equity allocation
- Mid Cap: {precomputed_metrics.equity_pct * 0.25:.0f}% of equity allocation  
- Small Cap: {precomputed_metrics.equity_pct * 0.14:.0f}% of equity allocation
- Debt: {precomputed_metrics.debt_pct}%
- Gold: {precomputed_metrics.gold_pct}%
- PPF: Max Rs 12,500/month (Rs 1,50,000/year limit)
- NPS: Max Rs 4,167/month (Rs 50,000/year limit under 80CCD(1B))

CRITICAL RULES:
- PPF contribution MUST NOT exceed Rs 12,500/month (Rs 1,50,000/year limit)
- NPS 80CCD(1B) MUST NOT exceed Rs 50,000/year
- Fund options are EDUCATIONAL - include disclaimer about past performance""",
        expected_output=(
            "Complete investment strategy: monthly SIP breakdown by category, "
            "6-month SIP schedule with PPF/NPS contributions, "
            "and portfolio overlap analysis if CAS data was available."
        ),
        agent=agents[2],
        context=[task_1, task_2],
    )

    # ── Task 4: Compliance Review ─────────────────────────────
    task_4 = Task(
        description=f"""Review ALL previous agent outputs for regulatory compliance.

Check each of the following:
1. Fund recommendations are presented as EDUCATIONAL OPTIONS with historical data
   - Verify they include disclaimers about past performance
2. Are PPF contributions exceeding Rs 1.5L/year or NPS exceeding Rs 50K/year?
   - If yes, flag for correction.
3. Do tax calculations use correct FY 2025-26 slabs?
4. Does the plan include the SEBI disclaimer? The required text is:
   "{SEBI_DISCLAIMER}"
5. Does every recommendation explain WHY (educational value)?

If ANY violations are found, clearly list corrections needed.
If all checks pass, confirm compliance and output the disclaimer text.""",
        expected_output=(
            "Compliance review: PASS/FAIL with specific violations listed, "
            "corrections needed, and the mandatory SEBI disclaimer text."
        ),
        agent=agents[3],
        context=[task_1, task_2, task_3],
    )

    # ── Task 5: Plan Synthesis (uses cached funds) ────────────
    # Format fund options for direct inclusion (no tool call needed)
    fund_options_json = json.dumps(cached_funds, indent=2, default=str)
    
    task_5 = Task(
        description=f"""Synthesize ALL previous agent outputs into a single FinancialPlan JSON.

PLAN MONTHS: {plan_months_str}
CURRENT TIMESTAMP: {current_timestamp}

PRE-COMPUTED VALUES TO USE:
- Target Corpus: {precomputed_metrics.corpus_needed}
- Monthly SIP Total: {precomputed_metrics.monthly_sip_required}
- Asset Allocation: Equity {precomputed_metrics.equity_pct}%, Debt {precomputed_metrics.debt_pct}%, Gold {precomputed_metrics.gold_pct}%

TAX COMPARISON:
- Old Regime Tax: {precomputed_tax['old_regime_tax']}
- New Regime Tax: {precomputed_tax['new_regime_tax']}
- Recommended: {precomputed_tax['recommended_regime']}
- Savings: {precomputed_tax['savings_amount']}

INSURANCE GAPS:
- Term: Recommended {precomputed_metrics.term_insurance_recommended}, Gap {precomputed_metrics.term_insurance_gap}
- Health: Recommended {precomputed_metrics.health_insurance_recommended}, Gap {precomputed_metrics.health_insurance_gap}

CACHED FUND OPTIONS (use these directly, DO NOT call get_all_fund_recommendations):
{fund_options_json}

Combine insights from:
- Financial snapshot from Agent 1
- Tax + insurance recommendations from Agent 2
- Investment strategy + monthly SIP schedule from Agent 3
- Compliance review from Agent 4

The output MUST follow the FinancialPlan schema exactly.

CRITICAL REQUIREMENTS:
1. Include exactly 6 MonthlyPlanEntry items for months: {plan_months_str}
2. Use the CACHED FUND OPTIONS above for fund_options (top 3 per category)
3. Set plan_start_month to "{plan_months[0]}"
4. Set plan_generated_at to "{current_timestamp}"
5. Include the SEBI disclaimer
6. Include educational_notes explaining WHY for each recommendation
7. Set scenario_type to "custom"
8. Include confidence_notes listing assumptions and limitations
9. Include assumptions dict with return rates, inflation, SWR used

OUTPUT: Return valid JSON matching FinancialPlan schema. No markdown code blocks.""",
        expected_output="A complete FinancialPlan JSON matching the Pydantic schema with fund_options.",
        agent=agents[4],
        context=[task_1, task_2, task_3, task_4],
        output_pydantic=FinancialPlan,
        guardrail=validate_financial_plan,
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
