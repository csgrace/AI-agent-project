"""Post-processing validator for course recommendation plans.

Provides automatic validation, conflict detection, and self-correction
to replace manual frontend-only checks used in the original implementation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    CourseMeeting,
    RecommendationPlan,
)


class PlanValidationResult:
    """Result of plan validation with issues and suggested fixes."""

    def __init__(self):
        self.is_valid: bool = True
        self.issues: List[str] = []
        self.fixes: Dict[str, Any] = {}
        self.warnings: List[str] = []

    def add_issue(self, issue: str, fix: Optional[Dict] = None):
        self.issues.append(issue)
        self.is_valid = False
        if fix:
            self.fixes.update(fix)

    def add_warning(self, warning: str):
        self.warnings.append(warning)


class PlanValidator:
    """Validates and auto-fixes generated course recommendation plans.
    
    This replaces the original implementation's approach of relying on
    manual frontend checks by providing automatic backend validation
    with a retry loop.
    """

    def __init__(
        self,
        min_credits: int = 0,
        max_credits: int = 18,
        completed_course_names: Optional[set[str]] = None,
    ):
        self.min_credits = min_credits
        self.max_credits = max_credits
        self.completed_names = completed_course_names or set()

    def validate(self, plan: RecommendationPlan) -> PlanValidationResult:
        """Run all validation checks on the plan.
        
        Returns a PlanValidationResult with is_valid flag, issues list,
        and suggested fixes for auto-correction.
        """
        result = PlanValidationResult()

        # 1. Credit range check
        self._validate_credits(plan, result)

        # 2. Duplicate / already-completed check
        self._validate_no_duplicates(plan, result)

        # 3. Time conflict detection
        self._validate_time_conflicts(plan, result)

        # 4. Meeting completeness check
        self._validate_meeting_completeness(plan, result)

        return result

    def auto_fix(self, plan: RecommendationPlan) -> Tuple[RecommendationPlan, List[str]]:
        """Apply automatic fixes based on validation issues.
        
        Returns the fixed plan and a list of applied fixes (warnings).
        """
        warnings: list[str] = []
        recs = list(plan.recommended_courses)
        meetings = list(plan.meetings)

        # Fix 1: Remove already-completed courses
        if self.completed_names:
            filtered = []
            removed = []
            for c in recs:
                norm = _normalize(c.course_name)
                if norm in self.completed_names:
                    removed.append(c.course_name)
                else:
                    filtered.append(c)
            if removed:
                recs = filtered
                warnings.append(f"已自动移除已修课程: {', '.join(removed)}")

        # Fix 2: Enforce credit limits (remove lowest-score first)
        total = sum(_safe_credits(c.credits) for c in recs)
        if total > self.max_credits:
            # Sort by score ascending, remove lowest until within limit
            scored = [(c, getattr(c, 'score', 50) or 50) for c in recs]
            scored.sort(key=lambda x: x[1])

            kept = []
            current = 0.0
            removed = []
            for course, score in reversed(scored):  # highest score first
                creds = _safe_credits(course.credits)
                if current + creds <= self.max_credits:
                    kept.append(course)
                    current += creds
                else:
                    removed.append(course.course_name)

            if removed:
                recs = list(reversed(kept))  # restore original order
                warnings.append(
                    f"根据学分上限({self.max_credits})自动移除: {', '.join(removed)}"
                )

        # Fix 3: Sync meetings with remaining courses
        remaining_names = {_normalize(c.course_name) for c in recs}
        meetings = [
            m for m in meetings
            if _normalize(m.course_name) in remaining_names
        ]

        # Fix 4: Remove time conflicts (keep first occurrence)
        seen_slots: dict[tuple, str] = {}
        clean_meetings = []
        conflict_count = 0
        for m in meetings:
            key = (m.day_of_week, m.start_slot, m.end_slot)
            if key in seen_slots:
                conflict_count += 1
                continue
            seen_slots[key] = m.course_name
            clean_meetings.append(m)

        if conflict_count:
            warnings.append(f"已自动解决 {conflict_count} 个时间冲突")
            meetings = clean_meetings

        # Build fixed plan
        plan.recommended_courses = recs
        plan.meetings = meetings
        plan.warnings = list(plan.warnings) + warnings

        return plan, warnings

    def _validate_credits(self, plan: RecommendationPlan, result: PlanValidationResult):
        total = sum(_safe_credits(c.credits) for c in plan.recommended_courses)
        if total > self.max_credits:
            result.add_issue(
                f"学分超限: 当前 {total:.1f} > 上限 {self.max_credits}",
                {"action": "trim_credits"}
            )
        elif total < self.min_credits:
            result.add_issue(
                f"学分不足: 当前 {total:.1f} < 下限 {self.min_credits}",
                {"action": "add_courses"}
            )

    def _validate_no_duplicates(self, plan: RecommendationPlan, result: PlanValidationResult):
        seen = set()
        for c in plan.recommended_courses:
            norm = _normalize(c.course_name)
            if norm in seen:
                result.add_issue(f"重复推荐: {c.course_name}")
            seen.add(norm)

        if self.completed_names:
            for c in plan.recommended_courses:
                if _normalize(c.course_name) in self.completed_names:
                    result.add_issue(
                        f"推荐已修课程: {c.course_name}",
                        {"action": "remove_completed"}
                    )

    def _validate_time_conflicts(self, plan: RecommendationPlan, result: PlanValidationResult):
        slots: dict[tuple, str] = {}
        for m in plan.meetings:
            key = (m.day_of_week, m.start_slot, m.end_slot)
            if key in slots:
                result.add_issue(
                    f"时间冲突: {m.course_name} 与 {slots[key]} "
                    f"(星期{m.day_of_week}, 第{m.start_slot}-{m.end_slot}节)",
                    {"action": "resolve_conflicts"}
                )
            else:
                slots[key] = m.course_name

    def _validate_meeting_completeness(self, plan: RecommendationPlan, result: PlanValidationResult):
        rec_names = {_normalize(c.course_name) for c in plan.recommended_courses}
        meeting_names = {_normalize(m.course_name) for m in plan.meetings}

        missing = rec_names - meeting_names
        if missing and rec_names:
            result.add_warning(
                f"以下课程缺少课表时间信息: {', '.join(missing)}"
            )


def _normalize(value: Optional[str]) -> str:
    """Normalize course name for comparison."""
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _safe_credits(value: Any) -> float:
    """Safely parse credits to float."""
    if value is None:
        return 3.0  # default assumption
    try:
        return float(value)
    except (TypeError, ValueError):
        return 3.0
