"""Convert Calendar Tool for LangChain.

This tool converts HTML table strings from academic calendar OCR into structured event data.
"""
from typing import List
from langchain.tools import ToolRuntime, tool
from .utils import convert_html_calendar_to_events as utils_convert_html_calendar_to_events
from .utils import post_process_calendar_extraction
from ..ocr_calendar.utils import (
    download_calendar_image,
    ocr_image,
    extract_markdown_text,
    extract_holiday_tables,
)
from ...models.calendar.enums import DirtyType
from ...core.global_state import get_draft_calendar


def _emit_progress(runtime: ToolRuntime, stage: str, message: str) -> None:
    writer = runtime.stream_writer
    if writer is None:
        return

    writer(
        {
            "tool": "fetch_university_calendar",
            "stage": stage,
            "message": message,
        }
    )


@tool
def fetch_university_calendar(runtime: ToolRuntime) -> str:
    """Fetch university calendar events.

    This tool runs a pipeline with no input parameters:
    download SUSTech calendar image -> OCR -> extract holiday/teaching tables
    -> convert tables to calendar events -> write into draft calendar.
    
    Returns:
        str: Success message indicating whether events were added to draft calendar.
    
    Raises:
        Exception: If the extraction fails after retries or if the input is invalid.
    
    Example:
        >>> result = fetch_university_calendar()
        >>> print(result)
    """
    # Check if there are uncommitted modifications
    draft_calendar = get_draft_calendar()
    if draft_calendar is not None and draft_calendar.dirty == DirtyType.MODIFY:
        raise Exception("There are uncommitted modifications in the draft calendar. Please commit or discard them before fetching new events.")

    _emit_progress(runtime, "fetch", "Fetching academic calendar image from SUSTech website...")
    image_content, _ = download_calendar_image()

    _emit_progress(runtime, "ocr", "Running OCR on downloaded calendar image...")
    ocr_result = ocr_image(file_bytes=image_content, file_type=1)

    _emit_progress(runtime, "extract", "Extracting calendar tables from OCR result...")
    markdown_text = extract_markdown_text(ocr_result)
    html_tables: List[str] = extract_holiday_tables(markdown_text)

    if not html_tables:
        _emit_progress(runtime, "done", "No calendar tables found in OCR output")
        return "No calendar tables found for conversion"

    # Step 1: Convert HTML tables to extraction result
    _emit_progress(runtime, "convert", "Converting extracted tables to structured calendar events...")
    extraction_result = utils_convert_html_calendar_to_events(html_tables)
    
    # Step 2: Post-process to get full CalendarEvent objects
    _emit_progress(runtime, "post_process", "Post-processing extracted events...")
    calendar_events = post_process_calendar_extraction(extraction_result)
    
    # Step 3: Add events to global DRAFT_CALENDAR using batch update
    if draft_calendar is not None and calendar_events:
        draft_calendar.update_event_batch(calendar_events)
        draft_calendar.dirty = DirtyType.FETCH
        _emit_progress(runtime, "done", f"Imported {len(calendar_events)} events into draft calendar")
        return "Successfully added events to draft calendar"
    else:
        _emit_progress(runtime, "done", "No events were imported into draft calendar")
        return "No events added to draft calendar"