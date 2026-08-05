"""Event extraction models for LLM structured output."""
from typing import List, Optional
from pydantic import BaseModel, Field


class SingleEventExtract(BaseModel):
    """Single event extraction structure for LLM structured output."""
    
    title: str = Field(description="Event title, e.g., '本科生期末复习考试周'")
    start_date: str = Field(description="Start date in YYYY-mm-dd format, e.g., '2025-12-29'")
    end_date: Optional[str] = Field(description="End date in YYYY-mm-dd format, e.g., '2026-01-90'. Same to start date if the event only has a single date.")


class CalendarExtractionResult(BaseModel):
    """Complete extraction result containing multiple events from academic calendar."""
    
    events: List[SingleEventExtract] = Field(
        description="List of all events extracted from the academic calendar HTML"
    )
