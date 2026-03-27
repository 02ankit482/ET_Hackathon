# chatbot.py
# ─────────────────────────────────────────────────────────────
# Main chatbot — ties together retriever, user profile, and
# the Anthropic API into a conversational finance advisor.
#
# Usage:
#   python chatbot.py                    # new session
#   python chatbot.py --profile path.json  # load saved profile
# ─────────────────────────────────────────────────────────────

import json
import argparse
from typing import List, Dict

import google.generativeai as genai
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    SYSTEM_PROMPT,
    FINANCIAL_CONSTANTS,
)
from retriever import HybridRetriever
from user_profile import UserProfile, build_profile_interactively

console = Console()

if not GEMINI_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY is not set in the environment.")

genai.configure(api_key=GEMINI_API_KEY)


# ── Finance Chatbot ───────────────────────────────────────────

class FinanceChatbot:
    """
    Stateful chatbot that keeps:
      - conversation history (multi-turn)
      - user profile (personalisation)
      - a HybridRetriever instance (RAG)
    """

    MAX_HISTORY = 12   # keep last N turns to stay within context window

    def __init__(self, profile: UserProfile):
        self.profile   = profile
        self.retriever = HybridRetriever()
        self.history: List[Dict[str, str]] = []
        self.model_name = GEMINI_MODEL
        # Debug fields for diagnosing truncated/partial responses
        self.last_finish_reason = None
        self.last_usage_metadata = None
        # Debug / UI fields
        self.last_hits: List[Dict] = []
        self.last_context: str = ""

    # ── Profile Auto-Update from Chat ──────────────────────────

    def _maybe_update_profile_from_utterance(self, user_query: str) -> None:
        """
        Use Gemini to infer profile updates from natural language, e.g.:
        "I'm 32, earn 80k, expenses 45k, I'm aggressive" → updates fields.

        This is best-effort and silently ignored on error.
        """
        try:
            model = genai.GenerativeModel(self.model_name)
            prompt = (
                "You are a parser for a personal finance chatbot.\n"
                "Given the current structured profile JSON and a new user message, "
                "return ONLY a JSON object with any fields that should be updated.\n"
                "Valid keys: name, age, city, monthly_income_inr, monthly_expense_inr, "
                "existing_savings_inr, existing_investments_inr, emi_obligations_inr, "
                "risk_appetite, experience_level, investment_horizon_years, goals, "
                "has_term_insurance, has_health_insurance.\n"
                "- goals should be an array of strings when present.\n"
                "- Booleans must be true/false.\n"
                "If nothing should change, return an empty JSON object {}.\n\n"
                f"Current profile JSON:\n{json.dumps(self.profile.to_dict(), indent=2)}\n\n"
                f"User message:\n{user_query}\n\n"
                "Respond with JSON only, no explanation."
            )
            resp = model.generate_content(prompt)
            raw = (getattr(resp, "text", "") or "").strip()
            if not raw:
                return
            # Try to locate JSON object in the text
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return
            obj = json.loads(raw[start : end + 1])
        except Exception:
            return

        if not isinstance(obj, dict):
            return

        # Merge into profile, only for known fields
        for key, value in obj.items():
            if not hasattr(self.profile, key):
                continue
            # Basic type coercions
            try:
                if key in {"age", "investment_horizon_years"}:
                    setattr(self.profile, key, int(value))
                elif key.endswith("_inr"):
                    setattr(self.profile, key, float(value))
                elif key in {"has_term_insurance", "has_health_insurance"}:
                    setattr(self.profile, key, bool(value))
                elif key == "goals":
                    if isinstance(value, list):
                        self.profile.goals = [str(g) for g in value if str(g).strip()]
                    elif isinstance(value, str):
                        self.profile.goals = [g.strip() for g in value.split(",") if g.strip()]
                else:
                    setattr(self.profile, key, value)
            except Exception:
                continue

    # ── Query Pipeline ────────────────────────────────────────

    def ask(self, user_query: str) -> str:
        # 0. Try to enrich profile from this utterance
        self._maybe_update_profile_from_utterance(user_query)

        # 1. Retrieve relevant chunks
        hits    = self.retriever.retrieve(user_query, self.profile.to_dict())
        context = self.retriever.format_context(hits)
        self.last_hits = hits
        self.last_context = context

        # 2. Build system prompt with constants + profile + context
        system = SYSTEM_PROMPT.format(
            constants    = json.dumps(FINANCIAL_CONSTANTS, indent=2),
            user_profile = self.profile.to_prompt_str(),
            context      = context,
        )

        # 3. Append current user message to history
        self.history.append({"role": "user", "content": user_query})

        # 4. Trim history to MAX_HISTORY turns
        trimmed_history = self.history[-self.MAX_HISTORY:]

        # 5. Call Gemini as a proper chat w/ system instruction
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system,
        )

        # Convert our history into Gemini chat roles
        gemini_history = []
        for turn in trimmed_history[:-1]:  # exclude latest user turn; we'll send it below
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "assistant":
                gemini_history.append({"role": "model", "parts": [content]})
            else:
                gemini_history.append({"role": "user", "parts": [content]})

        chat = model.start_chat(history=gemini_history)
        response = chat.send_message(
            user_query,
            generation_config={"max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS},
        )

        # Expose metadata for debugging truncated responses
        try:
            cand0 = response.candidates[0] if getattr(response, "candidates", None) else None
            finish_reason = getattr(cand0, "finish_reason", None)
            self.last_finish_reason = str(finish_reason) if finish_reason is not None else None

            usage = getattr(response, "usage_metadata", None)
            if usage is None:
                self.last_usage_metadata = None
            else:
                self.last_usage_metadata = {
                    "prompt_token_count": getattr(usage, "prompt_token_count", None),
                    "candidates_token_count": getattr(usage, "candidates_token_count", None),
                    "total_token_count": getattr(usage, "total_token_count", None),
                }
        except Exception:
            self.last_finish_reason = None
            self.last_usage_metadata = None

        assistant_reply = getattr(response, "text", "") or ""
        if not assistant_reply.strip():
            # Fallback: ensure we never return a blank/ack-only response
            assistant_reply = "I couldn't generate a complete answer. Please try rephrasing your question."

        # 7. Save assistant reply to history
        self.history.append({"role": "assistant", "content": assistant_reply})

        return assistant_reply

    # ── Special Commands ──────────────────────────────────────

    def handle_command(self, cmd: str) -> bool:
        """
        Returns True if the input was a command (not a finance question).
        Commands: /profile, /clear, /save, /help
        """
        cmd = cmd.strip().lower()

        if cmd == "/profile":
            console.print(Panel(self.profile.to_prompt_str(), title="Your Profile"))
            return True

        if cmd == "/clear":
            self.history.clear()
            console.print("[yellow]Conversation history cleared.[/yellow]")
            return True

        if cmd == "/save":
            self.profile.save()
            console.print("[green]Profile saved to user_profile.json[/green]")
            return True

        if cmd == "/help":
            console.print(Panel(
                "/profile — show your financial profile\n"
                "/clear   — reset conversation history\n"
                "/save    — save your profile to disk\n"
                "/quit    — exit the chatbot\n"
                "/help    — show this message",
                title="Commands",
            ))
            return True

        return False

    # ── Main Loop ─────────────────────────────────────────────

    def run(self):
        console.print(Panel(
            f"[bold green]Finance Advisor Chatbot[/bold green]\n"
            f"Hello [cyan]{self.profile.name}[/cyan]! I'm your personal finance advisor.\n"
            f"Type [dim]/help[/dim] for commands or [dim]/quit[/dim] to exit.",
            expand=False,
        ))

        while True:
            try:
                user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Goodbye![/yellow]")
                break

            if not user_input:
                continue

            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                console.print("[yellow]Goodbye![/yellow]")
                break

            if self.handle_command(user_input):
                continue

            # Show spinner while thinking
            with console.status("[dim]Thinking…[/dim]"):
                try:
                    reply = self.ask(user_input)
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    continue

            console.print("\n[bold green]Advisor:[/bold green]")
            console.print(Markdown(reply))


# ── Entry Point ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Finance RAG Chatbot")
    parser.add_argument("--profile", default="user_profile.json",
                        help="Path to saved user profile JSON")
    parser.add_argument("--no-setup", action="store_true",
                        help="Skip profile setup wizard")
    args = parser.parse_args()

    # Load or build profile
    from pathlib import Path
    if Path(args.profile).exists():
        profile = UserProfile.load(args.profile)
        console.print(f"[green]Loaded profile for: {profile.name}[/green]")
    elif args.no_setup:
        profile = UserProfile()
    else:
        profile = build_profile_interactively()
        profile.save(args.profile)

    bot = FinanceChatbot(profile)
    bot.run()


if __name__ == "__main__":
    main()
