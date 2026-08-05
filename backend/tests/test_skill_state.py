"""Unit tests for global_state module."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import global_state


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean up SKILL_REGISTRY after each test."""
    yield
    global_state.SKILL_REGISTRY.clear()


class TestSkillRegistry:
    """Test module-level skill registry variables."""

    def test_skill_registry_initially_empty(self):
        """Test that SKILL_REGISTRY is initially empty."""
        assert len(global_state.SKILL_REGISTRY) == 0

    def test_get_skill_registry_returns_dict(self):
        """Test that get_skill_registry returns a dictionary."""
        registry = global_state.get_skill_registry()
        assert isinstance(registry, dict)

    def test_skill_registry_mutable(self):
        """Test that SKILL_REGISTRY can be modified."""
        global_state.SKILL_REGISTRY["test_skill"] = {
            "path": "/path/to/skill.md",
            "description": "Test description",
        }
        assert "test_skill" in global_state.SKILL_REGISTRY
        assert global_state.SKILL_REGISTRY["test_skill"]["path"] == "/path/to/skill.md"

    def test_get_skill_registry_returns_same_object(self):
        """Test that get_skill_registry returns the same registry object."""
        registry1 = global_state.get_skill_registry()
        registry2 = global_state.get_skill_registry()
        assert registry1 is registry2

    def test_registry_persists_across_calls(self):
        """Test that registry changes persist across function calls."""
        global_state.SKILL_REGISTRY["skill1"] = {"path": "path1", "description": "desc1"}

        registry = global_state.get_skill_registry()
        assert "skill1" in registry
        assert registry["skill1"]["path"] == "path1"


class TestCalendarState:
    """Test module-level calendar state variables."""

    def test_calendar_initially_none(self):
        """Test that CALENDAR is initially None."""
        assert global_state.CALENDAR is None

    def test_get_calendar_returns_none_initially(self):
        """Test that get_calendar returns None initially."""
        calendar = global_state.get_calendar()
        assert calendar is None

    def test_set_calendar(self):
        """Test that set_calendar sets the global calendar."""
        from src.models.calendar.calendar import Calendar
        
        test_calendar = Calendar(name="Test Calendar")
        global_state.set_calendar(test_calendar)
        
        assert global_state.CALENDAR is test_calendar
        assert global_state.get_calendar() is test_calendar

    def test_get_calendar_returns_same_object(self):
        """Test that get_calendar returns the same calendar object."""
        from src.models.calendar.calendar import Calendar
        
        test_calendar = Calendar(name="Test Calendar")
        global_state.set_calendar(test_calendar)
        
        calendar1 = global_state.get_calendar()
        calendar2 = global_state.get_calendar()
        assert calendar1 is calendar2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
