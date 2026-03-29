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

    # Dwell
    valid_dwell = weekdays[weekdays["dwell_hours"] > 0]["dwell_hours"]
    avg_dwell = round(valid_dwell.mean(), 1) if len(valid_dwell) > 0 else 0

    # Office baseline comparison — use cached baselines from query_office_intel
    from tools.query_office_intel import _ensure_cache, _cache
    _ensure_cache()
    office_bl = _cache.get("baselines", {}).get(office, {})
    office_pool = office_bl.get("active_pool", 0)

    # Compare to office average
    # Sum of DOW rates = expected days/week for a random person in the pool
    office_dow_baselines = office_bl.get("dow_baselines", {})
    office_avg_days = sum(b.get("rate", 0) for b in office_dow_baselines.values()) if office_dow_baselines else 0

    return {
        "person": {
            "name": name,
            "email": email,
            "office": office,
            "stream": stream,
            "title": title,
            "seniority": seniority,
            "workday_matched": matched,
        },
        "attendance": {
            "total_weekdays_present": total_weekdays,
            "avg_days_per_week": round(avg_days_per_week, 1),
            "trend": trend,
            "recent_avg": round(recent_avg, 1),
            "prior_avg": round(prior_avg, 1),
            "avg_dwell_hours": avg_dwell,
            "dow_pattern": dow_pattern,
        },
        "office_comparison": {
            "office": office,
            "office_pool": office_pool,
            "office_avg_days_per_week": round(office_avg_days, 1),
            "vs_office": f"{'+' if avg_days_per_week > office_avg_days else ''}{avg_days_per_week - office_avg_days:.1f} days/week vs office avg",
        },
        "weekly_history": [
            {"week": str(r["date"].date()), "days": int(r["days"])}
            for _, r in weeks.tail(8).iterrows()
        ],
    }


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
        "period": f"Last 2 weeks vs prior 4 weeks",
        "people": [
            {
                "name": r["name"] if pd.notna(r["name"]) else r["email"],
                "office": r["office"] if pd.notna(r["office"]) else "Unknown",
                "stream": r["stream"] if pd.notna(r["stream"]) else "Unknown",
                "recent_days_per_week": round(r["recent_per_week"], 1),
                "prior_days_per_week": round(r["prior_per_week"], 1),
                "delta": round(r["delta"], 1),
            }
            for _, r in top.iterrows()
            if abs(r["delta"]) > 0.3  # Only show meaningful changes
        ],
    }


TOOL_SCHEMA = {
    "name": "query_person",
    "description": "Get attendance data for an individual person, list who was in an office on the most recent day, or find people whose attendance is trending up or down. Use for person-level questions, 'who was in' questions, and trending queries.",
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
                "enum": ["pattern", "who_was_in", "trending_up", "trending_down"],
                "description": "Type of query. Default: 'pattern' for person queries, 'who_was_in' for office queries.",
            },
        },
        "required": [],
    },
}
