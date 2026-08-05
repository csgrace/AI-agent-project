"""Generic agent factory for building LangChain create_agent instances.

Provides shared infrastructure (runtime timestamp injection, skill catalog
formatting, default middleware) that can be customised per agent via
parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from .middleware import handle_tool_error


CN_TZ = ZoneInfo("Asia/Shanghai")


def build_runtime_system_prompt(base_prompt: str) -> str:
    """Attach runtime timestamp to system prompt for temporal awareness."""
    now = datetime.now(CN_TZ).replace(tzinfo=None)
    now_text = now.isoformat(timespec="seconds")
    return (
        f"{base_prompt.strip()}\n"
        f"Current runtime datetime (Asia/Shanghai, naive): {now_text}.\n"
        "When interpreting relative dates like today/tomorrow/this week, use this runtime datetime.\n"
        "For tool datetime fields, always use Asia/Shanghai local naive datetime strings without timezone offsets."
    )


def _format_skill_catalog(skill_registry: Dict[str, Dict[str, Any]]) -> str:
    """Build a concise skill catalog text for system prompt injection."""
    if not skill_registry:
        return ""

    lines = [
        "Available skills (loaded at startup):",
        "Use the load_skill tool only when detailed procedural guidance is required.",
    ]
    for skill_name in sorted(skill_registry.keys()):
        description = str(skill_registry[skill_name].get("description", "")).strip()
        if description:
            lines.append(f"- {skill_name}: {description}")
        else:
            lines.append(f"- {skill_name}")

    return "\n".join(lines)


def default_middleware(
    model: Any,
    *,
    summary_trigger: int = 36,
    summary_keep: int = 14,
) -> list:
    """Return the default middleware pipeline used by the scheduler agent.

    Can be passed directly to :func:`build_agent` via the ``middleware``
    parameter, or used as a starting point for customisation::

        my_middleware = [m for m in default_middleware(model) if ...]
        my_middleware.append(my_custom_middleware)
        build_agent(model, tools, system_prompt, middleware=my_middleware)
    """
    return [
        SummarizationMiddleware(
            model=model,
            trigger=("messages", summary_trigger),
            keep=("messages", summary_keep),
        ),
        handle_tool_error,
    ]


def build_agent(
    model: Any,
    *,
    tools: List[Any],
    system_prompt: str,
    skill_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    middleware: Optional[Sequence[Any]] = None,
):
    """Create a compiled LangChain agent with shared infrastructure.

    Parameters
    ----------
    model:
        The LLM to power the agent (e.g. ``ChatOpenAI``).
    tools:
        List of ``@tool``-decorated functions the agent can call.
    system_prompt:
        **Required.** System prompt defining the agent's persona and rules.
        Unlike the old interface, there is **no default** — forgetting to
        supply one will raise a ``TypeError`` at call time.
    skill_registry:
        Optional dict of available skills (name -> metadata).  If provided,
        a skill catalog is appended to the system prompt.
    middleware:
        Optional middleware pipeline.  When ``None`` (the default),
        ``default_middleware(model)`` is used (summarisation + tool error
        handling).  Pass an empty list ``[]`` to disable middleware entirely.
    """
    resolved_system_prompt = build_runtime_system_prompt(system_prompt)
    skill_catalog = _format_skill_catalog(skill_registry or {})
    if skill_catalog:
        resolved_system_prompt = f"{resolved_system_prompt}\n\n{skill_catalog}"

    if middleware is None:
        middleware = default_middleware(model)

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=resolved_system_prompt,
        middleware=list(middleware),
    )
