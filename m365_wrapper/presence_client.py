"""HTTP client for the Presence agent service."""

from __future__ import annotations

import logging
import httpx

logger = logging.getLogger(__name__)


class PresenceClient:
    """Thin async client to the Presence agent /api/agent/message endpoint."""

    def __init__(self, base_url: str, timeout: float = 300.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def send_turn(self, conversation_id: str, text: str, user_id: str = "unknown") -> dict:
        """Send a message to the agent and return the response dict."""
        url = f"{self._base_url}/api/agent/message"
        payload = {
            "conversation_id": conversation_id,
            "text": text,
            "user_id": user_id,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def health_check(self) -> bool:
        """Check if the agent service is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
