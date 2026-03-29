"""Veeam Presence — FastAPI agent service.

Receives messages from the M365 gateway, runs Claude with tools,
returns structured responses (card JSON or plain text).
"""

import os
import sys
import json
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(__file__))
import config
from agent import run_agent
from tools.query_office_intel import load_cache
from tools.query_person import _load_enriched

# Conversation state — in-memory, keyed by conversation ID
_conversations = {}
_CONV_TTL = 1800  # 30 minutes
_CONV_MAX_HISTORY = 20  # 10 pairs


@asynccontextmanager
async def lifespan(app):
    """Pre-load caches on startup."""
    print("Loading Presence data caches...")
    load_cache()
    _load_enriched()
    print("Caches loaded. Ready.")
    yield


app = FastAPI(title="Veeam Presence", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "veeam-presence"}


@app.post("/api/agent/message")
async def handle_message(request: Request):
    """
    Receive a message from the gateway, process with Claude, return response.

    Expected body: {"conversation_id": "...", "text": "...", "user_id": "..."}
    Returns: {"text": "...", "card": {...} or null}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    conversation_id = body.get("conversation_id", "default")
    user_text = body.get("text", "").strip()
    if not user_text:
        return JSONResponse({"text": "I didn't get a message. Try asking about office attendance.", "card": None})

    # Get or create conversation state
    _cleanup_stale()
    conv = _conversations.get(conversation_id, {"history": [], "last_active": time.time()})

    # Run agent
    try:
        response_text, history = run_agent(user_text, conv["history"])
    except Exception as e:
        print(f"Agent error: {e}")
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
        pass  # Card parsing failed, send as plain text

    return JSONResponse({
        "text": response_text,
        "card": card,
    })


def _cleanup_stale():
    """Remove expired conversations."""
    now = time.time()
    expired = [k for k, v in _conversations.items() if now - v["last_active"] > _CONV_TTL]
    for k in expired:
        del _conversations[k]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
