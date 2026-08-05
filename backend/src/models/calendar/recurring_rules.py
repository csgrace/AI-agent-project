"""Recurring rule model for repeating events."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator


class RecurringRule(BaseModel):
    """
    Rules for recurring events.
    Supports daily, weekly, monthly, yearly recurrence.
    """

    # Recurrence frequency
    frequency: str = Field(..., description="daily/weekly/monthly/yearly")

    # Recurrence interval (every N days/weeks/months/years)
    interval: int = Field(default=1, ge=1, description="Recurrence interval")

    # End conditions (either until date or count)
    until: Optional[datetime] = Field(None, description="Recur until this date")
    count: Optional[int] = Field(None, ge=1, description="Number of occurrences")

    # Weekly specific: which days of week
    weekdays: Optional[List[int]] = Field(
        None,
        description="Days of week (0=Monday, 6=Sunday) for weekly recurrence"
    )

    # Monthly specific: day of month (1-31)
    month_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month")

    # ========== Field Validators ==========

    @field_validator('frequency')
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        """Validate frequency value."""
        allowed = ['daily', 'weekly', 'monthly', 'yearly']
        if v not in allowed:
            raise ValueError(f'frequency must be one of {allowed}')
        return v

    @field_validator('weekdays')
    @classmethod
    def validate_weekdays(cls, v: Optional[List[int]], info) -> Optional[List[int]]:
        """
        Validate weekdays for weekly recurrence.
        info.data contains all validated fields.
        """
        # Access other fields via info.data
        frequency = info.data.get('frequency')

        # For weekly recurrence, weekdays must be specified
        if frequency == 'weekly' and not v:
            raise ValueError('Weekly recurrence must specify weekdays')

        # Validate each weekday is in range 0-6
        if v:
            for day in v:
                if day < 0 or day > 6:
                    raise ValueError('Weekday must be between 0 (Monday) and 6 (Sunday)')
        return v

    # ========== Model Validator (for cross-field validation) ==========

    @model_validator(mode='after')
    def validate_end_condition(self) -> 'RecurringRule':
        """
        Validate that only one end condition is set.
        Runs after all field validators.
        """
        if self.until is not None and self.count is not None:
            raise ValueError('Cannot specify both until and count')
        return self

    # ========== Methods ==========