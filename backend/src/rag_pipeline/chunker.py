"""Document chunking strategy for retrieval."""

from __future__ import annotations

import re
from typing import Sequence
from pathlib import Path

from .models import ChunkRecord, DocumentRecord, coerce_document


def _normalize_text(text: str) -> str:
    # Remove excessive whitespace but keep some structure
    return re.sub(r"\s+", " ", text).strip()


def chunk_document(
    document: DocumentRecord,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[ChunkRecord]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = _normalize_text(document.text)
    if not text:
        return []


    source_path = Path(document.source_name)

    if len(source_path.parts) >= 2:
        course_hint = f"{source_path.parts[0]}/{source_path.parts[1]}"
    else:
        course_hint = source_path.parts[0] if source_path.parts else "Unknown"
    header = f"[Course: {course_hint} | File: {source_path.name}]\n"
    header_len = len(header)
    
    # Adjust effective chunk size to account for header
    effective_chunk_size = chunk_size - header_len
    if effective_chunk_size <= 0:
        effective_chunk_size = chunk_size // 2 # Fallback
        
    step = effective_chunk_size - overlap
    chunks: list[ChunkRecord] = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = min(len(text), start + effective_chunk_size)
        raw_text = text[start:end].strip()

        if raw_text:
            # Prepend the header to every chunk text
            final_text = f"{header}{raw_text}"
            chunks.append(
                ChunkRecord(
                    source_name=document.source_name,
                    source_path=document.source_path,
                    chunk_id=f"{document.source_name}#chunk-{chunk_index}",
                    text=final_text,
                    start_char=start,
                    end_char=end,
                    page_count=document.page_count,
                )
            )

        if end >= len(text):
            break

        start += step
        chunk_index += 1

    return chunks


def chunk_documents(
    documents: Sequence[DocumentRecord | dict],
    *,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []

    for document in documents:
        chunks.extend(
            chunk_document(
                coerce_document(document),
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )

    return chunks


def chunk_text(
    documents: Sequence[DocumentRecord | dict],
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[ChunkRecord]:
    return chunk_documents(documents, chunk_size=chunk_size, overlap=overlap)
