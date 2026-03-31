"""Build Adaptive Cards from tool results — LLM-directed card generation.

The LLM decides IF and WHAT card to show by calling render_card().
Tool wrappers stash raw data; render_card picks the template + provides
title/highlights; build_card() assembles the final Adaptive Card JSON.

Flow:
  1. tool_query_* runs → stashes raw dict via push()
  2. LLM reads tool result, decides a card is useful
  3. LLM calls render_card(card_type, title, highlights)
     → request_card() stores the request + builds from stashed data
  4. After agent.run(), caller reads build_card() → Adaptive Card JSON
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from cards.templates import (
    briefing_card,
    data_card,
    office_detail_card,
    person_card,
    trending_card,
    visitors_card,
    who_was_in_card,
)

logger = logging.getLogger(__name__)

# ── Per-conversation stash ────────────────────────────────────────────────
_data_stash: dict[str, list[dict]] = {}   # conversation_id -> [{tool, data}]
_card_stash: dict[str, dict] = {}          # conversation_id -> built card
_lock = threading.Lock()

# Maps card_type → template function that takes raw data dict
_TYPED_TEMPLATES = {
    "briefing": briefing_card,
    "office_detail": office_detail_card,
    "person": person_card,
    "trending": trending_card,
    "visitors": visitors_card,
    "who_was_in": who_was_in_card,
}


def clear(conversation_id: str) -> None:
    """Reset stashes at the start of each turn."""
    with _lock:
        _data_stash.pop(conversation_id, None)
        _card_stash.pop(conversation_id, None)


def push(conversation_id: str, tool_name: str, raw_dict: dict) -> None:
    """Record a tool result for later card generation."""
    with _lock:
        _data_stash.setdefault(conversation_id, []).append(
            {"tool": tool_name, "data": raw_dict}
        )


def request_card(
    conversation_id: str,
    card_type: str,
    title: str,
    highlights: list[str] | None = None,
    follow_ups: list[list[str]] | None = None,
) -> str:
    """Called by the render_card tool. Builds the card and stashes it.

    Returns a short confirmation string for the LLM.
    """
    with _lock:
        data_results = list(_data_stash.get(conversation_id, []))

    if not data_results:
        return "No tool data available — call a query tool first, then render_card."

    # Use the last tool result as the data source
    last_data = data_results[-1]["data"]

    try:
        template_fn = _TYPED_TEMPLATES.get(card_type)
        if template_fn:
            card = template_fn(last_data)
        else:
            # Generic card — LLM provides title + highlights, template renders them
            actions_list = None
            if follow_ups:
                actions_list = [(f[0], f[1]) for f in follow_ups[:3] if len(f) >= 2]
            card = data_card(title, highlights or [], actions_list)

        if card:
            with _lock:
                _card_stash[conversation_id] = card
            return f"Card rendered: {card_type} — '{title}'"
        else:
            return "Template returned empty card."
    except Exception as e:
        logger.error("Card build error: %s", e)
        return f"Card build error: {e}"


def build_card(conversation_id: str) -> Optional[dict]:
    """Return the Adaptive Card JSON dict if the LLM requested one, else None."""
    with _lock:
        card = _card_stash.pop(conversation_id, None)
        _data_stash.pop(conversation_id, None)
    return card
