# flows/advisor_flow.py
# ─────────────────────────────────────────────────────────────
# CrewAI Flow orchestrating the full advisor lifecycle:
# Onboard → Generate Plan → Store → Chat → (Re-plan if needed)
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crews.planning_crew import create_planning_crew
from crews.chat_crew import create_chat_crew
from models import FinancialPlan, ChatResponse

logger = logging.getLogger(__name__)


async def generate_plan(
    profile_data: dict,
    cas_data: dict | None = None,
    db_collection=None,
    user_id: str | None = None,
) -> FinancialPlan:
    """
    Run the Planning Crew to generate a full financial plan.

    Args:
        profile_data: User's financial profile dict
        cas_data: Parsed CAS PDF data (optional)
        db_collection: MongoDB plans collection (optional, for persistence)
        user_id: User's MongoDB _id string (for linking plan to user)

    Returns:
        FinancialPlan Pydantic model
    """
    crew = create_planning_crew(profile_data, cas_data)
    # Use kickoff_async() since we're already in an async context (FastAPI/uvicorn)
    # This avoids "asyncio.run() cannot be called from a running event loop" error
    # that occurs when guardrails try to validate using async operations
    result = await crew.kickoff_async()

    # Extract the Pydantic output - handle both pydantic attribute and raw JSON parsing
    plan: FinancialPlan | None = None
    
    # Try pydantic attribute first (preferred)
    if hasattr(result, 'pydantic') and result.pydantic is not None:
        plan = result.pydantic
        logger.info("Plan extracted from result.pydantic")
    else:
        # Fallback: parse from raw output (JSON string)
        raw_output = result.raw if hasattr(result, 'raw') else str(result)
        logger.info(f"result.pydantic is None, parsing from raw output (len={len(raw_output)})")
        try:
            # Parse JSON and validate with Pydantic
            plan_data = json.loads(raw_output)
            plan = FinancialPlan.model_validate(plan_data)
            logger.info("Plan successfully parsed from raw JSON output")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {e}")
            raise ValueError(f"Invalid plan JSON from crew: {e}")
        except Exception as e:
            logger.error(f"Failed to validate plan data: {e}")
            raise ValueError(f"Plan validation failed: {e}")
    
    if plan is None:
        raise ValueError("Failed to extract FinancialPlan from crew result")

    # Persist to MongoDB if collection provided
    if db_collection is not None and user_id:
        # Get current version
        from bson import ObjectId
        latest = await db_collection.find_one(
            {"user_id": ObjectId(user_id)},
            sort=[("version", -1)]
        )
        version = (latest["version"] + 1) if latest else 1

        # Extract token usage safely - token_usage is a UsageMetrics object, not a dict
        token_usage_value = 0
        if hasattr(result, "token_usage") and result.token_usage is not None:
            usage = result.token_usage
            # UsageMetrics has attributes like total_tokens, not dict methods
            token_usage_value = getattr(usage, "total_tokens", 0) or 0
        
        plan_doc = {
            "user_id": ObjectId(user_id),
            "created_at": datetime.now(timezone.utc),
            "version": version,
            "trigger": "onboarding" if version == 1 else "chat_replan",
            "plan": plan.model_dump(),
            "token_usage": {
                "total_tokens": token_usage_value
            },
        }
        await db_collection.insert_one(plan_doc)
        logger.info(f"Plan saved to MongoDB: user_id={user_id}, version={version}")

    return plan


async def handle_chat(
    user_id: str,
    message: str,
    profile_data: dict,
    chat_history: list[dict] | None = None,
    chat_collection=None,
) -> ChatResponse:
    """
    Run the Chat Crew to handle a user message.

    Args:
        user_id: User's MongoDB _id string
        message: The user's chat message
        profile_data: Current user profile dict
        chat_history: Previous messages
        chat_collection: MongoDB chat_history collection (for persistence)

    Returns:
        ChatResponse with reply, needs_replan flag, and profile_updates
    """
    crew = create_chat_crew(user_id, message, profile_data, chat_history)
    # Use kickoff_async() since we're already in an async context (FastAPI/uvicorn)
    result = await crew.kickoff_async()

    # Extract the Pydantic output - handle both pydantic attribute and raw JSON parsing
    chat_response: ChatResponse | None = None
    
    # Try pydantic attribute first (preferred)
    if hasattr(result, 'pydantic') and result.pydantic is not None:
        chat_response = result.pydantic
        logger.info("ChatResponse extracted from result.pydantic")
    else:
        # Fallback: parse from raw output (JSON string)
        raw_output = result.raw if hasattr(result, 'raw') else str(result)
        logger.info(f"result.pydantic is None, parsing ChatResponse from raw output")
        try:
            response_data = json.loads(raw_output)
            chat_response = ChatResponse.model_validate(response_data)
            logger.info("ChatResponse successfully parsed from raw JSON output")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse chat response JSON: {e}")
            raise ValueError(f"Invalid chat response JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to validate chat response: {e}")
            raise ValueError(f"Chat response validation failed: {e}")
    
    if chat_response is None:
        raise ValueError("Failed to extract ChatResponse from crew result")

    # Persist messages to MongoDB if collection provided
    if chat_collection is not None:
        from bson import ObjectId
        timestamp = datetime.now(timezone.utc).isoformat()

        await chat_collection.update_one(
            {"user_id": ObjectId(user_id)},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {
                                "role": "user",
                                "content": message,
                                "timestamp": timestamp,
                            },
                            {
                                "role": "assistant",
                                "content": chat_response.reply,
                                "timestamp": timestamp,
                                "triggered_replan": chat_response.needs_replan,
                            },
                        ]
                    }
                },
                "$setOnInsert": {
                    "user_id": ObjectId(user_id),
                    "created_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

    return chat_response
