"""Calendar loader implementation.

This module provides functionality to load and save calendar data from JSON files
and initialize the global calendar instance.
"""
import json
from pathlib import Path
from typing import Optional

from ...core import get_calendar, set_calendar, set_draft_calendar
from ...models.calendar.calendar import Calendar
from ...models.calendar.draft_calendar import DraftCalendar
from ...models.calendar.enums import DirtyType


DEFAULT_CALENDAR_PATH = Path("data/tis_download/calendar.json")


def load_calendar_from_file(file_path: Optional[Path] = None) -> Calendar:
    """Load calendar from a JSON file.

    Args:
        file_path: Path to the calendar JSON file. If None, uses the default path.

    Returns:
        Calendar instance loaded from file, or a new empty calendar if file not found.
    """
    path = file_path or DEFAULT_CALENDAR_PATH

    if not path.exists():
        return Calendar(name="My Calendar")

    with open(path, 'r', encoding='utf-8') as f:
        json_str = f.read()

    if not json_str.strip():
        return Calendar(name="My Calendar")

    try:
        return Calendar.from_json(json_str)
    except json.JSONDecodeError:
        return Calendar(name="My Calendar")


def save_calendar_to_file(calendar: Calendar, file_path: Optional[Path] = None) -> Path:
    """Save calendar to a JSON file and return saved path."""
    path = file_path or DEFAULT_CALENDAR_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(calendar.to_json())

    return path


def init_calendar(file_path: Optional[Path] = None) -> Calendar:
    """Initialize the global calendar instance.

    Loads calendar from file and sets it as the global calendar variable.

    Args:
        file_path: Path to the calendar JSON file. If None, uses the default path.

    Returns:
        The initialized Calendar instance.
    """
    calendar = load_calendar_from_file(file_path)
    set_calendar(calendar)
    return calendar


# ---------------------------------------------------------------------------
# Draft calendar persistence
# ---------------------------------------------------------------------------


def save_draft_calendar_to_file(draft: DraftCalendar, file_path: Path) -> Path:
    """Save a DraftCalendar to a JSON file."""
    draft.to_json_file(file_path)
    return file_path


def load_draft_calendar_from_file(file_path: Path) -> Optional[DraftCalendar]:
    """Load a DraftCalendar from a JSON file.

    Returns None if the file does not exist or is corrupted.
    """
    return DraftCalendar.from_json_file(file_path)


def init_draft_calendar(calendar_path: Optional[Path], draft_path: Optional[Path]) -> DraftCalendar:
    """Initialize the global draft calendar.

    Tries to restore a previously persisted dirty draft first.
    Falls back to a clean draft cloned from the main calendar.

    Args:
        calendar_path: Path to the main calendar JSON file (for fallback).
        draft_path: Path to the persisted draft JSON file.

    Returns:
        The resolved DraftCalendar instance.
    """
    # Try to restore dirty draft from file.
    if draft_path is not None and draft_path.exists():
        loaded = load_draft_calendar_from_file(draft_path)
        if loaded is not None and loaded.dirty is not None and loaded.dirty != DirtyType.CLEAR:
            set_draft_calendar(loaded)
            return loaded

    # Fallback: clean draft cloned from main calendar.
    calendar = get_calendar()
    if calendar is not None:
        cloned_events = [event.model_copy(deep=True) for event in calendar.events]
        draft = DraftCalendar(events=cloned_events, dirty=DirtyType.CLEAR)
    else:
        draft = DraftCalendar(events=[], dirty=DirtyType.CLEAR)
    set_draft_calendar(draft)
    return draft
