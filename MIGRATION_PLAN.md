# Veeam Presence — Migration to Microsoft Agent Framework + Azure OpenAI + CI/CD

## Why Microsoft Agent Framework Over Raw SDK

The current codebase uses the Anthropic Python SDK with a hand-rolled tool-use loop
in `agent.py` (178 lines). A direct port to the `openai` SDK would be the simplest
path — the tool-use loop is only ~40 lines, the tool schemas are ~30 lines, and the
whole thing works. For a short-term fix, a raw SDK swap is faster and lower risk.

We are choosing the Microsoft Agent Framework (`agent-framework` v1.0.0rc5) for
**long-term** reasons:

| Factor | Raw `openai` SDK | Agent Framework |
|--------|-------------------|-----------------|
| **Tool-use loop** | Manual — you write the `while tool_calls` loop, dispatch, feed results back. Copy-paste across projects. | Automatic — `agent.run()` handles the full loop, dispatch, and result feeding. |
| **Tool schemas** | Hand-maintained JSON dicts (`{"type": "function", "function": {...}}`). Must stay in sync with function signatures manually. | Auto-generated from Python type hints (`Annotated[str, Field(...)]`). Schema is the code. |
| **Provider swap** | Locked to OpenAI/Azure OpenAI. Switching to Anthropic, Ollama, or Foundry means rewriting the loop, schema format, and response parsing. | Provider-agnostic. Swap `AzureOpenAIChatClient` → `AnthropicClient` or `OllamaClient` with zero tool or loop changes. |
| **Session/state** | Roll your own conversation history, TTL, and cleanup. | Built-in `AgentSession` with `create_session()`, serialization, and service-managed history support. |
| **Async** | Optional — you choose sync or async. | Async-first (`await agent.run()`). Aligns with our move to fully async FastAPI. |
| **Middleware** | None — add logging, telemetry, rate limiting by hand. | Pluggable middleware pipeline for request/response interception, OpenTelemetry tracing built in. |
| **Multi-agent** | Build from scratch. | Agent-as-tool composition (`agent.as_tool()`), graph-based workflows for orchestration. |
| **MCP support** | None. | Native local and hosted MCP tool integration. |
| **Maintenance** | Own the loop code forever. Every bug in dispatch, retry, or parsing is yours. | Microsoft-maintained. Bug fixes and new model support come from upstream. |

**Trade-offs we accept:**

- **Pre-GA risk** — v1.0.0rc5 may have breaking changes before 1.0. Mitigation: pin
  exact version, keep old `agent.py` on a branch for rollback.
- **Black-box dispatch** — tool calls happen inside the framework. Less visible during
  debugging. Mitigation: middleware logging, OpenTelemetry traces.
- **Extra dependency** — `agent-framework` pulls in `pydantic`, `openai`, and
  framework internals. Our current `anthropic` dependency is lighter.
- **Learning curve** — team must learn the `@tool` decorator, `AgentSession`, and
  async patterns. This is a one-time cost.

**Decision:** Use the Agent Framework. The 2-tool, 20-query/day profile of this
project does not demand it today, but we are building for a platform that will grow
in tools, providers, and agents. The framework investment pays off when we add MCP
tools, multi-agent workflows, or need to swap providers without rewriting
orchestration code.

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

Replace the entire Anthropic SDK orchestration with the Microsoft Agent Framework. The framework handles the tool-use loop automatically via `agent.run()`.

```python
"""Veeam Presence — Microsoft Agent Framework orchestration with Azure OpenAI."""

import asyncio
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential
import config
from system_prompt import SYSTEM_PROMPT
from tools.query_office_intel import tool_query_office_intel
from tools.query_person import tool_query_person

_agent = None
_sessions = {}  # conversation_id -> AgentSession


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
        )
    return _agent


def _add_routing_hint(message):
    """Keep existing routing hint logic unchanged."""
    lower = message.lower()
    # ... (all existing routing hint keyword matching stays as-is) ...
    return message


def run_agent(user_message, history=None, conversation_id="default"):
    """Run one turn of the Presence agent. Returns (response_text, updated_history)."""
    agent = _get_agent()
    routed_message = _add_routing_hint(user_message)

    # Get or create session for this conversation
    if conversation_id not in _sessions:
        _sessions[conversation_id] = agent.create_session()
    session = _sessions[conversation_id]

    # Framework handles tool dispatch + loop automatically
    result = asyncio.run(agent.run(routed_message, session=session))
    response_text = result.text if hasattr(result, 'text') else str(result)

    # Maintain history for compatibility with app.py
    history = history or []
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_text})
    return response_text, history
```

**What disappears:** manual `client.messages.create()`, `while response.stop_reason == "tool_use"` loop, `TOOL_DISPATCH` dict, `TOOLS` list with schema dicts, manual tool result message construction. ~90 lines eliminated.

**What stays:** `_add_routing_hint()` (unchanged), `run_agent()` public API (same signature + `conversation_id`).

**Async consideration:** `asyncio.run()` works from a sync context but will fail if already inside an async event loop (e.g., FastAPI async endpoint). If `app.py` uses `async def handle_message`, use `await agent.run(...)` instead.

### A6. `app.py` — Minor adjustments

- Pass `conversation_id` to `run_agent()`:
  ```python
  response_text, conv["history"] = run_agent(user_text, conv["history"], conversation_id=conversation_id)
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
- Test and iterate after structural migration

### A8. `test_harness.py` — Update credential check

Replace `ANTHROPIC_API_KEY` check with `AZURE_OPENAI_ENDPOINT`.

### A9. `tests/integration_test.py` — Update tests

- Remove `TOOL_SCHEMA` shape tests (no more schema dicts)
- Add import test for `agent_framework`
- Update Dockerfile reference tests

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
| 3 | Agent rewrite | `agent.py` | `python test_harness.py` with 15+ queries |
| 4 | App wiring | `app.py` | End-to-end via test harness |
| 5 | Tests update | `tests/integration_test.py`, `test_harness.py` | Test suite passes |
| 6 | Docker updates | `Dockerfile`, `docker-compose.yml` | `docker-compose build` |
| 7 | CI workflow | `.github/workflows/ci.yml` | Push to `dev` triggers CI |
| 8 | Infra scripts | `infra/scripts/*`, `infra/bicep/foundation.bicep` | `bash -n` validation |
| 9 | Deploy workflows | `.github/workflows/deploy-*.yml` | Integration deploy succeeds |
| 10 | OIDC setup | `infra/scripts/setup-github-oidc.sh` + Entra config | `az login --federated-token` |
| 11 | Bootstrap | `infra/scripts/bootstrap-azure.sh` | Foundation resources created |
| 12 | Prompt tuning | `system_prompt.py`, `agent.py` routing hints | 30-query comparison matrix |
| 13 | DEPLOYMENT.md | `DEPLOYMENT.md` | Documentation review |

Phases 1-6 are the code migration (can be done locally).
Phases 7-11 are the CI/CD infrastructure (requires Azure + GitHub setup).
Phase 12 is iterative prompt tuning.

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `agent-framework` v1.0.0rc5 is pre-GA | Medium | Pin exact version, keep old `agent.py` on branch for rollback |
| GPT-5.3-chat tool-calling behavior differs from Claude | Medium | Routing hints + iterative prompt tuning in Phase 12 |
| `asyncio.run()` conflict with FastAPI event loop | Medium | Make endpoints async, use `await agent.run(...)` directly |
| AgentSession state differs from current in-memory history | Low | Keep app.py's TTL/cleanup as a wrapper around sessions |
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
