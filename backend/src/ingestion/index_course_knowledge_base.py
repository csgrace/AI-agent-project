"""Build course KB from schedule and arrangement data.

This script creates a dedicated vector index for course recommendation analysis
without overwriting the generic document QA index files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import faiss
import fitz
import os

from src.rag_pipeline.chunker import chunk_documents
from src.rag_pipeline.models import DocumentRecord
from src.rag_pipeline.vector_store import VectorStore

os.environ["DASHSCOPE_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"

DEFAULT_SCHEDULE_DIR = DATA_DIR / "tis_download" / "course_schedule"
DEFAULT_ARRANGEMENT_DIR = DATA_DIR / "course_arrangement"
DEFAULT_SUSTECH_ONLINE_DIR = DATA_DIR / "sustech.online"
DEFAULT_FULL_COURSE_TABLE_PATH = DATA_DIR / "tis_download" / "full_course_table" / "all_courses_merged.json"
DEFAULT_ACADEMIC_PROGRESS_DIR = DATA_DIR / "tis_download"

DEFAULT_CHUNKS_PATH = STORAGE_DIR / "course_kb_chunks.json"
DEFAULT_FAISS_PATH = STORAGE_DIR / "course_kb_index.faiss"
DEFAULT_MANIFEST_PATH = STORAGE_DIR / "course_kb_manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build course recommendation KB from schedule JSON "
            "and arrangement PDFs"
        )
    )
    parser.add_argument(
        "--schedule-dir",
        default=str(DEFAULT_SCHEDULE_DIR),
        help="Directory containing course schedule JSON files",
    )
    parser.add_argument(
        "--arrangement-dir",
        default=str(DEFAULT_ARRANGEMENT_DIR),
        help="Directory containing course arrangement PDFs/TXTs",
    )
    parser.add_argument(
        "--chunks-path",
        default=str(DEFAULT_CHUNKS_PATH),
        help="Output JSON path for chunk records",
    )
    parser.add_argument(
        "--faiss-path",
        default=str(DEFAULT_FAISS_PATH),
        help="Output path for FAISS index",
    )
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Output JSON path for indexing manifest",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=900,
        help="Chunk size used for splitting loaded documents",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=140,
        help="Chunk overlap used for splitting loaded documents",
    )
    return parser.parse_args()


def _relative_source_name(file_path: Path, base_dir: Path) -> str:
    if file_path.is_relative_to(base_dir):
        return str(file_path.relative_to(base_dir)).replace("\\", "/")
    return file_path.name


def _iter_files(folder: Path, suffixes: set[str]) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []

    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _load_pdf_document(file_path: Path) -> DocumentRecord | None:
    try:
        with fitz.open(str(file_path)) as pdf:
            text_parts = [page.get_text("text") for page in pdf]
            text = "\n".join(
                part.strip() for part in text_parts if part.strip()
            )
            if not text:
                return None

            return DocumentRecord(
                source_name=_relative_source_name(file_path, DATA_DIR),
                source_path=str(file_path),
                text=text,
                page_count=len(pdf),
            )
    except Exception:
        return None


def _load_text_document(file_path: Path) -> DocumentRecord | None:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            return None
        return DocumentRecord(
            source_name=_relative_source_name(file_path, DATA_DIR),
            source_path=str(file_path),
            text=text,
            page_count=1,
        )
    except Exception:
        return None


def _load_json_document(file_path: Path) -> DocumentRecord | None:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if not text.strip():
            return None
        return DocumentRecord(
            source_name=_relative_source_name(file_path, DATA_DIR),
            source_path=str(file_path),
            text=text,
            page_count=1,
        )
    except Exception:
        return None


def _build_schedule_text(payload: dict, *, fallback_term: str) -> str:
    term_label = str(payload.get("term_label") or fallback_term)
    meetings = payload.get("meetings") or []

    lines: list[str] = [f"学期: {term_label}", f"课程条目数: {len(meetings)}", ""]

    for index, meeting in enumerate(meetings, start=1):
        if not isinstance(meeting, dict):
            continue
        course_name = str(meeting.get("course_name") or "未知课程")
        instructor = str(meeting.get("instructor") or "未知教师")
        day_of_week = meeting.get("day_of_week", "?")
        start_slot = meeting.get("start_slot", "?")
        end_slot = meeting.get("end_slot", "?")
        weeks = str(meeting.get("weeks") or "未知周次")
        location = str(meeting.get("location") or "未知地点")
        credits = meeting.get("credits")
        course_id = meeting.get("course_id")

        lines.append(
            (
                f"{index}. 课程: {course_name} | 教师: {instructor} | "
                f"星期: {day_of_week} | 节次: {start_slot}-{end_slot} | "
                f"周次: {weeks} | 地点: {location} | "
                f"课程号: {course_id if course_id is not None else '未知'} | "
                f"学分: {credits if credits is not None else '未知'}"
            )
        )

    return "\n".join(lines).strip()


def _load_schedule_documents(schedule_dir: Path) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []
    for file_path in _iter_files(schedule_dir, suffixes={".json"}):
        try:
            payload = json.loads(
                file_path.read_text(encoding="utf-8", errors="ignore")
            )
            if not isinstance(payload, dict):
                continue

            text = _build_schedule_text(payload, fallback_term=file_path.stem)
            if not text:
                continue

            documents.append(
                DocumentRecord(
                    source_name=_relative_source_name(file_path, DATA_DIR),
                    source_path=str(file_path),
                    text=text,
                    page_count=1,
                )
            )
        except Exception:
            continue

    return documents


def _load_arrangement_documents(arrangement_dir: Path) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []

    for file_path in _iter_files(arrangement_dir, suffixes={".pdf", ".txt"}):
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            record = _load_pdf_document(file_path)
        elif suffix == ".txt":
            record = _load_text_document(file_path)
        else:
            record = None

        if record is not None:
            documents.append(record)

    return documents


def _load_misc_documents(
    *,
    sustech_online_dir: Path,
    full_course_table_path: Path,
    academic_progress_dir: Path,
) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []

    for file_path in _iter_files(sustech_online_dir, suffixes={".json", ".html", ".htm", ".md", ".txt"}):
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            record = _load_json_document(file_path)
        else:
            record = _load_text_document(file_path)
        if record is not None:
            documents.append(record)

    if full_course_table_path.exists():
        record = _load_json_document(full_course_table_path)
        if record is not None:
            documents.append(record)

    for file_path in _iter_files(academic_progress_dir, suffixes={".json"}):
        if file_path.name.startswith("academic_progress_"):
            record = _load_json_document(file_path)
            if record is not None:
                documents.append(record)

    return documents


def main() -> None:
    args = parse_args()

    schedule_dir = Path(args.schedule_dir)
    arrangement_dir = Path(args.arrangement_dir)
    chunks_path = Path(args.chunks_path)
    faiss_path = Path(args.faiss_path)
    manifest_path = Path(args.manifest_path)

    schedule_docs = _load_schedule_documents(schedule_dir)
    arrangement_docs = _load_arrangement_documents(arrangement_dir)
    misc_docs = _load_misc_documents(
        sustech_online_dir=DEFAULT_SUSTECH_ONLINE_DIR,
        full_course_table_path=DEFAULT_FULL_COURSE_TABLE_PATH,
        academic_progress_dir=DEFAULT_ACADEMIC_PROGRESS_DIR,
    )
    documents = [*schedule_docs, *arrangement_docs, *misc_docs]

    print("Starting Course KB indexing...")
    print(f"Schedule source: {schedule_dir}")
    print(f"Arrangement source: {arrangement_dir}")
    print(f"Loaded {len(schedule_docs)} schedule documents")
    print(f"Loaded {len(arrangement_docs)} arrangement documents")
    print(f"Loaded {len(misc_docs)} extra documents")
    print(f"Total loaded documents: {len(documents)}")

    if not documents:
        raise RuntimeError(
            "No documents loaded. Please check source directories."
        )

    chunks = chunk_documents(
        documents,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(f"Created {len(chunks)} chunks")

    vector_store = VectorStore()
    vector_store.build(chunks)
    print("Built vector index")

    chunks_path.parent.mkdir(parents=True, exist_ok=True)

    with chunks_path.open("w", encoding="utf-8") as f:
        json.dump(
            [chunk.to_dict() for chunk in chunks],
            f,
            ensure_ascii=False,
            indent=2,
        )

    if vector_store.index is None:
        raise RuntimeError("Vector index build failed: empty index")
    faiss.write_index(vector_store.index, str(faiss_path))

    manifest = {
        "schedule_dir": str(schedule_dir),
        "arrangement_dir": str(arrangement_dir),
        "sustech_online_dir": str(DEFAULT_SUSTECH_ONLINE_DIR),
        "full_course_table_path": str(DEFAULT_FULL_COURSE_TABLE_PATH),
        "academic_progress_dir": str(DEFAULT_ACADEMIC_PROGRESS_DIR),
        "chunks_path": str(chunks_path),
        "faiss_path": str(faiss_path),
        "schedule_documents": len(schedule_docs),
        "arrangement_documents": len(arrangement_docs),
        "extra_documents": len(misc_docs),
        "total_documents": len(documents),
        "total_chunks": len(chunks),
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("Course KB build completed.")
    print(f"Chunks file: {chunks_path}")
    print(f"FAISS file: {faiss_path}")
    print(f"Manifest file: {manifest_path}")


if __name__ == "__main__":
    main()
