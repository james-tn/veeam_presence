"""Adaptive Card template definitions for Teams rendering."""


def briefing_card(data):
    """All offices ranked by headcount."""
    items = []
    for office in data.get("offices", []):
        name = office.get("name", "")
        people = office.get("people_in", 0)
        typical = office.get("typical", 0)
        diff = people - typical
        diff_str = f" ({'+' if diff > 0 else ''}{diff})" if diff != 0 else ""
        items.append({
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": name, "weight": "Bolder", "size": "Small"}
                ]},
                {"type": "Column", "width": "auto", "items": [
                    {"type": "TextBlock", "text": f"{people} people{diff_str}", "size": "Small", "horizontalAlignment": "Right"}
                ]},
            ],
            "spacing": "Small",
        })

    return _wrap_card(
        body=[
            {"type": "TextBlock", "text": f"Office Attendance — {data.get('data_through', '')}", "weight": "Bolder", "size": "Medium"},
            {"type": "TextBlock", "text": f"{data.get('total_people_in', 0)} people across {data.get('total_offices', 17)} offices", "size": "Small", "isSubtle": True, "spacing": "None"},
        ] + items,
        actions=_default_actions(["Which offices need attention?", "Show me the leaderboard for Prague", "Who's trending up?"]),
    )


def office_detail_card(data):
    """Single office detail."""
    facts = [
        {"title": "People in", "value": str(data.get("people_in", 0))},
        {"title": "Typical", "value": str(data.get("typical", 0))},
        {"title": "Day", "value": data.get("day", "")},
        {"title": "Date", "value": data.get("data_through", "")},
    ]

    # Top people
    top_items = []
    for p in data.get("top_people_this_week", [])[:5]:
        top_items.append({
            "type": "TextBlock",
            "text": f"**{p.get('name', '')}** ({p.get('role', '')}) — {p.get('days', '')}",
            "size": "Small", "spacing": "None",
        })

    body = [
        {"type": "TextBlock", "text": data.get("office", "Office"), "weight": "Bolder", "size": "Medium"},
        {"type": "FactSet", "facts": facts},
    ]
    if top_items:
        body.append({"type": "TextBlock", "text": "Top people this week", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        body.extend(top_items)

    return _wrap_card(body=body, actions=_default_actions([
        f"Who's trending up in {data.get('office', '')}?",
        f"Who was in {data.get('office', '')} this week?",
        "Compare to another office",
    ]))


def leaderboard_card(data):
    """Top people per office."""
    entries = data.get("entries", data.get("top_people_this_week", []))
    office = data.get("office", "")

    items = []
    for i, entry in enumerate(entries[:10], 1):
        name = entry.get("name", "")
        role = entry.get("role", entry.get("stream", ""))
        days = entry.get("days", "")
        trend = entry.get("trend", "")
        trend_icon = {"up": " ↑", "down": " ↓", "steady": ""}.get(trend, "")

        items.append({
            "type": "TextBlock",
            "text": f"**{i}. {name}** ({role}) — {days}{trend_icon}",
            "size": "Small", "spacing": "None",
        })

    body = [
        {"type": "TextBlock", "text": f"Leaderboard — {office}" if office else "Leaderboard", "weight": "Bolder", "size": "Medium"},
    ] + items

    return _wrap_card(body=body, actions=_default_actions([
        f"Tell me more about {office}" if office else "Show all offices",
        "Who's trending up?",
    ]))


def person_card(data):
    """Individual person pattern."""
    name = data.get("name", "")
    facts = [
        {"title": "Office", "value": data.get("office", "")},
        {"title": "Role", "value": data.get("role", "")},
        {"title": "Days/week", "value": str(data.get("days_per_week", ""))},
        {"title": "Usual arrival", "value": data.get("usual_arrival", "N/A")},
        {"title": "Usual departure", "value": data.get("usual_departure", "N/A")},
        {"title": "Avg stay", "value": f"{data.get('avg_dwell_hours', 0)}h"},
    ]

    # Days pattern
    dow = data.get("days_they_come_in", {})
    if dow:
        dow_str = ", ".join(f"{d}: {n}" for d, n in dow.items())
        facts.append({"title": "Pattern", "value": dow_str})

    body = [
        {"type": "TextBlock", "text": name, "weight": "Bolder", "size": "Medium"},
        {"type": "FactSet", "facts": facts},
    ]

    return _wrap_card(body=body, actions=_default_actions([
        f"Who else is in {data.get('office', '')} regularly?",
        "Who's trending up?",
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
        top = o.get("top_people_this_week", [{}])
        if top:
            facts.append({"title": "#1", "value": top[0].get("name", "")})

        columns.append({
            "type": "Column", "width": "stretch",
            "items": [
                {"type": "TextBlock", "text": o.get("office", ""), "weight": "Bolder", "size": "Medium"},
                {"type": "FactSet", "facts": facts},
            ],
        })

    body = [{"type": "ColumnSet", "columns": columns}]
    return _wrap_card(body=body, actions=_default_actions(["Show leaderboard", "Who's trending up?"]))


def trending_card(data):
    """People trending up or down."""
    direction = data.get("direction", "trending_up")
    label = "Trending Up" if "up" in direction else "Trending Down"

    items = []
    for p in data.get("people", [])[:10]:
        name = p.get("name", "")
        office = p.get("office", "")
        was = p.get("was", "")
        now = p.get("now", "")
        items.append({
            "type": "TextBlock",
            "text": f"**{name}** ({office}) — {was} → {now}",
            "size": "Small", "spacing": "None",
        })

    body = [
        {"type": "TextBlock", "text": label, "weight": "Bolder", "size": "Medium"},
    ] + items

    return _wrap_card(body=body, actions=_default_actions([
        "Who's trending down?" if "up" in direction else "Who's trending up?",
        "Show all office headcounts",
    ]))


def visitors_card(data):
    """Cross-office travel flows."""
    items = []
    for flow in data.get("flows", [])[:8]:
        items.append({
            "type": "TextBlock",
            "text": f"**{flow['from']} → {flow['to']}**: {flow['people']} people, {flow['days']} visit days",
            "size": "Small", "spacing": "None",
        })

    trip_items = []
    for trip in data.get("recent_trips", [])[:5]:
        trip_items.append({
            "type": "TextBlock",
            "text": f"{trip['name']} ({trip['home_office']}) → {trip['visited']}, {trip['days']} days",
            "size": "Small", "spacing": "None",
        })

    body = [
        {"type": "TextBlock", "text": "Cross-Office Travel (last 4 weeks)", "weight": "Bolder", "size": "Medium"},
    ] + items

    if trip_items:
        body.append({"type": "TextBlock", "text": "Recent trips", "weight": "Bolder", "size": "Small", "spacing": "Medium"})
        body.extend(trip_items)

    return _wrap_card(body=body, actions=_default_actions(["Show all office headcounts", "Who's trending up?"]))


def who_was_in_card(data):
    """People who were in an office on a specific day."""
    items = []
    for p in data.get("people", [])[:20]:
        items.append({
            "type": "TextBlock",
            "text": f"**{p.get('name', '')}** ({p.get('stream', '')}) — arrived {p.get('arrival', '')}",
            "size": "Small", "spacing": "None",
        })

    body = [
        {"type": "TextBlock", "text": f"{data.get('office', '')} — {data.get('date', '')}", "weight": "Bolder", "size": "Medium"},
        {"type": "TextBlock", "text": f"{data.get('headcount', 0)} people", "size": "Small", "isSubtle": True, "spacing": "None"},
    ] + items

    return _wrap_card(body=body, actions=_default_actions([
        f"Show leaderboard for {data.get('office', '')}",
        f"Tell me more about {data.get('office', '')}",
    ]))


def welcome_card():
    """First-contact welcome card."""
    return _wrap_card(
        body=[
            {"type": "TextBlock", "text": "Veeam Presence", "weight": "Bolder", "size": "Large"},
            {"type": "TextBlock", "text": "I know who's coming into every Veeam office. Ask me anything about office attendance — headcounts, leaderboards, trends, travel between offices, or individual patterns.", "wrap": True, "size": "Small"},
            {"type": "TextBlock", "text": "17 offices · ~3,000 people · refreshed daily", "size": "Small", "isSubtle": True, "spacing": "Small"},
        ],
        actions=[
            {"type": "Action.Submit", "title": "Daily briefing", "data": {"msteams": {"type": "imBack", "value": "Give me the daily briefing"}}},
            {"type": "Action.Submit", "title": "Who's busiest?", "data": {"msteams": {"type": "imBack", "value": "Which offices are busiest this week?"}}},
            {"type": "Action.Submit", "title": "Leaderboard", "data": {"msteams": {"type": "imBack", "value": "Show me the leaderboard for Prague"}}},
            {"type": "Action.Submit", "title": "Who's traveling?", "data": {"msteams": {"type": "imBack", "value": "Who is traveling between offices?"}}},
        ],
    )


def error_card(message):
    """Error state card."""
    return _wrap_card(
        body=[
            {"type": "TextBlock", "text": "Something went wrong", "weight": "Bolder", "size": "Medium", "color": "Attention"},
            {"type": "TextBlock", "text": message, "wrap": True, "size": "Small"},
        ],
        actions=[{"type": "Action.Submit", "title": "Try again", "data": {"msteams": {"type": "imBack", "value": "Give me the daily briefing"}}}],
    )


# --- Helpers ---

def _wrap_card(body, actions=None):
    """Wrap body elements in a standard Adaptive Card envelope."""
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def _default_actions(labels):
    """Create imBack actions from label strings."""
    return [
        {"type": "Action.Submit", "title": label, "data": {"msteams": {"type": "imBack", "value": label}}}
        for label in labels[:3]
    ]
