"""Learning assistant orchestrator with batch processing capability.

Ties together file parsers, summarizer, and question generator.
Supports single-file and batch processing modes.
"""

import os
import time
from pathlib import Path
from typing import Any

from ...rag_pipeline.llm_service import LLMService
from .parsers.ppt_parser import PPTParser
from .parsers.markdown_parser import MarkdownParser
from .summarizer import Summarizer
from .question_generator import QuestionGenerator

SUPPORTED_EXTENSIONS = {".pptx", ".ppt", ".md"}


class LearningAssistantService:
    """Main orchestrator for the learning assistant module."""

    def __init__(self, llm_service: LLMService | None = None):
        self.llm = llm_service or LLMService()
        self.summarizer = Summarizer(self.llm)
        self.question_gen = QuestionGenerator(self.llm)

    # ----- Single file operations -----

    def parse_file(self, file_path: str | Path) -> dict[str, Any]:
        """Parse a single file (PPT or Markdown) and return structured content.

        Args:
            file_path: Path to the file.

        Returns:
            Structured content dict.

        Raises:
            ValueError: If file format is not supported.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".pptx" or ext == ".ppt":
            return PPTParser.parse(path)
        elif ext == ".md":
            return MarkdownParser.parse(path)
        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    def summarize_file(
        self,
        file_path: str | Path,
        style: str = "concise",
    ) -> dict[str, Any]:
        """Parse and summarize a single file.

        Args:
            file_path: Path to the file.
            style: Summary style.

        Returns:
            Dict with file_name, style, and summary fields.
        """
        content = self.parse_file(file_path)
        summary = self.summarizer.summarize(content, style)
        return {
            "file_name": Path(file_path).name,
            "style": style,
            "summary": summary,
        }

    def generate_questions(
        self,
        file_path: str | Path,
        question_type: str = "multiple_choice",
        num_questions: int = 5,
        difficulty: str | None = None,
        difficulty_ratio: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Parse a file and generate quiz questions.

        Args:
            file_path: Path to the file.
            question_type: Type of question.
            num_questions: Number of questions.
            difficulty: Single difficulty level, or None for mixed.
            difficulty_ratio: Difficulty distribution (only used if difficulty is None).

        Returns:
            Dict with file_name, questions list, and metadata.
        """
        content = self.parse_file(file_path)

        if difficulty is not None:
            questions = self.question_gen.generate(content, question_type, num_questions, difficulty)
        else:
            questions = self.question_gen.generate_mixed_difficulty(
                content, question_type, num_questions, difficulty_ratio
            )

        return {
            "file_name": Path(file_path).name,
            "question_type": question_type,
            "total_questions": len(questions),
            "questions": questions,
        }

    # ----- Batch operations (T3.9) -----

    def scan_directory(self, directory: str | Path) -> list[Path]:
        """Scan a directory for supported files.

        Args:
            directory: Path to the directory.

        Returns:
            List of supported file paths, sorted by name.

        Raises:
            NotADirectoryError: If directory does not exist.
        """
        path = Path(directory)
        if not path.exists():
            raise NotADirectoryError(f"Directory not found: {directory}")

        files: list[Path] = []
        for f in sorted(path.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(f)
        return files

    def batch_summarize(
        self,
        directory: str | Path,
        style: str = "concise",
        merge: bool = False,
    ) -> dict[str, Any]:
        """Process all supported files in a directory for summarization.

        Args:
            directory: Path to the directory containing files.
            style: Summary style.
            merge: If True, merge all content before summarizing.

        Returns:
            Dict with processing results and metadata.
        """
        files = self.scan_directory(directory)
        if not files:
            return {"files": [], "total_files": 0, "message": "No supported files found."}

        results: list[dict[str, Any]] = []
        total_start = time.time()

        if merge:
            # Merge all content into one summary
            all_content: dict[str, Any] = {"file_name": "merged", "slides": [], "sections": []}
            for f in files:
                content = self.parse_file(f)
                all_content["slides"].extend(content.get("slides", []))
                all_content["sections"].extend(content.get("sections", []))
            summary = self.summarizer.summarize(all_content, style)
            results.append({
                "file_name": "merged",
                "files_merged": [f.name for f in files],
                "style": style,
                "summary": summary,
            })
        else:
            for f in files:
                try:
                    result = self.summarize_file(f, style)
                    results.append(result)
                except Exception as e:
                    results.append({"file_name": f.name, "error": str(e)})

        elapsed = time.time() - total_start
        return {
            "files": results,
            "total_files": len(files),
            "mode": "merged" if merge else "individual",
            "time_seconds": round(elapsed, 2),
        }

    def batch_generate_questions(
        self,
        directory: str | Path,
        question_type: str = "multiple_choice",
        num_questions: int = 5,
        difficulty: str | None = None,
        difficulty_ratio: dict[str, float] | None = None,
        merge: bool = False,
    ) -> dict[str, Any]:
        """Process all supported files in a directory for question generation.

        Args:
            directory: Path to the directory.
            question_type: Type of question.
            num_questions: Number of questions.
            difficulty: Difficulty level.
            difficulty_ratio: Difficulty distribution.
            merge: If True, merge all content before generating.

        Returns:
            Dict with processing results.
        """
        files = self.scan_directory(directory)
        if not files:
            return {"files": [], "total_files": 0, "message": "No supported files found."}

        results: list[dict[str, Any]] = []
        total_start = time.time()

        if merge:
            all_content: dict[str, Any] = {"file_name": "merged", "slides": [], "sections": []}
            for f in files:
                content = self.parse_file(f)
                all_content["slides"].extend(content.get("slides", []))
                all_content["sections"].extend(content.get("sections", []))

            if difficulty is not None:
                questions = self.question_gen.generate(all_content, question_type, num_questions, difficulty)
            else:
                questions = self.question_gen.generate_mixed_difficulty(
                    all_content, question_type, num_questions, difficulty_ratio
                )
            results.append({
                "file_name": "merged",
                "files_merged": [f.name for f in files],
                "total_questions": len(questions),
                "questions": questions,
            })
        else:
            for f in files:
                try:
                    result = self.generate_questions(f, question_type, num_questions, difficulty, difficulty_ratio)
                    results.append(result)
                except Exception as e:
                    results.append({"file_name": f.name, "error": str(e)})

        elapsed = time.time() - total_start
        return {
            "files": results,
            "total_files": len(files),
            "mode": "merged" if merge else "individual",
            "time_seconds": round(elapsed, 2),
        }

    def get_progress_info(self, total: int, current: int) -> dict[str, Any]:
        """Get progress information for batch processing.

        Args:
            total: Total number of items.
            current: Current item index.

        Returns:
            Dict with progress info.
        """
        return {
            "current": current,
            "total": total,
            "percentage": round(current / max(total, 1) * 100, 1),
        }


# Global singleton
_service_instance: LearningAssistantService | None = None


def get_learning_assistant_service() -> LearningAssistantService:
    """Get or create the global LearningAssistantService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = LearningAssistantService()
    return _service_instance


def reset_learning_assistant_service() -> None:
    """Force the LearningAssistantService singleton to be recreated on next access."""
    global _service_instance
    _service_instance = None
