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

    # Register user for proactive briefing (auto-register on first message)
    try:
        async with aiohttp.ClientSession() as reg_session:
            await reg_session.post(
                f"{AGENT_SERVICE_URL}/api/register_user",
                json={
                    "conversation_id": turn_context.activity.conversation.id,
                    "user_id": turn_context.activity.from_property.id or "",
                    "service_url": turn_context.activity.service_url or "",
                },
                timeout=aiohttp.ClientTimeout(total=2),
            )
    except Exception:
        pass  # Non-critical — don't block the response

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


async def proactive(req: web.Request) -> web.Response:
    """Send a proactive message to a user (called by briefing scheduler)."""
    try:
        body = await req.json()
        conversation_id = body.get("conversation_id")
        text = body.get("text", "")

        if not conversation_id or not text:
            return web.json_response({"error": "Missing conversation_id or text"}, status=400)

        # Build a conversation reference and send proactively
        service_url = body.get("service_url", "https://smba.trafficmanager.net/teams/")
        conversation_ref = {
            "conversation": {"id": conversation_id},
            "serviceUrl": service_url,
            "bot": {"id": BOT_APP_ID},
        }

        async def send_callback(turn_context: TurnContext):
            await turn_context.send_activity(text)

        await adapter.continue_conversation(
            conversation_ref, send_callback, BOT_APP_ID
        )
        return web.json_response({"status": "sent"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


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
app.router.add_post("/api/proactive", proactive)
app.router.add_get("/health", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)
