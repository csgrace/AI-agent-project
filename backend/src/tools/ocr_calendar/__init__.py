"""OCR Calendar Tool for LangChain.

This module provides a LangChain-compatible tool for fetching and extracting
academic calendar information from SUSTech official website.
"""
from .tool import get_calendar_tables
# from .utils import (
#     download_calendar_image,
#     ocr_image,
#     extract_markdown_text,
#     extract_holiday_tables,
# )

__all__ = [
    "get_calendar_tables",
]
