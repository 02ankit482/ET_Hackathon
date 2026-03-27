"""
Minimal web server wrapper for the Finance RAG chatbot.

Run:
  pip install -r requirements.txt
  uvicorn server:app --reload --host 127.0.0.1 --port 8000
Then open:
  http://127.0.0.1:8000
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from user_profile import UserProfile
from chatbot import FinanceChatbot


app = FastAPI(title="Finance RAG Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProfileIn(BaseModel):
    name: str = "User"
    age: int = 30
    city: str = "India"
    monthly_income_inr: float = 0.0
    monthly_expense_inr: float = 0.0
    existing_savings_inr: float = 0.0
    existing_investments_inr: float = 0.0
    emi_obligations_inr: float = 0.0
    risk_appetite: str = Field(default="moderate", pattern="^(conservative|moderate|aggressive)$")
    experience_level: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    investment_horizon_years: int = 10
    goals: str = "Retirement"  # comma-separated in UI
    has_term_insurance: bool = False
    has_health_insurance: bool = False


class ChatIn(BaseModel):
    session_id: str
    message: str


_sessions: Dict[str, FinanceChatbot] = {}


def _profile_from_in(p: ProfileIn) -> UserProfile:
    goals = [g.strip() for g in (p.goals or "").split(",") if g.strip()]
    return UserProfile(
        name=p.name,
        age=p.age,
        city=p.city,
        monthly_income_inr=p.monthly_income_inr,
        monthly_expense_inr=p.monthly_expense_inr,
        existing_savings_inr=p.existing_savings_inr,
        existing_investments_inr=p.existing_investments_inr,
        emi_obligations_inr=p.emi_obligations_inr,
        risk_appetite=p.risk_appetite,
        experience_level=p.experience_level,
        investment_horizon_years=p.investment_horizon_years,
        goals=goals,
        has_term_insurance=p.has_term_insurance,
        has_health_insurance=p.has_health_insurance,
    )


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/session/new")
def new_session():
    session_id = str(uuid4())
    # Initialize with defaults; UI can overwrite via /api/profile
    _sessions[session_id] = FinanceChatbot(UserProfile())
    return {"session_id": session_id}


@app.post("/api/profile")
def set_profile(session_id: str, profile: ProfileIn):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    bot = _sessions.get(session_id)
    if bot is None:
        bot = FinanceChatbot(UserProfile())
        _sessions[session_id] = bot

    bot.profile = _profile_from_in(profile)
    return {"ok": True, "profile": bot.profile.to_dict()}


@app.post("/api/chat")
def chat(payload: ChatIn):
    bot = _sessions.get(payload.session_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Unknown session_id. Create a session first.")

    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message required")

    reply = bot.ask(msg)
    return {
        "reply": reply,
        "profile": bot.profile.to_dict(),
        "history_len": len(bot.history),
        "finish_reason": bot.last_finish_reason,
        "usage_metadata": bot.last_usage_metadata,
        "context": bot.last_context,
        "hits": [
            {
                "text": h.get("text", ""),
                "metadata": h.get("metadata", {}),
                "score": h.get("score", None),
            }
            for h in getattr(bot, "last_hits", []) or []
        ],
    }


# --- Static frontend ---
app.mount("/static", StaticFiles(directory="frontend", html=False), name="static")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")

