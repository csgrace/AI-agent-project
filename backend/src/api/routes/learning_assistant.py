"""API routes for the learning assistant agent — chat-driven summarization & quiz generation."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from ...agents.learning_assistant.prompts import GRADE_SYSTEM_PROMPT, build_grade_prompt
from ...agents.registry import AgentRegistry
from ...rag_pipeline.llm_service import LLMService
from ...services.llm_config import LLMConfig

router = APIRouter(prefix="/api/learning-assistant", tags=["learning-assistant"])

AGENT_NAME = "learning_assistant"

# ===== Request Models =====


class ChatRequest(BaseModel):
    message: str
    file_context: str | None = None  # uploaded file path, if any


class ResetRequest(BaseModel):
    message: str = ""


class GradeRequest(BaseModel):
    question_text: str
    student_answer: str
    correct_answer: str
    explanations: dict[str, Any] | None = None


# ===== Helpers =====


def _is_agent_busy() -> bool:
    return AgentRegistry.is_busy(AGENT_NAME)


# ===== Upload Endpoint =====


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a PPT or Markdown file and return its storage path."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pptx", ".ppt", ".md"):
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {ext}")

    storage_dir = Path(__file__).resolve().parents[3] / "storage" / "uploads"
    storage_dir.mkdir(parents=True, exist_ok=True)

    save_path = storage_dir / file.filename
    content_bytes = await file.read()
    save_path.write_bytes(content_bytes)

    return {
        "file_name": file.filename,
        "file_path": str(save_path.resolve()),
        "size": len(content_bytes),
    }


# ===== Chat Endpoint (SSE) =====


@router.post("/chat")
async def chat(req: ChatRequest):
    if not LLMConfig.get_instance().api_key:
        raise HTTPException(status_code=503, detail="未配置 API Key，请前往个人中心 → API 配置 填入密钥后再试")
    agent = AgentRegistry.get(AGENT_NAME)
    if agent is None:
        raise HTTPException(status_code=503, detail="Learning assistant not initialized")

    if not AgentRegistry.acquire(AGENT_NAME):
        raise HTTPException(
            status_code=429,
            detail="Agent is busy. Please wait or reset.",
        )

    user_text = req.message
    if req.file_context:
        user_text = f"[已上传文件: {req.file_context}]\n{user_text}"

    async def event_generator():
        try:
            async for event in iterate_in_threadpool(agent.run_turn_stream(user_text)):
                yield {
                    "event": event.get("event", "unknown"),
                    "data": json.dumps(dict(event), ensure_ascii=True, default=str),
                }
        finally:
            AgentRegistry.release(AGENT_NAME)

    return EventSourceResponse(event_generator())


@router.post("/chat/reset")
async def reset_agent():
    agent = AgentRegistry.get(AGENT_NAME)
    if agent is None:
        raise HTTPException(status_code=503, detail="Learning assistant not initialized")

    agent.messages = []
    AgentRegistry.release(AGENT_NAME)
    return {"ok": True, "message": "Agent state has been reset."}


@router.get("/chat/status")
async def chat_status():
    return {
        "busy": AgentRegistry.is_busy(AGENT_NAME),
        "agent_initialized": AgentRegistry.is_initialized(AGENT_NAME),
    }


# ===== Info Endpoints =====


@router.post("/grade")
def grade_short_answer(req: GradeRequest):
    """Grade a short answer question using AI evaluation."""
    llm = LLMService()
    prompt = build_grade_prompt(
        req.question_text,
        req.student_answer,
        req.correct_answer,
        req.explanations,
    )
    result = llm._chat_completion(
        prompt=prompt,
        temperature=0.2,
        max_tokens=1024,
        label="grade_answer",
        system_prompt=GRADE_SYSTEM_PROMPT,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Grading failed — LLM returned empty response")

    # Parse JSON from response
    import re
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", result, re.DOTALL)
    if json_match:
        result = json_match.group(1)
    try:
        parsed = json.loads(result)
        return {
            "score": parsed.get("score", 50),
            "level": parsed.get("level", "partial"),
            "feedback": parsed.get("feedback", "评分完成。"),
        }
    except json.JSONDecodeError:
        return {
            "score": 50,
            "level": "partial",
            "feedback": result.strip()[:500],
        }


@router.get("/styles")
def list_styles():
    """List available summary styles and question types."""
    return {
        "summary_styles": ["concise", "detailed", "outline", "mind_map"],
        "question_types": ["multiple_choice", "fill_in_blank", "true_false", "short_answer"],
        "difficulty_levels": ["easy", "medium", "hard"],
    }
