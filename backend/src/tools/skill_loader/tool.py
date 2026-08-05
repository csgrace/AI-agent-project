"""Skill loader tool for LangChain.

This tool allows agents to load skill content by name.
"""
from langchain.tools import tool
# try:
#     from langchain.tools import tool
# except ImportError:
#     # Fallback when langchain is not available (for testing)
#     def tool(func):
#         return func

from ...core.global_state import SKILL_REGISTRY


@tool
def load_skill(skill_name: str) -> str:
    """Load the complete content of a skill by its name.

    This tool retrieves the full content of a skill file (including YAML frontmatter)
    that has been registered in the skill registry.

    Args:
        skill_name: The name of the skill to load. Available skills include:
            {available_skills}

    Returns:
        str: The complete content of the skill.md file (including frontmatter).

    Raises:
        ValueError: If the skill is not found in the registry.

    Example:
        >>> content = load_skill("fetch_calendar")
        >>> print(content)
        ---
        name: fetch_calendar
        description: 获取校历并转换为事件列表
        ---
        # fetch_calendar
        ...
    """
    # Look up the skill in the registry
    skill_info = SKILL_REGISTRY.get(skill_name)

    if not skill_info:
        available = list(SKILL_REGISTRY.keys())
        available_str = ", ".join(available) if available else "(none)"
        raise ValueError(
            f"Skill '{skill_name}' not found. "
            f"Available skills: {available_str}"
        )

    file_path = skill_info['path']

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        raise ValueError(f"Failed to load skill '{skill_name}' from {file_path}: {e}")


@tool
def list_available_skills() -> str:
    """List all available skills with their descriptions.

    Returns:
        str: A formatted list of all registered skills.

    Example:
        >>> skills = list_available_skills()
        >>> print(skills)
        Available skills:
        - fetch_calendar: 获取校历并转换为事件列表
    """
    if not SKILL_REGISTRY:
        return "No skills registered."

    lines = ["Available skills:"]
    for name, info in SKILL_REGISTRY.items():
        description = info.get('description', 'No description')
        lines.append(f"- {name}: {description}")

    return "\n".join(lines)


# Dynamically update the docstring with available skills
def _update_load_skill_docstring():
    """Update the load_skill docstring with current available skills."""
    available = list(SKILL_REGISTRY.keys())
    if available:
        available_str = ", ".join([f'"{s}"' for s in available])
    else:
        available_str = "(no skills registered)"

    load_skill.__doc__ = load_skill.__doc__.format(
        available_skills=available_str
    )


# Update docstring when module is loaded
_update_load_skill_docstring()
