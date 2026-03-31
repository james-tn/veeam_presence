"""Tests for the agent module — skills, structure, and mocked agent calls."""

import pytest


class TestSkillDefinitions:
    """Verify all 10 skills are properly defined."""

    def test_skills_list_has_10_items(self):
        from agent.agent import SKILLS
        assert len(SKILLS) == 10

    def test_each_skill_has_required_fields(self):
        from agent.agent import SKILLS
        for skill in SKILLS:
            assert skill.name, f"Skill missing name"
            assert skill.description, f"Skill {skill.name} missing description"
            assert skill.content, f"Skill {skill.name} missing content"

    def test_skill_names_are_unique(self):
        from agent.agent import SKILLS
        names = [s.name for s in SKILLS]
        assert len(names) == len(set(names)), "Duplicate skill names"

    def test_expected_skill_names_present(self):
        from agent.agent import SKILLS
        names = {s.name for s in SKILLS}
        expected = {
            "office-intelligence", "person-attendance", "travel-visitors",
            "team-sync", "ghost-detection", "trending-attendance",
            "org-leader-rollup", "manager-gravity", "new-hires", "weekend-activity",
        }
        assert names == expected

    def test_skills_provider_initialized(self):
        from agent.agent import _skills_provider
        assert _skills_provider is not None

    def test_ghost_detection_mentions_query_type(self):
        from agent.agent import SKILLS
        ghost = next(s for s in SKILLS if s.name == "ghost-detection")
        assert "ghost" in ghost.content.lower()
        assert "query_type" in ghost.content

    def test_travel_visitors_mentions_visitors(self):
        from agent.agent import SKILLS
        travel = next(s for s in SKILLS if s.name == "travel-visitors")
        assert "visitors" in travel.content.lower()

    def test_weekend_skill_mentions_weekend(self):
        from agent.agent import SKILLS
        weekend = next(s for s in SKILLS if s.name == "weekend-activity")
        assert "weekend" in weekend.content.lower()


class TestAgentModule:
    """Test agent module structure."""

    def test_run_agent_is_async(self):
        import inspect
        from agent.agent import run_agent
        assert inspect.iscoroutinefunction(run_agent)

    def test_cleanup_sessions_callable(self):
        from agent.agent import cleanup_sessions
        assert callable(cleanup_sessions)

    def test_session_ttl_is_reasonable(self):
        from agent.agent import _SESSION_TTL
        assert 300 <= _SESSION_TTL <= 7200  # 5min to 2hr


class TestSkillQueryMapping:
    """Verify each skill's content instructs the LLM to call the right tool."""

    def test_office_intelligence_calls_office_intel(self):
        from agent.agent import SKILLS
        skill = next(s for s in SKILLS if s.name == "office-intelligence")
        assert "tool_query_office_intel" in skill.content

    def test_person_attendance_calls_query_person(self):
        from agent.agent import SKILLS
        skill = next(s for s in SKILLS if s.name == "person-attendance")
        assert "tool_query_person" in skill.content

    def test_all_query_type_skills_reference_tool_query_person(self):
        from agent.agent import SKILLS
        query_type_skills = [
            "travel-visitors", "team-sync", "ghost-detection",
            "trending-attendance", "org-leader-rollup", "manager-gravity",
            "new-hires", "weekend-activity",
        ]
        for name in query_type_skills:
            skill = next(s for s in SKILLS if s.name == name)
            assert "tool_query_person" in skill.content, f"{name} should reference tool_query_person"
