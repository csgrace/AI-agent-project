from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class TermInfo(BaseModel):
    term_id: str
    year: int
    semester: int
    label: str
    status: str = "unknown"


class CourseMeeting(BaseModel):
    course_id: Optional[str] = None
    course_name: str
    instructor: Optional[str] = None
    location: Optional[str] = None
    day_of_week: int = Field(ge=1, le=7)
    start_slot: int = Field(ge=1, le=11)
    end_slot: int = Field(ge=1, le=11)
    weeks: Optional[str] = None
    credits: Optional[float] = None
    source: str = "tis"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CourseSchedule(BaseModel):
    term: TermInfo
    meetings: List[CourseMeeting] = Field(default_factory=list)
    source: str = "tis"


class CompletedCourse(BaseModel):
    course_id: Optional[str] = None
    course_name: str
    term_id: Optional[str] = None
    grade: Optional[str] = None
    credits: Optional[float] = None
    status: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudentProfile(BaseModel):
    student_id: Optional[str] = None
    major: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    career_goal: Optional[str] = None
    desired_courses: List[str] = Field(default_factory=list)
    recommendation_note: Optional[str] = None
    completed_courses: List[CompletedCourse] = Field(default_factory=list)


class RecommendedCourse(BaseModel):
    course_id: Optional[str] = None
    course_name: str
    credits: Optional[float] = None
    score: float = 0.0
    reason: Optional[str] = None
    status: str = "scheduled"
    source: str = "system_supplement"


class GraduationCheck(BaseModel):
    status: str = "needs_review"
    summary: str = ""
    missing_courses: List[str] = Field(default_factory=list)


class RecommendationPlan(BaseModel):
    term: TermInfo
    recommended_courses: List[RecommendedCourse] = Field(default_factory=list)
    postponed_courses: List[RecommendedCourse] = Field(default_factory=list)
    meetings: List[CourseMeeting] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    rationale: str = ""
    graduation_check: GraduationCheck = Field(default_factory=GraduationCheck)
