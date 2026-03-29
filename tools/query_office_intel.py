"""Tier 1 Tool: query_office_intel — headcounts, names, and office health."""

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
    # Phase 2 + v1.5 data
    for name in ("team_sync", "signals", "chi", "seniority", "manager_gravity",
                  "new_hires", "weekend", "mixing"):
        path = os.path.join(data_dir, f"{name}.pkl")
        if os.path.exists(path):
            with open(path, "rb") as f:
                _cache[name] = pickle.load(f)


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

    # Typical by day
    typical_by_day = {}
    for dow, d in bl.get("dow_baselines", {}).items():
        typical_by_day[DOW_NAMES.get(int(dow), str(dow))] = round(pool * d.get("rate", 0))

    # Top people — names and days only
    top = []
    for entry in an.get("leaderboard", [])[:10]:
        top.append({
            "name": entry.get("name", ""),
            "role": entry.get("stream", ""),
            "days": entry.get("days", ""),
        })

    result = {
        "office": matched,
        "region": config.OFFICES.get(matched, {}).get("region", "Unknown"),
        "data_through": latest.get("date", "unknown"),
        "day": DOW_NAMES.get(latest_dow, ""),
        "people_in": latest_hc,
        "typical": typical,
        "typical_by_day": typical_by_day,
        "weekly_headcounts": weekly,
        "top_people_this_week": top,
    }

    # --- Phase 2: Ghost signals (plain language) ---
    sig = _cache.get("signals", {}).get(matched, {})
    if sig.get("signals"):
        result["things_to_note"] = sig["signals"]

    # --- Phase 2: CHI score ---
    chi = _cache.get("chi", {}).get(matched, {})
    if chi:
        result["health_score"] = chi["chi"]

    # --- Phase 2: Team sync summary for this office ---
    team_sync = _cache.get("team_sync", {})
    office_teams = {k: v for k, v in team_sync.items() if v.get("office") == matched}
    if office_teams:
        scores = [t["sync_score"] for t in office_teams.values()]
        low_sync = [t for t in office_teams.values() if t["sync_score"] < 0.2]
        result["teams"] = {
            "total_teams": len(office_teams),
            "teams_coming_in_same_days": len(office_teams) - len(low_sync),
            "teams_on_different_days": len(low_sync),
        }

    # --- v1.5: Seniority breakdown ---
    seniority = _cache.get("seniority", {}).get("office_seniority", {}).get(matched, {})
    if seniority:
        result["by_seniority"] = {
            band: {"people": s["people"], "avg_days_per_week": s["avg_days_per_week"]}
            for band, s in seniority.items()
        }

    # --- v1.5: Weekend attendance ---
    weekend = _cache.get("weekend", {}).get("offices", {}).get(matched, {})
    if weekend and weekend.get("weekend_people", 0) > 0:
        result["weekend"] = {
            "people_on_weekends": weekend["weekend_people"],
            "avg_per_weekend_day": weekend["avg_per_weekend_day"],
        }

    # --- v1.5: Mixing score ---
    mixing = _cache.get("mixing", {}).get(matched, {})
    if mixing:
        result["cross_functional_mix"] = f"{mixing.get('avg_streams_per_day', 0)} of {mixing.get('streams_present', 0)} teams present on a typical day"

    return result


def _global_summary():
    _ensure_cache()
    baselines = _cache["baselines"]
    chi_data = _cache.get("chi", {})

    offices = []
    for name, bl in baselines.items():
        latest = bl.get("latest", {})
        hc = latest.get("headcount", 0)
        pool = bl.get("active_pool", 0)
        latest_dow = latest.get("dow", 0)
        dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
        typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0

        entry = {
            "name": name,
            "people_in": hc,
            "typical": typical,
        }

        chi = chi_data.get(name, {})
        if chi:
            entry["health_score"] = chi["chi"]

        offices.append(entry)

    offices.sort(key=lambda x: x["people_in"], reverse=True)

    latest_date = "unknown"
    for bl in baselines.values():
        d = bl.get("latest", {}).get("date")
        if d:
            latest_date = d
            break

    # Ghost flags
    signals = _cache.get("signals", {})
    ghost_offices = [name for name, s in signals.items() if s.get("ghost_flag")]

    result = {
        "data_through": latest_date,
        "offices": offices,
    }
    if ghost_offices:
        result["offices_to_watch"] = ghost_offices

    return result


TOOL_SCHEMA = {
    "name": "query_office_intel",
    "description": "Get office headcounts, top people, health scores, and team info. No office = all offices. With office name = that office's full detail.",
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
