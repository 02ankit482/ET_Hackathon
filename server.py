# server.py
# ─────────────────────────────────────────────────────────────
# FastAPI server for the Everything Money Financial Advisor.
# Endpoints: onboarding, plan generation, chat, CAS parsing.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import os
import json
import tempfile
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import BASE_DIR, SEBI_DISCLAIMER
from database import (
    connect_to_db, close_db_connection, get_collection,
    USERS_COLLECTION, PLANS_COLLECTION, CHAT_COLLECTION,
)
from models import OnboardingRequest, ChatRequest, FinancialPlan, ChatResponse, InitUserRequest
from flows.advisor_flow import generate_plan, handle_chat
from cas_parser import parse_cas_pdf, extract_mf_summary


# ── App Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MongoDB connection lifecycle."""
    await connect_to_db()
    yield
    await close_db_connection()


app = FastAPI(
    title="Everything Money — Financial Advisor API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Everything Money Financial Advisor",
        "version": "2.0.0",
        "endpoints": [
            "POST /api/session/new",
            "POST /api/parse-cas",
            "POST /api/plan/generate",
            "POST /api/plan/regenerate",
            "GET  /api/plan/{user_id}",
            "POST /api/chat",
            "GET  /api/chat/history/{user_id}",
            "GET  /api/profile/{user_id}",
            "PUT  /api/profile/{user_id}",
        ],
    }


# ── Session / Onboarding ─────────────────────────────────────

@app.post("/api/session/new")
async def create_session(req: OnboardingRequest):
    """Create a new user with their onboarding profile."""
    users = get_collection(USERS_COLLECTION)

    # Extract setu_data and cas_data from request
    setu_data = req.setu_data
    cas_data = req.cas_data
    
    # Profile excludes clerk_user_id and the data source fields
    profile = req.model_dump(exclude={"clerk_user_id", "setu_data", "cas_data", "asset_tab"})

    # Check if user already exists (by clerk_user_id)
    existing = await users.find_one({"clerk_user_id": req.clerk_user_id})
    if existing:
        # Update profile instead of creating new
        update_data = {
            "profile": profile,
            "onboarding_completed": True,
            "updated_at": datetime.now(timezone.utc),
        }
        if setu_data:
            update_data["setu_data"] = setu_data
        if cas_data:
            update_data["cas_data"] = cas_data
            
        await users.update_one(
            {"clerk_user_id": req.clerk_user_id},
            {"$set": update_data},
        )
        return {
            "status": "updated",
            "user_id": str(existing["_id"]),
            "message": "Profile updated successfully",
        }

    # Create new user
    user_doc = {
        "clerk_user_id": req.clerk_user_id,
        "created_at": datetime.now(timezone.utc),
        "onboarding_completed": True,
        "profile": profile,
        "cas_data": cas_data,
        "setu_data": setu_data,
    }
    result = await users.insert_one(user_doc)

    return {
        "status": "created",
        "user_id": str(result.inserted_id),
        "message": "User profile created. Ready for plan generation.",
    }


# ── CAS PDF Parsing ──────────────────────────────────────────

@app.post("/api/parse-cas")
async def parse_cas(
    file: UploadFile = File(...),
    password: str = Form(""),
    user_id: str = Form(""),
):
    """Upload and parse a CAMS/KFintech CAS PDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file")

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Parse the CAS PDF
        cas_data = parse_cas_pdf(tmp_path, password)
        summary = extract_mf_summary(cas_data)

        # Persist to user profile if user_id provided
        if user_id:
            from bson import ObjectId
            users = get_collection(USERS_COLLECTION)
            await users.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "cas_data": summary,
                        "profile.existing_mf": summary["total_mf_value"],
                    }
                },
            )

        return {
            "success": True,
            "message": f"Parsed {summary['fund_count']} mutual fund schemes",
            "data": summary,
        }
    except Exception as e:
        raise HTTPException(400, f"Failed to parse CAS: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ── Plan Generation ───────────────────────────────────────────

@app.post("/api/plan/generate")
async def generate_plan_endpoint(user_id: str = Form(...)):
    """Generate a financial plan for the user."""
    from bson import ObjectId

    users = get_collection(USERS_COLLECTION)
    user = await users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(404, "User not found")

    profile_data = user.get("profile", {})
    cas_data = user.get("cas_data")
    plans_collection = get_collection(PLANS_COLLECTION)

    try:
        plan = await generate_plan(
            profile_data=profile_data,
            cas_data=cas_data,
            db_collection=plans_collection,
            user_id=user_id,
        )
        return {
            "success": True,
            "message": "Financial plan generated successfully",
            "plan": plan.model_dump(),
        }
    except Exception as e:
        raise HTTPException(500, f"Plan generation failed: {str(e)}")


@app.post("/api/plan/regenerate")
async def regenerate_plan(user_id: str = Form(...)):
    """Regenerate plan after profile changes (triggered by chat)."""
    from bson import ObjectId

    users = get_collection(USERS_COLLECTION)
    user = await users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(404, "User not found")

    profile_data = user.get("profile", {})
    cas_data = user.get("cas_data")
    plans_collection = get_collection(PLANS_COLLECTION)

    try:
        plan = await generate_plan(
            profile_data=profile_data,
            cas_data=cas_data,
            db_collection=plans_collection,
            user_id=user_id,
        )
        return {
            "success": True,
            "message": "Plan regenerated with updated profile",
            "plan": plan.model_dump(),
        }
    except Exception as e:
        raise HTTPException(500, f"Plan regeneration failed: {str(e)}")


@app.get("/api/plan/{user_id}")
async def get_plan(user_id: str):
    """Get the latest financial plan for a user."""
    from bson import ObjectId

    plans = get_collection(PLANS_COLLECTION)
    latest = await plans.find_one(
        {"user_id": ObjectId(user_id)},
        sort=[("version", -1)],
    )

    if not latest:
        raise HTTPException(404, "No plan found. Generate one first.")

    latest["_id"] = str(latest["_id"])
    latest["user_id"] = str(latest["user_id"])
    if "created_at" in latest:
        latest["created_at"] = latest["created_at"].isoformat()

    return {"success": True, "plan": latest}


# ── Chat ──────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Send a chat message and get advisor response."""
    from bson import ObjectId

    users = get_collection(USERS_COLLECTION)
    user = await users.find_one({"_id": ObjectId(req.user_id)})
    if not user:
        raise HTTPException(404, "User not found")

    profile_data = user.get("profile", {})
    chat_collection = get_collection(CHAT_COLLECTION)

    # Get chat history
    chat_doc = await chat_collection.find_one({"user_id": ObjectId(req.user_id)})
    chat_history = chat_doc.get("messages", []) if chat_doc else []

    try:
        response = await handle_chat(
            user_id=req.user_id,
            message=req.message,
            profile_data=profile_data,
            chat_history=chat_history,
            chat_collection=chat_collection,
        )
        return {
            "success": True,
            "reply": response.reply,
            "needs_replan": response.needs_replan,
            "profile_updates": response.profile_updates,
        }
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {str(e)}")


@app.get("/api/chat/history/{user_id}")
async def get_chat_history(user_id: str):
    """Get chat history for a user."""
    from bson import ObjectId

    chat_collection = get_collection(CHAT_COLLECTION)
    chat_doc = await chat_collection.find_one({"user_id": ObjectId(user_id)})

    if not chat_doc:
        return {"success": True, "messages": []}

    return {
        "success": True,
        "messages": chat_doc.get("messages", []),
    }


# ── Profile Management ───────────────────────────────────────

@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    """Get the user's current profile."""
    from bson import ObjectId

    users = get_collection(USERS_COLLECTION)
    user = await users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(404, "User not found")

    return {
        "success": True,
        "profile": user.get("profile", {}),
        "onboarding_completed": user.get("onboarding_completed", False),
        "has_cas_data": user.get("cas_data") is not None,
        "has_setu_data": user.get("setu_data") is not None,
    }


class ProfileUpdateRequest(BaseModel):
    updates: dict


@app.put("/api/profile/{user_id}")
async def update_profile(user_id: str, req: ProfileUpdateRequest):
    """Update specific profile fields."""
    from bson import ObjectId

    users = get_collection(USERS_COLLECTION)
    update_dict = {f"profile.{k}": v for k, v in req.updates.items()}
    update_dict["updated_at"] = datetime.now(timezone.utc)

    result = await users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_dict},
    )

    if result.modified_count == 0:
        raise HTTPException(404, "User not found or no changes made")

    return {
        "success": True,
        "message": "Profile updated",
        "fields_changed": list(req.updates.keys()),
    }


# ── Lookup by Clerk ID ───────────────────────────────────────

@app.get("/api/user/by-clerk/{clerk_user_id}")
async def get_user_by_clerk_id(clerk_user_id: str):
    """Find a user by their Clerk user ID."""
    users = get_collection(USERS_COLLECTION)
    user = await users.find_one({"clerk_user_id": clerk_user_id})

    if not user:
        return {"found": False}

    return {
        "found": True,
        "user_id": str(user["_id"]),
        "onboarding_completed": user.get("onboarding_completed", False),
    }


@app.post("/api/user/init")
async def init_user(req: InitUserRequest):
    """Ensure user exists in DB on first login. Returns found status and ID."""
    users = get_collection(USERS_COLLECTION)
    user = await users.find_one({"clerk_user_id": req.clerk_user_id})

    if user:
        return {
            "found": True,
            "user_id": str(user["_id"]),
            "onboarding_completed": user.get("onboarding_completed", False),
        }

    # Create skeleton document
    new_user = {
        "clerk_user_id": req.clerk_user_id,
        "email": req.email,
        "first_name": req.first_name,
        "last_name": req.last_name,
        "created_at": datetime.now(timezone.utc),
        "onboarding_completed": False,
        "profile": {},
        "cas_data": None,
        "setu_data": None,
    }
    result = await users.insert_one(new_user)
    
    return {
        "found": True,
        "user_id": str(result.inserted_id),
        "onboarding_completed": False,
    }
