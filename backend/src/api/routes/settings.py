"""Settings API — runtime LLM configuration.

Endpoints
---------
- ``GET  /api/settings/llm/status`` — current config summary (keys masked)
- ``POST /api/settings/llm`` — set new config, inject credentials into agents, persist
- ``POST /api/settings/llm/test`` — validate a key with a lightweight call
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pathlib import Path
from pydantic import BaseModel, Field, SecretStr

from ...agents.registry import AgentRegistry
from ...services.document_qa import reset_document_qa_service
from ...services.llm_config import LLMConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class TierConfig(BaseModel):
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    temperature: Optional[float] = None


class LLMSetConfigRequest(BaseModel):
    provider: str = "dashscope"
    api_key: str = ""
    base_url: Optional[str] = None
    fallback_provider: Optional[str] = None
    fallback_api_key: Optional[str] = None
    fallback_base_url: Optional[str] = None
    fallback_enabled: bool = True
    tiers: Optional[Dict[str, Dict[str, Any]]] = None


class LLMTestRequest(BaseModel):
    provider: str = "dashscope"
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None


class LLMStatusResponse(BaseModel):
    configured: bool
    provider: Optional[str] = None
    base_url: str = ""
    fallback_provider: Optional[str] = None
    fallback_base_url: str = ""
    fallback_enabled: bool = False
    has_api_key: bool = False
    has_fallback_key: bool = False
    api_key_masked: str = ""
    fallback_api_key_masked: str = ""
    tiers: Dict[str, Any] = Field(default_factory=dict)
    llm_available: bool = False


class LLMTestResponse(BaseModel):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]


def _rebuild_all_agents(llm_config: LLMConfig) -> int:
    """Hot-swap the inner ChatOpenAI on all registered agents via proxy.

    Creates a fresh ChatOpenAI with current config and swaps it into the
    ChatModelProxy that all agents share — no graph recompilation needed,
    no internal field hacking.  The proxy handles delegation transparently.

    Returns the number of agents updated.
    """
    active = llm_config._active_config(use_fallback=False)
    new_api_key = active["api_key"]
    new_base_url = active["base_url"]
    if not new_api_key:
        return 0

    count = 0
    # All agents share the same ChatModelProxy instance, so swapping once
    # affects all of them.  Still iterate for safety / future-proofing.
    seen = set()
    for name in AgentRegistry.list_agents():
        agent = AgentRegistry.get(name)
        if agent is None:
            continue
        proxy = getattr(agent, "model", None)
        if proxy is None or id(proxy) in seen:
            continue
        seen.add(id(proxy))
        if hasattr(proxy, "swap_model"):
            # Build a fresh ChatOpenAI preserving the original model_name + temperature
            inner = proxy._inner
            new_llm = ChatOpenAI(
                model=inner.model_name,
                api_key=SecretStr(new_api_key),
                base_url=new_base_url,
                temperature=inner.temperature,
            )
            proxy.swap_model(new_llm)
            count += 1

    if count:
        print(f"[settings] {count} proxy instance(s) hot-swapped with new credentials.")
    return count


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/llm/status", response_model=LLMStatusResponse)
async def get_llm_status():
    """Return a summary of the current LLM configuration (keys masked)."""
    cfg = LLMConfig.get_instance()

    has_key = bool(cfg.api_key)
    has_fallback = cfg.is_fallback_available()

    # Is there any usable LLM at all?
    llm_available = has_key or bool(os.getenv("DASHSCOPE_API_KEY")) or bool(os.getenv("OPENAI_API_KEY"))

    return LLMStatusResponse(
        configured=has_key or cfg._version > 0,
        provider=cfg.provider if has_key else None,
        base_url=cfg.base_url or "",
        fallback_provider=cfg.fallback_provider if has_fallback else None,
        fallback_base_url=cfg.fallback_base_url or "",
        fallback_enabled=cfg.fallback_enabled,
        has_api_key=has_key,
        has_fallback_key=has_fallback,
        api_key_masked=_mask_key(cfg.api_key),
        fallback_api_key_masked=_mask_key(cfg.fallback_api_key),
        tiers=cfg.tiers,
        llm_available=llm_available,
    )


@router.post("/llm", response_model=LLMStatusResponse)
async def set_llm_config(req: LLMSetConfigRequest):
    """Set a new LLM configuration, inject credentials into agents, and persist.

    Agents are pre-compiled at startup (with placeholder credentials if no
    key was available).  This endpoint only mutates the existing ChatOpenAI
    instances in-place — no LangChain graph recompilation needed.
    """
    cfg = LLMConfig.get_instance()

    # If api_key is empty, keep the existing one (to allow frontend to
    # omit the key without overwriting it).
    api_key = req.api_key or cfg.api_key or ""
    fallback_api_key = req.fallback_api_key or cfg.fallback_api_key or ""

    cfg.set_config(
        provider=req.provider,
        api_key=api_key,
        base_url=req.base_url,
        fallback_provider=req.fallback_provider,
        fallback_api_key=fallback_api_key,
        fallback_base_url=req.fallback_base_url,
        fallback_enabled=req.fallback_enabled,
        tiers=req.tiers,
    )

    updated = _rebuild_all_agents(cfg)
    print(f"[settings] LLM config updated, {updated} agent(s) credentials injected.")

    # Reset cached singletons that hold LLMService instances so they
    # pick up the new credentials on the next request.
    reset_document_qa_service()

    try:
        from ...agents.learning_assistant.service import reset_learning_assistant_service
        reset_learning_assistant_service()
    except ImportError:
        pass

    return await get_llm_status()


@router.post("/llm/test", response_model=LLMTestResponse)
async def test_llm_connection(req: LLMTestRequest):
    """Test a provider/api-key/model combination with a simple API call.

    This does **not** persist the config — it's a dry-run validation.
    """
    base_url = req.base_url
    if not base_url:
        if req.provider == "dashscope":
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        elif req.provider == "openai":
            base_url = "https://api.openai.com/v1"
        else:
            base_url = ""

    model = req.model or "gpt-4o-mini" if req.provider == "openai" else "qwen-turbo"

    try:
        client = OpenAI(api_key=req.api_key, base_url=base_url or None)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "回复ok"}],
            max_tokens=10,
        )
        reply = response.choices[0].message.content.strip()
        return LLMTestResponse(ok=True, message=f"连接成功，模型回复: {reply}")
    except Exception as exc:
        return LLMTestResponse(ok=False, message=f"连接失败: {exc}")
