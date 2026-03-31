"""Veeam Presence — FastAPI agent service endpoints.

Receives messages from the M365 wrapper or Dev UI,
runs the agent with tools, returns structured responses.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# Ensure project root is on path for tools/cards/config imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from agent.agent import run_agent, cleanup_sessions
from response_cache import (
    load_pregenerated, check_pregenerated, check_query_cache, store_query_cache,
)

logger = logging.getLogger(__name__)

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
    logger.info("Loading Presence data caches...")
    from tools.query_office_intel import load_cache
    from tools.query_person import _load_enriched
    load_cache()
    _load_enriched()
    load_pregenerated()
    logger.info("Caches loaded. Ready.")
    yield


app = FastAPI(title="Veeam Presence", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "veeam-presence"}


@app.get("/api/stats")
async def stats():
    """Usage stats endpoint."""
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
    Receive a message, process with agent, return response.

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

    # Layer 1: Check pre-generated cache (instant, no LLM call)
    pregen_response = check_pregenerated(user_text)
    if pregen_response:
        elapsed = time.time() - start_time
        logger.info("QUERY user=%s text=\"%s\" response=pregenerated time=%.3fs", user_id, user_text[:80], elapsed)
        return JSONResponse({"text": pregen_response, "card": None})

    # Layer 2: Check short-TTL query cache (recent identical queries)
    cached_response, cached_card = check_query_cache(user_text, conversation_id)
    if cached_response:
        elapsed = time.time() - start_time
        logger.info("QUERY user=%s text=\"%s\" response=cached time=%.3fs", user_id, user_text[:80], elapsed)
        return JSONResponse({"text": cached_response, "card": cached_card})

    # Layer 3: Call agent (async)
    _cleanup_stale()
    conv = _conversations.get(conversation_id, {"history": [], "last_active": time.time()})

    try:
        response_text, history = await run_agent(user_text, conv["history"], conversation_id)
    except Exception as e:
        _stats["errors"] += 1
        elapsed = time.time() - start_time
        logger.error("QUERY user=%s text=\"%s\" error=\"%s\" time=%.1fs", user_id, user_text[:80], e, elapsed)
        return JSONResponse({
            "text": "Something went wrong processing your request. Try again in a moment.",
            "card": None,
        })

    # Update conversation state
    conv["history"] = history[-_CONV_MAX_HISTORY:]
    conv["last_active"] = time.time()
    _conversations[conversation_id] = conv

    # Primary card source: card_builder stash (populated by tool_render_card)
    from cards import card_builder
    card = card_builder.build_card(conversation_id)

    # Fallback: legacy try_parse_card for backward compat
    if card is None:
        try:
            from cards.renderer import try_parse_card
            card, remaining_text = try_parse_card(response_text)
            if card:
                response_text = remaining_text or ""
        except Exception:
            pass

    # Cache this response for 5 minutes (text + card)
    store_query_cache(user_text, response_text, card, conversation_id)

    elapsed = time.time() - start_time
    has_card = "card" if card else "text"
    logger.info("QUERY user=%s text=\"%s\" response=%s time=%.1fs", user_id, user_text[:80], has_card, elapsed)

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
    cleanup_sessions()
