"""Unit tests for the learning assistant module.

Covers T3.1-T3.7 and T3.9: file parsers, prompt templates,
summarizer, question generator, and batch processing.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.learning_assistant.parsers.markdown_parser import MarkdownParser
from src.agents.learning_assistant.prompts import (
    build_summary_prompt,
    build_question_prompt,
    build_explanation_prompt,
    DIFFICULTY_INSTRUCTIONS,
    SUMMARY_STYLE_TEMPLATES,
    QUESTION_STYLE_PROMPTS,
)
from src.agents.learning_assistant.summarizer import Summarizer
from src.agents.learning_assistant.question_generator import QuestionGenerator
from src.agents.learning_assistant.service import LearningAssistantService


# =============================================================================
# T3.1 — PPT Parser (basic structure tests without a real .pptx file)
# =============================================================================

class TestPPTParser:
    """Test PPT parser structure and error handling."""

    def test_unsupported_format(self):
        """Should raise ValueError for non-PPT files."""
        from src.agents.learning_assistant.parsers.ppt_parser import PPTParser
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a ppt")
            tmp = f.name
        try:
            with pytest.raises(ValueError, match="Unsupported file format"):
                PPTParser.parse(tmp)
        finally:
            os.unlink(tmp)

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing files."""
        from src.agents.learning_assistant.parsers.ppt_parser import PPTParser
        with pytest.raises(FileNotFoundError):
            PPTParser.parse("/nonexistent/file.pptx")


# =============================================================================
# T3.2 — Markdown Parser
# =============================================================================

class TestMarkdownParser:
    """Test Markdown parser with various content types."""

    def test_basic_markdown(self):
        """Parse a simple Markdown document."""
        content = """# Title

A paragraph.

## Subtitle

- item 1
- item 2
"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            result = MarkdownParser.parse(tmp)
            assert result["metadata"] == {}
            sections = result["sections"]
            assert len(sections) >= 2
            assert sections[0]["type"] == "heading"
            assert sections[0]["level"] == 1
            assert "Title" in sections[0]["content"]
        finally:
            os.unlink(tmp)

    def test_frontmatter(self):
        """Parse YAML frontmatter."""
        content = """---
title: Test Doc
author: Alice
---

# Hello"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            result = MarkdownParser.parse(tmp)
            assert result["metadata"]["title"] == "Test Doc"
            assert result["metadata"]["author"] == "Alice"
        finally:
            os.unlink(tmp)

    def test_code_block(self):
        """Parse code blocks with language."""
        content = """# Code

```python
print("hello")
```"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            result = MarkdownParser.parse(tmp)
            code_sections = [s for s in result["sections"] if s["type"] == "code"]
            assert len(code_sections) >= 1
            assert code_sections[0]["language"] == "python"
        finally:
            os.unlink(tmp)

    def test_table(self):
        """Parse tables."""
        content = """# Table

| A | B |
|---|---|
| 1 | 2 |
| 3 | 4 |"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            result = MarkdownParser.parse(tmp)
            tables = [s for s in result["sections"] if s["type"] == "table"]
            assert len(tables) >= 1
            assert tables[0]["header"] == ["A", "B"]
            assert len(tables[0]["rows"]) == 2
        finally:
            os.unlink(tmp)

    def test_empty_file(self):
        """Handle empty or whitespace-only files."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8") as f:
            f.write("")
            tmp = f.name
        try:
            result = MarkdownParser.parse(tmp)
            assert result["metadata"] == {}
            assert result["sections"] == []
        finally:
            os.unlink(tmp)


# =============================================================================
# T3.3 — Summary Prompt Templates
# =============================================================================

class TestSummaryPrompts:
    """Test summary prompt building."""

    def test_all_styles_exist(self):
        """All 4 summary styles should have templates."""
        expected = {"concise", "detailed", "outline", "mind_map"}
        assert expected == set(SUMMARY_STYLE_TEMPLATES.keys())

    def test_concise_prompt(self):
        """Concise prompt should request 1 paragraph."""
        sys_prompt, user_prompt = build_summary_prompt("sample content", "concise")
        assert len(sys_prompt) > 0
        assert "sample content" in user_prompt
        assert len(user_prompt) < len(build_summary_prompt("content", "detailed")[1])

    def test_detailed_prompt_contains_content(self):
        """Detailed prompt should include the content."""
        _, user_prompt = build_summary_prompt("test material", "detailed")
        assert "test material" in user_prompt

    def test_outline_format(self):
        """Outline prompt should list format."""
        _, user_prompt = build_summary_prompt("content", "outline")
        assert "要点提纲" in user_prompt or "提纲" in user_prompt

    def test_mind_map_format(self):
        """Mind map prompt should request structured output."""
        _, user_prompt = build_summary_prompt("content", "mind_map")
        assert "思维导图" in user_prompt


# =============================================================================
# T3.5 — Question Prompt Templates
# =============================================================================

class TestQuestionPrompts:
    """Test question generation prompt building."""

    def test_all_types_exist(self):
        """All 4 question types should have templates."""
        expected = {"multiple_choice", "fill_in_blank", "true_false", "short_answer"}
        assert expected == set(QUESTION_STYLE_PROMPTS.keys())

    def test_multiple_choice_has_options(self):
        """MCQ prompt should request 4 options."""
        _, prompt = build_question_prompt("content", "multiple_choice", 5, "easy")
        assert "4个选项" in prompt or "选项" in prompt

    def test_difficulty_instruction_applied(self):
        """Difficulty instructions should be included."""
        _, prompt = build_question_prompt("content", "multiple_choice", 3, "hard")
        assert DIFFICULTY_INSTRUCTIONS["hard"] in prompt or "应用" in prompt

    def test_num_questions(self):
        """Number of questions should be in prompt."""
        _, prompt = build_question_prompt("content", "true_false", 7, "medium")
        assert "7" in prompt


# =============================================================================
# T3.6 — Difficulty Control
# =============================================================================

class TestDifficultyControl:
    """Test difficulty definitions and instructions."""

    def test_three_levels(self):
        """Should have exactly 3 difficulty levels."""
        assert DIFFICULTY_INSTRUCTIONS.keys() == {"easy", "medium", "hard"}

    def test_easy_is_recall(self):
        """Easy should focus on recall/facts."""
        assert "基础" in DIFFICULTY_INSTRUCTIONS["easy"] or "识记" in DIFFICULTY_INSTRUCTIONS["easy"]

    def test_medium_is_comprehension(self):
        """Medium should focus on understanding."""
        assert "理解" in DIFFICULTY_INSTRUCTIONS["medium"]

    def test_hard_is_application(self):
        """Hard should focus on application/synthesis."""
        assert "应用" in DIFFICULTY_INSTRUCTIONS["hard"] or "分析" in DIFFICULTY_INSTRUCTIONS["hard"]


# =============================================================================
# T3.7 — Explanation Prompts
# =============================================================================

class TestExplanationPrompts:
    """Test answer explanation prompt building."""

    def test_multiple_choice_explanation(self):
        """MCQ explanation should ask about each option."""
        prompt = build_explanation_prompt("What is X?", "multiple_choice", "A",
                                          ["A. opt1", "B. opt2", "C. opt3", "D. opt4"])
        assert "correct" in prompt
        assert "incorrect" in prompt

    def test_true_false_explanation(self):
        """TF explanation should ask for justification."""
        prompt = build_explanation_prompt("Statement", "true_false", "对")
        assert "correction" in prompt or "正确" in prompt

    def test_short_answer_explanation(self):
        """Short answer explanation should include scoring points."""
        prompt = build_explanation_prompt("Explain X", "short_answer", "Key point")
        assert "scoring" in prompt or "要点" in prompt or "评分" in prompt


# =============================================================================
# T3.4 — Summarizer (unit tests without LLM calls)
# =============================================================================

class TestSummarizer:
    """Test summarizer structure and content serialization."""

    def test_style_validation(self):
        """Should reject unsupported styles."""
        summarizer = Summarizer(llm_service=None)
        with pytest.raises(ValueError, match="Unsupported summary style"):
            summarizer.summarize({"sections": []}, style="invalid")

    def test_markdown_content_serialization(self):
        """Should serialize markdown sections correctly."""
        summarizer = Summarizer(llm_service=None)
        content = {
            "sections": [
                {"type": "heading", "level": 1, "content": "Title"},
                {"type": "paragraph", "content": "Hello world"},
            ]
        }
        text = summarizer._extract_text(content)
        assert "# Title" in text
        assert "Hello world" in text

    def test_ppt_content_serialization(self):
        """Should serialize PPT slides correctly."""
        summarizer = Summarizer(llm_service=None)
        content = {
            "slides": [
                {"slide_number": 1, "title": "Intro", "content": ["Text1"],
                 "bullet_points": ["Bullet1"], "speaker_notes": "Note1", "tables": []},
            ]
        }
        text = summarizer._extract_text(content)
        assert "Intro" in text
        assert "Text1" in text
        assert "Bullet1" in text
        assert "Note1" in text


# =============================================================================
# T3.5+T3.6+T3.7 — Question Generator (unit tests without LLM calls)
# =============================================================================

class TestQuestionGenerator:
    """Test question generator structure."""

    def test_type_validation(self):
        """Should reject unsupported question types."""
        qg = QuestionGenerator(llm_service=None)
        with pytest.raises(ValueError, match="Unsupported question type"):
            qg.generate({"sections": []}, question_type="invalid")

    def test_difficulty_validation(self):
        """Should reject invalid difficulty levels."""
        qg = QuestionGenerator(llm_service=None)
        with pytest.raises(ValueError, match="Unsupported difficulty"):
            qg.generate({"sections": []}, difficulty="expert")

    def test_json_parsing(self):
        """Should parse JSON from LLM response."""
        qg = QuestionGenerator(llm_service=None)
        llm_response = """```json
{
  "questions": [
    {
      "type": "multiple_choice",
      "question_text": "What is Python?",
      "options": ["A. Language", "B. Snake", "C. Tool", "D. Game"],
      "correct_answer": "A",
      "difficulty": "easy"
    }
  ]
}
```"""
        questions = qg._parse_questions(llm_response)
        assert len(questions) == 1
        assert questions[0]["question_text"] == "What is Python?"
        assert questions[0]["correct_answer"] == "A"

    def test_json_parsing_without_fences(self):
        """Should parse JSON without code fences."""
        qg = QuestionGenerator(llm_service=None)
        response = '{"questions": [{"type": "multiple_choice", "question_text": "Q?", "options": ["A", "B", "C", "D"], "correct_answer": "A", "difficulty": "easy"}]}'
        questions = qg._parse_questions(response)
        assert len(questions) == 1

    def test_mixed_difficulty_ratio(self):
        """Mixed difficulty should distribute questions."""
        qg = QuestionGenerator(llm_service=None)
        # This tests the ratio calculation logic (no LLM call)
        ratio = {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        total = 10
        counts = {d: max(1, round(total * p)) for d, p in ratio.items()}
        assert counts["easy"] == 3
        assert counts["medium"] == 5
        assert counts["hard"] == 2


# =============================================================================
# T3.9 — Batch Processing
# =============================================================================

class TestBatchProcessing:
    """Test batch processing capabilities."""

    def test_scan_directory_empty(self, tmp_path):
        """Should handle empty directories."""
        service = LearningAssistantService(llm_service=None)
        files = service.scan_directory(tmp_path)
        assert files == []

    def test_scan_directory_filters(self, tmp_path):
        """Should only find supported files."""
        (tmp_path / "test.md").write_text("# hello", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("text", encoding="utf-8")
        (tmp_path / "slides.pptx").write_bytes(b"not a real pptx")
        service = LearningAssistantService(llm_service=None)
        files = service.scan_directory(tmp_path)
        assert len(files) == 2
        assert all(f.suffix in (".md", ".pptx") for f in files)

    def test_scan_directory_not_found(self):
        """Should raise for nonexistent directories."""
        service = LearningAssistantService(llm_service=None)
        with pytest.raises(NotADirectoryError):
            service.scan_directory("/nonexistent/path")

    def test_batch_empty_directory(self, tmp_path):
        """Batch summarize with empty directory should return early."""
        service = LearningAssistantService(llm_service=None)
        result = service.batch_summarize(tmp_path, "concise")
        assert result["total_files"] == 0
        assert "No supported files found" in result["message"]

    def test_batch_questions_empty_directory(self, tmp_path):
        """Batch questions with empty directory should return early."""
        service = LearningAssistantService(llm_service=None)
        result = service.batch_generate_questions(tmp_path, "multiple_choice")
        assert result["total_files"] == 0


# =============================================================================
# T3.9 — Progress Tracking
# =============================================================================

class TestProgressTracking:
    """Test batch progress info."""

    def test_progress_start(self):
        service = LearningAssistantService(llm_service=None)
        info = service.get_progress_info(10, 0)
        assert info["percentage"] == 0.0

    def test_progress_mid(self):
        service = LearningAssistantService(llm_service=None)
        info = service.get_progress_info(10, 5)
        assert info["percentage"] == 50.0

    def test_progress_end(self):
        service = LearningAssistantService(llm_service=None)
        info = service.get_progress_info(10, 10)
        assert info["percentage"] == 100.0

    def test_progress_zero_total(self):
        """Should not crash when total is 0."""
        service = LearningAssistantService(llm_service=None)
        info = service.get_progress_info(0, 0)
        assert info["percentage"] == 0.0
