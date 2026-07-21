"""
Solar Advisor — Agent backend

A thin, stateless layer that lets you ask natural-language questions about your
solar budget ("can I run the AC and washing machine right now?") and have Claude
reason about it using REAL numbers computed by the frontend — not guesses.

Design principle: the LLM never invents wattage math. It calls a tool that does
plain arithmetic against the exact data the frontend already computed (available
watts from the physics model, your appliance list, your logged test history).
The model's job is only to reason and explain in natural language — the safety-
critical numbers stay deterministic.

Run:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8787
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

app = FastAPI(title="Solar Advisor Agent")

# Allow the static frontend (served from anywhere — file://, localhost, or your
# deployed Vercel/Netlify URL) to call this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-4-6"


# ---------- Request/response schema ----------

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
    source: str            # "satellite" | "model" | "manual override"
    ageMin: Optional[int] = None
    marginPct: float
    inverterCap: float
    appliances: list[Appliance]
    recentLogs: list[LogEntry] = []


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    context: ChatContext


# ---------- Tool: deterministic appliance-fit check ----------
# This is the only place wattage arithmetic happens. The model calls it; it never
# computes the numbers itself.

def check_combo(appliance_names: list[str], context: ChatContext) -> dict:
    by_name = {a.name.lower(): a for a in context.appliances}
    matched, unmatched = [], []
    for n in appliance_names:
        hit = by_name.get(n.lower())
        if hit:
            matched.append(hit)
        else:
            # loose substring match as a fallback
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


TOOLS = [
    {
        "name": "check_combo",
        "description": (
            "Check whether a specific combination of appliances fits within the "
            "current solar power budget. Always use this instead of doing the "
            "arithmetic yourself — it uses the live, physics-model-derived available "
            "wattage, not an assumption."
        ),
        "input_schema": {
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
    {
        "name": "get_test_history",
        "description": (
            "Look up real logged outcomes from past tests on this system (whether the "
            "inverter actually held or tripped for a given combination). Use this when "
            "the person asks about reliability or past experience, not just the model's "
            "prediction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appliance_filter": {
                    "type": "string",
                    "description": "Optional: filter logs to entries mentioning this appliance name",
                }
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


@app.post("/chat")
def chat(req: ChatRequest):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(500, "ANTHROPIC_API_KEY not set on the server.")

    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})

    # Give the model a compact snapshot of current state up front so it has context
    # even before calling a tool.
    snapshot = (
        f"[Current state: {req.context.availableWatts}W available "
        f"(source: {req.context.source}"
        + (f", {req.context.ageMin}m old" if req.context.ageMin is not None else "")
        + f"), inverter cap {req.context.inverterCap}W, safety margin "
        f"{req.context.marginPct}%. Known appliances: "
        + ", ".join(f"{a.name} ({a.watt}W, {'on' if a.active else 'off'})" for a in req.context.appliances)
        + "]"
    )
    messages[-1]["content"] = f"{snapshot}\n\n{req.message}"

    for _ in range(4):  # cap tool-use loop
        resp = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if resp.stop_reason != "tool_use":
            final_text = "".join(b.text for b in resp.content if b.type == "text")
            return {"reply": final_text}

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "check_combo":
                result = check_combo(block.input.get("appliance_names", []), req.context)
            elif block.name == "get_test_history":
                result = get_test_history(req.context, block.input.get("appliance_filter"))
            else:
                result = {"error": f"unknown tool {block.name}"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return {"reply": "Sorry, I got stuck reasoning about that — try rephrasing your question."}


@app.get("/health")
def health():
    return {"ok": True, "key_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}
