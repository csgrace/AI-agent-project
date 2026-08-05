"""Middleware adapters built on top of LangChain SummarizationMiddleware."""

from __future__ import annotations

from langchain.agents.middleware import SummarizationMiddleware


def build_summarization_middleware(model, *, trigger: int = 24, keep: int = 10) -> SummarizationMiddleware:
    """Return a configured SummarizationMiddleware instance."""
    return SummarizationMiddleware(
        model=model,
        trigger=trigger,
        keep=keep,
    )

