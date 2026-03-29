"""Render structured response objects into Adaptive Card JSON.

Takes the JSON that Claude outputs and maps it to the appropriate
card template. Falls back to plain text if no card structure detected.
"""

import json
from cards.templates import (
    briefing_card, office_detail_card, leaderboard_card, person_card,
    comparison_card, trending_card, visitors_card, who_was_in_card,
    welcome_card, overview_card, error_card,
)


def render_card(structured_response):
    """
    Convert a structured response dict to Adaptive Card JSON.

    The structured_response should have a 'template' field indicating
    which card type to render. If no template is specified, returns None
    (caller should use plain text).
    """
    if not isinstance(structured_response, dict):
        return None

    template = structured_response.get("template", "")

    if template == "briefing":
        return briefing_card(structured_response)
    elif template == "office_detail":
        return office_detail_card(structured_response)
    elif template == "leaderboard":
        return leaderboard_card(structured_response)
    elif template == "person":
        return person_card(structured_response)
    elif template == "comparison":
        return comparison_card(structured_response)
    elif template == "trending":
        return trending_card(structured_response)
    elif template == "visitors":
        return visitors_card(structured_response)
    elif template == "who_was_in":
        return who_was_in_card(structured_response)
    elif template == "welcome":
        return welcome_card()
    elif template == "overview":
        return overview_card()
    elif template == "error":
        return error_card(structured_response.get("message", "An error occurred."))
    else:
        # Unknown template or standard_insight — build a generic card
        return _generic_card(structured_response)


def _generic_card(data):
    """Fallback card for standard_insight or unrecognized templates."""
    body = []

    summary = data.get("summary", data.get("headline", ""))
    if summary:
        body.append({"type": "TextBlock", "text": summary, "weight": "Bolder", "size": "Medium", "wrap": True})

    text_body = data.get("body", "")
    if text_body:
        body.append({"type": "TextBlock", "text": text_body, "wrap": True, "size": "Small"})

    facts = data.get("facts", [])
    if facts:
        body.append({
            "type": "FactSet",
            "facts": [{"title": f.get("title", ""), "value": f.get("value", "")} for f in facts[:8]],
        })

    context = data.get("context_note", "")
    if context:
        body.append({"type": "TextBlock", "text": context, "size": "Small", "isSubtle": True, "wrap": True})

    actions = []
    for a in data.get("actions", [])[:3]:
        actions.append({
            "type": "Action.Submit",
            "title": a.get("label", ""),
            "data": {"msteams": {"type": "imBack", "value": a.get("message", "")}},
        })

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
    if actions:
        card["actions"] = actions

    return card


def try_parse_card(text):
    """
    Try to extract and render a card from Claude's text response.
    Returns (card_json, remaining_text) or (None, original_text).
    """
    # Look for JSON block
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            json_str = text[start:end].strip()
            data = json.loads(json_str)

            if data.get("card"):
                card = render_card(data)
                # Text before/after the JSON block
                before = text[:text.index("```json")].strip()
                after = text[end + 3:].strip()
                remaining = f"{before}\n{after}".strip() if before or after else ""
                return card, remaining

        except (json.JSONDecodeError, ValueError):
            pass

    elif "```" in text:
        try:
            start = text.index("```") + 3
            end = text.index("```", start)
            json_str = text[start:end].strip()
            if json_str.startswith("{"):
                data = json.loads(json_str)
                if data.get("card"):
                    card = render_card(data)
                    before = text[:text.index("```")].strip()
                    after = text[end + 3:].strip()
                    remaining = f"{before}\n{after}".strip() if before or after else ""
                    return card, remaining
        except (json.JSONDecodeError, ValueError):
            pass

    return None, text
