"""Tests for tools — query_office_intel and query_person against fixture data."""

import json
import pytest


class TestQueryOfficeIntel:
    """Tests for query_office_intel tool."""

    def test_global_summary_returns_all_offices(self):
        from tools.query_office_intel import query_office_intel
        result = query_office_intel()
        assert "offices" in result
        assert len(result["offices"]) >= 4  # 17 with real data, 4 with fixtures
        assert "data_through" in result

    def test_specific_office_returns_detail(self):
        from tools.query_office_intel import query_office_intel
        result = query_office_intel(office="Prague Rustonka")
        assert result["office"] == "Prague Rustonka"
        assert "people_in" in result
        assert "top_people_this_week" in result
        assert "typical_by_day" in result

    def test_fuzzy_office_match(self):
        from tools.query_office_intel import query_office_intel
        result = query_office_intel(office="Prague")
        assert result["office"] == "Prague Rustonka"

    def test_unknown_office_returns_error(self):
        from tools.query_office_intel import query_office_intel
        result = query_office_intel(office="Narnia")
        assert "error" in result
        assert "available_offices" in result

    def test_office_has_health_score(self):
        from tools.query_office_intel import query_office_intel
        result = query_office_intel(office="Seattle")
        assert "health_score" in result

    def test_office_has_team_info(self):
        from tools.query_office_intel import query_office_intel
        result = query_office_intel(office="Prague Rustonka")
        assert "teams" in result
        assert "total_teams" in result["teams"]

    def test_typed_wrapper_returns_json_string(self):
        from tools.query_office_intel import tool_query_office_intel
        result = tool_query_office_intel()
        parsed = json.loads(result)
        assert "offices" in parsed

    def test_typed_wrapper_with_office(self):
        from tools.query_office_intel import tool_query_office_intel
        result = tool_query_office_intel(office="Atlanta")
        parsed = json.loads(result)
        assert parsed["office"] == "Atlanta"


class TestQueryPerson:
    """Tests for query_person tool — all 11 query types."""

    def test_person_pattern(self):
        from tools.query_person import query_person
        result = query_person(person="Jan Novak")
        assert "error" not in result
        assert "days_per_week" in result
        assert "usual_arrival" in result

    def test_person_not_found(self):
        from tools.query_person import query_person
        result = query_person(person="Nobody McFakename")
        assert "error" in result

    def test_who_was_in(self):
        from tools.query_person import query_person
        result = query_person(office="Atlanta", query_type="who_was_in")
        assert "people" in result
        assert "headcount" in result

    def test_trending_up(self):
        from tools.query_person import query_person
        result = query_person(query_type="trending_up")
        assert "people" in result
        assert "direction" in result

    def test_trending_down(self):
        from tools.query_person import query_person
        result = query_person(query_type="trending_down")
        assert "direction" in result
        assert result["direction"] == "trending_down"

    def test_visitors(self):
        from tools.query_person import query_person
        result = query_person(query_type="visitors")
        assert "flows" in result or "routes" in result

    def test_team_sync(self):
        from tools.query_person import query_person
        result = query_person(query_type="team_sync")
        assert "total_teams" in result

    def test_ghost(self):
        from tools.query_person import query_person
        result = query_person(query_type="ghost")
        assert "offices_with_changes" in result

    def test_org_leader(self):
        from tools.query_person import query_person
        result = query_person(query_type="org_leader")
        assert "leaders" in result

    def test_manager_gravity(self):
        from tools.query_person import query_person
        result = query_person(query_type="manager_gravity")
        assert "top_gravity" in result

    def test_new_hires(self):
        from tools.query_person import query_person
        result = query_person(query_type="new_hires")
        assert "people" in result
        assert "total_new_hires" in result

    def test_weekend(self):
        from tools.query_person import query_person
        result = query_person(query_type="weekend")
        assert "total_weekend_people" in result

    def test_typed_wrapper_returns_json_string(self):
        from tools.query_person import tool_query_person
        result = tool_query_person(person="Jan Novak")
        parsed = json.loads(result)
        assert "error" not in parsed
        assert "days_per_week" in parsed

    def test_typed_wrapper_with_query_type(self):
        from tools.query_person import tool_query_person
        result = tool_query_person(query_type="visitors")
        parsed = json.loads(result)
        assert "flows" in parsed or "routes" in parsed
