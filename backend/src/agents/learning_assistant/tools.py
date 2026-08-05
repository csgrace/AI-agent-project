"""LangChain tools for the learning assistant agent.

Provides summarization and question generation tools that can be
called by the LLM via the create_agent runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from langchain.tools import tool

from .service import LearningAssistantService


def _resolve_path(file_path: str) -> str:
    """Resolve a file path, checking storage/uploads as fallback."""
    p = Path(file_path)
    if p.is_absolute() and p.exists():
        return str(p.resolve())
    if p.exists():
        return str(p.resolve())
    # Try storage/uploads
    from_path = (
        Path(__file__).resolve().parents[3] / "storage" / "uploads" / p.name
    )
    if from_path.exists():
        return str(from_path.resolve())
    return str(p.resolve())


def _get_service() -> LearningAssistantService:
    return LearningAssistantService()


@tool
def summarize_document(
    file_path: str,
    style: str = "concise",
) -> str:
    """Summarize a PPT or Markdown document in the specified style.

    Use this tool when the user asks to summarize, outline, or get a
    mind-map of an uploaded document.

    Args:
        file_path: Path or filename of the uploaded file (.pptx/.ppt/.md).
        style: Summary style — one of "concise", "detailed", "outline", "mind_map".

    Returns:
        The generated summary text.
    """
    resolved = _resolve_path(file_path)
    svc = _get_service()
    result = svc.summarize_file(resolved, style)
    return result["summary"]


@tool
def generate_questions(
    file_path: str,
    question_type: str = "multiple_choice",
    num_questions: int = 5,
    difficulty: Optional[str] = None,
) -> str:
    """Generate quiz questions from a PPT or Markdown document.

    Use this tool when the user asks to generate quiz questions, test
    questions, or exam questions from an uploaded document.

    Args:
        file_path: Path or filename of the uploaded file (.pptx/.ppt/.md).
        question_type: Type of question — one of "multiple_choice",
            "fill_in_blank", "true_false", "short_answer".
        num_questions: Number of questions to generate (1-20).
        difficulty: Difficulty level — "easy", "medium", "hard", or None for mixed.

    Returns:
        JSON string with _type: "quiz" and questions data for frontend rendering.
    """
    resolved = _resolve_path(file_path)
    svc = _get_service()
    result = svc.generate_questions(
        resolved,
        question_type=question_type,
        num_questions=num_questions,
        difficulty=difficulty,
    )

    output = {
        "_type": "quiz",
        "metadata": {
            "file_name": result.get("file_name", ""),
            "question_type": question_type,
            "total": result.get("total_questions", 0),
            "difficulty": difficulty or "mixed",
        },
        "questions": result.get("questions", []),
    }
    return json.dumps(output, ensure_ascii=True)


@tool
def list_supported_formats() -> str:
    """List the file formats and options supported by the learning assistant.

    Use this tool when the user asks what file types are supported or
    what options are available for summarization or questions.
    """
    return (
        "支持的格式：.pptx、.ppt、.md\n\n"
        "总结风格：\n"
        "- concise：简洁总结（1个段落）\n"
        "- detailed：详细总结（多段落）\n"
        "- outline：要点提纲\n"
        "- mind_map：思维导图格式\n\n"
        "题目类型：\n"
        "- multiple_choice：单选题（4个选项）\n"
        "- fill_in_blank：填空题\n"
        "- true_false：判断题\n"
        "- short_answer：简答题\n\n"
        "难度级别：easy（简单）、medium（中等）、hard（困难），不指定则为混合难度"
    )
