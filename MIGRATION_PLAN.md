# Veeam Presence — Migration to Microsoft Agent Framework + Azure OpenAI + CI/CD

## Current Anthropic SDK vs Microsoft Agent Framework

The current codebase uses the Anthropic Python SDK (`anthropic` package) with a hand-rolled
tool-use loop in `agent.py` (178 lines). Below is a direct comparison of what we have today
versus what we gain by moving to the Microsoft Agent Framework.

### What the Current Anthropic SDK Approach Looks Like

```python
# agent.py — current implementation (simplified)
import anthropic

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
TOOLS = [OFFICE_SCHEMA, PERSON_SCHEMA]          # Hand-maintained JSON dicts
TOOL_DISPATCH = {"query_office_intel": ..., "query_person": ...}

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    system=SYSTEM_PROMPT,
    tools=TOOLS,
    messages=messages,
)

# Manual tool-use loop — developer writes and maintains this
while response.stop_reason == "tool_use":
    for block in response.content:
        if block.type == "tool_use":
            func = TOOL_DISPATCH[block.name]
            result = func(**block.input)
            # ... build tool_result message, append, re-call client.messages.create()

# Manual routing hints — 65 lines of keyword matching to compensate for
# model refusal on certain query types (travel, ghost, team sync, etc.)
def _add_routing_hint(message):
    if "travel" in message.lower():
        return "[ROUTING: call query_person with query_type='visitors']\n\n" + message
    # ... 8 keyword categories, each with its own word list and routing instruction
```

**Pain points with the current approach:**

1. **Manual tool-use loop** (lines 125-165) — 40 lines of dispatch, result packaging, re-calling the API. Repeated in every project that uses tools.
2. **Hand-maintained tool schemas** — JSON dicts in each tool file (`TOOL_SCHEMA`), manually kept in sync with function signatures. Drift causes silent failures.
3. **Keyword routing workaround** (lines 21-85) — 65 lines of regex/keyword matching that prepends `[ROUTING: ...]` hints to user messages. Exists because Claude sometimes refuses to call tools for certain query patterns (e.g., "is Seattle dying?" doesn't trigger ghost detection). Brittle — every new query pattern needs new keywords.
4. **Provider lock-in** — Anthropic SDK is Anthropic-only. Switching to Azure OpenAI means rewriting the loop, schema format, and response parsing.
5. **No session management** — Conversation history is a plain list managed by `app.py` with manual TTL and trimming.
6. **No middleware** — Logging, telemetry, and rate limiting are bolted on by hand.

### What Agent Framework Replaces It With

```python
# agent.py — new implementation (simplified)
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import SkillsProvider
from azure.identity import DefaultAzureCredential

client = AzureOpenAIChatClient(
    endpoint=config.AZURE_OPENAI_ENDPOINT,
    deployment_name="gpt-5.3-chat",
    credential=DefaultAzureCredential(),
)

agent = client.as_agent(
    name="VeeamPresence",
    instructions=SYSTEM_PROMPT,
    tools=[tool_query_office_intel, tool_query_person],  # Python functions with type hints
    context_providers=[skills_provider],                  # Progressive skill discovery
)

# One call — framework handles tool dispatch, result feeding, and multi-turn loop
result = await agent.run(user_message, session=session)
```

### Side-by-Side Comparison

| Aspect | Current: Anthropic SDK | New: Agent Framework |
|--------|----------------------|---------------------|
| **Tool-use loop** | Manual `while response.stop_reason == "tool_use"` — 40 lines of dispatch, result packaging, re-calling API | Automatic — `agent.run()` handles full loop internally |
| **Tool schemas** | Hand-maintained JSON dicts (`TOOL_SCHEMA` per tool file, ~30 lines each). Must stay in sync with function signatures manually | Auto-generated from Python type hints (`Annotated[str, Field(...)]`). Schema is the code |
| **Tool routing** | 65-line keyword matching function (`_add_routing_hint`) that injects `[ROUTING: ...]` into user messages. Brittle — misses synonyms, needs manual updates for each new query pattern | **Agent Skills** with progressive discovery. LLM reads skill catalog (name + description) and self-activates. Handles synonyms and novel phrasings via LLM reasoning |
| **Provider** | Locked to Anthropic Claude. Response format, tool schema format, and stop_reason parsing are Anthropic-specific | Provider-agnostic. Swap `AzureOpenAIChatClient` → `AnthropicClient` or `OllamaClient` with zero tool or loop changes |
| **Session/state** | Roll-your-own: plain list in `app.py`, manual 20-message trim, 30-min TTL cleanup | Built-in `AgentSession` with `create_session()`, framework-managed history, serialization |
| **Async** | Sync only (`client.messages.create()`) — blocks the event loop in async FastAPI | Async-first (`await agent.run()`). Native alignment with async FastAPI |
| **LLM model** | `claude-sonnet-4-20250514` (Anthropic hosted) | `gpt-5.3-chat` (Azure OpenAI, managed identity, no API key) |
| **Auth** | `ANTHROPIC_API_KEY` env var (long-lived secret) | `DefaultAzureCredential` — managed identity in Azure, no stored API key |
| **Middleware** | None — add logging by hand | Pluggable middleware pipeline, OpenTelemetry tracing built in |
| **Multi-agent** | Build from scratch | Agent-as-tool composition (`agent.as_tool()`), graph-based workflows |
| **MCP support** | None | Native local and hosted MCP tool integration |
| **Lines eliminated** | — | ~130 lines (tool loop + schemas + routing hints) |

### Trade-Offs We Accept

- **Pre-GA risk** — `agent-framework` v1.0.0rc5 may have breaking changes before 1.0. Mitigation: pin exact version, keep old `agent.py` on a branch for rollback.
- **Black-box dispatch** — tool calls happen inside the framework. Less visible during debugging. Mitigation: middleware logging, OpenTelemetry traces.
- **Extra dependency** — `agent-framework` pulls in `pydantic`, `openai`, and framework internals. Our current `anthropic` dependency is lighter.
- **Learning curve** — team must learn `SkillsProvider`, `AgentSession`, and async patterns. One-time cost.
- **Skill description quality** — progressive skill discovery relies on LLM reading descriptions to decide activation. If descriptions are poorly written, the LLM may not activate the right skill. Mitigation: test with the 30-query comparison matrix.

### Decision

Use the Agent Framework. The investment pays off across three dimensions:

1. **Immediate** — eliminates 130+ lines of hand-rolled tool dispatch, schema maintenance, and keyword routing
2. **Medium-term** — progressive skill discovery handles novel query phrasings that keyword routing can never catch
3. **Long-term** — provider-agnostic architecture, MCP support, and multi-agent composition as the platform grows

---

## Overview

Migrate the Veeam Presence agent from:
- **Anthropic Claude** (raw `anthropic` SDK, hand-rolled tool-use loop) → **Microsoft Agent Framework** (`agent-framework` v1.0.0rc5) + **Azure OpenAI** (`gpt-5.3-chat`)
- **No CI/CD** (manual `docker build` + `az containerapp create`) → **GitHub Actions CI/CD** modeled after the daily_planner reference repo

The application moves to **fully async** — FastAPI async endpoints, `await agent.run()`, no `asyncio.run()` bridges.

Keep: two-service architecture (agent + gateway), botbuilder gateway, pipeline job, all data tools, Adaptive Cards.

## Part A: Agent Framework + Azure OpenAI Migration

### Model: `gpt-5.3-chat`

The reference daily_planner repo defaults to `gpt-5.2-chat`. We will use `gpt-5.3-chat` per user request.

### A1. `config.py` — Replace LLM credentials

Remove:
```python
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
```

Add:
```python
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-5.3-chat")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
```

No API key — using DefaultAzureCredential (Entra ID / Managed Identity).

### A2. `requirements.txt` — Swap packages

Remove: `anthropic>=0.40.0`
Add:
```
agent-framework>=1.0.0rc5
azure-identity>=1.15.0
```
Keep: `fastapi`, `uvicorn`, `pandas`, `numpy`, `holidays`, `aiohttp`, `requests`

### A3. `tools/query_office_intel.py` — Add typed wrapper, remove TOOL_SCHEMA

Keep the existing `query_office_intel()` function untouched. Add a typed wrapper function that the Agent Framework auto-discovers. Delete the `TOOL_SCHEMA` dict.

```python
from typing import Annotated, Optional
from pydantic import Field

def tool_query_office_intel(
    office: Annotated[Optional[str], Field(description="Office name. Omit for all offices.")] = None,
) -> str:
    """Get office headcounts, top people, health scores, and team info. No office = all offices. With office name = that office's full detail."""
    import json
    return json.dumps(query_office_intel(office=office), default=str)
```

### A4. `tools/query_person.py` — Add typed wrapper, remove TOOL_SCHEMA

Same pattern. Keep `query_person()` untouched. Add wrapper, delete schema.

```python
from typing import Annotated, Optional, Literal
from pydantic import Field

def tool_query_person(
    person: Annotated[Optional[str], Field(description="Person's name or email")] = None,
    office: Annotated[Optional[str], Field(description="Office name")] = None,
    query_type: Annotated[Optional[Literal[
        "pattern", "who_was_in", "trending_up", "trending_down", "visitors",
        "team_sync", "ghost", "org_leader", "manager_gravity", "new_hires", "weekend"
    ]], Field(description="Type of query. Default: 'pattern' for person, 'who_was_in' for office.")] = None,
) -> str:
    """Get data about people and teams. Query types: pattern, who_was_in, trending_up/down, visitors, team_sync, ghost, org_leader, manager_gravity, new_hires, weekend."""
    import json
    return json.dumps(query_person(person=person, office=office, query_type=query_type), default=str)
```

### A5. `agent.py` — Full rewrite (core change)

Replace the entire Anthropic SDK orchestration with the Microsoft Agent Framework. The framework handles the tool-use loop automatically via `agent.run()`. Keyword routing hints are replaced by Agent Skills with progressive discovery (see A10).

```python
"""Veeam Presence — Microsoft Agent Framework orchestration with Azure OpenAI."""

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import Skill, SkillsProvider
from azure.identity import DefaultAzureCredential
import config
from system_prompt import SYSTEM_PROMPT
from tools.query_office_intel import tool_query_office_intel
from tools.query_person import tool_query_person

_agent = None
_sessions = {}  # conversation_id -> AgentSession


# --- Agent Skills (replaces _add_routing_hint keyword matching) ---
# Each skill is a lightweight instruction package. The LLM sees only the name + description
# in its system prompt (~50-100 tokens each). When a user query matches a description,
# the LLM activates the skill via load_skill, which injects the full instructions.

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
    global _agent
    if _agent is None:
        client = AzureOpenAIChatClient(
            endpoint=config.AZURE_OPENAI_ENDPOINT,
            deployment_name=config.AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,
            credential=DefaultAzureCredential(),
        )
        _agent = client.as_agent(
            name="VeeamPresence",
            instructions=SYSTEM_PROMPT,
            tools=[tool_query_office_intel, tool_query_person],
            context_providers=[_skills_provider],
        )
    return _agent


async def run_agent(user_message, history=None, conversation_id="default"):
    """Run one turn of the Presence agent. Returns (response_text, updated_history)."""
    agent = _get_agent()

    # Get or create session for this conversation
    if conversation_id not in _sessions:
        _sessions[conversation_id] = agent.create_session()
    session = _sessions[conversation_id]

    # Framework handles tool dispatch + loop + skill activation automatically
    result = await agent.run(user_message, session=session)
    response_text = result.text if hasattr(result, 'text') else str(result)

    # Maintain history for compatibility with app.py
    history = history or []
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_text})
    return response_text, history
```

**What disappears:**
- Manual `client.messages.create()` call
- `while response.stop_reason == "tool_use"` loop (40 lines)
- `TOOL_DISPATCH` dict and `TOOLS` list with schema dicts
- Manual tool result message construction
- `_add_routing_hint()` function (65 lines of keyword matching)
- Total: ~130 lines eliminated

**What's new:**
- `SKILLS` list — 10 skill definitions with name, description, and activation instructions
- `SkillsProvider` — injects skill catalog into system prompt, exposes `load_skill` tool
- Progressive discovery — LLM sees ~500 tokens of skill catalog, loads full instructions on demand

**How skills replace keyword routing:**

| Keyword routing (old) | Agent Skills (new) |
|---|---|
| Developer writes regex: `"ghost", "declining", "dying"` | Developer writes description: `"Declining offices, ghost offices, erosion signals"` |
| Misses synonyms: "is Seattle fading?" → no match | LLM reasons: "fading" ≈ "declining" → activates ghost-detection skill |
| Prepends `[ROUTING: call query_person...]` to message | Skill content instructs: `"Call tool_query_person with query_type='ghost'"` |
| New query patterns need code changes | New patterns handled by LLM generalization |
| 65 lines of keyword/routing code | 0 lines of routing code (descriptions are config, not logic) |

### A6. `app.py` — Minor adjustments

- Pass `conversation_id` to `run_agent()` and `await` it:
  ```python
  response_text, conv["history"] = await run_agent(user_text, conv["history"], conversation_id=conversation_id)
  ```
- Add session cleanup in `_cleanup_stale()` to also evict `_sessions` entries:
  ```python
  from agent import _sessions
  for cid in stale_ids:
      _sessions.pop(cid, None)
  ```

### A7. `system_prompt.py` — Prompt tuning (iterative, post-migration)

The prompt is a plain string usable by any LLM. However:
- GPT models may need stronger "ALWAYS call a tool" reinforcement
- Tone may drift (GPT tends to be more verbose)
- The skills system provides implicit routing guidance, reducing the prompt's burden for tool-call coercion
- Test and iterate after structural migration using the 30-query comparison matrix

### A8. `test_harness.py` — Update credential check

Replace `ANTHROPIC_API_KEY` check with `AZURE_OPENAI_ENDPOINT`.

### A9. `tests/integration_test.py` — Update tests

- Remove `TOOL_SCHEMA` shape tests (no more schema dicts)
- Add import test for `agent_framework`
- Add test that `SKILLS` list is non-empty and each skill has name + description
- Update Dockerfile reference tests

### A10. Agent Skills — Progressive Skill Discovery (replaces keyword routing)

This is the key architectural change beyond the SDK swap. The current `_add_routing_hint()` function (65 lines of keyword matching in `agent.py`) is replaced by Agent Skills with progressive discovery.

#### Problem Being Solved

LLMs sometimes refuse to call tools for queries that seem conversational but actually require data lookup. Example: "is the Seattle office dying?" — Claude sees no explicit data question and responds conversationally instead of calling `query_person(query_type='ghost')`.

The current workaround is keyword matching that injects routing hints into the user message before the LLM sees it. This is brittle (misses synonyms), requires developer maintenance, and can't generalize to novel phrasings.

#### How Agent Skills Work

Agent Skills use a 3-tier progressive loading pattern:

```
Tier 1 — Catalog (always in system prompt, ~50-100 tokens/skill):
  "ghost-detection: Declining offices, ghost offices, erosion signals, offices losing attendance"

Tier 2 — Load (injected when LLM activates skill via load_skill tool):
  "Call tool_query_person with query_type='ghost'. Returns offices with 3+ decay signals..."

Tier 3 — Resources (loaded on demand via read_skill_resource):
  Additional context, example queries, output format templates
```

**Activation flow:**

1. LLM receives user message: "is Seattle dying?"
2. LLM sees skill catalog in system prompt → matches "ghost-detection" description
3. LLM calls `load_skill("ghost-detection")` → receives full instructions
4. Instructions say: call `tool_query_person` with `query_type='ghost'`
5. LLM calls the tool with correct parameters

The key difference: keyword routing uses **developer-maintained pattern matching** (if "dying" in message → inject hint). Skills use **LLM reasoning over descriptions** ("dying" ≈ "declining offices, erosion signals" → activate skill). The LLM generalizes to novel phrasings that keyword matching would miss.

#### Skill Inventory

| Skill Name | Description (what LLM sees in catalog) | Replaces Routing Keywords |
|---|---|---|
| `office-intelligence` | Office headcounts, health scores, day-of-week patterns, team breakdowns | `office`, `headcount`, `health` |
| `person-attendance` | Individual person's attendance pattern, schedule, presence history | person names, `pattern` |
| `travel-visitors` | Cross-office travelers, visitors from other offices | `travel`, `visiting`, `between offices` |
| `team-sync` | Team coordination, overlapping days, teams in office together | `team sync`, `overlapping`, `same days` |
| `ghost-detection` | Declining offices, ghost offices, erosion signals | `ghost`, `declining`, `dying`, `going quiet` |
| `trending-attendance` | People trending up or down in office attendance | `trending`, `more`, `less` |
| `org-leader-rollup` | Organization leader attendance rollups, VP/exec org | `org leader`, specific exec names |
| `manager-gravity` | Manager pull effect, teams following managers | `manager gravity`, `manager pull` |
| `new-hires` | New hire onboarding attendance, integration patterns | `new hire`, `onboarding` |
| `weekend-activity` | Weekend and after-hours badge activity | `weekend`, `saturday`, `sunday` |

**Token budget:** 10 skills × ~50 tokens/description = ~500 tokens added to system prompt. Compared to the current routing hint approach (which adds ~50-100 tokens per matched message), this is a fixed one-time cost with better coverage.

#### Fallback Strategy

If skill-based activation proves unreliable for specific query patterns during testing (Phase 12), we can:
1. Improve skill descriptions (first line of defense)
2. Add reinforcement in `system_prompt.py`: "When asked about declining offices, use the ghost-detection skill"
3. As a last resort, keep a minimal `_add_routing_hint()` for the few hardest cases — but the goal is zero keyword routing

---

## Part B: CI/CD Implementation (modeled after daily_planner)

### Branch Model

Adapted from the reference repo's 4-branch model:

| Branch | Purpose |
|--------|---------|
| `feature/*` | Developer working branches (e.g., `features/james-dev`) |
| `dev` | Engineering integration — validates builds and tests |
| `integration` | Auto-deploys to non-production Azure environment |
| `main` | Production — promotes tested release after approval |

### GitHub Environments

| Environment | Branch | Protection |
|-------------|--------|------------|
| `integration` | `integration` branch only | Optional reviewer gate |
| `production` | `main` branch only | Required infra team reviewer |
| `teams-catalog-admin` | Manual only | M365 admin reviewer |
| `bootstrap-foundation` | Manual only | Infra team reviewer |

### Deployment Concerns

Veeam Presence has 5 deployment concerns (like the reference):

1. **Agent service deployment** (replaces "planner")
2. **Gateway deployment** (replaces "wrapper")
3. **Pipeline job deployment** (new — nightly cron)
4. **Teams app package publish** (same pattern as reference)
5. **Foundation/bootstrap** (rare — new Azure resources)

### B1. New file: `.github/workflows/ci.yml`

Adapted from reference `ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [dev, integration, main]
  push:
    branches: [dev, integration, main]
    paths-ignore:
      - "**/*.md"

permissions:
  contents: read
  pull-requests: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  changes:
    name: Classify Changes
    runs-on: ubuntu-latest
    outputs:
      agent_runtime: ${{ steps.filter.outputs.agent_runtime }}
      gateway_runtime: ${{ steps.filter.outputs.gateway_runtime }}
      pipeline_runtime: ${{ steps.filter.outputs.pipeline_runtime }}
      m365_package: ${{ steps.filter.outputs.m365_package }}
      deploy_relevant: ${{ steps.classify.outputs.deploy_relevant }}
    steps:
      - uses: actions/checkout@v5
      - uses: dorny/paths-filter@v4.0.1
        id: filter
        with:
          filters: |
            agent_runtime:
              - 'app.py'
              - 'agent.py'
              - 'config.py'
              - 'system_prompt.py'
              - 'response_cache.py'
              - 'proactive_briefing.py'
              - 'tools/**'
              - 'cards/**'
              - 'pipeline/**'
              - 'Dockerfile'
              - 'requirements.txt'
            gateway_runtime:
              - 'gateway/**'
            pipeline_runtime:
              - 'pipeline/**'
              - 'Dockerfile.pipeline'
              - 'requirements.pipeline.txt'
            m365_package:
              - 'appPackage/**'
      - id: classify
        shell: bash
        run: |
          set -euo pipefail
          deploy_relevant=false
          if [[ "${{ steps.filter.outputs.agent_runtime }}" == "true" || \
                "${{ steps.filter.outputs.gateway_runtime }}" == "true" || \
                "${{ steps.filter.outputs.pipeline_runtime }}" == "true" ]]; then
            deploy_relevant=true
          fi
          echo "deploy_relevant=$deploy_relevant" >> "$GITHUB_OUTPUT"

  python-tests:
    name: Python Tests
    needs: changes
    if: github.event_name == 'pull_request' || needs.changes.outputs.deploy_relevant == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python tests/integration_test.py

  docker-build-smoke:
    name: Docker Build Smoke
    needs: changes
    if: github.event_name == 'pull_request' || needs.changes.outputs.deploy_relevant == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Build agent image
        if: needs.changes.outputs.agent_runtime == 'true' || github.event_name == 'pull_request'
        run: docker build -t presence-agent-smoke:ci -f Dockerfile .
      - name: Build gateway image
        if: needs.changes.outputs.gateway_runtime == 'true' || github.event_name == 'pull_request'
        run: docker build -t presence-gateway-smoke:ci -f gateway/Dockerfile ./gateway
      - name: Build pipeline image
        if: needs.changes.outputs.pipeline_runtime == 'true' || github.event_name == 'pull_request'
        run: docker build -t presence-pipeline-smoke:ci -f Dockerfile.pipeline .

  build-release-artifacts:
    name: Build Release Artifacts
    if: >-
      always() &&
      github.event_name == 'push' &&
      github.ref_name == 'integration' &&
      needs.changes.outputs.deploy_relevant == 'true' &&
      needs.python-tests.result == 'success' &&
      needs.docker-build-smoke.result == 'success'
    runs-on: ubuntu-latest
    needs: [changes, python-tests, docker-build-smoke]
    environment: integration
    permissions:
      contents: read
      id-token: write
    env:
      AZURE_CLIENT_ID: ${{ vars.AZURE_CLIENT_ID }}
      AZURE_TENANT_ID: ${{ vars.AZURE_TENANT_ID }}
      AZURE_SUBSCRIPTION_ID: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      ACR_NAME: ${{ vars.ACR_NAME }}
    steps:
      - uses: actions/checkout@v5
      - uses: azure/login@v3
        with:
          client-id: ${{ env.AZURE_CLIENT_ID }}
          tenant-id: ${{ env.AZURE_TENANT_ID }}
          subscription-id: ${{ env.AZURE_SUBSCRIPTION_ID }}
      - name: Build images in ACR
        id: build-images
        shell: bash
        run: |
          set -euo pipefail
          short_sha="${GITHUB_SHA::12}"
          az acr build --registry "$ACR_NAME" \
            --image "presence/agent:${short_sha}" -f Dockerfile .
          az acr build --registry "$ACR_NAME" \
            --image "presence/gateway:${short_sha}" -f gateway/Dockerfile ./gateway
          az acr build --registry "$ACR_NAME" \
            --image "presence/pipeline:${short_sha}" -f Dockerfile.pipeline .
          echo "IMAGE_TAG=${short_sha}" >> "$GITHUB_ENV"
      - name: Write release metadata
        shell: bash
        run: |
          cat <<EOF > "${{ runner.temp }}/release-metadata.json"
          {
            "git_sha": "${{ github.sha }}",
            "git_ref": "${{ github.ref_name }}",
            "agent_image": "${ACR_NAME}.azurecr.io/presence/agent:${IMAGE_TAG}",
            "gateway_image": "${ACR_NAME}.azurecr.io/presence/gateway:${IMAGE_TAG}",
            "pipeline_image": "${ACR_NAME}.azurecr.io/presence/pipeline:${IMAGE_TAG}"
          }
          EOF
      - uses: actions/upload-artifact@v6
        with:
          name: release-metadata-${{ github.sha }}
          path: ${{ runner.temp }}/release-metadata.json
```

### B2. New file: `.github/workflows/deploy-integration.yml`

```yaml
name: Deploy Integration

on:
  push:
    branches: [integration]
    paths-ignore: ["**/*.md"]

permissions:
  contents: read
  actions: read
  id-token: write

concurrency:
  group: deploy-integration
  cancel-in-progress: true

jobs:
  deploy:
    name: Deploy Integration
    runs-on: ubuntu-latest
    environment: integration
    env:
      AZURE_CLIENT_ID: ${{ vars.AZURE_CLIENT_ID }}
      AZURE_TENANT_ID: ${{ vars.AZURE_TENANT_ID }}
      AZURE_SUBSCRIPTION_ID: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      AZURE_RESOURCE_GROUP: ${{ vars.AZURE_RESOURCE_GROUP }}
      ACR_NAME: ${{ vars.ACR_NAME }}
      ACA_ENVIRONMENT_NAME: ${{ vars.ACA_ENVIRONMENT_NAME }}
      AGENT_ACA_APP_NAME: ${{ vars.AGENT_ACA_APP_NAME }}
      GATEWAY_ACA_APP_NAME: ${{ vars.GATEWAY_ACA_APP_NAME }}
      PIPELINE_ACA_JOB_NAME: ${{ vars.PIPELINE_ACA_JOB_NAME }}
      AZURE_OPENAI_ENDPOINT: ${{ vars.AZURE_OPENAI_ENDPOINT }}
      AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: ${{ vars.AZURE_OPENAI_CHAT_DEPLOYMENT_NAME }}
      BOT_APP_ID: ${{ vars.BOT_APP_ID }}
      BOT_APP_PASSWORD: ${{ secrets.BOT_APP_PASSWORD }}
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_TOKEN }}
      DATABRICKS_HTTP_PATH: ${{ vars.DATABRICKS_HTTP_PATH }}
      KEYVAULT_NAME: ${{ vars.KEYVAULT_NAME }}
    steps:
      - uses: actions/checkout@v5
      - uses: azure/login@v3
        with:
          client-id: ${{ env.AZURE_CLIENT_ID }}
          tenant-id: ${{ env.AZURE_TENANT_ID }}
          subscription-id: ${{ env.AZURE_SUBSCRIPTION_ID }}
      - name: Download release metadata
        uses: actions/download-artifact@v6
        with:
          name: release-metadata-${{ github.sha }}
          path: ${{ runner.temp }}/release-metadata
      - name: Deploy agent, gateway, and pipeline
        shell: bash
        run: bash infra/scripts/ci-deploy-stack.sh
      - name: Run integration validation
        shell: bash
        run: bash infra/scripts/ci-validate-integration.sh
```

### B3. New file: `.github/workflows/deploy-production.yml`

Same pattern as reference — resolves promoted SHA from integration, downloads release metadata, deploys with `production` environment approval gate.

### B4. New file: `.github/workflows/bootstrap-foundation.yml`

Manual workflow for rare foundation changes (new Azure resources via Bicep).

### B5. New file: `.github/workflows/publish-teams-catalog.yml`

Manual workflow for Teams app publish — separate trust boundary.

### B6. Infrastructure files to create

```
infra/
  bicep/
    foundation.bicep          — ACR, Key Vault, Log Analytics, VNet (secure mode), ACA Environment
  scripts/
    bootstrap-azure.sh        — Orchestrates foundation + app regs + deploys
    deploy-foundation.sh      — Runs Bicep deployment
    ci-deploy-stack.sh        — Deploys agent + gateway + pipeline to ACA
    ci-deploy-agent.sh        — Agent-only deploy
    ci-deploy-gateway.sh      — Gateway-only deploy
    ci-validate-integration.sh — Health checks + basic query validation
    ci-render-runtime-env.sh  — Renders ephemeral .env from release metadata + vars
    ci-write-release-metadata.sh — Writes JSON metadata artifact
    ci-download-release-artifact.sh — GH API artifact download with retry
    ci-redact-env-file.sh     — Strips secrets for artifact upload
    setup-github-oidc.sh      — Creates federated OIDC credentials in Entra
  tests/
    test_infra.py             — Validates scripts, bicep, env templates
  outputs/
    (gitignored — bootstrap status files)
```

### B7. OIDC Authentication (Azure to GitHub Actions)

Following the reference repo pattern:

Two separate OIDC identities:
- `gh-presence-integration` — federated credential for `integration` branch
- `gh-presence-production` — federated credential for `main` branch

RBAC:
- Integration: `Contributor` (resource group) + `AcrPush` (ACR) + `Key Vault Secrets User`
- Production: `Contributor` (resource group) + `Key Vault Secrets User` (no AcrPush)

Setup helper: `infra/scripts/setup-github-oidc.sh`

### B8. Secrets and Variables Model

**GitHub Environment Variables** (non-secret):
- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `ACR_NAME`
- `ACA_ENVIRONMENT_NAME`, `AGENT_ACA_APP_NAME`, `GATEWAY_ACA_APP_NAME`
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
- `BOT_APP_ID`, `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`
- `KEYVAULT_NAME`

**GitHub Environment Secrets** (or Key Vault fallback):
- `BOT_APP_PASSWORD`
- `DATABRICKS_TOKEN`

**Key Vault Secrets** (runtime — injected into ACA via managed identity):
- `DATABRICKS-HOST`, `DATABRICKS-TOKEN`, `DATABRICKS-HTTP-PATH`
- `BOT-APP-ID`, `BOT-APP-PASSWORD`

No `ANTHROPIC-API-KEY` — Azure OpenAI uses managed identity, no API key.

### B9. `DEPLOYMENT.md` — Full rewrite

Update to reflect:
- Azure OpenAI instead of Anthropic
- gpt-5.3-chat model
- CI/CD workflow-driven deployment instead of manual `az containerapp create`
- OIDC auth instead of long-lived credentials
- Cost estimate update (Azure OpenAI pricing vs Anthropic)

### B10. `.env.inputs.example` — Operator input template

```bash
AZURE_TENANT_ID=
AZURE_SUBSCRIPTION_ID=
AZURE_RESOURCE_GROUP=rg-presence
AZURE_LOCATION=eastus
INFRA_NAME_PREFIX=presence
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-5.3-chat
DATABRICKS_HOST=
DATABRICKS_HTTP_PATH=
```

---

## Part C: Docker and Container Updates

### C1. `Dockerfile` — Update for Azure OpenAI

No structural change. Requirements install picks up `agent-framework` instead of `anthropic`. Remove any `ANTHROPIC_API_KEY` references from health check.

### C2. `docker-compose.yml` — Update env vars

```yaml
services:
  agent:
    environment:
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME:-gpt-5.3-chat}
      - AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY:-}  # fallback for local dev
      - DATABRICKS_HOST=${DATABRICKS_HOST}
      - DATABRICKS_TOKEN=${DATABRICKS_TOKEN}
      - DATABRICKS_HTTP_PATH=${DATABRICKS_HTTP_PATH}
  gateway:
    environment:
      - BOT_APP_ID=${BOT_APP_ID}
      - BOT_APP_PASSWORD=${BOT_APP_PASSWORD}
      - AGENT_SERVICE_URL=http://agent:8000
```

Note: For local dev without managed identity, `AZURE_OPENAI_API_KEY` is accepted as a fallback. The `AzureOpenAIChatClient` supports both credential types.

---

## Implementation Order

| Phase | What | Files | Test |
|-------|------|-------|------|
| 0 | Branch baseline | — | `python tests/integration_test.py` passes |
| 1 | Config + deps | `config.py`, `requirements.txt` | `python -c "import config"` |
| 2 | Tool wrappers | `tools/query_office_intel.py`, `tools/query_person.py` | Import test |
| 3 | Agent Skills | `agent.py` (SKILLS list + SkillsProvider) | Skill import test |
| 4 | Agent rewrite | `agent.py` (full rewrite) | `python test_harness.py` with 15+ queries |
| 5 | App wiring | `app.py` | End-to-end via test harness |
| 6 | Tests update | `tests/integration_test.py`, `test_harness.py` | Test suite passes |
| 7 | Docker updates | `Dockerfile`, `docker-compose.yml` | `docker-compose build` |
| 8 | CI workflow | `.github/workflows/ci.yml` | Push to `dev` triggers CI |
| 9 | Infra scripts | `infra/scripts/*`, `infra/bicep/foundation.bicep` | `bash -n` validation |
| 10 | Deploy workflows | `.github/workflows/deploy-*.yml` | Integration deploy succeeds |
| 11 | OIDC setup | `infra/scripts/setup-github-oidc.sh` + Entra config | `az login --federated-token` |
| 12 | Bootstrap | `infra/scripts/bootstrap-azure.sh` | Foundation resources created |
| 13 | Skill tuning | `agent.py` skill descriptions, `system_prompt.py` | 30-query comparison matrix |
| 14 | DEPLOYMENT.md | `DEPLOYMENT.md` | Documentation review |

Phases 1-7 are the code migration (can be done locally).
Phases 8-12 are the CI/CD infrastructure (requires Azure + GitHub setup).
Phase 13 is iterative skill description tuning (replaces "prompt tuning" — the descriptions are the new tuning surface).

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `agent-framework` v1.0.0rc5 is pre-GA | Medium | Pin exact version, keep old `agent.py` on branch for rollback |
| GPT-5.3-chat tool-calling behavior differs from Claude | Medium | Agent Skills provide implicit routing; skill descriptions tuned in Phase 13 |
| Skill descriptions don't cover edge-case queries | Medium | 30-query comparison matrix in Phase 13. Fallback: add reinforcement in system prompt or minimal keyword routing for hardest cases |
| Event-loop conflict if mixing sync/async | Low | All endpoints are `async def`, `run_agent()` uses `await` directly |
| AgentSession state differs from current in-memory history | Low | Keep app.py's TTL/cleanup as a wrapper around sessions |
| Progressive discovery adds latency (2 LLM calls for skill activation) | Low | Skill load is fast (~100ms); total latency increase is marginal vs 3-6s LLM call. Pre-generated cache layer still serves instant responses for common queries |
| OIDC setup requires Entra admin access | Low | Either single-operator or split-responsibility model |
| ACR build requires public network access | Low | Keep ACR public (same as reference repo pattern) |
| gpt-5.3-chat may not be available in all Azure regions | Low | Set `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` as configurable override |

---

## Cost Comparison

| Component | Current (Anthropic) | New (Azure OpenAI) |
|-----------|--------------------|--------------------|
| LLM API | ~$15-30/mo (Anthropic) | Part of Azure OpenAI resource (consumption) |
| Agent Container App | ~$30-50/mo | ~$30-50/mo (unchanged) |
| Gateway Container App | ~$15-25/mo | ~$15-25/mo (unchanged) |
| Pipeline Job | ~$1/mo | ~$1/mo (unchanged) |
| Azure OpenAI resource | — | ~$0 (pay per token, GlobalStandard) |
| Azure Bot Service | Free | Free |
| ACR, Key Vault, Log Analytics | Not deployed | ~$5-10/mo |
| **Total** | **~$62-107/mo** | **~$55-95/mo** |
