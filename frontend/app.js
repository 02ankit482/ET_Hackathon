// app.js — Finance Advisor CrewAI + Legacy UI
// ─────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

// ══════════════════════════════════════════════
// API LAYER
// ══════════════════════════════════════════════

const API = {
  async health() {
    const r = await fetch("/api/health");
    return r.json();
  },
  // Legacy
  async newSession() {
    const r = await fetch("/api/session/new", { method: "POST" });
    if (!r.ok) throw new Error("Failed to create legacy session");
    return r.json();
  },
  async setProfile(sessionId, profile) {
    const url = new URL("/api/profile", window.location.origin);
    url.searchParams.set("session_id", sessionId);
    const r = await fetch(url.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async chat(sessionId, message) {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  // CrewAI
  async crewNewSession() {
    const r = await fetch("/api/crew/session/new", { method: "POST" });
    if (!r.ok) throw new Error("Failed to create crew session");
    return r.json();
  },
  async crewProfileChat(sessionId, message) {
    const r = await fetch("/api/crew/profile-chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async crewRun(sessionId, query) {
    const r = await fetch("/api/crew/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, query }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

// ══════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════

let activeTab = "crew";            // "crew" | "legacy"
let crewSessionId = null;
let crewPhase = "profile";         // "profile" | "query" | "results"
let legacySessionId = null;

// ══════════════════════════════════════════════
// TAB SWITCHING
// ══════════════════════════════════════════════

window.switchTab = function (tab) {
  activeTab = tab;
  $("crewPanel").classList.toggle("hidden", tab !== "crew");
  $("legacyPanel").classList.toggle("hidden", tab !== "legacy");
  $("tabCrew").className = tab === "crew"
    ? "tab-active px-4 py-2 rounded border text-sm font-medium transition-all"
    : "tab-inactive px-4 py-2 rounded border text-sm font-medium transition-all";
  $("tabLegacy").className = tab === "legacy"
    ? "tab-active px-4 py-2 rounded border text-sm font-medium transition-all"
    : "tab-inactive px-4 py-2 rounded border text-sm font-medium transition-all";
};

window.switchResultTab = function (tab) {
  $("planPanel").classList.toggle("hidden", tab !== "plan");
  $("advicePanel").classList.toggle("hidden", tab !== "advice");
  $("rTabPlan").className = tab === "plan"
    ? "tab-active px-3 py-1.5 rounded border text-xs font-medium transition-all"
    : "tab-inactive px-3 py-1.5 rounded border text-xs font-medium transition-all";
  $("rTabAdvice").className = tab === "advice"
    ? "tab-active px-3 py-1.5 rounded border text-xs font-medium transition-all"
    : "tab-inactive px-3 py-1.5 rounded border text-xs font-medium transition-all";
};

// ══════════════════════════════════════════════
// CREW CHAT UI
// ══════════════════════════════════════════════

function crewAddBubble(role, text) {
  const log = $("crewChatLog");
  const wrap = document.createElement("div");
  wrap.className = role === "user" ? "flex justify-end" : "flex justify-start gap-2";

  if (role !== "user") {
    const avatar = document.createElement("div");
    avatar.className = "w-7 h-7 rounded-full bg-indigo-700 flex items-center justify-center text-sm flex-shrink-0 mt-0.5";
    avatar.textContent = "🤖";
    wrap.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = (role === "user"
    ? "bg-indigo-700/70 border-indigo-600/40 text-white"
    : "bg-slate-900 border-slate-700 text-slate-200")
    + " max-w-[85%] border rounded-xl px-4 py-2.5 text-sm prose";

  // Render markdown-lite
  bubble.innerHTML = markdownToHtml(text);

  wrap.appendChild(bubble);
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return bubble;
}

function crewAddTyping() {
  const log = $("crewChatLog");
  const wrap = document.createElement("div");
  wrap.className = "flex justify-start gap-2";
  wrap.id = "typingIndicator";

  const avatar = document.createElement("div");
  avatar.className = "w-7 h-7 rounded-full bg-indigo-700 flex items-center justify-center text-sm flex-shrink-0 mt-0.5";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 flex gap-1.5 items-center";
  bubble.innerHTML = `
    <span class="typing-dot w-1.5 h-1.5 bg-slate-400 rounded-full"></span>
    <span class="typing-dot w-1.5 h-1.5 bg-slate-400 rounded-full"></span>
    <span class="typing-dot w-1.5 h-1.5 bg-slate-400 rounded-full"></span>
  `;

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

function removeTyping() {
  const el = $("typingIndicator");
  if (el) el.remove();
}

// ══════════════════════════════════════════════
// MARKDOWN → HTML (minimal renderer)
// ══════════════════════════════════════════════

function markdownToHtml(md) {
  if (!md) return "";
  return md
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Checkboxes
    .replace(/- \[ \] (.+)/g, '<li style="list-style:none">☐ $1</li>')
    .replace(/- \[x\] (.+)/gi, '<li style="list-style:none">☑ $1</li>')
    // Bullet lists
    .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // Code inline
    .replace(/`(.+?)`/g, '<code>$1</code>')
    // Horizontal rule
    .replace(/^---+$/gm, '<hr style="border-color:#334155;margin:.8rem 0">')
    // Line breaks
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

// ══════════════════════════════════════════════
// STEP INDICATOR
// ══════════════════════════════════════════════

function setStep(step) {
  // step: 1, 2, 3
  const steps = ["step1", "step2", "step3"];
  const labels = [
    "Phase 1 · Profile Building",
    "Phase 2 · Generating Plan",
    "Phase 3 · Advisor Advice",
  ];
  const agents = [
    "Profile Builder Agent",
    "Financial Planner Agent",
    "Financial Advisor Agent",
  ];
  const icons = ["1", "2", "3"];
  const activeColors = ["bg-indigo-600", "bg-green-600", "bg-blue-600"];

  steps.forEach((id, i) => {
    const el = $(id);
    const icon = el.querySelector(".step-icon");
    if (i < step) {
      el.classList.remove("opacity-40");
      icon.className = `step-icon w-6 h-6 rounded-full ${activeColors[i]} text-white flex items-center justify-center text-xs font-bold flex-shrink-0`;
      icon.textContent = i < step - 1 ? "✓" : icons[i];
    } else if (i === step - 1) {
      el.classList.remove("opacity-40");
    } else {
      el.classList.add("opacity-40");
    }
  });

  $("phaseLabel").textContent = labels[step - 1] || "";
  $("agentBadge").textContent = agents[step - 1] || "";
}

// ══════════════════════════════════════════════
// CREW SESSION INIT
// ══════════════════════════════════════════════

async function initCrewSession() {
  try {
    const res = await API.crewNewSession();
    crewSessionId = res.session_id;
    sessionStorage.setItem("crew_session_id", crewSessionId);
    crewPhase = "profile";
    setStep(1);
    $("crewChatLog").innerHTML = "";
    $("crewProfileBox").textContent = "(not yet built)";
    $("resultsSection").classList.add("hidden");
    crewAddBubble("assistant", res.message);
    $("crewInput").placeholder = "Tell me about yourself…";
    $("inputHint").textContent =
      "The profile agent will ask you targeted questions. Answer as much or as little as you're comfortable with.";
  } catch (e) {
    crewAddBubble("assistant", "⚠️ Could not connect to server: " + e.message);
  }
}

// ══════════════════════════════════════════════
// CREW PROFILE CHAT HANDLER
// ══════════════════════════════════════════════

async function handleCrewProfileMessage(message) {
  crewAddBubble("user", message);
  const typing = crewAddTyping();

  try {
    const res = await API.crewProfileChat(crewSessionId, message);
    removeTyping();

    crewAddBubble("assistant", res.message);

    if (res.profile_complete && res.profile) {
      // Update profile sidebar
      $("crewProfileBox").textContent = res.profile_summary || JSON.stringify(res.profile, null, 2);

      // Transition to query phase
      crewPhase = "query";
      setStep(2);
      $("crewInput").placeholder = "What financial goal would you like help with? (e.g. 'I want to retire by 55')";
      $("inputHint").textContent =
        "Your profile is complete! Now describe your financial goal or question — the Planner and Advisor agents will get to work.";

      // Small delay then show prompt
      setTimeout(() => {
        crewAddBubble("assistant",
          `✅ Perfect, your profile is all set!\n\n` +
          `Now tell me — **what would you like to achieve financially?**\n\n` +
          `For example:\n- "I want to retire comfortably by age 55"\n` +
          `- "How should I invest my ₹${(res.profile.monthly_surplus_inr || 0).toLocaleString("en-IN")} monthly surplus?"\n` +
          `- "I want to buy a house in 5 years and save for my child's education"`
        );
      }, 400);
    }
  } catch (e) {
    removeTyping();
    crewAddBubble("assistant", "⚠️ Error: " + e.message);
  }
}

// ══════════════════════════════════════════════
// CREW RUN (PLANNER + ADVISOR)
// ══════════════════════════════════════════════

async function handleCrewRun(query) {
  crewAddBubble("user", query);

  // Show planner running
  setStep(2);
  const typingPlan = crewAddTyping();
  crewAddBubble("assistant",
    "🤔 **Financial Planner Agent** is analysing your profile and building your timeline…\n\n" +
    "This may take 30-60 seconds as the agents retrieve knowledge and calculate your numbers."
  );

  try {
    const res = await API.crewRun(crewSessionId, query);
    removeTyping();

    // Update profile sidebar with latest
    if (res.profile) {
      $("crewProfileBox").textContent = JSON.stringify(res.profile, null, 2);
    }

    // Show results section
    $("resultsSection").classList.remove("hidden");
    $("planContent").innerHTML = markdownToHtml(res.plan);
    $("adviceContent").innerHTML = markdownToHtml(res.advice);
    switchResultTab("plan");

    setStep(3);
    crewPhase = "results";

    crewAddBubble("assistant",
      "✅ Done! Your **Financial Plan** and **Advisor Advice** are ready — " +
      "check the panels below the chat.\n\n" +
      "You can ask follow-up questions or describe another goal."
    );

    $("inputHint").textContent =
      "You can ask a follow-up question or describe another financial goal.";
    $("crewInput").placeholder = "Ask a follow-up or describe another goal…";

    // Scroll to results
    setTimeout(() => {
      $("resultsSection").scrollIntoView({ behavior: "smooth", block: "start" });
    }, 500);

  } catch (e) {
    removeTyping();
    setStep(2);
    crewAddBubble("assistant", "⚠️ Agent error: " + e.message +
      "\n\nMake sure you have ingested documents and that your GOOGLE_API_KEY is set.");
  }
}

// ══════════════════════════════════════════════
// CREW FORM SUBMIT
// ══════════════════════════════════════════════

function setupCrewForm() {
  $("crewChatForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("crewInput");
    const message = (input.value || "").trim();
    if (!message) return;
    input.value = "";
    input.focus();

    if (!crewSessionId) {
      await initCrewSession();
    }

    if (crewPhase === "profile") {
      await handleCrewProfileMessage(message);
    } else {
      // query or results phase — run the crew
      await handleCrewRun(message);
    }
  });
}

// ══════════════════════════════════════════════
// LEGACY UI (unchanged logic)
// ══════════════════════════════════════════════

function renderProfile(obj) {
  $("profileBox").textContent = JSON.stringify(obj ?? {}, null, 2);
}

function renderContext(res) {
  const box = $("contextBox");
  if (!box) return;
  const hits = res?.hits || [];
  if (!hits.length) { box.textContent = "(no retrieved chunks)"; return; }
  const lines = [];
  hits.forEach((h, idx) => {
    const meta = h.metadata || {};
    lines.push(`#${idx+1} ${meta.source_file||"?"} | topic: ${meta.topic||"?"}`);
    lines.push((h.text||"").slice(0,300).trim() + (h.text?.length > 300 ? " …" : ""));
    lines.push("");
  });
  box.textContent = lines.join("\n");
}

function addLegacyBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = role === "user" ? "flex justify-end" : "flex justify-start";
  const bubble = document.createElement("div");
  bubble.className = (role === "user"
    ? "bg-indigo-600/80 border-indigo-500/50"
    : "bg-slate-950/70 border-slate-800")
    + " max-w-[85%] border rounded px-3 py-2 text-sm whitespace-pre-wrap";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  $("chatLog").appendChild(wrap);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
  return bubble;
}

async function ensureLegacySession() {
  if (!legacySessionId) {
    const { session_id } = await API.newSession();
    legacySessionId = session_id;
  }
  return legacySessionId;
}

function openModal() { $("modal").classList.replace("hidden","flex"); }
function closeModal() { $("modal").classList.replace("flex","hidden"); }

function formToProfile(form) {
  const fd = new FormData(form);
  const getNum = k => Number(fd.get(k)||0);
  return {
    name: String(fd.get("name")||"User"),
    age: Number(fd.get("age")||30),
    city: String(fd.get("city")||"India"),
    monthly_income_inr: getNum("monthly_income_inr"),
    monthly_expense_inr: getNum("monthly_expense_inr"),
    existing_savings_inr: getNum("existing_savings_inr"),
    existing_investments_inr: getNum("existing_investments_inr"),
    emi_obligations_inr: getNum("emi_obligations_inr"),
    risk_appetite: String(fd.get("risk_appetite")||"moderate"),
    experience_level: String(fd.get("experience_level")||"beginner"),
    investment_horizon_years: Number(fd.get("investment_horizon_years")||10),
    goals: String(fd.get("goals")||""),
    has_term_insurance: fd.get("has_term_insurance")==="on",
    has_health_insurance: fd.get("has_health_insurance")==="on",
  };
}

function setupLegacyUI() {
  $("btnProfile").addEventListener("click", openModal);
  $("btnClose").addEventListener("click", closeModal);
  $("btnCancel").addEventListener("click", closeModal);

  $("profileForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sid = await ensureLegacySession();
    const profile = formToProfile(e.target);
    const res = await API.setProfile(sid, profile);
    renderProfile(res.profile);
    closeModal();
    addLegacyBubble("assistant", "Profile saved. Ask your question when ready.");
  });

  $("chatForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("chatInput");
    const message = (input.value||"").trim();
    if (!message) return;
    input.value = "";
    input.focus();
    addLegacyBubble("user", message);
    const sid = await ensureLegacySession();
    try {
      const res = await API.chat(sid, message);
      renderProfile(res.profile);
      renderContext(res);
      addLegacyBubble("assistant", res.reply || "(no reply)");
    } catch (err) {
      addLegacyBubble("assistant", "Error: " + String(err?.message||err));
    }
  });

  ensureLegacySession().then(sid => {
    renderProfile({ session_id: sid });
    addLegacyBubble("assistant", "Ask a finance question. For best results, ingest your documents first.");
  });
}

// ══════════════════════════════════════════════
// MAIN
// ══════════════════════════════════════════════

async function main() {
  // Health check
  try {
    const h = await API.health();
    $("healthDot").className = "inline-block w-2.5 h-2.5 rounded-full " +
      (h.ok ? "bg-emerald-500" : "bg-rose-500");
  } catch {
    $("healthDot").className = "inline-block w-2.5 h-2.5 rounded-full bg-rose-500";
  }

  // Restore crew session from sessionStorage
  const savedSid = sessionStorage.getItem("crew_session_id");
  if (savedSid) {
    crewSessionId = savedSid;
    crewAddBubble("assistant",
      "Welcome back! Your previous session is still active. " +
      "Continue building your profile or ask a new financial question."
    );
  } else {
    await initCrewSession();
  }

  // New session button
  $("btnReset").addEventListener("click", async () => {
    sessionStorage.removeItem("crew_session_id");
    crewSessionId = null;
    legacySessionId = null;
    $("chatLog").innerHTML = "";
    await initCrewSession();
  });

  setupCrewForm();
  setupLegacyUI();
}

main();