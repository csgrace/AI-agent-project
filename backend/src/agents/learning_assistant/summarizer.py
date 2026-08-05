"""Content summarization service with multiple style templates.

Supports concise, detailed, outline, and mind_map summary styles.
"""

import json
import re
from typing import Any

from ...rag_pipeline.llm_service import LLMService
from .prompts import build_summary_prompt

SUMMARIZABLE_TYPES = {"heading", "paragraph", "list", "code", "blockquote", "table", "latex"}


def _serialize_content(sections: list[dict[str, Any]]) -> str:
    """Convert structured sections into plain text for LLM input."""
    lines: list[str] = []
    for sec in sections:
        t = sec.get("type", "")
        if t not in SUMMARIZABLE_TYPES:
            continue
        if t == "heading":
            prefix = "#" * sec.get("level", 1)
            lines.append(f"{prefix} {sec.get('content', '')}")
        elif t == "paragraph":
            lines.append(sec.get("content", ""))
        elif t == "list":
            for item in sec.get("items", []):
                _render_list_item(item, lines, 0)
        elif t == "code":
            lines.append(f"[代码块: {sec.get('language', '')}]\n{sec.get('content', '')}\n[/代码块]")
        elif t == "blockquote":
            lines.append(f"> {sec.get('content', '')}")
        elif t == "table":
            header = " | ".join(sec.get("header", []))
            rows = [" | ".join(r) for r in sec.get("rows", [])]
            lines.append(f"[表格]\n{header}\n" + "\n".join(rows) + "\n[/表格]")
        elif t == "latex":
            lines.append(f"[公式] {sec.get('content', '')}")
    return "\n\n".join(lines)


def _render_list_item(item: dict[str, Any], lines: list[str], depth: int) -> None:
    """Render a list item and its children recursively."""
    indent = "  " * depth
    prefix = "- " if depth == 0 else "* "
    content = item.get("content", "")
    if content:
        lines.append(f"{indent}{prefix}{content}")
    for child in item.get("children", []):
        lines.append(f"{indent}  {child.get('content', '')}")
    for sub in item.get("sub_items", []):
        _render_list_item(sub, lines, depth + 1)


class Summarizer:
    """Generate content summaries in different styles using LLM."""

    STYLES = {"concise", "detailed", "outline", "mind_map"}

    def __init__(self, llm_service: LLMService | None = None):
        self.llm = llm_service or LLMService()

    def summarize(
        self,
        content: dict[str, Any],
        style: str = "concise",
    ) -> str:
        """Generate a summary for the given structured content.

        Args:
            content: Structured content dict (from parser output).
                Must contain a "sections" list for Markdown or "slides" list for PPT.
            style: Summary style. One of "concise", "detailed", "outline", "mind_map".

        Returns:
            Generated summary text.

        Raises:
            ValueError: If style is not supported.
        """
        if style not in self.STYLES:
            raise ValueError(f"Unsupported summary style: {style}. Choose from {self.STYLES}")

        # Serialize content based on its source type
        text_content = self._extract_text(content)

        system_prompt, user_prompt = build_summary_prompt(text_content, style)

        result = self.llm._chat_completion(
            prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
            label=f"summarize_{style}",
            system_prompt=system_prompt,
        )

        if not result:
            return "摘要生成失败。请检查 LLM 服务是否可用。"

        cleaned = self._post_process(result)
        return cleaned

    def _extract_text(self, content: dict[str, Any]) -> str:
        """Extract text from either Markdown sections or PPT slides."""
        if "sections" in content:
            return _serialize_content(content["sections"])
        if "slides" in content:
            return self._serialize_slides(content["slides"])
        return str(content)

    def _serialize_slides(self, slides: list[dict[str, Any]]) -> str:
        """Serialize PPT slides into text."""
        lines: list[str] = []
        for slide in slides:
            num = slide.get("slide_number", 0)
            title = slide.get("title", "")
            lines.append(f"--- 幻灯片 {num}: {title} ---")
            for item in slide.get("content", []):
                lines.append(item)
            for bullet in slide.get("bullet_points", []):
                lines.append(f"  - {bullet}")
            notes = slide.get("speaker_notes", "")
            if notes:
                lines.append(f"  [备注]: {notes}")
            for table in slide.get("tables", []):
                for row in table:
                    lines.append("  | " + " | ".join(row) + " |")
            lines.append("")
        return "\n".join(lines)

    def _post_process(self, text: str) -> str:
        """Clean up whitespace and formatting issues."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        # Remove any markdown code fences the LLM might have wrapped around the output
        text = re.sub(r"^```[\w]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        return text.strip()
