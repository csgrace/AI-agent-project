"""Unit tests for skill_loader tool module."""
import sys
from pathlib import Path
import pytest

# Add backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import global_state as skill_state
from src.tools.skill_loader.tool import load_skill, list_available_skills


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean up SKILL_REGISTRY after each test."""
    yield
    skill_state.SKILL_REGISTRY.clear()


@pytest.fixture
def sample_skill_content():
    """Return sample skill.md content."""
    return """---
name: test_skill
description: A test skill for unit testing
---

# Test Skill

This is the test skill content.
It has multiple lines.
"""


@pytest.fixture
def populate_registry(tmp_path, sample_skill_content):
    """Populate SKILL_REGISTRY with test skills."""
    # Create temporary skill files
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    
    # Create test_skill
    skill1_dir = skills_dir / "test_skill"
    skill1_dir.mkdir()
    skill1_file = skill1_dir / "skill.md"
    skill1_file.write_text(sample_skill_content)
    
    # Create another_skill
    skill2_dir = skills_dir / "another_skill"
    skill2_dir.mkdir()
    skill2_file = skill2_dir / "skill.md"
    skill2_file.write_text("""---
name: another_skill
description: Another test skill
---

# Another Skill

More content here.
""")
    
    # Populate registry
    skill_state.SKILL_REGISTRY["test_skill"] = {
        "path": str(skill1_file),
        "description": "A test skill for unit testing",
        "last_modified": skill1_file.stat().st_mtime
    }
    skill_state.SKILL_REGISTRY["another_skill"] = {
        "path": str(skill2_file),
        "description": "Another test skill",
        "last_modified": skill2_file.stat().st_mtime
    }
    
    return str(skills_dir)


class TestLoadSkill:
    """Test load_skill tool function."""

    def test_load_existing_skill(self, populate_registry):
        """Test loading an existing skill."""
        content = load_skill.invoke({"skill_name": "test_skill"})

        assert content is not None
        assert "test_skill" in content
        assert "A test skill for unit testing" in content

    def test_load_returns_full_content(self, populate_registry, sample_skill_content):
        """Test that load returns the full file content."""
        content = load_skill.invoke({"skill_name": "test_skill"})

        # Should return exactly what's in the file
        assert content == sample_skill_content

    def test_load_includes_frontmatter(self, populate_registry):
        """Test that loaded content includes frontmatter."""
        content = load_skill.invoke({"skill_name": "test_skill"})

        assert "---" in content
        assert "name: test_skill" in content
        assert "description:" in content

    def test_load_nonexistent_skill(self):
        """Test loading a non-existent skill raises error."""
        with pytest.raises(ValueError) as exc_info:
            load_skill.invoke({"skill_name": "nonexistent_skill"})

        assert "nonexistent_skill" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()

    def test_load_shows_available_skills_on_error(self, populate_registry):
        """Test that error message shows available skills."""
        with pytest.raises(ValueError) as exc_info:
            load_skill.invoke({"skill_name": "unknown_skill"})

        error_msg = str(exc_info.value)
        assert "test_skill" in error_msg
        assert "another_skill" in error_msg

    def test_load_another_skill(self, populate_registry):
        """Test loading a different skill."""
        content = load_skill.invoke({"skill_name": "another_skill"})

        assert "another_skill" in content
        assert "Another test skill" in content
        assert "More content here" in content

    def test_load_from_empty_registry(self):
        """Test loading when registry is empty."""
        with pytest.raises(ValueError) as exc_info:
            load_skill.invoke({"skill_name": "any_skill"})

        assert "any_skill" in str(exc_info.value)
        assert "(none)" in str(exc_info.value) or "available" in str(exc_info.value).lower()


class TestListAvailableSkills:
    """Test list_available_skills tool function."""

    def test_list_empty_registry(self):
        """Test listing skills when registry is empty."""
        result = list_available_skills.invoke({})

        assert result == "No skills registered."

    def test_list_with_skills(self, populate_registry):
        """Test listing skills when registry has items."""
        result = list_available_skills.invoke({})

        assert "Available skills:" in result
        assert "test_skill" in result
        assert "another_skill" in result

    def test_list_includes_descriptions(self, populate_registry):
        """Test that list includes skill descriptions."""
        result = list_available_skills.invoke({})

        assert "A test skill for unit testing" in result
        assert "Another test skill" in result

    def test_list_format(self, populate_registry):
        """Test the format of the skills list."""
        result = list_available_skills.invoke({})

        lines = result.split("\n")
        assert lines[0] == "Available skills:"
        # Each skill should be on its own line with "- " prefix
        skill_lines = [line for line in lines[1:] if line.strip()]
        assert len(skill_lines) == 2
        for line in skill_lines:
            assert line.startswith("- ")
            assert ":" in line

    def test_list_single_skill(self, tmp_path):
        """Test listing with only one skill."""
        # Create single skill
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "single_skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "skill.md"
        skill_file.write_text("""---
name: single_skill
description: Only skill
---

Content.
""")
        
        skill_state.SKILL_REGISTRY["single_skill"] = {
            "path": str(skill_file),
            "description": "Only skill",
            "last_modified": skill_file.stat().st_mtime
        }

        result = list_available_skills.invoke({})

        assert "single_skill" in result
        assert "Only skill" in result
        assert result.count("-") == 1  # Only one skill line

    def test_list_skills_without_description(self, tmp_path):
        """Test listing skills that have no description."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "no_desc_skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "skill.md"
        skill_file.write_text("""---
name: no_desc_skill
---

Content.
""")
        
        skill_state.SKILL_REGISTRY["no_desc_skill"] = {
            "path": str(skill_file),
            "description": "",  # Empty description
            "last_modified": skill_file.stat().st_mtime
        }

        result = list_available_skills.invoke({})

        assert "no_desc_skill" in result
        # Should show empty string or handle gracefully
        assert "no_desc_skill:" in result


class TestToolIntegration:
    """Integration tests for the skill loader tools."""

    def test_load_after_list(self, populate_registry):
        """Test that skills listed can be loaded."""
        # First list available skills
        list_result = list_available_skills.invoke({})

        # Then load each skill
        for skill_name in ["test_skill", "another_skill"]:
            content = load_skill.invoke({"skill_name": skill_name})
            assert content is not None
            assert skill_name in content

    def test_registry_consistency(self, populate_registry):
        """Test that registry is consistent between tools."""
        # Get list from list_available_skills
        list_result = list_available_skills.invoke({})

        # Get list from SKILL_REGISTRY directly
        registry_skills = list(skill_state.SKILL_REGISTRY.keys())

        # Both should contain the same skills
        for skill in registry_skills:
            assert skill in list_result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
