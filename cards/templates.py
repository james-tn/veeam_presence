"""Adaptive Card templates — designed for Teams rendering.

Design principles:
- Scannable in 3 seconds: key number visible without scrolling
- Compact: never more than ~15 body elements (Teams truncates long cards)
- Mobile-first: wrap all text, avoid wide ColumnSets
- Color: Good (green) for above normal, Attention (amber) for below
- Every card has: header, content, data freshness note, 2-3 actions
"""


def briefing_card(data):
    """Daily briefing — top offices with context, rest summarized."""
    offices = data.get("offices", [])
    date = data.get("data_through", "")
    total = data.get("total_people_in", sum(o["people_in"] for o in offices))

    body = [
        {"type": "TextBlock", "text": "Veeam Presence", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "TextBlock", "text": f"{total} people across {len(offices)} offices", "size": "Small", "isSubtle": True, "spacing": "None"},
        # Column headers
        {"type": "ColumnSet", "spacing": "Medium", "columns": [
            _col("stretch", "Office", subtle=True),
            _col("60px", "In", subtle=True, align="Right"),
            _col("70px", "Typical", subtle=True, align="Right"),
        ]},
    ]

    # Show top 10 offices, summarize rest
    show = offices[:10]
    rest = offices[10:]

    for o in show:
        diff = o["people_in"] - o["typical"]
        color = "Good" if diff > 3 else ("Attention" if diff < -3 else "Default")
        people_str = str(o["people_in"]) if o["people_in"] != 1 else "1"

        body.append({"type": "ColumnSet", "spacing": "None", "columns": [
            _col("stretch", o["name"], bold=o["people_in"] > 50),
            _col("60px", people_str, align="Right", bold=True),
            _col("70px", str(o["typical"]), align="Right", color=color),
        ]})

    if rest:
        rest_names = ", ".join(o["name"] for o in rest)
        rest_total = sum(o["people_in"] for o in rest)
        body.append({"type": "TextBlock", "text": f"+ {len(rest)} more offices ({rest_total} people): {rest_names}", "size": "Small", "isSubtle": True, "wrap": True, "spacing": "Small"})

    body.append(_freshness(date))

    return _wrap(body, _actions([
        ("Show all offices", "Show me all 17 offices"),
        ("Leaderboard", "Show me the leaderboard for Prague"),
        ("Trending up", "Who's trending up the most?"),
    ]))


def office_detail_card(data):
    """Single office — key number, top people, one notable signal."""
    office = data.get("office", "")
    people = data.get("people_in", 0)
    typical = data.get("typical", 0)
    diff = people - typical
    date = data.get("data_through", "")
    day = data.get("day", "")

    diff_text = f"+{diff} vs typical" if diff > 0 else f"{diff} vs typical" if diff < 0 else "right at typical"
    diff_color = "Good" if diff > 3 else ("Attention" if diff < -3 else "Default")

    body = [
        {"type": "TextBlock", "text": office, "weight": "Bolder", "size": "Large", "color": "Accent"},
        {"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "auto", "items": [
                {"type": "TextBlock", "text": str(people), "size": "ExtraLarge", "weight": "Bolder"},
            ]},
            {"type": "Column", "width": "stretch", "verticalContentAlignment": "Center", "items": [
                {"type": "TextBlock", "text": f"people on {day}", "size": "Small", "isSubtle": True},
                {"type": "TextBlock", "text": diff_text, "size": "Small", "color": diff_color, "spacing": "None"},
            ]},
        ]},
    ]

    # Weekly trend (compact)
    weekly = data.get("weekly_headcounts", [])
    if weekly:
        body.append({"type": "TextBlock", "text": f"Recent weeks: {' → '.join(str(w) for w in weekly)}", "size": "Small", "isSubtle": True, "spacing": "Small"})

    # One notable signal (if any)
    notes = data.get("things_to_note", [])
    if notes:
        body.append({"type": "Container", "style": "Attention", "items": [
            {"type": "TextBlock", "text": notes[0], "size": "Small", "wrap": True},
        ], "spacing": "Small"})

    # Top people (limit to 4)
    top = data.get("top_people_this_week", [])
    if top:
        body.append({"type": "TextBlock", "text": "Top people this week", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        for p in top[:4]:
            body.append({"type": "TextBlock", "text": f"**{p['name']}** ({p.get('role', '')}) — {p['days']}", "size": "Small", "spacing": "None", "wrap": True})

    body.append(_freshness(date))

    return _wrap(body, _actions([
        ("Leaderboard", f"Show me the leaderboard for {office.split()[0]}"),
        ("Who's trending", f"Who's trending up in {office.split()[0]}?"),
        ("Compare", "Compare to another office"),
    ]))


def leaderboard_card(data):
    """Top people at an office."""
    entries = data.get("entries", data.get("top_people_this_week", []))
    office = data.get("office", "")

    body = [
        {"type": "TextBlock", "text": f"Leaderboard — {office}" if office else "Leaderboard", "weight": "Bolder", "size": "Medium", "color": "Accent"},
    ]

    for i, entry in enumerate(entries[:10], 1):
        name = entry.get("name", "")
        role = entry.get("role", entry.get("stream", ""))
        days = entry.get("days", "")
        trend = entry.get("trend", "")
        trend_icon = {"up": " ↑", "down": " ↓"}.get(trend, "")
        color = "Good" if trend == "up" else ("Attention" if trend == "down" else "Default")

        body.append({"type": "ColumnSet", "spacing": "Small" if i == 1 else "None", "columns": [
            _col("24px", f"**{i}**"),
            _col("stretch", f"**{name}**  \n{role}", wrap=True),
            _col("55px", f"{days}{trend_icon}", align="Right", bold=True, color=color),
        ]})

    return _wrap(body, _actions([
        (f"About {office}" if office else "All offices", f"Tell me about {office}" if office else "Give me the daily briefing"),
        ("Trending up", "Who's trending up the most?"),
    ]))


def person_card(data):
    """Individual person."""
    name = data.get("name", "")
    office = data.get("office", "")
    title = data.get("title", "")
    total_in = data.get("total_days_in", "")
    total_wd = data.get("total_workdays", "")

    body = [
        {"type": "TextBlock", "text": name, "weight": "Bolder", "size": "Large", "color": "Accent"},
        {"type": "TextBlock", "text": f"{title} · {office}" if title else office, "size": "Small", "isSubtle": True, "spacing": "None", "wrap": True},
        {"type": "FactSet", "spacing": "Medium", "facts": [
            {"title": "Days/week", "value": str(data.get("days_per_week", ""))},
            {"title": "Arrives", "value": data.get("usual_arrival", "N/A")},
            {"title": "Leaves", "value": data.get("usual_departure", "N/A")},
            {"title": "Avg stay", "value": f"{data.get('avg_dwell_hours', 0)}h"},
            {"title": "YTD", "value": f"{total_in} of {total_wd} workdays" if total_in else ""},
        ]},
    ]

    # Day pattern as FactSet (simple, renders everywhere)
    dow = data.get("days_they_come_in", {})
    if dow:
        body.append({"type": "TextBlock", "text": "Day pattern", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        body.append({"type": "FactSet", "facts": [
            {"title": d, "value": str(n)} for d, n in dow.items()
        ]})

    # Recent absences (compact)
    absent = data.get("days_not_in", [])
    if absent:
        recent = absent[-8:]  # Last 8 only
        body.append({"type": "TextBlock", "text": f"Recent days not in: {', '.join(recent)}", "size": "Small", "isSubtle": True, "wrap": True, "spacing": "Small"})

    return _wrap(body, _actions([
        (f"Who else in {office}?", f"Who was in {office} this week?"),
        ("All offices", "Give me the daily briefing"),
    ]))


def comparison_card(offices):
    """Two offices side by side."""
    columns = []
    for o in offices[:2]:
        diff = o.get("people_in", 0) - o.get("typical", 0)
        diff_text = f"+{diff}" if diff > 0 else str(diff) if diff != 0 else "on target"

        top = o.get("top_people_this_week", [])
        top_name = top[0].get("name", "N/A") if top else "N/A"

        columns.append({"type": "Column", "width": "stretch", "items": [
            {"type": "TextBlock", "text": o.get("office", ""), "weight": "Bolder", "size": "Medium", "color": "Accent"},
            {"type": "TextBlock", "text": f"{o.get('people_in', 0)} people", "size": "ExtraLarge", "weight": "Bolder"},
            {"type": "FactSet", "facts": [
                {"title": "Typical", "value": str(o.get("typical", 0))},
                {"title": "vs typical", "value": diff_text},
                {"title": "Peak day", "value": o.get("peak_day", "")},
                {"title": "Top person", "value": top_name},
            ]},
        ]})

    body = [{"type": "ColumnSet", "columns": columns}]

    return _wrap(body, _actions([
        ("Leaderboard", f"Show me the leaderboard for {offices[0].get('office', '')}"),
        ("Trending", "Who's trending up the most?"),
    ]))


def trending_card(data):
    """People trending up or down."""
    direction = data.get("direction", "trending_up")
    is_up = "up" in direction
    label = "Trending Up" if is_up else "Trending Down"

    body = [
        {"type": "TextBlock", "text": label, "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "ColumnSet", "spacing": "Small", "columns": [
            _col("stretch", "Person", subtle=True),
            _col("70px", "Was", subtle=True, align="Right"),
            _col("70px", "Now", subtle=True, align="Right"),
        ]},
    ]

    for p in data.get("people", [])[:8]:
        body.append({"type": "ColumnSet", "spacing": "None", "columns": [
            _col("stretch", f"**{p['name']}**  \n{p.get('office', '')}", wrap=True),
            _col("70px", p.get("was", ""), align="Right"),
            _col("70px", p.get("now", ""), align="Right", bold=True, color="Good" if is_up else "Attention"),
        ]})

    return _wrap(body, _actions([
        ("Trending down" if is_up else "Trending up", "Who's trending down?" if is_up else "Who's trending up?"),
        ("All offices", "Give me the daily briefing"),
    ]))


def visitors_card(data):
    """Cross-office travel."""
    body = [
        {"type": "TextBlock", "text": "Cross-Office Travel", "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "TextBlock", "text": "Last 4 weeks", "size": "Small", "isSubtle": True, "spacing": "None"},
        {"type": "ColumnSet", "spacing": "Small", "columns": [
            _col("stretch", "Route", subtle=True),
            _col("60px", "People", subtle=True, align="Right"),
        ]},
    ]

    for flow in data.get("flows", [])[:6]:
        body.append({"type": "ColumnSet", "spacing": "None", "columns": [
            _col("stretch", f"{flow['from']} → {flow['to']}"),
            _col("60px", f"{flow['people']}", align="Right", bold=True),
        ]})

    trips = data.get("recent_trips", [])[:3]
    if trips:
        body.append({"type": "TextBlock", "text": "Recent trips", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        for t in trips:
            body.append({"type": "TextBlock", "text": f"**{t['name']}** ({t['home_office']}) visited {t['visited']} for {t['days']} days", "size": "Small", "spacing": "None", "wrap": True})

    return _wrap(body, _actions([("All offices", "Give me the daily briefing")]))


def who_was_in_card(data):
    """People in an office on a specific day."""
    body = [
        {"type": "TextBlock", "text": data.get("office", ""), "weight": "Bolder", "size": "Medium", "color": "Accent"},
        {"type": "TextBlock", "text": f"{data.get('headcount', 0)} people on {data.get('date', '')}", "size": "Small", "isSubtle": True, "spacing": "None"},
        {"type": "ColumnSet", "spacing": "Small", "columns": [
            _col("stretch", "Name", subtle=True),
            _col("60px", "Role", subtle=True),
            _col("50px", "In at", subtle=True, align="Right"),
        ]},
    ]

    for p in data.get("people", [])[:12]:
        body.append({"type": "ColumnSet", "spacing": "None", "columns": [
            _col("stretch", f"**{p.get('name', '')}**"),
            _col("60px", p.get("stream", ""), subtle=True),
            _col("50px", p.get("arrival", ""), align="Right"),
        ]})

    return _wrap(body, _actions([
        ("Leaderboard", f"Show me the leaderboard for {data.get('office', '')}"),
        ("About this office", f"Tell me about {data.get('office', '')}"),
    ]))


def welcome_card():
    """First-contact welcome card."""
    return _wrap(
        body=[
            {"type": "Container", "style": "Accent", "bleed": True, "items": [
                {"type": "TextBlock", "text": "Veeam Presence", "weight": "Bolder", "size": "Large", "color": "Light"},
                {"type": "TextBlock", "text": "Office attendance intelligence for leadership", "size": "Small", "color": "Light", "spacing": "None", "wrap": True},
            ]},
            {"type": "TextBlock", "text": "I know who's coming into every Veeam office. Ask me about headcounts, leaderboards, trends, travel between offices, or individual patterns.", "wrap": True, "size": "Small", "spacing": "Medium"},
            {"type": "FactSet", "facts": [
                {"title": "Offices", "value": "17 worldwide"},
                {"title": "People tracked", "value": "~3,000"},
                {"title": "Data refresh", "value": "Daily"},
            ]},
        ],
        actions=[
            {"type": "Action.Submit", "title": "Daily briefing", "data": {"msteams": {"type": "imBack", "value": "Give me the daily briefing"}}},
            {"type": "Action.Submit", "title": "Leaderboard", "data": {"msteams": {"type": "imBack", "value": "Show me the leaderboard for Prague"}}},
            {"type": "Action.Submit", "title": "Who's traveling?", "data": {"msteams": {"type": "imBack", "value": "Who is traveling between offices?"}}},
            {"type": "Action.Submit", "title": "Trending up", "data": {"msteams": {"type": "imBack", "value": "Who's trending up the most?"}}},
        ],
    )


def error_card(message):
    """Error state."""
    return _wrap(
        body=[
            {"type": "Container", "style": "Attention", "items": [
                {"type": "TextBlock", "text": "Something went wrong", "weight": "Bolder", "size": "Medium", "wrap": True},
                {"type": "TextBlock", "text": message, "wrap": True, "size": "Small"},
            ]},
        ],
        actions=[{"type": "Action.Submit", "title": "Try again", "data": {"msteams": {"type": "imBack", "value": "Give me the daily briefing"}}}],
    )


# ─── Helpers ───

def _wrap(body, actions=None):
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.5", "body": body}
    if actions:
        card["actions"] = actions
    return card


def _actions(pairs):
    return [{"type": "Action.Submit", "title": label, "data": {"msteams": {"type": "imBack", "value": msg}}} for label, msg in pairs[:3]]


def _col(width, text, bold=False, subtle=False, align=None, color=None, wrap=False):
    """Build a single-text Column for a ColumnSet row."""
    tb = {"type": "TextBlock", "text": text, "size": "Small"}
    if bold:
        tb["weight"] = "Bolder"
    if subtle:
        tb["isSubtle"] = True
    if align:
        tb["horizontalAlignment"] = align
    if color:
        tb["color"] = color
    if wrap:
        tb["wrap"] = True
    return {"type": "Column", "width": width, "items": [tb]}


def _freshness(date):
    """Subtle data-through footer."""
    return {"type": "TextBlock", "text": f"Data through {date}", "size": "Small", "isSubtle": True, "spacing": "Medium"}
