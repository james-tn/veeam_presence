"""Tests for Adaptive Card templates and renderer."""

import json
import pytest


def _valid_adaptive_card(card):
    """Assert card is a valid Adaptive Card structure."""
    assert isinstance(card, dict)
    assert card.get("type") == "AdaptiveCard"
    assert "body" in card
    assert isinstance(card["body"], list)


class TestCardTemplates:
    """Test each card template renders a valid Adaptive Card."""

    def test_briefing_card(self):
        from cards.templates import briefing_card
        data = {
            "offices": [
                {"name": "Prague", "people_in": 185, "typical": 190, "avg": 198, "trend": "down"},
                {"name": "Atlanta", "people_in": 134, "typical": 140, "avg": 140, "trend": "flat"},
            ],
            "data_through": "2025-03-28",
        }
        card = briefing_card(data)
        _valid_adaptive_card(card)

    def test_office_detail_card(self):
        from cards.templates import office_detail_card
        data = {
            "office": "Prague Rustonka",
            "people_in": 185,
            "typical": 190,
            "data_through": "2025-03-28",
            "day": "Fri",
            "peak_day": "Wednesday",
            "typical_by_day": {"Mon": 170, "Tue": 195, "Wed": 200, "Thu": 190, "Fri": 160},
            "top_people_this_week": [
                {"name": "Jan Novak", "role": "R&D", "days": 5},
            ],
            "weekly_headcounts": [338, 332, 310, 295],
        }
        card = office_detail_card(data)
        _valid_adaptive_card(card)

    def test_leaderboard_card(self):
        from cards.templates import leaderboard_card
        data = {
            "office": "Atlanta",
            "data_through": "2025-03-28",
            "leaderboard": [
                {"name": "Maria Garcia", "role": "Sales", "days": 5},
            ],
        }
        card = leaderboard_card(data)
        _valid_adaptive_card(card)

    def test_person_card(self):
        from cards.templates import person_card
        data = {
            "name": "Thomas Murphy",
            "office": "Seattle",
            "role": "R&D",
            "title": "Principal Engineer",
            "days_per_week": 4.2,
            "usual_arrival": "6:15am",
            "usual_departure": "4:00pm",
            "avg_dwell_hours": 9.8,
            "days_they_come_in": {"Mon": 8, "Tue": 9, "Wed": 9, "Thu": 8, "Fri": 3},
            "last_4_weeks": [5, 4, 5, 4],
            "total_days_in": 43,
            "total_workdays": 47,
        }
        card = person_card(data)
        _valid_adaptive_card(card)

    def test_comparison_card(self):
        from cards.templates import comparison_card
        offices = [
            {"office": "Atlanta", "people_in": 134, "typical": 140, "peak_day": "Tuesday"},
            {"office": "Seattle", "people_in": 20, "typical": 32, "peak_day": "Thursday"},
        ]
        card = comparison_card(offices)
        _valid_adaptive_card(card)

    def test_trending_card(self):
        from cards.templates import trending_card
        data = {
            "direction": "trending_up",
            "people": [
                {"name": "Eugene R", "office": "Prague", "was": "1 days/week", "now": "5 days/week"},
            ],
        }
        card = trending_card(data)
        _valid_adaptive_card(card)

    def test_visitors_card(self):
        from cards.templates import visitors_card
        data = {
            "routes": [
                {"from": "Prague", "to": "Berlin", "people": 3, "visit_days": 8},
            ],
            "recent_trips": [
                {"name": "Jan Novak", "home_office": "Prague", "visited": "Berlin", "days": 3},
            ],
        }
        card = visitors_card(data)
        _valid_adaptive_card(card)

    def test_who_was_in_card(self):
        from cards.templates import who_was_in_card
        data = {
            "office": "Seattle",
            "date": "2025-03-28",
            "headcount": 20,
            "people": [
                {"name": "Thomas Murphy", "stream": "R&D", "arrival": "6:15"},
            ],
        }
        card = who_was_in_card(data)
        _valid_adaptive_card(card)

    def test_welcome_card(self):
        from cards.templates import welcome_card
        card = welcome_card()
        _valid_adaptive_card(card)

    def test_overview_card(self):
        from cards.templates import overview_card
        card = overview_card()
        _valid_adaptive_card(card)

    def test_error_card(self):
        from cards.templates import error_card
        card = error_card("Something went wrong.")
        _valid_adaptive_card(card)


class TestRenderer:
    """Test render_card dispatch and try_parse_card."""

    def test_render_card_dispatches_briefing(self):
        from cards.renderer import render_card
        data = {
            "template": "briefing",
            "offices": [{"name": "Prague", "people_in": 100, "typical": 100, "avg": 100, "trend": "flat"}],
            "data_through": "2025-03-28",
        }
        card = render_card(data)
        _valid_adaptive_card(card)

    def test_render_card_generic_fallback(self):
        from cards.renderer import render_card
        data = {
            "template": "standard_insight",
            "card": True,
            "summary": "Test summary",
            "facts": [{"title": "Count", "value": "42"}],
        }
        card = render_card(data)
        _valid_adaptive_card(card)

    def test_try_parse_card_with_json_block(self):
        from cards.renderer import try_parse_card
        text = 'Some text\n```json\n{"card": true, "template": "standard_insight", "summary": "Test"}\n```\nMore text'
        card, remaining = try_parse_card(text)
        assert card is not None
        _valid_adaptive_card(card)

    def test_try_parse_card_no_json(self):
        from cards.renderer import try_parse_card
        card, remaining = try_parse_card("Just plain text response")
        assert card is None
        assert remaining == "Just plain text response"

    def test_render_card_returns_none_for_non_dict(self):
        from cards.renderer import render_card
        assert render_card("not a dict") is None
