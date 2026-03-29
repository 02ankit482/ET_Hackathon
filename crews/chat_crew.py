# crews/chat_crew.py
# ─────────────────────────────────────────────────────────────
# Chat Crew: single conversational agent for user interaction.
# Uses Gemini Flash for speed (financial reasoning deferred to
# the Planning Crew which uses GPT-4o-mini).
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from crewai import Agent, Task, Crew, Process, LLM

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CHAT_LLM,
    OPENROUTER_API_KEY,
    OPENAI_API_BASE,
    CHAT_MAX_TOKENS_DEFAULT,
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


def create_chat_crew(
    user_id: str,
    message: str,
    profile_data: dict,
    chat_history: list[dict] | None = None,
    max_tokens: int | None = None,
) -> Crew:
    """
    Create a lightweight Chat Crew for handling user messages.

    Args:
        user_id: MongoDB user ID
        message: The user's chat message
        profile_data: Current user profile dict
        chat_history: Previous messages [{role, content}, ...]

    Returns:
        Configured Crew ready to kickoff
    """
    history_str = ""
    if chat_history:
        for msg in chat_history[-10:]:  # Last 10 messages for context
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_str += f"{role.upper()}: {content}\n"

    profile_str = json.dumps(profile_data, indent=2)
    llm_max_tokens = max_tokens if max_tokens is not None else CHAT_MAX_TOKENS_DEFAULT
    chat_llm = LLM(
        model=CHAT_LLM,
        base_url=OPENAI_API_BASE,
        api_key=OPENROUTER_API_KEY,
        temperature=0.7,
        max_tokens=llm_max_tokens,
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

    return Crew(
        agents=[advisor_agent],
        tasks=[chat_task],
        process=Process.sequential,
        verbose=True,
    )
