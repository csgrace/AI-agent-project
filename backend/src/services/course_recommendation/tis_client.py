# 运行 python -m src.services.course_recommendation.cli_scrape 从教务系统抓取课表
# uvicorn src.api.server:app --reload --port 8000 运行后端
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import urllib3
from .models import (
    CourseMeeting,
    CourseSchedule,
    TermInfo,
    CompletedCourse,
)
# storage helper not required here

urllib3.disable_warnings()

DEFAULT_SCHEDULE_URL = (
    "https://tis.sustech.edu.cn/xszykb/queryxszykbzong"
)

COURSE_SCHEDULE_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "tis_download"
    / "course_schedule"
)


class TisClientError(RuntimeError):
    pass


def _parse_local_term_label(term_label: str) -> TermInfo:

    match = re.fullmatch(r"(\d{4})-(春|秋)", term_label.strip())

    if match:
        year = int(match.group(1))
        season = match.group(2)
        semester = 1 if season == "春" else 2

        return TermInfo(
            term_id=term_label,
            year=year,
            semester=semester,
            label=term_label,
        )

    return _parse_term_id(term_label)


def _load_schedule_from_json(
    json_path: Path,
    term: TermInfo,
) -> list[CourseMeeting]:

    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    items = payload.get("meetings", [])

    if not isinstance(items, list):
        raise TisClientError(f"课表文件格式错误: {json_path}")

    meetings: list[CourseMeeting] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        raw_credits = item.get("credits")
        credits = None

        if raw_credits is not None:
            try:
                credits = float(raw_credits)
            except (TypeError, ValueError):
                credits = None

        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {"raw": item}

        start_slot = int(item.get("start_slot", 1))
        end_slot = int(item.get("end_slot", 1))

        metadata_raw = metadata.get("raw")
        period_match = None

        if isinstance(metadata_raw, str):
            period_match = re.search(r"\[(\d+(?:-\d+)?)节\]", metadata_raw)
        elif isinstance(metadata_raw, dict):
            raw_text = str(metadata_raw.get("SKSJ") or metadata_raw.get("raw") or "")
            period_match = re.search(r"\[(\d+(?:-\d+)?)节\]", raw_text)

        if period_match:
            parsed_start, parsed_end = _parse_period_to_slots(period_match.group(1))
            if (parsed_start, parsed_end) != (start_slot, end_slot):
                start_slot, end_slot = parsed_start, parsed_end

        meeting = CourseMeeting(
            course_id=(
                str(item.get("course_id"))
                if item.get("course_id") is not None
                else None
            ),
            course_name=str(item.get("course_name") or "未命名课程"),
            instructor=(
                str(item.get("instructor"))
                if item.get("instructor") is not None
                else None
            ),
            location=(
                str(item.get("location"))
                if item.get("location") is not None
                else None
            ),
            day_of_week=int(item.get("day_of_week", 1)),
            start_slot=start_slot,
            end_slot=end_slot,
            weeks=(
                str(item.get("weeks"))
                if item.get("weeks") is not None
                else None
            ),
            credits=credits,
            source="tis_json",
            metadata={
                **metadata,
                "term_id": term.term_id,
            },
        )

        meetings.append(meeting)

    return meetings


def _parse_term_id(term_id: str) -> TermInfo:

    if not term_id:
        raise TisClientError("term_id 不能为空")

    parts = term_id.split("-")

    if (
        len(parts) == 3
        and parts[0].isdigit()
        and parts[1].isdigit()
        and parts[2].isdigit()
    ):
        year = int(parts[1])
        semester = int(parts[2])

        label = (
            f"{parts[0]}-{parts[1]} 学年第{semester}学期"
        )

        return TermInfo(
            term_id=term_id,
            year=year,
            semester=semester,
            label=label,
        )

    if (
        len(parts) == 2
        and parts[0].isdigit()
        and parts[1].isdigit()
    ):
        year = int(parts[0])
        semester = int(parts[1])

        label = f"{year} 学年第{semester}学期"

        return TermInfo(
            term_id=term_id,
            year=year,
            semester=semester,
            label=label,
        )

    raise TisClientError(
        "term_id 格式无效，请使用 2025-2026-2 或 2026-2"
    )


def _parse_period_to_slots(
    period: str,
) -> tuple[int, int]:

    cleaned = period.strip().rstrip("节")

    if not cleaned:
        return 1, 1

    if "-" in cleaned:

        left, right = cleaned.split("-", 1)

        if left.isdigit() and right.isdigit():
            return int(left), int(right)

    if cleaned.isdigit():

        slot = int(cleaned)
        return slot, slot

    match = re.search(r"(\d+)", cleaned)

    if match:

        slot = int(match.group(1))
        return slot, slot

    return 1, 1


def _parse_schedule_entries(
    entries: Iterable[dict[str, Any]],
    term: TermInfo,
) -> list[CourseMeeting]:

    meetings: list[CourseMeeting] = []

    for item in entries:

        raw_text = str(item.get("SKSJ", ""))

        lines = [
            line.strip()
            for line in raw_text.split("\n")
            if line.strip()
        ]

        if not lines:
            continue

        name = lines[0]

        instructor = (
            lines[1].strip("[]")
            if len(lines) > 1
            else None
        )

        location = None
        weeks = None
        period = ""

        if len(lines) > 3:

            brackets = re.findall(
                r"\[(.*?)\]",
                lines[3]
            )

            weeks = (
                brackets[0]
                if len(brackets) > 0
                else None
            )

            location = (
                brackets[1]
                if len(brackets) > 1
                else None
            )

            period = (
                brackets[2]
                if len(brackets) > 2
                else ""
            )

        key = str(item.get("KEY", ""))

        weekday = 1

        match = re.search(
            r"xq(\d)",
            key.lower()
        )

        if match:
            weekday = int(match.group(1))

        start_slot, end_slot = (
            _parse_period_to_slots(period)
        )

        course_id = (
            item.get("KCH")
            or item.get("KCMC")
            or item.get("KCDM")
        )

        credits = None

        if item.get("XF") is not None:

            try:
                credits = float(item.get("XF"))

            except (TypeError, ValueError):
                credits = None

        meetings.append(
            CourseMeeting(
                course_id=(
                    str(course_id)
                    if course_id
                    else None
                ),
                course_name=name,
                instructor=instructor,
                location=location,
                day_of_week=weekday,
                start_slot=start_slot,
                end_slot=end_slot,
                weeks=weeks,
                credits=credits,
                metadata={
                    "raw": item,
                    "term_id": term.term_id,
                },
            )
        )

    return meetings


def fetch_term_schedule(
    term_id: str,
    download_excel: bool = False,
) -> CourseSchedule:

    from ...tools.cas_course.utils import login
    from .excel_parser import parse_schedule_excel

    term = _parse_local_term_label(term_id)

    json_path = COURSE_SCHEDULE_DIR / f"{term_id}.json"

    if json_path.exists():
        meetings = _load_schedule_from_json(json_path, term)
        return CourseSchedule(
            term=term,
            meetings=meetings,
            source="tis_json",
        )

    excel_path = os.path.join(
        os.path.dirname(__file__),
        "../../../data/tis_download/course_schedule/学生课表.xlsx"
    )
    downloaded_path = login() if download_excel else None

    target_path = downloaded_path or excel_path

    # If the Excel file does not exist, fall back to empty meetings (JSON fallback handled above)
    if not target_path or not os.path.exists(target_path):
        print(f"[TIS] Excel schedule not found at {target_path!s}, falling back to local JSON if available.")
        return CourseSchedule(term=term, meetings=[], source="none")

    try:
        meetings = parse_schedule_excel(target_path)
    except FileNotFoundError:
        print(f"[TIS] Excel schedule missing during parse: {target_path!s}")
        meetings = []
    except Exception as exc:
        # If parsing fails, log and return empty meetings so API can degrade gracefully
        print(f"[TIS] Failed to parse Excel schedule: {exc}")
        meetings = []

    return CourseSchedule(
        term=term,
        meetings=meetings,
        source="tis_excel",
    )


def fetch_all_term_schedules() -> list[dict[str, str]]:
    from ...tools.cas_course.utils import download_all_term_schedules
    return download_all_term_schedules()


def fetch_completed_courses(refresh: bool = False, major: str = "") -> list[CompletedCourse]:
    """从 completed_courses_detailed.json 读取已修课程，支持根据专业生成课程类型。"""
    import importlib
    import json

    backend_root = Path(__file__).parents[3]
    detailed_json = backend_root / "data" / "tis_download" / "completed_courses_detailed.json"

    if refresh or not detailed_json.exists():
        try:
            gen_module = importlib.import_module("src.services.course_recommendation.generate_completed_courses")
            gen_module.build_completed_courses(force=True, major=major)
        except Exception as e:
            print(f"[TIS] 重新生成已修课程失败: {e}")
            return []

    if not detailed_json.exists():
        print("[TIS] 已修课程文件不存在，请先运行生成脚本或触发刷新。")
        return []

    try:
        with open(detailed_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[TIS] 读取 completed_courses_detailed.json 失败: {e}")
        return []

    courses_data = data.get("courses", []) if isinstance(data, dict) else []
    completed: list[CompletedCourse] = []

    for course in courses_data:
        if not isinstance(course, dict):
            continue

        credits_str = course.get("学分", "")
        try:
            credits = float(credits_str) if credits_str else None
        except (TypeError, ValueError):
            credits = None

        completed.append(
            CompletedCourse(
                course_id=None,
                course_name=str(course.get("course_name", "")),
                term_id=course.get("term_id"),
                grade=None,
                credits=credits,
                status=course.get("status", "completed"),
                metadata={
                    "课程类别": course.get("课程类别", ""),
                    "课程类型": course.get("课程类型", ""),
                },
            )
        )

    return completed


def fetch_course_offerings(
    term_id: str,
) -> list[dict[str, Any]]:
    """从课程专用向量索引中检索课程 offerings"""
    try:
        import sys

        backend_root = Path(__file__).parents[3]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))

        from src.rag_pipeline.vector_store import VectorStore
        from src.rag_pipeline.embeddings import SentenceTransformerEmbeddings
        from src.rag_pipeline.models import ChunkRecord
        import faiss

        storage_dir = backend_root / "storage"
        chunks_path = storage_dir / "course_kb_chunks.json"
        faiss_path = storage_dir / "course_kb_index.faiss"

        if not chunks_path.exists() or not faiss_path.exists():
            print("[TIS] 课程专用索引不存在，请先运行: python -m src.ingestion.index_course_knowledge_base")
            return []

        with open(chunks_path, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)

        chunks: list[ChunkRecord] = []
        for chunk_data in chunks_data:
            if not isinstance(chunk_data, dict):
                continue
            chunks.append(ChunkRecord(
                source_name=chunk_data["source_name"],
                source_path=chunk_data["source_path"],
                chunk_id=chunk_data["chunk_id"],
                text=chunk_data["text"],
                start_char=chunk_data.get("start_char", 0),
                end_char=chunk_data.get("end_char", 0),
                page_count=chunk_data.get("page_count", 0),
            ))

        embeddings = SentenceTransformerEmbeddings()
        index = faiss.read_index(str(faiss_path))

        test_emb = embeddings.encode(["test"])
        if test_emb.ndim == 1:
            test_emb = test_emb.reshape(1, -1)
        if test_emb.shape[1] != index.d:
            print(
                f"[TIS] Embedding dimension mismatch "
                f"(index={index.d}, model={test_emb.shape[1]}). "
                f"Rebuild with: python src\\ingestion\\index_course_knowledge_base.py"
            )
            return []

        vector_store = VectorStore(embeddings=embeddings)
        vector_store.index = index
        vector_store.chunks = chunks

        query = f"{term_id} 课程 开课 教学班 教师 地点 周次 节次"
        results = vector_store.search(query, k=30)

        offerings: list[dict[str, Any]] = []
        for result in results:
            course_info = extract_course_from_chunk(result.text, result.source_name)
            if course_info and course_info.get("course_name"):
                offerings.append(course_info)

        print(f"[TIS] 从课程索引检索到 {len(offerings)} 门课程")
        return offerings
    except Exception as e:
        import traceback
        print(f"[TIS] fetch_course_offerings 失败: {e}")
        traceback.print_exc()
        return []


def extract_course_from_chunk(text: str, source_name: str) -> dict[str, Any]:
    """从 chunk 文本中提取课程信息"""
    import re

    course_info: dict[str, Any] = {
        "course_name": "",
        "course_id": None,
        "credits": None,
        "teacher": "",
        "location": "",
        "weeks": "",
        "day_of_week": None,
        "start_slot": None,
        "end_slot": None,
    }

    name_match = re.search(r'课程名称[:\s]*([^|\n]+)', text)
    if name_match:
        course_info["course_name"] = name_match.group(1).strip()

    code_match = re.search(r'课程代码[:\s]*([^|\n]+)', text)
    if code_match:
        course_info["course_id"] = code_match.group(1).strip()

    teacher_match = re.search(r'教师[:\s]*([^|\n]+)', text)
    if teacher_match:
        course_info["teacher"] = teacher_match.group(1).strip()

    credit_match = re.search(r'学分[:\s]*([\d.]+)', text)
    if credit_match:
        try:
            course_info["credits"] = float(credit_match.group(1))
        except Exception:
            pass

    schedule_match = re.search(r'上课信息[:\s]*([^|\n]+)', text)
    if schedule_match:
        course_info["location"] = schedule_match.group(1).strip()

    return course_info


def fetch_term_list() -> list[TermInfo]:

    if COURSE_SCHEDULE_DIR.exists():
        terms: list[TermInfo] = []

        for path in COURSE_SCHEDULE_DIR.glob("*.json"):
            try:
                terms.append(_parse_local_term_label(path.stem))
            except TisClientError:
                continue

        if terms:
            ordered = sorted(
                terms,
                key=lambda term: (term.year, term.semester),
                reverse=True,
            )
            for term in ordered:
                term.status = infer_term_status(term)
            return ordered

    current_year = datetime.now().year
    current_month = datetime.now().month
    current_semester = 1 if current_month < 8 else 2

    terms: list[TermInfo] = []
    for offset in range(4):
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

    return terms


def infer_term_status(term: TermInfo) -> str:

    if term.status != "unknown":
        return term.status

    today = datetime.today()

    if today.month >= 8:
        current_year = today.year
        current_semester = 2
    elif today.month >= 2:
        current_year = today.year
        current_semester = 1
    else:
        current_year = today.year - 1
        current_semester = 2

    if (term.year, term.semester) < (current_year, current_semester):
        return "completed"

    if (term.year, term.semester) > (current_year, current_semester):
        return "future"

    return "current"
