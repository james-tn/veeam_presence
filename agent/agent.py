"""Veeam Presence — Microsoft Agent Framework orchestration with Azure OpenAI."""

import contextvars
import logging
import time
from dataclasses import dataclass, field

try:
    from agent_framework.azure import AzureOpenAIChatClient
    from agent_framework import Skill, SkillsProvider
    _HAS_AGENT_FRAMEWORK = True
except ImportError:
    # Allow module to load for testing without agent_framework installed
    _HAS_AGENT_FRAMEWORK = False

    @dataclass
    class Skill:
        name: str = ""
        description: str = ""
        content: str = ""

    class SkillsProvider:
        def __init__(self, skills=None):
            self.skills = skills or []

try:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AsyncAzureOpenAI
except ImportError:
    DefaultAzureCredential = None
    get_bearer_token_provider = None
    AsyncAzureOpenAI = None

from agent.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,
    AZURE_OPENAI_API_VERSION,
)
from system_prompt import SYSTEM_PROMPT
from cards import card_builder

logger = logging.getLogger(__name__)

_agent = None
_sessions = {}  # conversation_id -> {"session": AgentSession, "last_active": float}
_SESSION_TTL = 1800  # 30 minutes

# Per-coroutine conversation ID for card stashing (async-safe)
_conversation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_conversation_id_var", default="default"
)


# ---------------------------------------------------------------------------
# Card-stashing tool wrappers — these replace the plain typed wrappers.
# They call the underlying tool, stash the raw dict for card generation,
# then return the JSON string to the LLM.
# ---------------------------------------------------------------------------
from typing import Annotated, Optional, Literal
from pydantic import Field


def tool_query_office_intel(
    office: Annotated[Optional[str], Field(description="Office name. Omit for all offices.")] = None,
) -> str:
    """Get office headcounts, top people, health scores, and team info.
    No office = all offices. With office name = that office's full detail."""
    import json
    from tools.query_office_intel import query_office_intel
    result = query_office_intel(office=office)
    card_builder.push(_conversation_id_var.get(), "query_office_intel", result)
    return json.dumps(result, default=str)


def tool_query_person(
    person: Annotated[Optional[str], Field(description="Person's name or email (e.g. 'Scott Jackson', 'scott.jackson@veeam.com')")] = None,
    office: Annotated[Optional[str], Field(description="Office name — used with query_type='who_was_in' or to filter results")] = None,
    query_type: Annotated[Optional[Literal[
        "pattern", "who_was_in", "trending_up", "trending_down", "visitors",
        "team_sync", "ghost", "org_leader", "manager_gravity", "new_hires", "weekend"
    ]], Field(description="Type of query. Default: 'pattern' for person queries, 'who_was_in' for office queries.")] = None,
) -> str:
    """Get data about people and teams. Query types: pattern (person lookup), who_was_in (office attendees),
    trending_up/trending_down, visitors (cross-office travel), team_sync, ghost (declining offices),
    org_leader, manager_gravity, new_hires, weekend."""
    import json
    from tools.query_person import query_person
    result = query_person(person=person, office=office, query_type=query_type)
    card_builder.push(_conversation_id_var.get(), "query_person", result)
    return json.dumps(result, default=str)


def tool_render_card(
    card_type: Annotated[Literal[
        "briefing", "office_detail", "leaderboard", "person",
        "trending", "visitors", "who_was_in", "ghost", "team_sync",
        "org_leader", "manager_gravity", "new_hires", "weekend", "generic"
    ], Field(description="Card template to use. Use a specific type when it matches the data, or 'generic' for anything else.")],
    title: Annotated[str, Field(description="Card title — short, factual (e.g. 'Prague Office' or 'Offices Showing Decay')")],
    highlights: Annotated[Optional[list[str]], Field(description="Key data points to show on the card. Each string is one line. Used for generic/ghost/team_sync/org_leader/manager_gravity/new_hires/weekend cards.")] = None,
    follow_ups: Annotated[Optional[list[list[str]]], Field(description="Up to 3 follow-up actions as [button_label, message_to_send] pairs.")] = None,
) -> str:
    """Render a visual Adaptive Card for the user. Call AFTER a query tool when
    the data is best shown visually (tables, lists, comparisons, rankings).
    Do NOT call for simple factual answers that fit in 1-2 sentences."""
    return card_builder.request_card(
        conversation_id=_conversation_id_var.get(),
        card_type=card_type,
        title=title,
        highlights=highlights,
        follow_ups=follow_ups,
    )


# ---------------------------------------------------------------------------
# Agent Skills — replaces _add_routing_hint() keyword matching (65 lines)
# LLM sees only name + description in system prompt (~50-100 tokens each).
# When a query matches, LLM calls load_skill() → full instructions injected.
# ---------------------------------------------------------------------------

SKILLS = [
    Skill(
        name="office-intelligence",
        description="Office headcounts, health scores, day-of-week patterns, and team breakdowns",
        content=(
            "Call tool_query_office_intel. Without an office name → global summary of all offices. "
            "With an office name → that office's full detail including headcount, rate, deviation, "
            "day-of-week pattern, top people, team breakdown, and health score."
        ),
    ),
    Skill(
        name="person-attendance",
        description="Individual person's attendance pattern, schedule, presence history",
        content=(
            "Call tool_query_person with the person's name or email. Default query_type='pattern' "
            "returns their attendance days, preferred days, dwell time, and trend."
        ),
    ),
    Skill(
        name="travel-visitors",
        description="Cross-office travelers, visitors from other offices, who visited where",
        content=(
            "Call tool_query_person with query_type='visitors'. Optionally include office= to see "
            "who visited that specific office. Returns list of visitors with home office, visit "
            "dates, and frequency."
        ),
    ),
    Skill(
        name="team-sync",
        description="Team coordination, overlapping days, when teams are in the office together",
        content=(
            "Call tool_query_person with query_type='team_sync'. Include office= to see team "
            "overlap for a specific office. Returns team co-presence matrix and best overlap days."
        ),
    ),
    Skill(
        name="ghost-detection",
        description="Declining offices, ghost offices, erosion signals, offices losing attendance",
        content=(
            "Call tool_query_person with query_type='ghost'. Returns offices with 3+ decay signals "
            "(Friday erosion, peak ceiling drop, shape flattening, dwell compression). "
            "Also works for questions like 'is X office dying?' or 'which offices are getting quieter?'"
        ),
    ),
    Skill(
        name="trending-attendance",
        description="People trending up or down in office attendance, changing patterns",
        content=(
            "Call tool_query_person with query_type='trending_up' or 'trending_down'. "
            "Optionally include office= to filter by location. Returns people whose attendance "
            "has significantly changed in recent weeks."
        ),
    ),
    Skill(
        name="org-leader-rollup",
        description="Organization leader attendance rollups, VP/executive org attendance",
        content=(
            "Call tool_query_person with query_type='org_leader'. Optionally include person= "
            "with the leader's name. Returns attendance aggregated across the leader's full org tree."
        ),
    ),
    Skill(
        name="manager-gravity",
        description="Manager pull effect, whether teams follow managers to the office",
        content=(
            "Call tool_query_person with query_type='manager_gravity'. Optionally include office=. "
            "Returns correlation between manager presence and team attendance — does the team "
            "come in more when the manager is there?"
        ),
    ),
    Skill(
        name="new-hires",
        description="New hire onboarding attendance, recently hired employee integration patterns",
        content=(
            "Call tool_query_person with query_type='new_hires'. Optionally include office=. "
            "Returns new hires (last 90 days) with their attendance frequency, comparing to "
            "office norms. Flags under-integrated new hires."
        ),
    ),
    Skill(
        name="weekend-activity",
        description="Weekend and after-hours badge activity, Saturday/Sunday attendance",
        content=(
            "Call tool_query_person with query_type='weekend'. Optionally include office=. "
            "Returns weekend badge-in activity — who comes in on weekends and how often."
        ),
    ),
]

_skills_provider = SkillsProvider(skills=SKILLS)


def _get_agent():
    """Lazy-initialize the Agent Framework agent."""
    if not _HAS_AGENT_FRAMEWORK:
        raise RuntimeError("agent_framework package not installed")
    global _agent
    if _agent is None:
        # Build a pre-authenticated AsyncAzureOpenAI client with token provider.
        # DefaultAzureCredential → AzureCliCredential locally, ManagedIdentity in Azure.
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        async_client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_ad_token_provider=token_provider,
            api_version=AZURE_OPENAI_API_VERSION,
        )
        client = AzureOpenAIChatClient(
            deployment_name=AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,
            async_client=async_client,
        )
        _agent = client.as_agent(
            name="VeeamPresence",
            instructions=SYSTEM_PROMPT,
            tools=[tool_query_office_intel, tool_query_person, tool_render_card],
            context_providers=[_skills_provider],
        )
    return _agent


async def run_agent(user_message, history=None, conversation_id="default"):
    """
    Run one turn of the Presence agent.

    Args:
        user_message: The user's question
        history: List of prior message dicts (kept for API compat)
        conversation_id: Session key for multi-turn conversations

    Returns:
        (response_text, updated_history)
    """
    agent = _get_agent()

    # Get or create session for this conversation
    if conversation_id not in _sessions:
        _sessions[conversation_id] = {"session": agent.create_session(), "last_active": time.time()}
    entry = _sessions[conversation_id]
    entry["last_active"] = time.time()
    session = entry["session"]

    # Set per-coroutine conversation ID for card stashing (async-safe)
    _conversation_id_var.set(conversation_id)
    card_builder.clear(conversation_id)

    # Framework handles tool dispatch + loop + skill activation automatically
    result = await agent.run(user_message, session=session)
    response_text = result.text if hasattr(result, "text") else str(result)

    # Maintain history for compatibility
    history = history or []
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_text})

    logger.info("Agent turn: conv=%s msg=%s response_len=%d", conversation_id, user_message[:60], len(response_text))
    return response_text, history


def cleanup_sessions():
    """Remove expired sessions."""
    now = time.time()
    expired = [k for k, v in _sessions.items()
               if now - v["last_active"] > _SESSION_TTL]
    for k in expired:
        del _sessions[k]
