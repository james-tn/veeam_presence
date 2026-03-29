"""Tier 1 Tool: query_office_intel — headcounts and names only."""

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


def query_office_intel(office=None):
    """Get office attendance. No office = all offices. With office = that office's detail."""
    _ensure_cache()

    if not office:
        return _global_summary()

    matched = _match_office(office)
    if not matched:
        return {
            "error": f"Office '{office}' not found.",
            "available_offices": sorted(_cache["baselines"].keys()),
        }

    bl = _cache["baselines"].get(matched, {})
    an = _cache["anchors"].get(matched, {})

    latest = bl.get("latest", {})
    pool = bl.get("active_pool", 0)
    latest_hc = latest.get("headcount", 0)
    latest_dow = latest.get("dow", 0)
    dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
    typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0

    # Weekly trend — just people counts
    weekly = [w["headcount"] for w in bl.get("weekly_trend", [])[-4:]]

    # Top people — names and days only
    top = []
    for entry in an.get("leaderboard", [])[:10]:
        top.append({
            "name": entry.get("name", ""),
            "role": entry.get("stream", ""),
            "days": entry.get("days", ""),
        })

    return {
        "office": matched,
        "region": config.OFFICES.get(matched, {}).get("region", "Unknown"),
        "data_through": latest.get("date", "unknown"),
        "day": DOW_NAMES.get(latest_dow, ""),
        "people_in": latest_hc,
        "typical": typical,
        "weekly_headcounts": weekly,
        "top_people_this_week": top,
    }


def _global_summary():
    _ensure_cache()
    baselines = _cache["baselines"]

    offices = []
    for name, bl in baselines.items():
        latest = bl.get("latest", {})
        hc = latest.get("headcount", 0)
        pool = bl.get("active_pool", 0)
        latest_dow = latest.get("dow", 0)
        dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
        typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0

        offices.append({
            "name": name,
            "people_in": hc,
            "typical": typical,
        })

    offices.sort(key=lambda x: x["people_in"], reverse=True)

    latest_date = "unknown"
    for bl in baselines.values():
        d = bl.get("latest", {}).get("date")
        if d:
            latest_date = d
            break

    return {
        "data_through": latest_date,
        "offices": offices,
    }


TOOL_SCHEMA = {
    "name": "query_office_intel",
    "description": "Get office headcounts. No office = all offices sorted by size. With office name = that office plus top people.",
    "input_schema": {
        "type": "object",
        "properties": {
            "office": {
                "type": "string",
                "description": "Office name. Omit for all offices.",
            },
        },
        "required": [],
    },
}
