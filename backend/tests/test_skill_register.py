"""Unit tests for skill_register module."""
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import SKILL_REGISTRY
from src.services.skill_register.register import (
    parse_skill_md,
    scan_skills,
    register_all_skills,
    refresh_skills,
    get_skill_path,
    get_skill_description,
    list_skills,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean up SKILL_REGISTRY after each test."""
    yield
    SKILL_REGISTRY.clear()


@pytest.fixture
def sample_skill_content():
    """Return sample skill.md content."""
    return """---
name: test_skill
description: A test skill for unit testing
---

# Test Skill

This is a test skill content.
"""


@pytest.fixture
def temp_skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill1_dir = skills_dir / "test_skill"
    skill1_dir.mkdir()
    skill1_file = skill1_dir / "skill.md"
    skill1_file.write_text("""---
name: test_skill
description: Test skill description
---

# Test Skill

Content here.
""")

    skill2_dir = skills_dir / "another_skill"
    skill2_dir.mkdir()
    skill2_file = skill2_dir / "skill.md"
    skill2_file.write_text("""---
name: another_skill
description: Another test skill
---

# Another Skill

More content.
""")

    return str(skills_dir)


class TestParseSkillMd:
    """Test parse_skill_md function."""

    def test_parse_valid_skill_md(self, tmp_path, sample_skill_content):
        """Test parsing a valid skill.md file."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text(sample_skill_content)

        result = parse_skill_md(str(skill_file))

        assert result is not None
        assert result["name"] == "test_skill"
        assert result["description"] == "A test skill for unit testing"

    def test_parse_skill_md_without_frontmatter(self, tmp_path):
        """Test parsing a file without frontmatter."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("# Just a markdown file\n\nNo frontmatter here.")

        result = parse_skill_md(str(skill_file))

        assert result is None

    def test_parse_skill_md_invalid_yaml(self, tmp_path):
        """Test parsing a file with invalid YAML."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("""---
invalid: yaml: content: [
---

Content.
""")

        result = parse_skill_md(str(skill_file))

        assert result is None

    def test_parse_skill_md_missing_name(self, tmp_path):
        """Test parsing a file with frontmatter but no name field."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("""---
description: Just a description
---

Content.
""")

        result = parse_skill_md(str(skill_file))

        assert result is None

    def test_parse_nonexistent_file(self):
        """Test parsing a non-existent file."""
        result = parse_skill_md("/nonexistent/path/skill.md")

        assert result is None

    def test_parse_skill_md_empty_description(self, tmp_path):
        """Test parsing a file with empty description."""
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("""---
name: test_skill
---

Content.
""")

        result = parse_skill_md(str(skill_file))

        assert result is not None
        assert result["name"] == "test_skill"
        assert result["description"] == ""


class TestScanSkills:
    """Test scan_skills function."""

    def test_scan_empty_directory(self, tmp_path):
        """Test scanning an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = scan_skills(str(empty_dir))

        assert result == {}

    def test_scan_with_skills(self, temp_skills_dir):
        """Test scanning a directory with skills."""
        result = scan_skills(temp_skills_dir)

        assert len(result) == 2
        assert "test_skill" in result
        assert "another_skill" in result
        assert result["test_skill"]["description"] == "Test skill description"
        assert result["another_skill"]["description"] == "Another test skill"

    def test_scan_skips_non_skill_dirs(self, tmp_path):
        """Test that scan skips directories without skill.md."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        no_skill_dir = skills_dir / "no_skill"
        no_skill_dir.mkdir()
        (no_skill_dir / "other.txt").write_text("Not a skill")

        valid_dir = skills_dir / "valid_skill"
        valid_dir.mkdir()
        (valid_dir / "skill.md").write_text("""---
name: valid_skill
description: Valid skill
---

Content.
""")

        result = scan_skills(str(skills_dir))

        assert len(result) == 1
        assert "valid_skill" in result
        assert "no_skill" not in result

    def test_scan_skips_files(self, tmp_path):
        """Test that scan skips files in the skills directory."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        (skills_dir / "not_a_dir.txt").write_text("I'm a file")

        result = scan_skills(str(skills_dir))

        assert result == {}

    def test_scan_nonexistent_directory(self):
        """Test scanning a non-existent directory."""
        result = scan_skills("/nonexistent/directory")

        assert result == {}


class TestRegisterAllSkills:
    """Test register_all_skills function."""

    def test_register_clears_previous_registry(self, temp_skills_dir):
        """Test that register clears previous registry."""
        register_all_skills(temp_skills_dir)
        assert len(SKILL_REGISTRY) == 2

        SKILL_REGISTRY["extra_skill"] = {"path": "extra", "description": "Extra"}
        assert len(SKILL_REGISTRY) == 3

        register_all_skills(temp_skills_dir)
        assert len(SKILL_REGISTRY) == 2
        assert "extra_skill" not in SKILL_REGISTRY

    def test_register_populates_registry(self, temp_skills_dir):
        """Test that register populates the registry."""
        result = register_all_skills(temp_skills_dir)

        assert len(SKILL_REGISTRY) == 2
        assert "test_skill" in SKILL_REGISTRY
        assert "another_skill" in SKILL_REGISTRY
        assert SKILL_REGISTRY["test_skill"]["path"].endswith(os.path.join("test_skill", "skill.md"))

    def test_register_returns_skills_dict(self, temp_skills_dir):
        """Test that register returns the skills dictionary."""
        result = register_all_skills(temp_skills_dir)

        assert isinstance(result, dict)
        assert len(result) == 2
        assert result == SKILL_REGISTRY


class TestRefreshSkills:
    """Test refresh_skills function."""

    def test_refresh_adds_new_skills(self, tmp_path):
        """Test that refresh adds new skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill1_dir = skills_dir / "skill1"
        skill1_dir.mkdir()
        (skill1_dir / "skill.md").write_text("""---
name: skill1
description: First skill
---

Content.
""")
        register_all_skills(str(skills_dir))
        assert len(SKILL_REGISTRY) == 1

        skill2_dir = skills_dir / "skill2"
        skill2_dir.mkdir()
        (skill2_dir / "skill.md").write_text("""---
name: skill2
description: Second skill
---

Content.
""")

        result = refresh_skills(str(skills_dir))

        assert len(SKILL_REGISTRY) == 2
        assert "skill2" in SKILL_REGISTRY
        assert "skill2" in result

    def test_refresh_updates_modified_skills(self, tmp_path):
        """Test that refresh updates modified skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        skill_file = skill_dir / "skill.md"
        skill_file.write_text("""---
name: skill1
description: Original description
---

Content.
""")
        register_all_skills(str(skills_dir))

        skill_file.write_text("""---
name: skill1
description: Modified description
---

Modified content.
""")

        result = refresh_skills(str(skills_dir))

        assert "skill1" in result
        assert SKILL_REGISTRY["skill1"]["description"] == "Modified description"

    def test_refresh_removes_deleted_skills(self, tmp_path):
        """Test that refresh removes deleted skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill1_dir = skills_dir / "skill1"
        skill1_dir.mkdir()
        (skill1_dir / "skill.md").write_text("""---
name: skill1
description: First skill
---

Content.
""")

        skill2_dir = skills_dir / "skill2"
        skill2_dir.mkdir()
        (skill2_dir / "skill.md").write_text("""---
name: skill2
description: Second skill
---

Content.
""")

        register_all_skills(str(skills_dir))
        assert len(SKILL_REGISTRY) == 2

        import shutil
        shutil.rmtree(skill2_dir)

        result = refresh_skills(str(skills_dir))

        assert len(SKILL_REGISTRY) == 1
        assert "skill1" in SKILL_REGISTRY
        assert "skill2" not in SKILL_REGISTRY

    def test_refresh_returns_all_skills(self, temp_skills_dir):
        """Test that refresh returns all registered skill names."""
        register_all_skills(temp_skills_dir)

        result = refresh_skills(temp_skills_dir)

        assert isinstance(result, list)
        assert len(result) == 2
        assert "test_skill" in result
        assert "another_skill" in result

    def test_refresh_clears_and_re_registers(self, tmp_path):
        """Test that refresh clears registry and re-registers all skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("""---
name: skill1
description: First skill
---

Content.
""")
        register_all_skills(str(skills_dir))

        SKILL_REGISTRY["extra"] = {"path": "extra", "description": "Extra"}

        result = refresh_skills(str(skills_dir))

        assert "extra" not in SKILL_REGISTRY
        assert len(SKILL_REGISTRY) == 1
        assert "skill1" in result


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_skill_path_existing(self, temp_skills_dir):
        """Test getting path for existing skill."""
        register_all_skills(temp_skills_dir)

        path = get_skill_path("test_skill")

        assert path is not None
        assert path.endswith(os.path.join("test_skill", "skill.md"))

    def test_get_skill_path_nonexistent(self, temp_skills_dir):
        """Test getting path for non-existent skill."""
        register_all_skills(temp_skills_dir)

        path = get_skill_path("nonexistent")

        assert path is None

    def test_get_skill_description_existing(self, temp_skills_dir):
        """Test getting description for existing skill."""
        register_all_skills(temp_skills_dir)

        description = get_skill_description("test_skill")

        assert description == "Test skill description"

    def test_get_skill_description_nonexistent(self, temp_skills_dir):
        """Test getting description for non-existent skill."""
        register_all_skills(temp_skills_dir)

        description = get_skill_description("nonexistent")

        assert description is None

    def test_list_skills_empty(self):
        """Test listing skills when registry is empty."""
        skills = list_skills()

        assert skills == []

    def test_list_skills_with_items(self, temp_skills_dir):
        """Test listing skills when registry has items."""
        register_all_skills(temp_skills_dir)

        skills = list_skills()

        assert len(skills) == 2
        assert "test_skill" in skills
        assert "another_skill" in skills


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
