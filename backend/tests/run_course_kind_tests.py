from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.course_recommendation import recommendation_engine as engine
from src.services.course_recommendation.models import StudentProfile, TermInfo


COURSES_JSON = ROOT / "data" / "tis_download" / "full_course_table" / "all_courses_merged.json"


def backup_original() -> Path | None:
    if not COURSES_JSON.exists():
        return None
    backup_path = COURSES_JSON.with_suffix(".json.bak")
    shutil.copy2(COURSES_JSON, backup_path)
    return backup_path


def restore_original(backup_path: Path | None) -> None:
    if backup_path and backup_path.exists():
        shutil.move(str(backup_path), str(COURSES_JSON))


def write_courses(courses: list[dict]) -> None:
    COURSES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with COURSES_JSON.open("w", encoding="utf-8") as handle:
        json.dump(courses, handle, ensure_ascii=False, indent=2)


def patch_llm() -> None:
    engine.LLMService._chat_completion = lambda self, *args, **kwargs: "测试推荐理由"


def make_term() -> TermInfo:
    return TermInfo(term_id="2026-1", year=2026, semester=1, label="2026春")


def make_profile() -> StudentProfile:
    return StudentProfile(major="CS", interests=["Core"], recommendation_note="Core")


def count_core(plan, prefix: str) -> int:
    return sum(1 for course in plan.recommended_courses if course.course_name.startswith(prefix))


def count_exact(plan, course_name: str) -> int:
    return sum(1 for course in plan.recommended_courses if course.course_name == course_name)


def total_plan_credits(plan) -> float:
    total = 0.0
    for course in plan.recommended_courses:
        if course.credits is None:
            continue
        total += float(course.credits)
    return total


def scenario_only_theory() -> None:
    write_courses([
        {"课程代码": "T1", "课程名称": "TheoryOnly", "学分": "3", "上课信息": "1-15周,星期一第1-2节 一教101", "课程种类": "theory"},
        {"课程代码": "T2", "课程名称": "TheoryOnly", "学分": "3", "上课信息": "1-15周,星期二第1-2节 一教102", "课程种类": "theory"},
    ])
    plan = engine.plan_schedule_with_llm(make_term(), make_profile(), term_id="2026-1", max_credits=6)
    theory_count = count_exact(plan, "TheoryOnly")
    print("only theory count:", theory_count)
    assert theory_count == 1, f"expected 1 theory offering, got {theory_count}"


def scenario_only_lab() -> None:
    write_courses([
        {"课程代码": "L1", "课程名称": "LabOnly", "学分": "3", "上课信息": "1-15周,星期三第1-2节 实验楼201", "课程种类": "lab"},
        {"课程代码": "L2", "课程名称": "LabOnly", "学分": "3", "上课信息": "1-15周,星期四第1-2节 实验楼202", "课程种类": "lab"},
    ])
    plan = engine.plan_schedule_with_llm(make_term(), make_profile(), term_id="2026-1", max_credits=6)
    lab_count = count_exact(plan, "LabOnly")
    print("only lab count:", lab_count)
    assert lab_count == 1, f"expected 1 lab offering, got {lab_count}"


def scenario_both_but_insufficient() -> None:
    write_courses([
        {"课程代码": "C1", "课程名称": "MixedCourse", "学分": "3", "上课信息": "1-15周,星期五第1-2节 一教301", "课程种类": "theory"},
        {"课程代码": "C2", "课程名称": "MixedCourse", "学分": "3", "上课信息": "1-15周,星期五第3-4节 实验楼301", "课程种类": "lab"},
        {"课程代码": "C3", "课程名称": "MixedCourse", "学分": "3", "上课信息": "1-15周,星期五第5-6节 一教302", "课程种类": "theory"},
        {"课程代码": "C4", "课程名称": "MixedCourse", "学分": "3", "上课信息": "1-15周,星期五第7-8节 实验楼302", "课程种类": "lab"},
    ])
    plan = engine.plan_schedule_with_llm(make_term(), make_profile(), term_id="2026-1", max_credits=6)
    mixed_count = count_exact(plan, "MixedCourse")
    print("mixed course count with enough credits:", mixed_count)
    assert mixed_count == 2, f"expected 2 mixed offerings (one theory + one lab), got {mixed_count}"

    plan2 = engine.plan_schedule_with_llm(make_term(), make_profile(), term_id="2026-1", max_credits=3)
    mixed_count2 = count_exact(plan2, "MixedCourse")
    print("mixed course count with insufficient credits:", mixed_count2)
    assert mixed_count2 == 0, f"expected 0 mixed offerings when credits are insufficient, got {mixed_count2}"


def scenario_credit_range() -> None:
    write_courses([
        {"课程代码": "R1", "课程名称": "RangeCourseOne", "学分": "3", "上课信息": "1-15周,星期一第1-2节 一教101", "课程种类": "theory"},
        {"课程代码": "R2", "课程名称": "RangeCourseTwo", "学分": "3", "上课信息": "1-15周,星期二第1-2节 一教102", "课程种类": "theory"},
        {"课程代码": "R3", "课程名称": "RangeCourseThree", "学分": "3", "上课信息": "1-15周,星期三第1-2节 一教103", "课程种类": "theory"},
    ])
    plan = engine.plan_schedule_with_llm(make_term(), make_profile(), term_id="2026-1", min_credits=6, max_credits=9)
    credits = total_plan_credits(plan)
    print("credit range total:", credits)
    assert 6 <= credits <= 9, f"expected total credits within [6, 9], got {credits}"


def scenario_partial_required_keyword() -> None:
    write_courses([
        {"课程代码": "P1", "课程名称": "Python程序设计", "学分": "3", "上课信息": "1-15周,星期一第1-2节 一教101", "课程种类": "theory"},
        {"课程代码": "P2", "课程名称": "Python程序设计", "学分": "3", "上课信息": "1-15周,星期二第1-2节 一教102", "课程种类": "theory"},
        {"课程代码": "E1", "课程名称": "普通选修课", "学分": "3", "上课信息": "1-15周,星期三第1-2节 一教103", "课程种类": "theory"},
    ])
    profile = StudentProfile(major="CS", interests=["我要学Python程序设计"], recommendation_note="我要学Python程序设计")
    plan = engine.plan_schedule_with_llm(make_term(), profile, term_id="2026-1", max_credits=3)
    python_count = count_exact(plan, "Python程序设计")
    print("partial required keyword python count:", python_count)
    assert python_count == 1, f"expected fuzzy required keyword to match Python program design course, got {python_count}"


def scenario_required_beats_conflict() -> None:
    write_courses([
        {"课程代码": "R1", "课程名称": "RequiredCourse", "学分": "3", "上课信息": "1-15周,星期一第1-2节 一教101", "课程种类": "theory"},
        {"课程代码": "N1", "课程名称": "NonRequiredCourse", "学分": "3", "上课信息": "1-15周,星期一第1-2节 一教102", "课程种类": "theory"},
        {"课程代码": "M1", "课程名称": "MixedAtomic", "学分": "3", "上课信息": "1-15周,星期二第1-2节 一教201", "课程种类": "theory"},
        {"课程代码": "M2", "课程名称": "MixedAtomic", "学分": "3", "上课信息": "1-15周,星期三第1-2节 实验楼201", "课程种类": "lab"},
    ])
    profile = StudentProfile(major="CS", interests=["RequiredCourse"], recommendation_note="RequiredCourse")
    plan = engine.plan_schedule_with_llm(make_term(), profile, term_id="2026-1", max_credits=6)
    names = [course.course_name for course in plan.recommended_courses]
    print("required beats conflict names:", names)
    assert any(name == "RequiredCourse" for name in names), "required course should be kept"
    assert "NonRequiredCourse" not in names, "conflicting non-required course should be removed"
    mixed_count = count_exact(plan, "MixedAtomic")
    assert mixed_count in (0, 2), f"mixed core must be all-or-none, got {mixed_count}"


def scenario_no_same_time_dupes() -> None:
    write_courses([
        {"课程代码": "C1", "课程名称": "Alpha", "学分": "3", "上课信息": "1-15周,星期四第1-2节 一教301", "课程种类": "theory"},
        {"课程代码": "C2", "课程名称": "Beta", "学分": "3", "上课信息": "1-15周,星期四第1-2节 一教302", "课程种类": "theory"},
    ])
    profile = StudentProfile(major="CS", interests=[], recommendation_note=None)
    plan = engine.plan_schedule_with_llm(make_term(), profile, term_id="2026-1", max_credits=6)
    names = [course.course_name for course in plan.recommended_courses]
    print("same time result names:", names)
    assert len(names) <= 1, f"courses with the same time slot should not both be selected, got {names}"


def main() -> int:
    backup_path = backup_original()
    patch_llm()
    try:
        scenario_only_theory()
        scenario_only_lab()
        scenario_both_but_insufficient()
        scenario_credit_range()
        scenario_partial_required_keyword()
        scenario_required_beats_conflict()
        scenario_no_same_time_dupes()
        print("all course-kind checks passed")
        return 0
    finally:
        restore_original(backup_path)


if __name__ == "__main__":
    raise SystemExit(main())
