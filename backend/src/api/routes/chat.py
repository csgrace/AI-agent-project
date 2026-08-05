import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from ...agents.registry import AgentRegistry
from ...core.global_state import get_draft_calendar
from ...models.calendar.enums import DirtyType
from ...services.llm_config import LLMConfig
from ..schemas import ChatRequest

router = APIRouter(prefix="/api", tags=["chat"])

AGENT_NAME = "scheduler"


class ChatEventResponse(BaseModel):
    event: str
    data: dict


class ResetRequest(BaseModel):
    message: str = ""


# ---------------------------------------------------------------------------
# Backward-compatible helpers (used by server.py)
# ---------------------------------------------------------------------------

def get_agent():
    """Return the scheduler agent instance, or None."""
    return AgentRegistry.get(AGENT_NAME)


def set_agent(agent):
    """Register the scheduler agent (delegates to AgentRegistry)."""
    AgentRegistry.register(AGENT_NAME, agent)


def _is_agent_busy() -> bool:
    return AgentRegistry.is_busy(AGENT_NAME)


# ---------------------------------------------------------------------------
# Endpoints  (API contract MUST remain unchanged)
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(req: ChatRequest):
    if not LLMConfig.get_instance().api_key:
        raise HTTPException(status_code=503, detail="未配置 API Key，请前往个人中心 → API 配置 填入密钥后再试")
    agent = AgentRegistry.get(AGENT_NAME)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    if not AgentRegistry.acquire(AGENT_NAME):
        raise HTTPException(
            status_code=429,
            detail="Agent is busy processing another request. Please wait or reset.",
        )

    async def event_generator():
        try:
            async for event in iterate_in_threadpool(agent.run_turn_stream(req.message)):
                event_type = event.get("event", "unknown")
                payload = dict(event)

                if event_type == "final":
                    draft = get_draft_calendar()
                    requires_commit = False
                    if draft is not None and draft.dirty != DirtyType.CLEAR:
                        requires_commit = True
                    payload["requires_commit"] = requires_commit
                    # 前端通过单独的 /api/calendar/draft 获取草稿数据
                    # if requires_commit:
                    #     payload["draft"] = draft_to_response(draft).model_dump()

                yield {
                    "event": event_type,
                    "data": json.dumps(payload, ensure_ascii=False, default=str),
                }
        finally:
            AgentRegistry.release(AGENT_NAME)

    return EventSourceResponse(event_generator())


@router.get("/chat/history")
async def get_chat_history():
    """Return conversation history for the frontend to restore on page load."""
    if not LLMConfig.get_instance().api_key:
        raise HTTPException(status_code=503, detail="未配置 API Key，请前往个人中心 → API 配置 填入密钥后再试")
    agent = AgentRegistry.get(AGENT_NAME)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    from langchain_core.messages import AIMessage, HumanMessage

    history: list[dict] = []
    for msg in agent.messages:
        # Skip summarization placeholder messages.
        extra = getattr(msg, "additional_kwargs", {}) or {}
        if extra.get("lc_source") == "summarization":
            continue

        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content.strip():
                history.append({"role": "user", "content": content})
        elif isinstance(msg, AIMessage):
            # Only include final AI responses (no tool_calls).
            tool_calls = list(getattr(msg, "tool_calls", []) or [])
            if not tool_calls:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content.strip():
                    history.append({"role": "assistant", "content": content})

    return {"ok": True, "messages": history}


@router.post("/chat/reset")
async def reset_agent():
    agent = AgentRegistry.get(AGENT_NAME)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Clear both agent.messages and runner.messages so the reset
    # actually takes effect on the next turn.
    agent.runner.messages = []
    agent.messages = []

    # Force-release the lock in case a previous request hung.
    AgentRegistry.release(AGENT_NAME)

    return {"ok": True, "message": "Agent state has been reset."}


@router.get("/chat/status")
async def chat_status():
    return {
        "busy": AgentRegistry.is_busy(AGENT_NAME),
        "agent_initialized": AgentRegistry.is_initialized(AGENT_NAME),
    }
