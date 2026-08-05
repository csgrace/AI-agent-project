"""Document loading utilities for document QA (PDF + TXT)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
import json

import fitz  # PyMuPDF

from .models import DocumentRecord

BASE_DIR = Path(__file__).resolve().parents[2] # backend/src/rag_pipeline -> backend
DATA_DIR = BASE_DIR / "data"
# Default ingestion scope: index the whole `data` directory so PDFs/TXTs
# placed directly under `data/` (or in any subfolder) are included.
DOCUMENTS_DIR = DATA_DIR


def _suppress_mupdf_warnings() -> None:
    """Suppress noisy MuPDF warnings from malformed PDF metadata/profile blocks."""

    tools = getattr(fitz, "TOOLS", None)
    if tools is None:
        return

    for method_name in ("mupdf_display_errors", "mupdf_display_warnings"):
        method = getattr(tools, method_name, None)
        if callable(method):
            try:
                method(False)
            except Exception:
                # Best-effort suppression; keep ingestion resilient.
                pass


_suppress_mupdf_warnings()


def _candidate_folders(folder: str | Path | None = None) -> list[Path]:
    if folder is not None:
        return [Path(folder)]

    # Default ingestion scope is restricted to sustech.online only.
    return [DOCUMENTS_DIR]


def _iter_files(folder: Path, *, suffixes: set[str]) -> Iterable[Path]:
    if not folder.exists() or not folder.is_dir():
        return []

    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _relative_source_name(file_path: Path, base_dir: Path) -> str:
    if file_path.is_relative_to(base_dir):
        return str(file_path.relative_to(base_dir)).replace("\\", "/")
    return file_path.name


def _load_pdf_document(file_path: Path, base_dir: Path) -> DocumentRecord | None:
    try:
        with fitz.open(str(file_path)) as pdf:
            text_parts = [page.get_text("text") for page in pdf]
            text = "\n".join(part.strip() for part in text_parts if part.strip())
            return DocumentRecord(
                source_name=_relative_source_name(file_path, base_dir),
                source_path=str(file_path),
                text=text,
                page_count=len(pdf),
            )
    except Exception:
        return None


def _load_text_document(file_path: Path, base_dir: Path) -> DocumentRecord | None:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        return DocumentRecord(
            source_name=_relative_source_name(file_path, base_dir),
            source_path=str(file_path),
            text=text,
            page_count=1,
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
        )
    except Exception:
        return None


def load_pdfs(folder: str | Path | None = None) -> list[DocumentRecord]:
    """Extract text from PDF files under the selected folder."""

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
    """Extract text from PDF and TXT files under the selected folder."""

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
