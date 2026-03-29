"""Tier 1 Tool: query_office_intel — serves pre-computed office intelligence."""

import os, sys, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

_cache = {}


def load_cache():
    """Load pre-computed data from pipeline output."""
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
    """Fuzzy match user input to an office name."""
    _ensure_cache()
    offices = list(_cache["baselines"].keys())
    name_lower = name.lower().strip()
    # Exact match
    for o in offices:
        if o.lower() == name_lower:
            return o
    # Partial match
    for o in offices:
        if name_lower in o.lower() or o.lower() in name_lower:
            return o
    return None


def query_office_intel(office=None, metric=None):
    """
    Get intelligence for a specific office or all offices.

    Parameters:
      office: Office name (e.g. "Prague", "Atlanta", "Bucharest"). Optional — omit for global summary.
      metric: Optional filter — "baseline", "personality", "leaderboard", "all" (default: "all")

    Returns dict with office intelligence.
    """
    _ensure_cache()
    metric = metric or "all"

    # Global summary mode
    if not office:
        return _global_summary()

    matched = _match_office(office)
    if not matched:
        available = sorted(_cache["baselines"].keys())
        return {
            "error": f"Office '{office}' not found.",
            "available_offices": available,
            "suggestion": "Try one of the available office names.",
        }

    result = {"office": matched}

    bl = _cache["baselines"].get(matched, {})
    pr = _cache["personality"].get(matched, {})
    an = _cache["anchors"].get(matched, {})

    if metric in ("all", "baseline"):
        # Compact role baselines — only send latest rate + deviation, not full DOW arrays
        compact_roles = {}
        for stream, rb in bl.get("role_baselines", {}).items():
            compact_roles[stream] = {
                "pool": rb.get("pool", 0),
                "latest_rate": rb.get("latest_rate", 0),
                "deviation_pp": rb.get("deviation_pp", 0),
            }
        result["baseline"] = {
            "active_pool": bl.get("active_pool", 0),
            "latest": bl.get("latest", {}),
            "dow_baselines": bl.get("dow_baselines", {}),
            "weekly_trend": bl.get("weekly_trend", [])[-4:],  # Last 4 weeks only
            "role_baselines": compact_roles,
            "seniority_baselines": bl.get("seniority_baselines", {}),
        }

    if metric in ("all", "personality"):
        result["personality"] = pr

    if metric in ("all", "leaderboard"):
        result["leaderboard"] = {
            "top_n": an.get("top_n", 10),
            "size_class": an.get("size_class", "unknown"),
            "max_days_this_week": an.get("max_days_this_week", 5),
            "total_appeared_this_week": an.get("total_appeared_this_week", 0),
            "entries": an.get("leaderboard", [])[:10],  # Card cap at 10
            "erosion_rate": an.get("erosion_rate", 0),
            "erosion_alert": an.get("erosion_alert", False),
        }

    meta = config.OFFICES.get(matched, {})
    result["metadata"] = {
        "region": meta.get("region", "Unknown"),
        "sources": meta.get("sources", []),
        "size_class": meta.get("size_class", "unknown"),
    }

    return result


def _global_summary():
    """Return global pulse across all offices."""
    _ensure_cache()
    baselines = _cache["baselines"]
    personality = _cache["personality"]
    anchors = _cache["anchors"]

    offices = []
    total_pool = 0
    total_latest_hc = 0

    for name, bl in sorted(baselines.items()):
        latest = bl.get("latest", {})
        pool = bl.get("active_pool", 0)
        hc = latest.get("headcount", 0)
        rate = latest.get("rate", 0)
        dev = latest.get("deviation_pp", 0)
        total_pool += pool
        total_latest_hc += hc

        pr = personality.get(name, {})
        an = anchors.get(name, {})

        offices.append({
            "name": name,
            "region": config.OFFICES.get(name, {}).get("region", "Unknown"),
            "pool": pool,
            "headcount": hc,
            "rate": rate,
            "dev_pp": dev,
            "erosion": an.get("erosion_alert", False),
        })

    # Regional aggregation
    regions = {}
    for o in offices:
        r = o["region"]
        if r not in regions:
            regions[r] = {"pool": 0, "headcount": 0, "offices": 0}
        regions[r]["pool"] += o["active_pool"]
        regions[r]["headcount"] += o["latest_headcount"]
        regions[r]["offices"] += 1

    latest_date = baselines.get(list(baselines.keys())[0], {}).get("latest", {}).get("date", "unknown") if baselines else "unknown"

    return {
        "type": "global_summary",
        "data_through": latest_date,
        "total_offices": len(offices),
        "total_active_pool": total_pool,
        "total_latest_headcount": total_latest_hc,
        "global_rate": round(total_latest_hc / total_pool, 4) if total_pool > 0 else 0,
        "regions": {
            name: {
                "offices": r["offices"],
                "pool": r["pool"],
                "headcount": r["headcount"],
                "rate": round(r["headcount"] / r["pool"], 4) if r["pool"] > 0 else 0,
            }
            for name, r in regions.items()
        },
        "offices": offices,
    }


# Tool schema for Claude's tool_use
TOOL_SCHEMA = {
    "name": "query_office_intel",
    "description": "Get office intelligence: attendance baselines, personality profiles, leaderboards, and trends. Call with no office parameter for a global summary across all 17 offices. Call with an office name for deep detail on that office.",
    "input_schema": {
        "type": "object",
        "properties": {
            "office": {
                "type": "string",
                "description": "Office name (e.g. 'Prague', 'Atlanta', 'Bucharest'). Omit for global summary.",
            },
            "metric": {
                "type": "string",
                "enum": ["all", "baseline", "personality", "leaderboard"],
                "description": "Which data to return. Default: 'all'.",
            },
        },
        "required": [],
    },
}
