"""Document QA pipeline for T2."""

from ...rag_pipeline.loader import DOCUMENTS_DIR
from ...rag_pipeline.models import AnswerResult, ChunkRecord, DocumentRecord, SearchResult
from .qa_service import QAService

_service_instance: QAService | None = None


def get_document_qa_service() -> QAService:
    """Singleton pattern for QA Service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = QAService()
    return _service_instance


def reset_document_qa_service() -> None:
    """Force the QA Service singleton to be recreated on next access.

    Call this after updating LLMConfig at runtime (e.g. when the user
    sets an API key via the web UI).
    """
    global _service_instance
    _service_instance = None


def get_qa_service() -> QAService:
    return get_document_qa_service()


__all__ = [
    "AnswerResult",
    "ChunkRecord",
    "DOCUMENTS_DIR",
    "QAService",
    "DocumentRecord",
    "SearchResult",
    "get_document_qa_service",
    "get_qa_service",
    "reset_document_qa_service",
]
