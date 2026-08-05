"""Todoist Tool for LangChain.

This tool provides functions for interacting with Todoist API.
"""
from typing import List, Optional
from datetime import datetime

# Try to import langchain tools, but handle case where they're not available
from langchain.tools import tool

# Try to import models, but handle case where they're not available
from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.enums import Priority, EventCategory, DirtyType
from ...core.global_state import get_calendar, get_draft_calendar, get_object_store


from .utils import (
    create_task,
    get_task,
    get_tasks,
    transform_calendar_priority,
)


@tool
def fetch_todoist_tasks() -> str:
    """Fetch tasks from Todoist and convert them to CalendarEvent objects.
    
    This function retrieves tasks from the user's Todoist account and converts
    them to CalendarEvent format for integration with the calendar system.
    Tasks can be filtered by project ID or label name.
    
    Args:
        project_id: Optional project ID to filter tasks by
        label: Optional label name to filter tasks by
        limit: Maximum number of tasks to fetch (default 200)
        
    Returns:
        str: Success message indicating whether Todoist tasks were added to draft calendar.
        
    Raises:
        Exception: If authentication fails or API request fails
        
    Example:
        >>> result = fetch_todoist_tasks()
        >>> print(result)
    """
    # Check if there are uncommitted modifications
    draft_calendar = get_draft_calendar()
    if draft_calendar is not None and draft_calendar.dirty == DirtyType.MODIFY:
        raise Exception("There are uncommitted modifications in the draft calendar. Please commit or discard them before fetching new events.")
    
    try:
        # Fetch tasks from Todoist API
        todoist_tasks = get_tasks()
        
        if draft_calendar is not None and todoist_tasks:
            draft_calendar.update_event_batch(todoist_tasks)
            draft_calendar.dirty = DirtyType.FETCH
            return "Successfully added Todoist tasks to draft calendar"
        else:
            return "No Todoist tasks added to draft calendar"
        
    except Exception as e:
        print(f"Error fetching Todoist tasks: {str(e)}")
        raise


@tool
def fetch_todoist_task(task_id: int) -> CalendarEvent:
    """Fetch a task from Todoist by ID and convert it to CalendarEvent format.
    
    This function retrieves a task from the user's Todoist account and converts
    it to CalendarEvent format for integration with the calendar system.
    
    Args:
        task_id: Todoist task ID to fetch
        
    Returns:
        CalendarEvent object representing the Todoist task
        
    Raises:
        Exception: If authentication fails or API request fails
        
    Example:
        >>> event = get_todoist_task(123456)
        >>> print(event.title)
    """
    try:
        # Fetch task from Todoist API
        todoist_task = get_task(task_id)
        
        return todoist_task
        
    except Exception as e:
        print(f"Error fetching Todoist task: {str(e)}")
        raise

@tool
def create_todoist_task(content: str,
                       description: Optional[str] = None,
                       priority: Optional[Priority] = None,
                       due_date: Optional[datetime] = None,
                       labels: Optional[List[str]] = None) -> str:
    """Create a new task in Todoist.
    
    This function creates a new task in the user's Todoist account.
    The task can include a description, be assigned to a project,
    have a priority level, and have a due date.
    
    Args:
        content: Task content/title (required)
        description: Optional task description
        project_id: Optional project ID to add task to
        priority: Optional task priority (1-4, where 4 is highest)
        due_date: Optional due date in YYYY-MM-DD format
        labels: Optional list of label names
        
    Returns:
        Success message with task details
        
    Raises:
        Exception: If authentication fails or API request fails
        
    Example:
        >>> result = create_todoist_task("Buy groceries", due_string="tomorrow")
        >>> print(result)
    """
    try:       
        # Create task in Todoist
        task = CalendarEvent(
            title=content,
            description=description,
            priority=priority,
            due_date=due_date,
            tags=labels,
            category=EventCategory.SOLID
        )
        todoist_task = create_task(task)
        
        return f"Successfully created task: {task.title} (ID: {todoist_task.id})"
    except Exception as e:
        print(f"Error creating Todoist task: {str(e)}")
        raise