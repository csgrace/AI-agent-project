"""Semantic chunking — splits on topic shifts detected via embedding similarity.

Adjacent sentences whose cosine similarity drops below a threshold
indicate a topic boundary.  Chunks are formed by merging sentences
within a target size, respecting those semantic boundaries.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import numpy as np

from .models import ChunkRecord, DocumentRecord, coerce_document

# ── Module-level embedder cache (reused across all chunk_document calls) ─

_EMBEDDER = None

def _get_embedder():
    """Return a cached SentenceTransformerEmbeddings instance."""
    global _EMBEDDER
    if _EMBEDDER is None:
        from .embeddings import SentenceTransformerEmbeddings
        _EMBEDDER = SentenceTransformerEmbeddings()
    return _EMBEDDER


# ── Sentence splitting ─────────────────────────────────────────────

_SENTENCE_END = re.compile(r"[。！？!?\n]+")


def _split_sentences(text: str) -> list[str]:
    raw = _SENTENCE_END.split(text)
    sentences = [part.strip() for part in raw if part.strip()]
    if not sentences:
        stripped = text.strip()
        if stripped:
            sentences = [stripped]
    return sentences


# ── Helpers ─────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _build_header(source_path: Path) -> str:
    if len(source_path.parts) >= 2:
        course_hint = f"{source_path.parts[0]}/{source_path.parts[1]}"
    else:
        course_hint = source_path.parts[0] if source_path.parts else "Unknown"
    return f"[Course: {course_hint} | File: {source_path.name}]\n"


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-d vectors."""
    dot = float(np.dot(a, b))
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Semantic chunking ───────────────────────────────────────────────

# Thresholds
_SIM_THRESHOLD = 0.50       # cosine similarity below this → topic boundary
_MAX_CHUNK_CHARS = 2000     # hard cap, ignore similarity if exceeded
_MIN_CHUNK_CHARS = 200      # don't split if chunk is still this small


def chunk_document(
    document: DocumentRecord,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[ChunkRecord]:
    """Semantic chunking via embedding similarity between adjacent sentences.

    1. Split text into sentences.
    2. Compute embedding for each sentence.
    3. Compute cosine similarity between each adjacent sentence pair.
    4. Merge sentences into chunks.  A chunk boundary is inserted when:
       - The chunk is ≥ 60% of *chunk_size* **and** adjacent sentence
         similarity < 0.50 (a topic shift), **or**
       - The chunk exceeds *max_chunk_chars* (hard cap), **or**
       - The document ends.
    5. Overlap is applied by copying the last few sentences of the
       previous chunk as a prefix for the next.
    """
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
    header = _build_header(source_path)
    header_len = len(header)
    effective_chunk_size = max(chunk_size - header_len, chunk_size // 2)

    sentences = _split_sentences(text)
    if not sentences:
        return []

    # Single-sentence document — just return it
    if len(sentences) == 1:
        final_text = f"{header}{sentences[0]}"
        return [ChunkRecord(
            source_name=document.source_name,
            source_path=document.source_path,
            chunk_id=f"{document.source_name}#chunk-0",
            text=final_text[:_MAX_CHUNK_CHARS],
            start_char=0,
            end_char=len(sentences[0]),
            page_count=document.page_count,
        )]

    # Compute sentence embeddings (use cached embedder from module-level)
    sent_embs = _get_embedder().encode(sentences)
    if sent_embs.ndim == 1:
        sent_embs = sent_embs.reshape(1, -1)

    # Compute adjacent similarities
    similarities = np.zeros(len(sentences) - 1, dtype=np.float32)
    for i in range(len(sentences) - 1):
        similarities[i] = _cosine_sim(sent_embs[i], sent_embs[i + 1])

    # Build chunks
    chunks: list[ChunkRecord] = []
    chunk_index = 0
    i = 0

    while i < len(sentences):
        current: list[str] = []
        current_len = 0

        for j in range(i, len(sentences)):
            sent = sentences[j]
            sent_len = len(sent)

            # Hard cap — break NOW
            if current_len + sent_len > _MAX_CHUNK_CHARS and current_len > 0:
                break

            # Semantic boundary check: if we're already at a good size
            # AND this sentence starts a new topic (low similarity to previous)
            if (
                current_len > effective_chunk_size * 0.6  # chunk is 60%+ full
                and j > i  # not the first sentence
                and similarities[j - 1] < _SIM_THRESHOLD  # topic shift detected
            ):
                break

            current.append(sent)
            current_len += sent_len

        if not current:
            current = [sentences[i]]
            i += 1
        else:
            i += len(current)

        raw_text = " ".join(current).strip()
        if not raw_text:
            continue

        final_text = f"{header}{raw_text}"
        if len(final_text) > _MAX_CHUNK_CHARS:
            final_text = final_text[:_MAX_CHUNK_CHARS]

        start_char = text.find(current[0]) if current[0] in text else 0
        last = current[-1]
        end_pos = text.find(last, start_char) if last in text else start_char
        end_char = end_pos + len(last) if end_pos >= 0 else start_char + len(raw_text)

        chunks.append(ChunkRecord(
            source_name=document.source_name,
            source_path=document.source_path,
            chunk_id=f"{document.source_name}#chunk-{chunk_index}",
            text=final_text,
            start_char=start_char,
            end_char=end_char,
            page_count=document.page_count,
        ))
        chunk_index += 1

        # Overlap: step back a few sentences
        if overlap > 0 and i < len(sentences):
            overlap_chars = 0
            for k in range(len(current) - 1, -1, -1):
                overlap_chars += len(current[k])
                if overlap_chars >= overlap:
                    i = max(i - (len(current) - k), i - len(current) + 1)
                    break

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
