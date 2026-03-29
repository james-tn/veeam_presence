"""Tier 2 Tool: query_person — individual attendance patterns and office queries."""

import os, sys, pickle
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

_enriched = None


def _load_enriched():
    global _enriched
    if _enriched is None:
        _enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    return _enriched


def _match_person(query):
    """Find a person by name or email. Returns list of matches."""
    df = _load_enriched()
    q = query.lower().strip()

    # Try email match first
    email_match = df[df["email"].str.lower() == q]
    if len(email_match) > 0:
        return email_match["email"].iloc[0], True

    # Try name match (preferred_name)
    name_matches = df[df["preferred_name"].fillna("").str.lower().str.contains(q, regex=False)]
    if len(name_matches) > 0:
        # Return best match (most person-days = most data)
        top = name_matches.groupby("email")["date"].count().idxmax()
        return top, True

    return None, False


def query_person(person=None, office=None, query_type=None):
    """
    Get attendance data for a person, or list who was in an office.

    Parameters:
      person: Name or email of a person (e.g. "Scott Jackson", "scott.jackson@veeam.com")
      office: Office name — used with query_type="who_was_in" to list attendees
      query_type: "pattern" (default for person), "who_was_in" (for office), "trending_up", "trending_down"

    Returns attendance pattern, office comparison, or attendee list.
    """
    df = _load_enriched()
    query_type = query_type or ("who_was_in" if office and not person else "pattern")

    # --- Who was in an office ---
    if query_type == "who_was_in" and office:
        return _who_was_in(df, office)

    # --- Trending up/down across all offices ---
    if query_type in ("trending_up", "trending_down"):
        return _trending(df, direction=query_type)

    # --- Cross-office travel ---
    if query_type == "visitors":
        return _visitors()

    # --- Team sync ---
    if query_type == "team_sync":
        return _team_sync(office)

    # --- Ghost / which offices are quiet ---
    if query_type == "ghost":
        return _ghost_offices()

    # --- v1.5: Org leader rollups ---
    if query_type == "org_leader":
        return _org_leaders(person)

    # --- v1.5: Manager gravity ---
    if query_type == "manager_gravity":
        return _manager_gravity(office)

    # --- v1.5: New hire integration ---
    if query_type == "new_hires":
        return _new_hires(office)

    # --- v1.5: Weekend attendance ---
    if query_type == "weekend":
        return _weekend(office)

    # --- Person pattern ---
    if not person:
        return {"error": "Provide a person name/email or use query_type='who_was_in' with an office."}

    email, found = _match_person(person)
    if not found:
        return {"error": f"No match found for '{person}'. Try a full name or email address."}

    return _person_pattern(df, email)


def _person_pattern(df, email):
    """Detailed attendance pattern for one person."""
    pdf = df[df["email"] == email].copy()
    if len(pdf) == 0:
        return {"error": f"No attendance data for {email}"}

    # Basic info — safe extraction with fallbacks
    first = pdf.iloc[0]
    name = first["preferred_name"] if pd.notna(first.get("preferred_name")) else email
    office = pdf["office"].mode().iloc[0] if len(pdf["office"].mode()) > 0 else "Unknown"
    stream = first.get("stream", "Unknown") if pd.notna(first.get("stream")) else "Unknown"
    title = first.get("businesstitle", "") if pd.notna(first.get("businesstitle")) else ""
    seniority = first.get("seniority_band", "") if pd.notna(first.get("seniority_band")) else ""
    matched = bool(first.get("workday_matched", False))

    # Weekday attendance
    weekdays = pdf[pdf["dow"] <= 4]
    total_weekdays = weekdays["date"].nunique()

    # Weekly pattern
    weeks = weekdays.groupby(pd.Grouper(key="date", freq="W-MON")).agg(
        days=("date", "nunique"),
    ).reset_index()
    weeks = weeks[weeks["days"] > 0]

    avg_days_per_week = weeks["days"].mean() if len(weeks) > 0 else 0

    # Recent vs prior (last 2 weeks vs weeks 3-4)
    max_date = pdf["date"].max()
    recent = weekdays[weekdays["date"] >= max_date - pd.Timedelta(weeks=2)]
    prior = weekdays[(weekdays["date"] >= max_date - pd.Timedelta(weeks=4)) &
                     (weekdays["date"] < max_date - pd.Timedelta(weeks=2))]
    recent_avg = recent.groupby(pd.Grouper(key="date", freq="W-MON"))["date"].nunique().mean() if len(recent) > 0 else 0
    prior_avg = prior.groupby(pd.Grouper(key="date", freq="W-MON"))["date"].nunique().mean() if len(prior) > 0 else 0

    if recent_avg > prior_avg + 0.5:
        trend = "increasing"
    elif recent_avg < prior_avg - 0.5:
        trend = "decreasing"
    else:
        trend = "stable"

    # Day-of-week distribution
    dow_counts = weekdays.groupby("dow")["date"].nunique()
    dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    dow_pattern = {dow_names.get(k, str(k)): int(v) for k, v in dow_counts.items()}

    # Dwell and arrival/departure times
    valid_dwell = weekdays[weekdays["dwell_hours"] > 0]
    avg_dwell = round(valid_dwell["dwell_hours"].mean(), 1) if len(valid_dwell) > 0 else 0
    avg_arrival = round(valid_dwell["arrival_hour"].mean(), 1) if len(valid_dwell) > 0 and "arrival_hour" in valid_dwell.columns else 0
    avg_departure = round(valid_dwell["departure_hour"].mean(), 1) if len(valid_dwell) > 0 and "departure_hour" in valid_dwell.columns else 0

    # Compute specific dates present and absent (excluding holidays)
    from pipeline.holidays_cal import get_workdays, get_holiday_name
    start = weekdays["date"].min()
    end = weekdays["date"].max()
    workdays_list = get_workdays(office, start, end)
    dates_present = set(weekdays["date"].dt.date)
    dates_absent_raw = [d.date() for d in workdays_list if d.date() not in dates_present]
    # Separate holidays from actual absences
    holidays_missed = [(str(d), get_holiday_name(office, d)) for d in dates_absent_raw if get_holiday_name(office, d)]
    dates_absent = sorted([d for d in dates_absent_raw if not get_holiday_name(office, d)])

    return {
        "name": name,
        "office": office,
        "role": stream,
        "title": title,
        "days_per_week": round(avg_days_per_week, 1),
        "usual_arrival": _hour_to_time(avg_arrival),
        "usual_departure": _hour_to_time(avg_departure),
        "avg_dwell_hours": avg_dwell,
        "days_they_come_in": dow_pattern,
        "last_4_weeks": [int(r["days"]) for _, r in weeks.tail(4).iterrows()],
        "total_days_in": len(dates_present),
        "total_workdays": len(workdays_list),
        "holidays_excluded": len(holidays_missed),
        "days_not_in": [str(d) for d in dates_absent],
    }


def _hour_to_time(h):
    """Convert decimal hour to readable time string."""
    if not h or h == 0:
        return "N/A"
    hours = int(h)
    minutes = int((h - hours) * 60)
    am_pm = "am" if hours < 12 else "pm"
    display_hour = hours if hours <= 12 else hours - 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minutes:02d}{am_pm}"


def _who_was_in(df, office):
    """List people who were in an office on the most recent day with data."""
    from tools.query_office_intel import _match_office
    matched_office = _match_office(office)
    if not matched_office:
        return {"error": f"Office '{office}' not found."}

    odf = df[df["office"] == matched_office].copy()
    latest_date = odf["date"].max()
    latest_data = odf[odf["date"] == latest_date]

    people = latest_data.groupby("email").agg(
        name=("preferred_name", "first"),
        stream=("stream", "first"),
        arrival_hour=("arrival_hour", "first"),
        dwell_hours=("dwell_hours", "first"),
    ).reset_index().sort_values("arrival_hour")

    return {
        "office": matched_office,
        "date": str(latest_date.date()),
        "headcount": len(people),
        "people": [
            {
                "name": r["name"] if pd.notna(r["name"]) else r["email"],
                "stream": r["stream"] if pd.notna(r["stream"]) else "Unknown",
                "arrival": f"{int(r['arrival_hour'])}:{int((r['arrival_hour'] % 1) * 60):02d}" if pd.notna(r["arrival_hour"]) else "N/A",
            }
            for _, r in people.iterrows()
        ],
    }


def _trending(df, direction="trending_up"):
    """Find people with biggest attendance changes (up or down)."""
    weekdays = df[df["dow"] <= 4].copy()
    max_date = weekdays["date"].max()

    recent = weekdays[weekdays["date"] >= max_date - pd.Timedelta(weeks=2)]
    prior = weekdays[(weekdays["date"] >= max_date - pd.Timedelta(weeks=6)) &
                     (weekdays["date"] < max_date - pd.Timedelta(weeks=2))]

    recent_stats = recent.groupby("email").agg(
        recent_days=("date", "nunique"),
        name=("preferred_name", "first"),
        office=("office", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else x.iloc[0]),
        stream=("stream", "first"),
    ).reset_index()

    prior_stats = prior.groupby("email").agg(
        prior_days=("date", "nunique"),
    ).reset_index()

    merged = recent_stats.merge(prior_stats, on="email", how="outer").fillna(0)
    # Normalize to per-week (recent = 2 weeks, prior = 4 weeks)
    merged["recent_per_week"] = merged["recent_days"] / 2
    merged["prior_per_week"] = merged["prior_days"] / 4
    merged["delta"] = merged["recent_per_week"] - merged["prior_per_week"]

    if direction == "trending_up":
        top = merged.nlargest(15, "delta")
    else:
        top = merged.nsmallest(15, "delta")

    return {
        "direction": direction,
        "people": [
            {
                "name": r["name"] if pd.notna(r["name"]) else r["email"],
                "office": r["office"] if pd.notna(r["office"]) else "Unknown",
                "was": f"{round(r['prior_per_week'], 1)} days/week",
                "now": f"{round(r['recent_per_week'], 1)} days/week",
            }
            for _, r in top.iterrows()
            if abs(r["delta"]) > 0.3
        ],
    }


def _visitors():
    """Cross-office travel — who's visiting other offices."""
    visitors_path = os.path.join(config.DATA_DIR, "visitors.pkl")
    if not os.path.exists(visitors_path):
        return {"error": "Visitor data not available. Run the pipeline first."}
    with open(visitors_path, "rb") as f:
        data = pickle.load(f)
    return data


def _team_sync(office=None):
    """Team synchronization — are teams coming in on the same days?"""
    ts_path = os.path.join(config.DATA_DIR, "team_sync.pkl")
    if not os.path.exists(ts_path):
        return {"error": "Team sync data not available. Run the pipeline first."}
    with open(ts_path, "rb") as f:
        data = pickle.load(f)

    # Filter to office if specified
    if office:
        from tools.query_office_intel import _match_office
        matched = _match_office(office)
        if matched:
            data = {k: v for k, v in data.items() if v.get("office") == matched}

    # Sort: low sync first (these are the interesting ones)
    teams = sorted(data.values(), key=lambda x: x.get("sync_score", 0))

    # Plain language output
    same_days = [t for t in teams if t["sync_score"] >= 0.4]
    mixed = [t for t in teams if 0.2 <= t["sync_score"] < 0.4]
    different_days = [t for t in teams if t["sync_score"] < 0.2]

    result = {
        "total_teams": len(teams),
        "teams_on_same_days": len(same_days),
        "teams_mixed": len(mixed),
        "teams_on_different_days": len(different_days),
    }

    # Show the worst teams (most interesting)
    if different_days:
        result["teams_rarely_overlapping"] = [
            {"team": t["team"], "office": t["office"], "manager": t["manager"],
             "members": t["members"]}
            for t in different_days[:10]
        ]

    # Show the best teams
    if same_days:
        result["teams_well_coordinated"] = [
            {"team": t["team"], "office": t["office"], "manager": t["manager"],
             "members": t["members"]}
            for t in reversed(same_days[-5:])
        ]

    return result


def _org_leaders(search=None):
    """Org leader attendance rollups."""
    path = os.path.join(config.DATA_DIR, "seniority.pkl")
    if not os.path.exists(path):
        return {"error": "Org leader data not available. Run the pipeline first."}
    with open(path, "rb") as f:
        data = pickle.load(f)

    leaders = data.get("org_leaders", {})
    if search:
        # Filter to matching leader
        search_lower = search.lower()
        leaders = {k: v for k, v in leaders.items() if search_lower in k.lower()}

    # Sort by people count
    sorted_leaders = sorted(leaders.values(), key=lambda x: x.get("people", 0), reverse=True)

    return {
        "total_leaders": len(sorted_leaders),
        "leaders": [
            {"leader": l["leader"], "level": l["level"], "people": l["people"],
             "offices": l["offices"], "avg_days_per_week": l["avg_days_per_week"],
             "top_offices": l["top_offices"]}
            for l in sorted_leaders[:15]
        ],
    }


def _manager_gravity(office=None):
    """Which managers pull their teams into the office?"""
    path = os.path.join(config.DATA_DIR, "manager_gravity.pkl")
    if not os.path.exists(path):
        return {"error": "Manager gravity data not available. Run the pipeline first."}
    with open(path, "rb") as f:
        data = pickle.load(f)

    if office:
        from tools.query_office_intel import _match_office
        matched = _match_office(office)
        if matched:
            data = {k: v for k, v in data.items() if v.get("office") == matched}

    managers = sorted(data.values(), key=lambda x: x.get("gravity_score", 0), reverse=True)

    strong_pull = [m for m in managers if m["gravity_score"] > 0.15]
    no_effect = [m for m in managers if -0.1 <= m["gravity_score"] <= 0.1]

    return {
        "total_managers": len(managers),
        "managers_with_strong_pull": len(strong_pull),
        "managers_with_no_effect": len(no_effect),
        "top_gravity": [
            {"manager": m["manager"], "office": m["office"], "team_size": m["team_size"],
             "team_in_when_mgr_in": f"{m['team_attendance_when_mgr_in']}%",
             "team_in_when_mgr_out": f"{m['team_attendance_when_mgr_out']}%"}
            for m in managers[:10]
        ],
    }


def _new_hires(office=None):
    """Are new hires establishing office rhythm?"""
    path = os.path.join(config.DATA_DIR, "new_hires.pkl")
    if not os.path.exists(path):
        return {"error": "New hire data not available. Run the pipeline first."}
    with open(path, "rb") as f:
        data = pickle.load(f)

    people = data.get("people", [])
    if office:
        from tools.query_office_intel import _match_office
        matched = _match_office(office)
        if matched:
            people = [p for p in people if p.get("office") == matched]

    return {
        "total_new_hires": len(people),
        "ramping_up": len([p for p in people if p["trend"] == "ramping up"]),
        "steady": len([p for p in people if p["trend"] == "steady"]),
        "fading": len([p for p in people if p["trend"] == "fading"]),
        "people": [
            {"name": p["name"], "office": p["office"], "role": p["role"],
             "hired": p["hire_date"], "days_per_week": p["avg_days_per_week"],
             "trend": p["trend"]}
            for p in people[:15]
        ],
    }


def _weekend(office=None):
    """Weekend attendance — who's coming in on weekends?"""
    path = os.path.join(config.DATA_DIR, "weekend.pkl")
    if not os.path.exists(path):
        return {"error": "Weekend data not available. Run the pipeline first."}
    with open(path, "rb") as f:
        data = pickle.load(f)

    offices = data.get("offices", {})
    if office:
        from tools.query_office_intel import _match_office
        matched = _match_office(office)
        if matched and matched in offices:
            return {"office": matched, **offices[matched]}
        return {"error": f"No weekend data for {office}"}

    return {
        "total_weekend_people": data.get("total_weekend_people", 0),
        "offices": [
            {"office": name, "people": o["weekend_people"], "avg_per_day": o["avg_per_weekend_day"]}
            for name, o in sorted(offices.items(), key=lambda x: x[1]["weekend_people"], reverse=True)
            if o["weekend_people"] > 0
        ],
    }


def _ghost_offices():
    """Which offices have multiple declining signals?"""
    sig_path = os.path.join(config.DATA_DIR, "signals.pkl")
    if not os.path.exists(sig_path):
        return {"error": "Signals data not available. Run the pipeline first."}
    with open(sig_path, "rb") as f:
        data = pickle.load(f)

    offices = []
    for name, sig in sorted(data.items(), key=lambda x: x[1].get("signals_active", 0), reverse=True):
        if sig.get("signals"):
            offices.append({
                "office": name,
                "things_happening": sig["signals"],
            })

    return {"offices_with_changes": offices}


TOOL_SCHEMA = {
    "name": "query_person",
    "description": "Get data about people and teams. Query types: pattern (person lookup), who_was_in (office attendees), trending_up/trending_down, visitors (cross-office travel), team_sync, ghost (declining offices), org_leader (org hierarchy rollups), manager_gravity (does manager presence pull team in?), new_hires (are new hires integrating?), weekend (weekend attendance).",
    "input_schema": {
        "type": "object",
        "properties": {
            "person": {
                "type": "string",
                "description": "Person's name or email (e.g. 'Scott Jackson', 'scott.jackson@veeam.com')",
            },
            "office": {
                "type": "string",
                "description": "Office name — used with query_type='who_was_in'",
            },
            "query_type": {
                "type": "string",
                "enum": ["pattern", "who_was_in", "trending_up", "trending_down", "visitors", "team_sync", "ghost", "org_leader", "manager_gravity", "new_hires", "weekend"],
                "description": "Type of query. Default: 'pattern' for person queries, 'who_was_in' for office queries.",
            },
        },
        "required": [],
    },
}
