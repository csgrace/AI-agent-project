"""Conversation memory for Document QA service.

Provides sliding-window multi-turn context for campus QA interactions.
Each session tracks recent Q&A pairs and injects them into subsequent prompts.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ...rag_pipeline.models import SearchResult


@dataclass
class QATurn:
    """Single QA turn record."""
    question: str
    answer: str
    sources: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class DocumentQAMemory:
    """Sliding-window conversation memory for document QA.
    
    Maintains recent conversation context to enable multi-turn interactions
    like follow-up questions and pronoun resolution.
    
    Usage:
        memory = DocumentQAMemory(window_size=6)
        memory.add_turn("什么是VPN", "VPN是...", ["campus_guide.pdf"])
        context = memory.get_context_str()
    """

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self._history: OrderedDict[str, QATurn] = OrderedDict()

    def add_turn(
        self,
        question: str,
        answer: str,
        sources: Optional[List[str]] = None,
    ) -> None:
        """Record a QA turn."""
        turn_id = str(int(time.time() * 1000))
        self._history[turn_id] = QATurn(
            question=question[:200],
            answer=answer[:300],
            sources=sources or [],
        )
        # Enforce sliding window
        while len(self._history) > self.window_size:
            self._history.popitem(last=False)

    def get_context_str(self) -> str:
        """Get formatted conversation context for prompt injection."""
        if not self._history:
            return ""

        lines = ["<conversation_history>"]
        for i, (_, turn) in enumerate(self._history.items(), 1):
            lines.append(f'<turn number="{i}">')
            lines.append(f"  <question>{turn.question}</question>")
            lines.append(f"  <answer_summary>{turn.answer[:150]}...</answer_summary>")
            if turn.sources:
                lines.append(f"  <sources>{', '.join(turn.sources[:2])}</sources>")
            lines.append("</turn>")
        lines.append("</conversation_history>")
        lines.append(
            "\n注：回答后续问题时可以参考以上历史对话，保持回答的连贯性。"
        )
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all conversation history."""
        self._history.clear()

    @property
    def turn_count(self) -> int:
        return len(self._history)


# Global session store (session_id -> memory)
_session_memories: Dict[str, DocumentQAMemory] = {}


def get_or_create_memory(session_id: str, window_size: int = 6) -> DocumentQAMemory:
    """Get or create memory instance for a session."""
    if session_id not in _session_memories:
        _session_memories[session_id] = DocumentQAMemory(window_size=window_size)
    return _session_memories[session_id]


def clear_session_memory(session_id: str) -> None:
    """Clear memory for a specific session."""
    if session_id in _session_memories:
        _session_memories[session_id].clear()


def get_all_sessions() -> Dict[str, DocumentQAMemory]:
    """Get all active sessions (for admin/monitoring)."""
    return dict(_session_memories)
