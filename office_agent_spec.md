# Veeam Presence — Specification

## What Is This

**Veeam Presence** — a daily intelligence agent that knows what "normal" looks like for every office, every team, and every layer of the organization, and tells you when something interesting is happening. Not a dashboard you stare at — a briefing that finds you.

Silence means normal. Cards appear only when there's something worth saying.

### What this is NOT

- **Not surveillance.** Person-level data is for the individual or their direct manager. It does not power stack-ranking, compliance tracking, or mandate enforcement.
- **Not performance-linked.** Office presence and sales performance have a weak, confounded relationship (validated in prior analysis). This agent does not claim "more office = more output." It measures organizational and cultural health.
- **Not a dashboard.** Dashboards require you to look. This agent tells you when to look and what you're seeing.

---

## Data Sources

### Primary: Office Occupancy Events

**Table:** `dev_catalog.jf_salesforce_bronze.office_occupancy_o_365_verkada`

| Column | Type | Description |
|--------|------|-------------|
| `userPrincipalName` | string | Email address (person identifier) |
| `source` | string | `O365` (Wi-Fi/network) or `Verkada` (physical badge) |
| `timestamp` | timestamp | UTC event time |
| `Office` | string | Office site name (18 offices) |
| `offset` | bigint | UTC offset in seconds |
| `local_timestamp` | timestamp | Localized event time |

**Key properties:**
- **2.3M events**, 4,995 unique people, 18 offices
- **Event-level grain** — multiple events per person per day (1-30+). Enables arrival time, departure proxy, dwell time, and intensity analysis.
- **Two sources:** O365 (76%) = in-office network activity; Verkada (24%) = physical badge readers. Not all offices have both.
- **Pre-filtered:** Validated to contain zero overnight events and zero work-from-home leakage.
- **Date range:** Dec 2024 — present (16+ months). Refreshed daily with ~1-2 day processing lag.
- **Known issue:** Q1 2025 has a sensor deployment gap (~200 extra zero-day rows). Early data needs caveating.

**Offices by headcount:**

| Office | People | Sources | UTC Offset |
|--------|--------|---------|------------|
| Bucharest (AFI) | 1,805 | O365 + Verkada | +2h |
| Atlanta | 982 | O365 + Verkada | -5h |
| Prague Rustonka | 968 | O365 + Verkada | +1h |
| Seattle | 450 | O365 + Verkada | -8h |
| Berlin | 245 | O365 + Verkada | +1h |
| Columbus | 243 | O365 + Verkada | -5h |
| Kuala Lumpur | 241 | O365 | +8h |
| Lisbon | 162 | O365 | 0 |
| Singapore | 161 | O365 | +8h |
| Paris | 157 | O365 | +1h |
| Yerevan | 152 | O365 | +4h |
| Sydney | 135 | O365 | +10h |
| Phoenix | 129 | O365 + Verkada | -7h |
| Mumbai | 99 | O365 | +5:30h |
| Baar | 80 | O365 + Verkada | +1h |
| Buenos Aires | 74 | O365 | -3h |
| Shanghai | 56 | O365 | +8h |
| Mexico | 47 | O365 | -6h |

### Enrichment: People & Organization (Workday)

**Table:** `dev_catalog.revenue_intelligence.workday_enhanced`

6,726 employees, 40 columns. **Join rate to occupancy: 80%** (3,988 of 4,995 matched by email). Key fields:

| Field | What it gives us |
|-------|-----------------|
| `job_family` / `job_family_group` / `stream` | Role-aware baselines (Inside Sales vs. Field Sales vs. R&D vs. Support) |
| `management_level` | 14 tiers from Board of Directors to Para-professional. Seniority analysis. |
| `ismanager` / `Manager_Flag` | Manager identification. 1,216 flagged as managers. |
| `manager_id` / `manager_name` | Direct manager. Enables team-level groupings. |
| `CF_EE_Org_Leader_1` through `_7` | Full reporting chain up to 7 levels. Org-level rollups. |
| `supervisory_organization` | Named team unit. Enables team synchronization analysis. |
| `hire_date` / `original_hire_date` / `continuous_service_date` | Tenure. New hire detection. Integration curve tracking. |
| `VX_Hierarchy` / `location_hierarchy_region` | Region (EMEA/Americas/APJ). |
| `sales_segment` / `sub_region` / `country` | Geographic and segment detail. |
| `businesstitle` / `job_profile` | Specific title for person-level context. |
| `preferred_name` / `legal_name` | Display names for leaderboard and person queries. |
| `worker_status` | Active / On Leave filter. |

### Enrichment: Weather

- Free API (Open-Meteo, no key required) per office city
- Daily: temperature, precipitation, snow, wind
- Purpose: separate behavioral change from weather noise when reporting anomalies
- Per-office learned coefficients over time

### Enrichment: Calendar / Holidays

- Public holiday calendars per office country
- Known company events (all-hands, offsites, SKOs) if available
- School holiday periods by country (optional, v1.5)

### Future: Seat Capacity

- Per-office seat count from facilities
- Enables utilization % and capacity planning
- Not required for v1 — the agent works with headcount and relative metrics

---

## Intelligence Architecture

The agent operates across four tiers. Each tier builds on the one below it.

### Tier 1: Physical Space Intelligence

What's happening in the building today, compared to what's normal.

#### Office Baseline Engine

The foundation. Per-office, per-day-of-week, rolling 8-week window. "Normal for Prague on a Wednesday" is the reference point. Every observation is compared to its own baseline, not a company-wide average.

Baselines are computed at three levels:
1. **Office-wide** — total headcount vs. baseline
2. **Role-segmented** — separate baselines per stream (Sales / R&D / G&A / Cost of Revenue / Marketing). A 15% drop in R&D in Bucharest means something different than a 15% drop in Field Sales in Atlanta.
3. **Seniority-segmented** — separate baselines for IC vs. Manager vs. Director+. Reveals whether drops are top-down or bottom-up.

#### Office Personality Profile

Each office gets a computed behavioral fingerprint, updated on a rolling basis:

| Dimension | What it captures | How it's computed |
|-----------|-----------------|-------------------|
| **Rhythm type** | Steady (4-5 day), spiky (Tue-Wed only), distributed (even spread) | Coefficient of variation across weekdays |
| **Peak shape** | Sharp (everyone arrives at once) vs. gradual (rolling arrivals) | Std deviation of arrival times within a day |
| **Active window** | How long the office is "alive" | Median first-event to last-event per person per day |
| **Arrival center** | When people actually show up | Median arrival time (first event of day, local time) |
| **Weekend boundary** | Hard Friday cliff vs. gradual fade | Friday/Thursday attendance ratio |
| **Volatility** | How predictable is this office week-to-week | 8-week std deviation of daily headcount |
| **Size class** | Mega (1000+), Large (200+), Mid (100+), Small (<100) | Distinct person count. Determines statistical confidence and viable metrics. |

The personality is the lens. Deviations are measured against *that office's own pattern*. Prague at 60% might be a red flag. Atlanta at 60% might be a great day.

#### Dwell Time / Active Window Tracking

Not just "who showed up" but "how long did they stay." Computed from first O365 event to last O365 event per person per day (nobody badges out — last network event is the departure proxy).

Tracked as a baseline dimension: per-office median active window, rolling 8-week. When the active window compresses — people arriving later or leaving earlier — it's a leading indicator that precedes headcount drops.

```
PRAGUE  Active window: 7.2h → 5.8h over 6 weeks (headcount still stable)
  → People are still showing up but not staying — early disengagement signal
```

#### Arrival Drift

Per-office median arrival time, tracked as its own baseline with trend detection. A gradual shift from 8:30am to 10:15am over three months signals a cultural change — "morning remote, afternoon office" — even if daily headcount is flat. This is a rhythm shift in the time-of-day dimension that weekly shape analysis would miss.

#### Dual-Source Confidence

For offices with both O365 and Verkada:
- **Both agree**: high confidence, sustained presence
- **O365 only**: on network but no badge — entered with someone, or Verkada gap
- **Verkada only**: badged but no network activity — brief visit, drive-by

Aggregated per office per day as a **confidence score** and a **drive-by rate**. When dual-source agreement drops, the agent flags it as a data quality issue before interpreting attendance changes. For O365-only offices, the agent notes lower confidence and doesn't attempt drive-by detection.

### Tier 2: Temporal Intelligence

Patterns across time that reveal trends, rhythms, and shifts.

#### Ghost Office Detection

A running composite score tracking four decay signals simultaneously:

1. **Friday erosion** — Friday utilization trending down relative to its own baseline. The canary.
2. **Peak ceiling drop** — the best day of the week is getting worse. The power users are leaving.
3. **Shape flattening** — the gap between peak and trough days is narrowing. The culture is dissolving into uniform mediocrity.
4. **Active window compression** — people who do come in are staying shorter. Ghost offices hollow out before they empty out.

When all signals move in the same direction for 4+ weeks, the agent surfaces it as a narrative, not an alarm.

#### Rhythm Shift Detection

Separate from ghost detection. Sometimes an office doesn't die — it *changes*. The Tuesday-Thursday office becomes Monday-Wednesday. Early-arrival culture shifts to late-arrival. The agent detects when the *shape* changes even if the *level* stays the same, in both the day-of-week and time-of-day dimensions.

#### Seasonal Intelligence

With 16+ months of data, the agent builds seasonal context:
- Year-over-year comparison (March 2026 vs. March 2025) where data permits
- Quarter-end effects (do offices surge or empty at quarter close?)
- Summer slump detection and magnitude per office
- Holiday shoulder effects (the days before/after long weekends)

#### Collaboration Window

The hours per day when >X% of that day's attendees are simultaneously present. This is the actual window where spontaneous interaction happens. If arrivals spread out and departures get earlier, the collaboration window shrinks even if the headcount doesn't. Captures the *quality* of in-office time, not just the quantity.

#### Cohort Overlap (The "Same People?" Test)

For each office, each week: Jaccard similarity between Tuesday's attendance set and Wednesday's attendance set (and every other day-pair). Answers: "Are the same people coming on peak days, or is this two separate shifts that never meet?"

An office with 200 people Tuesday and 200 people Wednesday but only 60 overlap has almost no collaboration value. An office with 120 people both days with 100 overlap has genuine team time. Invisible in headcount metrics.

### Tier 3: Organizational Intelligence

The unique value from combining physical presence with org data.

#### Role-Aware Baselines

Different roles have fundamentally different expected cadences:
- **Inside Sales**: expected in-office most days
- **Field Sales**: almost never in — a 10% baseline is normal
- **R&D / Engineering**: typically high attendance (Bucharest, Prague, Yerevan)
- **Support**: depends on the center
- **G&A / Marketing**: moderate, varies by function

The baseline engine segments by `stream` (5 buckets) and by `job_family` (30+ buckets) for deeper analysis. A 15% office drop isn't a story until you know *which roles* stopped coming.

```
ATLANTA  Overall: 31% (baseline 48%) | -17pp
  Inside Sales: 28% (baseline 62%) | -34pp  ← this is the story
  Field Sales: 8% (baseline 12%) | -4pp     ← noise
  SE: 45% (baseline 52%) | -7pp             ← minor
```

#### Office Leaderboard

Per-office, weekly, named. Celebrates the people who make the office work — culture carriers, not clock-punchers.

**Computation (nightly):**
- For each office, rank all people by days present this week (ties broken by dwell time)
- Compare to prior week: compute trend (up / down / steady)
- Track rolling 4-week streak (consecutive weeks in top 10)

**Leaderboard card:**
```
PRAGUE — Top 10 this week
Week of March 24-28 · 968 employees · 412 appeared this week

1. Jana Novakova (Inside Sales) — 5/5 ↑ was 3/5 · 6 weeks in top 10
2. Martin Holub (Product Engineering) — 5/5 → steady · 12 weeks
3. Petra Svobodova (Technical Support) — 4/5 ↑ was 2/5 · new
4. Tomas Krchnak (Product Engineering) — 4/5 → steady · 8 weeks
5. Sofia Lysenko (Inside Sales) — 4/5 ↓ was 5/5 · 12 weeks
...
```

**Framing in system prompt:** The leaderboard is recognition, not compliance. The tone is "these are the people who make the office work." Never frame as a performance indicator.

#### Manager Gravity

When a manager is in the office, does their team follow? Measure the correlation between manager presence on day T and direct-report presence on day T (and T+1). Some managers are gravitational — their presence measurably increases team attendance. Others are invisible.

#### Team Synchronization Score

Within a `supervisory_organization`, what's the weekly overlap? If a team of 8 has 6 people coming in per week but never more than 2 on the same day, the in-office time has zero collaboration value.

**Team sync** = (average daily co-present team members) / (total team members who came in that week). High sync = coordinated days. Low sync = scheduling past each other.

#### Seniority Inversion Detection

Compare attendance rates by `management_level` bands within each office. When ICs are consistently more present than their leadership chain and the gap is widening, the agent flags the pattern without editorializing.

#### New Hire Integration Curve

Using `hire_date` + occupancy timeline: for each person hired in the last 12 months, plot their office attendance by week-of-tenure. Aggregate into a cohort curve per office.

- **Healthy:** attendance starts moderate, rises over first 4-8 weeks, stabilizes at or near baseline
- **Concerning:** attendance starts high, decays steadily — new hire tried and gave up

Tracked as a per-office metric: **integration slope** — positive = ramping in, negative = disengaging.

#### Cross-Functional Collision Potential

On any given day at an office, which `stream` groups are represented? Measured as a **mixing score**: how many stream-pairs have at least N people from each present? If mixing is declining, teams are siloing physically.

### Tier 4: Network & Predictive Intelligence

Cross-office and forward-looking signals.

#### Cross-Office Visitor Flows

A person appearing in Prague on Monday and Berlin on Wednesday is traveling. Track:
- **Visitor volume** per office per month
- **Flow direction**: which offices send visitors where
- **Visitor role context**: "Berlin received 12 visitors from Prague — 8 Engineering, 4 Product"
- **Magnet offices** / **Isolated offices**

Home office inferred as most-frequent office over trailing 8 weeks.

#### Company-Wide Trend Layer

Global summary before per-office cards:
```
GLOBAL PULSE — Week of March 23
  18 offices | 2,310 active this week | 8-week trend: -4%
  Americas: -9% vs baseline | EMEA: +3% | APJ: flat
  Inside Sales globally: -8% over 4 weeks — emerging pattern
```

#### Underutilization Score

For smaller offices, tracks how often the office hits meaningful attendance thresholds:
```
MEXICO  Days with 10+ people this month: 4 of 20
  Trend: declining (was 8 of 20 two months ago)
```
Not a "kill this office" signal. Data for the space allocation conversation.

#### Weekend / After-Hours Signal

Tracked per office: is weekend presence growing, concentrated in specific teams, always the same people? Surfaced when a trend emerges, not on every briefing.

#### Culture Health Index (CHI)

Composite per-office score. Seven components, each 0-100, weighted:

| Component | Weight | What it measures | Scoring |
|-----------|--------|-----------------|---------|
| **Consistency** | 20% | Week-to-week headcount volatility per DOW | CV across 8 weeks. CV=0→100, CV=0.5→0 |
| **Depth** | 15% | Active window vs. own baseline | current_dwell / baseline_dwell × 100 |
| **Synchronization** | 20% | Team-level pairwise co-presence rates | Mean Jaccard across teams × 100 |
| **Anchor Stability** | 15% | Top-10 anchor retention over 8 weeks | retained/10 × 100 |
| **Integration** | 10% | New hire attendance slope | Positive slope → high, negative → low. Default 70 if <3 hires |
| **Leadership Presence** | 10% | IC-vs-leadership gap trajectory | Gap widening → lower. Stable gap → 80 |
| **Breadth** | 10% | Cross-functional stream representation | Daily qualifying streams / max possible × 100 |

Reported with weekly trend and component-level breakdown:
```
ATLANTA  CHI: 44 (↓3/week for 6 weeks)
  Driving decline: Synchronization (22 ↓8), Anchor Stability (30 ↓12)
  Holding steady: Consistency (68), Depth (55), Breadth (71)
```

---

## Daily Briefing

The primary output. Pushed every morning. Tiered, not flat. On quiet days the briefing is short — a few lines confirming everything is normal. On active days it tells you exactly where to look.

### Level 1: Global Pulse (always present)

```
VEEAM PRESENCE — March 28, 2026
Data through: March 26 (Thursday)
═══════════════════════════════════════════════

GLOBAL PULSE
  18 offices | 2,310 active this week | 8-week trend: -4%
  Americas: -9% vs baseline | EMEA: +3% | APJ: flat
  Inside Sales globally: -8% over 4 weeks — emerging pattern
```

### Level 2: Office Cards (only when notable)

```
PRAGUE ██████████████████░░ 84% | baseline 71% | +13pp
  R&D: 91% (+8pp) | Sales: 68% (+22pp ← unusual)
  Active window: 7.8h (normal) | Arrival: 8:20am (25min early)
  Weather-adjusted: +6pp (rainy day, typically +7pp)
  Anchors: 11/12 present | Team sync: 0.72 (high)
  Culture Health: 81 (stable)
  → 3rd consecutive day above baseline — emerging surge
  → Sales surge coincides with quarter-end — likely temporary

ATLANTA ██████░░░░░░░░░░░░░░ 31% | baseline 48% | -17pp
  Inside Sales: 28% (baseline 62%) | -34pp ← the story
  Active window: 4.1h (baseline 6.2h) — people leaving early
  Weather-adjusted: -12pp (clear day, no weather excuse)
  Anchors: 2/8 present | Team sync: 0.18 (low)
  Culture Health: 44 (declining, -3/week for 6 weeks)
  → Inside Sales driving the drop — Field Sales and SE unchanged
  → Friday pattern appearing on Wednesdays — watch this

BUCHAREST — no card (within baseline, CHI stable)
COLUMBUS — no card
SEATTLE — no card
```

### Level 3: Organizational Signals (only when triggered)

```
ORG SIGNALS
  New hire integration: Prague curve is healthy (positive slope)
  New hire integration: Atlanta curve is decaying — 6 of 8 recent hires
    trending below office baseline by week 8
  Seniority inversion widening in Berlin — Director+ attendance
    dropped to 1.1 days/week while IC steady at 3.4
```

### Level 4: Watch List (persistent, updated weekly)

```
WATCH LIST (not urgent, developing)
  ◦ Mexico underutilization: 4 of 20 days above 10 people (declining)
  ◦ Atlanta anchor group: 40% turnover since January
  ◦ Shanghai: only 12 unique people appeared this month
  ◦ Prague-Berlin visitor traffic up 3x — investigate driver
```

### Quiet Day Briefing

When nothing notable is happening:

```
VEEAM PRESENCE — March 28, 2026
Data through: March 26 (Thursday)
═══════════════════════════════════════════════

GLOBAL PULSE
  18 offices | 2,280 active this week | 8-week trend: flat
  All offices within baseline. No active signals.

WATCH LIST (unchanged)
  ◦ Mexico underutilization: trending (week 7 of 8)
```

### Card Trigger Rules

| Trigger | Threshold |
|---------|-----------|
| Deviation from DOW baseline | > ±10pp (configurable) |
| Role-segmented deviation | > ±15pp for any stream within an office |
| Active window compression | > 1.5h below baseline sustained 2+ weeks |
| Ghost score threshold crossed | Composite of Friday + peak + shape + dwell |
| Rhythm shift sustained | Profile change held 4+ weeks |
| Anchor erosion | 2+ anchors absent 3+ consecutive weeks |
| Team sync collapse | Score drops below 0.2 for 3+ weeks |
| Seniority inversion widening | Gap increased >1 day/week over 8 weeks |
| New hire integration decay | Negative slope sustained across 3+ recent hires |
| CHI decline | >3 points/week for 4+ consecutive weeks |
| Cross-office visitor spike | >2x vs. 8-week average |
| Underutilization (small offices) | <5 people on >60% of working days |
| Weather-adjusted anomaly | Large deviation with no weather explanation |

### No-Card Rule

If an office is within ±5pp of its baseline, all role segments within ±10pp, no background signals active, and CHI stable — no card. Three offices producing cards is a busy day. Zero cards is the goal.

---

## Conversational Queries

Beyond the briefing, the agent answers questions on demand. No restrictions on person-level queries — access is controlled at the user level via Azure AD security group.

### Office Queries

| Query | Response |
|-------|----------|
| "How's Prague trending?" | Personality, CHI, all active signals, 8-week trend by role segment |
| "Compare Atlanta and Bucharest" | Side-by-side profiles, different rhythms, role composition, relative trends |
| "Emptiest office on Fridays?" | Ranked list with role context |
| "Biggest attendance change this quarter?" | Trend comparison across sites with role decomposition |
| "Monday vs Friday across all offices?" | Day-of-week comparison with cohort overlap analysis |
| "Show me the last 6 months for Bucharest" | Time series: rhythm, trend, CHI, notable events, seasonal effects |
| "When did Atlanta start declining?" | Inflection point detection — which role segment broke first |
| "What happened the week of SKO?" | Event-annotated view, before/during/after comparison |
| "Which offices have the best team sync?" | Ranked by synchronization score with team-level detail |
| "Where are our cross-office travel hotspots?" | Visitor flow network, top corridors, role breakdown |
| "Show me the leaderboard for Prague" | Top 10 with names, roles, trends, streaks |
| "Who's trending up the most across all offices?" | Global leaderboard of biggest attendance increases |

### People Queries

| Query | Response |
|-------|----------|
| "Show me Scott's attendance pattern" | Personal rhythm, trend, comparison to office baseline, role-peer comparison |
| "Who are the anchors in Prague?" | Top 10 consistent attenders with role, title, streak length |
| "Who overlaps with Scott the most?" | Same-office, same-day frequency — "who you'd bump into" |
| "Who's been coming in less lately?" | People whose pattern shifted down, with tenure and role context |
| "Is anyone in Atlanta today?" | Most recent day's attendance for a site |
| "How are new hires integrating in Berlin?" | Cohort integration curves for recent hires |

### Team Queries

| Query | Response |
|-------|----------|
| "How's Sarah Chen's team doing?" | Team sync score, attendance by member, manager-team correlation |
| "Which teams in EMEA have the lowest sync?" | Ranked supervisory_organizations by synchronization score |
| "Are managers in Prague coming in more than ICs?" | Seniority breakdown for that office |
| "Show me Tim Pfaelzer's org attendance" | Org leader rollup using hierarchy fields |
| "Which departments mix the most in Bucharest?" | Cross-functional collision scores |

### Proactive Signals

| Signal | Trigger |
|--------|---------|
| **Ghost office early warning** | Friday + peak + shape + dwell all declining 4+ weeks |
| **Rhythm shift** | Weekly shape changed and held 4+ weeks |
| **Anchor erosion** | 2+ anchors absent 3+ weeks |
| **Team sync collapse** | Score below 0.2 for 3+ weeks |
| **Seniority inversion** | Gap widening between IC and leadership attendance |
| **New hire disengagement** | Negative integration slopes across multiple recent hires |
| **Cross-office surge** | Visitor traffic to a site spikes >2x |
| **Active window compression** | Median dwell declining while headcount stable |
| **Weather-adjusted anomaly** | Large deviation with no weather explanation |
| **CHI decline** | CHI dropping 3+/week for 4+ weeks |

---

## Conversation Starters

9 starters displayed before user types anything. Sound like a person, not a menu. Each triggers a specific card template. Static text, live data on first click.

| # | Title | Text on Click | Template |
|---|-------|---------------|----------|
| 1 | How are our offices doing? | "Give me the global pulse — which offices are trending up or down this week?" | Global Pulse |
| 2 | Which office has the strongest culture? | "Which office has the highest Culture Health Index and what's driving it?" | Standard Insight |
| 3 | Are teams actually overlapping? | "Are teams coming in on the same days, or are people scheduling past each other?" | Comparison |
| 4 | Show me the leaderboard | "Who are the top office attenders across the company this week?" | Leaderboard |
| 5 | Are new hires integrating? | "Are recent hires establishing office rhythm, or fading out after the first few weeks?" | Standard Insight |
| 6 | Where is office culture eroding? | "Are any offices showing early signs of ghost-office decay?" | Standard Insight (attention) |
| 7 | Who's traveling where? | "Which offices are sending and receiving the most cross-office visitors?" | Network/Flow |
| 8 | Is leadership showing up? | "Is there a gap between leadership and IC attendance, and is it growing?" | Comparison |
| 9 | Surprise me | "What's the most interesting pattern you're seeing in office presence right now?" | Varies |

3 slots reserved for pilot feedback.

### Welcome Card

```
WELCOME TO VEEAM PRESENCE

I monitor every office across the company — attendance patterns, team
synchronization, cultural health signals, and emerging trends — analyzed
daily and ready to query.

4,995 people · 18 offices · 16 months of history · refreshed daily

Buttons:
  [Show me today's briefing]
  [Which offices need attention?]
  [Show me the leaderboard]
  [Surprise me]
```

---

## Adaptive Card Templates

Claude outputs a structured response object. The API layer renders it into Adaptive Card JSON. Claude never writes raw Adaptive Card markup.

### Design Rules

- **Every number tells a story** — never "Attendance: 31%". Always "Attendance: 31% — 17pp below baseline."
- **Urgency is visual** — `default` (neutral), `attention` (amber, warnings), `good` (green, positive)
- **Scannable in 3 seconds** — headline is the takeaway; body is support; facts are evidence; actions are next moves
- **Mobile-first** — ColumnSets stack vertically. No horizontal tables.
- **No brand header after welcome** — bot avatar identifies Presence

### Templates

| # | Template | Use Case | Key Elements |
|---|----------|----------|-------------|
| 1 | **Standard Insight** | Most queries. CHI, ghost, role breakdowns, anchors. | headline, body, facts (max 8), context_note, actions (max 4) |
| 2 | **Data Comparison** | Office vs. office, QoQ, seniority splits, before/after. | Two columns + summary_line for mobile fallback |
| 3 | **Office Profile** | Deep dive on a single office. | office_stats, chi_breakdown, role_breakdown, signals, actions |
| 4 | **Leaderboard** | Top 10 per office with names, roles, trends, streaks. | entries (max 10), subtitle with office stats |
| 5 | **Team View** | Team sync, manager correlation, member attendance. | team_stats, member_list, actions |
| 6 | **Welcome** | First contact. Brand header, data scale, 4 buttons. | capability_statement, data_scale, starter_buttons |
| 7 | **Daily Briefing** | Proactive morning push. 4-level structure. | global_pulse, office_cards, org_signals, watch_list |
| 8 | **Empty State** | No data for filter. | message, suggestions |
| 9 | **Error State** | System error. | error_message, retry_suggestion |

### Size Limits (Teams enforced)

- FactSet: max 8 facts
- Leaderboard: max 10 entries
- Office cards in briefing: max 5 (with "Show all notable offices" overflow)
- Actions per card: max 4
- Total character limit: ~3,000 chars

### Example: Leaderboard Card

```json
{
  "template": "leaderboard",
  "card_tone": "good",
  "headline": "Prague — Top 10 this week",
  "subtitle": "Week of March 24-28 · 968 employees · 412 appeared",
  "entries": [
    {
      "rank": 1,
      "name": "Jana Novakova",
      "role": "Inside Sales",
      "days": "5/5",
      "trend": "up",
      "prior": "3/5",
      "streak": "6 weeks in top 10"
    }
  ],
  "context_note": "Based on O365 + Verkada presence. 80% Workday match.",
  "actions": [
    {"label": "All 18 offices", "message": "Show leaderboards for all offices"},
    {"label": "Trending up fastest?", "message": "Who improved attendance the most in 4 weeks?"},
    {"label": "Compare to last month", "message": "How has Prague's top 10 changed?"}
  ]
}
```

### Example: Office Profile Card

```json
{
  "template": "office_profile",
  "card_tone": "attention",
  "headline": "Atlanta is in a sustained decline — Inside Sales driving the drop",
  "body": "6 consecutive weeks below baseline. Active window compressing. Anchor group turned over 40% since January.",
  "office_stats": {
    "attendance": "31%",
    "baseline": "48%",
    "delta": "-17pp",
    "chi": "44",
    "chi_trend": "declining 3/week for 6 weeks"
  },
  "chi_breakdown": [
    {"component": "Synchronization", "score": 22, "trend": "declining"},
    {"component": "Anchor Stability", "score": 30, "trend": "declining"},
    {"component": "Depth", "score": 55, "trend": "declining"},
    {"component": "Consistency", "score": 68, "trend": "stable"},
    {"component": "Leadership", "score": 61, "trend": "stable"},
    {"component": "Breadth", "score": 71, "trend": "stable"},
    {"component": "Integration", "score": 38, "trend": "declining"}
  ],
  "role_breakdown": [
    {"stream": "Inside Sales", "rate": "28%", "baseline": "62%", "delta": "-34pp"},
    {"stream": "R&D", "rate": "72%", "baseline": "68%", "delta": "+4pp"},
    {"stream": "G&A", "rate": "41%", "baseline": "45%", "delta": "-4pp"}
  ],
  "context_note": "982 matched employees. 80% Workday coverage.",
  "actions": [
    {"label": "Which teams?", "message": "Show team sync scores for Atlanta"},
    {"label": "Anchor changes", "message": "Who were anchors 8 weeks ago vs now?"},
    {"label": "Compare to Prague", "message": "Compare Atlanta and Prague"}
  ]
}
```

---

## Architecture

### Deployment

| Component | Technology |
|-----------|-----------|
| **Runtime** | Azure Container App (single container) |
| **Frontend** | Microsoft Teams (1:1 bot) + Microsoft Copilot (agent channel) |
| **Integration** | M365 Agents SDK (Python) |
| **Reasoning** | Claude Sonnet 4.6 via Anthropic API with tool_use |
| **Data** | Databricks SQL warehouse |
| **Access control** | Azure AD security group `SG-PI-Users` |

### System Flow

```
Exec in Teams / Copilot
    ↓ (HTTPS)
FastAPI /api/messages endpoint
    ↓
Claude reasoning engine (system prompt + tool_use)
    ↓
4-tool dispatcher:
    ├─ query_office_intel()  → Tier 1 cache (sub-second)
    ├─ query_org_intel()     → Tier 1 cache (sub-second)
    ├─ query_occupancy()     → Tier 2 live SQL (2-5 sec)
    └─ query_person()        → Tier 2-3 live SQL (2-5 sec)
    ↓
Response rendering:
    ├─ Structured response object → Adaptive Card
    └─ Plain text → chat message
```

### Three-Tier Query Architecture

| Tier | Source | Latency | Coverage |
|------|--------|---------|----------|
| **Tier 1** | In-memory cache (pre-computed nightly) | <100ms | ~70% of questions |
| **Tier 2** | Live SQL against Databricks | 2-5 sec | Custom filters |
| **Tier 3** | Person-level detail queries | 2-5 sec | Specific drilldowns |

### Four Tools

| Tool | Tier | What it serves |
|------|------|---------------|
| `query_office_intel` | 1 | Baselines, personality, signals, CHI, leaderboard for any office |
| `query_org_intel` | 1 | Team sync, seniority splits, new hire curves, cross-office flows, global pulse |
| `query_occupancy` | 2 | Live SQL for custom filters (specific team, date range, role, office combo) |
| `query_person` | 2-3 | Individual attendance patterns, overlaps, trends |

### Nightly Pre-Computation Pipeline

Runs ~2:00 AM UTC. Pure Python math — no Claude API calls needed.

```
1. Pull yesterday's occupancy events from Databricks
2. Aggregate to person-day level (arrival, departure, dwell, office, source)
3. Join to Workday (role, team, manager, seniority, name)
4. Recompute rolling 8-week baselines (per office × DOW × role segment)
5. Recompute office personality profiles
6. Recompute anchor lists and leaderboards (with trends, streaks)
7. Recompute team sync scores, cohort overlaps
8. Run signal detectors (ghost, rhythm shift, anchor erosion, dwell compression, seniority inversion)
9. Recompute CHI components and composite
10. Compute cross-office visitor flows
11. Generate daily briefing content
12. Write to pre-computed tables / in-memory store
```

### Conversation State

- In-memory cache keyed by Teams conversation ID
- TTL: 30 minutes (auto-expire)
- Capacity: last 10 message pairs
- History trimming: tool results stripped, only user messages + final responses kept
- On restart: cache lost (acceptable at exec volume)

### Local Testing

**CLI Test Harness** (primary dev mode):
```
python test_harness.py

PI> How's Prague trending?
[tool: query_office_intel(office="Prague Rustonka")] → 0.08s

PRAGUE RUSTONKA  ██████████████████░░ 84% | baseline 71% | +13pp
  R&D: 91% (+8pp) | Sales: 68% (+22pp)
  CHI: 81 (stable) | Team sync: 0.72
  → 3rd consecutive day above baseline
  [Card JSON → output/last_card.json]

PI> _
```

Claude API with tool_use, real Databricks data, formatted text output with card JSON capture. Iterate on system prompt, tools, and response quality without any Azure/Teams infrastructure.

**Local Bot with ngrok** (Teams integration testing):
1. `uvicorn app:main --port 3978`
2. `ngrok http 3978`
3. Update Azure Bot messaging endpoint to ngrok URL
4. Test in Teams against real bot registration

### Data Freshness

Pipeline refreshes daily with ~1-2 day processing lag. The briefing states the data-through date explicitly ("Data through: March 26"). Do not caveat every response. Be honest when the user asks about "today" or "right now": "My data refreshes overnight — most recent data is from Thursday March 26."

### Proactive Daily Briefing

Pushed every morning (7:00 AM per geo):
- Always pushed, even on quiet days (quiet = short 2-line confirmation)
- Content only includes what changed or is notable
- Users auto-registered on first chat
- Generated from pre-computed briefing content (no real-time queries needed)

### Error Handling

| Failure | Response |
|---------|----------|
| Databricks unreachable | "I'm having trouble reaching the data warehouse. Usually resolves in a few minutes." |
| Claude API rate limit | "Processing a lot of queries — give me 30 seconds." |
| Tool returns empty | Claude handles naturally: "I don't have data for that filter. Try..." |
| Off-topic request | "I'm focused on office presence intelligence. Want to explore any of the areas I cover?" |

### Cost Model

- **Query time:** ~$0.02-0.06/query (Claude API). At 10-20 queries/day = ~$0.50-1.00/day
- **Nightly compute:** Pure Python, no Claude calls. Databricks warehouse time only (~$20-50/mo if shared)
- **Infrastructure:** Container App ~$30-50/mo
- **Total monthly:** ~$50-100

---

## System Prompt Design

### Identity

> You are Veeam Presence, a conversational intelligence agent for senior leadership. You monitor every office across the company — attendance patterns, team synchronization, cultural health, and emerging trends. You are not a dashboard. You are the chief of staff who walks every office floor every day and tells leadership what they need to know.

### Audience

CROs, CMOs, CPOs, CEOs, regional VPs, chiefs of staff. They think in organizational health, culture, real estate efficiency, and talent retention — not SQL or data models.

### Core Principles

1. **Lead with insight, anchor in evidence.** Bad: "Atlanta attendance was 31%." Good: "Atlanta is hollowing out — Inside Sales dropped 34pp and people who do come in are leaving 2 hours early."

2. **Guide the next move.** Always offer 2-3 specific follow-ups: "The drop is concentrated in Inside Sales. Want me to show which teams?"

3. **Recommendations opt-in.** Default is insight + evidence. Prescriptive only when asked.

4. **Be concise.** Headline → 2-3 data points → drill-down paths → stop.

5. **Transparency on gaps.** "Occupancy data covers 80% of the workforce — 20% are unmatched to Workday records (likely contractors)."

6. **No jargon.** "Office days" not "person-day aggregations." "Teams" not "supervisory organizations."

7. **Recognition, not surveillance.** Leaderboards celebrate consistency. Person queries are factual and neutral. Never frame attendance as a performance indicator.

### Tone

Professional, direct, confident. The smartest workplace analyst in the room who respects the exec's time.
- No hedging ("seems like maybe")
- No filler ("Great question!")
- No jargon ("O365 events," "Jaccard overlap")
- Use "people," "days in office," "teams," not technical terms

### Response Format Logic

**Use a card** when: structured data, metrics, comparisons, leaderboards, or first answer to a topic.

**Use plain text** when: short answer (1-2 sentences), strategic advice, clarifying questions, conversational follow-up.

### Data Freshness Rule

Data refreshes overnight. Do not caveat every response. Be honest when asked about "today": "My data refreshes overnight — most recent is from [date]."

### What Presence Does NOT Do

- Rank people by attendance for performance purposes
- Enforce office mandates or policy compliance
- Claim that office attendance drives performance
- Access or modify HR systems
- Share data outside the `SG-PI-Users` security group

---

## Roadmap

### v1 — Core

| Feature | Notes |
|---------|-------|
| Office baselines (per-DOW, rolling 8-week, role-segmented) | Foundation |
| Daily briefing (4-level: global, cards, org signals, watch list) | Primary output |
| Office personality profiles | Rhythm, peak shape, active window, arrival, volatility |
| Dwell time / active window tracking | First/last O365 event |
| Arrival drift | Median arrival as tracked baseline |
| Anchors | Top attenders per office, erosion tracking |
| Office leaderboard | Top 10 per office, names, roles, trends, streaks |
| Ghost / rhythm shift detection | Composite score with 4 signals |
| Role-aware baselines | Workday join, segment by stream |
| Team synchronization scoring | Per team Jaccard overlap |
| Cohort overlap (same-people test) | Per office day-pair Jaccard |
| Cross-office visitor tracking | Flow network |
| Company-wide trend layer | Global pulse |
| Underutilization score | Small office viability |
| Dual-source confidence | Background quality check |
| Culture Health Index | 7-component composite |
| Conversational queries (office, person, team) | On-demand |
| CLI test harness | Local development |
| Azure Container App deployment | Production |
| Teams + Copilot integration | M365 Agents SDK |

### v1.5

| Feature | Notes |
|---------|-------|
| Weather adjustment | Open-Meteo, per-office learned coefficients |
| Holiday / event annotation | Public calendars, company events |
| Manager gravity scoring | Manager-team attendance correlation |
| Seniority inversion detection | Management level comparison |
| New hire integration curves | Cohort analysis by office |
| Cross-functional collision scoring | Stream mixing per office |
| Weekend / after-hours tracking | Per office, per team |
| Seasonal decomposition | YoY, quarter-end, summer patterns |

### v2

| Feature | Notes |
|---------|-------|
| Capacity simulation | Needs seat counts from facilities |
| Predictive attendance forecasting | History + weather forecast + calendar |
| Attrition precursor signal | Consistent attenders whose pattern drops |
| Physical collaboration network map | Cross-office graph visualization |
| Org-leader rollup views | Full hierarchy aggregation |

---

## Resolved Questions

| Question | Answer |
|----------|--------|
| Data grain? | Event-level. Multiple events per person per day (1-30+). |
| How many offices? | 18. Feasible for all-office queries. |
| Person identifier? | Email (userPrincipalName). Joins to Workday on email. 80% match. |
| Role/job family? | Not on occupancy table. LEFT JOIN to workday_enhanced. |
| Data refresh? | Daily, ~1-2 day lag. Pipeline healthy as of March 2026. |
| Delivery? | Azure Container App → Teams + Copilot. Daily push + conversational. |
| Audience? | Senior leadership (same as Veeam Signal). |
| Person query access? | No restrictions. Access controlled at user level via SG-PI-Users. |
| Leaderboard? | Per-office, weekly, named with roles/trends/streaks. |
| Testing? | CLI harness first (Claude API + real data), then ngrok for Teams. |
| Name? | Veeam Presence. |
