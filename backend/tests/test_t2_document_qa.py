"""Tests for the T2 document QA pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import fitz
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.document_qa import (  # noqa: E402
    DocumentQAService,
    VectorStore,
    build_rag_prompt,
    chunk_documents,
    load_pdfs,
)


class FakeEmbeddings:
    def encode(self, texts):
        payload = [texts] if isinstance(texts, str) else list(texts)
        vectors = []

        for text in payload:
            lowered = text.lower()
            vector = np.zeros(3, dtype=np.float32)
            if "physics" in lowered:
                vector[0] = 1.0
            if "math" in lowered:
                vector[1] = 1.0
            if "calendar" in lowered or "syllabus" in lowered:
                vector[2] = 1.0
            if not vector.any():
                vector[2] = 1.0
            vectors.append(vector)

        return np.asarray(vectors, dtype=np.float32)


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_load_pdfs_recursively_extracts_text(tmp_path):
    nested_dir = tmp_path / "school" / "course"
    nested_dir.mkdir(parents=True)
    pdf_path = nested_dir / "sample.pdf"
    _write_pdf(pdf_path, "Physics class handout")

    documents = load_pdfs(tmp_path)

    assert len(documents) == 1
    assert documents[0].source_name == "school/course/sample.pdf"
    assert "Physics class handout" in documents[0].text


def test_chunk_documents_uses_overlap(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _write_pdf(pdf_path, "abcdefghijklmnopqrst")

    documents = load_pdfs(tmp_path)
    chunks = chunk_documents(documents, chunk_size=10, overlap=2)

    assert len(chunks) == 3
    assert chunks[0].text == "abcdefghij"
    assert chunks[1].text.startswith("ij")


def test_semantic_search_returns_best_chunk():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {"source_name": "physics.pdf", "text": "physics mechanics note", "chunk_id": "a"},
            {"source_name": "math.pdf", "text": "math algebra note", "chunk_id": "b"},
        ]
    )

    results = service.search("physics", k=2)

    assert len(results) == 2
    assert results[0].source_name == "physics.pdf"
    assert results[0].score >= results[1].score


def test_low_confidence_query_requests_clarification():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {"source_name": "physics.pdf", "text": "physics mechanics note", "chunk_id": "a"},
            {"source_name": "math.pdf", "text": "math algebra note", "chunk_id": "b"},
        ]
    )

    result = service.answer_question("biology", min_confidence=0.25)

    assert result.answerable is False
    assert result.needs_clarification is True
    assert result.confidence == 0.0
    assert "补充" in result.answer or "检索" in result.answer


def test_irrelevant_course_match_is_not_treated_as_answer():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {
                "source_name": "bb/Announcements – 计算伦理学（2026春）/ethics.pdf",
                "text": "Nuremberg Code and research ethics principles",
                "chunk_id": "a",
            },
            {
                "source_name": "bb/Announcements – 计算伦理学（2026春）/policy.pdf",
                "text": "Human subject protection and experimentation ethics",
                "chunk_id": "b",
            },
        ]
    )

    result = service.answer_question("计算机伦理的课程分数构成", course_scope="bb/Announcements – 计算伦理学（2026春）")

    assert result.answerable is False
    assert result.needs_clarification is True
    assert result.citations
    assert result.confidence < 0.25
    assert "补充" in result.answer or "具体" in result.answer


def test_search_respects_course_scope_filter():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {
                "source_name": "bb/公告 – 阿拉伯世界的1500年（2026春）/a.pdf",
                "text": "physics mechanics note",
                "chunk_id": "a",
            },
            {
                "source_name": "bb/公告 – 计算伦理学（2026春）/b.pdf",
                "text": "physics score percentage syllabus",
                "chunk_id": "b",
            },
        ]
    )

    results = service.search("physics", k=2, course_scope="bb/公告 – 计算伦理学（2026春）")

    assert results
    assert all("计算伦理学" in item.source_name for item in results)


def test_detect_course_scope_from_query():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {
                "source_name": "bb/公告 – 计算伦理学（2026春）/b.pdf",
                "text": "ethics score percentage syllabus",
                "chunk_id": "b",
            },
            {
                "source_name": "bb/公告 – 软件工程（2026春）/c.pdf",
                "text": "software engineering project",
                "chunk_id": "c",
            },
        ]
    )

    detected = service.detect_course_scope("请问计算机伦理学这门课的分数占比")

    assert detected is not None
    assert "计算伦理学" in detected


def test_prompt_contains_context_sources():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {"source_name": "physics.pdf", "text": "physics mechanics note", "chunk_id": "a"},
        ]
    )
    result = service.search("physics", k=1)
    prompt = build_rag_prompt("what is physics", result)

    assert "physics.pdf" in prompt
    assert "Question: what is physics" in prompt


def test_grading_query_extracts_percentage_answer():
    service = DocumentQAService(vector_store=VectorStore(embeddings=FakeEmbeddings()))
    service.set_chunks(
        [
            {
                "source_name": "bb/Announcements – 计算伦理学（2026春）/file_28.pdf",
                "text": "Deliverable and grading: Attendance 10%, Project 40%, Final Exam 50%",
                "chunk_id": "g1",
            },
            {
                "source_name": "bb/Announcements – 计算伦理学（2026春）/file_23.pdf",
                "text": "Ethics in AI image search and implicit association test",
                "chunk_id": "g2",
            },
        ]
    )

    result = service.answer_question("计算机伦理学的分数构成", course_scope="bb/Announcements – 计算伦理学（2026春）")

    assert "Attendance" in result.answer
    assert "10%" in result.answer
    assert result.answerable is True


def test_vector_store_search_returns_candidate_pool():
    store = VectorStore(embeddings=FakeEmbeddings())
    chunks = [
        {"source_name": "c1.pdf", "text": "physics note", "chunk_id": "1"},
        {"source_name": "c2.pdf", "text": "physics chapter", "chunk_id": "2"},
        {"source_name": "c3.pdf", "text": "physics lab", "chunk_id": "3"},
    ]

    service = DocumentQAService(vector_store=store)
    service.set_chunks(chunks)
    service.build_index()

    results = store.search("physics", k=1, fetch_k=3)

    assert len(results) == 3
