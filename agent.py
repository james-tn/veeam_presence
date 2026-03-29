"""Veeam Presence — Claude orchestration with tool_use."""

import json
import anthropic
import config
from system_prompt import SYSTEM_PROMPT
from tools.query_office_intel import query_office_intel, TOOL_SCHEMA as OFFICE_SCHEMA
from tools.query_person import query_person, TOOL_SCHEMA as PERSON_SCHEMA

TOOLS = [OFFICE_SCHEMA, PERSON_SCHEMA]

TOOL_DISPATCH = {
    "query_office_intel": query_office_intel,
    "query_person": query_person,
}


def _add_routing_hint(message):
    """
    Add routing hints for queries where Claude's priors override the prompt.
    Returns the message with a system hint prepended if needed.
    """
    lower = message.lower()

    # Travel/visitor queries
    travel_words = ["travel", "traveling", "travelling", "visiting other", "between offices",
                    "cross-office", "who went to", "who visited"]
    if any(w in lower for w in travel_words):
        return (f"[ROUTING: This is a cross-office travel question. You have this data. "
                f"Call query_person with query_type='visitors' immediately.]\n\n{message}")

    # Team sync queries
    sync_words = ["team sync", "same days", "overlapping", "teams coordin", "teams coming in"]
    if any(w in lower for w in sync_words):
        return (f"[ROUTING: This is a team sync question. You have this data. "
                f"Call query_person with query_type='team_sync' immediately.]\n\n{message}")

    # Ghost / declining office queries
    ghost_words = ["ghost", "declining", "dying", "going quiet", "offices quiet",
                   "offices losing", "offices getting worse"]
    if any(w in lower for w in ghost_words):
        return (f"[ROUTING: This is about which offices are changing. You have this data. "
                f"Call query_person with query_type='ghost' immediately.]\n\n{message}")

    # Org leader rollups
    org_words = ["org leader", "organization leader", "whose org", "leader's org",
                 "john jester", "matthew bishop", "tim pfaelzer", "rehan jalil"]
    if any(w in lower for w in org_words):
        return (f"[ROUTING: This is about org leader attendance rollups. You have this data. "
                f"Call query_person with query_type='org_leader'.]\n\n{message}")

    # Manager gravity
    gravity_words = ["manager gravity", "manager pull", "does the manager", "when the manager",
                     "manager come in", "team follow"]
    if any(w in lower for w in gravity_words):
        return (f"[ROUTING: This is about manager gravity. You have this data. "
                f"Call query_person with query_type='manager_gravity'.]\n\n{message}")

    # New hires
    hire_words = ["new hire", "new hires", "recent hire", "recently hired", "onboarding",
                  "integrating", "integration"]
    if any(w in lower for w in hire_words):
        return (f"[ROUTING: This is about new hire integration. You have this data. "
                f"Call query_person with query_type='new_hires'.]\n\n{message}")

    # Weekend
    weekend_words = ["weekend", "saturday", "sunday", "after hours"]
    if any(w in lower for w in weekend_words):
        return (f"[ROUTING: This is about weekend attendance. You have this data. "
                f"Call query_person with query_type='weekend'.]\n\n{message}")

    return message


def run_agent(user_message, history=None):
    """
    Run one turn of the Presence agent.

    Args:
        user_message: The user's question (string)
        history: List of prior message dicts [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        (response_text, updated_history)
        response_text is either plain text or a JSON string (card response)
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    history = history or []

    # Add routing hints for tricky queries
    routed_message = _add_routing_hint(user_message)

    # Build messages — trim to last 10 exchanges, ensure starts with user
    messages = list(history[-20:])
    if messages and messages[0].get("role") != "user":
        messages = messages[1:]  # Drop orphaned assistant message
    messages.append({"role": "user", "content": routed_message})

    # Claude API call with tools
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    # Tool use loop — Claude may call tools, then we feed results back
    while response.stop_reason == "tool_use":
        # Find tool use blocks
        tool_results = []
        assistant_content = response.content

        for block in assistant_content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                print(f"  [tool: {tool_name}({json.dumps(tool_input, default=str)})]", flush=True)

                # Dispatch
                func = TOOL_DISPATCH.get(tool_name)
                if func:
                    try:
                        result = func(**tool_input)
                        result_str = json.dumps(result, default=str)
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)})
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_str,
                })

        # Feed tool results back to Claude
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    # Extract final text response
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    # Update history (trimmed — only user messages and final text, not tool calls)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": final_text})

    return final_text, history
