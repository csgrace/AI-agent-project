"""Todoist Tool Utilities.

This module provides utility functions for interacting with Todoist API,
including OAuth authentication, fetching tasks, and creating tasks.
"""
import requests
import json
import os
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Any, Union, Optional
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.src.models.calendar.calendar_event import CalendarEvent
from backend.src.models.calendar.enums import EventSource, Priority, EventStatus, ColorTag, EventCategory, DirtyType
from backend.src.tools.todoist.todoist_utils import authenticate

current_dir = Path(__file__).resolve().parents[3]
TOKEN_FILE = str(current_dir / "credentials" / "todoist_credentials.json")

def create_task(task: CalendarEvent) -> Task:
    """创建任务"""
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            try:
                token_data = json.load(f)
            except json.JSONDecodeError:
                authenticate()
                with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
    except FileNotFoundError:
        authenticate()
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
    
    api = TodoistAPI(token_data['access_token'])
    todoist_task = api.add_task(content=task.title,
                        priority=transform_calendar_priority(task.priority),
                        due_datetime=task.deadline,
                        description=task.description,
                        labels=task.tags
                        )
    
    return todoist_task


def get_task(task_id: int) -> CalendarEvent:
    """获取任务"""
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            try:
                token_data = json.load(f)
            except json.JSONDecodeError:
                authenticate()
                with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
    except FileNotFoundError:
        authenticate()
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
    
    api = TodoistAPI(token_data['access_token'])
    task = api.get_task(task_id)
    print("...")
    print(task)
    print("...")
    calendar_event = task_to_calendar_event(task)
    return calendar_event

def get_tasks() -> List[CalendarEvent]:
    """获取所有任务"""
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            try:
                token_data = json.load(f)
            except json.JSONDecodeError:
                authenticate()
                with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
    except FileNotFoundError:
        authenticate()
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
    
    api = TodoistAPI(token_data['access_token'])
    tasks_paginator = api.get_tasks()
    print(tasks_paginator)
    
    calendar_events = []
    for tasks_page in tasks_paginator:
        for task in tasks_page:
            if hasattr(task, 'content'):
                calendar_events.append(task_to_calendar_event(task))
    
    return calendar_events

def task_to_calendar_event(task: Task) -> CalendarEvent:
    """将Todoist任务转换为CalendarEvent对象
    
    :param task: Todoist任务对象
    :return calendar_event: CalendarEvent对象
    """
    # 处理 due 属性
    end_time = None
    start_time = task.created_at.astimezone().replace(tzinfo=None)
    
    # 处理时区差异，确保两个时间对象类型一致
    def make_naive(dt):
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    
    start_time = make_naive(start_time)
    
    if hasattr(task, 'due') and task.due:
        if hasattr(task.due, 'datetime') and task.due.datetime:
            end_time = make_naive(task.due.datetime)
        elif hasattr(task.due, 'date') and task.due.date:
            due_date = task.due.date
            if isinstance(due_date, date) and not isinstance(due_date, datetime):
                end_time = datetime.combine(due_date, time(23, 59, 59))
            else:
                end_time = make_naive(due_date)
    
    # 确保 end_time 晚于 start_time
    if end_time and end_time <= start_time:
        # 如果 end_time 是今天且早于当前时间，设置为今天 23:59:59
        if end_time.date() == start_time.date():
            end_time = datetime.combine(start_time.date(), time(23, 59, 59))
    
    calendar_event = CalendarEvent(
        title=task.content,
        description=task.description,
        source=EventSource.PERSONAL,
        scheduled_start=start_time,
        deadline=end_time,
        duration=30,
        priority=transform_todoist_priority(task.priority),
        tags=task.labels,
        category=EventCategory.SOLID
    )
    return calendar_event


def transform_todoist_priority(priority: int) -> Priority:
    """将Todoist优先级转换为CalendarEvent优先级"""
    if priority == 3:
        return Priority.HIGH
    elif priority == 2:
        return Priority.MEDIUM
    elif priority == 1:
        return Priority.LOW
    else:
        return Priority.HIGH
    
def transform_calendar_priority(priority: Priority) -> int:
    """将CalendarEvent优先级转换为Todoist优先级"""
    if priority == Priority.HIGH:
        return 3
    elif priority == Priority.MEDIUM:
        return 2
    elif priority == Priority.LOW:
        return 1
    else:
        return 2


# def main():
#     with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
#         try:
#             token_data = json.load(f)
#         except json.JSONDecodeError:
#             authenticate()
#             token_data = json.load(f)

#         api = TodoistAPI(token_data['access_token'])
#         calendar_event = CalendarEvent(
#             title="TEST",
#             description="TEST",
#             source=EventSource.PERSONAL,
#             start_time=datetime.now(),
#             end_time=datetime.now() + timedelta(days=1),
#             priority=Priority.HIGH,
#             tags=["TEST"]
#         )
#         todoist_task = create_task(calendar_event)
#         print(f"Successfully created task: {todoist_task.content} (ID: {todoist_task.id})")
        
#         print(calendar_event)

# if __name__ == "__main__":
#     main()