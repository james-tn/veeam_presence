"""Adaptive Card templates — designed for Teams rendering.

Design principles:
- Visual hierarchy: big numbers up top, details below
- Compact: use ColumnSets as table rows, not one per item
- Color: green (good) for above normal, attention (amber) for below
- Mobile-first: stacks vertically on narrow screens
- Scannable in 3 seconds: headline visible without scrolling
"""

# Veeam green for accent
VEEAM_GREEN = "Good"
VEEAM_ATTENTION = "Attention"


def briefing_card(data):
    """Daily briefing — all offices ranked. Top 5 detailed, rest compact."""
    offices = data.get("offices", [])
    date = data.get("data_through", "")
    total = data.get("total_people_in", sum(o["people_in"] for o in offices))

    # Header
    body = [
        {"type": "TextBlock", "text": f"Veeam Presence — {date}", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "TextBlock", "text": f"{total} people across {len(offices)} offices", "size": "Small", "isSubtle": True, "spacing": "None"},
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "stretch", "items": [
                {"type": "TextBlock", "text": "Office", "weight": "Bolder", "size": "Small", "isSubtle": True}]},
            {"type": "Column", "width": "80px", "items": [
                {"type": "TextBlock", "text": "People", "weight": "Bolder", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}]},
            {"type": "Column", "width": "60px", "items": [
                {"type": "TextBlock", "text": "vs typical", "weight": "Bolder", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}]},
        ], "spacing": "Medium"},
    ]

    # Office rows
    for o in offices:
        diff = o["people_in"] - o["typical"]
        diff_str = f"+{diff}" if diff > 0 else str(diff) if diff != 0 else "—"
        color = "Good" if diff > 5 else ("Attention" if diff < -5 else "Default")

        body.append({
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": o["name"], "size": "Small", "weight": "Bolder" if o["people_in"] > 50 else "Default"}
                ]},
                {"type": "Column", "width": "80px", "items": [
                    {"type": "TextBlock", "text": str(o["people_in"]), "size": "Small", "horizontalAlignment": "Right", "weight": "Bolder"}
                ]},
                {"type": "Column", "width": "60px", "items": [
                    {"type": "TextBlock", "text": diff_str, "size": "Small", "horizontalAlignment": "Right", "color": color}
                ]},
            ],
            "spacing": "None",
        })

    return _wrap_card(body=body, actions=_actions([
        ("Quietest offices", "Which offices are really quiet?"),
        ("Leaderboard", "Show me the leaderboard for Prague"),
        ("Trending up", "Who's trending up the most?"),
    ]))


def office_detail_card(data):
    """Single office deep dive."""
    office = data.get("office", "")
    people = data.get("people_in", 0)
    typical = data.get("typical", 0)
    diff = people - typical
    day = data.get("day", "")
    date = data.get("data_through", "")
    health = data.get("health_score", "")

    # Header with hero number
    body = [
        {"type": "TextBlock", "text": office, "weight": "Bolder", "size": "Large", "color": "Accent"},
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "auto", "items": [
                {"type": "TextBlock", "text": str(people), "size": "ExtraLarge", "weight": "Bolder"},
                {"type": "TextBlock", "text": f"people on {day}", "size": "Small", "isSubtle": True, "spacing": "None"},
            ]},
            {"type": "Column", "width": "stretch", "items": [
                {"type": "FactSet", "facts": [
                    {"title": "Typical", "value": str(typical)},
                    {"title": "Difference", "value": f"+{diff}" if diff > 0 else str(diff)},
                ] + ([{"title": "Health", "value": f"{health}/100"}] if health else [])},
            ]},
        ]},
    ]

    # Typical by day
    tbd = data.get("typical_by_day", {})
    if tbd:
        day_row = " · ".join(f"**{d}** {n}" for d, n in tbd.items())
        body.append({"type": "TextBlock", "text": f"Typical week: {day_row}", "size": "Small", "wrap": True, "spacing": "Medium"})

    # Weekly trend
    weekly = data.get("weekly_headcounts", [])
    if weekly:
        body.append({"type": "TextBlock", "text": f"Weekly totals: {' → '.join(str(w) for w in weekly)}", "size": "Small", "isSubtle": True})

    # Notes
    notes = data.get("things_to_note", [])
    if notes:
        for note in notes[:2]:
            body.append({"type": "TextBlock", "text": f"📌 {note}", "size": "Small", "color": "Attention", "wrap": True})

    # Top people
    top = data.get("top_people_this_week", [])
    if top:
        body.append({"type": "TextBlock", "text": "Top people this week", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        for p in top[:5]:
            body.append({"type": "TextBlock", "text": f"**{p['name']}** ({p.get('role', '')}) — {p['days']}", "size": "Small", "spacing": "None"})

    # Seniority
    sen = data.get("by_seniority", {})
    if sen:
        body.append({"type": "TextBlock", "text": "By level", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        for band, s in sen.items():
            body.append({"type": "TextBlock", "text": f"{band}: {s['people']} people, {s['avg_days_per_week']} days/week avg", "size": "Small", "spacing": "None"})

    return _wrap_card(body=body, actions=_actions([
        (f"Leaderboard", f"Show me the leaderboard for {office}"),
        (f"Trending", f"Who's trending up in {office.split()[0]}?"),
        ("Compare", "Compare to another office"),
    ]))


def leaderboard_card(data):
    """Top people per office."""
    entries = data.get("entries", data.get("top_people_this_week", []))
    office = data.get("office", "")

    body = [
        {"type": "TextBlock", "text": f"Leaderboard — {office}" if office else "Leaderboard", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        # Column headers
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "20px", "items": [{"type": "TextBlock", "text": "#", "size": "Small", "isSubtle": True}]},
            {"type": "Column", "width": "stretch", "items": [{"type": "TextBlock", "text": "Name", "size": "Small", "isSubtle": True}]},
            {"type": "Column", "width": "50px", "items": [{"type": "TextBlock", "text": "Days", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}]},
        ], "spacing": "Small"},
    ]

    for i, entry in enumerate(entries[:10], 1):
        name = entry.get("name", "")
        role = entry.get("role", entry.get("stream", ""))
        days = entry.get("days", "")
        trend = entry.get("trend", "")
        trend_icon = {"up": " ↑", "down": " ↓"}.get(trend, "")

        body.append({
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "20px", "items": [
                    {"type": "TextBlock", "text": str(i), "size": "Small", "weight": "Bolder"}]},
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": f"**{name}**", "size": "Small"},
                    {"type": "TextBlock", "text": role, "size": "Small", "isSubtle": True, "spacing": "None"},
                ]},
                {"type": "Column", "width": "50px", "items": [
                    {"type": "TextBlock", "text": f"{days}{trend_icon}", "size": "Small", "horizontalAlignment": "Right", "weight": "Bolder"}]},
            ],
            "spacing": "None",
        })

    return _wrap_card(body=body, actions=_actions([
        (f"About {office}" if office else "All offices", f"Tell me about {office}" if office else "Give me the daily briefing"),
        ("Trending up", "Who's trending up the most?"),
    ]))


def person_card(data):
    """Individual person pattern."""
    name = data.get("name", "")
    office = data.get("office", "")

    body = [
        {"type": "TextBlock", "text": name, "weight": "Bolder", "size": "Large", "color": "Accent"},
        {"type": "TextBlock", "text": f"{data.get('title', '')} · {office}", "size": "Small", "isSubtle": True, "spacing": "None"},
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "stretch", "items": [
                {"type": "FactSet", "facts": [
                    {"title": "Days/week", "value": str(data.get("days_per_week", ""))},
                    {"title": "Arrives", "value": data.get("usual_arrival", "N/A")},
                    {"title": "Leaves", "value": data.get("usual_departure", "N/A")},
                    {"title": "Avg stay", "value": f"{data.get('avg_dwell_hours', 0)}h"},
                ]},
            ]},
            {"type": "Column", "width": "stretch", "items": [
                {"type": "FactSet", "facts": [
                    {"title": "Days in", "value": f"{data.get('total_days_in', '')} of {data.get('total_workdays', '')} workdays"},
                ]},
            ]},
        ]},
    ]

    # Day pattern
    dow = data.get("days_they_come_in", {})
    if dow:
        max_days = max(dow.values()) if dow.values() else 1
        day_items = []
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            n = dow.get(d, 0)
            bar = "█" * int(n / max_days * 5) if max_days > 0 else ""
            day_items.append({"type": "TextBlock", "text": f"**{d}** {bar} {n}", "size": "Small", "spacing": "None"})
        body.append({"type": "TextBlock", "text": "Day pattern", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        body.extend(day_items)

    # Absent dates
    absent = data.get("days_not_in", [])
    if absent and len(absent) <= 20:
        body.append({"type": "TextBlock", "text": f"Days not in ({len(absent)}): {', '.join(absent[-10:])}", "size": "Small", "isSubtle": True, "wrap": True, "spacing": "Small"})

    return _wrap_card(body=body, actions=_actions([
        (f"Who else in {office}?", f"Who was in {office} this week?"),
        ("Trending", "Who's trending up the most?"),
    ]))


def comparison_card(offices):
    """Two offices side by side."""
    columns = []
    for o in offices[:2]:
        facts = [
            {"title": "People in", "value": str(o.get("people_in", 0))},
            {"title": "Typical", "value": str(o.get("typical", 0))},
            {"title": "Peak day", "value": o.get("peak_day", "")},
        ]
        top = o.get("top_people_this_week", [])
        if top:
            facts.append({"title": "#1", "value": top[0].get("name", "")})

        columns.append({
            "type": "Column", "width": "stretch",
            "items": [
                {"type": "TextBlock", "text": o.get("office", ""), "weight": "Bolder", "size": "Medium", "color": "Accent"},
                {"type": "FactSet", "facts": facts},
            ],
        })

    body = [{"type": "ColumnSet", "columns": columns}]
    return _wrap_card(body=body, actions=_actions([
        ("Leaderboard", f"Show me the leaderboard for {offices[0].get('office', '')}"),
        ("Trending", "Who's trending up the most?"),
    ]))


def trending_card(data):
    """People trending up or down."""
    direction = data.get("direction", "trending_up")
    label = "Trending Up" if "up" in direction else "Trending Down"
    icon = "📈" if "up" in direction else "📉"

    body = [
        {"type": "TextBlock", "text": f"{icon} {label}", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "stretch", "items": [{"type": "TextBlock", "text": "Person", "size": "Small", "isSubtle": True}]},
            {"type": "Column", "width": "80px", "items": [{"type": "TextBlock", "text": "Was", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}]},
            {"type": "Column", "width": "80px", "items": [{"type": "TextBlock", "text": "Now", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}]},
        ], "spacing": "Small"},
    ]

    for p in data.get("people", [])[:10]:
        body.append({
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": f"**{p['name']}**", "size": "Small"},
                    {"type": "TextBlock", "text": p.get("office", ""), "size": "Small", "isSubtle": True, "spacing": "None"},
                ]},
                {"type": "Column", "width": "80px", "items": [
                    {"type": "TextBlock", "text": p.get("was", ""), "size": "Small", "horizontalAlignment": "Right"}]},
                {"type": "Column", "width": "80px", "items": [
                    {"type": "TextBlock", "text": p.get("now", ""), "size": "Small", "horizontalAlignment": "Right", "weight": "Bolder", "color": "Good" if "up" in direction else "Attention"}]},
            ],
            "spacing": "None",
        })

    return _wrap_card(body=body, actions=_actions([
        ("Trending down" if "up" in direction else "Trending up",
         "Who's trending down?" if "up" in direction else "Who's trending up?"),
        ("All offices", "Give me the daily briefing"),
    ]))


def visitors_card(data):
    """Cross-office travel flows."""
    body = [
        {"type": "TextBlock", "text": "✈ Cross-Office Travel", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "TextBlock", "text": "Last 4 weeks", "size": "Small", "isSubtle": True, "spacing": "None"},
    ]

    for flow in data.get("flows", [])[:8]:
        body.append({
            "type": "ColumnSet", "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": f"**{flow['from']}** → **{flow['to']}**", "size": "Small"}]},
                {"type": "Column", "width": "auto", "items": [
                    {"type": "TextBlock", "text": f"{flow['people']} people", "size": "Small", "weight": "Bolder"}]},
            ], "spacing": "None",
        })

    trips = data.get("recent_trips", [])[:4]
    if trips:
        body.append({"type": "TextBlock", "text": "Recent trips", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        for t in trips:
            body.append({"type": "TextBlock", "text": f"**{t['name']}** ({t['home_office']}) → {t['visited']}, {t['days']} days", "size": "Small", "spacing": "None"})

    return _wrap_card(body=body, actions=_actions([("All offices", "Give me the daily briefing")]))


def who_was_in_card(data):
    """People in an office on a specific day."""
    body = [
        {"type": "TextBlock", "text": f"{data.get('office', '')} — {data.get('date', '')}", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "TextBlock", "text": f"{data.get('headcount', 0)} people", "size": "Small", "isSubtle": True, "spacing": "None"},
    ]

    for p in data.get("people", [])[:15]:
        body.append({
            "type": "ColumnSet", "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": f"**{p.get('name', '')}**", "size": "Small"}]},
                {"type": "Column", "width": "60px", "items": [
                    {"type": "TextBlock", "text": p.get("stream", ""), "size": "Small", "isSubtle": True}]},
                {"type": "Column", "width": "50px", "items": [
                    {"type": "TextBlock", "text": p.get("arrival", ""), "size": "Small", "horizontalAlignment": "Right"}]},
            ], "spacing": "None",
        })

    return _wrap_card(body=body, actions=_actions([
        (f"Leaderboard", f"Show me the leaderboard for {data.get('office', '')}"),
        (f"About {data.get('office', '')}", f"Tell me about {data.get('office', '')}"),
    ]))


def welcome_card():
    """First-contact welcome card with branding."""
    return _wrap_card(
        body=[
            {"type": "Container", "style": "Accent", "bleed": True, "items": [
                {"type": "TextBlock", "text": "Veeam Presence", "weight": "Bolder", "size": "Large", "color": "Light"},
                {"type": "TextBlock", "text": "Office attendance intelligence", "size": "Small", "color": "Light", "spacing": "None"},
            ], "padding": "Default"},
            {"type": "TextBlock", "text": "I know who's coming into every Veeam office. Ask me about headcounts, leaderboards, trends, travel between offices, or individual patterns.", "wrap": True, "size": "Small", "spacing": "Medium"},
            {"type": "TextBlock", "text": "17 offices · ~3,000 people · refreshed daily", "size": "Small", "isSubtle": True, "spacing": "Small"},
        ],
        actions=[
            {"type": "Action.Submit", "title": "📋 Daily briefing", "data": {"msteams": {"type": "imBack", "value": "Give me the daily briefing"}}},
            {"type": "Action.Submit", "title": "🏆 Leaderboard", "data": {"msteams": {"type": "imBack", "value": "Show me the leaderboard for Prague"}}},
            {"type": "Action.Submit", "title": "✈ Who's traveling?", "data": {"msteams": {"type": "imBack", "value": "Who is traveling between offices?"}}},
            {"type": "Action.Submit", "title": "📈 Trending up", "data": {"msteams": {"type": "imBack", "value": "Who's trending up the most?"}}},
        ],
    )


def error_card(message):
    """Error state."""
    return _wrap_card(
        body=[
            {"type": "TextBlock", "text": "Something went wrong", "weight": "Bolder", "size": "Medium", "color": "Attention"},
            {"type": "TextBlock", "text": message, "wrap": True, "size": "Small"},
        ],
        actions=[{"type": "Action.Submit", "title": "Try again", "data": {"msteams": {"type": "imBack", "value": "Give me the daily briefing"}}}],
    )


# --- Helpers ---

def _wrap_card(body, actions=None):
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def _actions(pairs):
    return [
        {"type": "Action.Submit", "title": label, "data": {"msteams": {"type": "imBack", "value": msg}}}
        for label, msg in pairs[:3]
    ]
