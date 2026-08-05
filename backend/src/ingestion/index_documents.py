"""Build the local document QA index with enhanced metadata tracking."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import os

import faiss

# Fix path to ensure src is importable
current_dir = Path(__file__).resolve().parent
repo_root = current_dir.parents[1]  # backend/src/ingestion -> backend/src
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root.parent))  # Add backend to sys.path
    sys.path.insert(0, str(repo_root))         # Add backend/src to sys.path

from src.rag_pipeline.loader import load_documents, DOCUMENTS_DIR
from src.rag_pipeline.chunker import chunk_documents
from src.rag_pipeline.vector_store import VectorStore

os.environ["DASHSCOPE_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

from src.rag_pipeline.models import coerce_chunk

BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BASE_DIR / "storage"
CHUNKS_PATH = STORAGE_DIR / "chunks.json"
FAISS_PATH = STORAGE_DIR / "index.faiss"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index documents (PDF + TXT) for document Q&A")
    parser.add_argument(
        "--folder",
        default=str(DOCUMENTS_DIR),
        help="Folder containing PDF/TXT documents to index",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing even if cache exists",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    folder = Path(args.folder)

    print("Starting Production Re-indexing...")
    print(f"Source: {folder}")

    # Load documents
    documents = load_documents(str(folder))
    print(f"Loaded {len(documents)} documents")
    
    # Chunk documents
    chunks = chunk_documents(documents)
    print(f"Created {len(chunks)} chunks")
    
    # Build vector store
    vector_store = VectorStore()
    vector_store.build(chunks)
    print("Built vector index")
    
    # Save to storage
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save Chunks as JSON
    chunks_data = [c.to_dict() for c in chunks]
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)
        
    # Save FAISS index
    if vector_store.index is not None:
        faiss.write_index(vector_store.index, str(FAISS_PATH))
        
    print(f"Index saved to {STORAGE_DIR}")
    print("\nStorage updated in backend/storage/ (chunks.json & index.faiss)")


if __name__ == "__main__":
    main()
