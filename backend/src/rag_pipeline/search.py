"""Semantic search helpers for document QA."""

from __future__ import annotations

from typing import Any

from .models import SearchResult
from .service import get_document_qa_service


def semantic_search(query: str, k: int = 3, course_scope: str | None = None) -> list[SearchResult]:
    return get_document_qa_service().search(query, k=k, course_scope=course_scope)


def semantic_search_dicts(query: str, k: int = 3, course_scope: str | None = None) -> list[dict[str, Any]]:
    return [result.to_dict() for result in semantic_search(query, k=k, course_scope=course_scope)]


def semantic_search_for_courses(query: str, k: int = 30) -> list[dict[str, Any]]:
    """专门从课程索引中搜索，返回课程信息字典"""
    service = get_document_qa_service()
    results = service.search(query, k=k, course_scope="course_kb")

    courses: list[dict[str, Any]] = []
    for result in results:
        text = result.text
        course: dict[str, Any] = {}
        for line in text.split("\n"):
            if "课程名称:" in line:
                course["course_name"] = line.split("课程名称:")[1].split("|")[0].strip()
            elif "课程代码:" in line:
                course["course_id"] = line.split("课程代码:")[1].split("|")[0].strip()
            elif "学分:" in line:
                try:
                    course["credits"] = float(line.split("学分:")[1].split("|")[0].strip())
                except Exception:
                    course["credits"] = 3.0
            elif "教师:" in line:
                course["teacher"] = line.split("教师:")[1].split("|")[0].strip()
            elif "上课信息:" in line:
                course["schedule"] = line.split("上课信息:")[1].split("|")[0].strip()
        if course.get("course_name"):
            courses.append(course)

    return courses
