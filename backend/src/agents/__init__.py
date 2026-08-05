"""Agent package — multi-agent hosting with shared infrastructure.

Sub-packages
------------
- scheduler/  : Calendar & task scheduling agent.
- automation/ : (future) Automation script agent.

Shared components (root level)
------------------------------
- agent_factory.py  : create_agent wrapper with summarisation & error middleware.
- agent_runner.py   : Streaming message runner with normalised events.
- registry.py       : Thread-safe AgentRegistry for multi-agent lifecycle.
- middleware/       : Tool error handler & message compression.
"""

from .agent_factory import build_agent
from .agent_runner import AgentRunner
from .registry import AgentRegistry
from .learning_assistant.service import LearningAssistantService, get_learning_assistant_service

__all__ = [
    "AgentRegistry",
    "AgentRunner",
    "LearningAssistantService",
    "get_learning_assistant_service",
    "build_agent",
]
