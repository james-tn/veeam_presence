"""Tests for the M365 wrapper — mocked runtime."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Skip tests that require microsoft_agents.hosting.fastapi if not installed
try:
    import microsoft_agents.hosting.fastapi  # noqa: F401
    _HAS_MS_AGENTS = True
except (ImportError, ModuleNotFoundError):
    _HAS_MS_AGENTS = False

ms_agents_required = pytest.mark.skipif(
    not _HAS_MS_AGENTS, reason="microsoft-agents SDK not installed"
)


class TestPresenceClient:
    """Tests for the HTTP client."""

    @pytest.mark.asyncio
    async def test_send_turn(self):
        from m365_wrapper.presence_client import PresenceClient
        client = PresenceClient(base_url="http://localhost:8000")
        assert client._base_url == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_unreachable(self):
        from m365_wrapper.presence_client import PresenceClient
        client = PresenceClient(base_url="http://localhost:99999")
        result = await client.health_check()
        assert result is False

    def test_client_strips_trailing_slash(self):
        from m365_wrapper.presence_client import PresenceClient
        client = PresenceClient(base_url="http://localhost:8000/")
        assert client._base_url == "http://localhost:8000"


@ms_agents_required
class TestWrapperRuntime:
    """Tests for session management."""

    def test_mark_busy_and_free(self):
        from m365_wrapper.app import WrapperRuntime
        runtime = WrapperRuntime()
        runtime.mark_busy("session-1")
        assert runtime.is_busy("session-1")
        runtime.mark_free("session-1")
        assert not runtime.is_busy("session-1")

    def test_mark_busy_twice_raises(self):
        from m365_wrapper.app import WrapperRuntime, SessionBusyError
        runtime = WrapperRuntime()
        runtime.mark_busy("session-1")
        with pytest.raises(SessionBusyError):
            runtime.mark_busy("session-1")


@ms_agents_required
class TestCardAttachment:
    """Tests for card wrapping."""

    def test_build_card_attachment(self):
        from m365_wrapper.app import _build_card_attachment
        card = {"type": "AdaptiveCard", "body": []}
        attachment = _build_card_attachment(card)
        assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
        assert attachment["content"] == card
