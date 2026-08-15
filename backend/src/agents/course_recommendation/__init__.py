"""Course recommendation agent package."""

from .agent import CourseRecommendationAgent
from .prompt_builder import COURSE_AGENT_SYSTEM_PROMPT

# Backward-compatible alias
COURSE_RECOMMENDATION_SYSTEM_PROMPT = COURSE_AGENT_SYSTEM_PROMPT

__all__ = [
    "CourseRecommendationAgent",
    "COURSE_RECOMMENDATION_SYSTEM_PROMPT",
    "COURSE_AGENT_SYSTEM_PROMPT",
]