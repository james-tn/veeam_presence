"""Generate sample Adaptive Card JSON for each template — paste into adaptivecards.io/designer to preview."""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from cards.templates import (
    briefing_card, office_detail_card, leaderboard_card, person_card,
    comparison_card, trending_card, visitors_card, who_was_in_card,
    welcome_card, overview_card, error_card, data_card,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "card_samples")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --- 1. Briefing Card ---
briefing_data = {
    "data_through": "2026-03-26",
    "total_offices": 17,
    "total_people_in": 801,
    "offices": [
        {"name": "Bucharest", "people_in": 217, "typical": 179},
        {"name": "Prague", "people_in": 185, "typical": 190},
        {"name": "Atlanta", "people_in": 134, "typical": 143},
        {"name": "Kuala Lumpur", "people_in": 74, "typical": 22},
        {"name": "Berlin", "people_in": 41, "typical": 36},
        {"name": "Mumbai", "people_in": 28, "typical": 18},
        {"name": "Singapore", "people_in": 25, "typical": 26},
        {"name": "Seattle", "people_in": 20, "typical": 32},
        {"name": "Phoenix", "people_in": 18, "typical": 18},
        {"name": "Paris", "people_in": 15, "typical": 11},
        {"name": "Buenos Aires", "people_in": 12, "typical": 13},
        {"name": "Yerevan", "people_in": 10, "typical": 12},
        {"name": "Mexico", "people_in": 8, "typical": 7},
        {"name": "Sydney", "people_in": 6, "typical": 9},
        {"name": "Baar", "people_in": 5, "typical": 7},
        {"name": "Columbus", "people_in": 2, "typical": 5},
        {"name": "Shanghai", "people_in": 1, "typical": 2},
    ],
}

# --- 2. Office Detail Card ---
office_data = {
    "office": "Prague Rustonka",
    "region": "EMEA",
    "data_through": "2026-03-26",
    "day": "Thu",
    "people_in": 185,
    "typical": 190,
    "typical_by_day": {"Mon": 165, "Tue": 188, "Wed": 196, "Thu": 190, "Fri": 143},
    "weekly_headcounts": [333, 338, 309, 295],
    "top_people_this_week": [
        {"name": "Valery Rubtsov", "role": "R&D", "days": "4/4"},
        {"name": "Andrey Borovik", "role": "R&D", "days": "4/4"},
        {"name": "Roman Sakov", "role": "R&D", "days": "4/4"},
        {"name": "Alex Trushchalov", "role": "R&D", "days": "4/4"},
        {"name": "Anastassiya Larina", "role": "R&D", "days": "3/4"},
    ],
    "health_score": 64,
    "things_to_note": ["Friday attendance down: 106 vs 146 prior avg"],
    "by_seniority": {"IC": {"people": 350, "avg_days_per_week": 2.1}, "Manager": {"people": 140, "avg_days_per_week": 1.8}, "Senior Leader": {"people": 99, "avg_days_per_week": 1.5}},
}

# --- 3. Leaderboard Card ---
leaderboard_data = {
    "office": "Atlanta",
    "entries": [
        {"name": "Marrilyn Keutcha", "role": "G&A", "days": "4/4", "trend": "steady"},
        {"name": "Maria Garcia", "role": "Sales", "days": "4/4", "trend": "up"},
        {"name": "Greyson Stevens", "role": "G&A", "days": "4/4", "trend": "up"},
        {"name": "Vadim Chumakov", "role": "Sales", "days": "4/4", "trend": "up"},
        {"name": "Jason Wright", "role": "Sales", "days": "3/4", "trend": "steady"},
        {"name": "Ashley Monroe", "role": "G&A", "days": "3/4", "trend": "down"},
        {"name": "Carlos Ruiz", "role": "Sales", "days": "3/4", "trend": "steady"},
        {"name": "Denise Powell", "role": "G&A", "days": "2/4", "trend": "down"},
    ],
}

# --- 4. Person Card ---
person_data = {
    "name": "Thomas Murphy",
    "office": "Seattle",
    "role": "G&A",
    "title": "Desktop Support Engineer II",
    "days_per_week": 4.2,
    "usual_arrival": "6:42am",
    "usual_departure": "4:30pm",
    "avg_dwell_hours": 9.8,
    "days_they_come_in": {"Mon": 7, "Tue": 9, "Wed": 8, "Thu": 9, "Fri": 3},
    "total_days_in": 36,
    "total_workdays": 47,
    "days_not_in": ["2026-01-20", "2026-01-27", "2026-02-03", "2026-02-14", "2026-02-21", "2026-03-03", "2026-03-07", "2026-03-14", "2026-03-17", "2026-03-21", "2026-03-24"],
}

# --- 5. Comparison Card ---
comparison_offices = [
    {"office": "Atlanta", "people_in": 134, "typical": 143, "peak_day": "Tue",
     "top_people_this_week": [{"name": "Marrilyn Keutcha", "days": "4/4"}]},
    {"office": "Seattle", "people_in": 20, "typical": 32, "peak_day": "Thu",
     "top_people_this_week": [{"name": "Aaron Fink", "days": "4/4"}]},
]

# --- 6. Trending Card ---
trending_data = {
    "direction": "trending_up",
    "people": [
        {"name": "Eugene Romanyuk", "office": "Prague", "was": "0.8 days/week", "now": "5.5 days/week"},
        {"name": "Alex Moise", "office": "Bucharest", "was": "0 days/week", "now": "4.0 days/week"},
        {"name": "Piotr Tarach", "office": "Prague", "was": "0 days/week", "now": "3.5 days/week"},
        {"name": "Polina Shchukina", "office": "Berlin", "was": "0 days/week", "now": "3.5 days/week"},
        {"name": "Sam Brysbaert", "office": "Prague", "was": "0 days/week", "now": "3.5 days/week"},
    ],
}

# --- 7. Visitors Card ---
visitors_data = {
    "flows": [
        {"from": "Seattle", "to": "Atlanta", "people": 8, "days": 10},
        {"from": "Paris", "to": "Bucharest", "people": 6, "days": 5},
        {"from": "Prague", "to": "Bucharest", "people": 5, "days": 10},
        {"from": "Bucharest", "to": "Prague", "people": 5, "days": 7},
        {"from": "Singapore", "to": "KL", "people": 5, "days": 6},
    ],
    "recent_trips": [
        {"name": "Joe Foggiato", "home_office": "Singapore", "visited": "Seattle", "days": 4},
        {"name": "Keith Sng", "home_office": "Singapore", "visited": "Seattle", "days": 4},
        {"name": "Cubitt Betham", "home_office": "Sydney", "visited": "Singapore", "days": 3},
    ],
}

# --- 8. Who Was In Card ---
who_was_in_data = {
    "office": "Seattle",
    "date": "2026-03-26",
    "headcount": 20,
    "people": [
        {"name": "Aaron Fink", "stream": "G&A", "arrival": "6:15"},
        {"name": "Thomas Murphy", "stream": "G&A", "arrival": "6:42"},
        {"name": "Sarah Chen", "stream": "Sales", "arrival": "7:10"},
        {"name": "Mike Roberts", "stream": "R&D", "arrival": "7:30"},
        {"name": "Lisa Park", "stream": "G&A", "arrival": "8:05"},
    ],
}

# --- 9. Ghost Detection (data_card) ---
ghost_data_highlights = [
    "Phoenix — 4 signals: Friday erosion, peak ceiling drop, shape flattening, dwell compression",
    "Baar — 2 signals: Friday erosion, peak ceiling drop",
    "Prague — 1 signal: Friday attendance down vs prior avg",
]

# --- 10. Team Sync (data_card) ---
team_sync_highlights = [
    "R&D Prague — 89% of team overlaps on Tuesdays and Wednesdays",
    "Sales Atlanta — 62% overlap, best day is Thursday",
    "G&A Seattle — 45% overlap, fragmented schedule",
    "108 of 364 teams have < 30% member overlap on any single day",
]


# --- Generate all cards ---
samples = {
    "01_briefing": briefing_card(briefing_data),
    "02_office_detail": office_detail_card(office_data),
    "03_leaderboard": leaderboard_card(leaderboard_data),
    "04_person": person_card(person_data),
    "05_comparison": comparison_card(comparison_offices),
    "06_trending": trending_card(trending_data),
    "07_visitors": visitors_card(visitors_data),
    "08_who_was_in": who_was_in_card(who_was_in_data),
    "09_ghost": data_card("Offices Showing Decay", ghost_data_highlights, [
        ("Details on Phoenix", "Tell me about Phoenix"),
        ("All offices", "Give me the daily briefing"),
    ]),
    "10_team_sync": data_card("Team Coordination", team_sync_highlights, [
        ("Which teams are least coordinated?", "Which teams are least coordinated?"),
        ("All offices", "Give me the daily briefing"),
    ]),
    "11_welcome": welcome_card(),
    "12_overview": overview_card(),
    "13_error": error_card("Having trouble reaching the data warehouse. Usually resolves in a few minutes."),
}

for name, card in samples.items():
    path = os.path.join(OUTPUT_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)
    print(f"  {name}.json")

print(f"\nSaved {len(samples)} cards to {OUTPUT_DIR}/")
print("Paste any of these into https://adaptivecards.io/designer/ to preview")
print("Select 'Microsoft Teams' as the host app in the designer")
