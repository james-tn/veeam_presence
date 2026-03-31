"""Veeam Presence — M365 Teams wrapper.

Adapted from daily_planner/mvp/m365_wrapper/app.py.
Simplified: no OBO auth chain, no debug chat endpoint.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Any

from fastapi import FastAPI, Request
from microsoft_agents.activity import Activity, ActivityTypes, Attachment
from microsoft_agents.hosting.core import AgentApplication, ApplicationOptions, Authorization, MemoryStorage
from microsoft_agents.hosting.core.turn_context import TurnContext
from microsoft_agents.hosting.fastapi import CloudAdapter, JwtAuthorizationMiddleware, start_agent_process

try:
    from .config import (
        get_bot_app_id,
        build_auth_handlers,
        build_connection_manager,
        get_presence_service_base_url,
        get_wrapper_ack_threshold_seconds,
        get_wrapper_timeout_seconds,
    )
    from .presence_client import PresenceClient
except ImportError:
    from config import (
        get_bot_app_id,
        build_auth_handlers,
        build_connection_manager,
        get_presence_service_base_url,
        get_wrapper_ack_threshold_seconds,
        get_wrapper_timeout_seconds,
    )
    from presence_client import PresenceClient

logger = logging.getLogger(__name__)

WORKING_MESSAGE = "Working on it..."
BUSY_MESSAGE = "I'm still working on your previous request. I'll send the result when it's ready."
CHANNEL_SEND_MAX_ATTEMPTS = 3
CHANNEL_SEND_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class SessionBusyError(RuntimeError):
    """Raised when a session already has an active turn."""


class ConditionalJwtAuthorizationMiddleware(JwtAuthorizationMiddleware):
    """Skip JWT validation on health check endpoint."""

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/health":
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


class CompatAgentApplication(AgentApplication):
    """Workaround: expose adapter + app_id for proactive messaging."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._cloud_adapter: CloudAdapter | None = None

    def set_cloud_adapter(self, adapter: CloudAdapter) -> None:
        self._cloud_adapter = adapter

    @property
    def cloud_adapter(self) -> CloudAdapter | None:
        return self._cloud_adapter

    @property
    def app_id(self) -> str:
        return get_bot_app_id()


class WrapperRuntime:
    """Manages state for the wrapper service."""

    def __init__(self):
        self.presence_client: PresenceClient | None = None
        self.agent_app: CompatAgentApplication | None = None
        self._active_sessions: dict[str, bool] = {}

    def mark_busy(self, session_id: str) -> None:
        if self._active_sessions.get(session_id):
            raise SessionBusyError(session_id)
        self._active_sessions[session_id] = True

    def mark_free(self, session_id: str) -> None:
        self._active_sessions.pop(session_id, None)

    def is_busy(self, session_id: str) -> bool:
        return self._active_sessions.get(session_id, False)


_runtime = WrapperRuntime()


def _build_card_attachment(card_json: dict) -> Attachment:
    """Wrap an Adaptive Card dict as a Teams Attachment."""
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card_json,
    )


async def _send_proactive(
    turn_context: TurnContext,
    text: str,
    card: dict | None = None,
) -> None:
    """Send a proactive message back to the same conversation."""
    reply = Activity(
        type=ActivityTypes.message,
        text=text,
    )
    if card:
        reply.attachments = [_build_card_attachment(card)]

    adapter = _runtime.agent_app.cloud_adapter
    if adapter is None:
        logger.error("Cannot send proactive message: no cloud adapter")
        return

    reference = turn_context.activity.get_conversation_reference()
    continuation_activity = reference.get_continuation_activity()

    async def _callback(ctx: TurnContext) -> None:
        await ctx.send_activity(reply)

    for attempt in range(1, CHANNEL_SEND_MAX_ATTEMPTS + 1):
        try:
            await adapter.continue_conversation(
                _runtime.agent_app.app_id,
                continuation_activity,
                _callback,
            )
            return
        except Exception as exc:
            status = getattr(exc, "status_code", 0)
            if status in CHANNEL_SEND_RETRYABLE_STATUS_CODES and attempt < CHANNEL_SEND_MAX_ATTEMPTS:
                await asyncio.sleep(1.0 * attempt)
                continue
            logger.error("Proactive send failed (attempt %d): %s", attempt, exc)
            raise


async def _handle_message(turn_context: TurnContext, state: Any) -> None:
    """Handle an incoming Teams message."""
    activity = turn_context.activity
    text = (activity.text or "").strip()
    if not text:
        return

    conversation_id = activity.conversation.id if activity.conversation else "default"
    user_id = activity.from_property.id if activity.from_property else "unknown"
    session_id = conversation_id

    # Reject if already busy
    try:
        _runtime.mark_busy(session_id)
    except SessionBusyError:
        await turn_context.send_activity(Activity(type=ActivityTypes.message, text=BUSY_MESSAGE))
        return

    ack_threshold = get_wrapper_ack_threshold_seconds()
    timeout = get_wrapper_timeout_seconds()

    try:
        # Race: agent response vs ack threshold
        agent_task = asyncio.create_task(
            _runtime.presence_client.send_turn(conversation_id, text, user_id)
        )

        done, _ = await asyncio.wait({agent_task}, timeout=ack_threshold)

        if done:
            # Agent responded before ack threshold — send inline
            result = agent_task.result()
            reply_text = result.get("text", "")
            card = result.get("card")

            reply = Activity(type=ActivityTypes.message, text=reply_text)
            if card:
                reply.attachments = [_build_card_attachment(card)]
            await turn_context.send_activity(reply)
        else:
            # Agent still working — send ack, then deliver proactively
            await turn_context.send_activity(
                Activity(type=ActivityTypes.message, text=WORKING_MESSAGE)
            )

            try:
                result = await asyncio.wait_for(agent_task, timeout=timeout - ack_threshold)
                reply_text = result.get("text", "")
                card = result.get("card")
                await _send_proactive(turn_context, reply_text, card)
            except asyncio.TimeoutError:
                logger.error("Agent timed out for session %s", session_id)
                await _send_proactive(
                    turn_context,
                    "Sorry, the request took too long. Please try again.",
                )
            except Exception as exc:
                logger.error("Agent error for session %s: %s", session_id, exc)
                await _send_proactive(
                    turn_context,
                    "Something went wrong. Please try again.",
                )
    finally:
        _runtime.mark_free(session_id)


def create_app() -> FastAPI:
    """Create and configure the M365 wrapper FastAPI application."""
    connection_manager = build_connection_manager()
    storage = MemoryStorage()
    auth_handlers = build_auth_handlers()
    authorization = Authorization(
        storage=storage,
        connection_manager=connection_manager,
        auth_handlers=auth_handlers,
    )

    adapter = CloudAdapter(connection_manager=connection_manager)

    agent_app = CompatAgentApplication(
        options=ApplicationOptions(
            adapter=adapter,
            storage=storage,
            bot_app_id=get_bot_app_id(),
            long_running_messages=False,
        ),
        connection_manager=connection_manager,
        authorization=authorization,
    )

    agent_app.activity(ActivityTypes.message)(_handle_message)
    agent_app.set_cloud_adapter(adapter)

    _runtime.agent_app = agent_app
    _runtime.presence_client = PresenceClient(
        base_url=get_presence_service_base_url(),
        timeout=get_wrapper_timeout_seconds(),
    )

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        healthy = await _runtime.presence_client.health_check()
        logger.info("Presence agent health: %s", "ok" if healthy else "unreachable")
        yield

    fastapi_app = FastAPI(title="Veeam Presence M365 Wrapper", lifespan=lifespan)

    # Set app state for SDK middleware/routing (matches daily_planner pattern)
    fastapi_app.state.agent_configuration = connection_manager.get_default_connection_configuration()
    fastapi_app.state.agent_application = agent_app
    fastapi_app.state.adapter = adapter

    fastapi_app.add_middleware(ConditionalJwtAuthorizationMiddleware)

    @fastapi_app.get("/health")
    async def health():
        return {"status": "ok", "service": "veeam-presence-wrapper"}

    @fastapi_app.post("/api/messages", response_model=None)
    async def messages(request: Request):
        return await start_agent_process(request, agent_app, adapter)

    return fastapi_app


app = create_app()
