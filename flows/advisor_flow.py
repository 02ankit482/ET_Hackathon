# flows/advisor_flow.py
# ─────────────────────────────────────────────────────────────
# CrewAI Flow orchestrating the full advisor lifecycle:
# Onboard → Generate Plan → Store → Chat → (Re-plan if needed)
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crews.planning_crew import create_planning_crew
from crews.chat_crew import create_chat_crew
from config import (
    CHAT_MAX_TOKENS_DEFAULT,
    CHAT_RETRY_TOKEN_BUFFER,
    PLANNING_MAX_TOKENS_DEFAULT,
    PLANNING_RETRY_TOKEN_BUFFER,
    PLANNING_RETRY_MAX_TOKENS_ON_TRUNCATION,
)
from models import FinancialPlan, ChatResponse

logger = logging.getLogger(__name__)

_AFFORDABLE_TOKENS_PATTERNS = (
    re.compile(r"can only afford\s+(\d+)", re.IGNORECASE),
    re.compile(r"afford\s+up to\s+(\d+)", re.IGNORECASE),
)


def _extract_json_object(raw_text: str) -> str:
    """Extract a JSON object string from raw LLM output.

    Handles common wrappers:
    - Markdown code fences: ```json ... ```
    - Surrounding prose before/after JSON
    """
    text = raw_text.strip()

    # Strip markdown code fences first if present.
    if text.startswith("```"):
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()

    # Fast path for valid JSON object text.
    if text.startswith("{") and text.endswith("}"):
        return text

    # Fallback: pick the largest object-looking substring.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


def _extract_affordable_max_tokens(error_text: str) -> int | None:
    """Extract provider-reported affordable token cap from OpenRouter credit errors."""
    for pattern in _AFFORDABLE_TOKENS_PATTERNS:
        match = pattern.search(error_text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _is_length_limit_error(error_text: str) -> bool:
    """Check if error indicates token/length limit was exceeded.
    
    Handles:
    - "length limit was reached" - OpenRouter/OpenAI structured output truncation
    - "Could not parse response content as the length limit was reached" - exact error from logs
    - "context length exceeded" - OpenAI context window error
    - "maximum context length" - alternate phrasing
    """
    lowered = error_text.lower()
    return (
        "length limit was reached" in lowered
        or "could not parse response content" in lowered
        or "context length exceeded" in lowered
        or "maximum context length" in lowered
        or "completion_tokens" in lowered and "finish_reason" in lowered
    )


async def generate_plan(
    profile_data: dict,
    cas_data: dict | None = None,
    db_collection=None,
    user_id: str | None = None,
    event_callback=None,
) -> FinancialPlan:
    """
    Run the Planning Crew to generate a full financial plan.

    Args:
        profile_data: User's financial profile dict
        cas_data: Parsed CAS PDF data (optional)
        db_collection: MongoDB plans collection (optional, for persistence)
        user_id: User's MongoDB _id string (for linking plan to user)
        event_callback: Optional callback for capturing crew events (for SSE streaming)

    Returns:
        FinancialPlan Pydantic model
    """
    requested_max_tokens = PLANNING_MAX_TOKENS_DEFAULT
    current_max_tokens = requested_max_tokens
    compact_output = False
    result = None

    # Retry mechanism: up to 5 attempts with progressive token reduction
    # This handles both "length limit" errors and OpenRouter credit limit errors
    for attempt in range(5):  # Increased from 3 to 5 for better resilience
        try:
            crew = create_planning_crew(
                profile_data,
                cas_data,
                max_tokens=current_max_tokens,
                compact_output=compact_output,
                event_callback=event_callback,
            )
            result = await crew.kickoff_async()
            break
        except Exception as exc:
            if attempt == 4:  # Last attempt (0,1,2,3,4)
                raise

            error_text = str(exc)
            affordable_tokens = _extract_affordable_max_tokens(error_text)
            next_max_tokens = current_max_tokens
            next_compact_output = compact_output

            if affordable_tokens is not None:
                # OpenRouter credit limit: be aggressive with reduction
                # Use a larger buffer to ensure we stay under the limit
                buffer = max(PLANNING_RETRY_TOKEN_BUFFER, int(affordable_tokens * 0.05))  # 5% buffer
                next_max_tokens = max(512, affordable_tokens - buffer)
                next_compact_output = True
            elif _is_length_limit_error(error_text):
                if not compact_output:
                    next_compact_output = True
                    next_max_tokens = min(current_max_tokens, PLANNING_RETRY_MAX_TOKENS_ON_TRUNCATION)
                else:
                    # More aggressive reduction on subsequent retries
                    reduction = 2048 if attempt < 2 else 1024
                    next_max_tokens = max(1024, current_max_tokens - reduction)
            else:
                raise

            if (
                next_max_tokens >= current_max_tokens
                and next_compact_output == compact_output
            ):
                raise

            logger.warning(
                "Planning crew failed on attempt %s (max_tokens=%s, compact_output=%s). "
                "Retrying with max_tokens=%s, compact_output=%s. Error excerpt: %s",
                attempt + 1,
                current_max_tokens,
                compact_output,
                next_max_tokens,
                next_compact_output,
                error_text[:240],
            )
            current_max_tokens = next_max_tokens
            compact_output = next_compact_output

    if result is None:
        raise ValueError("Planning crew did not return a result")

    # Extract the Pydantic output - handle both pydantic attribute and raw JSON parsing
    plan: FinancialPlan | None = None
    
    # Try pydantic attribute first (preferred)
    if hasattr(result, 'pydantic') and result.pydantic is not None:
        plan = result.pydantic
        logger.info("Plan extracted from result.pydantic")
    else:
        # Fallback: parse from raw output (JSON string)
        raw_output = result.raw if hasattr(result, 'raw') else str(result)
        normalized_output = _extract_json_object(raw_output)
        logger.info(
            "result.pydantic is None, parsing from raw output (len=%s, normalized_len=%s)",
            len(raw_output),
            len(normalized_output),
        )
        try:
            # Parse JSON and validate with Pydantic
            plan_data = json.loads(normalized_output)
            plan = FinancialPlan.model_validate(plan_data)
            logger.info("Plan successfully parsed from raw JSON output")
        except json.JSONDecodeError as e:
            logger.error("Failed to parse plan JSON after normalization: %s", e)
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
    event_callback=None,
) -> ChatResponse:
    """
    Run the Chat Crew to handle a user message.

    Args:
        user_id: User's MongoDB _id string
        message: The user's chat message
        profile_data: Current user profile dict
        chat_history: Previous messages
        chat_collection: MongoDB chat_history collection (for persistence)
        event_callback: Optional callback for capturing crew events (for SSE streaming)

    Returns:
        ChatResponse with reply, needs_replan flag, and profile_updates
    """
    requested_max_tokens = CHAT_MAX_TOKENS_DEFAULT
    crew_or_response = create_chat_crew(
        user_id,
        message,
        profile_data,
        chat_history,
        max_tokens=requested_max_tokens,
        event_callback=event_callback,
    )

    # Fast path: routing may return a direct ChatResponse (e.g., explicit replan requests)
    if isinstance(crew_or_response, ChatResponse):
        chat_response = crew_or_response
        result = None
    else:
        crew = crew_or_response
        # Use kickoff_async() since we're already in an async context (FastAPI/uvicorn)
        try:
            result = await crew.kickoff_async()
        except Exception as exc:
            error_text = str(exc)
            affordable_tokens = _extract_affordable_max_tokens(error_text)
            if affordable_tokens is None:
                raise

            retry_max_tokens = max(256, affordable_tokens - CHAT_RETRY_TOKEN_BUFFER)
            if retry_max_tokens >= requested_max_tokens:
                raise

            logger.warning(
                "Chat hit OpenRouter credit/token limit (requested=%s, affordable=%s). "
                "Retrying once with max_tokens=%s.",
                requested_max_tokens,
                affordable_tokens,
                retry_max_tokens,
            )
            retry_crew_or_response = create_chat_crew(
                user_id,
                message,
                profile_data,
                chat_history,
                max_tokens=retry_max_tokens,
                event_callback=event_callback,
            )
            if isinstance(retry_crew_or_response, ChatResponse):
                chat_response = retry_crew_or_response
                result = None
            else:
                result = await retry_crew_or_response.kickoff_async()

    # Extract the Pydantic output - handle both pydantic attribute and raw JSON parsing
    if 'chat_response' not in locals():
        chat_response = None
    
    # Try pydantic attribute first (preferred)
    if hasattr(result, 'pydantic') and result.pydantic is not None:
        chat_response = result.pydantic
        logger.info("ChatResponse extracted from result.pydantic")
    else:
        # Fallback: parse from raw output (JSON string)
        raw_output = result.raw if hasattr(result, 'raw') else str(result)
        normalized_output = _extract_json_object(raw_output)
        logger.info(f"result.pydantic is None, parsing ChatResponse from raw output")
        try:
            response_data = json.loads(normalized_output)
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
