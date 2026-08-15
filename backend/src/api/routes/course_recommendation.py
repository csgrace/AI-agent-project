from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr

from ...agents.registry import AgentRegistry
from ...services.course_recommendation import (
    CompletedCourse,
    CourseSchedule,
    RecommendationPlan,
    TermInfo,
    build_student_profile,
    fetch_completed_courses,
    fetch_term_list,
    fetch_term_schedule,
    fetch_course_offerings,
    infer_term_status,
)
from ...services.course_recommendation.tis_client import TisClientError
from ...services.course_recommendation.validator import PlanValidator
from ...agents.course_recommendation.tools import (
    CourseSearchIndex,
    set_search_index,
    clear_search_index,
    get_course_recommendation_tools,
)
from ...services.document_qa import get_document_qa_service
from ...rag_pipeline.llm_service import LLMService
from ...services.course_recommendation.recommendation_engine import (
    parse_all_schedules,
)


COURSE_RECOMMENDATION_AGENT_NAME = "course_recommendation"
COURSE_SCHEDULE_SOURCE = "backend/data/tis_download/course_schedule/"
FULL_COURSE_TABLE_SOURCE = (
    "backend/data/tis_download/full_course_table/all_courses_merged.json"
)
CURRICULUM_PLAN_INDEX_SOURCE = (
    "backend/storage/chunks.json + backend/storage/index.faiss"
)
IGNORED_SOURCES = (
    "backend/data/tis_download/completed_courses_detailed.json, "
    "backend/data/tis_download/academic_progress.json"
)

router = APIRouter(
    prefix="/api/course-recommendation",
    tags=["course-recommendation"],
)


class TermListResponse(BaseModel):
    terms: List[TermInfo] = Field(default_factory=list)
    message: Optional[str] = None


class ScheduleResponse(BaseModel):
    schedule: CourseSchedule


class CompletedCoursesResponse(BaseModel):
    courses: list[dict]


class RecommendationRequest(BaseModel):
    term_id: str
    major: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    career_goal: Optional[str] = None
    recommendation_note: Optional[str] = None
    min_credits: int = 0
    max_credits: int = 18
    use_llm: bool = True


class RecommendationResponse(BaseModel):
    plan: RecommendationPlan


class ExplanationRequest(BaseModel):
    term_id: str
    recommended_courses: List[dict]
    postponed_courses: List[dict] = Field(default_factory=list)
    user_major: Optional[str] = None
    user_note: Optional[str] = None


class ExplanationResponse(BaseModel):
    based_on: List[str] = Field(default_factory=list)
    matched_courses: List[dict] = Field(default_factory=list)
    requirement_summary: str = ''


class AnalysisResponse(BaseModel):
    major: str
    completed_credits: float
    required_credits: float
    completed_courses: List[str]
    suggested_courses: List[str]


class RefreshCompletedRequest(BaseModel):
    major: Optional[str] = None


class GraduationRequirementsResponse(BaseModel):
    major: str
    requirements: dict[str, Union[int, float, str]]


class CourseItem(BaseModel):
    name: str
    credits: Optional[float] = None


class AcademicStatusCategory(BaseModel):
    category: str
    required: Union[int, float, str]
    completed: Union[int, float]
    remaining: Union[int, float, str]
    courses: List[CourseItem]


class AcademicStatusResponse(BaseModel):
    major: str
    completed_credits: float
    required_credits: Union[float, str]
    course_count: int
    total_hours: float
    categories: List[AcademicStatusCategory]


GRADUATION_REQUIREMENT_CATEGORIES = [
    "思政类",
    "体育类",
    "军训类",
    "综合素质类",
    "美育类",
    "计算机类",
    "写作类",
    "外语类",
    "人文社科类",
    "数学类",
    "物理类",
    "化学类",
    "地生类",
    "专业导论类",
    "专业基础课",
    "专业核心课",
    "集中实践",
    "专业选修课",
    "国学类",
]


def _normalize_text(value: str | None) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    return text.lower().strip()


def _safe_float(value: object) -> Optional[float]:
    if value in (None, "", "?"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_requirement_values(raw_response: str) -> dict[str, Union[int, float, str]]:
    parsed = _parse_json_payload(raw_response)
    requirements: dict[str, Union[int, float, str]] = {}

    if isinstance(parsed, dict):
        for category in GRADUATION_REQUIREMENT_CATEGORIES:
            if category not in parsed:
                continue
            value = parsed.get(category)
            numeric_value = _safe_float(value)
            if numeric_value is not None:
                requirements[category] = int(numeric_value) if numeric_value.is_integer() else numeric_value
            elif value not in (None, ""):
                requirements[category] = str(value).strip()

    if requirements:
        return requirements

    for category in GRADUATION_REQUIREMENT_CATEGORIES:
        match = re.search(
            rf"{re.escape(category)}\s*[:：]?\s*(\d+(?:\.\d+)?)",
            raw_response,
        )
        if not match:
            continue
        numeric_value = float(match.group(1))
        requirements[category] = int(numeric_value) if numeric_value.is_integer() else numeric_value

    return requirements


def _fetch_graduation_requirements_sync(major: str) -> dict[str, Union[int, float, str]]:
    """获取专业毕业要求学分。
    
    优化：直接从完整培养方案 PDF 提取文本作为上下文，
    不再使用 RAG 切分召回（避免信息丢失）。
    """
    # 1. 尝试直接从完整 PDF 加载
    full_text = _load_full_curriculum_text(major)
    if full_text:
        categories_str = "、".join(GRADUATION_REQUIREMENT_CATEGORIES)
        prompt = f"""从以下完整的培养方案文本中提取各类课程的毕业学分要求。

<curriculum_plan>
{full_text}
</curriculum_plan>

<requested_categories>
{categories_str}
</requested_categories>

<output_format>
输出一个 JSON 对象，键为类别名称，值为数字（学分）。
只输出 JSON，不要其他内容。
</output_format>"""

        llm = LLMService()
        response = llm._chat_completion(
            prompt,
            temperature=0,
            max_tokens=500,
            label=f"grad_req_full_{major[:20]}",
            model=llm.lightweight_model_name,
            fallback_model=llm._lightweight_fallback_model,
        )
        result = _parse_requirement_values(response or "")
        if result:
            return result

    # 2. Fallback: 使用 RAG 检索
    qa = get_document_qa_service()
    categories_str = "、".join(GRADUATION_REQUIREMENT_CATEGORIES)
    query = (
        f"提取{major}专业本科培养方案中各类课程的毕业学分要求。"
        f"类别包括：{categories_str}。"
        "输出一个JSON对象，键为类别名称，值为数字（学分）。只输出JSON，不要其他内容。"
    )

    results = qa.search(query, k=5)
    if not results:
        return {}

    context = "\n\n".join(result.text for result in results)
    llm = LLMService()
    prompt = f"""基于以下培养方案资料，回答问题。
资料：
{context}

问题：{query}
"""

    response = llm._chat_completion(
        prompt,
        temperature=0,
        max_tokens=500,
        label=f"grad_req_{major[:20]}",
        model=llm.lightweight_model_name,
        fallback_model=llm._lightweight_fallback_model,
    )
    return _parse_requirement_values(response or "")


def _load_full_curriculum_text(major: str) -> Optional[str]:
    """加载完整培养方案 PDF 文本（不走 RAG）。
    
    培养方案 PDF 通常 15-20 页、约 6000 字符，
    现代 LLM 上下文窗口可以完整容纳。
    """
    backend_root = Path(__file__).resolve().parents[3]
    pdf_path = _find_program_pdf(backend_root, major)
    if not pdf_path:
        return None
    return _extract_pdf_text(pdf_path, max_pages=25, max_chars=50000)


def _find_program_pdf(backend_root: Path, major_name: str) -> Optional[Path]:
    arrangement_dir = backend_root / "data" / "course_arrangement"
    if not arrangement_dir.exists():
        return None

    normalized_major = re.sub(r"\s+", "", major_name or "")
    major_tokens = [token for token in re.split(r"[\s·、/-]+", normalized_major) if token]

    candidates: list[tuple[int, Path]] = []
    for pdf_path in arrangement_dir.rglob("*.pdf"):
        filename = pdf_path.name
        score = 0
        if "培养方案" in filename:
            score += 5
        if normalized_major and normalized_major in filename.replace(" ", ""):
            score += 20
        for token in major_tokens:
            if token and token in filename:
                score += 3
        if "本科人才培养方案" in filename:
            score += 2
        candidates.append((score, pdf_path))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    best_score, best_path = candidates[0]
    if best_score <= 0:
        return next(
            (path for _, path in candidates if "培养方案" in path.name),
            None,
        )
    return best_path

def _extract_pdf_text(pdf_path: Path, *, max_pages: int = 18, max_chars: int = 18000) -> str:
    try:
        import fitz
    except Exception:
        return ""

    try:
        with fitz.open(str(pdf_path)) as document:
            collected: list[str] = []
            for page_index, page in enumerate(document):
                if page_index >= max_pages:
                    break
                collected.append(page.get_text())
                if sum(len(chunk) for chunk in collected) >= max_chars:
                    break
            return "\n".join(collected)[:max_chars]
    except Exception:
        return ""


def _parse_json_payload(raw_text: str | None) -> object:
    if not raw_text:
        return None

    text = str(raw_text).strip()
    if not text:
        return None

    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, text, re.S)
        if not match:
            continue
        try:
            return json.loads(match.group(0))
        except Exception:
            continue
    return None


def _parse_term_order(term_id: str | None) -> tuple[int, int]:
    if not term_id:
        return (0, 0)

    text = str(term_id).strip()
    match = re.fullmatch(r"(\d{4})-(春|秋)", text)
    if match:
        year = int(match.group(1))
        semester = 1 if match.group(2) == "春" else 2
        return (year, semester)

    parts = text.split("-")
    if len(parts) >= 2 and parts[0].isdigit():
        year = int(parts[0])
        semester = 1 if "春" in parts[1] else 2
        return (year, semester)

    return (0, 0)


def _split_completed_courses_by_term(
    completed_courses: list[dict],
    target_term_id: str,
) -> dict[str, list[dict]]:
    target_key = _parse_term_order(target_term_id)

    prior_courses: list[dict] = []
    current_term_courses: list[dict] = []
    future_courses: list[dict] = []

    for course in completed_courses:
        course_key = _parse_term_order(str(course.get("term_id") or ""))
        if course_key < target_key:
            prior_courses.append(course)
        elif course_key == target_key:
            current_term_courses.append(course)
        else:
            future_courses.append(course)

    return {
        "prior_courses": prior_courses,
        "current_term_courses": current_term_courses,
        "future_courses": future_courses,
    }


def _load_completed_courses_from_schedule_dir(
    target_term_id: str,
) -> list[CompletedCourse]:
    backend_root = Path(__file__).resolve().parents[3]
    schedule_dir = backend_root / "data" / "tis_download" / "course_schedule"
    target_key = _parse_term_order(target_term_id)

    completed_courses: list[CompletedCourse] = []
    seen: set[tuple[str, str]] = set()

    if not schedule_dir.exists():
        return completed_courses

    schedule_files = sorted(schedule_dir.glob("*.json"))
    for json_file in schedule_files:
        term_id = json_file.stem
        if _parse_term_order(term_id) >= target_key:
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue

        meetings = payload.get("meetings", []) if isinstance(payload, dict) else []
        if not isinstance(meetings, list):
            continue

        for meeting in meetings:
            if not isinstance(meeting, dict):
                continue

            course_name = str(meeting.get("course_name") or "").strip()
            if not course_name:
                continue

            key = (term_id, course_name)
            if key in seen:
                continue
            seen.add(key)

            completed_courses.append(
                CompletedCourse(
                    course_id=str(meeting.get("course_id"))
                    if meeting.get("course_id") is not None
                    else None,
                    course_name=course_name,
                    term_id=term_id,
                    grade=None,
                    credits=None,
                    status="completed",
                    metadata={
                        "source": "course_schedule",
                        "instructor": meeting.get("instructor", ""),
                        "location": meeting.get("location", ""),
                        "weeks": meeting.get("weeks", ""),
                    },
                )
            )

    return completed_courses


def _load_curriculum_plan_context(major: str, *, limit: int = 5) -> list[dict]:
    if not major:
        return []

    try:
        qa = get_document_qa_service()
    except Exception:
        return []

    query = (
        f"{major} 专业 培养方案 课程类别 学分 专业基础课 专业核心课 专业选修课"
    )
    try:
        results = qa.search(query, k=limit)
    except Exception:
        return []

    context: list[dict] = []
    for result in results[:limit]:
        context.append(
            {
                "source_name": result.source_name,
                "chunk_id": result.chunk_id,
                "score": result.score,
                "text": result.text,
            }
        )
    return context


def _load_course_offerings_from_full_table(
    limit: Optional[int] = None,
) -> list[dict]:
    backend_root = Path(__file__).resolve().parents[3]
    courses_path = (
        backend_root
        / "data"
        / "tis_download"
        / "full_course_table"
        / "all_courses_merged.json"
    )

    if not courses_path.exists():
        return []

    try:
        with open(courses_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception:
        return []

    if not isinstance(loaded, list):
        return []

    offerings: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for course in loaded:
        if not isinstance(course, dict):
            continue

        course_name = str(
            course.get("课程名称") or course.get("name") or ""
        ).strip()
        teaching_class = str(course.get("教学班") or "").strip()
        course_code = str(course.get("课程代码") or "").strip()
        schedule_text = str(course.get("上课信息") or "").strip()

        if not course_name:
            continue

        schedules = parse_all_schedules(schedule_text) or [(0, 0, 0, "", "")]
        for index, schedule_item in enumerate(schedules):
            day_of_week, start_slot, end_slot, location, weeks = schedule_item
            dedupe_key = (
                course_name,
                teaching_class,
                f"{index}:{schedule_text}",
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            offerings.append(
                {
                    "course_id": course_code or None,
                    "course_name": course_name,
                    "teaching_class": teaching_class or None,
                    "credits": (
                        float(course["学分"])
                        if str(course.get("学分") or "").strip()
                        and str(course.get("学分") or "").strip() != "未知"
                        else None
                    ),
                    "instructor": str(course.get("教师") or "").strip() or None,
                    "location": (
                        location
                        or str(course.get("上课信息") or "").strip()
                        or None
                    ),
                    "day_of_week": day_of_week or None,
                    "start_slot": start_slot or None,
                    "end_slot": end_slot or None,
                    "weeks": weeks or None,
                    "source": "all_courses_merged.json",
                    # Keep original Chinese fields at top level for downstream lookups
                    "上课信息": schedule_text,
                    "课程种类": course.get("课程种类", ""),
                    "metadata": {
                        "课程类别": course.get("课程类别", ""),
                        "授课语言": course.get("授课语言", ""),
                        "开课院系": course.get("开课院系", ""),
                        "课程种类": course.get("课程种类", ""),
                        "上课信息": schedule_text,
                    },
                }
            )
            if limit is not None and len(offerings) >= limit:
                return offerings

    return offerings


def _normalize_course_key(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def extract_course_core_for_dedup(course_name: str) -> str:
    """Extract core course name for meeting dedup: strip parentheticals and normalize."""
    core = re.sub(r"[（(].*", "", course_name).strip()
    return re.sub(r"\s+", "", core).casefold()


def _get_offering_field(offering: dict, *english_names: str, chinese: str = "", default: object = None) -> object:
    """Get a field value from an offering dict, trying English names first, then Chinese."""
    for name in english_names:
        val = offering.get(name)
        if val not in (None, ""):
            return val
    if chinese:
        val = offering.get(chinese)
        if val not in (None, ""):
            return val
    return default


def _coerce_optional_int(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _parse_schedule_to_slots(schedule_str: str) -> list[tuple[int, int, int]]:
    """Parse '星期二第3-4节; 星期二第5-6节' → [(2,3,4), (2,5,6)]."""
    if not schedule_str:
        return []
    wd_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7}
    slots: list[tuple[int, int, int]] = []
    for m in re.finditer(r'星期([一二三四五六日])第(\d+)-(\d+)节', str(schedule_str)):
        slots.append((wd_map[m.group(1)], int(m.group(2)), int(m.group(3))))
    return slots


def _build_course_offering_lookup(offerings: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for offering in offerings:
        if not isinstance(offering, dict):
            continue
        # Pre-parse schedule info so sanitization can fill missing time slots
        raw_schedule = str(offering.get("上课信息") or "")
        all_slots = _parse_schedule_to_slots(raw_schedule)
        enriched = dict(offering)
        if all_slots:
            enriched["all_slots"] = all_slots
            # Backward compat: first slot as primary
            enriched["day_of_week"] = all_slots[0][0]
            enriched["start_slot"] = all_slots[0][1]
            enriched["end_slot"] = all_slots[0][2]
        # Support BOTH Chinese and English field names (PG search uses English, full table uses Chinese)
        candidate_fields = (
            "course_id", "course_name", "teaching_class",
            "课程代码", "课程名称", "教学班",
        )
        for field in candidate_fields:
            key = _normalize_course_key(offering.get(field))
            if not key:
                continue
            if key not in lookup:
                lookup[key] = enriched
            else:
                # Merge: union all_slots from theory+lab offerings of the same course
                existing = lookup[key]
                existing_slots = existing.get("all_slots") or []
                new_slots = enriched.get("all_slots") or []
                if new_slots:
                    merged: list[tuple[int, int, int]] = list(existing_slots)
                    for s in new_slots:
                        if s not in merged:
                            merged.append(s)
                    if len(merged) > len(existing_slots):
                        existing["all_slots"] = merged
    return lookup


def _find_matching_offering(
    meeting: dict,
    lookup: dict[str, dict],
) -> Optional[dict]:
    candidate_keys = [
        _normalize_course_key(meeting.get(field))
        for field in ("course_id", "course_name", "teaching_class",
                       "课程代码", "课程名称", "教学班", "KCH", "KCMC")
    ]
    candidate_keys = [key for key in candidate_keys if key]
    for key in candidate_keys:
        if key in lookup:
            return lookup[key]

    for key in candidate_keys:
        for lookup_key, offering in lookup.items():
            if key in lookup_key or lookup_key in key:
                return offering
    return None


def _enforce_credit_limits(
    parsed: dict,
    min_credits: int,
    max_credits: int,
    desired_courses: list[str],
    offerings: list[dict],
) -> dict:
    """Enforce credit limits on the generated plan.

    Drops non-user-required courses when total exceeds max_credits.
    Adds warnings when total falls below min_credits.
    """
    recs: list[dict] = parsed.get("recommended_courses") or []
    meetings: list[dict] = parsed.get("meetings") or []
    warnings: list[str] = list(parsed.get("warnings") or [])

    if not recs:
        return parsed

    # Identify user-desired courses (keep these)
    desired_norm = {_normalize_text(d) for d in desired_courses}

    def _is_desired(course: dict) -> bool:
        name = str(course.get("course_name") or "")
        core = re.sub(r"[（(].*", "", name).strip()
        norm = _normalize_text(name)
        core_norm = _normalize_text(core)
        return norm in desired_norm or core_norm in desired_norm

    # Deduplicate by course name (keep first occurrence)
    seen_names: set[str] = set()
    deduped: list[dict] = []
    for c in recs:
        name = str(c.get("course_name") or "").strip()
        if name and name not in seen_names:
            seen_names.add(name)
            deduped.append(c)

    # Separate desired vs extra courses
    desired_recs = [c for c in deduped if _is_desired(c)]
    extra_recs = [c for c in deduped if not _is_desired(c)]

    def _credits(course: dict) -> float:
        try:
            return float(course.get("credits") or 3.0)
        except (TypeError, ValueError):
            return 3.0

    # Always keep desired courses, then add extras up to max_credits
    final_recs: list[dict] = list(desired_recs)
    total = sum(_credits(c) for c in final_recs)

    trimmed = 0
    for c in extra_recs:
        credits = _credits(c)
        if total + credits > max_credits:
            trimmed += 1
            continue
        final_recs.append(c)
        total += credits

    if trimmed > 0:
        warnings.append(
            f"已根据学分上限 ({max_credits} 学分) 自动移除 {trimmed} 门课程，当前总学分 {total:.0f}"
        )

    if desired_recs and total > max_credits:
        # Even user-desired courses exceed the limit — keep them but warn
        warnings.append(
            f"用户要求的课程已达 {sum(_credits(c) for c in desired_recs):.0f} 学分，超出上限 {max_credits} 学分，已全部保留"
        )
        final_recs = desired_recs
        total = sum(_credits(c) for c in final_recs)

    if total < min_credits and min_credits > 0:
        warnings.append(
            f"当前推荐总学分 {total:.0f} 低于最低要求 {min_credits} 学分，可能无可选课程或已修课程过多"
        )

    # Sync meetings: fuzzy-match against final recommended courses
    def _name_match(meeting_name: str, course_names: set[str]) -> bool:
        mn = _normalize_text(meeting_name)
        if not mn:
            return False
        for cn in course_names:
            cn_norm = _normalize_text(cn)
            if not cn_norm:
                continue
            if mn == cn_norm or mn in cn_norm or cn_norm in mn:
                return True
            # Also try matching core name (before parentheses)
            cn_core = _normalize_text(re.sub(r"[（(].*", "", cn))
            if cn_core and (mn == cn_core or cn_core in mn or mn in cn_core):
                return True
        return False

    final_names = {str(c.get("course_name") or "").strip() for c in final_recs}
    final_meetings = [
        m for m in meetings
        if _name_match(str(m.get("course_name") or ""), final_names)
    ]

    # Build offering lookup for schedule promotion
    lookup = _build_course_offering_lookup(offerings)

    def _add_meetings_from_offering(course: dict, matched: dict) -> int:
        """Create meeting entries from a matched offering. Returns number created."""
        all_slots = matched.get("all_slots") or []
        if not all_slots:
            dow = matched.get("day_of_week")
            ss = matched.get("start_slot")
            es = matched.get("end_slot")
            if dow is not None and ss is not None and es is not None:
                all_slots = [(dow, ss, es)]
        if not all_slots:
            return 0
        created = 0
        for dow, ss, es in all_slots:
            meeting = dict(course)
            meeting["day_of_week"] = dow
            meeting["start_slot"] = ss
            meeting["end_slot"] = es
            meeting["location"] = (meeting.get("location")
                or _get_offering_field(matched, "location", chinese="上课地点")
                or "待定")
            meeting["instructor"] = (meeting.get("instructor")
                or _get_offering_field(matched, "instructor", "teacher", chinese="教师")
                or "待定")
            meeting["weeks"] = (meeting.get("weeks")
                or _get_offering_field(matched, "weeks", chinese="周次")
                or "1-16周")
            if meeting.get("status"):
                meeting["status"] = "scheduled"
            final_meetings.append(meeting)
            created += 1
        return created

    # Promote postponed courses that actually have schedule info
    postponed: list[dict] = parsed.get("postponed_courses") or []
    promoted = 0
    remaining_postponed: list[dict] = []
    for pc in postponed:
        pc_name = str(pc.get("course_name") or "").strip()
        matched = _find_matching_offering({"course_name": pc_name}, lookup)
        if matched:
            n = _add_meetings_from_offering(pc, matched)
            if n > 0:
                if pc not in final_recs:
                    final_recs.append(pc)
                promoted += 1
                continue
        remaining_postponed.append(pc)

    if promoted > 0:
        warnings.append(f"已将 {promoted} 门有课表的后置课程提升到课表中")

    # Fill/expand meetings: ensure every recommended course has ALL time slots from offering
    filled = 0
    expanded = 0
    for rc in final_recs:
        rc_name = str(rc.get("course_name") or "").strip()
        if not rc_name:
            continue
        matched = _find_matching_offering({"course_name": rc_name}, lookup)
        if not matched:
            continue
        all_slots = matched.get("all_slots") or []
        if not all_slots:
            # fallback to single slot
            dow = matched.get("day_of_week")
            ss = matched.get("start_slot")
            es = matched.get("end_slot")
            if dow is not None and ss is not None and es is not None:
                all_slots = [(dow, ss, es)]
        if not all_slots:
            continue

        # Check which slots already exist for this course
        existing_slots = {
            (m.get("day_of_week"), m.get("start_slot"), m.get("end_slot"))
            for m in final_meetings
            if str(m.get("course_name") or "").strip() == rc_name
        }
        if not existing_slots:
            # No meetings at all — create all from offering
            n = _add_meetings_from_offering(rc, matched)
            if n > 0:
                filled += 1
        else:
            # Has some meetings — add missing slots
            for dow, ss, es in all_slots:
                if (dow, ss, es) not in existing_slots:
                    meeting = dict(rc)
                    meeting["day_of_week"] = dow
                    meeting["start_slot"] = ss
                    meeting["end_slot"] = es
                    meeting["location"] = (meeting.get("location")
                        or _get_offering_field(matched, "location", chinese="上课地点")
                        or "待定")
                    meeting["instructor"] = (meeting.get("instructor")
                        or _get_offering_field(matched, "instructor", "teacher", chinese="教师")
                        or "待定")
                    meeting["weeks"] = (meeting.get("weeks")
                        or _get_offering_field(matched, "weeks", chinese="周次")
                        or "1-16周")
                    if meeting.get("status"):
                        meeting["status"] = "scheduled"
                    final_meetings.append(meeting)
                    expanded += 1

    if filled > 0:
        warnings.append(f"已为 {filled} 门课程自动补全课表时间（含多课节）")
    if expanded > 0:
        warnings.append(f"已为 {expanded} 个缺失课节补全时间")

    # Debug: log final state
    print(f"[CREDIT] final: {len(final_recs)} recs, {len(final_meetings)} meetings, total={total:.0f}cr")
    for m in final_meetings:
        print(f"  MEETING: {m.get('course_name','?')} | dow={m.get('day_of_week')} slot={m.get('start_slot')}-{m.get('end_slot')} | loc={m.get('location','?')}")
    for rc in final_recs:
        rc_name = str(rc.get("course_name") or "").strip()
        in_meeting = any(str(m.get("course_name") or "").strip() == rc_name for m in final_meetings)
        print(f"  REC: {rc_name} ({rc.get('credits','?')}cr) in_meeting={in_meeting}")

    # Dedup meetings: same course core name + same (day, start, end) → keep only one
    seen_meetings: set[tuple[str, int, int, int]] = set()
    deduped_meetings: list[dict] = []
    dedup_dropped = 0
    for m in final_meetings:
        core = extract_course_core_for_dedup(str(m.get("course_name") or ""))
        dow = _coerce_optional_int(m.get("day_of_week"))
        ss = _coerce_optional_int(m.get("start_slot"))
        es = _coerce_optional_int(m.get("end_slot"))
        if dow is None or ss is None or es is None:
            deduped_meetings.append(m)
            continue
        key = (core, dow, ss, es)
        if key in seen_meetings:
            dedup_dropped += 1
            continue
        seen_meetings.add(key)
        deduped_meetings.append(m)
    if dedup_dropped > 0:
        print(f"[MEETING] Dedup dropped {dedup_dropped} duplicate meeting(s)")
    final_meetings = deduped_meetings

    parsed["recommended_courses"] = final_recs
    parsed["meetings"] = final_meetings
    parsed["postponed_courses"] = remaining_postponed
    parsed["warnings"] = warnings

    return parsed


def _sanitize_recommendation_payload(
    parsed: dict,
    offerings: list[dict],
) -> dict:
    sanitized = dict(parsed)
    warnings = list(sanitized.get("warnings") or [])
    lookup = _build_course_offering_lookup(offerings)
    cleaned_meetings: list[dict] = []
    dropped_count = 0

    for meeting in sanitized.get("meetings") or []:
        if not isinstance(meeting, dict):
            dropped_count += 1
            continue

        candidate = dict(meeting)
        matched = _find_matching_offering(candidate, lookup)
        if matched:
            for field in (
                "course_id",
                "course_name",
                "instructor",
                "location",
                "weeks",
                "credits",
                "day_of_week",
                "start_slot",
                "end_slot",
            ):
                if candidate.get(field) in (None, ""):
                    matched_value = matched.get(field)
                    if matched_value not in (None, ""):
                        candidate[field] = matched_value
            if not candidate.get("metadata") and isinstance(
                matched.get("metadata"),
                dict,
            ):
                candidate["metadata"] = matched["metadata"]

        candidate["day_of_week"] = _coerce_optional_int(
            candidate.get("day_of_week")
        )
        candidate["start_slot"] = _coerce_optional_int(
            candidate.get("start_slot")
        )
        candidate["end_slot"] = _coerce_optional_int(
            candidate.get("end_slot")
        )

        if (
            candidate.get("course_name")
            and candidate.get("day_of_week") is not None
            and candidate.get("start_slot") is not None
            and candidate.get("end_slot") is not None
            and 1 <= candidate["day_of_week"] <= 7
            and 1 <= candidate["start_slot"] <= 11
            and 1 <= candidate["end_slot"] <= 11
            and candidate["start_slot"] <= candidate["end_slot"]
        ):
            cleaned_meetings.append(candidate)
        else:
            dropped_count += 1

    if dropped_count:
        warnings.append(
            f"已忽略 {dropped_count} 条缺少完整上课时间的 meetings，"
            "避免因空字段导致生成失败。"
        )

    sanitized["meetings"] = cleaned_meetings
    sanitized["warnings"] = warnings
    return sanitized


def _extract_desired_courses_from_note(
    note: Optional[str],
    offerings: list[dict],
) -> list[str]:
    if not note:
        return []

    candidates: list[str] = []
    for quoted in re.findall(r"《([^》]+)》|[“\"]([^”\"]+)[”\"]", note):
        candidate = (quoted[0] or quoted[1]).strip()
        if candidate:
            candidates.append(candidate)

    for part in re.split(r"[，,。；;、\n/]+", note):
        candidate = part.strip()
        if 1 < len(candidate) <= 40:
            candidates.append(candidate)

    matched_courses: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = _normalize_course_key(candidate)
        if not normalized_candidate:
            continue
        for offering in offerings:
            if not isinstance(offering, dict):
                continue
            for field in ("course_id", "course_name", "teaching_class"):
                value = str(offering.get(field) or "").strip()
                if not value:
                    continue
                normalized_value = _normalize_course_key(value)
                if (
                    normalized_candidate in normalized_value
                    or normalized_value in normalized_candidate
                ):
                    course_name = str(offering.get("course_name") or "").strip()
                    if course_name and course_name not in seen:
                        seen.add(course_name)
                        matched_courses.append(course_name)
                    break
            if len(matched_courses) >= 8:
                return matched_courses

    return matched_courses


def _extract_plan_search_terms(
    major: Optional[str],
    desired_courses: list[str],
    curriculum_plan_context: list[dict],
) -> set[str]:
    terms: set[str] = set()

    def _add_term(value: object) -> None:
        text = str(value or "").strip()
        if not text:
            return
        normalized = _normalize_course_key(text)
        if normalized:
            terms.add(normalized)

    _add_term(major)
    for course in desired_courses:
        _add_term(course)

    for chunk in curriculum_plan_context:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or "")
        if not text:
            continue

        for code in re.findall(r"\b[A-Z]{2,}\d{3}[A-Z0-9-]*\b", text):
            _add_term(code)

        for left, right in re.findall(r"《([^》]+)》|[“\"]([^”\"]+)[”\"]", text):
            _add_term(left or right)

    return terms


def _select_course_offerings_for_prompt(
    offerings: list[dict],
    *,
    major: Optional[str],
    desired_courses: list[str],
    curriculum_plan_context: list[dict],
    limit: int = 180,
) -> list[dict]:
    if not offerings:
        return []

    search_terms = _extract_plan_search_terms(
        major,
        desired_courses,
        curriculum_plan_context,
    )

    if not search_terms:
        return offerings[: min(limit, len(offerings))]

    scored: list[tuple[int, dict]] = []
    for offering in offerings:
        if not isinstance(offering, dict):
            continue

        score = 0
        fields = [
            _normalize_course_key(offering.get("course_id")),
            _normalize_course_key(offering.get("course_name")),
            _normalize_course_key(offering.get("teaching_class")),
            _normalize_course_key(offering.get("instructor")),
        ]
        fields = [field for field in fields if field]

        for term in search_terms:
            if any(term == field for field in fields):
                score += 8
                continue
            if any(term in field or field in term for field in fields):
                score += 4

        if score > 0:
            scored.append((score, offering))

    scored.sort(key=lambda item: item[0], reverse=True)
    prioritized = [offering for _, offering in scored]

    seen: set[tuple[str, str, str]] = set()
    selected: list[dict] = []
    for offering in prioritized + offerings:
        key = (
            str(offering.get("course_id") or "").strip(),
            str(offering.get("course_name") or "").strip(),
            str(offering.get("teaching_class") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(offering)
        if len(selected) >= limit:
            break

    return selected


def _format_curriculum_context(curriculum_plan_context: list[dict]) -> str:
    """Format curriculum plan context chunks into readable text."""
    if not curriculum_plan_context:
        return "暂无培养方案信息"
    parts = []
    for chunk in curriculum_plan_context[:5]:
        text = chunk.get("text", "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts) if parts else "暂无培养方案信息"


def _format_completed_summary(completed_courses: list) -> str:
    """Format completed courses into a readable summary."""
    if not completed_courses:
        return "无已修课程"
    lines = []
    for c in completed_courses[:20]:
        name = getattr(c, 'course_name', str(c))
        term = getattr(c, 'term_id', '')
        lines.append(f"- {name} ({term})" if term else f"- {name}")
    if len(completed_courses) > 20:
        lines.append(f"... 等共 {len(completed_courses)} 门课程")
    return "\n".join(lines)


def _build_recommendation_agent_prompt(
    req: RecommendationRequest,
    profile,
    schedule: CourseSchedule,
    offerings_for_prompt: list[dict],
    completed_course_sections: dict[str, list[dict]],
    curriculum_plan_context: list[dict],
    desired_courses: list[str],
) -> str:
    # Trim offerings to minimal fields to stay within model token limits
    trimmed_offerings: list[dict] = []
    for o in offerings_for_prompt:
        name = o.get("course_name") or o.get("课程名称") or ""
        sched = o.get("上课信息") or ""
        trimmed_offerings.append({
            "n": name,                                          # course_name
            "c": o.get("course_id") or o.get("课程代码") or "", # course_id
            "k": o.get("课程种类") or o.get("course_kind") or "theory",  # kind
            "cr": o.get("credits") or None,                     # credits
            "s": sched[:80] if sched else "",                   # schedule (truncated)
        })

    payload = {
        "request": {
            "term_id": req.term_id,
            "major": req.major,
            "interests": req.interests,
            "career_goal": req.career_goal,
            "recommendation_note": req.recommendation_note,
            "min_credits": req.min_credits,
            "max_credits": req.max_credits,
            "use_llm": req.use_llm,
        },
        "completed_courses_source": COURSE_SCHEDULE_SOURCE,
        "full_course_table_source": FULL_COURSE_TABLE_SOURCE,
        "curriculum_plan_index_source": CURRICULUM_PLAN_INDEX_SOURCE,
        "ignored_sources": IGNORED_SOURCES,
        "student_profile": profile.model_dump(mode="json"),
        "desired_courses_from_note": desired_courses,
        "target_term": schedule.term.model_dump(mode="json"),
        "target_term_schedule_present": bool(schedule.meetings),
        "target_term_schedule": schedule.meetings,
        "completed_courses_by_term": completed_course_sections,
        "curriculum_plan_context": curriculum_plan_context,
        "course_offerings": trimmed_offerings,
    }

    return (
        "你现在要生成课表推荐结果。"
        "不要调用本地推荐引擎，不要输出分析过程，不要输出 markdown。"
        "只根据下面的 JSON 输入生成一个严格符合 schema 的 JSON 对象。\n\n"
        "推荐原则：\n"
        f"1. 已修课程数据来自 {COURSE_SCHEDULE_SOURCE}。\n"
        f"2. 明确忽略 {IGNORED_SOURCES}，不要从这两份文件读取或推断已修课程。\n"
        "3. 避开已学课程时，只避开目标学期之前的课程；"
        "目标学期当期的课程不要当作需要避开的历史已修课。\n"
        "4. 如果目标学期已经有课表，也当作不存在，不要把它当成约束；"
        "你需要自己重新生成推荐。\n"
        "5. 先结合个人中心识别到的专业和 curriculum_plan_context 中的培养方案片段，"
        "再决定专业基础课、专业核心课、专业选修课和通识课的取舍。\n"
        "5.0 student_profile.major 必须以个人中心保存的专业为准；如果个人中心专业"
        "已修改，要以最新值为准，不要写死某个固定专业。\n"
        "5.1 如果 student_profile.desired_courses 或 desired_courses_from_note 不为空，"
        "要优先推荐这些课程，只要它们能在 course_offerings 中找到。\n"
        "5.2 判断已修课程或培养方案当前学期课程是否命中时，不要求逐字完全对应；"
        "可以按课程代码、课程核心名、中文/英文别名和简称做模糊匹配。\n"
        f"6. full_course_table_source 是 {FULL_COURSE_TABLE_SOURCE}，"
        "course_offerings 代表全校可选课程，包含教学班、教师、上课信息和学分。"
        "查找全校课表课程时，不要求逐字完全对应，可以根据课程代码、课程名片段、"
        "中文/英文别名、教师名和教学班号做模糊匹配。\n"
        "6.1 如果某门课的课程种类既有'theory'又有'lab'，你只能选择一节'theory'和一节'lab'，或者不选这门课。\n"
        "6.1a 注意：部分 lab 教学班的「上课信息」已同时包含理论课和实验课的时间（因为学生选了该 lab 班后需要同时上理论+实验），"
        "此时 lab 条目本身就有多个时间段（如「周二第3-4节 智华楼207; 周二第5-6节 智华楼508机房」），"
        "你仍然按照 6.1 的规则选择对应的 theory + lab 各一条。\n"
        "6.1b 生成 meetings 时，如果 theory 和 lab 条目有重复的时间段（同一个 day_of_week + 同一个 start_slot + 同一个 end_slot），只保留一条。\n"
        "6.2 如果 student_profile.desired_courses 或 desired_courses_from_note 不为空，"
        "要优先推荐这些课程，只要它们能在全校课表中找到。\n"
        "7. meetings 里的每一项都必须有完整的 day_of_week、start_slot、end_slot；"
        "如果某门课没有完整时间，就不要输出这条 meeting，在 warnings 中说明。\n"
        "8. 如果课程信息不完整，在 warnings 中说明。\n"
        "9. 课程名称必须来自输入中的 course_offerings，不要编造课程。\n"
        "10. recommended_courses 和 postponed_courses 都可以为空，"
        "但 reason / rationale / warnings 要诚实。\n"
        f"11. 【重要】必须严格遵守学分要求：总共推荐课程的学分必须在 {req.min_credits} 到 {req.max_credits} 之间。"
        f"如果可选课程不足以达到最低学分，在 warnings 中说明。"
        f"课程不足时，可以从同专业大类（计算机、电子、自动化等）或相近方向推荐补充课程。\n\n"
        "输入 JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
    )


def _split_category_name(category_name: str) -> str:
    normalized = re.sub(r"\s+", "", str(category_name or ""))
    if any(token in normalized for token in ("基础", "通识", "平台")):
        return "专业基础课"
    if any(token in normalized for token in ("核心", "主干")):
        return "专业核心课"
    if any(token in normalized for token in ("选修", "拓展", "实践", "专题")):
        return "专业选修课"
    return "其他"


def _fallback_course_classification(completed_courses: list[dict]) -> dict[str, list[dict]]:
    grouped = {
        "专业基础课": [],
        "专业核心课": [],
        "专业选修课": [],
    }

    for course in completed_courses:
        course_name = str(course.get("course_name") or course.get("name") or "").strip()
        normalized_name = _normalize_text(course_name)
        target_category = "专业选修课"
        if any(keyword in normalized_name for keyword in ("高等数学", "线性代数", "大学物理", "程序设计", "基础", "导论")):
            target_category = "专业基础课"
        elif any(keyword in normalized_name for keyword in ("操作系统", "数据库", "计算机网络", "软件工程", "算法", "编译", "人工智能")):
            target_category = "专业核心课"

        grouped[target_category].append(course)

    return grouped


@router.get("/terms", response_model=TermListResponse)
def list_terms():
    try:
        terms = fetch_term_list()
    except TisClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not terms:
        import datetime

        current_year = datetime.datetime.now().year
        current_month = datetime.datetime.now().month
        current_semester = 1 if current_month < 8 else 2

        terms = []
        for offset in range(8):
            year = current_year + (offset // 2)
            semester = current_semester + (offset % 2)
            if semester > 2:
                semester = 1
                year += 1

            term_id = f"{year}-{'春' if semester == 1 else '秋'}"
            status = "current" if offset == 0 else "future"
            terms.append(
                TermInfo(
                    term_id=term_id,
                    year=year,
                    semester=semester,
                    label=f"{year}年{'春季' if semester == 1 else '秋季'}学期",
                    status=status,
                )
            )

    enriched = []
    for term in terms:
        term.status = infer_term_status(term)
        enriched.append(term)

    current_index = next((i for i, t in enumerate(enriched) if t.status == "current"), 0)
    future_terms = enriched[current_index:]

    return TermListResponse(terms=future_terms)


@router.get("/schedule", response_model=ScheduleResponse)
def get_schedule(term_id: str):
    try:
        schedule = fetch_term_schedule(term_id)
        return ScheduleResponse(schedule=schedule)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"schedule fetch failed: {str(e)}"
        )


@router.get("/completed", response_model=CompletedCoursesResponse)
def get_completed_courses():
    try:
        courses = fetch_completed_courses()
    except TisClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return CompletedCoursesResponse(courses=[c.model_dump() for c in courses])


@router.post("/refresh-completed")
def refresh_completed_courses(req: RefreshCompletedRequest):
    """强制重新生成已修课程数据。"""
    try:
        fetch_completed_courses(refresh=True, major=req.major or "")
        return {"status": "success", "message": "已修课程数据已刷新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/graduation-requirements",
    response_model=GraduationRequirementsResponse,
)
def get_graduation_requirements(
    major: str = Query(..., description="专业名称，如：计算机科学与技术"),
):
    """根据专业从培养方案文档中提取各类课程的毕业要求学分。"""
    try:
        requirements = _fetch_graduation_requirements_sync(major)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not requirements:
        raise HTTPException(status_code=404, detail="未找到相关培养方案文档或无法解析毕业要求学分")

    return GraduationRequirementsResponse(major=major, requirements=requirements)


@router.get("/academic-status", response_model=AcademicStatusResponse)
async def get_academic_status(
    major: str = Query("", description="专业名称"),
    refresh: bool = Query(False, description="是否强制刷新已修课程数据"),
):
    """获取学业现状：数值字段取自 academic_progress.json，课程明细取自 completed_courses_detailed.json。"""
    if refresh:
        fetch_completed_courses(refresh=True, major=major)

    completed_courses = fetch_completed_courses(major=major)

    requirements: dict[str, Union[int, float, str]] = {}
    category_completed: dict[str, float] = {}
    category_courses: dict[str, list[CourseItem]] = {}
    total_required: Union[float, str] = "?"
    total_completed: Union[float, str] = "?"
    category_remaining: dict[str, Union[int, float, str]] = {}

    # If there is a local academic_progress.json produced by TIS, use it for all numeric values.
    try:
        backend_root = Path(__file__).resolve().parents[3]
        progress_path = backend_root / 'data' / 'tis_download' / 'academic_progress.json'
        if progress_path.exists():
            with open(progress_path, 'r', encoding='utf-8') as fh:
                prog = json.load(fh)
            overall = prog.get('整体修读进度') or {}
            total_required_parsed = _safe_float(overall.get('要求修读学分'))
            total_completed_parsed = _safe_float(overall.get('已修读学分'))
            if total_required_parsed is not None:
                total_required = round(float(total_required_parsed), 1)
            if total_completed_parsed is not None:
                total_completed = round(float(total_completed_parsed), 1)

            category_list = prog.get('课程列表') or []
            for item in category_list:
                cat_name = str(item.get('学分类别') or '').strip()
                if not cat_name:
                    continue
                req = item.get('要求学分')
                comp = item.get('已完成学分')
                rem = item.get('未完成学分')
                try:
                    if req is not None and req != '':
                        requirements[cat_name] = float(req)
                except Exception:
                    pass

                try:
                    if comp is not None and comp != '':
                        category_completed[cat_name] = float(comp)
                except Exception:
                    category_completed[cat_name] = 0.0

                try:
                    if rem is not None and str(rem).strip() != '':
                        category_remaining[cat_name] = float(rem)
                except Exception:
                    pass
    except Exception:
        pass

    if not requirements:
        try:
            requirements = _fetch_graduation_requirements_sync(major)
        except Exception:
            requirements = {}

    # Course lists still come from completed_courses_detailed.json.
    for course in completed_courses:
        course_type = str(course.metadata.get("课程类型") or "").strip()
        if not course_type:
            continue

        category_courses.setdefault(course_type, []).append(
            CourseItem(
                name=course.course_name,
                credits=course.credits,
            )
        )

    all_categories = set(requirements.keys()) | set(category_completed.keys())
    fixed_order = [
        "思政类",
        "体育类",
        "军训类",
        "综合素质类",
        "美育类",
        "计算机类",
        "写作类",
        "外语类",
        "人文社科类",
        "数学类",
        "物理类",
        "化学类",
        "地生类",
        "专业导论类",
        "专业基础课",
        "专业核心课",
        "集中实践",
        "专业选修课",
        "国学类",
    ]
    sorted_categories = [cat for cat in fixed_order if cat in all_categories] + [
        cat for cat in all_categories if cat not in fixed_order
    ]

    if total_required == "?":
        numeric_requirements = [value for value in requirements.values() if isinstance(value, (int, float))]
        total_required = round(float(sum(numeric_requirements)), 1) if numeric_requirements else "?"

    if total_completed == "?":
        numeric_completed = [value for value in category_completed.values() if isinstance(value, (int, float))]
        total_completed = round(float(sum(numeric_completed)), 1) if numeric_completed else "?"

    categories_response: list[AcademicStatusCategory] = []
    for category in sorted_categories:
        required = requirements.get(category, "?")
        completed = round(category_completed.get(category, 0.0), 1)
        remaining: Union[float, str]
        if category in category_remaining and isinstance(category_remaining[category], (int, float)):
            remaining = round(float(category_remaining[category]), 1)
        elif isinstance(required, (int, float)):
            remaining = max(0.0, float(required) - float(completed))
        else:
            remaining = "?"

        categories_response.append(
            AcademicStatusCategory(
                category=category,
                required=required,
                completed=completed,
                remaining=remaining,
                courses=category_courses.get(category, []),
            )
        )

    return AcademicStatusResponse(
        major=major,
        completed_credits=total_completed,
        required_credits=total_required,
        course_count=len(completed_courses),
        total_hours=round(total_completed * 16.0, 1),
        categories=categories_response,
    )


@router.post("/plan", response_model=RecommendationResponse)
def plan_courses(req: RecommendationRequest):
    try:
        schedule = fetch_term_schedule(req.term_id)
    except TisClientError:
        year_part, semester_part = req.term_id.split("-")
        schedule = CourseSchedule(
            term=TermInfo(
                term_id=req.term_id,
                year=int(year_part),
                semester=1 if "春" in semester_part else 2,
                label=f"{year_part}年{semester_part}学期",
                status="future",
            ),
            meetings=[],
            source="generated",
        )

    completed = _load_completed_courses_from_schedule_dir(req.term_id)

    try:
        offerings = fetch_course_offerings(req.term_id)
    except TisClientError:
        offerings = []

    # Always supplement with full course table to ensure desired courses are present.
    # Use (course_id, teaching_class) as dedup key to keep theory+lab variants.
    full_table = _load_course_offerings_from_full_table()
    if full_table:
        existing_ids = {
            (str(o.get("course_id") or ""), str(o.get("课程名称") or o.get("course_name") or "").strip(),
             str(o.get("teaching_class") or o.get("教学班") or "").strip())
            for o in offerings
        }
        for course in full_table:
            key = (str(course.get("course_id") or ""),
                   str(course.get("课程名称") or course.get("course_name") or "").strip(),
                   str(course.get("teaching_class") or course.get("教学班") or "").strip())
            if key not in existing_ids:
                offerings.append(course)
                existing_ids.add(key)

    # Dedup by (课程名称, 课程种类): for courses with both theory and lab,
    # keep the best offering of EACH kind. Treat missing/empty 课程种类 as "theory".
    # Supports both Chinese (full table) and English (PG search) field names.
    by_name_kind: dict[tuple[str, str], list[dict]] = {}
    for o in offerings:
        name = str(o.get("课程名称") or o.get("course_name") or "").strip()
        if not name:
            continue
        kind = str(o.get("课程种类") or o.get("course_kind") or "").strip().lower()
        if kind not in ("theory", "lab"):
            kind = "theory"
        by_name_kind.setdefault((name, kind), []).append(o)

    deduped_offerings: list[dict] = []
    dropped = 0
    for (_name, _kind), items in by_name_kind.items():
        if len(items) == 1:
            deduped_offerings.extend(items)
            continue
        # Count time slots for each offering
        def _slot_count(offering: dict) -> int:
            raw = str(offering.get("上课信息") or "")
            return len(re.findall(r'星期[一二三四五六日]第\d+-\d+节', raw))
        max_slots = max(_slot_count(item) for item in items)
        # Keep only the first (best) offering per (name, kind) to avoid merging
        # slots from unrelated teaching classes
        best = [item for item in items if _slot_count(item) == max_slots]
        kept = best[:1]
        dropped += len(items) - len(kept)
        deduped_offerings.extend(kept)

    if dropped > 0:
        print(f"[OFFER] Dropped {dropped} course(s) with fewer time slots (same name+kind)")
        offerings = deduped_offerings

    print(f"[OFFER] {len(offerings)} courses (PG search + full table + dedup)")

    curriculum_plan_context = _load_curriculum_plan_context(req.major or "")
    desired_courses = _extract_desired_courses_from_note(
        req.recommendation_note,
        offerings,
    )

    try:
        if req.min_credits < 0 or req.max_credits < 0:
            raise HTTPException(status_code=400, detail="学分上下限必须为非负数")
        if req.min_credits > req.max_credits:
            raise HTTPException(status_code=400, detail="最低学分不能大于最高学分")

        profile = build_student_profile(
            completed,
            major=req.major,
            interests=req.interests,
            career_goal=req.career_goal,
            desired_courses=desired_courses,
            recommendation_note=req.recommendation_note,
        )

        completed_course_sections = _split_completed_courses_by_term(
            [course.model_dump(mode="json") for course in profile.completed_courses],
            req.term_id,
        )
        offerings_for_prompt = _select_course_offerings_for_prompt(
            offerings,
            major=req.major,
            desired_courses=desired_courses,
            curriculum_plan_context=curriculum_plan_context,
            limit=80,
        )

        agent = AgentRegistry.get(COURSE_RECOMMENDATION_AGENT_NAME)
        if agent is None:
            raise HTTPException(
                status_code=503,
                detail="Course recommendation agent not initialized",
            )

        if not AgentRegistry.acquire(COURSE_RECOMMENDATION_AGENT_NAME):
            raise HTTPException(
                status_code=429,
                detail="Course recommendation agent is busy. Please wait.",
            )

        # Set up search index for agent tools (enables multi-step agent loop)
        search_index = CourseSearchIndex(offerings, [c.model_dump() for c in completed])
        set_search_index(search_index)

        try:
            # Build structured XML prompt for better instruction following
            curriculum_text = _load_full_curriculum_text(req.major or "") or _format_curriculum_context(curriculum_plan_context)
            completed_summary = _format_completed_summary(completed)
            
            prompt = _build_recommendation_agent_prompt(
                req,
                profile,
                schedule,
                offerings_for_prompt,
                completed_course_sections,
                curriculum_plan_context,
                desired_courses,
            )
            # Try with fallback models if agent's primary model fails
            raw_response = ""
            cascade_models = list(dict.fromkeys(
                ["qwen3.7-plus", "qwen3.6-plus", "qwen3.7-max",
                 "qwen3-235b-a22b-instruct-2507", "qwen-plus-2025-07-28",
                 "qwen3.7-flash-2026-07-15", "deepseek-v4-flash-0731", "deepseek-r1"]
            ))
            for attempt, fallback_model in enumerate(cascade_models):
                if attempt > 0:
                    print(f"[AGENT] Retrying with fallback model {fallback_model}...")
                    try:
                        from langchain_openai import ChatOpenAI
                        from ...services.llm_config import LLMConfig
                        cfg = LLMConfig.get_instance()
                        new_llm = ChatOpenAI(
                            model=fallback_model,
                            api_key=SecretStr(cfg.api_key or ""),
                            base_url=cfg.base_url,
                            temperature=0,
                        )
                        agent.reinitialize(new_llm)
                    except Exception as e:
                        print(f"[AGENT] Failed to reinitialize with {fallback_model}: {e}")
                        continue
                try:
                    result = agent.run_turn(prompt)
                    raw_response = result.get("reply", "") if isinstance(result, dict) else ""
                    parsed = _parse_json_payload(raw_response)
                    if isinstance(parsed, dict) and parsed.get("recommended_courses"):
                        break  # Success!
                except Exception as e:
                    last_error = e
                    print(f"[AGENT] Model {fallback_model} failed: {e}")
                    raw_response = ""
        finally:
            AgentRegistry.release(COURSE_RECOMMENDATION_AGENT_NAME)
            clear_search_index()  # Clean up search index after request

        parsed = _parse_json_payload(raw_response)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"Agent response is not valid JSON: {raw_response[:500]}"
            )

        parsed.setdefault("term", schedule.term.model_dump(mode="json"))
        parsed = _sanitize_recommendation_payload(parsed, offerings)

        # ── Enforce credit limits ──────────────────────────────────
        parsed = _enforce_credit_limits(
            parsed,
            min_credits=req.min_credits,
            max_credits=req.max_credits,
            desired_courses=desired_courses,
            offerings=offerings,
        )

        plan = RecommendationPlan.model_validate(parsed)

        # ── Post-processing validation & auto-fix ───────────────────
        completed_names = {c.course_name for c in completed}
        validator = PlanValidator(
            min_credits=req.min_credits,
            max_credits=req.max_credits,
            completed_course_names=completed_names,
        )
        validation_result = validator.validate(plan)
        if not validation_result.is_valid:
            print(f"[VALIDATOR] Issues found: {validation_result.issues}")
            plan, fix_warnings = validator.auto_fix(plan)
            plan.warnings.extend(fix_warnings)
            print(f"[VALIDATOR] Auto-fix applied, final plan: {len(plan.recommended_courses)} courses")
    except Exception as e:
        import os
        import traceback

        log_dir = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            '..',
            'logs',
        )
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, 'course_recommendation_error.log')
            with open(log_path, 'a', encoding='utf-8') as fh:
                fh.write('---\n')
                fh.write('Exception when generating course plan:\n')
                traceback.print_exc(file=fh)
                fh.write('\n')
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to generate course plan (logged to "
                "backend/logs/course_recommendation_error.log): "
                f"{type(e).__name__}: {e}"
            ),
        )

    return RecommendationResponse(plan=plan)


@router.post("/explain", response_model=ExplanationResponse)
def explain_recommendation(req: ExplanationRequest):
    from ...rag_pipeline.llm_service import LLMService

    llm = LLMService()

    postponed_keys = {
        str(course.get('course_code') or course.get('course_id') or '')
        or str(course.get('course_name') or '')
        for course in req.postponed_courses
        if isinstance(course, dict)
    }

    # ── 优先复用 plan 中已有 reason，仅对缺失的课程批量生成 ──
    courses_need_llm: list[tuple[int, dict]] = []  # (index, course_dict)
    matched: list[dict] = [None] * len(req.recommended_courses)  # placeholder

    for idx, rc in enumerate(req.recommended_courses):
        course_name = rc.get('course_name', '')
        existing_reason = (rc.get('reason') or '').strip()
        if existing_reason and len(existing_reason) >= 4:
            # Already has a meaningful reason from the agent — use it directly
            reason = existing_reason
        else:
            courses_need_llm.append((idx, rc))
            reason = "该课程匹配您的兴趣和培养方案要求。"

        course_key = str(rc.get('course_code') or rc.get('course_id') or '') or course_name
        if course_key in postponed_keys or course_name in postponed_keys:
            reason = f"{reason.strip()} 该课程为后置名单，无具体课表时间。"

        matched[idx] = {
            'course_code': rc.get('course_code') or rc.get('course_id'),
            'course_name': course_name,
            'credits': rc.get('credits'),
            'status': rc.get('status') or ('postponed' if course_key in postponed_keys or course_name in postponed_keys else 'scheduled'),
            'source': rc.get('source') or ('system_supplement' if rc.get('status') == 'postponed' else 'user_required'),
            'reason': reason.strip(),
        }

    # ── 批量生成缺失的理由（一次 LLM 调用） ──
    if courses_need_llm:
        course_list_lines = "\n".join(
            f"{i+1}. 《{rc.get('course_name', '')}》"
            for i, (_, rc) in enumerate(courses_need_llm)
        )
        batch_prompt = f"""
请为以下每门课程分别生成一条推荐理由（每条20字以内，有理有据）：
- 学生专业：{req.user_major or '计算机科学与技术'}
- 用户需求：{req.user_note or '无'}
- 培养方案参考：专业基础课、核心课等要求

课程列表：
{course_list_lines}

输出 JSON 对象，键为课程名称，值为理由字符串。只输出 JSON，不要其他内容。
示例：{{"课程A": "核心课程，匹配培养方案要求", "课程B": "与兴趣高度相关，建议选修"}}
"""
        batch_result = llm._chat_completion(
            batch_prompt,
            temperature=0.2,
            max_tokens=100 + 60 * len(courses_need_llm),
            label="explain_reason_batch",
            model=llm.lightweight_model_name,
            fallback_model=llm._lightweight_fallback_model,
        )
        if batch_result:
            import json
            import re
            try:
                match = re.search(r"\{.*\}", batch_result, re.S)
                if match:
                    reason_map = json.loads(match.group(0))
                    for idx, rc in courses_need_llm:
                        course_name = rc.get('course_name', '')
                        generated = (reason_map.get(course_name) or '').strip()
                        if generated:
                            matched[idx]['reason'] = generated
            except Exception:
                pass  # fallback: keep default reason

    requirement_summary = f"基于您的要求：{req.user_note or '无'}{'，已排除冲突时间段' if req.user_note else ''}，结合已修课程和培养方案，推荐以下课程。"

    return ExplanationResponse(
        based_on=['已修课程分析', '培养方案匹配', '时间冲突检测'],
        matched_courses=matched,
        requirement_summary=requirement_summary,
    )


@router.get("/analysis", response_model=AnalysisResponse)
def get_student_analysis():
    """获取学生学业现状分析"""
    try:
        completed = fetch_completed_courses()
        total_credits = float(sum(c.credits for c in completed if c.credits))

        backend_root = Path(__file__).parents[3]
        program_path = backend_root / "data" / "course_arrangement" / "计算机系培养方案.json"

        suggested_courses = ["软件工程", "数据库系统", "操作系统"]
        if program_path.exists():
            try:
                import json
                with open(program_path, "r", encoding="utf-8") as f:
                    program_data = json.load(f)
                if isinstance(program_data, dict):
                    for key in ("suggested_courses", "recommended_courses", "必修", "选修"):
                        value = program_data.get(key)
                        if isinstance(value, list) and value:
                            suggested_courses = [str(item) for item in value[:3]]
                            break
            except Exception:
                pass

        return {
            "major": "计算机科学与工程系",
            "completed_credits": total_credits,
            "required_credits": 140,
            "completed_courses": [c.course_name for c in completed[:20]],
            "suggested_courses": suggested_courses,
        }
    except Exception as e:
        return {"error": str(e)}


