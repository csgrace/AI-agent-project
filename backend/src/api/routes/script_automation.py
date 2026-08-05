"""API routes for the Script Automation Agent.

Provides SSE streaming chat, reset, status, kill, and sandbox directory endpoints.
Pattern follows the existing scheduler chat.py convention.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...agents.registry import AgentRegistry
from ...agents.script_automation.agent import ScriptAutomationAgent
from ...services.llm_config import LLMConfig
from ...core.global_state import (
    get_script_sandbox_dir,
    save_script_sandbox_config,
    set_script_sandbox_dir,
)
from ...tools.script_automation.execution_manager import kill_execution
from ...tools.script_automation.safety import validate_and_resolve_sandbox_dir
from ..schemas import ChatRequest

router = APIRouter(prefix="/api", tags=["script-automation"])

AGENT_NAME = "script_automation"


# ---------------------------------------------------------------------------
# Chat — SSE streaming
# ---------------------------------------------------------------------------


@router.post("/script-chat")
async def script_chat(req: ChatRequest):
    """SSE streaming chat with the Script Automation Agent."""
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
        seq = 0
        try:
            for event in agent.run_turn_stream(req.message):
                seq += 1
                event_type = event.get("event", "unknown")
                payload = dict(event)

                # ── DEBUG: log every SSE event being sent ──────────
                stage_info = ""
                if event_type == "script_execution":
                    stage_info = f" stage={event.get('stage')}"
                elif event_type == "script_output":
                    stage_info = f" stream={event.get('stream')} msg_len={len(str(event.get('message', '')))}"
                elif event_type == "tool_result":
                    stage_info = f" output_len={len(str(event.get('tool_output', '')))}"
                print(f"[SSE #{seq}] {event_type}{stage_info}")
                # ── END DEBUG ─────────────────────────────────────

                yield {
                    "event": event_type,
                    "data": json.dumps(payload, ensure_ascii=False, default=str),
                }
        finally:
            AgentRegistry.release(AGENT_NAME)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Reset — clear conversation history
# ---------------------------------------------------------------------------


@router.get("/script-chat/history")
async def get_script_chat_history():
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


@router.post("/script-chat/reset")
async def reset_script_agent():
    """Reset the agent's conversation history and force-release the lock.

    Note: does NOT delete scripts or packages in the sandbox.
    """
    agent = AgentRegistry.get(AGENT_NAME)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Clear both agent.messages and runner.messages so the reset
    # actually takes effect on the next turn.
    agent.runner.messages = []
    agent.messages = []

    # Force-release the lock in case a previous request hung.
    AgentRegistry.release(AGENT_NAME)

    return {"ok": True, "message": "对话历史已重置"}


# ---------------------------------------------------------------------------
# Status — check if the agent is busy
# ---------------------------------------------------------------------------


@router.get("/script-chat/status")
async def script_chat_status():
    """Return whether the agent is currently busy / initialized."""
    return {
        "busy": AgentRegistry.is_busy(AGENT_NAME),
        "agent_initialized": AgentRegistry.is_initialized(AGENT_NAME),
    }


# ---------------------------------------------------------------------------
# Kill — terminate a running script execution
# ---------------------------------------------------------------------------


@router.post("/script-chat/{execution_id}/kill")
async def kill_script_execution(execution_id: str):
    """Kill a running script execution by its execution_id.

    This endpoint does NOT require the Agent lock — it operates on the
    global process registry directly, allowing termination even when
    the agent is busy.
    """
    killed = kill_execution(execution_id)
    if not killed:
        raise HTTPException(
            status_code=404,
            detail=f"执行 {execution_id} 未找到或已完成",
        )
    return {"ok": True, "execution_id": execution_id, "message": "已终止"}


# ---------------------------------------------------------------------------
# Sandbox directory — get / set working directory
# ---------------------------------------------------------------------------


class SandboxDirRequest(BaseModel):
    directory: str


@router.get("/script-sandbox")
async def get_script_sandbox():
    """返回当前沙箱工作目录路径和存在状态。"""
    sandbox_dir = get_script_sandbox_dir()
    exists = False
    if sandbox_dir:
        p = Path(sandbox_dir)
        exists = p.is_dir()
    return {
        "directory": sandbox_dir or "",
        "exists": exists,
    }


@router.put("/script-sandbox")
async def set_script_sandbox(req: SandboxDirRequest):
    """设置新的沙箱工作目录并重建 Agent。

    验证路径存在且是目录后：
    1. 保存旧 Agent 的对话历史到文件（安全备份）
    2. 清空历史文件（新目录 → 新对话）
    3. 设置新的全局 sandbox_dir
    4. 重建 ScriptAutomationAgent（新 system prompt + 空对话）
    5. 注册新 Agent 到 registry

    Args:
        req: 包含 ``directory`` 字段（绝对路径）。

    Returns:
        成功时 ``{"ok": true, "directory": "/resolved/path"}``，
        失败时 HTTP 400/404。
    """
    from ...agents.agent_runner import AgentRunner

    # 1. 验证路径
    try:
        resolved = validate_and_resolve_sandbox_dir(req.directory)
    except (FileNotFoundError, NotADirectoryError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 获取旧 Agent
    old_agent: ScriptAutomationAgent | None = AgentRegistry.get(AGENT_NAME)

    # 3. 保存旧对话并清空历史文件
    if old_agent is not None and old_agent._history_path is not None:
        hp = old_agent._history_path
        try:
            AgentRunner.save_history(old_agent.runner.messages, hp)
            # 覆盖为空数组
            with open(hp, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False)
        except Exception:
            pass  # 非关键步骤，继续执行

    # 4. 释放锁并注销旧 Agent
    AgentRegistry.release(AGENT_NAME)
    if old_agent is not None:
        AgentRegistry.unregister(AGENT_NAME)

    # 5. 设置新目录到 global state 并持久化
    set_script_sandbox_dir(str(resolved))
    save_script_sandbox_config(str(resolved))

    # 6. 重建 Agent（使用已更新的 global_state）
    try:
        new_agent = old_agent.rebuild() if old_agent else None
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent 重建失败: {e}",
        )

    if new_agent is None:
        raise HTTPException(status_code=503, detail="无法重建 Agent（旧 Agent 不存在）")

    # 7. 注册新 Agent
    AgentRegistry.register(AGENT_NAME, new_agent)

    return {"ok": True, "directory": str(resolved)}
