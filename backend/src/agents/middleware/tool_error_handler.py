"""Middleware for converting tool exceptions into recoverable tool messages."""

from __future__ import annotations

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.messages import ToolMessage


@wrap_tool_call(name="tool_error_handler")
def handle_tool_error(request: ToolCallRequest, handler):
    """Return tool errors as ToolMessage so the agent can continue reasoning.

    This keeps tool failures in-band for the LLM instead of terminating the turn.
    """
    try:
        return handler(request)
    except Exception as exc:
        tool_name = str(request.tool_call.get("name", "unknown_tool"))
        tool_call_id = str(request.tool_call.get("id", ""))
        if not tool_call_id:
            tool_call_id = f"{tool_name}_error"

        return ToolMessage(
            content=(
                f"Tool '{tool_name}' failed: {exc}. "
                "This is a recoverable tool error. "
                "Retry with corrected arguments or choose another tool."
            ),
            tool_call_id=tool_call_id,
        )
