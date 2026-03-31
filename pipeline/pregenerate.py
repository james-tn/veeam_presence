"""Step 16: Pre-generate common responses — serve without Claude call.

Generates ready-to-serve text + card JSON for the most common queries.
The agent checks pre-generated cache first; if hit, returns instantly.
"""

import json
import os
import sys
import pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def pregenerate(baselines, personality, anchors, visitors_data, team_sync, signals, chi):
    """Generate cached responses for common queries."""
    results = {}

    # --- Daily Briefing ---
    offices = []
    for name, bl in baselines.items():
        latest = bl.get("latest", {})
        hc = latest.get("headcount", 0)
        pool = bl.get("active_pool", 0)
        latest_dow = latest.get("dow", 0)
        dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
        typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0

        # Rolling avg + trend
        weekly = [w["headcount"] for w in bl.get("weekly_trend", [])[-4:]]
        daily_avgs = [pool * d.get("rate", 0) for d in bl.get("dow_baselines", {}).values()]
        avg = round(sum(daily_avgs) / len(daily_avgs)) if daily_avgs else typical

        if len(weekly) >= 4:
            recent = sum(weekly[-2:]) / 2
            prior = sum(weekly[:2]) / 2
            trend = "↑" if recent > prior * 1.05 else ("↓" if recent < prior * 0.95 else "→")
        else:
            trend = "→"

        offices.append({"name": name, "hc": hc, "avg": avg, "trend": trend})

    offices.sort(key=lambda x: x["hc"], reverse=True)
    date = "unknown"
    for bl in baselines.values():
        d = bl.get("latest", {}).get("date")
        if d:
            date = d
            break

    total = sum(o["hc"] for o in offices)
    lines = [f"Through {date}, here's attendance across all offices:", ""]
    for o in offices[:10]:
        lines.append(f"{o['name']} — {o['hc']} people, 4wk avg {o['avg']} {o['trend']}")
    rest = offices[10:]
    if rest:
        rest_total = sum(o["hc"] for o in rest)
        lines.append(f"\n+ {len(rest)} smaller offices ({rest_total} people total)")
    lines.append("\nAnything you want to dig into?")

    results["briefing"] = "\n".join(lines)

    # --- Per-office detail ---
    dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    for name, bl in baselines.items():
        latest = bl.get("latest", {})
        hc = latest.get("headcount", 0)
        pool = bl.get("active_pool", 0)
        latest_dow = latest.get("dow", 0)
        dow_bl = bl.get("dow_baselines", {}).get(latest_dow, {})
        typical = round(pool * dow_bl.get("rate", 0)) if dow_bl else 0
        day = dow_names.get(latest_dow, "")
        weekly = [w["headcount"] for w in bl.get("weekly_trend", [])[-4:]]

        an = anchors.get(name, {})
        top = an.get("leaderboard", [])[:4]

        lines = [f"{name} had {hc} people on {day}. Typical for a {day} is about {typical}."]

        if top:
            names = ", ".join(f"{p.get('name', '')} ({p.get('days', '')})" for p in top)
            lines.append(f"\nTop people this week: {names}.")

        if weekly:
            lines.append(f"\nWeekly totals lately: {', '.join(str(w) for w in weekly)}.")

        sig = signals.get(name, {})
        if sig.get("signals"):
            lines.append(f"\n{sig['signals'][0]}.")

        lines.append(f"\nWant to see who's trending up or down in {name.split()[0]}?")

        key = f"office:{name.lower()}"
        results[key] = "\n".join(lines)

    # --- Leaderboards ---
    for name, an in anchors.items():
        top = an.get("leaderboard", [])[:10]
        if not top:
            continue

        lines = [f"Top people in {name} this week:", ""]
        for i, entry in enumerate(top, 1):
            trend_icon = {"up": " ↑", "down": " ↓"}.get(entry.get("trend", ""), "")
            lines.append(f"{i}. {entry.get('name', '')} ({entry.get('stream', '')}) — {entry.get('days', '')}{trend_icon}")

        lines.append(f"\nWant to see trending or office details?")

        key = f"leaderboard:{name.lower()}"
        results[key] = "\n".join(lines)

    # --- Trending up ---
    # Need enriched data for this — skip if not available, agent will compute live

    print(f"  [Pregenerate] {len(results)} cached responses")
    print(f"    Briefing: 1, Office details: {len(baselines)}, Leaderboards: {len(anchors)}")

    return results


if __name__ == "__main__":
    data_dir = config.DATA_DIR
    with open(os.path.join(data_dir, "baselines.pkl"), "rb") as f:
        baselines = pickle.load(f)
    with open(os.path.join(data_dir, "personality.pkl"), "rb") as f:
        personality = pickle.load(f)
    with open(os.path.join(data_dir, "anchors.pkl"), "rb") as f:
        anchors = pickle.load(f)
    with open(os.path.join(data_dir, "visitors.pkl"), "rb") as f:
        visitors = pickle.load(f)
    with open(os.path.join(data_dir, "team_sync.pkl"), "rb") as f:
        team_sync = pickle.load(f)
    with open(os.path.join(data_dir, "signals.pkl"), "rb") as f:
        signals = pickle.load(f)
    with open(os.path.join(data_dir, "chi.pkl"), "rb") as f:
        chi = pickle.load(f)

    results = pregenerate(baselines, personality, anchors, visitors, team_sync, signals, chi)
    with open(os.path.join(data_dir, "pregenerated.pkl"), "wb") as f:
        pickle.dump(results, f)
    print(f"  Saved to {data_dir}/pregenerated.pkl")
