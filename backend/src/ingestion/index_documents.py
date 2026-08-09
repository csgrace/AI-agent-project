"""Unified document index builder — RAG QA + course recommendation.

Indexes ALL documents (campus PDFs, course schedules, course arrangements,
full course table, academic progress) into a single PostgreSQL + vector index.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import os

import fitz

current_dir = Path(__file__).resolve().parent
repo_root = current_dir.parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root.parent))
    sys.path.insert(0, str(repo_root))

from src.rag_pipeline.loader import load_documents, DOCUMENTS_DIR
from src.rag_pipeline.chunker import chunk_documents
from src.rag_pipeline.models import DocumentRecord
from src.rag_pipeline.vector_store import VectorStore
from src.rag_pipeline.pg_store import (
    init_db,
    insert_document,
    count_documents,
    count_chunks,
)

os.environ["DASHSCOPE_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

# Course data paths
SCHEDULE_DIR = DATA_DIR / "tis_download" / "course_schedule"
ARRANGEMENT_DIR = DATA_DIR / "course_arrangement"
FULL_COURSE_TABLE = DATA_DIR / "tis_download" / "full_course_table" / "all_courses_merged.json"


# ── Course data loaders ────────────────────────────────────────────


def _rel_path(file_path: Path) -> str:
    if file_path.is_relative_to(DATA_DIR):
        return str(file_path.relative_to(DATA_DIR)).replace("\\", "/")
    return file_path.name


def _iter_files(folder: Path, suffixes: set[str]) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)


def _load_schedule_documents() -> list[DocumentRecord]:
    docs: list[DocumentRecord] = []
    for fp in _iter_files(SCHEDULE_DIR, suffixes={".json"}):
        try:
            data = json.loads(fp.read_text(encoding="utf-8", errors="ignore"))
            if not isinstance(data, dict):
                continue
            term = str(data.get("term_label") or fp.stem)
            meetings = data.get("meetings") or []
            lines = [f"学期: {term}", f"课程条目数: {len(meetings)}", ""]
            for i, m in enumerate(meetings, 1):
                if not isinstance(m, dict):
                    continue
                lines.append(
                    f"{i}. 课程: {m.get('course_name','?')} | 教师: {m.get('instructor','?')} | "
                    f"星期: {m.get('day_of_week','?')} | 节次: {m.get('start_slot','?')}-{m.get('end_slot','?')} | "
                    f"周次: {m.get('weeks','?')} | 地点: {m.get('location','?')} | "
                    f"课程号: {m.get('course_id','?')} | 学分: {m.get('credits','?')}"
                )
            text = "\n".join(lines).strip()
            if text:
                docs.append(DocumentRecord(source_name=_rel_path(fp), source_path=str(fp), text=text, page_count=1, title=fp.stem))
        except Exception:
            continue
    return docs


def _load_arrangement_documents() -> list[DocumentRecord]:
    docs: list[DocumentRecord] = []
    for fp in _iter_files(ARRANGEMENT_DIR, suffixes={".pdf", ".txt"}):
        try:
            if fp.suffix.lower() == ".pdf":
                with fitz.open(str(fp)) as pdf:
                    text = "\n".join(p.get_text("text").strip() for p in pdf if p.get_text("text").strip())
            else:
                text = fp.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                docs.append(DocumentRecord(source_name=_rel_path(fp), source_path=str(fp), text=text, page_count=1, title=fp.stem))
        except Exception:
            continue
    return docs


def _load_course_table() -> list[DocumentRecord]:
    if not FULL_COURSE_TABLE.exists():
        return []
    try:
        data = json.loads(FULL_COURSE_TABLE.read_text(encoding="utf-8", errors="ignore"))
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return [DocumentRecord(source_name=_rel_path(FULL_COURSE_TABLE), source_path=str(FULL_COURSE_TABLE), text=text, page_count=1, title="全校课程表")]
    except Exception:
        return []


def _load_academic_progress() -> list[DocumentRecord]:
    docs: list[DocumentRecord] = []
    for fp in _iter_files(DATA_DIR / "tis_download", suffixes={".json"}):
        if not fp.name.startswith("academic_progress_"):
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8", errors="ignore"))
            text = json.dumps(data, ensure_ascii=False, indent=2)
            docs.append(DocumentRecord(source_name=_rel_path(fp), source_path=str(fp), text=text, page_count=1, title=fp.stem))
        except Exception:
            continue
    return docs


# ── Main ────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified index builder (RAG QA + course recommendation)")
    parser.add_argument("--folder", default=str(DOCUMENTS_DIR), help="Folder for campus PDF/TXT documents")
    parser.add_argument("--no-course-data", action="store_true", help="Skip course schedule/arrangement/table data")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Unified Index Builder — RAG QA + Course Recommendation")
    print(f"Campus docs folder: {args.folder}")

    # 1. Init DB
    init_db()
    print(f"  PostgreSQL: {count_documents()} docs, {count_chunks()} chunks currently stored.")

    # 2. Load all documents
    documents = load_documents(str(args.folder))
    print(f"Campus documents: {len(documents)}")

    if not args.no_course_data:
        schedule = _load_schedule_documents()
        arrangements = _load_arrangement_documents()
        course_table = _load_course_table()
        progress = _load_academic_progress()
        course_docs = [*schedule, *arrangements, *course_table, *progress]
        print(f"Course data: schedule={len(schedule)}, arrangement={len(arrangements)}, table={len(course_table)}, progress={len(progress)}")

        # Deduplicate by source_name, course data wins (more structured)
        seen = {d.source_name for d in documents}
        added = 0
        for d in course_docs:
            if d.source_name not in seen:
                documents.append(d)
                seen.add(d.source_name)
                added += 1
        print(f"Added {added} unique course documents (dedup by source_name)")

    print(f"Total documents to index: {len(documents)}")

    # 3. Store in PG
    for doc in documents:
        insert_document(doc)
    print(f"Stored {len(documents)} documents in PostgreSQL")

    # 4. Semantic chunking
    chunks = chunk_documents(documents)
    print(f"Created {len(chunks)} chunks (semantic chunking)")

    # 5. Build vector index
    vector_store = VectorStore()
    vector_store.build(chunks)
    print("Vector index built and stored in PostgreSQL")

    print(f"\nStorage summary:")
    print(f"  PostgreSQL documents: {count_documents()}")
    print(f"  PostgreSQL chunks:    {count_chunks()} (with embedding vectors)")
    print(f"  Search via:           cosine_similarity() in PostgreSQL")


if __name__ == "__main__":
    main()
