"""Tests for agent API endpoints using httpx.ASGITransport."""

import os
import sys
import pytest
import httpx

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Set up fixture data before importing the app
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "../../tests/fixtures")
import config
config.DATA_DIR = FIXTURE_DIR

# Generate fixtures if needed
pkl_count = len([f for f in os.listdir(FIXTURE_DIR) if f.endswith(".pkl")]) if os.path.isdir(FIXTURE_DIR) else 0
if pkl_count < 14:
    from tests.fixtures.generate_fixtures import generate_all
    generate_all()


@pytest.fixture
def client():
    """Create httpx async client with ASGITransport."""
    from agent.api import app
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "veeam-presence"


@pytest.mark.asyncio
async def test_stats_endpoint(client):
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_queries" in data
    assert "active_conversations" in data


@pytest.mark.asyncio
async def test_message_empty_text(client):
    resp = await client.post("/api/agent/message", json={
        "conversation_id": "test",
        "text": "",
        "user_id": "tester",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "didn't get a message" in data["text"].lower()


@pytest.mark.asyncio
async def test_message_pregenerated_briefing(client):
    """Briefing should hit pre-generated cache — no LLM needed."""
    resp = await client.post("/api/agent/message", json={
        "conversation_id": "test-briefing",
        "text": "give me the daily briefing",
        "user_id": "tester",
    })
    assert resp.status_code == 200
    data = resp.json()
    # Pre-generated cache should return a response
    assert data["text"]
    assert "card" in data


@pytest.mark.asyncio
async def test_message_invalid_json(client):
    resp = await client.post(
        "/api/agent/message",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stats_increment_after_query(client):
    # Get initial stats
    resp1 = await client.get("/api/stats")
    initial = resp1.json()["total_queries"]

    # Send a query (pregenerated, no LLM)
    await client.post("/api/agent/message", json={
        "conversation_id": "test-stats",
        "text": "daily briefing",
        "user_id": "stats-tester",
    })

    resp2 = await client.get("/api/stats")
    assert resp2.json()["total_queries"] > initial
