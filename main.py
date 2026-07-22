"""
Solar Advisor — Agent backend (FREE / local version, runs on Ollama)

Same idea as before, but instead of calling Anthropic's paid API, this talks to
Ollama — a free, open-source tool that runs an LLM entirely on your own PC.
No API key, no internet dependency once the model is downloaded, no per-query
cost, ever.

Design principle (unchanged): the LLM never invents wattage math. It calls a
tool that does plain arithmetic against the exact data the frontend already
computed. The model's job is only to reason and explain in natural language —
the safety-critical numbers stay deterministic.

One-time setup:
    1. Install Ollama: https://ollama.com/download  (free, all platforms)
    2. Pull a tool-calling-capable model, e.g.:
         ollama pull llama3.1
       (llama3.1:8b needs ~5GB RAM/disk. If your PC is limited, try
       `ollama pull qwen2.5:3b` instead — smaller and still supports tools —
       and change MODEL below to match.)
    3. Ollama runs its own local server automatically on http://localhost:11434
       after install — nothing else to start for that part.

Run this backend:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8787
"""

import json
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Solar Advisor Agent (Ollama / free)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"


# ---------- Request/response schema (unchanged — frontend needs no updates) ----------

class Appliance(BaseModel):
    name: str
    watt: float
    active: bool


class LogEntry(BaseModel):
    time: str
    predictedWatts: float
    activeLoad: float
    appliances: str
    outcome: str
    note: Optional[str] = ""


class ChatContext(BaseModel):
    availableWatts: float
    source: str
    ageMin: Optional[int] = None
    marginPct: float
    inverterCap: float
    appliances: list[Appliance]
    recentLogs: list[LogEntry] = []


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    context: ChatContext


# ---------- Tool: deterministic appliance-fit check ----------

def check_combo(appliance_names: list[str], context: ChatContext) -> dict:
    by_name = {a.name.lower(): a for a in context.appliances}
    matched, unmatched = [], []
    for n in appliance_names:
        hit = by_name.get(n.lower())
        if hit:
            matched.append(hit)
        else:
            candidates = [a for a in context.appliances if n.lower() in a.name.lower()]
            if candidates:
                matched.append(candidates[0])
            else:
                unmatched.append(n)

    total = sum(a.watt for a in matched)
    safe_limit = context.availableWatts * (1 - context.marginPct / 100)

    if total == 0:
        verdict = "no_appliances_matched"
    elif total <= safe_limit:
        verdict = "safe"
    elif total <= context.availableWatts:
        verdict = "marginal"
    else:
        verdict = "over_budget"

    return {
        "matched_appliances": [{"name": a.name, "watt": a.watt} for a in matched],
        "unmatched_names": unmatched,
        "total_watts": total,
        "available_watts": context.availableWatts,
        "safe_limit_watts": round(safe_limit),
        "inverter_capacity_watts": context.inverterCap,
        "verdict": verdict,
    }


def get_test_history(context: ChatContext, appliance_filter: Optional[str] = None) -> dict:
    logs = context.recentLogs
    if appliance_filter:
        logs = [l for l in logs if appliance_filter.lower() in l.appliances.lower()]
    return {
        "count": len(logs),
        "entries": [l.model_dump() for l in logs[:10]],
    }


# Ollama uses the same OpenAI-style function-calling schema.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_combo",
            "description": (
                "Check whether a specific combination of appliances fits within the "
                "current solar power budget. Always use this instead of doing the "
                "arithmetic yourself — it uses the live, physics-model-derived available "
                "wattage, not an assumption."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appliance_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of appliances to check, e.g. ['AC', 'Fridge']",
                    }
                },
                "required": ["appliance_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_test_history",
            "description": (
                "Look up real logged outcomes from past tests on this system (whether the "
                "inverter actually held or tripped for a given combination). Use this when "
                "the person asks about reliability or past experience, not just the model's "
                "prediction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appliance_filter": {
                        "type": "string",
                        "description": "Optional: filter logs to entries mentioning this appliance name",
                    }
                },
            },
        },
    },
]

SYSTEM_PROMPT = """You are the assistant inside "Solar Advisor" — a personal app that \
tells the user what appliances they can safely run on solar-only inverter mode, based \
on live sun/weather data for their specific home system.

Ground rules:
- Never compute or guess wattage totals yourself. Always call check_combo for any \
question about whether something fits, even if it seems like simple addition.
- If the person asks about past reliability ("has this worked before?", "did the AC \
trip last time?"), call get_test_history rather than speculating.
- Be direct and concrete. State the verdict plainly (safe / marginal / over budget), \
then briefly explain why, referencing actual numbers from the tool result.
- If a combination is "marginal", warn that a passing cloud could tip it over — don't \
present it as fully safe.
- Keep responses short — this is a quick check-in tool, not a report. 2-4 sentences \
unless the person asks for more detail.
- You do not have live access to anything not given to you in tool results or context. \
Don't invent weather details, exact percentages, or appliance wattages that weren't \
provided."""


def call_ollama(messages: list[dict]) -> dict:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


@app.post("/chat")
def chat(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})

    snapshot = (
        f"[Current state: {req.context.availableWatts}W available "
        f"(source: {req.context.source}"
        + (f", {req.context.ageMin}m old" if req.context.ageMin is not None else "")
        + f"), inverter cap {req.context.inverterCap}W, safety margin "
        f"{req.context.marginPct}%. Known appliances: "
        + ", ".join(f"{a.name} ({a.watt}W, {'on' if a.active else 'off'})" for a in req.context.appliances)
        + "]"
    )
    messages.append({"role": "user", "content": f"{snapshot}\n\n{req.message}"})

    try:
        for _ in range(4):  # cap tool-use loop
            data = call_ollama(messages)
            msg = data.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return {"reply": msg.get("content", "").strip() or "I'm not sure how to answer that."}

            messages.append(msg)
            for call in tool_calls:
                fn = call["function"]["name"]
                args = call["function"].get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)

                if fn == "check_combo":
                    result = check_combo(args.get("appliance_names", []), req.context)
                elif fn == "get_test_history":
                    result = get_test_history(req.context, args.get("appliance_filter"))
                else:
                    result = {"error": f"unknown tool {fn}"}

                messages.append({"role": "tool", "content": json.dumps(result)})

        return {"reply": "Sorry, I got stuck reasoning about that — try rephrasing your question."}

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            502,
            "Can't reach Ollama at localhost:11434 — make sure Ollama is installed and running "
            "(it should start automatically after install; try running `ollama list` in a terminal "
            "to check, or `ollama serve` to start it manually).",
        )


@app.get("/health")
def health():
    # Kept as "key_configured" so the existing frontend (which checks this exact field)
    # doesn't need any changes — here it just means "Ollama is reachable and has the model."
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        model_ready = any(MODEL in m for m in models)
        return {
            "ok": True,
            "key_configured": model_ready,
            "detail": None if model_ready else f"Ollama is running but '{MODEL}' isn't pulled yet — run: ollama pull {MODEL}",
        }
    except requests.exceptions.RequestException:
        return {"ok": False, "key_configured": False, "detail": "Ollama isn't running on localhost:11434"}