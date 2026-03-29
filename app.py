"""Veeam Presence — FastAPI agent service.

Receives messages from the M365 gateway, runs Claude with tools,
returns structured responses (card JSON or plain text).
Logs every request for usage monitoring.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(__file__))
import config
from agent import run_agent
from tools.query_office_intel import load_cache
from tools.query_person import _load_enriched

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("presence")

# Conversation state — in-memory, keyed by conversation ID
_conversations = {}
_CONV_TTL = 1800  # 30 minutes
_CONV_MAX_HISTORY = 20  # 10 pairs

# Usage stats — in-memory, reset on restart
_stats = {
    "total_queries": 0,
    "queries_today": 0,
    "today_date": "",
    "unique_users": set(),
    "errors": 0,
}


@asynccontextmanager
async def lifespan(app):
    """Pre-load caches on startup."""
    log.info("Loading Presence data caches...")
    load_cache()
    _load_enriched()
    log.info("Caches loaded. Ready.")
    yield


app = FastAPI(title="Veeam Presence", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "veeam-presence"}


@app.get("/api/stats")
async def stats():
    """Usage stats endpoint — check how much the agent is being used."""
    return {
        "total_queries": _stats["total_queries"],
        "queries_today": _stats["queries_today"],
        "today": _stats["today_date"],
        "unique_users": len(_stats["unique_users"]),
        "errors": _stats["errors"],
        "active_conversations": len(_conversations),
    }


@app.post("/api/agent/message")
async def handle_message(request: Request):
    """
    Receive a message from the gateway, process with Claude, return response.

    Expected body: {"conversation_id": "...", "text": "...", "user_id": "..."}
    Returns: {"text": "...", "card": {...} or null}
    """
    start_time = time.time()

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    conversation_id = body.get("conversation_id", "default")
    user_text = body.get("text", "").strip()
    user_id = body.get("user_id", "unknown")

    if not user_text:
        return JSONResponse({"text": "I didn't get a message. Try asking about office attendance.", "card": None})

    # Track usage
    _track_query(user_id)

    # Get or create conversation state
    _cleanup_stale()
    conv = _conversations.get(conversation_id, {"history": [], "last_active": time.time()})

    # Run agent
    try:
        response_text, history = run_agent(user_text, conv["history"])
    except Exception as e:
        _stats["errors"] += 1
        elapsed = time.time() - start_time
        log.error(f"QUERY user={user_id} text=\"{user_text[:80]}\" error=\"{e}\" time={elapsed:.1f}s")
        return JSONResponse({
            "text": "Something went wrong processing your request. Try again in a moment.",
            "card": None,
        })

    # Update conversation state
    conv["history"] = history[-_CONV_MAX_HISTORY:]
    conv["last_active"] = time.time()
    _conversations[conversation_id] = conv

    # Try to extract card from response
    card = None
    try:
        from cards.renderer import try_parse_card
        card, remaining_text = try_parse_card(response_text)
        if card:
            response_text = remaining_text or ""
    except Exception:
        pass

    elapsed = time.time() - start_time
    has_card = "card" if card else "text"
    log.info(f"QUERY user={user_id} text=\"{user_text[:80]}\" response={has_card} time={elapsed:.1f}s")

    return JSONResponse({
        "text": response_text,
        "card": card,
    })


def _track_query(user_id):
    """Update usage counters."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _stats["today_date"] != today:
        _stats["queries_today"] = 0
        _stats["today_date"] = today
    _stats["total_queries"] += 1
    _stats["queries_today"] += 1
    _stats["unique_users"].add(user_id)


def _cleanup_stale():
    """Remove expired conversations."""
    now = time.time()
    expired = [k for k, v in _conversations.items() if now - v["last_active"] > _CONV_TTL]
    for k in expired:
        del _conversations[k]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
