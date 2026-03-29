# Veeam Presence — Build Workflow

## Architecture

```
┌──────────────────────┐     ┌──────────────────────┐
│  M365 Gateway        │     │  Agent Service        │
│  (gateway/)          │────→│  (Presence)           │
│                      │     │                       │
│  - Auth / JWT        │     │  - Claude orchestration│
│  - Card rendering    │     │  - Tool functions      │
│  - Typing indicator  │     │  - Pre-computed cache  │
└──────────────────────┘     └──────────────────────┘
         ↑                            ↑
    Teams / Copilot              Databricks
                              (read-only, nightly)
```

Plus: **Pipeline Job** runs nightly, pulls from Databricks, computes baselines/signals/CHI, writes pickle files that the agent service loads.

## What Was Built

### Pipeline (15 steps, ~60 seconds)
1. Pull occupancy events from Databricks (PowerShell — Windows HTTP required)
2. Aggregate to person-day (arrival, departure, dwell, office)
3. Enrich with Workday (role, team, manager, seniority, name)
4. Rolling 8-week baselines (per office x DOW x role segment)
5. Office personality profiles (7 dimensions)
6. Anchor lists + leaderboards (scaled by office size)
7. Cross-office visitor flows
8. Team synchronization scores (364 teams)
9. Ghost detection (4-signal composite)
10. Culture Health Index (7-component score)
11. Seniority breakdowns + org leader rollups
12. Manager gravity scoring (270 managers)
13. New hire integration curves (175 hires)
14. Weekend attendance tracking
15. Cross-functional mixing scores

### Agent Service
- 2 tools: `query_office_intel`, `query_person`
- System prompt with example-driven tone control
- Code-level routing hints for tricky queries (travel, team sync, etc.)
- Conversation state with 30-minute TTL

### Cards (11 templates)
Welcome, Overview, Briefing, Office Detail, Leaderboard, Person, Comparison, Trending, Visitors, Who Was In, Error

### Gateway
- M365 Agents SDK (botbuilder)
- Typing indicator on message receipt
- Adaptive Card attachment rendering
- Health check endpoint

## Local Testing

```bash
# Step 1: Pull data (requires Windows + Databricks access)
powershell -ExecutionPolicy Bypass -File run_pipeline.ps1

# Step 2: Talk to Presence in terminal
powershell -ExecutionPolicy Bypass -File run_harness.ps1

# Step 3: Full-stack with Docker (optional)
docker-compose up
# Then: ngrok http 3978 → update Bot Service endpoint → test in Teams
```

## Key Design Decisions

- **PowerShell for Databricks**: Corporate network ACLs block Python's HTTP stack. PowerShell uses Windows WinHTTP which is allowed.
- **Per-country holidays**: 18 offices → 15 countries via `holidays` Python package.
- **Boring tone**: System prompt rule #1 is "be boring." Tool output contains only headcounts and names — no rates, percentages, or analytical fields. This prevents Claude from dramatizing.
- **Routing hints**: Claude's training priors override the system prompt for certain queries (travel, team sync). Code-level routing in `agent.py` prepends hints to force correct tool calls.
