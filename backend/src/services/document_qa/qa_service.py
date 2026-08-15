"""RAG-first orchestrator with LLM-based query routing for document QA."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Generator, Optional

from ...rag_pipeline.llm_service import LLMService
from ...rag_pipeline.models import AnswerResult, ChunkRecord, SearchResult
from ...rag_pipeline.prompt import (
    build_answer_system_prompt,
    build_clarification_prompt,
    build_rag_prompt,
)
from ...rag_pipeline.vector_store import VectorStore
from .memory import DocumentQAMemory, get_or_create_memory

BASE_DIR = Path(__file__).resolve().parents[3]
STORAGE_DIR = BASE_DIR / "storage"
CHUNKS_PATH = STORAGE_DIR / "chunks.json"


class QAService:
    def __init__(self, vector_store: Optional[VectorStore] = None) -> None:
        self.vector_store = vector_store or VectorStore()
        self.llm_service = LLMService()
        self.chunks: list[ChunkRecord] = []
        self._index_ready = False
        self._default_session_id = str(uuid.uuid4())
        self.load_index()

    @property
    def memory(self) -> DocumentQAMemory:
        """Get the QA memory for the current default session."""
        return get_or_create_memory(self._default_session_id)

    def load_index(self) -> bool:
        """Load persisted index from PostgreSQL."""
        try:
            self._index_ready = self.vector_store.load_index()
            if self._index_ready:
                self.chunks = self.vector_store.chunks
                print(f"QA Service: {len(self.chunks)} chunks ready.")
            else:
                print("QA Service: No index found. Run index_documents.py first.")
            return self._index_ready
        except Exception as e:
            print(f"QA Service: Load failed: {e}")
            return False

    def search(
        self,
        query: str,
        k: int = 5,
        course_scope: str | None = None,
    ) -> list[SearchResult]:
        if not self._index_ready and not self.load_index():
            return []

        allowed_prefixes = [course_scope] if course_scope else None
        return self.vector_store.search(
            query,
            k=k,
            allowed_source_prefixes=allowed_prefixes,
        )

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize text into Latin words and CJK characters."""
        lowered = text.lower()
        latin_tokens = {w for w in lowered.split() if len(w) > 1}
        cjk_tokens = {c for c in lowered if "\u4e00" <= c <= "\u9fff"}
        return latin_tokens | cjk_tokens

    def _top_lexical_overlap(self, query: str, results: list[SearchResult]) -> float:
        """Compute lexical overlap between query and top results."""
        if not query or not results:
            return 0.0

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0.0

        best = 0.0
        for item in results[:3]:
            text_tokens = self._tokenize(item.text)
            if not text_tokens:
                continue
            overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
            best = max(best, overlap)
        return float(best)

    def _should_use_rag(
        self,
        query_kind: str,
        routing_confidence: float,
        max_score: float,
        lexical_overlap: float,
        similarity_threshold: float,
    ) -> bool:
        """Decide whether to use RAG (vector search results) or general chat."""
        # Keep #sym:max_score as primary signal, refined by the model's routing decision.
        score_gate = max_score >= similarity_threshold
        strong_score_gate = max_score >= (similarity_threshold + 0.08)
        overlap_gate = lexical_overlap >= 0.05

        if query_kind == "chat":
            return strong_score_gate and overlap_gate and routing_confidence >= 0.55
        if query_kind == "document":
            return score_gate or overlap_gate or routing_confidence >= 0.55
        return (score_gate and overlap_gate) or routing_confidence >= 0.75

    def answer_question(
        self,
        query: str,
        k: int = 5,
        course_scope: str | None = None,
        similarity_threshold: float = 0.35,
        session_id: Optional[str] = None,
    ) -> AnswerResult:
        """Route between general chat and grounded QA while retaining #sym:max_score signal.
        
        Args:
            session_id: Optional session ID for conversation memory. If provided,
                       previous QA context will be injected into the prompt.
        """
        if not self._index_ready and not self.load_index():
            return self._fallback_no_index(query)

        # Get conversation memory context
        memory_context = ""
        if session_id:
            mem = get_or_create_memory(session_id)
            memory_context = mem.get_context_str()

        results = self.vector_store.search(
            query,
            k=k,
            allowed_source_prefixes=[course_scope] if course_scope else None,
        )

        max_score = results[0].score if results else 0.0

        # ── Speculative parallel: launch all three lightweight LLM calls at once ──
        # Group results by source for keyword extraction (speculative on all results)
        grouped: dict[str, list[str]] = {}
        for item in results:
            grouped.setdefault(item.source_name, []).append(item.text)

        with ThreadPoolExecutor(max_workers=3) as pool:
            future_route = pool.submit(
                self.llm_service.classify_query_kind, query, max_score=max_score
            )
            future_keywords = (
                pool.submit(self.llm_service.extract_keywords_batch, query, grouped)
                if grouped else None
            )
            future_answerability = (
                pool.submit(self.llm_service.assess_answerability, query, results)
                if results else None
            )

            # ── Wait for routing (needed for decision) ──
            routing = future_route.result()

        query_kind = routing.intent
        lexical_overlap = self._top_lexical_overlap(query, results)
        use_rag = self._should_use_rag(
            query_kind=query_kind,
            routing_confidence=routing.confidence,
            max_score=max_score,
            lexical_overlap=lexical_overlap,
            similarity_threshold=similarity_threshold,
        )

        print(
            "RAG Decision: "
            f"query_kind={query_kind}, "
            f"routing_confidence={routing.confidence:.4f}, "
            f"#sym:max_score={max_score:.4f}, "
            f"lexical_overlap={lexical_overlap:.4f}, "
            f"mode={'rag' if use_rag else 'general'}"
        )

        chosen_citations = results if use_rag else []

        # ── Collect keyword results (only if RAG) ──
        keywords_map: dict[str, list[str]] = {}
        if use_rag and future_keywords:
            try:
                keywords_map = future_keywords.result()
            except Exception as e:
                print(f"Keyword extraction failed: {e}")

        # ── Collect answerability result (only if document RAG) ──
        if use_rag and query_kind == "document":
            answerability = None
            if future_answerability:
                try:
                    answerability = future_answerability.result()
                except Exception as e:
                    print(f"Answerability check failed: {e}")
            if answerability is not None and not answerability.answerable:
                clarification = self.llm_service.generate_clarification(
                    query,
                    chosen_citations,
                    reason=answerability.reason,
                )
                return AnswerResult(
                    answer=clarification or answerability.reason,
                    citations=chosen_citations,
                    confidence=float(answerability.confidence),
                    answerable=False,
                    needs_clarification=True,
                    detected_course_scope=course_scope,
                )

        answer = self.llm_service.generate_answer(
            query,
            chosen_citations,
            max_score=max_score,
            query_kind=query_kind,
            memory_context=memory_context,
        )

        final_answer = answer or "抱歉，我现在无法回答这个问题。"
        needs_clarification = (query_kind == "document") and (not use_rag)
        confidence = float(max_score if use_rag else routing.confidence)

        # Record turn in memory
        if session_id:
            sources = [c.source_name for c in chosen_citations[:3]]
            get_or_create_memory(session_id).add_turn(query, final_answer, sources)

        return AnswerResult(
            answer=final_answer,
            citations=chosen_citations,
            confidence=confidence,
            answerable=bool(answer),
            needs_clarification=needs_clarification,
            detected_course_scope=course_scope,
            keywords=keywords_map or None,
        )

    def _fallback_no_index(self, query: str) -> AnswerResult:
        print("No index found. Falling back to direct LLM response.")
        clarification = self.llm_service.generate_clarification(query, [], reason="系统索引当前不可用。")
        return AnswerResult(
            answer=clarification or "系统索引当前不可用。",
            citations=[],
            confidence=0.0,
            answerable=False,
            needs_clarification=True,
        )

    def answer_question_stream(
        self,
        query: str,
        k: int = 5,
        course_scope: str | None = None,
        similarity_threshold: float = 0.35,
        session_id: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """Stream the answer generation, yielding token events followed by metadata.

        Yields:
            {"event": "token", "data": "<text chunk>"}
            {"event": "metadata", "data": { ... citations, confidence, etc. }}
            {"event": "done", "data": ""}
            {"event": "error", "data": "<error message>"}

        Args:
            session_id: Optional session ID for conversation memory.
        """
        # Phase 1: Load index
        if not self._index_ready and not self.load_index():
            yield {"event": "error", "data": "知识库索引不可用，请稍后再试。"}
            return

        # Get conversation memory context
        memory_context = ""
        if session_id:
            mem = get_or_create_memory(session_id)
            memory_context = mem.get_context_str()

        yield {"event": "status", "data": "正在检索知识库..."}

        # Phase 2: Vector search
        results = self.vector_store.search(
            query,
            k=k,
            allowed_source_prefixes=[course_scope] if course_scope else None,
        )

        max_score = results[0].score if results else 0.0

        yield {"event": "status", "data": "正在分析RAG结果..."}

        # ── Speculative parallel: launch all three lightweight LLM calls at once ──
        grouped: dict[str, list[str]] = {}
        for item in results:
            grouped.setdefault(item.source_name, []).append(item.text)

        with ThreadPoolExecutor(max_workers=3) as pool:
            future_route = pool.submit(
                self.llm_service.classify_query_kind, query, max_score=max_score
            )
            future_keywords = (
                pool.submit(self.llm_service.extract_keywords_batch, query, grouped)
                if grouped else None
            )
            future_answerability = (
                pool.submit(self.llm_service.assess_answerability, query, results)
                if results else None
            )

            # ── Wait for routing (needed for decision) ──
            routing = future_route.result()

        query_kind = routing.intent
        lexical_overlap = self._top_lexical_overlap(query, results)
        use_rag = self._should_use_rag(
            query_kind=query_kind,
            routing_confidence=routing.confidence,
            max_score=max_score,
            lexical_overlap=lexical_overlap,
            similarity_threshold=similarity_threshold,
        )

        print(
            "RAG Decision [stream]: "
            f"query_kind={query_kind}, "
            f"routing_confidence={routing.confidence:.4f}, "
            f"#sym:max_score={max_score:.4f}, "
            f"lexical_overlap={lexical_overlap:.4f}, "
            f"mode={'rag' if use_rag else 'general'}"
        )

        chosen_citations = results if use_rag else []

        yield {"event": "status", "data": "正在生成回答..."}

        # ── Collect answerability result (only if document RAG) ──
        answerable = True
        needs_clarification = False
        if use_rag and query_kind == "document":
            answerability = None
            if future_answerability:
                try:
                    answerability = future_answerability.result()
                except Exception as e:
                    print(f"Answerability check failed: {e}")
            if answerability is not None and not answerability.answerable:
                # Stream clarification instead of answer
                answerable = False
                needs_clarification = True
                clarification_prompt = build_clarification_prompt(
                    query, chosen_citations, reason=answerability.reason
                )
                stream_complete = False
                for token in self.llm_service._chat_completion_stream(
                    clarification_prompt,
                    temperature=0.1,
                    max_tokens=256,
                    label="clarification/stream",
                    model=self.llm_service.lightweight_model_name,
                    fallback_model=self.llm_service._lightweight_fallback_model,
                    system_prompt=(
                        "You are SUSTech Campus Assistant. "
                        "Write a concise clarification reply only. "
                        "Do not answer the original question directly."
                    ),
                ):
                    yield {"event": "token", "data": token}
                else:
                    stream_complete = True

                metadata = {
                    "citations": [c.to_dict() for c in chosen_citations],
                    "confidence": float(answerability.confidence),
                    "answerable": False,
                    "needs_clarification": True,
                    "detected_course_scope": course_scope,
                    "keywords": {},
                    "stream_complete": stream_complete,
                }
                yield {"event": "metadata", "data": metadata}
                yield {"event": "done", "data": ""}
                return

        # ── Collect keyword results (only if RAG) ──
        keywords_map: dict[str, list[str]] = {}
        if use_rag and future_keywords:
            try:
                keywords_map = future_keywords.result()
            except Exception as e:
                print(f"Keyword extraction failed: {e}")

        # Phase 6: Stream answer generation
        prompt = build_rag_prompt(
            query,
            chosen_citations,
            max_score=max_score,
            query_kind=query_kind,
            memory_context=memory_context,
        )

        resolved_query_kind = query_kind.strip().lower()
        if resolved_query_kind == "document":
            temperature = 0.1
            max_tokens_val = 768
        elif resolved_query_kind == "chat":
            temperature = 0.2
            max_tokens_val = 1024
        else:
            temperature = 0.1
            max_tokens_val = 1024

        full_answer = ""
        stream_complete = False
        for token in self.llm_service._chat_completion_stream(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens_val,
            label="answer/stream",
            system_prompt=build_answer_system_prompt(resolved_query_kind),
        ):
            full_answer += token
            yield {"event": "token", "data": token}
        else:
            stream_complete = True

        compacted = self.llm_service._compact_answer(full_answer, query_kind=resolved_query_kind)
        if resolved_query_kind == "document" and self.llm_service._looks_repetitive(compacted):
            compacted = self.llm_service._compact_answer(compacted, query_kind="document")[:240]

        final_answer = compacted or "抱歉，我现在无法回答这个问题。"
        confidence = float(max_score if use_rag else routing.confidence)

        metadata = {
            "answer": final_answer,
            "citations": [c.to_dict() for c in chosen_citations],
            "confidence": confidence,
            "answerable": bool(compacted),
            "needs_clarification": (query_kind == "document") and (not use_rag),
            "detected_course_scope": course_scope,
            "keywords": keywords_map or None,
            "stream_complete": stream_complete,
        }
        yield {"event": "metadata", "data": metadata}
        yield {"event": "done", "data": ""}

        # Record turn in memory after stream completes
        if session_id:
            sources = [c.source_name for c in chosen_citations[:3]]
            get_or_create_memory(session_id).add_turn(query, final_answer, sources)
