"""FAISS-backed vector store for semantic search."""

from __future__ import annotations

from typing import Sequence

import faiss
import numpy as np

from .embeddings import SentenceTransformerEmbeddings
from .models import ChunkRecord, SearchResult


class VectorStore:
    def __init__(self, embeddings: SentenceTransformerEmbeddings | None = None) -> None:
        self.embeddings = embeddings or SentenceTransformerEmbeddings()
        self.index: faiss.Index | None = None
        self.chunks: list[ChunkRecord] = []

    def reset(self) -> None:
        self.index = None
        self.chunks = []

    def build(self, chunks: Sequence[ChunkRecord]) -> None:
        self.chunks = list(chunks)

        if not self.chunks:
            self.reset()
            return

        texts = [chunk.text for chunk in self.chunks]
        embeddings = self.embeddings.encode(texts)

        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)

        embeddings = np.asarray(embeddings, dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = embeddings / norms

        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)

    def search(
        self,
        query: str,
        k: int = 3,
        *,
        fetch_k: int | None = None,
        allowed_source_prefixes: Sequence[str] | None = None,
    ) -> list[SearchResult]:
        if self.index is None or not self.chunks or not query.strip():
            return []

        # 1. 扩大检索范围（fetch_k 可以设大一点，比如 k * 3）
        fetch_k = fetch_k or max(k * 3, 10)
        top_k = min(fetch_k, len(self.chunks))
        
        # 2. 标准化课程前缀
        normalized_prefixes = tuple(
            prefix.strip().rstrip("/") + "/"
            for prefix in (allowed_source_prefixes or [])
            if prefix and prefix.strip()
        )
        
        # 3. 计算 query embedding
        query_embedding = self.embeddings.encode([query])
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        query_embedding = np.asarray(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_embedding, axis=1, keepdims=True)
        query_norm[query_norm == 0] = 1.0
        query_embedding = query_embedding / query_norm
        
        # 4. 检索 fetch_k 个最相似结果
        scores, indices = self.index.search(query_embedding, top_k)
        
        # 5. 过滤 + 取前 k 个符合条件的
        results: list[SearchResult] = []
        for score, index in zip(scores[0], indices[0]):
            if index < 0:
                continue
            
            chunk = self.chunks[index]
            
            # 课程过滤
            if normalized_prefixes:
                # 检查 chunk 的 source_name 是否以任一允许的前缀开头
                matched = any(
                    chunk.source_name.startswith(prefix) 
                    for prefix in normalized_prefixes
                )
                if not matched:
                    continue
            
            results.append(
                SearchResult(
                    source_name=chunk.source_name,
                    source_path=chunk.source_path,
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=float(score),
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    page_count=chunk.page_count,
                )
            )
            
            if len(results) >= k:
                break
        
        return results
