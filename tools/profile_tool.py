# tools/profile_tool.py
# ─────────────────────────────────────────────────────────────
# Tools for reading and updating user profile from/to MongoDB.
# Used by the Chat Crew agent to detect and apply profile changes.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from typing import Type, Dict, Any
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ProfileReadInput(BaseModel):
    user_id: str = Field(description="The MongoDB user _id to read profile for")


class ProfileUpdateInput(BaseModel):
    user_id: str = Field(description="The MongoDB user _id to update")
    updates: Dict[str, Any] = Field(
        description=(
            "Dict of profile fields to update, e.g. "
            "{'target_retirement_age': 55, 'risk_appetite': 'aggressive'}"
        )
    )


class ProfileReadTool(BaseTool):
    name: str = "read_user_profile"
    description: str = """Read the current user financial profile from the database.
Returns all profile fields including: demographics, income, expenses, 
existing investments, goals, insurance, and risk preferences.
Use this to understand the user's current financial situation before answering questions."""
    args_schema: Type[BaseModel] = ProfileReadInput

    _db_getter: object = None

    def _run(self, user_id: str) -> str:
        try:
            # We import here to avoid circular deps at module load
            import asyncio
            from database import get_collection, USERS_COLLECTION

            async def _read():
                coll = get_collection(USERS_COLLECTION)
                from bson import ObjectId
                user = await coll.find_one({"_id": ObjectId(user_id)})
                if not user:
                    return {"error": f"User {user_id} not found"}
                profile = user.get("profile", {})
                profile["user_id"] = str(user["_id"])
                profile["onboarding_completed"] = user.get("onboarding_completed", False)
                return profile

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, _read()).result()
            else:
                result = asyncio.run(_read())

            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})


class ProfileUpdateTool(BaseTool):
    name: str = "update_user_profile"
    description: str = """Update specific fields in the user's financial profile.
Use this when the user's chat message implies a change to their profile,
e.g. "What if I retire at 55?" → update target_retirement_age to 55.

Valid fields: name, age, city, dependents, annual_income, monthly_expenses,
home_loan_emi, car_loan_emi, other_emi, existing_mf, existing_ppf, 
existing_nps, existing_epf, existing_fd, existing_savings, current_sip,
primary_goal, target_retirement_age, target_monthly_draw, risk_appetite,
investment_horizon_years, has_term_insurance, term_cover_amount,
has_health_insurance, health_cover_amount"""
    args_schema: Type[BaseModel] = ProfileUpdateInput

    def _run(self, user_id: str, updates: dict) -> str:
        try:
            if isinstance(updates, str):
                updates = json.loads(updates)

            import asyncio
            from database import get_collection, USERS_COLLECTION

            async def _update():
                coll = get_collection(USERS_COLLECTION)
                from bson import ObjectId

                # Prefix all keys with "profile."
                update_dict = {f"profile.{k}": v for k, v in updates.items()}

                result = await coll.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": update_dict}
                )

                if result.modified_count > 0:
                    return {
                        "status": "updated",
                        "fields_changed": list(updates.keys()),
                        "new_values": updates,
                    }
                else:
                    return {"status": "no_change", "reason": "User not found or values unchanged"}

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, _update()).result()
            else:
                result = asyncio.run(_update())

            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
