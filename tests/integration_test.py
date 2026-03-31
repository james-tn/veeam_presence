"""Integration test — verifies every module loads, every tool runs, every card renders.

Run this BEFORE any commit. If it fails, don't push.

Usage: python tests/integration_test.py
"""

import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
ERRORS = []


def test(name, fn):
    global PASS, FAIL
    try:
        result = fn()
        if result is False:
            FAIL += 1
            ERRORS.append(f"FAIL: {name}")
            print(f"  FAIL  {name}")
        else:
            PASS += 1
            print(f"  OK    {name}")
    except Exception as e:
        FAIL += 1
        ERRORS.append(f"FAIL: {name} — {e}")
        print(f"  FAIL  {name} — {e}")
        traceback.print_exc()


print("=" * 60)
print("INTEGRATION TEST — Veeam Presence")
print("=" * 60)

# --- 1. Module imports ---
print("\n[1] Module imports")

test("import config", lambda: __import__("config"))
test("import agent", lambda: __import__("agent"))
test("import system_prompt", lambda: __import__("system_prompt"))
test("import response_cache", lambda: __import__("response_cache"))
try:
    __import__("aiohttp")
    test("import proactive_briefing", lambda: __import__("proactive_briefing"))
except ImportError:
    print("  SKIP import proactive_briefing (aiohttp not installed locally — OK, Docker-only)")
try:
    __import__("fastapi")
    test("import app", lambda: __import__("app"))
except ImportError:
    print("  SKIP import app (fastapi not installed locally — OK, Docker-only)")
test("import cards.templates", lambda: __import__("cards.templates"))
test("import cards.renderer", lambda: __import__("cards.renderer"))
test("import tools.query_office_intel", lambda: __import__("tools.query_office_intel"))
test("import tools.query_person", lambda: __import__("tools.query_person"))
test("import pipeline.holidays_cal", lambda: __import__("pipeline.holidays_cal"))

# --- 2. Data files exist ---
print("\n[2] Data files")
import config

data_files = [
    "baselines.pkl", "personality.pkl", "anchors.pkl", "visitors.pkl",
    "team_sync.pkl", "signals.pkl", "chi.pkl", "seniority.pkl",
    "manager_gravity.pkl", "new_hires.pkl", "weekend.pkl", "mixing.pkl",
    "pregenerated.pkl", "enriched.pkl",
]
for f in data_files:
    path = os.path.join(config.DATA_DIR, f)
    test(f"data/{f} exists", lambda p=path: os.path.exists(p) or False)

# --- 3. Tool loading ---
print("\n[3] Tool loading")

from tools.query_office_intel import load_cache, query_office_intel, _match_office
load_cache()
test("office cache loaded", lambda: True)

from tools.query_person import _load_enriched, query_person
_load_enriched()
test("enriched data loaded", lambda: True)

from response_cache import load_pregenerated, check_pregenerated
load_pregenerated()
test("pregenerated cache loaded", lambda: True)

# --- 4. Tool queries ---
print("\n[4] Tool queries — office intel")

def test_global_summary():
    r = query_office_intel()
    assert "offices" in r, "missing offices key"
    assert len(r["offices"]) > 0, "no offices"
    for o in r["offices"]:
        assert "name" in o, "office missing name"
        assert "people_in" in o, "office missing people_in"
        assert "trend" in o, "office missing trend"
        assert o["trend"] in ("up", "down", "flat"), f"bad trend: {o['trend']}"
    return True

test("global summary", test_global_summary)

def test_office_detail():
    r = query_office_intel(office="Prague")
    assert r.get("office") == "Prague Rustonka", f"wrong office: {r.get('office')}"
    assert "people_in" in r, "missing people_in"
    assert "typical" in r, "missing typical"
    assert "top_people_this_week" in r, "missing top_people"
    assert "peak_day" in r, "missing peak_day"
    return True

test("office detail (Prague)", test_office_detail)

def test_office_not_found():
    r = query_office_intel(office="Narnia")
    assert "error" in r, "should return error for unknown office"
    return True

test("office not found", test_office_not_found)

def test_office_fuzzy_match():
    assert _match_office("bucharest") == "Bucharest (AFI)"
    assert _match_office("prague") == "Prague Rustonka"
    assert _match_office("atlanta") == "Atlanta"
    return True

test("office fuzzy matching", test_office_fuzzy_match)

# --- 5. Tool queries — person ---
print("\n[5] Tool queries — person")

def test_person_pattern():
    r = query_person(person="Scott Jackson")
    assert "name" in r, "missing name"
    assert r["name"] != "", "empty name"
    # Critical: name must NOT be a holiday name
    assert "Day" not in r["name"] and "Birthday" not in r["name"], f"name is a holiday: {r['name']}"
    assert "days_per_week" in r, "missing days_per_week"
    assert "usual_arrival" in r, "missing usual_arrival"
    assert "days_not_in" in r, "missing days_not_in"
    assert "holidays_excluded" in r, "missing holidays_excluded"
    return True

test("person pattern (Scott Jackson)", test_person_pattern)

def test_person_nickname():
    r = query_person(person="Tom Murphy")
    assert "name" in r, "missing name"
    assert "murphy" in r.get("name", "").lower() or "murphy" in r.get("office", "").lower() or "error" not in r, \
        f"Tom Murphy not found: {r}"
    return True

test("person nickname (Tom Murphy)", test_person_nickname)

def test_person_not_found():
    r = query_person(person="Nonexistent Person XYZ123")
    assert "error" in r, "should return error for unknown person"
    return True

test("person not found", test_person_not_found)

def test_trending_up():
    r = query_person(query_type="trending_up")
    assert "people" in r, "missing people key"
    for p in r["people"][:3]:
        assert "name" in p, "trending person missing name"
        assert p["name"] != 0 and p["name"] != "0", f"name is 0 (fillna bug): {p}"
    return True

test("trending up", test_trending_up)

def test_trending_down():
    r = query_person(query_type="trending_down")
    assert "people" in r, "missing people key"
    for p in r["people"][:3]:
        assert p.get("name") != 0 and p.get("name") != "0", f"name is 0: {p}"
    return True

test("trending down", test_trending_down)

def test_visitors():
    r = query_person(query_type="visitors")
    assert "flows" in r, "missing flows"
    assert len(r["flows"]) > 0, "no visitor flows"
    return True

test("visitors", test_visitors)

def test_team_sync():
    r = query_person(query_type="team_sync")
    assert "total_teams" in r, "missing total_teams"
    return True

test("team sync", test_team_sync)

def test_ghost():
    r = query_person(query_type="ghost")
    assert "offices_with_changes" in r, "missing offices_with_changes"
    return True

test("ghost detection", test_ghost)

def test_who_was_in():
    r = query_person(office="Seattle", query_type="who_was_in")
    assert "people" in r, "missing people"
    assert "headcount" in r, "missing headcount"
    return True

test("who was in (Seattle)", test_who_was_in)

# --- 6. Pre-generated cache ---
print("\n[6] Pre-generated cache")

def test_pregen_briefing():
    r = check_pregenerated("give me the daily briefing")
    assert r is not None, "briefing not cached"
    assert "Bucharest" in r, "briefing doesn't mention Bucharest"
    return True

test("pregen: briefing", test_pregen_briefing)

def test_pregen_office():
    r = check_pregenerated("what's going on in Prague?")
    assert r is not None, "Prague not cached"
    assert "Prague" in r, "response doesn't mention Prague"
    return True

test("pregen: office detail", test_pregen_office)

def test_pregen_compare_excluded():
    r = check_pregenerated("compare Prague and Atlanta")
    assert r is None, "compare should NOT hit pre-gen cache"
    return True

test("pregen: compare excluded", test_pregen_compare_excluded)

def test_pregen_person_excluded():
    r = check_pregenerated("who is Scott Jackson?")
    assert r is None, "person query should NOT hit pre-gen cache"
    return True

test("pregen: person excluded", test_pregen_person_excluded)

# --- 7. Card rendering ---
print("\n[7] Card rendering")

from cards.templates import (
    briefing_card, office_detail_card, leaderboard_card, person_card,
    comparison_card, trending_card, visitors_card, who_was_in_card,
    welcome_card, overview_card, error_card,
)
from cards.renderer import render_card, try_parse_card

def test_card_renders(name, card_fn, *args):
    card = card_fn(*args)
    assert card is not None, "card is None"
    assert card.get("type") == "AdaptiveCard", "not an AdaptiveCard"
    assert card.get("version") == "1.5", f"wrong version: {card.get('version')}"
    assert len(card.get("body", [])) > 0, "empty body"
    # Verify JSON serializable
    json.dumps(card)
    return True

sample_offices = [
    {"name": "Atlanta", "people_in": 134, "typical": 143, "avg": 140, "trend": "flat"},
    {"name": "Prague", "people_in": 185, "typical": 190, "avg": 178, "trend": "down"},
]

test("card: welcome", lambda: test_card_renders("welcome", welcome_card))
test("card: overview", lambda: test_card_renders("overview", overview_card))
test("card: error", lambda: test_card_renders("error", error_card, "Test error"))
test("card: briefing", lambda: test_card_renders("briefing", briefing_card, {
    "data_through": "2026-03-26", "total_people_in": 801, "offices": sample_offices}))
test("card: office detail", lambda: test_card_renders("office", office_detail_card, {
    "office": "Prague", "people_in": 185, "typical": 190, "day": "Thu", "data_through": "2026-03-26"}))
test("card: leaderboard", lambda: test_card_renders("leaderboard", leaderboard_card, {
    "office": "Prague", "entries": [{"name": "Test", "role": "R&D", "days": "4/4", "trend": "up"}]}))
test("card: person", lambda: test_card_renders("person", person_card, {
    "name": "Test Person", "office": "Seattle", "title": "Engineer", "days_per_week": 4.2,
    "usual_arrival": "8:00am", "usual_departure": "5:00pm", "avg_dwell_hours": 9}))
test("card: comparison", lambda: test_card_renders("comparison", comparison_card, sample_offices))
test("card: trending", lambda: test_card_renders("trending", trending_card, {
    "direction": "trending_up", "people": [{"name": "Test", "office": "Prague", "was": "1", "now": "4"}]}))

def test_renderer_comparison():
    """Verify renderer passes list not dict to comparison_card."""
    card = render_card({"template": "comparison", "offices": sample_offices})
    assert card is not None, "comparison render returned None"
    assert card.get("type") == "AdaptiveCard"
    return True

test("renderer: comparison passes list", test_renderer_comparison)

# --- 8. Holidays ---
print("\n[8] Holidays")

from datetime import date
from pipeline.holidays_cal import is_holiday, get_workday_count

test("US Presidents Day is holiday for Atlanta",
     lambda: is_holiday("Atlanta", date(2026, 2, 16)) or False)
test("US Presidents Day is NOT holiday for Prague",
     lambda: (not is_holiday("Prague Rustonka", date(2026, 2, 16))) or False)
test("Atlanta workdays Jan-Mar 2026",
     lambda: 55 <= get_workday_count("Atlanta", date(2026, 1, 1), date(2026, 3, 26)) <= 60 or False)

# --- 9. Dockerfile completeness ---
print("\n[9] Dockerfile")

def test_dockerfile_has_all_files():
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "Dockerfile")) as f:
        content = f.read()
    required = ["config.py", "app.py", "agent.py", "system_prompt.py",
                "response_cache.py", "proactive_briefing.py",
                "pipeline/", "tools/", "cards/"]
    missing = [r for r in required if r not in content]
    assert not missing, f"Dockerfile missing COPY for: {missing}"
    return True

test("Dockerfile has all files", test_dockerfile_has_all_files)

# --- 10. Agent routing ---
print("\n[10] Agent routing")

from agent import _add_routing_hint

test("travel routing", lambda: "[ROUTING:" in _add_routing_hint("who is traveling between offices?"))
test("team sync routing", lambda: "[ROUTING:" in _add_routing_hint("are teams coming in on the same days?"))
test("ghost routing", lambda: "[ROUTING:" in _add_routing_hint("which offices are going quiet?"))
test("overview routing", lambda: "[ROUTING:" in _add_routing_hint("what can you tell me?"))
test("normal query no routing", lambda: "[ROUTING:" not in _add_routing_hint("how's Prague?"))

# --- Summary ---
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
if ERRORS:
    print("\nFAILURES:")
    for e in ERRORS:
        print(f"  {e}")
print("=" * 60)

sys.exit(1 if FAIL > 0 else 0)
