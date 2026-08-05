"""LangChain tool for OCR calendar processing."""
from langchain.tools import tool

from ...core.global_state import get_object_store

from .utils import (
    download_calendar_image,
    ocr_image,
    extract_markdown_text,
    extract_holiday_tables,
)


@tool
def get_calendar_tables() -> str:
    """Fetch academic calendar tables from SUSTech official website.

    This tool downloads the latest academic calendar image from the Southern University
    of Science and Technology (SUSTech) official website, performs OCR recognition to
    extract text content, and then extracts HTML tables containing academic schedule
    information as html tables.

    The extracted tables contain information like:
    - National holidays (国家节假日)
    - Major events (重大活动)
    - Undergraduate teaching schedules (教学安排-本科)
    - Graduate teaching schedules (教学安排-研究生)

    Pipeline: Download calendar image → OCR recognition → Extract holiday/academic tables.

    Returns:
        str: ObjectStore key pointing to ``List[str]`` HTML tables.

    Raises:
        Exception: If the calendar image cannot be downloaded, OCR processing fails,
            or network errors occur.
    """
    # 1. Download calendar image
    image_content, _ = download_calendar_image()

    # 2. OCR recognition
    ocr_result = ocr_image(file_bytes=image_content, file_type=1)
    markdown_text = extract_markdown_text(ocr_result)

    # 3. Extract holiday tables
    holiday_tables = extract_holiday_tables(markdown_text)

    object_store = get_object_store()
    output_key = object_store.put(
        holiday_tables,
        metadata={
            "kind": "html_table_list",
            "generated_by": "get_calendar_tables",
        },
    )
    return output_key
