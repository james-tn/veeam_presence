"""Proactive daily briefing — pushes the morning briefing to registered users.

Runs as a scheduled job after the pipeline completes.
Uses the M365 Agents SDK proactive messaging to send to each user's 1:1 chat.

User registration: when a user first messages Presence, the gateway stores
their conversation reference. This script reads those references and sends
the pre-generated briefing to each one.
"""

import os
import sys
import json
import pickle
import aiohttp
import asyncio

sys.path.insert(0, os.path.dirname(__file__))
import config

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:3978")
USER_REGISTRY_PATH = os.path.join(config.DATA_DIR, "registered_users.json")


def get_briefing_text():
    """Load the pre-generated briefing."""
    path = os.path.join(config.DATA_DIR, "pregenerated.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        pregen = pickle.load(f)
    return pregen.get("briefing")


def get_registered_users():
    """Load the list of users who have chatted with Presence."""
    if not os.path.exists(USER_REGISTRY_PATH):
        return []
    with open(USER_REGISTRY_PATH, "r") as f:
        return json.load(f)


def register_user(conversation_id, user_id, service_url):
    """Register a user for proactive messaging (called by gateway on first message)."""
    users = get_registered_users()
    existing = {u["user_id"] for u in users}
    if user_id not in existing:
        users.append({
            "conversation_id": conversation_id,
            "user_id": user_id,
            "service_url": service_url,
        })
        os.makedirs(os.path.dirname(USER_REGISTRY_PATH), exist_ok=True)
        with open(USER_REGISTRY_PATH, "w") as f:
            json.dump(users, f, indent=2)


async def send_briefing():
    """Send the daily briefing to all registered users via the gateway."""
    briefing = get_briefing_text()
    if not briefing:
        print("No briefing available — pipeline may not have run yet.")
        return

    users = get_registered_users()
    if not users:
        print("No registered users — nobody has chatted with Presence yet.")
        return

    print(f"Sending briefing to {len(users)} users...")

    async with aiohttp.ClientSession() as session:
        for user in users:
            try:
                await session.post(
                    f"{GATEWAY_URL}/api/proactive",
                    json={
                        "conversation_id": user["conversation_id"],
                        "user_id": user["user_id"],
                        "service_url": user["service_url"],
                        "text": briefing,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                print(f"  Sent to {user['user_id']}")
            except Exception as e:
                print(f"  Failed for {user['user_id']}: {e}")


if __name__ == "__main__":
    asyncio.run(send_briefing())
