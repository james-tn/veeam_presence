# Veeam Presence — Function Flow & Technical Specification

## 1. System Overview

Veeam Presence is an office attendance intelligence agent deployed as a Microsoft Teams bot. It tracks daily attendance across 17 Veeam offices worldwide, answering natural-language questions about who's in the office, attendance patterns, trends, cross-office travel, team coordination, and more.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Microsoft Teams                              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS (Bot Framework protocol)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Gateway Service (gateway/app.py)                    Port 3978      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ BotFrameworkAdapter (botbuilder-core)                       │    │
│  │   • Auth validation     • Typing indicator                  │    │
│  │   • Proactive messaging • Card attachment rendering         │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
└─────────────────────────────┼──────────────────────────────────────┘
                              │ HTTP POST /api/agent/message
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Agent Service (app.py + agent.py)                   Port 8000      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ FastAPI (app.py)                                             │   │
│  │   • /api/agent/message  — main query endpoint                │   │
│  │   • /api/register_user  — proactive briefing registration    │   │
│  │   • /api/stats          — usage monitoring                   │   │
│  │   • /health             — liveness probe                     │   │
│  │                                                              │   │
│  │ Response Cache (response_cache.py)                           │   │
│  │   • Layer 1: Pre-generated cache (pipeline output, instant)  │   │
│  │   • Layer 2: Query cache (5-min TTL, LLM-generated)          │   │
│  │                                                              │   │
│  │ Agent (agent.py)                                             │   │
│  │   • Anthropic Claude API + tool-use loop                     │   │
│  │   • Routing hints (keyword → tool dispatch hints)            │   │
│  │   • Two tools: query_office_intel, query_person              │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │ Python function calls                  │
│  ┌──────────────────────────┴───────────────────────────────────┐   │
│  │ Tools                                                        │   │
│  │   • query_office_intel (tools/query_office_intel.py)         │   │
│  │   • query_person       (tools/query_person.py)               │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │ Read from pickle files                  │
│  ┌──────────────────────────┴───────────────────────────────────┐   │
│  │ Data Cache (data/*.pkl)                                      │   │
│  │   enriched.pkl, baselines.pkl, personality.pkl, anchors.pkl, │   │
│  │   visitors.pkl, team_sync.pkl, signals.pkl, chi.pkl,         │   │
│  │   seniority.pkl, manager_gravity.pkl, new_hires.pkl,         │   │
│  │   weekend.pkl, mixing.pkl, pregenerated.pkl                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Cards (cards/renderer.py + cards/templates.py)               │   │
│  │   Transforms structured JSON → Adaptive Card JSON for Teams  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Pipeline (Nightly Cron Job)                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ pull_events.py → aggregate.py → enrich.py → baselines.py →  │   │
│  │ personality.py → anchors.py → visitors.py → team_sync.py →  │   │
│  │ signals.py → chi.py → seniority.py → manager_gravity.py →   │   │
│  │ new_hires.py → weekend.py → mixing.py → pregenerate.py      │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │                                    │
│  Databricks ◄───────────────────┘ SQL via REST API                   │
│    • dev_catalog.jf_salesforce_bronze.office_occupancy_o_365_verkada │
│    • dev_catalog.revenue_intelligence.workday_enhanced               │
└─────────────────────────────────────────────────────────────────────┘
```

### Services

| Service | Runtime | Port | Image | Purpose |
|---------|---------|------|-------|---------|
| Agent | FastAPI + Uvicorn | 8000 | `presence/agent` | LLM orchestration, tool dispatch, caching |
| Gateway | aiohttp | 3978 | `presence/gateway` | Bot Framework adapter, Teams protocol |
| Pipeline | Python script (cron) | — | `presence/pipeline` | Nightly data pull + analytics |

---

## 2. End-to-End Request Flow

### 2.1 User Query (Happy Path)

```
User types "what's going on in Prague?" in Teams
│
├─1─► Teams sends Activity to gateway /api/messages
│     gateway/app.py:messages() → adapter.process_activity() → on_message()
│
├─2─► on_message() sends typing indicator to Teams
│     on_message() POSTs user registration to /api/register_user (async, non-blocking)
│
├─3─► on_message() POSTs to agent service:
│     POST http://agent:8000/api/agent/message
│     Body: {"conversation_id": "...", "text": "what's going on in Prague?", "user_id": "..."}
│
├─4─► app.py:handle_message() receives request
│     │
│     ├─4a─► Layer 1: check_pregenerated("what's going on in Prague?")
│     │      Matches "office:prague rustonka" → returns cached text instantly
│     │      ──► SHORTCUT: Returns {"text": "...", "card": null} (no LLM call)
│     │
│     ├─4b─► (If no pregenerated hit) Layer 2: check_query_cache()
│     │      MD5 of normalized query → check 5-min TTL cache
│     │      ──► SHORTCUT: Returns cached response (no LLM call)
│     │
│     └─4c─► (If no cache hit) Layer 3: Call Claude via agent.py:run_agent()
│            │
│            ├─► _add_routing_hint() — no routing hint needed for this query
│            │
│            ├─► Build messages: history[-20:] + new user message
│            │
│            ├─► client.messages.create(model, system=SYSTEM_PROMPT, tools=TOOLS, messages)
│            │   Claude's response: stop_reason="tool_use"
│            │   Tool call: query_office_intel(office="Prague")
│            │
│            ├─► TOOL DISPATCH LOOP:
│            │   │
│            │   ├─► query_office_intel(office="Prague")
│            │   │   _match_office("Prague") → "Prague Rustonka"
│            │   │   Reads: baselines.pkl, anchors.pkl, personality.pkl,
│            │   │          signals.pkl, chi.pkl, team_sync.pkl,
│            │   │          seniority.pkl, weekend.pkl, mixing.pkl
│            │   │   Returns: {office, people_in, typical, top_people, health_score, ...}
│            │   │
│            │   └─► Feed tool result back to Claude
│            │       client.messages.create(messages + [tool_result])
│            │       Claude's response: stop_reason="end_turn"
│            │       Final text: "Prague had 185 people on Thursday..."
│            │
│            ├─► try_parse_card(response_text) — check for JSON card in response
│            │
│            └─► store_query_cache(user_text, response_text) — cache for 5 min
│
├─5─► app.py returns {"text": "Prague had 185...", "card": null} to gateway
│
├─6─► on_message() sends text reply to Teams
│     (If card present: wraps in Adaptive Card Attachment)
│
└─7─► User sees response in Teams chat
```

### 2.2 Routing Hint Flow

For queries where Claude would otherwise refuse or misroute, `_add_routing_hint()` injects a system-level instruction:

```
User: "who's visiting other offices?"
│
├─► _add_routing_hint() matches "visiting other" in travel_words
│   Prepends: "[ROUTING: This is a cross-office travel question. You have this data.
│              Call query_person with query_type='visitors' immediately.]"
│
└─► Claude receives the routed message and calls query_person(query_type="visitors")
    instead of hesitating or saying "I don't have that data"
```

**Routing categories (agent.py lines 24-85):**

| Category | Keywords | Routed tool call |
|----------|----------|-----------------|
| Overview | "what can you", "capabilities" | No tool — respond with capability list |
| Travel | "travel", "visiting", "cross-office" | `query_person(query_type="visitors")` |
| Team sync | "team sync", "same days", "overlapping" | `query_person(query_type="team_sync")` |
| Ghost offices | "ghost", "declining", "going quiet" | `query_person(query_type="ghost")` |
| Org leaders | "org leader", specific exec names | `query_person(query_type="org_leader")` |
| Manager gravity | "manager gravity", "manager pull" | `query_person(query_type="manager_gravity")` |
| New hires | "new hire", "onboarding" | `query_person(query_type="new_hires")` |
| Weekend | "weekend", "saturday", "sunday" | `query_person(query_type="weekend")` |

### 2.3 Adaptive Card Rendering Flow

```
Claude returns text with embedded JSON:
  "Here's the briefing: ```json {"card": true, "template": "briefing", ...} ```"
│
├─► try_parse_card(text) in cards/renderer.py
│   Extracts JSON between ```json ... ``` markers
│   Validates {"card": true}
│
├─► render_card(data) dispatches by template:
│   "briefing"      → briefing_card()
│   "office_detail"  → office_detail_card()
│   "leaderboard"    → leaderboard_card()
│   "person"         → person_card()
│   "comparison"     → comparison_card()
│   "trending"       → trending_card()
│   "visitors"       → visitors_card()
│   "who_was_in"     → who_was_in_card()
│   "welcome"        → welcome_card()
│   "overview"       → overview_card()
│   "error"          → error_card()
│   other/standard   → _generic_card()
│
└─► Returns Adaptive Card JSON (v1.5 schema)
    Sent as attachment via BotFrameworkAdapter
```

**Card design principles (cards/templates.py):**
- Scannable in 3 seconds — key number visible without scrolling
- Max ~15 body elements (Teams truncates long cards)
- Mobile-first — all text wraps
- Color coding: Good (green) = above normal, Attention (amber) = below
- Every card has: header, content, data freshness note, 2-3 action buttons

---

## 3. Data Pipeline Flow

The pipeline runs nightly, pulling raw data from Databricks, computing all analytics,
and writing pickle files that the agent service reads at query time.

### 3.1 Pipeline Steps (run_analytics.py)

```
Step 1: pull_events.py
  ├─► pull_occupancy() — Databricks SQL via PowerShell REST
  │   Table: office_occupancy_o_365_verkada (trailing 10 weeks)
  │   Fields: userPrincipalName, source, timestamp, Office, offset, local_timestamp
  │
  └─► pull_workday() — Databricks SQL
      Table: workday_enhanced
      Fields: email, preferred_name, stream, job_family, management_level,
              ismanager, manager_name, supervisory_organization, hire_date, ...
      ▼
Step 2: aggregate.py → aggregate_person_day(events)
  • Raw events → 1 row per person per day
  • Computes: arrival_hour, departure_hour, dwell_hours, office (mode), dow
  • Excludes partial-ingestion weekdays (<20% of median headcount)
  Output: person-day DataFrame
      ▼
Step 3: enrich.py → enrich_with_workday(person_day, workday)
  • LEFT JOIN on email
  • Applies stream fallback mapping (config.STREAM_FALLBACK)
  • Assigns seniority_band from management_level (config.SENIORITY_BANDS)
  • Flags workday_matched = True/False
  Output: enriched.pkl (~180k+ person-day rows)
      ▼
Step 4: baselines.py → compute_baselines(enriched)
  • Per office × DOW: attendance rate = daily headcount / active_pool
  • Role-segmented baselines (by stream, min 10 people)
  • Seniority-segmented baselines (IC / Manager / Senior Leader)
  • Weekly headcount trend (trailing 8 weeks)
  • Latest day stats with deviation from baseline
  • Excludes public holidays via holidays_cal.py
  Output: baselines.pkl
      ▼
Step 5: personality.py → compute_personality(enriched, baselines)
  • 7 dimensions per office:
    1. Rhythm type (steady / spiky / distributed)
    2. Peak shape (sharp arrivals vs gradual)
    3. Active window (median dwell hours)
    4. Arrival center (median arrival hour)
    5. Weekend boundary (Friday/Thursday ratio)
    6. Volatility (week-to-week CV)
    7. Size class (from config)
  Output: personality.pkl
      ▼
Step 6: anchors.py → compute_anchors(enriched)
  • Top-N most consistent attenders per office (N scales by size: 5/10/15/20)
  • Current-week leaderboard with prior-week trend comparison
  • 4-week rolling streak tracking
  • Anchor erosion rate (weeks 5-8 anchors retained in weeks 1-2)
  Output: anchors.pkl
      ▼
Step 7: visitors.py → compute_visitors(enriched)
  • Determines home office (>60% of days in trailing 8 weeks)
  • Cross-office visits = appearances at non-home office
  • Aggregates flows: office-to-office, visitor count, visit days
  • Recent individual trips (last 4 weeks)
  Output: visitors.pkl
      ▼
Step 8: team_sync.py → compute_team_sync(enriched)
  • Per supervisory_organization (3+ members):
    Pairwise co-presence rate using Jaccard index
  • sync_score: mean of all pairwise co-presence rates
  • Categorizes: same_days (≥0.4), mixed (0.2-0.4), different_days (<0.2)
  Output: team_sync.pkl
      ▼
Step 9: signals.py → compute_signals(enriched, baselines)
  • 4 decay signals per office (recent 4 weeks vs prior 4 weeks):
    1. Friday erosion (Friday headcount down >15%)
    2. Peak ceiling drop (busiest-day headcount down >15%)
    3. Shape flattening (DOW variance decreased >30%)
    4. Dwell compression (median dwell down >15%)
  • Ghost flag: 3+ of 4 signals active
  Output: signals.pkl
      ▼
Step 10: chi.py → compute_chi(enriched, baselines, anchors, team_sync, signals)
  • Culture Health Index (0-100) per office, 7 weighted components:
    1. Consistency (20%) — week-to-week headcount volatility
    2. Depth (15%) — dwell time vs baseline
    3. Synchronization (20%) — team co-presence score
    4. Anchor Stability (15%) — top-N retention rate
    5. Integration (10%) — new hire attendance slope
    6. Leadership Presence (10%) — IC vs leader gap trajectory
    7. Breadth (10%) — cross-functional stream mix
  Output: chi.pkl
      ▼
Step 11: seniority.py → compute_seniority(enriched)
  • Per office: IC / Manager / Senior Leader attendance breakdowns
  • Org leader rollups using CF_EE_Org_Leader_1/2/3 hierarchy
  Output: seniority.pkl
      ▼
Step 12: manager_gravity.py → compute_manager_gravity(enriched)
  • Per manager: team attendance rate on days manager is in vs out
  • gravity_score = delta between the two rates
  Output: manager_gravity.pkl
      ▼
Step 13: new_hires.py → compute_new_hire_integration(enriched)
  • People hired in last 6 months: weekly attendance by tenure week
  • Trend classification: ramping up / steady / fading
  Output: new_hires.pkl
      ▼
Step 14: weekend.py → compute_weekend(enriched)
  • Saturday/Sunday attendance per office
  • Top weekend attenders, trend (increasing/stable/decreasing)
  Output: weekend.pkl
      ▼
Step 15: mixing.py → compute_mixing(enriched)
  • Per office per day: how many streams have 2+ people present
  • mixing_score = avg_streams_per_day / total_streams
  Output: mixing.pkl
      ▼
Step 16: pregenerate.py → pregenerate(baselines, personality, anchors, ...)
  • Pre-builds text responses for common queries:
    - Daily briefing (all offices summary)
    - Per-office detail (17 offices × 1 response each)
    - Leaderboards (17 offices × 1 response each)
  • Served instantly without LLM call
  Output: pregenerated.pkl
```

### 3.2 Data Sources

| Source | Table | ~Rows | Refresh | Content |
|--------|-------|-------|---------|---------|
| O365 + Verkada | `office_occupancy_o_365_verkada` | ~500k (10 weeks) | Daily | Badge swipe / WiFi events per person per office |
| Workday | `workday_enhanced` | ~5,000 | Daily | Employee directory: name, role, team, manager, hire date |

### 3.3 Pickle File Inventory

| File | Size | Producer | Consumer | Content |
|------|------|----------|----------|---------|
| `enriched.pkl` | ~50MB | enrich.py | query_person.py | Person-day DataFrame with Workday fields |
| `baselines.pkl` | ~200KB | baselines.py | query_office_intel.py, signals.py, chi.py | Per-office attendance rates + trends |
| `personality.pkl` | ~50KB | personality.py | query_office_intel.py | 7-dimension office profiles |
| `anchors.pkl` | ~300KB | anchors.py | query_office_intel.py, chi.py | Leaderboards + anchor stability |
| `visitors.pkl` | ~100KB | visitors.py | query_person.py | Cross-office travel flows + trips |
| `team_sync.pkl` | ~200KB | team_sync.py | query_person.py, query_office_intel.py, chi.py | Team co-presence scores |
| `signals.pkl` | ~50KB | signals.py | query_person.py, query_office_intel.py, chi.py | Decay signals + ghost flags |
| `chi.pkl` | ~20KB | chi.py | query_office_intel.py | Culture Health Index scores |
| `seniority.pkl` | ~100KB | seniority.py | query_office_intel.py, query_person.py | Seniority breakdowns + org leader rollups |
| `manager_gravity.pkl` | ~100KB | manager_gravity.py | query_person.py | Manager pull scores |
| `new_hires.pkl` | ~50KB | new_hires.py | query_person.py | New hire integration curves |
| `weekend.pkl` | ~30KB | weekend.py | query_person.py, query_office_intel.py | Weekend attendance |
| `mixing.pkl` | ~20KB | mixing.py | query_office_intel.py | Cross-functional stream mix |
| `pregenerated.pkl` | ~100KB | pregenerate.py | response_cache.py | Ready-to-serve text responses |

---

## 4. Tool Specifications

### 4.1 `query_office_intel(office=None)`

**File:** `tools/query_office_intel.py`

**Purpose:** Office-level attendance data. No parameters = global summary. With office name = detailed single-office view.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `office` | str | No | Office name (fuzzy matched). Omit for all offices. |

**Logic:**
1. `_ensure_cache()` — lazy-loads all pickle files on first call
2. If no office: `_global_summary()` — iterates all baselines, computes trend per office
3. If office: `_match_office(name)` — case-insensitive partial match against known offices
4. Reads from: baselines, anchors, personality, signals, chi, team_sync, seniority, weekend, mixing

**Output (global):**
```python
{
    "data_through": "2026-03-26",
    "offices": [
        {"name": "Bucharest (AFI)", "people_in": 217, "typical": 195, "avg": 195, "trend": "up"},
        ...
    ],
    "offices_to_watch": ["Phoenix", ...]  # ghost-flagged
}
```

**Output (single office):**
```python
{
    "office": "Prague Rustonka",
    "region": "EMEA",
    "data_through": "2026-03-26",
    "day": "Thu",
    "people_in": 185,
    "typical": 190,
    "peak_day": "Tue",
    "typical_by_day": {"Mon": 160, "Tue": 198, ...},
    "weekly_headcounts": [338, 332, 310, 295],
    "top_people_this_week": [{"name": "...", "role": "R&D", "days": "4/4"}, ...],
    "things_to_note": ["Friday attendance down: 52 vs 67 prior avg"],
    "health_score": 72,
    "teams": {"total_teams": 45, "teams_coming_in_same_days": 30, ...},
    "by_seniority": {"IC": {"people": 120, "avg_days_per_week": 3.2}, ...},
    "weekend": {"people_on_weekends": 8, "avg_per_weekend_day": 3.1},
    "cross_functional_mix": "4.2 of 6 teams present on a typical day"
}
```

### 4.2 `query_person(person=None, office=None, query_type=None)`

**File:** `tools/query_person.py`

**Purpose:** Person-level and specialized queries. Dispatches to 11 sub-functions based on `query_type`.

**Inputs:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `person` | str | No | Name or email (fuzzy matched) |
| `office` | str | No | Office name (for filtering) |
| `query_type` | str (enum) | No | One of 11 values below. Default: "pattern" for person, "who_was_in" for office |

**Query type dispatch:**

| query_type | Function | Data source | Description |
|------------|----------|-------------|-------------|
| `pattern` | `_person_pattern()` | enriched.pkl | Individual attendance pattern |
| `who_was_in` | `_who_was_in()` | enriched.pkl | List of people in office on most recent day |
| `trending_up` | `_trending()` | enriched.pkl | People with biggest attendance increases |
| `trending_down` | `_trending()` | enriched.pkl | People with biggest attendance decreases |
| `visitors` | `_visitors()` | visitors.pkl | Cross-office travel flows and trips |
| `team_sync` | `_team_sync()` | team_sync.pkl | Team co-presence scores |
| `ghost` | `_ghost_offices()` | signals.pkl | Offices with declining signals |
| `org_leader` | `_org_leaders()` | seniority.pkl | Org leader attendance rollups |
| `manager_gravity` | `_manager_gravity()` | manager_gravity.pkl | Manager pull effect on team |
| `new_hires` | `_new_hires()` | new_hires.pkl | New hire integration curves |
| `weekend` | `_weekend()` | weekend.pkl | Weekend attendance |

**Person matching (`_match_person`):**
1. Exact email match
2. Partial email match (e.g. "tom.murphy" → "tom.murphy@veeam.com")
3. Full name match against `preferred_name`
4. Multi-word match (all words must appear in name or email)
5. Last-name match with first-name tiebreaker

**Output (person pattern):**
```python
{
    "name": "Thomas Murphy",
    "office": "Seattle",
    "role": "R&D",
    "title": "Senior Engineer",
    "days_per_week": 4.2,
    "usual_arrival": "6:15am",
    "usual_departure": "4:00pm",
    "avg_dwell_hours": 9.8,
    "days_they_come_in": {"Mon": 8, "Tue": 9, "Wed": 9, "Thu": 8, "Fri": 4},
    "last_4_weeks": [5, 4, 4, 5],
    "total_days_in": 43,
    "total_workdays": 47,
    "holidays_excluded": ["Martin Luther King Jr. Day (2026-01-19)", ...],
    "days_not_in": ["2026-02-09", "2026-02-10", ...]
}
```

---

## 5. Response Caching Strategy

Three-layer caching minimizes LLM calls:

```
User query
  │
  ├─ Layer 1: Pre-generated cache (response_cache.py:check_pregenerated)
  │  • Built by pipeline nightly
  │  • ~35 cached responses: 1 briefing + 17 office details + 17 leaderboards
  │  • Matches via keyword phrases (e.g. "daily briefing" → briefing)
  │  • Hit rate: ~40% of queries
  │  • Latency: <1ms
  │
  ├─ Layer 2: Query cache (response_cache.py:check_query_cache)
  │  • MD5 of normalized query → cached LLM response
  │  • TTL: 300 seconds (5 minutes)
  │  • Catches repeat queries within a conversation
  │  • Latency: <1ms
  │
  └─ Layer 3: Claude LLM call (agent.py:run_agent)
     • Full tool-use loop (usually 1 tool call, sometimes 2)
     • Latency: 3-6 seconds
```

---

## 6. Conversation Management

**State:** In-memory dict in `app.py`, keyed by `conversation_id`.

```python
_conversations = {
    "conv_abc123": {
        "history": [
            {"role": "user", "content": "what's going on in Prague?"},
            {"role": "assistant", "content": "Prague had 185 people..."},
        ],
        "last_active": 1711800000.0,  # epoch seconds
    }
}
```

**Configuration:**
| Setting | Value | Description |
|---------|-------|-------------|
| `_CONV_TTL` | 1800s (30 min) | Conversations expire after 30 minutes of inactivity |
| `_CONV_MAX_HISTORY` | 20 messages | Max 10 user+assistant pairs (older messages trimmed) |

**History trimming in agent.py:**
- Takes last 20 messages from history
- If first message is "assistant", drops it (ensures starts with "user")
- Appends current user message

**Cleanup:** `_cleanup_stale()` runs before each request, evicting expired conversations.

---

## 7. Proactive Briefing Flow

```
Pipeline completes (nightly)
  │
  ├─► pregenerate.py builds briefing text → pregenerated.pkl
  │
  └─► proactive_briefing.py:send_briefing() runs
      │
      ├─► Loads pregenerated briefing text
      ├─► Loads registered_users.json (users who have messaged Presence)
      │
      └─► For each user:
          POST http://gateway:3978/api/proactive
          Body: {conversation_id, user_id, service_url, text}
          │
          └─► gateway/app.py:proactive()
              Builds ConversationReference from stored IDs
              adapter.continue_conversation() → sends message to user's Teams chat
```

**User registration:** The gateway auto-registers every user on their first message
(non-blocking POST to `/api/register_user`). Stored in `data/registered_users.json`.

---

## 8. Configuration (config.py)

### Credentials (environment variables)

| Variable | Description | Source |
|----------|-------------|--------|
| `DATABRICKS_HOST` | Databricks workspace URL | Azure Key Vault |
| `DATABRICKS_TOKEN` | Databricks PAT | Azure Key Vault |
| `DATABRICKS_HTTP_PATH` | SQL warehouse path | Azure Key Vault |
| `ANTHROPIC_API_KEY` | Claude API key | Azure Key Vault |
| `CLAUDE_MODEL` | Model name (default: claude-sonnet-4-20250514) | Environment |

### Office Registry (18 offices)

Each office has: region (Americas/EMEA/APJ), UTC offset, data sources (O365/Verkada), size class (small/mid/large/mega).

Size class drives anchor count: `{"small": 5, "mid": 10, "large": 15, "mega": 20}`

### Pipeline Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `BASELINE_WEEKS` | 8 | Rolling window for computing baselines |
| `PULL_WEEKS` | 10 | Extra buffer when pulling from Databricks |
| `MIN_N_ROLE_SEGMENT` | 10 | Minimum people for role-segmented baselines |
| `HOLIDAY_THRESHOLD` | 0.20 | Days below 20% of baseline excluded from rolling window |

---

## 9. Holiday Handling (pipeline/holidays_cal.py)

Each office maps to a country code (config.OFFICE_COUNTRY). The `holidays` Python package provides per-country public holiday calendars.

**Used in:**
- `baselines.py` — excludes holidays from attendance rate calculation
- `query_person.py` — excludes holidays from "days not in" count, lists excluded holidays by name

**Functions:**
| Function | Purpose |
|----------|---------|
| `is_holiday(office, date)` | Check if date is public holiday for office's country |
| `get_holiday_name(office, date)` | Get holiday name (e.g. "Presidents' Day") |
| `get_workdays(office, start, end)` | Business days minus public holidays |
| `get_workday_count(office, start, end)` | Count of workdays |

---

## 10. System Prompt Design (system_prompt.py)

186-line prompt with these sections:

1. **Identity:** "You are Veeam Presence. You are boring. You state facts."
2. **Tool-first instruction:** "ALWAYS call a tool before answering."
3. **7 complete example responses** — exact tone, length, formatting to match
4. **Rules:** Flat/factual tone, headcounts not percentages, data-through date, follow-up options, no editorializing
5. **Card format:** JSON schema for structured Adaptive Card responses

**Tone:** Deliberately flat and factual. "If 2 people came to Columbus, say '2 people came to Columbus.' Don't call it anything else."

---

## 11. Error Handling

| Layer | Error | Handling |
|-------|-------|----------|
| Gateway | Agent service unreachable | Returns "I'm having trouble connecting right now" |
| Gateway | Agent service 4xx/5xx | Returns "Something went wrong. Try again in a moment." |
| App | Invalid JSON body | HTTP 400 |
| App | Empty message | Returns friendly prompt to ask about attendance |
| App | Claude API failure | Increments error counter, returns generic error message |
| Agent | Unknown tool name | Returns `{"error": "Unknown tool: ..."}` as tool result |
| Agent | Tool execution exception | Returns `{"error": str(e)}` as tool result |
| Tools | Office not found | Returns error + list of available offices |
| Tools | Person not found | Returns error + suggestion to try full name or email |
| Tools | Pickle file missing | Returns "data not available. Run the pipeline first." |

---

## 12. File Index

```
veeam_presence/
├── app.py                    [196 lines] FastAPI agent service
├── agent.py                  [178 lines] Claude orchestration + tool-use loop
├── config.py                 [135 lines] Configuration, office registry, credentials
├── system_prompt.py          [186 lines] LLM system prompt
├── response_cache.py         [ 89 lines] Pre-generated + query response cache
├── proactive_briefing.py     [ 78 lines] Daily briefing push to registered users
├── test_harness.py                       Manual query testing interface
├── tools/
│   ├── __init__.py
│   ├── query_office_intel.py [227 lines] Office attendance data tool
│   └── query_person.py       [541 lines] Person/team/trend data tool (11 query types)
├── cards/
│   ├── __init__.py
│   ├── renderer.py           [107 lines] JSON → Adaptive Card dispatch
│   └── templates.py          [450 lines] 11 Adaptive Card templates
├── pipeline/
│   ├── __init__.py
│   ├── run_analytics.py      [145 lines] Pipeline orchestrator (steps 2-16)
│   ├── pull_events.py        [137 lines] Databricks data pull via PowerShell
│   ├── aggregate.py          [ 93 lines] Raw events → person-day
│   ├── enrich.py             [ 80 lines] Workday join + stream/seniority mapping
│   ├── baselines.py          [228 lines] Rolling 8-week attendance baselines
│   ├── personality.py        [127 lines] 7-dimension office personality profiles
│   ├── anchors.py            [214 lines] Leaderboards + anchor stability tracking
│   ├── visitors.py           [107 lines] Cross-office travel detection
│   ├── team_sync.py          [ 90 lines] Team co-presence scoring
│   ├── signals.py            [129 lines] Ghost detection + decay signals
│   ├── chi.py                [144 lines] Culture Health Index (7-component score)
│   ├── seniority.py          [103 lines] Seniority breakdowns + org leader rollups
│   ├── manager_gravity.py    [111 lines] Manager pull effect on team attendance
│   ├── new_hires.py          [ 93 lines] New hire integration curves
│   ├── weekend.py            [ 77 lines] Weekend/after-hours attendance
│   ├── mixing.py             [ 56 lines] Cross-functional stream mixing
│   ├── holidays_cal.py       [ 77 lines] Per-country holiday calendar engine
│   ├── pregenerate.py        [142 lines] Pre-build common query responses
│   └── qa_check.py           [123 lines] Pipeline output quality checks
├── gateway/
│   ├── app.py                [150 lines] Bot Framework adapter for Teams
│   ├── Dockerfile
│   └── requirements.txt
├── data/                     (gitignored) Pipeline output pickle files
├── tests/
│   └── integration_test.py   62-test suite
├── Dockerfile                Agent service container
├── Dockerfile.pipeline       Pipeline job container
├── docker-compose.yml        Local dev (agent + gateway)
├── requirements.txt          Agent service dependencies
└── requirements.pipeline.txt Pipeline dependencies
```
