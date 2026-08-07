"""Vector store using PostgreSQL pgvector-style cosine similarity search.

Replaces the previous FAISS in-memory index.  Embeddings are persisted
in the PostgreSQL chunks table; search runs via the cosine_similarity()
SQL function.
"""

from __future__ import annotations

from typing import Sequence, Optional

import numpy as np

from .embeddings import SentenceTransformerEmbeddings
from .models import ChunkRecord, SearchResult
from .pg_store import vector_search, insert_chunks, init_db, count_chunks, load_all_chunks


class VectorStore:
    """PostgreSQL-backed vector store with brute-force cosine search.

    Stores embeddings alongside chunk metadata in PG.  Search uses
    the ``cosine_similarity()`` PL/pgSQL function — equivalent to
    FAISS IndexFlatIP over L2-normalized vectors.
    """

    def __init__(self, embeddings: Optional[SentenceTransformerEmbeddings] = None) -> None:
        self.embeddings = embeddings or SentenceTransformerEmbeddings()
        self.chunks: list[ChunkRecord] = []
        self._index_ready = False
        self.load_index()

    def reset(self) -> None:
        self.chunks = []
        self._index_ready = False

    def build(self, chunks: Sequence[ChunkRecord]) -> None:
        """Build the vector index: encode chunks and persist to PostgreSQL."""
        self.chunks = list(chunks)
        if not self.chunks:
            self.reset()
            return

        # Initialize schema if needed
        init_db()

        # Encode all chunks
        texts = [chunk.text for chunk in self.chunks]
        embeddings = self.embeddings.encode(texts)
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        embeddings = np.asarray(embeddings, dtype=np.float32)

        # L2 normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = embeddings / norms

        # Persist to PostgreSQL
        insert_chunks(self.chunks, embeddings)

        self._index_ready = True
        print(f"VectorStore: Built index with {len(self.chunks)} chunks ({embeddings.shape[1]}d).")

    def load_index(self) -> bool:
        """Load existing chunks from PostgreSQL."""
        try:
            n = count_chunks()
            if n == 0:
                print("VectorStore: No chunks in database. Run index_documents.py first.")
                return False
            self.chunks = load_all_chunks()
            self._index_ready = True
            print(f"VectorStore: Loaded {len(self.chunks)} chunks from PostgreSQL.")
            return True
        except Exception as e:
            print(f"VectorStore: Load failed: {e}")
            return False

    def search(
        self,
        query: str,
        k: int = 3,
        *,
        fetch_k: int | None = None,
        allowed_source_prefixes: Sequence[str] | None = None,
    ) -> list[SearchResult]:
        """Semantic search via PostgreSQL cosine similarity."""
        if not self._index_ready and not self.load_index():
            return []

        if not query.strip():
            return []

        # Encode query
        query_embedding = self.embeddings.encode([query])
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        query_embedding = np.asarray(query_embedding, dtype=np.float32)

        # L2 normalize
        qnorm = np.linalg.norm(query_embedding, axis=1, keepdims=True)
        qnorm[qnorm == 0] = 1.0
        query_embedding = query_embedding / qnorm

        # PG vector search
        fetch = fetch_k or max(k * 3, 10)

        # Normalize source prefixes for LIKE matching
        prefixes: list[str] | None = None
        if allowed_source_prefixes:
            prefixes = [
                p.strip().rstrip("/") + "/"
                for p in allowed_source_prefixes
                if p and p.strip()
            ]
            if not prefixes:
                prefixes = None

        return vector_search(query_embedding, k=k, fetch_k=fetch, source_prefixes=prefixes)
