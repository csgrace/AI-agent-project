"""Quiz question generation with difficulty control and answer explanations.

Supports multiple choice, fill-in-blank, true/false, and short answer questions.
"""

import json
import random
import re
from typing import Any

from ...rag_pipeline.llm_service import LLMService
from .prompts import (
    DIFFICULTY_INSTRUCTIONS,
    build_explanation_prompt,
    build_question_prompt,
    EXPLANATION_SYSTEM_PROMPT,
)

QUESTION_TYPES = {"multiple_choice", "fill_in_blank", "true_false", "short_answer"}
DIFFICULTY_LEVELS = {"easy", "medium", "hard"}


class QuestionGenerator:
    """Generate quiz questions from structured content with difficulty control."""

    def __init__(self, llm_service: LLMService | None = None):
        self.llm = llm_service or LLMService()

    def generate(
        self,
        content: dict[str, Any],
        question_type: str = "multiple_choice",
        num_questions: int = 5,
        difficulty: str | None = None,
    ) -> list[dict[str, Any]]:
        """Generate questions from structured content.

        Args:
            content: Structured content dict (from parser output).
            question_type: Type of question.
            num_questions: How many questions to generate.
            difficulty: Difficulty level (easy, medium, hard) or None for mixed.

        Returns:
            List of question dicts, each with type, question_text, options (if applicable),
            correct_answer, difficulty, and explanations.

        Raises:
            ValueError: If question_type or difficulty is invalid.
        """
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"Unsupported question type: {question_type}. Choose from {QUESTION_TYPES}")
        if difficulty is not None and difficulty not in DIFFICULTY_LEVELS:
            raise ValueError(f"Unsupported difficulty: {difficulty}. Choose from {DIFFICULTY_LEVELS}")

        text_content = self._extract_text(content)

        system_prompt, user_prompt = build_question_prompt(
            content=text_content,
            question_type=question_type,
            num_questions=num_questions,
            difficulty=difficulty,
        )

        result = self.llm._chat_completion(
            prompt=user_prompt,
            temperature=0.4,
            max_tokens=4096,
            label=f"generate_{question_type}",
            system_prompt=system_prompt,
        )

        if not result:
            return []

        questions = self._parse_questions(result)
        if not questions:
            return []

        # Add explanations (T3.7)
        for q in questions:
            q["explanations"] = self._generate_explanation(q)

        return questions

    def generate_mixed_difficulty(
        self,
        content: dict[str, Any],
        question_type: str = "multiple_choice",
        total_questions: int = 10,
        ratio: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate questions with a specified difficulty distribution.

        Args:
            content: Structured content dict.
            question_type: Type of question.
            total_questions: Total number of questions to generate.
            ratio: Dict mapping difficulty to proportion, e.g.
                {"easy": 0.3, "medium": 0.5, "hard": 0.2}.
                Defaults to equal distribution.

        Returns:
            List of question dicts with mixed difficulties, sorted by difficulty.
        """
        if ratio is None:
            ratio = {"easy": 1 / 3, "medium": 1 / 3, "hard": 1 / 3}

        questions: list[dict[str, Any]] = []
        for difficulty, proportion in ratio.items():
            if proportion <= 0 or difficulty not in DIFFICULTY_LEVELS:
                continue
            count = max(1, round(total_questions * proportion))
            batch = self.generate(content, question_type, count, difficulty)
            questions.extend(batch)

        random.shuffle(questions)
        return questions[:total_questions]

    def _extract_text(self, content: dict[str, Any]) -> str:
        """Extract text from structured content."""
        if "sections" in content:
            return self._serialize_sections(content["sections"])
        if "slides" in content:
            return self._serialize_slides(content["slides"])
        return str(content)

    def _serialize_sections(self, sections: list[dict[str, Any]]) -> str:
        """Serialize markdown sections to text."""
        from .summarizer import _serialize_content
        return _serialize_content(sections)

    def _serialize_slides(self, slides: list[dict[str, Any]]) -> str:
        """Serialize PPT slides to text."""
        lines: list[str] = []
        for slide in slides:
            num = slide.get("slide_number", 0)
            title = slide.get("title", "")
            lines.append(f"幻灯片 {num}: {title}")
            for item in slide.get("content", []):
                lines.append(item)
            for bullet in slide.get("bullet_points", []):
                lines.append(f"- {bullet}")
            notes = slide.get("speaker_notes", "")
            if notes:
                lines.append(f"备注: {notes}")
            lines.append("")
        return "\n".join(lines)

    def _parse_questions(self, text: str) -> list[dict[str, Any]]:
        """Parse LLM response into question dicts."""
        # Try to extract JSON from code blocks
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        # Try parsing as JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "questions" in data:
                return data["questions"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object starting with { or [
        brace_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if brace_match:
            try:
                data = json.loads(brace_match.group(1))
                if isinstance(data, dict) and "questions" in data:
                    return data["questions"]
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        return []

    def _generate_explanation(self, question: dict[str, Any]) -> dict[str, Any]:
        """Generate educational explanation for a question.

        Args:
            question: The question dict.

        Returns:
            Explanation dict with type-specific fields.
        """
        q_type = question.get("type", "multiple_choice")
        q_text = question.get("question_text", "")
        correct = question.get("correct_answer", "")
        options = question.get("options")

        prompt = build_explanation_prompt(q_text, q_type, correct, options)

        result = self.llm._chat_completion(
            prompt=prompt,
            temperature=0.3,
            max_tokens=1024,
            label=f"explain_{q_type}",
            system_prompt=EXPLANATION_SYSTEM_PROMPT,
        )

        if not result:
            return {"correct": "解释生成失败。"}

        return self._parse_explanation(result)

    def _parse_explanation(self, text: str) -> dict[str, Any]:
        """Parse LLM explanation response into a dict."""
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        try:
            data = json.loads(text)
            if isinstance(data, dict) and "explanations" in data:
                return data["explanations"]
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        return {"correct": text.strip()[:500]}
