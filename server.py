"""
Finance RAG + CrewAI web server.

Run:
  pip install -r requirements.txt
  uvicorn server:app --reload --host 127.0.0.1 --port 8000

Endpoints:
  Legacy (Gemini direct):
    POST /api/session/new
    POST /api/profile
    POST /api/chat

  CrewAI multi-agent:
    POST /api/crew/session/new       → new CrewAI session
    POST /api/crew/profile-chat      → profile building conversation turn
    POST /api/crew/run               → run planner + advisor agents
    GET  /api/crew/profile/{sid}     → get current profile
"""

from __future__ import annotations

from typing import Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from user_profile import UserProfile
from chatbot import FinanceChatbot
from crew_agents import CrewFinanceSystem


app = FastAPI(title="Finance RAG + CrewAI Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════

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
    goals: str = "Retirement"
    has_term_insurance: bool = False
    has_health_insurance: bool = False


class ChatIn(BaseModel):
    session_id: str
    message: str


class CrewChatIn(BaseModel):
    session_id: str
    message: str


class CrewRunIn(BaseModel):
    session_id: str
    query: str


# ══════════════════════════════════════════════════════════════
# SESSION STORES
# ══════════════════════════════════════════════════════════════

_sessions: Dict[str, FinanceChatbot] = {}          # legacy sessions
_crew_sessions: Dict[str, CrewFinanceSystem] = {}  # crew sessions


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

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


def _get_crew(session_id: str) -> CrewFinanceSystem:
    system = _crew_sessions.get(session_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Unknown crew session_id. Create one first.")
    return system


# ══════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS (unchanged)
# ══════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/session/new")
def new_session():
    session_id = str(uuid4())
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
        raise HTTPException(status_code=404, detail="Unknown session_id.")
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


# ══════════════════════════════════════════════════════════════
# CREWAI ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.post("/api/crew/session/new")
def crew_new_session():
    """Create a new CrewAI session."""
    session_id = str(uuid4())
    _crew_sessions[session_id] = CrewFinanceSystem()
    return {
        "session_id": session_id,
        "message": (
            "Hello! I'm your personal finance profile specialist. "
            "To give you the best advice, I need to understand your financial situation. "
            "Let's start — could you tell me your name, age, and roughly where you're based in India?"
        ),
        "phase": "profile_building",
        "profile_complete": False,
    }


@app.post("/api/crew/profile-chat")
def crew_profile_chat(payload: CrewChatIn):
    """
    One turn of profile-building conversation.
    Returns agent response and whether profile is complete.
    """
    system = _get_crew(payload.session_id)

    if system.profile_complete:
        return {
            "message": "Profile already complete. Use /api/crew/run to get your financial plan.",
            "profile_complete": True,
            "profile": system.profile.to_dict() if system.profile else None,
            "phase": "ready",
        }

    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message required")

    try:
        response, complete = system.chat_profile(msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile agent error: {str(e)}")

    result = {
        "message": response,
        "profile_complete": complete,
        "phase": "ready" if complete else "profile_building",
    }

    if complete and system.profile:
        result["profile"] = system.profile.to_dict()
        result["profile_summary"] = system.profile.to_prompt_str()

    return result


@app.post("/api/crew/run")
def crew_run(payload: CrewRunIn):
    """
    Run the Planner + Advisor agents once profile is complete.
    Returns plan (timeline) and advice (how-to guide).
    """
    system = _get_crew(payload.session_id)

    if not system.profile_complete:
        raise HTTPException(
            status_code=400,
            detail="Profile not complete yet. Finish profile building first.",
        )

    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    try:
        results = system.run_finance_crew(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Finance crew error: {str(e)}")

    return {
        "plan": results["plan"],
        "advice": results["advice"],
        "profile": results["profile"],
        "query": query,
    }


@app.get("/api/crew/profile/{session_id}")
def crew_get_profile(session_id: str):
    """Get the current profile for a crew session."""
    system = _get_crew(session_id)
    if not system.profile:
        return {"profile": None, "profile_complete": False}
    return {
        "profile": system.profile.to_dict(),
        "profile_summary": system.profile.to_prompt_str(),
        "profile_complete": system.profile_complete,
    }


@app.post("/api/crew/reset/{session_id}")
def crew_reset(session_id: str):
    """Reset a crew session (clear profile and conversation)."""
    system = _get_crew(session_id)
    system.reset()
    return {"ok": True, "message": "Session reset. Start profile building again."}


# ══════════════════════════════════════════════════════════════
# STATIC FRONTEND
# ══════════════════════════════════════════════════════════════

app.mount("/static", StaticFiles(directory="frontend", html=False), name="static")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")