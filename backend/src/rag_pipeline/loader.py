"""Document loading utilities for document QA (PDF + TXT).

Structure-aware PDF loading: uses fitz dict mode to extract text blocks
with font sizes, then infers heading hierarchy from font size deltas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
import json

import fitz  # PyMuPDF

from .models import DocumentRecord

BASE_DIR = Path(__file__).resolve().parents[2] # backend/src/rag_pipeline -> backend
DATA_DIR = BASE_DIR / "data"
DOCUMENTS_DIR = DATA_DIR

# ── Font-size thresholds for heading detection ─────────────────────
# Typical campus PDFs use 14pt+ for titles, 12-13pt for H2, 10.5-11pt for H3
_TITLE_FONT_THRESHOLD = 14.0   # ≥ this → document title (H1)
_H2_FONT_THRESHOLD = 12.0      # ≥ this → section heading (H2)
_H3_FONT_THRESHOLD = 10.5      # ≥ this → sub-section (H3)
_BOLD_WEIGHT = 500             # font weight threshold for emphasis

# Characters below this count are ignored as headings (page numbers, etc.)
_MIN_HEADING_CHARS = 3


def _suppress_mupdf_warnings() -> None:
    tools = getattr(fitz, "TOOLS", None)
    if tools is None:
        return
    for method_name in ("mupdf_display_errors", "mupdf_display_warnings"):
        method = getattr(tools, method_name, None)
        if callable(method):
            try:
                method(False)
            except Exception:
                pass

_suppress_mupdf_warnings()


def _candidate_folders(folder: str | Path | None = None) -> list[Path]:
    if folder is not None:
        return [Path(folder)]
    return [DOCUMENTS_DIR]


def _iter_files(folder: Path, *, suffixes: set[str]) -> Iterable[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        path for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _relative_source_name(file_path: Path, base_dir: Path) -> str:
    if file_path.is_relative_to(base_dir):
        return str(file_path.relative_to(base_dir)).replace("\\", "/")
    return file_path.name


# ── Structure-aware PDF extraction ─────────────────────────────────

def _extract_pdf_structure(file_path: Path) -> tuple[str, str, list[dict]]:
    """Extract text + heading structure from a PDF using font-size analysis.

    Returns (full_text, doc_title, sections).
    sections = [{level, heading, page, start_char}]
    """
    sections: list[dict] = []
    all_lines: list[str] = []
    doc_title = ""

    try:
        with fitz.open(str(file_path)) as pdf:
            # Try metadata first
            meta = pdf.metadata or {}
            doc_title = (meta.get("title") or "").strip()

            char_offset = 0
            for page_idx, page in enumerate(pdf):
                blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
                for block in blocks:
                    if block.get("type") != 0:  # skip images
                        continue
                    for line in block.get("lines", []):
                        line_text = ""
                        line_fonts: list[float] = []
                        line_weights: list[float] = []

                        for span in line.get("spans", []):
                            line_text += span["text"]
                            line_fonts.append(float(span.get("size", 10)))
                            line_weights.append(float(getattr(span, "flags", 0)))

                        text = line_text.strip()
                        if not text:
                            continue

                        avg_font = sum(line_fonts) / max(len(line_fonts), 1)
                        is_bold = any(w >= _BOLD_WEIGHT for w in line_weights)

                        # Detect heading level from font size
                        level = 0
                        heading_text = text
                        if avg_font >= _TITLE_FONT_THRESHOLD and len(text) >= _MIN_HEADING_CHARS:
                            level = 1
                            if not doc_title:
                                doc_title = text
                        elif avg_font >= _H2_FONT_THRESHOLD and len(text) >= _MIN_HEADING_CHARS:
                            level = 2
                        elif avg_font >= _H3_FONT_THRESHOLD and len(text) >= _MIN_HEADING_CHARS:
                            level = 3
                        elif is_bold and avg_font >= _H3_FONT_THRESHOLD and len(text) >= _MIN_HEADING_CHARS:
                            level = 3

                        if level > 0:
                            sections.append({
                                "level": level,
                                "heading": heading_text,
                                "page": page_idx + 1,
                                "start_char": char_offset,
                            })

                        all_lines.append(text)
                        char_offset += len(text) + 1  # +1 for newline

    except Exception:
        return "", "", []

    full_text = "\n".join(all_lines)
    if not doc_title:
        doc_title = file_path.stem

    return full_text, doc_title, sections


def _load_pdf_document(file_path: Path, base_dir: Path) -> DocumentRecord | None:
    try:
        text, title, sections = _extract_pdf_structure(file_path)
        if not text:
            return None
        return DocumentRecord(
            source_name=_relative_source_name(file_path, base_dir),
            source_path=str(file_path),
            text=text,
            page_count=len(sections) or 1,  # will be overridden in caller
            title=title,
            sections=sections,
        )
    except Exception:
        # Fallback: plain text extraction
        try:
            with fitz.open(str(file_path)) as pdf:
                text_parts = [page.get_text("text") for page in pdf]
                text = "\n".join(part.strip() for part in text_parts if part.strip())
                return DocumentRecord(
                    source_name=_relative_source_name(file_path, base_dir),
                    source_path=str(file_path),
                    text=text,
                    page_count=len(pdf),
                    title=pdf.metadata.get("title", "") or file_path.stem,
                )
        except Exception:
            return None


def _load_text_document(file_path: Path, base_dir: Path) -> DocumentRecord | None:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        # Detect markdown headings for structure
        sections = []
        for i, line in enumerate(text.split("\n")):
            line = line.strip()
            if line.startswith("#"):
                depth = len(line) - len(line.lstrip("#"))
                heading = line.lstrip("#").strip()
                if depth <= 3 and len(heading) >= _MIN_HEADING_CHARS:
                    sections.append({
                        "level": depth,
                        "heading": heading,
                        "page": i + 1,
                        "start_char": text.find(line),
                    })
        return DocumentRecord(
            source_name=_relative_source_name(file_path, base_dir),
            source_path=str(file_path),
            text=text,
            page_count=1,
            title=file_path.stem,
            sections=sections,
        )
    except Exception:
        return None


def _load_json_document(file_path: Path, base_dir: Path) -> DocumentRecord | None:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return DocumentRecord(
            source_name=_relative_source_name(file_path, base_dir),
            source_path=str(file_path),
            text=text,
            page_count=1,
            title=file_path.stem,
        )
    except Exception:
        return None


def load_pdfs(folder: str | Path | None = None) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []
    for candidate in _candidate_folders(folder):
        pdf_files = list(_iter_files(candidate, suffixes={".pdf"}))
        if not pdf_files:
            continue
        for file_path in pdf_files:
            record = _load_pdf_document(file_path, candidate)
            if record is not None:
                documents.append(record)
        if documents:
            break
    return documents


def load_documents(folder: str | Path | None = None) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []
    for candidate in _candidate_folders(folder):
        files = list(_iter_files(candidate, suffixes={".pdf", ".txt", ".json", ".md", ".html", ".htm"}))
        if not files:
            continue
        for file_path in files:
            suffix = file_path.suffix.lower()
            if suffix == ".pdf":
                record = _load_pdf_document(file_path, candidate)
            elif suffix in {".txt", ".md", ".html", ".htm"}:
                record = _load_text_document(file_path, candidate)
            elif suffix == ".json":
                record = _load_json_document(file_path, candidate)
            else:
                record = None
            if record is not None:
                documents.append(record)
        if documents:
            break
    return documents
