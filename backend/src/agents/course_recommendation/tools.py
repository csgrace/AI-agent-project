"""Tools for course recommendation agent.

Enables multi-step Agent loop: the agent can iteratively search courses,
check constraints, validate schedule, and refine recommendations.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.tools import tool


class CourseSearchIndex:
    """In-memory index for course lookups during agent execution."""

    def __init__(self, offerings: list[dict], completed_courses: list[dict]):
        self.offerings = offerings
        self.completed_lookup = {
            _normalize_name(c.get("course_name", "")): c
            for c in completed_courses
        }
        # Build name index for fuzzy matching
        self.name_index: dict[str, dict] = {}
        for o in offerings:
            name = _normalize_name(o.get("course_name", ""))
            self.name_index[name] = o

    def search(
        self,
        query: str,
        *,
        course_type: Optional[str] = None,
        min_credits: Optional[float] = None,
        max_credits: Optional[float] = None,
        day_of_week: Optional[int] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search courses with structured filters."""
        results = []
        query_norm = _normalize_name(query)
        for name, offering in self.name_index.items():
            # Fuzzy match
            if query_norm not in name and not any(
                token in name for token in query_norm.split() if len(token) > 1
            ):
                continue
            
            # Apply filters
            if course_type:
                otype = str(offering.get("课程种类", "")).strip().lower()
                if otype not in ("", "theory", "lab"):
                    otype = "theory"
                if otype != course_type:
                    continue
            
            credits = offering.get("credits")
            if min_credits is not None and (credits is None or float(credits) < min_credits):
                continue
            if max_credits is not None and (credits is None or float(credits) > max_credits):
                continue
            
            # Format result
            result = {
                "course_name": offering.get("course_name", ""),
                "course_id": offering.get("course_id") or offering.get("课程代码"),
                "credits": credits,
                "instructor": offering.get("instructor") or offering.get("教师"),
                "location": offering.get("location") or offering.get("上课地点"),
                "schedule": offering.get("上课信息", ""),
                "kind": offering.get("课程种类", "theory"),
            }
            results.append(result)
            if len(results) >= limit:
                break
        
        return results

    def check_prerequisite(self, course_name: str) -> dict:
        """Check if a course's prerequisites are met."""
        norm = _normalize_name(course_name)
        is_completed = norm in self.completed_lookup
        return {
            "course_name": course_name,
            "already_completed": is_completed,
            "can_take": not is_completed,
        }


def _normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


# Global index (set during request handling, reset after)
_search_index: Optional[CourseSearchIndex] = None


def set_search_index(index: CourseSearchIndex):
    """Set the global search index for current request."""
    global _search_index
    _search_index = index


def clear_search_index():
    """Clear the global search index after request completes."""
    global _search_index
    _search_index = None


@tool
def search_available_courses(
    query: str = "所有课程",
    course_type: Optional[str] = None,
    min_credits: Optional[float] = None,
    max_credits: Optional[float] = None,
    limit: int = 10,
) -> str:
    """搜索可用的课程。
    
    Args:
        query: 搜索关键词（课程名、教师名等），输入"所有课程"返回全部
        course_type: 课程类型过滤，可选 "theory"（理论课）或 "lab"（实验课）
        min_credits: 最低学分过滤
        max_credits: 最高学分过滤
        limit: 返回结果数量上限
    
    Returns:
        JSON 格式的搜索结果字符串
    """
    if _search_index is None:
        return "[]"
    
    results = _search_index.search(
        query,
        course_type=course_type,
        min_credits=min_credits,
        max_credits=max_credits,
        limit=limit,
    )
    
    import json
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool
def check_course_eligibility(course_name: str) -> str:
    """检查某门课是否已修或是否有资格选修。
    
    Returns:
        JSON 字符串，包含 already_completed 和 can_take 字段
    """
    if _search_index is None:
        return '{"error": "索引未初始化"}'
    
    result = _search_index.check_prerequisite(course_name)
    import json
    return json.dumps(result, ensure_ascii=False)


@tool
def validate_time_slots(meetings_json: str) -> str:
    """验证课表时间段是否有冲突。
    
    Args:
        meetings_json: JSON 数组，每项包含 day_of_week, start_slot, end_slot, course_name
    
    Returns:
        JSON 字符串，包含 conflicts 列表和 has_conflicts 布尔值
    """
    import json
    
    try:
        meetings = json.loads(meetings_json) if isinstance(meetings_json, str) else meetings_json
    except Exception:
        return '{"error": "无效的 JSON 输入"}'
    
    slots: Dict[Tuple[int, int, int], str] = {}
    conflicts: list[dict] = []
    
    for m in meetings:
        day = m.get("day_of_week")
        start = m.get("start_slot")
        end = m.get("end_slot")
        name = m.get("course_name", "未知")
        
        if day is None or start is None or end is None:
            continue
        
        # Check for conflicts: same day and overlapping time slots
        for slot_num in range(start, end + 1):
            key = (day, slot_num, slot_num)
            if key in slots:
                conflicts.append({
                    "type": "time_conflict",
                    "course_a": name,
                    "course_b": slots[key],
                    "day": day,
                    "slot": slot_num,
                })
            else:
                slots[key] = name
    
    return json.dumps({
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts,
        "total_meetings": len(meetings),
    }, ensure_ascii=False)


@tool
def calculate_credit_summary(courses_json: str) -> str:
    """计算推荐课程的总学分和各类别学分分布。
    
    Args:
        courses_json: JSON 数组，每项包含 course_name, credits, category
    
    Returns:
        JSON 字符串，包含 total_credits 和 by_category 学分分布
    """
    import json
    
    try:
        courses = json.loads(courses_json) if isinstance(courses_json, str) else courses_json
    except Exception:
        return '{"error": "无效的 JSON 输入"}'
    
    total = 0.0
    by_category: Dict[str, float] = {}
    
    for c in courses:
        credits = float(c.get("credits") or 0)
        category = c.get("category") or "其他"
        total += credits
        by_category[category] = by_category.get(category, 0) + credits
    
    return json.dumps({
        "total_credits": round(total, 1),
        "by_category": {k: round(v, 1) for k, v in by_category.items()},
        "course_count": len(courses),
    }, ensure_ascii=False)


def get_course_recommendation_tools() -> list:
    """Return the list of tools for the course recommendation agent."""
    return [
        search_available_courses,
        check_course_eligibility,
        validate_time_slots,
        calculate_credit_summary,
    ]
