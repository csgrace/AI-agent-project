from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...rag_pipeline.llm_service import LLMService

router = APIRouter(prefix="/api", tags=["chat_sessions"])

_SESSIONS: Dict[str, List[dict[str, str]]] = {}


class SessionMessage(BaseModel):
    text: str


class SessionHistoryResponse(BaseModel):
    term_id: str
    history: List[dict[str, str]]


@router.post("/chat/session/{term_id}/message")
async def post_session_message(term_id: str, req: SessionMessage):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty message")

    history = _SESSIONS.setdefault(term_id, [])
    history.append({"role": "user", "text": text})

    llm = LLMService()
    prompt = "\n".join(
        [
            *(f"{item['role']}: {item['text']}" for item in history),
            "assistant:",
        ]
    )
    reply = llm._chat_completion(
        prompt,
        temperature=0.2,
        max_tokens=256,
        label=f"session-{term_id}",
        model=llm.lightweight_model_name,
        fallback_model=llm._lightweight_fallback_model,
    ) or "(无回应)"

    history.append({"role": "assistant", "text": reply})
    return {"event": "final", "data": {"text": reply}}


@router.get("/chat/session/{term_id}")
async def get_session_history(term_id: str):
    return SessionHistoryResponse(
        term_id=term_id,
        history=_SESSIONS.get(term_id, []),
    )


@router.post("/chat/session/{term_id}/reset")
async def reset_session(term_id: str):
    _SESSIONS.pop(term_id, None)
    return {"ok": True, "term_id": term_id}
