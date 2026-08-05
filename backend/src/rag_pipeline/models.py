"""Data models for the document QA pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class DocumentRecord:
    source_name: str
    source_path: str
    text: str
    page_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChunkRecord:
    source_name: str
    source_path: str
    chunk_id: str
    text: str
    start_char: int
    end_char: int
    page_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchResult:
    source_name: str
    source_path: str
    chunk_id: str
    text: str
    score: float
    start_char: int = 0
    end_char: int = 0
    page_count: int = 0
    page_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IngestSummary:
    source_name: str
    page_count: int
    chunk_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerResult:
    answer: str
    citations: list[SearchResult]
    confidence: float
    answerable: bool
    needs_clarification: bool
    prompt: str = ""
    detected_course_scope: str | None = None
    keywords: dict[str, list[str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["citations"] = [citation.to_dict() for citation in self.citations]
        # ensure keywords serializable
        payload["keywords"] = payload.get("keywords") or {}
        return payload


def coerce_document(value: DocumentRecord | Mapping[str, Any]) -> DocumentRecord:
    if isinstance(value, DocumentRecord):
        return value

    source_name = str(value.get("source_name", value.get("source", "unknown.pdf")))
    source_path = str(value.get("source_path", value.get("path", source_name)))
    text = str(value.get("text", ""))
    page_count = int(value.get("page_count", 0))
    return DocumentRecord(
        source_name=source_name,
        source_path=source_path,
        text=text,
        page_count=page_count,
    )


def coerce_chunk(value: ChunkRecord | Mapping[str, Any]) -> ChunkRecord:
    if isinstance(value, ChunkRecord):
        return value

    source_name = str(value.get("source_name", value.get("source", "unknown.pdf")))
    source_path = str(value.get("source_path", value.get("path", source_name)))
    chunk_id = str(value.get("chunk_id", value.get("id", "chunk-0")))
    text = str(value.get("text", ""))
    start_char = int(value.get("start_char", 0))
    end_char = int(value.get("end_char", len(text)))
    page_count = int(value.get("page_count", 0))
    return ChunkRecord(
        source_name=source_name,
        source_path=source_path,
        chunk_id=chunk_id,
        text=text,
        start_char=start_char,
        end_char=end_char,
        page_count=page_count,
    )
