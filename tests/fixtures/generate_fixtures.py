"""Generate synthetic test fixture pkl files.

Creates all 14 pkl files for 4 test offices with ~20 fake people.
Self-contained — only uses pandas, numpy, pickle.

Usage:
    python -m tests.fixtures.generate_fixtures
"""

import os
import pickle
import random
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd

FIXTURE_DIR = os.path.dirname(__file__)

# 4 test offices
OFFICES = ["Prague Rustonka", "Atlanta", "Seattle", "Bucharest (AFI)"]

# 20 fake people — 5 per office
PEOPLE = [
    # Prague
    {"name": "Jan Novak", "email": "jan.novak@veeam.com", "office": "Prague Rustonka", "stream": "R&D", "title": "Senior Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Eva Horakova", "email": "eva.horakova@veeam.com", "office": "Prague Rustonka", "stream": "R&D", "title": "Staff Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Petr Svoboda", "email": "petr.svoboda@veeam.com", "office": "Prague Rustonka", "stream": "R&D", "title": "Engineering Manager", "seniority_band": "Manager", "mgmt_level": "8. Manager"},
    {"name": "Marie Kralova", "email": "marie.kralova@veeam.com", "office": "Prague Rustonka", "stream": "Sales", "title": "Account Executive", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Tomas Dvorak", "email": "tomas.dvorak@veeam.com", "office": "Prague Rustonka", "stream": "G&A", "title": "HR Business Partner", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    # Atlanta
    {"name": "Maria Garcia", "email": "maria.garcia@veeam.com", "office": "Atlanta", "stream": "Sales", "title": "Regional VP Sales", "seniority_band": "Senior Leader", "mgmt_level": "4. Vice President"},
    {"name": "James Wilson", "email": "james.wilson@veeam.com", "office": "Atlanta", "stream": "Sales", "title": "Sr Account Exec", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Robert Brown", "email": "robert.brown@veeam.com", "office": "Atlanta", "stream": "Marketing", "title": "Marketing Manager", "seniority_band": "Manager", "mgmt_level": "8. Manager"},
    {"name": "Sarah Johnson", "email": "sarah.johnson@veeam.com", "office": "Atlanta", "stream": "G&A", "title": "Finance Analyst", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Michael Davis", "email": "michael.davis@veeam.com", "office": "Atlanta", "stream": "Sales", "title": "Sales Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    # Seattle
    {"name": "Thomas Murphy", "email": "thomas.murphy@veeam.com", "office": "Seattle", "stream": "R&D", "title": "Principal Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Aaron Fink", "email": "aaron.fink@veeam.com", "office": "Seattle", "stream": "R&D", "title": "Software Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Lisa Chen", "email": "lisa.chen@veeam.com", "office": "Seattle", "stream": "R&D", "title": "Engineering Director", "seniority_band": "Senior Leader", "mgmt_level": "6. Director"},
    {"name": "Kevin Park", "email": "kevin.park@veeam.com", "office": "Seattle", "stream": "R&D", "title": "QA Lead", "seniority_band": "Manager", "mgmt_level": "9. Team Leader"},
    {"name": "Amy Wang", "email": "amy.wang@veeam.com", "office": "Seattle", "stream": "G&A", "title": "Office Manager", "seniority_band": "IC", "mgmt_level": "13. Para - professional"},
    # Bucharest
    {"name": "Andrei Popescu", "email": "andrei.popescu@veeam.com", "office": "Bucharest (AFI)", "stream": "R&D", "title": "Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Elena Ionescu", "email": "elena.ionescu@veeam.com", "office": "Bucharest (AFI)", "stream": "R&D", "title": "Senior Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Mihai Radu", "email": "mihai.radu@veeam.com", "office": "Bucharest (AFI)", "stream": "R&D", "title": "Team Lead", "seniority_band": "Manager", "mgmt_level": "9. Team Leader"},
    {"name": "Ana Dumitrescu", "email": "ana.dumitrescu@veeam.com", "office": "Bucharest (AFI)", "stream": "Sales", "title": "Sales Rep", "seniority_band": "IC", "mgmt_level": "11. Professional"},
    {"name": "Cristian Marin", "email": "cristian.marin@veeam.com", "office": "Bucharest (AFI)", "stream": "Cost of Revenue", "title": "Support Engineer", "seniority_band": "IC", "mgmt_level": "11. Professional"},
]

# Date range: 10 weeks of data ending last Friday
def _last_friday():
    today = date(2025, 3, 28)  # Fixed for reproducibility
    days_since_friday = (today.weekday() - 4) % 7
    return today - timedelta(days=days_since_friday)

END_DATE = _last_friday()
START_DATE = END_DATE - timedelta(weeks=10)


def _generate_enriched():
    """Generate enriched.pkl — person-day DataFrame."""
    rows = []
    current = START_DATE
    while current <= END_DATE:
        dow = current.weekday()
        if dow >= 5:  # Skip weekends for most people
            current += timedelta(days=1)
            continue
        for p in PEOPLE:
            # Each person comes in ~3-4 days/week (random)
            if random.random() < 0.75:
                arrival = 7.0 + random.random() * 3  # 7:00-10:00
                dwell = 6.0 + random.random() * 4  # 6-10 hours
                rows.append({
                    "email": p["email"],
                    "preferred_name": p["name"],
                    "office": p["office"],
                    "stream": p["stream"],
                    "businesstitle": p["title"],
                    "seniority_band": p["seniority_band"],
                    "management_level": p["mgmt_level"],
                    "workday_matched": True,
                    "date": pd.Timestamp(current),
                    "dow": dow,
                    "dwell_hours": round(dwell, 1),
                    "arrival_hour": round(arrival, 1),
                    "departure_hour": round(arrival + dwell, 1),
                })
        current += timedelta(days=1)

    # Add a few weekend records for weekend.pkl testing
    for p in PEOPLE[:3]:
        for sat in pd.date_range(START_DATE, END_DATE, freq="W-SAT")[:4]:
            rows.append({
                "email": p["email"],
                "preferred_name": p["name"],
                "office": p["office"],
                "stream": p["stream"],
                "businesstitle": p["title"],
                "seniority_band": p["seniority_band"],
                "management_level": p["mgmt_level"],
                "workday_matched": True,
                "date": pd.Timestamp(sat),
                "dow": 5,
                "dwell_hours": round(3.0 + random.random() * 2, 1),
                "arrival_hour": round(9.0 + random.random() * 2, 1),
                "departure_hour": round(13.0 + random.random() * 2, 1),
            })

    df = pd.DataFrame(rows)
    return df


def _generate_baselines(enriched_df):
    """Generate baselines.pkl — per-office baselines."""
    baselines = {}
    for office in OFFICES:
        odf = enriched_df[enriched_df["office"] == office]
        weekdays = odf[odf["dow"] <= 4]
        people_emails = weekdays["email"].nunique()

        # DOW baselines
        dow_baselines = {}
        for dow in range(5):
            ddf = weekdays[weekdays["dow"] == dow]
            days_count = ddf["date"].nunique()
            if days_count > 0:
                avg_people = ddf.groupby("date")["email"].nunique().mean()
                rate = avg_people / max(people_emails, 1)
            else:
                rate = 0
            dow_baselines[dow] = {"rate": round(rate, 3)}

        # Latest day
        if len(weekdays) > 0:
            latest_date = weekdays["date"].max()
            latest_dow = latest_date.weekday()
            latest_hc = weekdays[weekdays["date"] == latest_date]["email"].nunique()
        else:
            latest_date = pd.Timestamp(END_DATE)
            latest_dow = END_DATE.weekday()
            latest_hc = 0

        # Weekly trend
        weekly_trend = []
        for _, wg in weekdays.groupby(pd.Grouper(key="date", freq="W-MON")):
            if len(wg) > 0:
                weekly_trend.append({"headcount": wg["email"].nunique()})

        baselines[office] = {
            "latest": {"headcount": latest_hc, "date": str(latest_date.date()), "dow": latest_dow},
            "active_pool": people_emails,
            "dow_baselines": dow_baselines,
            "weekly_trend": weekly_trend[-8:],
        }
    return baselines


def _generate_anchors(enriched_df):
    """Generate anchors.pkl — office leaderboards."""
    anchors = {}
    for office in OFFICES:
        odf = enriched_df[(enriched_df["office"] == office) & (enriched_df["dow"] <= 4)]
        person_days = odf.groupby("email").agg(
            name=("preferred_name", "first"),
            stream=("stream", "first"),
            days=("date", "nunique"),
        ).reset_index().sort_values("days", ascending=False)

        anchors[office] = {
            "leaderboard": [
                {"name": r["name"], "stream": r["stream"], "days": int(r["days"])}
                for _, r in person_days.head(10).iterrows()
            ]
        }
    return anchors


def _generate_personality():
    """Generate personality.pkl — office personality profiles."""
    personality = {}
    peak_days = ["Tuesday", "Wednesday", "Thursday", "Wednesday"]
    for i, office in enumerate(OFFICES):
        personality[office] = {"peak_day": peak_days[i]}
    return personality


def _generate_signals():
    """Generate signals.pkl — ghost detection signals."""
    signals = {}
    signals["Prague Rustonka"] = {
        "signals": [], "ghost_flag": False, "signals_active": 0,
    }
    signals["Atlanta"] = {
        "signals": [], "ghost_flag": False, "signals_active": 0,
    }
    signals["Seattle"] = {
        "signals": ["Friday attendance declining", "Peak day headcount lower than 4-week average"],
        "ghost_flag": True, "signals_active": 2,
    }
    signals["Bucharest (AFI)"] = {
        "signals": [], "ghost_flag": False, "signals_active": 0,
    }
    return signals


def _generate_chi():
    """Generate chi.pkl — Culture Health Index scores."""
    return {
        "Prague Rustonka": {"chi": 7.2},
        "Atlanta": {"chi": 6.8},
        "Seattle": {"chi": 5.1},
        "Bucharest (AFI)": {"chi": 7.5},
    }


def _generate_team_sync():
    """Generate team_sync.pkl — team synchronization scores."""
    teams = {}
    team_defs = [
        ("R&D Platform", "Prague Rustonka", "Petr Svoboda", 4, 0.65),
        ("Sales EMEA", "Prague Rustonka", "Marie Kralova", 3, 0.45),
        ("Sales Americas", "Atlanta", "Maria Garcia", 4, 0.55),
        ("Marketing US", "Atlanta", "Robert Brown", 3, 0.30),
        ("R&D Core", "Seattle", "Lisa Chen", 4, 0.70),
        ("R&D QA", "Seattle", "Kevin Park", 3, 0.15),
        ("R&D Cloud", "Bucharest (AFI)", "Mihai Radu", 5, 0.60),
        ("Support EMEA", "Bucharest (AFI)", "Cristian Marin", 3, 0.20),
    ]
    for team_name, office, manager, members, sync in team_defs:
        key = f"{office}|{team_name}"
        teams[key] = {
            "team": team_name,
            "office": office,
            "manager": manager,
            "members": members,
            "sync_score": sync,
        }
    return teams


def _generate_seniority():
    """Generate seniority.pkl — seniority breakdowns + org leader rollups."""
    office_seniority = {}
    for office in OFFICES:
        office_people = [p for p in PEOPLE if p["office"] == office]
        bands = {}
        for p in office_people:
            band = p["seniority_band"]
            if band not in bands:
                bands[band] = {"people": 0, "avg_days_per_week": 0}
            bands[band]["people"] += 1
            bands[band]["avg_days_per_week"] = round(3.0 + random.random(), 1)
        office_seniority[office] = bands

    org_leaders = {
        "Maria Garcia": {
            "leader": "Maria Garcia", "level": "Vice President",
            "people": 15, "offices": ["Atlanta", "Seattle"],
            "avg_days_per_week": 4.2, "top_offices": [{"office": "Atlanta", "people": 10}],
        },
        "Lisa Chen": {
            "leader": "Lisa Chen", "level": "Director",
            "people": 8, "offices": ["Seattle"],
            "avg_days_per_week": 3.8, "top_offices": [{"office": "Seattle", "people": 8}],
        },
    }

    return {"office_seniority": office_seniority, "org_leaders": org_leaders}


def _generate_visitors():
    """Generate visitors.pkl — cross-office visitor data."""
    return {
        "routes": [
            {"from": "Prague Rustonka", "to": "Atlanta", "people": 2, "visit_days": 5},
            {"from": "Atlanta", "to": "Seattle", "people": 1, "visit_days": 3},
            {"from": "Bucharest (AFI)", "to": "Prague Rustonka", "people": 1, "visit_days": 2},
        ],
        "recent_trips": [
            {"name": "Jan Novak", "home_office": "Prague Rustonka", "visited": "Atlanta", "days": 3},
            {"name": "James Wilson", "home_office": "Atlanta", "visited": "Seattle", "days": 3},
        ],
    }


def _generate_manager_gravity():
    """Generate manager_gravity.pkl — manager gravity scores."""
    managers = {}
    mgr_defs = [
        ("Petr Svoboda", "Prague Rustonka", 4, 0.25, 80, 55),
        ("Robert Brown", "Atlanta", 3, 0.10, 65, 55),
        ("Lisa Chen", "Seattle", 4, 0.30, 85, 50),
        ("Mihai Radu", "Bucharest (AFI)", 5, 0.20, 75, 55),
        ("Kevin Park", "Seattle", 3, 0.05, 60, 55),
        ("Maria Garcia", "Atlanta", 4, 0.35, 90, 45),
    ]
    for name, office, team_size, gravity, when_in, when_out in mgr_defs:
        managers[name] = {
            "manager": name,
            "office": office,
            "team_size": team_size,
            "gravity_score": gravity,
            "team_attendance_when_mgr_in": when_in,
            "team_attendance_when_mgr_out": when_out,
        }
    return managers


def _generate_new_hires():
    """Generate new_hires.pkl — new hire integration data."""
    return {
        "people": [
            {"name": "Aaron Fink", "office": "Seattle", "role": "R&D", "hire_date": "2025-01-15", "avg_days_per_week": 4.0, "trend": "ramping up"},
            {"name": "Ana Dumitrescu", "office": "Bucharest (AFI)", "role": "Sales", "hire_date": "2025-02-01", "avg_days_per_week": 3.5, "trend": "steady"},
            {"name": "Michael Davis", "office": "Atlanta", "role": "Sales", "hire_date": "2024-12-01", "avg_days_per_week": 2.0, "trend": "fading"},
        ],
    }


def _generate_weekend(enriched_df):
    """Generate weekend.pkl — weekend attendance data."""
    weekend_df = enriched_df[enriched_df["dow"] >= 5]
    offices_data = {}
    for office in OFFICES:
        odf = weekend_df[weekend_df["office"] == office]
        people_count = odf["email"].nunique()
        days_count = odf["date"].nunique()
        avg_per_day = round(odf.groupby("date")["email"].nunique().mean(), 1) if days_count > 0 else 0
        people_list = []
        for email in odf["email"].unique():
            pdf = odf[odf["email"] == email]
            people_list.append({
                "name": pdf["preferred_name"].iloc[0],
                "days": int(pdf["date"].nunique()),
            })
        offices_data[office] = {
            "weekend_people": people_count,
            "avg_per_weekend_day": avg_per_day,
            "people": people_list,
        }

    return {
        "total_weekend_people": weekend_df["email"].nunique(),
        "offices": offices_data,
    }


def _generate_mixing():
    """Generate mixing.pkl — cross-functional mixing scores."""
    return {
        "Prague Rustonka": {"avg_streams_per_day": 2.8, "streams_present": 3},
        "Atlanta": {"avg_streams_per_day": 3.2, "streams_present": 4},
        "Seattle": {"avg_streams_per_day": 1.8, "streams_present": 2},
        "Bucharest (AFI)": {"avg_streams_per_day": 2.5, "streams_present": 3},
    }


def _generate_pregenerated():
    """Generate pregenerated.pkl — pre-generated response cache."""
    pregen = {
        "briefing": (
            "Through Friday March 28, here's attendance across all offices:\n\n"
            "Bucharest — 4 people, 4wk avg 4 →\n"
            "Prague — 4 people, 4wk avg 4 →\n"
            "Atlanta — 4 people, 4wk avg 4 →\n"
            "Seattle — 3 people, 4wk avg 3 →\n\n"
            "Anything you want to dig into?"
        ),
    }
    for office in OFFICES:
        key = f"office:{office}"
        pregen[key] = f"{office} had 4 people on Friday. Typical for a Friday is about 3.\n\nWant to see the leaderboard?"
        ldr_key = f"leaderboard:{office}"
        pregen[ldr_key] = f"Top people in {office} this week: (fixture data)\n\nWant details on anyone?"
    return pregen


def generate_all():
    """Generate all 14 pkl files."""
    random.seed(42)
    np.random.seed(42)

    print("Generating synthetic fixtures...")

    # 1. Enriched DataFrame (base for several others)
    enriched = _generate_enriched()
    _save("enriched.pkl", enriched)
    print(f"  enriched.pkl: {len(enriched)} rows, {enriched['email'].nunique()} people")

    # 2-4. Baselines, anchors, personality
    baselines = _generate_baselines(enriched)
    _save("baselines.pkl", baselines)
    print(f"  baselines.pkl: {len(baselines)} offices")

    anchors = _generate_anchors(enriched)
    _save("anchors.pkl", anchors)
    print(f"  anchors.pkl: {len(anchors)} offices")

    personality = _generate_personality()
    _save("personality.pkl", personality)

    # 5-8. Signals, CHI, team_sync, seniority
    signals = _generate_signals()
    _save("signals.pkl", signals)

    chi = _generate_chi()
    _save("chi.pkl", chi)

    team_sync = _generate_team_sync()
    _save("team_sync.pkl", team_sync)

    seniority = _generate_seniority()
    _save("seniority.pkl", seniority)

    # 9-11. Visitors, manager gravity, new hires
    visitors = _generate_visitors()
    _save("visitors.pkl", visitors)

    manager_gravity = _generate_manager_gravity()
    _save("manager_gravity.pkl", manager_gravity)

    new_hires = _generate_new_hires()
    _save("new_hires.pkl", new_hires)

    # 12-13. Weekend, mixing
    weekend = _generate_weekend(enriched)
    _save("weekend.pkl", weekend)

    mixing = _generate_mixing()
    _save("mixing.pkl", mixing)

    # 14. Pregenerated
    pregenerated = _generate_pregenerated()
    _save("pregenerated.pkl", pregenerated)

    print(f"\nDone! 14 pkl files written to {FIXTURE_DIR}/")


def _save(filename, data):
    path = os.path.join(FIXTURE_DIR, filename)
    with open(path, "wb") as f:
        pickle.dump(data, f)


if __name__ == "__main__":
    generate_all()
