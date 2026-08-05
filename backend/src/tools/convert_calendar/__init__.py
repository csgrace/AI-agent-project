"""Convert Calendar Tool for LangChain.

This module provides a tool for converting HTML table strings from academic calendar OCR
into structured event data using LLM-based extraction.
"""
from .tool import fetch_university_calendar

__all__ = ["fetch_university_calendar"]
