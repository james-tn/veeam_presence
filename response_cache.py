"""Response cache — pre-generated responses + short-TTL query cache.

Two layers:
1. Pre-generated: built by pipeline, same for all users, instant
2. Query cache: recent Claude responses cached for 5 minutes
"""

import os
import time
import pickle
import hashlib
import config

_pregen = {}
_query_cache = {}
_CACHE_TTL = 300  # 5 minutes


def load_pregenerated():
    """Load pre-generated responses from pipeline output."""
    global _pregen
    path = os.path.join(config.DATA_DIR, "pregenerated.pkl")
    if os.path.exists(path):
        with open(path, "rb") as f:
            _pregen = pickle.load(f)
        print(f"  Pre-generated cache loaded: {len(_pregen)} responses")
    else:
        print("  No pre-generated cache found")


def check_pregenerated(user_message):
    """
    Check if this query matches a pre-generated response.
    Returns the response text if matched, None otherwise.
    """
    if not _pregen:
        return None

    q = user_message.lower().strip()

    # Briefing matches
    briefing_phrases = ["daily briefing", "briefing", "all offices", "office rundown",
                        "how are our offices", "how are offices"]
    if any(p in q for p in briefing_phrases):
        return _pregen.get("briefing")

    # Office detail matches
    for key, response in _pregen.items():
        if key.startswith("office:"):
            office_name = key.split(":", 1)[1]
            if office_name in q or any(word in q for word in office_name.split()):
                # Make sure it's an office question, not a person or leaderboard question
                if "leaderboard" not in q and "top" not in q and "who" not in q and "compare" not in q:
                    return response

    # Leaderboard matches
    for key, response in _pregen.items():
        if key.startswith("leaderboard:"):
            office_name = key.split(":", 1)[1]
            if ("leaderboard" in q or "top" in q or "showing up" in q) and \
               (office_name in q or any(word in q for word in office_name.split())):
                return response

    return None


def check_query_cache(user_message):
    """Check short-TTL cache for recent identical queries."""
    key = _cache_key(user_message)
    entry = _query_cache.get(key)
    if entry and time.time() - entry["time"] < _CACHE_TTL:
        return entry["response"]
    return None


def store_query_cache(user_message, response):
    """Cache a Claude response for 5 minutes."""
    key = _cache_key(user_message)
    _query_cache[key] = {"response": response, "time": time.time()}
    # Cleanup old entries
    now = time.time()
    expired = [k for k, v in _query_cache.items() if now - v["time"] > _CACHE_TTL]
    for k in expired:
        del _query_cache[k]


def _cache_key(text):
    """Normalize query to a cache key."""
    normalized = text.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()
