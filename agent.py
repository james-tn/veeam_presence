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

    # Build messages — trim to last 10 exchanges to control tokens
    messages = list(history[-20:])  # 10 pairs = 20 messages
    messages.append({"role": "user", "content": user_message})

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
