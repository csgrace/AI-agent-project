"""Blackboard Calendar Tool Utilities.

This module provides utility functions for fetching calendar data from Blackboard
and converting it to CalendarEvent objects.
"""
import requests
import urllib3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Union, Optional
from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.enums import EventSource, Priority, EventStatus, ColorTag, EventCategory

# Suppress urllib3 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Path to cookies file
CREDENTIALS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "credentials")
COOKIES_FILE = os.path.join(CREDENTIALS_DIR, "cookies.json")


def read_cookies() -> Dict[str, str]:
    """Read cookies from cookies.json file.
    
    Returns:
        Dictionary of cookies, or empty dict if file doesn't exist or is invalid
    """
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
                print("Loaded cookies from file")
                return cookies
        else:
            print("Cookies file not found")
            return {}
    except Exception as e:
        print(f"Error reading cookies file: {e}")
        return {}


def write_cookies(cookies: Dict[str, str]) -> None:
    """Write cookies to cookies.json file.
    
    Args:
        cookies: Dictionary of cookies to write
    """
    try:
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        print("Cookies saved to file")
    except Exception as e:
        print(f"Error writing cookies file: {e}")


def cas_login(sid: str, pwd: str) -> Dict[str, str]:
    """Login to SUSTech CAS and get session cookies.
    
    Args:
        sid: SUSTech student ID
        pwd: Password for CAS login
        
    Returns:
        Dictionary of cookies for authenticated session
        
    Raises:
        Exception: If login fails
    """
    print("Testing CAS connection...")
    
    try:
        session = requests.Session()
        session.verify = False
        
        login_url = "https://cas.sustech.edu.cn/cas/login?service=https%3A%2F%2Fbb.sustech.edu.cn%2Fwebapps%2Fbb-sso-BBLEARN%2Fexecute%2FcasLogin"
        
        response = session.get(login_url)
        execution = response.text.split('name="execution" value="')[1].split('"')[0]
        data = {
            'username': sid,
            'password': pwd,
            'execution': execution,
            '_eventId': 'submit',
            'geolocation': ''
        }
        session.post(login_url, data=data)
        
        session.get("https://bb.sustech.edu.cn")
        
        # Get cookies dict
        cookies = session.cookies.get_dict()
        
        # Save cookies to file
        write_cookies(cookies)
        
    except Exception as ex:
        raise Exception(f"Cannot login to CAS, please check your network connection or credentials: {ex}")
    
    return cookies



def fetch_blackboard_calendar_data(start_timestamp: int, end_timestamp: int, username: str, password: str) -> List[Dict]:
    """Fetch Blackboard calendar data for 6 months in one request.
    
    Args:
        start_timestamp: Start timestamp in milliseconds
        end_timestamp: End timestamp in milliseconds
        username: Blackboard username
        password: Blackboard password
        
    Returns:
        List of raw calendar events from Blackboard
    """
    # First try to use existing cookies from file
    cookies = read_cookies()
    
    # Fetch calendar data
    url = "https://bb.sustech.edu.cn/webapps/calendar/calendarData/selectedCalendarEvents"
    
    params = {
        "start": start_timestamp,
        "end": end_timestamp,
        "course_id": "",
        "mode": "personal"
    }
    
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://bb.sustech.edu.cn/webapps/calendar/viewMyBb?globalNavigation=false",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    try:
        response = requests.get(
            url, 
            params=params, 
            headers=headers, 
            cookies=cookies,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            # Extract events from response
            print(f"from {format_timestamp_to_date(start_timestamp)} to {format_timestamp_to_date(end_timestamp)}: {len(data)} events were fetched")
            
            return data
        else:
            print(f"Request failed with status code: {response.status_code}")
            print("Trying to login via CAS...")

            cookies = cas_login(username, password)
            # Try again with new cookies
            response = requests.get(
                url, 
                params=params, 
                headers=headers, 
                cookies=cookies,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                print(f"from {format_timestamp_to_date(start_timestamp)} to {format_timestamp_to_date(end_timestamp)}: {len(data)} events were fetched after login")
                return data
            else:
                print(f"Request failed again with status code: {response.status_code}")
                return []
                
    except requests.exceptions.RequestException as e:
        print(f"Request exception: {e}")
        print("Trying to login via CAS...")
        # Login via CAS if request fails
        try:
            cookies = cas_login(username, password)
            # Try again with new cookies
            response = requests.get(
                url, 
                params=params, 
                headers=headers, 
                cookies=cookies,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                print(f"from {format_timestamp_to_date(start_timestamp)} to {format_timestamp_to_date(end_timestamp)}: {len(data)} events were fetched after login")
                return data
            else:
                print(f"Request failed after login with status code: {response.status_code}")
                return []
        except Exception as ex:
            print(f"Login failed: {ex}")
            return []
    
def fetch_all_time_periods(username: str, password: str) -> List[Dict]:
    """
    Fetch calendar data for all time periods in Blackboard
    
    Args:
        username: Blackboard username
        password: Blackboard password
        
    Returns:
        List of raw calendar events from Blackboard
    """
    all_events = []
    
    time_periods = [
            {"start": 1772294400000, "end": 1775923200000, "name": "2026-02-28 to 2026-04-11"},
            {"start": 1774713600000, "end": 1778342400000, "name": "2026-03-28 to 2026-05-09"},
            {"start": 1777132800000, "end": 1780761600000, "name": "2026-04-25 to 2026-06-06"},
            {"start": 1780156800000, "end": 1783785600000, "name": "2026-05-30 to 2026-07-11"},
            {"start": 1782576000000, "end": 1786204800000, "name": "2026-06-27 to 2026-08-08"},
            {"start": 1784995200000, "end": 1788624000000, "name": "2026-07-25 to 2026-09-05"},
        ]
    
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://bb.sustech.edu.cn/webapps/calendar/viewMyBb?globalNavigation=false",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }
    
    for i, period in enumerate(time_periods, 1):
        print(f"[{i}/{len(time_periods)}] ", end="")
        event = fetch_blackboard_calendar_data(
            period['start'], 
            period['end'], 
            username, 
            password
        )
        all_events.extend(event)
    
    print(f"\n {len(all_events)} events were fetched from Blackboard")
    
    # Remove duplicates from the list
    unique_events = remove_duplicate_events(all_events)
    
    # Sort events by start time
    sorted_events = sort_events_by_time(unique_events)
    
    return sorted_events


def convert_bb_events_to_calendar_events(bb_events: List[Dict]) -> List[CalendarEvent]:
    """Convert list of Blackboard events to CalendarEvent objects.
    
    Args:
        bb_events: List of event dictionaries from Blackboard API
        
    Returns:
        List of CalendarEvent objects
    """
    calendar_events = []
    
    for bb_event in bb_events:
        try:
            title = bb_event.get('title', 'No Title')
            course_name = bb_event.get('calendarNameLocalizable', {}).get('rawValue', 'Unknown')
            title = f"{course_name} - {title}"
            
            deadline = datetime.fromisoformat(bb_event.get('end'))
            duration = 120  # 2 hours
            scheduled_start = deadline - timedelta(minutes=duration)
            
            if scheduled_start >= deadline:
                continue
            
            priority = Priority.MEDIUM
            status = EventStatus.PENDING
            
            calendar_event = CalendarEvent(
                title=title,
                source=EventSource.BLACKBOARD,
                scheduled_start=scheduled_start,
                deadline=deadline,
                duration=duration,
                priority=priority,
                status=status,
                category=EventCategory.SCHEDULABLE
            )
            
            calendar_events.append(calendar_event)
            
        except Exception as e:
            print(f"Error converting event: {e}")
            continue
    
    print(f"Converted {len(calendar_events)} events to CalendarEvent format")
    for event in calendar_events:
        print(event.to_json())
    
    return calendar_events


def format_timestamp_to_date(timestamp: Union[int, float, str, None]) -> str:
    """
    Convert milliseconds timestamp to date string, supporting multiple input formats
    
    Args:
        timestamp: Timestamp in milliseconds, or string in ISO format
        
    Returns:
        Date string in ISO format, if input is None
    """
    if timestamp is None:
        return "unknown"
    
    try:
        if isinstance(timestamp, str):
            if 'T' in timestamp or '-' in timestamp:
                return timestamp
        
        timestamp_ms = parse_timestamp(timestamp)
        if timestamp_ms:
            return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
    except:
        pass
    
    return str(timestamp)

def remove_duplicate_events(events: List[Dict]) -> List[Dict]:
    """
    Remove duplicate events from the list of events
    
    Args:
        events: List of event dictionaries
        
    Returns:
        List of unique event dictionaries, with first occurrence of each event retained
    """
    seen = set()
    unique_events = []
    
    for event in events:
        key = get_event_key(event)
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    duplicates_removed = len(events) - len(unique_events)
    if duplicates_removed > 0:
        print(f"{duplicates_removed} duplicate events were removed from {len(events)} events")  
    
    return unique_events

def sort_events_by_time(events: List[Dict]) -> List[Dict]:
    """
    Sort events by start time
    
    Args:
        events: List of event dictionaries
        
    Returns:
        List of event dictionaries sorted by start time
    """
    def get_sort_key(event):
        """
        Get sort key for event, preferring start time over end time
        
        Args:
            event: Dictionary of event data
        
        Returns:
            Sort key value, if start time is available, otherwise float('inf') if no start time is found
        """
        
        start = event.get('start', event.get('startTime', event.get('start_date', event.get('startDate'))))
        
        if start:
            parsed = parse_timestamp(start)
            if parsed is not None:
                return parsed
        
        # No start time found, place at the end
        return float('inf')
    
    return sorted(events, key=get_sort_key)

def get_event_key(event: Dict) -> str:
    """
    Generate unique identifier for event, used for deduplication
    
    Args:
        event: Dictionary of event data
        
    Returns:
        Unique identifier string, combining title, start time, and end time
    """
    # Get title from event data, preferring title over name, summary, subject, or empty string if none
    title = event.get('title', event.get('name', event.get('summary', event.get('subject', ''))))
    
    # Get start time from event data, preferring start over end, or empty string if none
    start = event.get('start', event.get('startTime', event.get('start_date', event.get('startDate', ''))))
    if start:
        start_parsed = parse_timestamp(start)
        start_str = str(start_parsed) if start_parsed else str(start)
    else:
        start_str = ''
    
    # Get end time from event data, preferring end over start, or empty string if none
    end = event.get('end', event.get('endTime', event.get('end_date', event.get('endDate', ''))))
    if end:
        end_parsed = parse_timestamp(end)
        end_str = str(end_parsed) if end_parsed else str(end)
    else:
        end_str = ''
    

    return f"{title}|{start_str}|{end_str}"

def parse_timestamp(timestamp: Union[int, float, str, None]) -> Union[int, float, None]:
    """
    Smartly parse timestamp, supporting multiple input formats
    
    Args:
        timestamp: Timestamp in milliseconds, or string in ISO format
        
    Returns:
        Parsed timestamp in milliseconds, if input is None
    """
    if timestamp is None:
        return None
    
    # If timestamp is already a number, return it as is
    if isinstance(timestamp, (int, float)):
        return timestamp
    
    # If timestamp is a string, try to parse it as a number
    if isinstance(timestamp, str):
        # Try to parse as a number (milliseconds timestamp string)
        if timestamp.isdigit():
            return int(timestamp)
        
        # Try to parse as ISO format (ISO 8601 format)
        try:
            # Handle common date formats
            if 'T' in timestamp:
                # ISO format: 2026-03-28T10:00:00
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.timestamp() * 1000
            else:
                # Common date format: 2026-03-28
                dt = datetime.strptime(timestamp, '%Y-%m-%d')
                return dt.timestamp() * 1000
        except:
            pass
    
    return None