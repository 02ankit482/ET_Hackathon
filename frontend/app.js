function $(id) { return document.getElementById(id); }

const API = {
  async health() {
    const r = await fetch("/api/health");
    return r.json();
  },
  async newSession() {
    const r = await fetch("/api/session/new", { method: "POST" });
    if (!r.ok) throw new Error("Failed to create session");
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
};

function renderProfile(obj) {
  $("profileBox").textContent = JSON.stringify(obj ?? {}, null, 2);
}

function renderContext(res) {
  const box = $("contextBox");
  if (!box) return;
  const hits = res?.hits || [];
  if (!hits.length) {
    box.textContent = "(no retrieved chunks for this question)";
    return;
  }
  const lines = [];
  hits.forEach((h, idx) => {
    const meta = h.metadata || {};
    lines.push(
      `#${idx + 1} ${meta.source_file || "?"} | topic: ${meta.topic || "?"} | risk: ${
        meta.risk_level || "?"
      }`,
    );
    const text = (h.text || "").slice(0, 400).trim();
    lines.push(text + (h.text && h.text.length > 400 ? " ..." : ""));
    lines.push("");
  });
  box.textContent = lines.join("\n");
}

function addBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = role === "user" ? "flex justify-end" : "flex justify-start";

  const bubble = document.createElement("div");
  bubble.className =
    (role === "user"
      ? "bg-indigo-600/80 border-indigo-500/50"
      : "bg-slate-950/70 border-slate-800") +
    " max-w-[85%] border rounded px-3 py-2 text-sm whitespace-pre-wrap";
  bubble.textContent = text;

  wrap.appendChild(bubble);
  $("chatLog").appendChild(wrap);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
  return bubble;
}

async function typeIntoBubble(bubble, fullText, delay = 15) {
  bubble.textContent = "";
  let i = 0;
  return new Promise((resolve) => {
    const tick = () => {
      if (i >= fullText.length) {
        resolve();
        return;
      }
      bubble.textContent += fullText[i++];
      $("chatLog").scrollTop = $("chatLog").scrollHeight;
      setTimeout(tick, delay);
    };
    tick();
  });
}

function setHealth(ok) {
  $("healthDot").className =
    "inline-block w-2 h-2 rounded-full " + (ok ? "bg-emerald-500" : "bg-rose-500");
}

function formToProfile(form) {
  const fd = new FormData(form);
  const getNum = (k) => Number(fd.get(k) || 0);
  return {
    name: String(fd.get("name") || "User"),
    age: Number(fd.get("age") || 30),
    city: String(fd.get("city") || "India"),
    monthly_income_inr: getNum("monthly_income_inr"),
    monthly_expense_inr: getNum("monthly_expense_inr"),
    existing_savings_inr: getNum("existing_savings_inr"),
    existing_investments_inr: getNum("existing_investments_inr"),
    emi_obligations_inr: getNum("emi_obligations_inr"),
    risk_appetite: String(fd.get("risk_appetite") || "moderate"),
    experience_level: String(fd.get("experience_level") || "beginner"),
    investment_horizon_years: Number(fd.get("investment_horizon_years") || 10),
    goals: String(fd.get("goals") || ""),
    has_term_insurance: fd.get("has_term_insurance") === "on",
    has_health_insurance: fd.get("has_health_insurance") === "on",
  };
}

function openModal() {
  $("modal").classList.remove("hidden");
  $("modal").classList.add("flex");
}

function closeModal() {
  $("modal").classList.add("hidden");
  $("modal").classList.remove("flex");
}

async function ensureSession() {
  let sessionId = localStorage.getItem("finance_demo_session_id");
  if (!sessionId) {
    const { session_id } = await API.newSession();
    sessionId = session_id;
    localStorage.setItem("finance_demo_session_id", sessionId);
  }
  return sessionId;
}

async function newSessionAndResetUI() {
  const { session_id } = await API.newSession();
  localStorage.setItem("finance_demo_session_id", session_id);
  $("chatLog").innerHTML = "";
  renderProfile({ session_id });
  addBubble("assistant", "New session created. Click “Edit profile” to personalize, then ask a question.");
}

async function main() {
  try {
    const h = await API.health();
    setHealth(!!h.ok);
  } catch {
    setHealth(false);
  }

  const sessionId = await ensureSession();
  renderProfile({ session_id: sessionId });
  addBubble("assistant", "Ask a finance question. For best results, run ingest on your documents first.");

  $("btnProfile").addEventListener("click", openModal);
  $("btnClose").addEventListener("click", closeModal);
  $("btnCancel").addEventListener("click", closeModal);
  $("btnNew").addEventListener("click", async () => {
    await newSessionAndResetUI();
  });

  $("profileForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sid = await ensureSession();
    const profile = formToProfile(e.target);
    const res = await API.setProfile(sid, profile);
    renderProfile(res.profile);
    closeModal();
    addBubble("assistant", "Profile saved. Ask your question when ready.");
  });

  $("chatForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("chatInput");
    const message = (input.value || "").trim();
    if (!message) return;
    input.value = "";
    input.focus();

    addBubble("user", message);
    const sid = await ensureSession();
    try {
      const res = await API.chat(sid, message);
      renderProfile(res.profile);
      renderContext(res);
      const debug = res.finish_reason ? `\n\n[debug] finish_reason: ${String(res.finish_reason)}` : "";
      const bubble = addBubble("assistant", "");
      await typeIntoBubble(bubble, (res.reply || "(no reply)") + debug);
    } catch (err) {
      addBubble("assistant", "Error: " + String(err?.message || err));
    }
  });
}

main();

