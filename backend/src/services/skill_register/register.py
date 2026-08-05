"""Skill register implementation.

This module provides functionality to scan, parse, and register skills
from the skills directory.
"""
import os
import sys
from typing import Dict, Any, Optional, List
from pathlib import Path

import yaml

from ...core import SKILL_REGISTRY


def parse_skill_md(file_path: str) -> Optional[Dict[str, str]]:
    """Parse a skill.md file and extract name and description from frontmatter.

    The skill.md file should have YAML frontmatter enclosed in --- markers:
    ---
    name: skill_name
    description: Skill description
    ---

    Args:
        file_path: Path to the skill.md file.

    Returns:
        Dict with 'name' and 'description' keys, or None if parsing fails.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if file has frontmatter (starts with ---)
        if not content.strip().startswith('---'):
            return None

        # Split by --- to extract frontmatter
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        frontmatter = parts[1].strip()

        # Parse YAML frontmatter
        metadata = yaml.safe_load(frontmatter)

        if not isinstance(metadata, dict):
            return None

        name = metadata.get('name')
        description = metadata.get('description')

        if not name:
            return None

        return {
            'name': name,
            'description': description or ''
        }

    except Exception as e:
        print(f"Error parsing skill file {file_path}: {e}")
        return None


def scan_skills(skills_dir: str) -> Dict[str, Dict[str, Any]]:
    """Scan the skills directory and parse all skill.md files.

    Expected directory structure:
        skills_dir/
            skill_name_1/
                skill.md
            skill_name_2/
                skill.md

    Args:
        skills_dir: Path to the skills directory.

    Returns:
        Dict mapping skill names to their metadata including path and description.
    """
    skills = {}
    skills_path = Path(skills_dir)

    if not skills_path.exists():
        print(f"Skills directory not found: {skills_dir}")
        return skills

    # Iterate through each subdirectory in skills_dir
    for skill_dir in skills_path.iterdir():
        if not skill_dir.is_dir():
            continue

        # Look for skill.md in the subdirectory
        skill_file = skill_dir / 'skill.md'

        if not skill_file.exists():
            continue

        # Parse the skill file
        metadata = parse_skill_md(str(skill_file))

        if metadata:
            skill_name = metadata['name']
            skills[skill_name] = {
                'path': str(skill_file),
                'description': metadata['description']
            }

    return skills


def register_all_skills(skills_dir: str) -> Dict[str, Dict[str, Any]]:
    """Register all skills to the global registry.

    This function scans the skills directory and updates the global
    SKILL_REGISTRY with all found skills.

    Args:
        skills_dir: Path to the skills directory.

    Returns:
        The updated skill registry dictionary.
    """
    skills = scan_skills(skills_dir)

    # Clear and update the global registry via module attribute
    SKILL_REGISTRY.clear()
    SKILL_REGISTRY.update(skills)

    print(f"Registered {len(skills)} skills: {list(skills.keys())}")

    return SKILL_REGISTRY


def refresh_skills(skills_dir: str) -> List[str]:
    """Refresh the skill registry by re-scanning the skills directory.

    This function clears the current registry and re-registers all skills
    from the skills directory, behaving identically to register_all_skills.

    Args:
        skills_dir: Path to the skills directory.

    Returns:
        List of registered skill names.
    """
    skills = scan_skills(skills_dir)

    SKILL_REGISTRY.clear()
    SKILL_REGISTRY.update(skills)

    print(f"Refreshed {len(skills)} skills: {list(skills.keys())}")

    return list(skills.keys())


def get_skill_path(skill_name: str) -> Optional[str]:
    """Get the file path for a registered skill.

    Args:
        skill_name: Name of the skill.

    Returns:
        Path to the skill.md file, or None if not found.
    """
    skill_info = SKILL_REGISTRY.get(skill_name)
    return skill_info['path'] if skill_info else None


def get_skill_description(skill_name: str) -> Optional[str]:
    """Get the description for a registered skill.

    Args:
        skill_name: Name of the skill.

    Returns:
        Skill description, or None if not found.
    """
    skill_info = SKILL_REGISTRY.get(skill_name)
    return skill_info['description'] if skill_info else None


def list_skills() -> List[str]:
    """List all registered skill names.

    Returns:
        List of skill names.
    """
    return list(SKILL_REGISTRY.keys())
