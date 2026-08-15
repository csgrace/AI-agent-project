import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool
import mimetypes

from src.services.document_qa import DOCUMENTS_DIR
from src.services.document_qa import get_document_qa_service
from src.services.document_qa.memory import clear_session_memory
from src.services.llm_config import LLMConfig

router = APIRouter(prefix="/api/qa", tags=["document-qa"])


class ChatRequest(BaseModel):
    message: str
    course_scope: str | None = None
    session_id: str | None = None  # 会话ID，用于多轮对话记忆


class SearchRequest(BaseModel):
    query: str
    k: int = 3
    course_scope: str | None = None


class CitationResponse(BaseModel):
    source_name: str
    source_path: str
    chunk_id: str
    text: str
    score: float
    start_char: int = 0
    end_char: int = 0
    page_count: int = 0
    page_number: int = 0
    keywords: list[str] | None = None


class ChatResponse(BaseModel):
    answer: str
    confidence: float
    answerable: bool
    needs_clarification: bool
    citations: list[CitationResponse]
    detected_course_scope: str | None = None
    keywords: dict[str, list[str]] | None = None


class SearchResponse(BaseModel):
    results: list[CitationResponse]


def _resolve_document_path(*, source_path: str | None = None, source_name: str | None = None) -> Path:
    documents_root = DOCUMENTS_DIR.resolve()
    candidates: list[Path] = []

    if source_path:
        source_path_input = Path(source_path)
        if source_path_input.is_absolute():
            candidates.append(source_path_input)
        else:
            candidates.append(documents_root / source_path_input)

    if source_name:
        source_name_input = Path(source_name)
        if source_name_input.is_absolute():
            candidates.append(source_name_input)
        else:
            candidates.append(documents_root / source_name_input)

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue

        cache_key = str(resolved)
        if cache_key in seen:
            continue
        seen.add(cache_key)

        if not resolved.exists() or not resolved.is_file():
            continue

        try:
            resolved.relative_to(documents_root)
        except ValueError:
            continue

        return resolved

    raise HTTPException(status_code=404, detail="document not found")


@router.post("/chat")
def chat(req: ChatRequest):
    if not LLMConfig.get_instance().api_key:
        raise HTTPException(status_code=503, detail="未配置 API Key，请前往个人中心 → API 配置 填入密钥后再试")
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    service = get_document_qa_service()
    result = service.answer_question(message, course_scope=req.course_scope, session_id=req.session_id)

    return ChatResponse(
        answer=result.answer,
        confidence=result.confidence,
        answerable=result.answerable,
        needs_clarification=result.needs_clarification,
        citations=[CitationResponse(**c.to_dict()) for c in result.citations],
        detected_course_scope=result.detected_course_scope,
        keywords=result.keywords or {}
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    service = get_document_qa_service()

    async def event_generator():
        async for event in iterate_in_threadpool(service.answer_question_stream(message, course_scope=req.course_scope, session_id=req.session_id)):
            event_type = event.get("event", "unknown")
            if event_type == "status":
                yield {
                    "event": "status",
                    "data": event["data"],
                }
            elif event_type == "metadata":
                yield {
                    "event": "metadata",
                    "data": json.dumps(event["data"], ensure_ascii=False, default=str),
                }
            elif event_type == "token":
                yield {
                    "event": "token",
                    "data": event["data"],
                }
            elif event_type == "error":
                yield {
                    "event": "error",
                    "data": event["data"],
                }
            elif event_type == "done":
                yield {
                    "event": "done",
                    "data": "",
                }

    return EventSourceResponse(event_generator())


@router.post("/reset")
def reset_memory(session_id: str):
    """Clear conversation memory for a session."""
    clear_session_memory(session_id)
    return {"ok": True, "message": "会话记忆已清除"}


@router.post("/search")
def search(req: SearchRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    service = get_document_qa_service()
    results = service.vector_store.search(query, k=req.k, allowed_source_prefixes=[req.course_scope] if req.course_scope else None)
    return SearchResponse(results=[CitationResponse(**item.to_dict()) for item in results])


@router.get("/courses")
def list_courses():
    service = get_document_qa_service()
    scopes = sorted(list(set(c.source_name.split('/')[0] for c in service.chunks if '/' in c.source_name)))
    return {"courses": scopes}


@router.get("/documents/raw")
def raw_document(source_path: str | None = None, source_name: str | None = None):
    if not source_path and not source_name:
        raise HTTPException(status_code=400, detail="source_path or source_name is required")

    pdf_path = _resolve_document_path(source_path=source_path, source_name=source_name)
    mime_type, _ = mimetypes.guess_type(pdf_path.name)
    if not mime_type:
        mime_type = "application/octet-stream"

    response = FileResponse(path=pdf_path, media_type=mime_type, filename=pdf_path.name)
    response.headers["Cache-Control"] = "no-store"
    return response
