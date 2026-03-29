# crews/chat_crew.py
# ─────────────────────────────────────────────────────────────
# Chat Crew: single conversational agent for user interaction.
# Uses DeepSeek for speed (financial reasoning deferred to
# the Planning Crew).
#
# TOKEN OPTIMIZATION:
# - Route simple queries to direct RAG (no agent needed)
# - Only use full agent for profile updates / complex queries
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import re
from crewai import Agent, Task, Crew, Process, LLM

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CHAT_LLM,
    OPENROUTER_API_KEY,
    OPENAI_API_BASE,
    CHAT_MAX_TOKENS_DEFAULT,
    SEBI_DISCLAIMER,
)
from models import ChatResponse
from tools.financial_calculator import FinancialCalculatorTool
from tools.rag_tool import FinanceRAGTool
from tools.profile_tool import ProfileReadTool, ProfileUpdateTool


# ── Shared Tool Instances ─────────────────────────────────────
calc_tool = FinancialCalculatorTool()
rag_tool = FinanceRAGTool()
profile_read = ProfileReadTool()
profile_update = ProfileUpdateTool()


# ── Query Type Classification ─────────────────────────────────
class QueryType:
    """Classify chat queries for routing."""
    SIMPLE_QA = "simple_qa"          # Direct RAG lookup, no agent needed
    PROFILE_UPDATE = "profile_update" # Needs agent to update profile
    REPLAN_REQUEST = "replan"         # User wants plan regeneration
    COMPLEX = "complex"               # Needs full agent reasoning


def classify_query(message: str) -> QueryType:
    """
    Classify the user's message to route to optimal handler.
    
    This saves ~50% tokens for simple Q&A queries by skipping the agent.
    """
    msg_lower = message.lower().strip()
    
    # Check for replan requests
    replan_patterns = [
        r'\b(regenerate|replan|refresh|recreate|update)\b.*\b(plan|financial plan)\b',
        r'\bplan\b.*\b(regenerate|refresh|update)\b',
    ]
    for pattern in replan_patterns:
        if re.search(pattern, msg_lower):
            return QueryType.REPLAN_REQUEST
    
    # Check for profile changes (income, age, expenses, goals, etc.)
    profile_change_patterns = [
        r'\b(i got|i have|my new|changed to|now earning|raise to|increased to)\b',
        r'\b(retire at|retirement age)\b.*\d+',
        r'\b(income|salary|ctc)\b.*\d+',
        r'\b(monthly expenses?|spending)\b.*\d+',
        r'\bwhat if\b.*\b(i|my)\b',  # What-if scenarios
    ]
    for pattern in profile_change_patterns:
        if re.search(pattern, msg_lower):
            return QueryType.PROFILE_UPDATE
    
    # Check for simple Q&A (just needs information lookup)
    simple_qa_patterns = [
        r'^(what is|what are|how does|how do|explain|tell me about|define)\b',
        r'\b(difference between|meaning of|types of)\b',
        r'\b(ppf|nps|elss|mutual fund|sip|fd|epf)\b.*(what|how|explain|rate)',
        r'^(should i|is it|can i)\b',  # Yes/no questions
    ]
    for pattern in simple_qa_patterns:
        if re.search(pattern, msg_lower):
            return QueryType.SIMPLE_QA
    
    # Default to complex for anything else
    return QueryType.COMPLEX


def handle_simple_qa(message: str, profile_data: dict) -> ChatResponse:
    """
    Handle simple Q&A without invoking the full agent.
    
    Uses direct RAG lookup - saves ~50% tokens vs full agent.
    """
    # Direct RAG search
    context = rag_tool._run(query=message)
    
    # Build a simple response (this could also use a lightweight LLM call)
    # For now, return the RAG context with formatting
    reply = f"""Based on available financial knowledge:

{context}

---
*Note: This is AI-generated educational guidance, not advice from a SEBI-registered Investment Adviser.*"""
    
    return ChatResponse(
        reply=reply,
        needs_replan=False,
        profile_updates={},
    )


def handle_replan_request(message: str) -> ChatResponse:
    """Handle explicit replan requests without full agent."""
    return ChatResponse(
        reply="I'll regenerate your financial plan with the latest profile data. This may take a moment...",
        needs_replan=True,
        profile_updates={},
    )


def create_chat_crew(
    user_id: str,
    message: str,
    profile_data: dict,
    chat_history: list[dict] | None = None,
    max_tokens: int | None = None,
    event_callback=None,
) -> Crew | ChatResponse:
    """
    Create a lightweight Chat Crew for handling user messages.
    
    TOKEN OPTIMIZATION:
    - Routes simple queries directly (no agent needed)
    - Only uses full CrewAI for complex queries / profile updates

    Args:
        user_id: MongoDB user ID
        message: The user's chat message
        profile_data: Current user profile dict
        chat_history: Previous messages [{role, content}, ...]

    Returns:
        Crew object (for complex queries) OR ChatResponse (for simple queries)
    """
    # ══════════════════════════════════════════════════════════════
    # ROUTING: Classify query and handle simple cases directly
    # This saves ~50% tokens for simple Q&A queries
    # ══════════════════════════════════════════════════════════════
    query_type = classify_query(message)
    
    if query_type == QueryType.REPLAN_REQUEST:
        # No agent needed - just signal replan
        return handle_replan_request(message)
    
    # For simple Q&A, we could bypass the agent entirely
    # But for now, let's use the agent for all queries to maintain quality
    # Uncomment below to enable direct RAG for simple queries:
    # if query_type == QueryType.SIMPLE_QA:
    #     return handle_simple_qa(message, profile_data)
    
    # ══════════════════════════════════════════════════════════════
    # FULL AGENT: For complex queries and profile updates
    # ══════════════════════════════════════════════════════════════
    
    # Compress chat history (only last 5 messages, not 10)
    history_str = ""
    if chat_history:
        for msg in chat_history[-5:]:  # Reduced from 10 to 5
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 200:
                content = content[:200] + "..."
            history_str += f"{role.upper()}: {content}\n"

    # Compact profile (only essential fields for chat)
    compact_profile = {
        "name": profile_data.get("name"),
        "age": profile_data.get("age"),
        "annual_income": profile_data.get("annual_income"),
        "monthly_expenses": profile_data.get("monthly_expenses"),
        "risk_appetite": profile_data.get("risk_appetite"),
        "primary_goal": profile_data.get("primary_goal"),
        "target_retirement_age": profile_data.get("target_retirement_age"),
    }
    profile_str = json.dumps(compact_profile, indent=2)
    
    llm_max_tokens = max_tokens if max_tokens is not None else CHAT_MAX_TOKENS_DEFAULT
    chat_llm = LLM(
        model=CHAT_LLM,
        base_url=OPENAI_API_BASE,
        api_key=OPENROUTER_API_KEY,
        temperature=0.7,
        max_tokens=min(llm_max_tokens, 4000),  # Cap output tokens
    )

    advisor_agent = Agent(
        role="Friendly Financial Educator & Advisor",
        goal=(
            "Answer the user's financial question clearly and helpfully. "
            "If the question implies a change to their financial profile "
            "(e.g., 'What if I retire at 55?', 'I got a raise to 30L'), "
            "detect the change and update their profile using the update_user_profile tool. "
            "For substantive financial questions, use the finance_knowledge_search tool "
            "to cite accurate information. For calculations, use the financial_calculator tool. "
            "Always end with a brief disclaimer for financial advice topics."
        ),
        backstory=(
            "You are an empathetic financial educator who explains complex topics simply. "
            "You know the user's complete financial profile and tailor every answer "
            "to their specific situation. When you detect a profile change in their "
            "message, you update it and flag that a plan regeneration is needed. "
            "You NEVER recommend specific mutual fund schemes, stocks, or ISINs. "
            "You always remind users this is AI-generated educational guidance, not "
            "licensed financial advice from a SEBI-registered Investment Adviser."
        ),
        tools=[calc_tool, rag_tool, profile_read, profile_update],
        llm=chat_llm,
        verbose=True,
    )

    chat_task = Task(
        description=f"""Respond to the user's message in the context of their financial profile.

USER ID: {user_id}
USER PROFILE:
{profile_str}

CHAT HISTORY:
{history_str or "No previous messages."}

CURRENT MESSAGE: {message}

INSTRUCTIONS:
1. If the message implies a PROFILE CHANGE (retirement age, income, expenses, goals, etc.):
    - Use the update_user_profile tool with user_id="{user_id}" and the new values
    - Set needs_replan=true in your response
    - Tell the user their plan will be updated
    
2. If the user explicitly asks to regenerate/replan/refresh/recreate their financial plan
   (even without profile changes), set needs_replan=true.
   - Examples: "regenerate my financial plan", "please replan", "refresh my plan"
   - In this case, keep profile_updates={{}} unless you also detected profile changes.

3. If the message is a FINANCIAL QUESTION:
    - Use finance_knowledge_search to find relevant information
    - Use financial_calculator for any numerical computations
    - Explain clearly, tailored to the user's experience level
    
4. For ALL substantive financial responses:
    - Add a brief disclaimer: "Note: This is AI-generated educational guidance, 
      not advice from a SEBI-registered Investment Adviser."

5. NEVER recommend specific fund names, ISINs, or stock tickers.

Your response must follow the ChatResponse schema:
- reply: Your response text
- needs_replan: true if profile changed OR if user explicitly requests plan regeneration; false otherwise
- profile_updates: dict of fields that changed (empty if no changes)""",
        expected_output=(
            "A ChatResponse with the advisor's reply, needs_replan flag, "
            "and any profile_updates."
        ),
        agent=advisor_agent,
        output_pydantic=ChatResponse,
    )

    # Register step_callback and task_callback instead of generic callbacks
    return Crew(
        agents=[advisor_agent],
        tasks=[chat_task],
        process=Process.sequential,
        verbose=True,
        step_callback=event_callback,
        task_callback=event_callback,
    )
