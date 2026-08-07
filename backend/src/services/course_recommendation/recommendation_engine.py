from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from ...rag_pipeline.llm_service import LLMService
from .models import (
    CompletedCourse,
    CourseMeeting,
    GraduationCheck,
    RecommendedCourse,
    RecommendationPlan,
    StudentProfile,
    TermInfo,
)


def _normalize(text: str) -> str:
    return "".join(
        ch.lower() for ch in text if ch.isalnum() or ch.isspace()
    ).strip()


def _course_name_aliases(name: str) -> set[str]:
    raw = str(name or "").strip()
    if not raw:
        return set()

    aliases: set[str] = set()
    chunks = [raw, extract_core_name(raw)]
    chunks.extend(re.split(r"[（(）)\-/·、,，;；\s]+", raw))

    for chunk in chunks:
        normalized = _normalize(str(chunk or ""))
        if normalized:
            aliases.add(normalized)
    return aliases


def _course_name_matches(name: str, aliases: set[str]) -> bool:
    normalized_name = _normalize(name)
    if not normalized_name or not aliases:
        return False
    for alias in aliases:
        if normalized_name == alias:
            return True
        if normalized_name in alias or alias in normalized_name:
            return True
    return False


def _stable_temp_course_id(course_name: str) -> str:
    digest = hashlib.sha1(course_name.encode("utf-8")).hexdigest()[:8]
    return f"temp_{digest}"


def _meeting_key(course_id: str | None, course_name: str) -> str:
    return course_id or _normalize(course_name)


def parse_avoid_time_slots(text: str) -> list[tuple[int, int, int]]:
    if not text:
        return []

    import json

    llm = LLMService()
    prompt = f"""
用户需求：避免在以下时间段有课：{text}
请提取出所有时间段，输出 JSON 数组，每个元素为 [星期几(1-7，1=周一), 开始节次, 结束节次]。
只输出数组，不要其他内容。
示例：[ [1,1,2], [3,3,4] ]
"""
    resp = llm._chat_completion(prompt, temperature=0, max_tokens=200, label="parse_avoid_slots", model=llm.lightweight_model_name, fallback_model=llm._lightweight_fallback_model)
    try:
        match = re.search(r"\[.*\]", resp or "", re.S)
        if match:
            data = json.loads(match.group(0))
            slots: list[tuple[int, int, int]] = []
            for item in data:
                if not isinstance(item, (list, tuple)) or len(item) != 3:
                    continue
                weekday, start, end = item
                try:
                    weekday_int = int(weekday)
                    start_int = int(start)
                    end_int = int(end)
                except (TypeError, ValueError):
                    continue
                if 1 <= weekday_int <= 7 and 1 <= start_int <= 11 and 1 <= end_int <= 11:
                    slots.append((weekday_int, start_int, end_int))
            return slots
    except Exception:
        pass
    return []


def parse_course_schedule(schedule_str: str):
    """从上课信息字符串中提取星期、节次、地点、周次"""
    weekday_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7}
    pattern = r'星期([一二三四五六日])第(\d+)-(\d+)节\s*(.*?)(?:；|$)'
    matches = re.findall(pattern, schedule_str or "")
    if not matches:
        return None
    wd_name, start, end, loc = matches[0]
    return (weekday_map[wd_name], int(start), int(end), loc.strip())


def parse_all_schedules(schedule_str: str):
    """解析上课信息，返回列表 [(星期几, 开始, 结束, 地点, 周次)]"""
    if not schedule_str:
        return []
    wd_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7}
    results: list[tuple[int, int, int, str, str]] = []

    # Split the schedule into segments around common separators while keeping
    # each '星期' occurrence as a segment boundary. This ensures multiple
    # meeting times (e.g. "星期一...；星期三...") are all parsed.
    segment_pattern = r'(?P<segment>(?P<weeks>\d+[-]?\d*周)?[，,]?\s*星期[一二三四五六日].*?)(?:；|;|,|，|$)'
    any_match = False
    for m in re.finditer(segment_pattern, schedule_str):
        any_match = True
        seg = m.group('segment') or ""
        # extract weeks if present
        weeks_m = re.search(r'(\d+[-]?\d*周)', seg)
        weeks = weeks_m.group(1) if weeks_m else '1-16周'
        # weekday
        wd_m = re.search(r'星期([一二三四五六日])', seg)
        if not wd_m:
            continue
        dow = wd_map.get(wd_m.group(1), 1)
        # slot range
        slot_m = re.search(r'第(\d+)-(\d+)节', seg)
        if not slot_m:
            # skip segments without explicit slot information
            continue
        start = int(slot_m.group(1))
        end = int(slot_m.group(2))
        # location (optional) - after the '节' there may be a location
        loc_m = re.search(r'第\d+-\d+节\s*([^\s；,，;]+)', seg)
        loc = loc_m.group(1) if loc_m else ''
        results.append((dow, start, end, loc, weeks))

    if any_match:
        return results

    # Fallback: previous simpler pattern (keeps backward compatibility)
    pattern = r'(?P<weeks>\d+[-]?\d*周)?[,]?星期([一二三四五六日])第(\d+)-(\d+)节\s*(?P<loc>[^\s]+)'
    for m in re.finditer(pattern, schedule_str):
        weeks = m.group('weeks') if m.group('weeks') else '1-16周'
        dow = wd_map[m.group(2)]
        start = int(m.group(3))
        end = int(m.group(4))
        loc = m.group('loc')
        results.append((dow, start, end, loc, weeks))
    return results


def has_conflict(course, avoid_slots):
    schedule = course.get('上课信息', '')
    if not schedule or not avoid_slots:
        return False
    for (dow, ss, es, _, _) in parse_all_schedules(schedule):
        for (ad, as_, ae) in avoid_slots:
            if dow == ad and not (es < as_ or ss > ae):
                return True
    return False


def _course_display_name(course: dict[str, Any]) -> str:
    for key in ("教学班", "课程名称", "name"):
        value = str(course.get(key) or "").strip()
        if value:
            return value
    return "未命名课程"


def extract_core_name(full_name: str) -> str:
    """提取核心课程名（去掉括号内的班级信息）"""
    match = re.match(r"^([^（(]+)", full_name or "")
    return match.group(1).strip() if match else (full_name or "").strip()


def _extract_required_keywords(profile: StudentProfile) -> list[str]:
    texts = [profile.recommendation_note or "", " ".join(profile.interests or [])]
    keywords: list[str] = []
    for text in texts:
        if not text:
            continue
        quoted = re.findall(r'《([^》]+)》|[“"]([^”"]+)[”"]', text)
        for left, right in quoted:
            candidate = (left or right).strip()
            if 1 < len(candidate) < 30 and candidate not in keywords:
                keywords.append(candidate)
        for candidate in re.split(r"[，,。；;、\n\s]+", text):
            candidate = candidate.strip()
            if 1 < len(candidate) < 30 and candidate not in keywords:
                keywords.append(candidate)
    return keywords


def _department_bonus(course: dict[str, Any]) -> float:
    department = str(course.get("开课院系") or "")
    if "计算机" in department:
        return 2.0
    return 0.0


def build_student_profile(
    completed_courses: Iterable[CompletedCourse],
    *,
    major: str | None = None,
    interests: list[str] | None = None,
    career_goal: str | None = None,
    desired_courses: list[str] | None = None,
    recommendation_note: str | None = None,
) -> StudentProfile:
    return StudentProfile(
        major=major,
        interests=interests or [],
        career_goal=career_goal,
        desired_courses=desired_courses or [],
        recommendation_note=recommendation_note,
        completed_courses=list(completed_courses),
    )


def check_graduation_requirements(profile: StudentProfile) -> GraduationCheck:
    if not profile.major:
        return GraduationCheck(
            status="needs_review",
            summary="未提供专业名称，无法自动比对毕业要求。",
        )

    return GraduationCheck(
        status="needs_review",
        summary=f"专业 {profile.major} 的毕业要求检查需要连接教务系统。",
        missing_courses=[],
    )


def score_courses(
    offerings: Iterable[dict[str, Any]],
    profile: StudentProfile,
) -> list[RecommendedCourse]:
    interest_tokens = [
        _normalize(token) for token in profile.interests if token
    ]
    career_tokens = [_normalize(profile.career_goal or "")]
    note_tokens = [
        _normalize(token)
        for token in re.split(r"[，,。；;\n]+", profile.recommendation_note or "")
        if token.strip()
    ]

    recommended: list[RecommendedCourse] = []
    for item in offerings:
        # Support offerings being either dict-like or simple course name strings.
        if isinstance(item, str):
            name = item
            course_id = None
            credits = None
            metadata = {}
        elif isinstance(item, dict):
            name = str(
                item.get("course_name")
                or item.get("KCMC")
                or item.get("name")
                or ""
            )
            course_id = (
                str(item.get("course_id") or item.get("KCH") or "") or None
            )
            credits = None
            if item.get("credits") is not None or item.get("XF") is not None:
                try:
                    credits = float(item.get("credits") or item.get("XF"))
                except (TypeError, ValueError):
                    credits = None
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        else:
            # Unknown item type; coerce to string for name and continue
            name = str(item)
            course_id = None
            credits = None
            metadata = {}

        if not name:
            continue

        normalized_name = _normalize(name)
        score = 0.0
        reason_bits: list[str] = []

        for token in interest_tokens:
            if token and token in normalized_name:
                score += 1.2
                reason_bits.append(f"匹配兴趣: {token}")

        for token in career_tokens:
            if token and token in normalized_name:
                score += 0.8
                reason_bits.append("与职业目标相关")

        for token in note_tokens:
            if token and token in normalized_name:
                score += 0.6
                reason_bits.append("匹配你的课程建议")

        if not reason_bits:
            reason_bits.append("基础匹配")

        recommended.append(
            RecommendedCourse(
                course_id=course_id,
                course_name=name,
                credits=credits,
                score=score,
                reason="; ".join(reason_bits),
                metadata=metadata if metadata else None,
            )
        )

    recommended.sort(key=lambda item: item.score, reverse=True)
    return recommended


def select_courses(
    candidates: list[RecommendedCourse],
    *,
    max_credits: int,
) -> list[RecommendedCourse]:
    selected: list[RecommendedCourse] = []
    total = 0.0
    for course in candidates:
        credits = course.credits or 3.0
        if total + credits > max_credits:
            continue
        selected.append(course)
        total += credits
    return selected


def plan_schedule(
    term: TermInfo,
    profile: StudentProfile,
    offerings: list[dict[str, Any]],
    meetings: list[CourseMeeting],
    *,
    max_credits: int,
    use_llm: bool,
) -> RecommendationPlan:
    offerings = offerings or []
    meetings = meetings or []

    recommended = score_courses(offerings, profile)
    selected = select_courses(recommended, max_credits=max_credits)
    selected_keys = set()
    for course in selected:
        if course.course_id:
            selected_keys.add(course.course_id)
        if course.course_name:
            selected_keys.update(_course_name_aliases(course.course_name))

    planned_meetings: list[CourseMeeting] = []
    for meeting in meetings:
        meeting_key = _meeting_key(meeting.course_id, meeting.course_name)
        normalized_meeting_name = _normalize(meeting.course_name)
        if meeting_key not in selected_keys and normalized_meeting_name not in selected_keys:
            continue

        # Enrich the meeting with the best available offering metadata.
        for offer in offerings:
            if not isinstance(offer, dict):
                continue

            offer_id = str(offer.get("course_id") or offer.get("KCH") or "") or None
            offer_name = str(
                offer.get("course_name")
                or offer.get("KCMC")
                or offer.get("name")
                or ""
            )
            offer_aliases = _course_name_aliases(offer_name)
            if offer_id:
                offer_aliases.add(_normalize(offer_id))
            if not (
                meeting_key in offer_aliases
                or _normalize(meeting.course_name) in offer_aliases
            ):
                continue

            if not meeting.course_id:
                meeting.course_id = offer_id
            if not meeting.location:
                meeting.location = str(
                    offer.get("location") or offer.get("JASMC") or ""
                ) or None
            if not meeting.instructor:
                meeting.instructor = str(
                    offer.get("instructor") or offer.get("JSXM") or ""
                ) or None
            if not meeting.weeks:
                meeting.weeks = str(offer.get("weeks") or offer.get("ZCD") or "") or None
            if meeting.credits is None:
                raw_credits = offer.get("credits") or offer.get("XF")
                try:
                    meeting.credits = float(raw_credits) if raw_credits is not None else None
                except (TypeError, ValueError):
                    meeting.credits = None
            break

        if not meeting.course_id:
            meeting.course_id = _stable_temp_course_id(meeting.course_name)
        if not meeting.location:
            meeting.location = "待定"
        if not meeting.instructor:
            meeting.instructor = "待定"
        if not meeting.weeks:
            meeting.weeks = "1-16周"

        planned_meetings.append(meeting)

    warnings: list[str] = []

    if not offerings:
        warnings.append("未抓取到可选课程列表，暂时无法生成可选课推荐。")

    if selected and not planned_meetings:
        warnings.append("推荐课程未包含排课信息，课表仅展示空模板。")

    rationale = ""
    if use_llm:
        try:
            llm_service = LLMService()
            prompt = _build_recommendation_prompt(profile, selected, term)
            response = llm_service._chat_completion(
                prompt,
                temperature=0.2,
                max_tokens=256,
                label="course_recommendation",
                model=llm_service.lightweight_model_name,
                fallback_model=llm_service._lightweight_fallback_model,
                system_prompt=(
                    "You are a course planning assistant. "
                    "Summarize the reasoning in Chinese in 2-3 short sentences."
                ),
            )
            rationale = response or ""
        except Exception:
            rationale = "（生成理由时发生错误，已使用默认理由。）"

    if not rationale:
        rationale = "根据兴趣关键词与学期课程匹配度生成推荐，并优先保留冲突较少的课程。"

    # graduation check may rely on external QA services — degrade gracefully
    try:
        grad_check = check_graduation_requirements(profile)
    except Exception:
        grad_check = GraduationCheck(status="needs_review", summary="无法自动检查毕业要求（检查服务不可用）", missing_courses=[])

    return RecommendationPlan(
        term=term,
        recommended_courses=selected,
        meetings=planned_meetings,
        warnings=warnings,
        rationale=rationale,
        graduation_check=grad_check,
    )


def plan_schedule_with_llm(
    term: TermInfo,
    profile: StudentProfile,
    term_id: str,
    *,
    min_credits: int = 0,
    max_credits: int,
) -> RecommendationPlan:
    """使用 LLM + 本地课程数据 进行智能推荐（稳定版本）"""
    import json
    import re
    from pathlib import Path

    backend_root = Path(__file__).parents[3]
    courses_json_path = backend_root / "data" / "tis_download" / "full_course_table" / "all_courses_merged.json"

    # 1. 加载全校课程
    all_courses: list[dict[str, Any]] = []
    if courses_json_path.exists():
        try:
            with open(courses_json_path, "r", encoding="utf-8") as f:
                loaded_courses = json.load(f)
            if isinstance(loaded_courses, list):
                all_courses = [course for course in loaded_courses if isinstance(course, dict)]
            print(f"[推荐] 从 JSON 加载了 {len(all_courses)} 门课程")
        except Exception as e:
            print(f"[推荐] 加载课程 JSON 失败: {e}")
            return RecommendationPlan(
                term=term,
                recommended_courses=[],
                meetings=[],
                warnings=["课程数据加载失败，无法推荐"],
                rationale="",
                graduation_check=GraduationCheck(),
            )
    else:
        return RecommendationPlan(
            term=term,
            recommended_courses=[],
            meetings=[],
            warnings=["课程文件不存在，请先运行 OCR 生成 all_courses_merged.json"],
            rationale="",
            graduation_check=GraduationCheck(),
        )

    # 2. 已修课程集合（核心名 + 完整名 + 中英文别名）
    completed_names: set[str] = set()
    for course in profile.completed_courses:
        if course.course_name:
            completed_names.update(_course_name_aliases(course.course_name))
    print(f"[推荐] 已修课程数: {len(completed_names)}")

    # 3. 提取用户明确要求的关键词（必须修读）
    required_keywords = _extract_required_keywords(profile)
    print(f"[推荐] 用户明确课程关键词: {required_keywords}")

    def _keyword_matches_course(keyword: str, core_name: str, full_name: str) -> bool:
        course_aliases = _course_name_aliases(core_name)
        course_aliases.update(_course_name_aliases(full_name))
        return _course_name_matches(keyword, course_aliases)

    # 4. 解析避开时间段（如果用户有输入）
    avoid_slots = parse_avoid_time_slots(profile.career_goal or "")

    # 5. 过滤课程：排除已修、排除冲突，区分必须课程和普通课程
    available: list[dict[str, Any]] = []
    must_selected: list[dict[str, Any]] = []
    remaining_required_keywords = list(required_keywords)
    matched_required_keywords: list[str] = []
    matched_required_cores: set[str] = set()

    for course in all_courses:
        course_name = str(course.get("课程名称", "")).strip()
        if not course_name:
            continue

        # 排除已修
        if _course_name_matches(course_name, completed_names):
            continue

        core = extract_core_name(course_name)
        if _course_name_matches(core, completed_names):
            continue

        # 排除冲突时间段
        if has_conflict(course, avoid_slots):
            continue

        # 检查是否为必须课程（核心名完全匹配）
        is_must = False
        for kw in list(remaining_required_keywords):
            if _keyword_matches_course(kw, core, course_name):
                is_must = True
                remaining_required_keywords.remove(kw)
                matched_required_keywords.append(kw)
                matched_required_cores.add(core)
                break

        if is_must:
            must_selected.append(course)
        else:
            available.append(course)

    print(f"[推荐] 排除已修和冲突后剩余 {len(available)} 门普通课程")
    print(f"[推荐] 必须课程匹配到 {len(must_selected)} 门")
    if remaining_required_keywords:
        print(f"[推荐] 未匹配到的必修关键词: {remaining_required_keywords}")

    # 6. 选择课程：优先必须课程，再按兴趣和院系补充
    selected_courses: list[dict[str, Any]] = []
    total_credits = 0.0
    warnings: list[str] = []

    def _slots_for(course: dict[str, Any]) -> list[tuple[int, int, int]]:
        slots = []
        for (dow, ss, es, _, _) in parse_all_schedules(str(course.get("上课信息") or "")):
            slots.append((dow, ss, es))
        return slots

    def _overlap(s1: tuple[int, int, int], s2: tuple[int, int, int]) -> bool:
        dow1, a1, b1 = s1
        dow2, a2, b2 = s2
        if dow1 != dow2:
            return False
        return not (b1 < a2 or a1 > b2)

    def _conflicts_with_selected(course: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
        slots = _slots_for(course)
        if not slots:
            return False
        for s in slots:
            for sel in selected:
                for s2 in _slots_for(sel):
                    if _overlap(s, s2):
                        return True
        return False

    def _evict_non_required_conflicts(course: dict[str, Any], selected: list[dict[str, Any]], protected_cores: set[str]) -> None:
        """Remove non-protected selected courses that conflict with `course` to make room."""
        nonlocal total_credits
        made_change = False
        for sel in list(selected):
            core_sel = extract_core_name(str(sel.get("课程名称") or ""))
            if core_sel in protected_cores:
                continue
            # if sel conflicts with course, remove it
            for s in _slots_for(sel):
                for sc in _slots_for(course):
                    if _overlap(s, sc):
                        _remove_selected(sel)
                        made_change = True
                        break
                if made_change:
                    break
        return

    def _unique_credits_sum(courses: list[dict[str, Any]]) -> float:
        """Sum credits by unique JSON `课程名称`. For duplicate names keep the maximum credits seen."""
        by_name: dict[str, float] = {}
        for item in courses:
            name = str(item.get("课程名称") or "").strip()
            if not name:
                continue
            try:
                credits_val = float(item.get("学分") or item.get("XF") or 0.0)
            except (TypeError, ValueError):
                credits_val = 0.0
            prev = by_name.get(name)
            if prev is None or credits_val > prev:
                by_name[name] = credits_val
        return sum(by_name.values())

    def _would_exceed_max_if_added(course: dict[str, Any], selected: list[dict[str, Any]], max_allowed: float) -> bool:
        """Return True if adding `course` (counted by JSON `课程名称`) would make unique-name credit sum exceed max_allowed."""
        current = _unique_credits_sum(selected)
        name = str(course.get("课程名称") or "").strip()
        try:
            credits = float(course.get("学分") or 3.0)
        except (TypeError, ValueError):
            credits = 3.0
        if not name:
            return current + credits > max_allowed
        # if same course name already in selected, adding won't increase unique sum
        for sel in selected:
            if str(sel.get("课程名称") or "").strip() == name:
                return False
        return current + credits > max_allowed

    # 先添加必须课程
    for course in must_selected:
        try:
            credits = float(course.get("学分", 3.0))
        except (TypeError, ValueError):
            credits = 3.0
        # If this required course conflicts with existing non-required selections,
        # evict those so we can include required ones.
        if _conflicts_with_selected(course, selected_courses):
            _evict_non_required_conflicts(course, selected_courses, matched_required_cores)
        if (not _would_exceed_max_if_added(course, selected_courses, max_credits)) and not _conflicts_with_selected(course, selected_courses):
            selected_courses.append(course)
        else:
            print(f"[推荐] 必须课程学分超限或与已选冲突，无法加入: {course.get('课程名称')}")

    # 再按兴趣补充剩余学分（按课程名称去重后的学分上限）
    if _unique_credits_sum(selected_courses) < max_credits:
        interest_keywords: list[str] = []
        if profile.recommendation_note:
            interest_keywords.extend(re.findall(r"[\u4e00-\u9fa5]{2,}", profile.recommendation_note))
        interest_keywords = list(dict.fromkeys(interest_keywords))

        scored: list[tuple[float, dict[str, Any]]] = []
        for course in available:
            name = str(course.get("课程名称", ""))
            core_name = extract_core_name(name)
            score = _department_bonus(course)
            for keyword in interest_keywords:
                if keyword in core_name:
                    score += 1.0
            scored.append((score, course))
        scored.sort(key=lambda item: item[0], reverse=True)

        # If user provided explicit required keywords, avoid selecting courses
        # that conflict with those required cores. Otherwise, select randomly
        # (one offering per core) while avoiding time conflicts.
        if matched_required_cores:
            for _, course in scored:
                try:
                    credits = float(course.get("学分", 3.0))
                except (TypeError, ValueError):
                    credits = 3.0
                core_name = extract_core_name(str(course.get("课程名称") or ""))
                # skip if this course conflicts with any protected required selection
                conflict_with_required = False
                for sel in selected_courses:
                    if extract_core_name(str(sel.get("课程名称") or "")) in matched_required_cores and _conflicts_with_selected(course, [sel]):
                        conflict_with_required = True
                        break
                if conflict_with_required:
                    continue
                if (not _would_exceed_max_if_added(course, selected_courses, max_credits)) and not _conflicts_with_selected(course, selected_courses):
                    selected_courses.append(course)
                if _unique_credits_sum(selected_courses) >= max_credits:
                    break
        else:
            # Randomized selection across cores (one offering per core)
            import random
            cores = {}
            for _, course in scored:
                core_name = extract_core_name(str(course.get("课程名称") or ""))
                cores.setdefault(core_name, []).append(course)
            core_list = list(cores.items())
            random.shuffle(core_list)
            for core_name, offerings_list in core_list:
                # pick a random offering from this core
                choice = random.choice(offerings_list)
                try:
                    credits = float(choice.get("学分", 3.0))
                except (TypeError, ValueError):
                    credits = 3.0
                if _would_exceed_max_if_added(choice, selected_courses, max_credits):
                    continue
                if _conflicts_with_selected(choice, selected_courses):
                    continue
                selected_courses.append(choice)
                if _unique_credits_sum(selected_courses) >= max_credits:
                    break

    print(f"[推荐] 最终推荐 {len(selected_courses)} 门课程，总学分 {_unique_credits_sum(selected_courses)}")

    # --- enforce per-core-name "课程种类" rules ---
    # Group candidates by core name and detect available types per core
    core_candidates: dict[str, list[dict[str, Any]]] = {}
    for c in must_selected + available:
        name = str(c.get("课程名称") or "").strip()
        if not name:
            continue
        core = extract_core_name(name)
        core_candidates.setdefault(core, []).append(c)

    def _course_kind(course: dict[str, Any]) -> str:
        kind = str(course.get("课程种类") or "").strip().lower()
        if kind not in ("lab", "theory"):
            return "theory"
        return kind

    # Build selected mapping by core -> {kind: [courses]}
    core_selected: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for c in list(selected_courses):
        name = str(c.get("课程名称") or "").strip()
        core = extract_core_name(name)
        kind = _course_kind(c)
        core_selected.setdefault(core, {}).setdefault(kind, []).append(c)

    def _remove_selected(course: dict[str, Any]) -> None:
        if course not in selected_courses:
            return
        try:
            credits_r = float(course.get("学分", 3.0))
        except (TypeError, ValueError):
            credits_r = 3.0
        selected_courses.remove(course)
        # total_credits is computed later as unique-name sum; do not maintain incremental raw sum here.

    def _free_room_for(credits_needed: float, protected_cores: set[str]) -> bool:
        """Remove non-protected selected courses from the end until enough room exists."""
        nonlocal total_credits
        # operate on unique-name credit sum
        current = _unique_credits_sum(selected_courses)
        if current + credits_needed <= max_credits:
            return True

        for course in list(reversed(selected_courses)):
            course_name = str(course.get("课程名称") or "").strip()
            if not course_name:
                continue
            core_name = extract_core_name(course_name)
            if core_name in protected_cores:
                continue
            _remove_selected(course)
            current = _unique_credits_sum(selected_courses)
            if current + credits_needed <= max_credits:
                return True
        return _unique_credits_sum(selected_courses) + credits_needed <= max_credits

    def _keep_one_item(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return items[:1] if items else []

    # Enforce rules per core
    for core, candidates in core_candidates.items():
        kinds_available = { _course_kind(c) for c in candidates }

        sel_by_kind = core_selected.get(core, {})

        # First, remove duplicate offerings of the same core + kind.
        for kind, sel_list in list(sel_by_kind.items()):
            if len(sel_list) > 1:
                for extra in sel_list[1:]:
                    _remove_selected(extra)
                sel_by_kind[kind] = _keep_one_item(sel_list)

        # If both kinds exist among candidates, we must include one of each or none
        if kinds_available == {"theory", "lab"}:
            has_theory = bool(sel_by_kind.get("theory"))
            has_lab = bool(sel_by_kind.get("lab"))
            if has_theory and not has_lab:
                # try to add a lab offering
                lab_choice = None
                for cand in candidates:
                    if _course_kind(cand) == "lab" and cand not in selected_courses:
                        lab_choice = cand
                        break
                if lab_choice:
                    try:
                        credits = float(lab_choice.get("学分", 3.0))
                    except (TypeError, ValueError):
                        credits = 3.0
                    if not _would_exceed_max_if_added(lab_choice, selected_courses, max_credits):
                        selected_courses.append(lab_choice)
                        core_selected.setdefault(core, {}).setdefault("lab", []).append(lab_choice)
                    elif core in matched_required_cores and _free_room_for(credits, matched_required_cores):
                        selected_courses.append(lab_choice)
                        core_selected.setdefault(core, {}).setdefault("lab", []).append(lab_choice)
                    else:
                        # cannot add matching lab due to credits -> remove the theory
                        for rem in list(sel_by_kind.get("theory", [])):
                            _remove_selected(rem)
                        core_selected.pop(core, None)
            elif has_lab and not has_theory:
                # try to add a theory offering
                theory_choice = None
                for cand in candidates:
                    if _course_kind(cand) == "theory" and cand not in selected_courses:
                        theory_choice = cand
                        break
                if theory_choice:
                    try:
                        credits = float(theory_choice.get("学分", 3.0))
                    except (TypeError, ValueError):
                        credits = 3.0
                    if not _would_exceed_max_if_added(theory_choice, selected_courses, max_credits):
                        selected_courses.append(theory_choice)
                        core_selected.setdefault(core, {}).setdefault("theory", []).append(theory_choice)
                    elif core in matched_required_cores and _free_room_for(credits, matched_required_cores):
                        selected_courses.append(theory_choice)
                        core_selected.setdefault(core, {}).setdefault("theory", []).append(theory_choice)
                    else:
                        # cannot add matching theory due to credits -> remove the lab
                        for rem in list(sel_by_kind.get("lab", [])):
                            _remove_selected(rem)
                        core_selected.pop(core, None)
            elif has_theory and has_lab:
                # both kinds already present; keep one of each and discard any extras above
                core_selected[core]["theory"] = _keep_one_item(sel_by_kind.get("theory", []))
                core_selected[core]["lab"] = _keep_one_item(sel_by_kind.get("lab", []))
            elif not has_theory and not has_lab:
                # If nothing was selected for this mixed course, leave it empty.
                pass
            # if neither present in selection, leave as none

        else:
            # only one kind available -> ensure at most one selected of that kind
            kind = next(iter(kinds_available)) if kinds_available else "theory"
            sel_list = sel_by_kind.get(kind, [])
            if len(sel_list) > 1:
                # keep the first, remove extras
                for extra in sel_list[1:]:
                    _remove_selected(extra)
                core_selected[core][kind] = sel_list[:1]

    # Recompute final selected count printout
    print(f"[推荐] 调整后推荐 {len(selected_courses)} 门课程，总学分 {_unique_credits_sum(selected_courses)}")
    def _effective_credits(courses: list[dict[str, Any]]) -> float:
        """Sum credits per core name, counting each core only once.

        For cores with multiple selected offerings (theory+lab), count the
        maximum credits among those offerings once to avoid double-counting.
        """
        by_core: dict[str, float] = {}
        for item in courses:
            course_name = str(item.get("课程名称") or "").strip()
            if not course_name:
                continue
            core = extract_core_name(course_name)
            try:
                credits = float(item.get("学分") or item.get("XF") or 0.0)
            except (TypeError, ValueError):
                credits = 0.0
            prev = by_core.get(core)
            if prev is None or credits > prev:
                by_core[core] = credits
        return sum(by_core.values())

    # If we still have not reached the requested lower bound (using
    # effective credits per core), try to backfill from remaining candidates
    # without violating duplicate/kind rules.
    def _selection_state(items: list[dict[str, Any]]) -> tuple[set[str], dict[str, set[str]]]:
        names: set[str] = set()
        kinds_by_core: dict[str, set[str]] = {}
        for item in items:
            course_name = str(item.get("课程名称") or "").strip()
            if not course_name:
                continue
            names.add(course_name)
            core_name = extract_core_name(course_name)
            kinds_by_core.setdefault(core_name, set()).add(_course_kind(item))
        return names, kinds_by_core

    def _can_select(course: dict[str, Any], selected_names: set[str], selected_kinds_by_core: dict[str, set[str]]) -> bool:
        course_name = str(course.get("课程名称") or "").strip()
        if not course_name or course_name in selected_names:
            return False
        core_name = extract_core_name(course_name)
        kind = _course_kind(course)
        available_kinds = {_course_kind(item) for item in core_candidates.get(core_name, [])}
        selected_kinds = selected_kinds_by_core.get(core_name, set())

        if kind in selected_kinds:
            return False

        if available_kinds == {"theory", "lab"}:
            if not selected_kinds:
                return True
            return selected_kinds == ({"theory"} if kind == "lab" else {"lab"})

        return not selected_kinds

    def _score_candidate(course: dict[str, Any]) -> float:
        score = _department_bonus(course)
        course_name = str(course.get("课程名称", ""))
        core_name = extract_core_name(course_name)
        for keyword in interest_keywords:
            if keyword in core_name:
                score += 1.0
        return score
    selected_names, selected_kinds_by_core = _selection_state(selected_courses)
    unique_total = _unique_credits_sum(selected_courses)
    if unique_total < min_credits:
        remaining_candidates = []
        for course in must_selected + available:
            if _can_select(course, selected_names, selected_kinds_by_core):
                remaining_candidates.append(( _score_candidate(course), course ))
        remaining_candidates.sort(key=lambda item: item[0], reverse=True)

        for _, course in remaining_candidates:
            # Stop if we've reached the effective lower bound or hit max raw credits
            unique_total = _unique_credits_sum(selected_courses)
            if unique_total >= min_credits or unique_total >= max_credits:
                break
            try:
                credits = float(course.get("学分", 3.0))
            except (TypeError, ValueError):
                credits = 3.0
            if _would_exceed_max_if_added(course, selected_courses, max_credits):
                continue
            selected_courses.append(course)
            course_name = str(course.get("课程名称") or "").strip()
            selected_names.add(course_name)
            core_name = extract_core_name(course_name)
            selected_kinds_by_core.setdefault(core_name, set()).add(_course_kind(course))
            # recompute unique total for next iteration
            unique_total = _unique_credits_sum(selected_courses)
    unique_total = _unique_credits_sum(selected_courses)
    if unique_total < min_credits:
        warnings.append(
            f"当前课程数据下无法达到最低学分要求 {min_credits}（按课程核算，不重复计科），已返回尽可能接近的结果。"
        )

    def _group_slots(group: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
        slots: list[tuple[int, int, int]] = []
        for course in group:
            slots.extend(_slots_for(course))
        return slots

    def _group_conflicts_with_courses(
        group: list[dict[str, Any]],
        courses: list[dict[str, Any]],
    ) -> bool:
        group_slots = _group_slots(group)
        if not group_slots:
            return False
        for course in courses:
            for slot_a in _slots_for(course):
                for slot_b in group_slots:
                    if _overlap(slot_a, slot_b):
                        return True
        return False

    def _normalize_selected_courses(
        courses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        first_index: dict[str, int] = {}
        for idx, course in enumerate(courses):
            core_name = extract_core_name(str(course.get("课程名称") or ""))
            if not core_name:
                continue
            grouped.setdefault(core_name, []).append(course)
            first_index.setdefault(core_name, idx)

        ordered_cores = sorted(
            grouped.keys(),
            key=lambda core_name: (
                0 if core_name in matched_required_cores else 1,
                first_index.get(core_name, 10**6),
            ),
        )

        normalized: list[dict[str, Any]] = []
        for core_name in ordered_cores:
            group = list(grouped.get(core_name, []))
            available_kinds = {_course_kind(item) for item in core_candidates.get(core_name, [])}
            selected_kinds = {_course_kind(item) for item in group}

            # Mixed-kind cores must be kept as a pair or not at all.
            if available_kinds == {"theory", "lab"} and selected_kinds and selected_kinds != {"theory", "lab"}:
                missing_kind = "lab" if "theory" in selected_kinds else "theory"
                missing_choice = None
                for cand in core_candidates.get(core_name, []):
                    if _course_kind(cand) == missing_kind and cand not in group:
                        missing_choice = cand
                        break
                if missing_choice is not None:
                    group.append(missing_choice)
                else:
                    group = []

            if not group:
                continue

            if _group_conflicts_with_courses(group, normalized):
                if core_name in matched_required_cores:
                    # Remove previously kept non-required courses that conflict with this required core.
                    for kept in list(normalized):
                        kept_core = extract_core_name(str(kept.get("课程名称") or ""))
                        if kept_core in matched_required_cores:
                            continue
                        if _group_conflicts_with_courses([kept], group):
                            _remove_selected(kept)
                            normalized.remove(kept)
                    if _group_conflicts_with_courses(group, normalized):
                        warnings.append(f"必修课程 {core_name} 与其他必修课程时间冲突，已保留前面的必修课程。")
                        continue
                else:
                    continue

            normalized.extend(group)

        return normalized

    selected_courses = _normalize_selected_courses(selected_courses)
    # Compute total credits by unique JSON `课程名称` (each course name counts once)
    total_credits = _unique_credits_sum(selected_courses)

    # 7. 生成推荐理由（按课程代码去重：同一课程代码的不同教学班只保留一次）
    llm_service = LLMService()
    rationale = ""
    if selected_courses:
        # 保留顺序的去重：以 `课程代码` 为主键，若无课程代码则以核心课程名作为键
        seen_keys: set[str] = set()
        unique_selected: list[dict[str, Any]] = []
        for course in selected_courses:
            code = str(course.get("课程代码") or "").strip()
            if code:
                key = f"code::{code}"
            else:
                key = f"core::{extract_core_name(str(course.get('课程名称') or ''))}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_selected.append(course)

        course_descs = "\n".join([
            f"- {course.get('课程名称')} ({course.get('学分')}学分)" for course in unique_selected[:10]
        ])
        prompt = f"""
学生专业: {profile.major or '计算机科学与技术'}
已修课程: {', '.join(list(completed_names)[:20])}
用户需求: {profile.recommendation_note or '无'}
推荐的课程列表:
{course_descs}

请用两句话说明为什么推荐这些课程（结合兴趣、培养方案、已修课程）。只输出文字，不要 JSON。
"""
        rationale = llm_service._chat_completion(
            prompt,
            temperature=0.3,
            max_tokens=200,
            label="generate_rationale",
            model=llm_service.lightweight_model_name,
            fallback_model=llm_service._lightweight_fallback_model,
        ) or "根据您的兴趣和已修课程，推荐以上课程以完成培养方案要求。"
    else:
        rationale = "未找到符合条件的课程，请调整学分上限或修改需求。"
        warnings = ["没有找到满足条件的课程，可能已修课程过多或必须课程未开设。"]

    # 8. 构建 meetings 和 postponed_courses
    # 去重：同一课程名称的不同教学班只保留一次；
    # 但混合型核心课程必须同时保留 theory + lab，因此这类核心按“核心名 + 种类”去重。
    seen_course_keys: set[str] = set()
    dedup_selected_courses: list[dict[str, Any]] = []
    for course in selected_courses:
        name = str(course.get("课程名称") or "").strip()
        core_name = extract_core_name(name)
        available_kinds = {_course_kind(item) for item in core_candidates.get(core_name, [])}
        kind = _course_kind(course)
        if name:
            if available_kinds == {"theory", "lab"}:
                key = f"core-kind::{core_name}::{kind}"
            else:
                key = f"name::{name}"
        else:
            if available_kinds == {"theory", "lab"}:
                key = f"core-kind::{core_name}::{kind}"
            else:
                key = f"core::{core_name}"
        if key in seen_course_keys:
            continue
        seen_course_keys.add(key)
        dedup_selected_courses.append(course)
    selected_courses = dedup_selected_courses
    meetings = []
    postponed_courses: list[RecommendedCourse] = []
    recommended_courses: list[RecommendedCourse] = []

    # 先给每门课打好 source 标记，然后批量生成推荐理由
    course_sources: dict[str, str] = {}  # core_name → source
    for course in selected_courses:
        core = extract_core_name(str(course.get("课程名称") or ""))
        course_sources[core] = "user_required" if core in matched_required_cores else "system_supplement"

    # 批量生成推荐理由：非必须课程让 LLM 给出多样化理由
    llm_reasons: dict[str, str] = {}
    non_required = [(c, extract_core_name(str(c.get("课程名称") or "")))
                    for c in selected_courses
                    if course_sources.get(extract_core_name(str(c.get("课程名称") or "")), "") != "user_required"]
    if non_required:
        try:
            llm_service2 = LLMService()
            course_list = "\n".join([
                f"- {cn} ({c.get('学分', 3)}学分) [{str(c.get('课程种类') or c.get('课程属性') or '')}]"
                for c, cn in non_required
            ])
            prompt = f"""
学生专业: {profile.major or '计算机科学与技术'}
已修课程: {', '.join(list(completed_names)[:15])}
用户需求: {profile.recommendation_note or '无'}

以下是系统补充推荐的课程，请为每门课写一句简短的推荐理由（10-20字），说明为什么推荐，结合专业方向、培养方案、技能拓展等角度，不要写"系统推荐"。

课程列表:
{course_list}

请按顺序为以上每门课输出一行理由，格式: 课程名: 理由
只输出理由，不要 JSON。
"""
            resp = llm_service2._chat_completion(
                prompt,
                temperature=0.4,
                max_tokens=300,
                label="course_reasons",
                model=llm_service2.lightweight_model_name,
                fallback_model=llm_service2._lightweight_fallback_model,
            )
            if resp:
                for line in resp.strip().split("\n"):
                    line = line.strip()
                    if ":" in line or "：" in line:
                        # Parse "课程名: 理由"
                        sep = ":" if ":" in line else "："
                        parts = line.split(sep, 1)
                        name_key = parts[0].strip()
                        reason_text = parts[1].strip() if len(parts) > 1 else ""
                        if name_key and reason_text:
                            # Match by fuzzy core name
                            for _, cn in non_required:
                                if _normalize(name_key) in _normalize(cn) or _normalize(cn) in _normalize(name_key):
                                    llm_reasons[cn] = reason_text
                                    break
                            else:
                                # fallback: store by the original name key
                                llm_reasons[name_key] = reason_text
        except Exception as e:
            print(f"[推荐] 生成课程理由失败: {e}")

    for course in selected_courses:
        schedule_str = course.get("上课信息", "")
        slots = parse_all_schedules(schedule_str)
        course_name = str(course.get("课程名称") or "").strip()
        if not course_name:
            course_name = _course_display_name(course)

        core = extract_core_name(course.get("课程名称", ""))
        source = course_sources.get(core, "system_supplement")

        # 确定推荐理由
        if source == "user_required":
            reason = "优先推荐，用户要求"
        else:
            # 优先用 LLM 生成的理由，fallback 用默认描述
            reason = llm_reasons.get(core) or llm_reasons.get(course_name) or "专业拓展，丰富知识结构"

        if slots:
            for (dow, ss, es, loc, weeks) in slots:
                meetings.append(CourseMeeting(
                    course_id=course.get("课程代码"),
                    course_name=course_name,
                    instructor=course.get("教师"),
                    location=loc,
                    day_of_week=dow,
                    start_slot=ss,
                    end_slot=es,
                    weeks=weeks,
                    credits=course.get("学分"),
                    source="recommendation",
                    metadata={},
                ))
            recommended_courses.append(RecommendedCourse(
                course_id=course.get("课程代码"),
                course_name=course_name,
                credits=course.get("学分"),
                score=0.8,
                reason=reason,
                status="scheduled",
                source=source,
            ))
        else:
            postponed_courses.append(RecommendedCourse(
                course_id=course.get("课程代码"),
                course_name=course_name,
                credits=course.get("学分"),
                score=0.8,
                reason=f"{reason}（该课程暂无具体课表时间）",
                status="postponed",
                source=source,
            ))
            recommended_courses.append(RecommendedCourse(
                course_id=course.get("课程代码"),
                course_name=course_name,
                credits=course.get("学分"),
                score=0.8,
                reason=f"{reason}（该课程暂无具体课表时间）",
                status="postponed",
                source=source,
            ))

    if postponed_courses:
        warnings.append(f"有 {len(postponed_courses)} 门后置名单课程暂无具体上课信息，已从课表中隐藏。")

    return RecommendationPlan(
        term=term,
        recommended_courses=recommended_courses,
        postponed_courses=postponed_courses,
        meetings=meetings,
        warnings=warnings,
        rationale=rationale,
        graduation_check=GraduationCheck(
            status="generated",
            summary=f"推荐了 {len(recommended_courses)} 门课程，共 {total_credits} 学分",
            missing_courses=[],
        ),
    )


def extract_meeting_from_chunk(text: str, course_name: str) -> CourseMeeting:
    """从 chunk 文本中提取上课信息"""
    import re

    meeting = CourseMeeting(
        course_id=None,
        course_name=course_name,
        instructor=None,
        location=None,
        day_of_week=1,
        start_slot=1,
        end_slot=2,
        weeks=None,
        credits=None,
        source="course_kb",
        metadata={"raw": text[:500]},
    )

    weeks_match = re.search(r'(\d+[-]?\d*周)', text)
    if weeks_match:
        meeting.weeks = weeks_match.group(1)

    location_match = re.search(r'([^,\n]+楼[^,\n]*)', text)
    if location_match:
        meeting.location = location_match.group(1).strip()

    day_match = re.search(r'星期[一二三四五六日]', text)
    if day_match:
        day_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7}
        meeting.day_of_week = day_map.get(day_match.group(0)[2], 1)

    slot_match = re.search(r'第(\d+)-(\d+)节', text)
    if slot_match:
        meeting.start_slot = int(slot_match.group(1))
        meeting.end_slot = int(slot_match.group(2))

    return meeting


def _build_recommendation_prompt(
    profile: StudentProfile,
    courses: list[RecommendedCourse],
    term: TermInfo,
) -> str:
    course_lines = []
    for course in courses:
        credit_text = (
            f"{course.credits}学分" if course.credits is not None else "学分未知"
        )
        course_lines.append(f"- {course.course_name} ({credit_text})")

    return (
        "学生画像:\n"
        f"专业: {profile.major or '未填写'}\n"
        f"兴趣: {', '.join(profile.interests) if profile.interests else '未填写'}\n"
        f"职业目标: {profile.career_goal or '未填写'}\n\n"
        f"课程建议: {profile.recommendation_note or '未填写'}\n\n"
        f"目标学期: {term.label}\n\n"
        "已筛选课程列表:\n"
        + "\n".join(course_lines)
        + "\n\n"
        "请输出 2-3 句简短理由，说明这些课程如何满足兴趣和培养方案方向。"
    )
