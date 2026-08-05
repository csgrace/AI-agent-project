"""Blackboard Calendar Tool for LangChain.

This tool fetches calendar data from Blackboard and converts it to CalendarEvent objects.
"""
from langchain.tools import tool
from .utils import (
    fetch_all_time_periods,
    convert_bb_events_to_calendar_events
)
from ...core.global_state import get_calendar, get_draft_calendar, get_object_store
from ...models.calendar.enums import DirtyType
import json
import os

CREDENTIALS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "credentials")
PROFILE_PATH = os.path.join(CREDENTIALS_DIR, "profile.json")


@tool
def fetch_blackboard_calendar() -> str:
    """Fetch calendar events from Blackboard using username and password.
    
    This tool logs into Blackboard with the provided credentials, retrieves calendar events
    from the user's personal calendar for the next 6 months, and converts them to CalendarEvent objects.
        
    Returns:
        str: Success message indicating whether Blackboard events were added to draft calendar.
            
    Raises:
        Exception: If login fails or data retrieval encounters errors.
    
    Example:
        >>> result = fetch_blackboard_calendar()
        >>> print(result)
        


    """
    
    
    try:
        with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
            profile = json.load(f)
            username = profile.get("username", "")
            password = profile.get("password", "")
    except (FileNotFoundError, json.JSONDecodeError):
        raise Exception("凭据文件未找到或格式错误，请先在个人中心配置 CAS 学号和密码。")
    
    # Check if there are uncommitted modifications
    draft_calendar = get_draft_calendar()
    if draft_calendar is not None and draft_calendar.dirty == DirtyType.MODIFY:
        raise Exception("There are uncommitted modifications in the draft calendar. Please commit or discard them before fetching new events.")
    
    print(f"Fetching Blackboard calendar for user: {username}")
    
    try:
        # Fetch raw calendar data from Blackboard
        bb_events = fetch_all_time_periods(username, password)
        
        # Convert to CalendarEvent objects
        calendar_events = convert_bb_events_to_calendar_events(bb_events)
        
        if draft_calendar is not None and calendar_events:
            draft_calendar.update_event_batch(calendar_events)
            draft_calendar.dirty = DirtyType.FETCH
            return "Successfully added Blackboard events to draft calendar"
        else:
            return "No Blackboard events added to draft calendar"
        
    except Exception as e:
        print(f"Error fetching Blackboard calendar: {str(e)}")
        raise Exception(f"Failed to fetch Blackboard calendar: {str(e)}")