"""Default tool set for the scheduler agent."""

from __future__ import annotations

from typing import Any, List

from ...tools.blackboard_calendar.tool import fetch_blackboard_calendar
from ...tools.convert_calendar.tool import fetch_university_calendar
from ...tools.cas_course.tool import fetch_student_course_schedule
from ...tools.operator_calendar.tool import (
    add_calendar_event,
    clear_draft_calendar,
    query_calendar,
    remove_calendar_event,
    reset_draft,
    update_calendar_event,
)
from ...tools.todoist.tool import (
    fetch_todoist_tasks,
)
from ...tools.skill_loader.tool import load_skill


def default_demo_tools() -> List[Any]:
    """Return the default minimal tool set for the scheduler demo."""
    return [
        fetch_university_calendar,
        fetch_blackboard_calendar,
        fetch_todoist_tasks,
        fetch_student_course_schedule,
        load_skill,
        query_calendar,
        add_calendar_event,
        update_calendar_event,
        remove_calendar_event,
        clear_draft_calendar,
        reset_draft,
    ]
