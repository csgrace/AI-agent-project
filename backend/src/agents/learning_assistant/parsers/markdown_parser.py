"""Markdown file parser using mistletoe.

Parses Markdown files into structured JSON with full document hierarchy
including headings, paragraphs, lists, code blocks, blockquotes, tables,
YAML frontmatter, LaTeX, and Mermaid diagrams.
"""

import re
from pathlib import Path
from typing import Any

import mistletoe
from mistletoe.block_token import (
    BlockCode,
    CodeFence,
    Heading,
    List,
    ListItem,
    Paragraph,
    Quote,
    Table,
    ThematicBreak,
)


class MarkdownParser:
    """Parser for Markdown (.md) files."""

    @staticmethod
    def parse(file_path: str | Path) -> dict[str, Any]:
        """Parse a Markdown file and return structured content.

        Args:
            file_path: Path to the .md file.

        Returns:
            JSON-compatible dict with metadata and sections list.
            Each section has type, and type-specific fields.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw_text = path.read_text(encoding="utf-8")

        # Extract YAML frontmatter
        metadata, body_start = _extract_frontmatter(raw_text)

        doc = mistletoe.Document(body_start)
        sections = _parse_document(doc)

        return {
            "metadata": metadata,
            "sections": sections,
        }


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter from the beginning of the text."""
    metadata: dict[str, str] = {}
    rest = text

    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            frontmatter_text = text[3:end].strip()
            rest = text[end + 3:].strip()

            for line in frontmatter_text.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    metadata[key.strip()] = value.strip().strip("\"'")

    return metadata, rest


def _parse_document(doc) -> list[dict[str, Any]]:
    """Parse all block-level tokens from the document."""
    sections: list[dict[str, Any]] = []

    for token in doc.children:
        section = _parse_block_token(token)
        if section:
            sections.append(section)

    return sections


def _parse_block_token(token) -> dict[str, Any] | None:
    """Parse a single block-level token into a structured dict."""
    if isinstance(token, Heading):
        children_text = _extract_children_text(token)
        return {"type": "heading", "level": token.level, "content": children_text}

    if isinstance(token, Paragraph):
        children_text = _extract_children_text(token)
        return {"type": "paragraph", "content": children_text}

    if isinstance(token, (BlockCode, CodeFence)):
        lang = token.language or ""
        content = token.children[0].content if token.children else ""
        return {"type": "code", "language": lang, "content": content}

    if isinstance(token, List):
        items = _parse_list_items(token)
        return {"type": "list", "ordered": token.start is not None, "items": items}

    if isinstance(token, Quote):
        children_text = _extract_children_text(token)
        return {"type": "blockquote", "content": children_text}

    if isinstance(token, Table):
        return _parse_table(token)

    if isinstance(token, ThematicBreak):
        return {"type": "thematic_break"}

    # Check for LaTeX blocks by content pattern
    text = _extract_children_text(token)
    if text and _is_latex_block(text):
        return {"type": "latex", "content": text}

    if text and _is_mermaid_block(text):
        return {"type": "mermaid", "content": text}

    return None


def _parse_list_items(token) -> list[dict[str, Any]]:
    """Parse list items recursively."""
    items: list[dict[str, Any]] = []
    for child in token.children:
        if isinstance(child, ListItem):
            item_text = _extract_children_text(child)
            nested = [_parse_block_token(sub) for sub in child.children if not isinstance(sub, List)]
            nested = [n for n in nested if n]

            sub_items: list[dict[str, Any]] = []
            for sub in child.children:
                if isinstance(sub, List):
                    sub_items = _parse_list_items(sub)

            item: dict[str, Any] = {"content": item_text}
            if nested:
                item["children"] = nested
            if sub_items:
                item["sub_items"] = sub_items
            items.append(item)
    return items


def _parse_table(token) -> dict[str, Any]:
    """Parse a table token."""
    # Header row
    header = [cell.children[0].content if cell.children else "" for cell in token.header.children]

    # Body rows
    rows: list[list[str]] = []
    for row_token in token.children:
        cells = [cell.children[0].content if cell.children else "" for cell in row_token.children]
        rows.append(cells)

    return {"type": "table", "header": header, "rows": rows}


def _extract_children_text(token) -> str:
    """Extract plain text from a token's children."""
    parts: list[str] = []
    for child in token.children:
        if hasattr(child, "content"):
            parts.append(str(child.content))
        else:
            parts.append(_extract_children_text(child))
    return "".join(parts)


def _is_latex_block(text: str) -> bool:
    """Check if text looks like a LaTeX block."""
    return bool(re.search(r"\$\$[\s\S]*?\$\$", text))


def _is_mermaid_block(text: str) -> bool:
    """Check if text looks like a Mermaid diagram."""
    return "graph" in text or "sequenceDiagram" in text or "classDiagram" in text
