"""Convert Calendar Tool for LangChain.

This tool converts HTML table strings from academic calendar OCR into structured event data.
"""
from datetime import datetime
from typing import List, Optional
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ...models.calendar.extraction import CalendarExtractionResult
from ...models.calendar.calendar_event import CalendarEvent
from ...models.calendar.enums import EventCategory, EventSource
from ...services.llm_config import LLMConfig

# ── Lazy LLM initializer ──────────────────────────────────────────────
_cached_llm: Optional[ChatOpenAI] = None
_cached_version: int = -1


def _get_llm() -> Optional[ChatOpenAI]:
    """Get a lightweight-tier ChatOpenAI, rebuilding if the config changed."""
    global _cached_llm, _cached_version
    cfg = LLMConfig.get_instance()
    version = cfg.get_version()
    if _cached_llm is None or _cached_version < version:
        _cached_llm = cfg.build_chat_model(tier="lightweight")
        _cached_version = version
    return _cached_llm

# ==================== System Prompt ====================
SYSTEM_PROMPT = """You are a data extraction specialist. Your task is to extract structured event information from HTML tables containing academic calendar data.

Given a list of HTML table strings, extract all events with their titles and date ranges.

Rules:
1. Each event is a string which date on the head and title on the tail such as "1月12日-2月23日 本科生寒假".
2. Parse each HTML table and extract event information. Some units have multiple events, such as "1月12日-2月23日本科生寒假1月12日-2月23日本科生春季学期积分选课". You need to divide them into two different events.
3. Convert Chinese dates to YYYY-mm-dd format
3. Handle date ranges (e.g., "1月12日-2月23日" → start: "2026-01-12", end: "2026-02-23")
4. Handle single dates (e.g., "2月17日" → start: "2026-02-17", end: 2026-02-17)
5. For ambiguous date ranges like "3月-4月", fill in the full month range (e.g., "2026-03-01" to "2026-04-30")
6. Infer the year based on the academic calendar context especially the event titles(eg., title "2026级硕士研究生招生复试与录取" means this calendar is for 2026 year.)
7. Return all extracted events in the specified structured format
8. If a date spans across years (e.g., "12月29日-1月9日"), you need to follow the sub-rules to infer whether it start from the past year or end in the next year.
    - If most months in the table is less than 7, it means it is the first half year. This date started from the past year.
    - If most months in the table is greater or equal than 7, it means it is the second half year. This date end in the next year.
9. Follow the structure output guidance, don't mix other information like markdown in the output.
"""

def convert_html_calendar_to_events(html_tables: List[str]) -> CalendarExtractionResult:
    """Convert HTML table strings to structured calendar events.
    
    This tool takes a list of HTML table strings (typically from academic calendar OCR)
    and extracts structured event information including titles and date ranges.
    
    Args:
        html_tables: A list of HTML table strings containing academic calendar information.
            Each string represents a complete HTML table with headers and rows.
            The tables typically contain information like:
            - National holidays (国家节假日)
            - Major events (重大活动)
            - Undergraduate teaching schedules (教学安排-本科)
            - Graduate teaching schedules (教学安排-研究生)
    
    Returns:
        CalendarExtractionResult: Structured extraction result containing all events
            with titles, start dates, and end dates in YYYY-mm-dd format.
    
    Raises:
        Exception: If the extraction fails after retries or if the input is invalid.
    
    Example:
        >>> tables = ["<table>...</table>", "<table>...</table>"]
        >>> result = convert_html_tables_to_events(tables)
        >>> print(f"Extracted {len(result.events)} events")
        >>> for event in result.events:
        ...     print(f"{event.title}: {event.start_date} to {event.end_date}")
    """
    
    parser = PydanticOutputParser(pydantic_object=CalendarExtractionResult)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\n{format_instructions}"),
        ("user", "{input}")
    ]).partial(format_instructions=parser.get_format_instructions())
    
    current_llm = _get_llm()
    if current_llm is None:
        raise RuntimeError("LLM not available — no API key configured")
    chain = prompt | current_llm | parser
    
    all_events = []
    for i, table in enumerate(html_tables):
        # print(f"处理表格 {i+1}/{len(html_tables)}")
        result = chain.invoke({"input": table})
        all_events.extend(result.events)
        # print(f"表格 {i+1} 提取了 {len(result.events)} 个事件，累计 {len(all_events)} 个")
        # print(result)
    
    # print(f"总共提取了 {len(all_events)} 个事件")
    return CalendarExtractionResult(events=all_events)


def post_process_calendar_extraction(
    extraction_result: CalendarExtractionResult
) -> List[CalendarEvent]:
    """Post-process extraction result and convert to full CalendarEvent objects.
    
    This function takes the extraction result containing simplified events and
    converts them to complete CalendarEvent objects with all required fields.
    
    Args:
        extraction_result: The extraction result containing simplified events.
    
    Returns:
        List[CalendarEvent]: List of complete CalendarEvent objects.
    """
    from datetime import timedelta
    
    calendar_events = []
    
    for event in extraction_result.events:
        # Parse start date
        start_date = datetime.strptime(event.start_date, "%Y-%m-%d")
        scheduled_start = start_date.replace(hour=0, minute=0, second=0)
        
        # Parse end date (use start_date if end_date is None)
        if event.end_date:
            end_date = datetime.strptime(event.end_date, "%Y-%m-%d")
        else:
            end_date = start_date
        deadline = end_date.replace(hour=23, minute=59, second=59)
        
        # Calculate duration in minutes
        duration = int((deadline - scheduled_start).total_seconds() / 60)
        
        # Create CalendarEvent
        calendar_event = CalendarEvent(
            title=event.title,
            source=EventSource.UNIVERSITY,
            scheduled_start=scheduled_start,
            deadline=deadline,
            duration=duration,
            category=EventCategory.BACKGROUND
        )
        
        calendar_events.append(calendar_event)
    
    return calendar_events

