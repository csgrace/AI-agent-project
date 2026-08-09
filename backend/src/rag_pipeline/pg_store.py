"""PostgreSQL storage + vector search for document QA.

Replaces FAISS in-memory index with PostgreSQL-native vector storage.
Embeddings stored as float4[] arrays; cosine similarity search via SQL.
Brute-force (FlatIP equivalent) — sufficient for campus document scale.

Tables:
  documents  — original document metadata + full text
  chunks     — chunked text with embedding vectors
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Generator, Optional, Any, Sequence

import numpy as np

from .models import ChunkRecord, DocumentRecord, SearchResult

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore[assignment]


# ── Connection helpers ──────────────────────────────────────────────


def _pg_dsn() -> str:
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    dbname = os.getenv("PG_DATABASE", "sustech_campus")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "postgres")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


@contextmanager
def _get_conn():
    if psycopg2 is None:
        raise ImportError("psycopg2 not installed — run: pip install psycopg2-binary")
    conn = psycopg2.connect(_pg_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ──────────────────────────────────────────────────────────


_COSINE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION cosine_similarity(a float4[], b float4[])
RETURNS float4 AS $$
DECLARE
    dot_product float4 := 0;
    norm_a float4 := 0;
    norm_b float4 := 0;
    i int;
BEGIN
    FOR i IN 1..array_length(a, 1) LOOP
        dot_product := dot_product + a[i] * b[i];
        norm_a := norm_a + a[i] * a[i];
        norm_b := norm_b + b[i] * b[i];
    END LOOP;
    IF norm_a = 0 OR norm_b = 0 THEN
        RETURN 0;
    END IF;
    RETURN dot_product / sqrt(norm_a * norm_b);
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
"""


def init_db() -> None:
    """Create tables, indexes, and cosine similarity function."""
    with _get_conn() as conn:
        cur = conn.cursor()

        # Documents table (with title + structured sections)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id              SERIAL PRIMARY KEY,
                source_name     TEXT NOT NULL UNIQUE,
                source_path     TEXT NOT NULL,
                title           TEXT NOT NULL DEFAULT '',
                text            TEXT NOT NULL,
                page_count      INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP DEFAULT NOW(),
                updated_at      TIMESTAMP DEFAULT NOW()
            );
        """)

        # Chunks table with embedding + context columns
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id              SERIAL PRIMARY KEY,
                source_name     TEXT NOT NULL REFERENCES documents(source_name) ON DELETE CASCADE,
                source_path     TEXT NOT NULL,
                chunk_id        TEXT NOT NULL UNIQUE,
                text            TEXT NOT NULL,
                doc_title       TEXT NOT NULL DEFAULT '',
                section_path    TEXT NOT NULL DEFAULT '',
                embedding       float4[] NOT NULL DEFAULT '{}',
                start_char      INTEGER NOT NULL DEFAULT 0,
                end_char        INTEGER NOT NULL DEFAULT 0,
                page_count      INTEGER NOT NULL DEFAULT 0,
                page_number     INTEGER NOT NULL DEFAULT 0,
                created_at      TIMESTAMP DEFAULT NOW()
            );
        """)

        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON chunks(chunk_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_path);")

        # Cosine similarity function
        cur.execute(_COSINE_FUNCTION_SQL)

        print("[PG] Database tables + cosine_similarity() ready.")


def drop_db() -> None:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS chunks CASCADE;")
        cur.execute("DROP TABLE IF EXISTS documents CASCADE;")
        cur.execute("DROP FUNCTION IF EXISTS cosine_similarity(float4[], float4[]);")
        print("[PG] Tables dropped.")


# ── Document CRUD ───────────────────────────────────────────────────


def insert_document(doc: DocumentRecord) -> None:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO documents (source_name, source_path, title, text, page_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_name)
            DO UPDATE SET source_path = EXCLUDED.source_path,
                          title       = EXCLUDED.title,
                          text        = EXCLUDED.text,
                          page_count  = EXCLUDED.page_count,
                          updated_at  = NOW();
            """,
            (doc.source_name, doc.source_path, getattr(doc, "title", "") or "", doc.text, doc.page_count),
        )


def get_document(source_name: str) -> Optional[dict[str, Any]]:
    with _get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM documents WHERE source_name = %s;", (source_name,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_documents() -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT source_name, source_path, page_count, created_at FROM documents ORDER BY source_name;")
        return [dict(row) for row in cur.fetchall()]


def count_documents() -> int:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents;")
        return cur.fetchone()[0]


# ── Chunk + Embedding CRUD ──────────────────────────────────────────


def insert_chunks(chunks: list[ChunkRecord], embeddings: Optional[np.ndarray] = None) -> None:
    """Batch-insert chunks with their embedding vectors and context metadata."""
    if not chunks:
        return

    with _get_conn() as conn:
        cur = conn.cursor()
        sources = list({c.source_name for c in chunks})
        cur.execute("DELETE FROM chunks WHERE source_name = ANY(%s);", (sources,))

        emb_list = embeddings.tolist() if embeddings is not None else None

        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO chunks (source_name, source_path, chunk_id, text,
                                doc_title, section_path,
                                embedding, start_char, end_char, page_count, page_number)
            VALUES %s;
            """,
            [
                (
                    c.source_name,
                    c.source_path,
                    c.chunk_id,
                    c.text,
                    getattr(c, "doc_title", "") or "",
                    getattr(c, "section_path", "") or "",
                    emb_list[i] if emb_list is not None else [],
                    c.start_char,
                    c.end_char,
                    c.page_count,
                    getattr(c, "page_number", 0) or 0,
                )
                for i, c in enumerate(chunks)
            ],
        )
        print(f"[PG] Inserted {len(chunks)} chunks with embeddings for {len(sources)} source(s).")


def get_chunks(source_name: Optional[str] = None) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if source_name:
            cur.execute(
                "SELECT * FROM chunks WHERE source_name = %s ORDER BY start_char;",
                (source_name,),
            )
        else:
            cur.execute("SELECT * FROM chunks ORDER BY source_name, start_char;")
        return [dict(row) for row in cur.fetchall()]


def count_chunks() -> int:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks;")
        return cur.fetchone()[0]


# ── Vector search (replaces FAISS) ──────────────────────────────────


def vector_search(
    query_embedding: np.ndarray,
    k: int = 5,
    *,
    fetch_k: int = 15,
    source_prefixes: Optional[Sequence[str]] = None,
) -> list[SearchResult]:
    """Cosine similarity search over chunks using PostgreSQL.

    Equivalent to FAISS IndexFlatIP (brute-force inner product over
    L2-normalized vectors).  For campus-scale data (< 10k chunks)
    this completes in single-digit milliseconds.
    """
    # Ensure flat list
    vec = query_embedding.flatten().astype(np.float32).tolist()

    with _get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Build WHERE clause for course-scope filtering
        where_clause = ""
        params: list[Any] = [vec, fetch_k]
        if source_prefixes:
            prefix_list = list(source_prefixes)
            placeholders = ",".join(["%s"] * len(prefix_list))
            where_clause = "WHERE " + " OR ".join(
                [f"c.source_name LIKE %s"] * len(prefix_list)
            )
            params = [vec] + [f"{p}%" for p in prefix_list] + [fetch_k]

        sql = f"""
            SELECT c.source_name, c.source_path, c.chunk_id, c.text,
                   c.doc_title, c.section_path,
                   c.embedding, c.start_char, c.end_char, c.page_count, c.page_number,
                   cosine_similarity(c.embedding, %s::float4[]) AS score
            FROM chunks c
            {where_clause}
            ORDER BY score DESC
            LIMIT %s;
        """

        cur.execute(sql, params)
        rows = cur.fetchall()

        results: list[SearchResult] = []
        for row in rows:
            results.append(SearchResult(
                source_name=str(row["source_name"]),
                source_path=str(row["source_path"]),
                chunk_id=str(row["chunk_id"]),
                text=str(row["text"]),
                score=float(row["score"]),
                start_char=int(row["start_char"]),
                end_char=int(row["end_char"]),
                page_count=int(row["page_count"]),
                page_number=int(row.get("page_number", 0) or 0),
                doc_title=str(row.get("doc_title", "") or ""),
                section_path=str(row.get("section_path", "") or ""),
            ))
            if len(results) >= k:
                break

        return results


# ── Backward-compat loaders ─────────────────────────────────────────


def chunk_from_row(row: dict[str, Any]) -> ChunkRecord:
    return ChunkRecord(
        source_name=str(row.get("source_name", "")),
        source_path=str(row.get("source_path", "")),
        chunk_id=str(row.get("chunk_id", "")),
        text=str(row.get("text", "")),
        start_char=int(row.get("start_char", 0)),
        end_char=int(row.get("end_char", 0)),
        page_count=int(row.get("page_count", 0)),
        doc_title=str(row.get("doc_title", "")),
        section_path=str(row.get("section_path", "")),
    )


def load_all_chunks() -> list[ChunkRecord]:
    rows = get_chunks()
    return [chunk_from_row(r) for r in rows]


def load_chunks_json_sidecar(path: str) -> list[ChunkRecord]:
    from .models import coerce_chunk
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [coerce_chunk(c) for c in data]
