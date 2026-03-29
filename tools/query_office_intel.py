"""Tier 1 Tool: query_office_intel — serves pre-computed office data as plain headcounts."""

import os, sys, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

_cache = {}

DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


def load_cache():
    global _cache
    data_dir = config.DATA_DIR
    with open(os.path.join(data_dir, "baselines.pkl"), "rb") as f:
        _cache["baselines"] = pickle.load(f)
    with open(os.path.join(data_dir, "personality.pkl"), "rb") as f:
        _cache["personality"] = pickle.load(f)
    with open(os.path.join(data_dir, "anchors.pkl"), "rb") as f:
        _cache["anchors"] = pickle.load(f)


def _ensure_cache():
    if not _cache:
        load_cache()


def _match_office(name):
    _ensure_cache()
    offices = list(_cache["baselines"].keys())
    name_lower = name.lower().strip()
    for o in offices:
        if o.lower() == name_lower:
            return o
    for o in offices:
        if name_lower in o.lower() or o.lower() in name_lower:
            return o
    return None


def query_office_intel(office=None, metric=None):
    """
    Get office attendance data. Headcounts and names only — no rates or analytics.
    Call with no office for all-office summary. Call with office name for that office.
    """
    _ensure_cache()
    metric = metric or "all"

    if not office:
        return _global_summary()

    matched = _match_office(office)
    if not matched:
        return {
            "error": f"Office '{office}' not found.",
            "available_offices": sorted(_cache["baselines"].keys()),
        }

    bl = _cache["baselines"].get(matched, {})
    pr = _cache["personality"].get(matched, {})
    an = _cache["anchors"].get(matched, {})

    latest = bl.get("latest", {})
    pool = bl.get("active_pool", 0)
    latest_hc = latest.get("headcount", 0)
    latest_dow = latest.get("dow", 0)
    latest_day = DOW_NAMES.get(latest_dow, "")

    # Typical headcount for this DOW
    dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
    typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0

    # Typical by day (as headcounts)
    typical_by_day = {}
    for dow, d in bl.get("dow_baselines", {}).items():
        typical_by_day[DOW_NAMES.get(int(dow), str(dow))] = round(pool * d.get("rate", 0))

    # Role breakdown (headcounts only)
    roles = {}
    for stream, rb in bl.get("role_baselines", {}).items():
        roles[stream] = rb.get("latest_headcount", 0)

    # Weekly trend (headcounts only)
    weekly = [{"week": w["week"], "people": w["headcount"]}
              for w in bl.get("weekly_trend", [])[-4:]]

    # Leaderboard (names, days, trend — no analytical fields)
    lb_entries = []
    for entry in an.get("leaderboard", [])[:10]:
        lb_entries.append({
            "name": entry.get("name", ""),
            "role": entry.get("stream", ""),
            "days": entry.get("days", ""),
            "trend": entry.get("trend", ""),
        })

    result = {
        "office": matched,
        "region": config.OFFICES.get(matched, {}).get("region", "Unknown"),
        "people_in": latest_hc,
        "typical_for_this_day": typical,
        "date": latest.get("date", "unknown"),
        "day": latest_day,
        "difference": latest_hc - typical,
        "regulars": pool,
        "typical_by_day": typical_by_day,
        "by_role": roles,
        "weekly_trend": weekly,
        "peak_day": pr.get("peak_day", "unknown"),
        "busiest_day_headcount": max(typical_by_day.values()) if typical_by_day else 0,
        "quietest_day_headcount": min(typical_by_day.values()) if typical_by_day else 0,
        "top_people": lb_entries,
        "people_appeared_this_week": an.get("total_appeared_this_week", 0),
    }

    return result


def _global_summary():
    _ensure_cache()
    baselines = _cache["baselines"]
    anchors = _cache["anchors"]

    offices = []
    for name, bl in sorted(baselines.items()):
        latest = bl.get("latest", {})
        pool = bl.get("active_pool", 0)
        hc = latest.get("headcount", 0)
        latest_dow = latest.get("dow", 0)
        dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
        typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0

        offices.append({
            "name": name,
            "region": config.OFFICES.get(name, {}).get("region", "Unknown"),
            "people_in": hc,
            "typical": typical,
            "difference": hc - typical,
        })

    # Sort busiest first
    offices.sort(key=lambda x: x["people_in"], reverse=True)

    # Find the data-through date
    latest_date = "unknown"
    for bl in baselines.values():
        d = bl.get("latest", {}).get("date")
        if d:
            latest_date = d
            break

    return {
        "type": "global_summary",
        "data_through": latest_date,
        "total_offices": len(offices),
        "total_people_in": sum(o["people_in"] for o in offices),
        "offices": offices,
    }


TOOL_SCHEMA = {
    "name": "query_office_intel",
    "description": "Get office attendance data. Call with no office parameter for a summary of all offices. Call with an office name for that office's details including top people. ONE call is usually enough.",
    "input_schema": {
        "type": "object",
        "properties": {
            "office": {
                "type": "string",
                "description": "Office name (e.g. 'Prague', 'Atlanta'). Omit for all-office summary.",
            },
        },
        "required": [],
    },
}
