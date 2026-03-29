"""Veeam Presence — M365 Gateway.

Thin wrapper that connects Teams/Copilot to the agent service.
Handles: auth, typing indicator, message routing, card rendering.

Based on the M365 Agents SDK (botbuilder) pattern from Veeam Signal.
"""

import os
import json
import aiohttp
from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes, Attachment

AGENT_SERVICE_URL = os.environ.get("AGENT_SERVICE_URL", "http://localhost:8000")
BOT_APP_ID = os.environ.get("BOT_APP_ID", "")
BOT_APP_PASSWORD = os.environ.get("BOT_APP_PASSWORD", "")

settings = BotFrameworkAdapterSettings(BOT_APP_ID, BOT_APP_PASSWORD)
adapter = BotFrameworkAdapter(settings)


async def on_message(turn_context: TurnContext):
    """Handle incoming message from Teams/Copilot."""
    # Send typing indicator immediately
    await turn_context.send_activity(Activity(type=ActivityTypes.typing))

    user_text = turn_context.activity.text or ""
    conversation_id = turn_context.activity.conversation.id or "default"

    # Call agent service
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{AGENT_SERVICE_URL}/api/agent/message",
                json={
                    "conversation_id": conversation_id,
                    "text": user_text,
                    "user_id": turn_context.activity.from_property.id or "",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    data = {"text": "Something went wrong. Try again in a moment.", "card": None}
    except Exception as e:
        print(f"Agent service error: {e}")
        data = {"text": "I'm having trouble connecting right now. Try again shortly.", "card": None}

    # Send response
    card = data.get("card")
    text = data.get("text", "")

    if card:
        # Send as Adaptive Card attachment
        attachment = Attachment(
            content_type="application/vnd.microsoft.card.adaptive",
            content=card,
        )
        reply = Activity(
            type=ActivityTypes.message,
            attachments=[attachment],
        )
        # Include text as fallback for clients that don't render cards
        if text:
            reply.text = text
        await turn_context.send_activity(reply)
    elif text:
        await turn_context.send_activity(text)


async def messages(req: web.Request) -> web.Response:
    """Main webhook endpoint for Teams/Copilot."""
    if "application/json" not in req.headers.get("Content-Type", ""):
        return web.Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    try:
        await adapter.process_activity(activity, auth_header, on_message)
        return web.Response(status=200)
    except Exception as e:
        print(f"Adapter error: {e}")
        return web.Response(status=500)


async def health(req: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "presence-gateway"})


app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/health", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)
