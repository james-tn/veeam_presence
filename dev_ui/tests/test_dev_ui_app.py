"""Tests for the Dev UI app."""

import pytest
import httpx


@pytest.fixture
def dev_app():
    """Get the Dev UI FastAPI app."""
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    import config
    config.DATA_DIR = os.path.join(os.path.dirname(__file__), "../../tests/fixtures")
    from dev_ui.app import app
    return app


@pytest.mark.asyncio
async def test_healthz(dev_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dev_app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_page_returns_html(dev_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dev_app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Veeam Presence" in resp.text

@pytest.mark.asyncio
async def test_chat_page_has_suggestions(dev_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dev_app), base_url="http://test") as client:
        resp = await client.get("/")
    assert "daily briefing" in resp.text

@pytest.mark.asyncio
async def test_chat_reset(dev_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dev_app), base_url="http://test", follow_redirects=True) as client:
        resp = await client.post("/chat/reset")
    assert resp.status_code == 200
