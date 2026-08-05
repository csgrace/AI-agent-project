"""
Comprehensive Integration Test for the RAG Pipeline.

用途:
1. 冒烟测试 (Smoke Test): 快速验证从 PDF 读取到 LLM 生成回答的整条路径是否通畅。
2. 模块核检: 细化测试文档摄入、语义搜索、环境配置三个核心组件。
3. 诊断工具: 当后端无法回答时，通过此脚本确认是数据问题 (Ingestion)、算法问题 (Search) 还是服务问题 (LLM)。
"""

import os
import sys
import pytest
from pathlib import Path

# Fix paths for module resolution
current_file_path = Path(__file__).resolve()
backend_root = current_file_path.parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from src.services.document_qa.service import get_document_qa_service
from src.services.document_qa.loader import DOCUMENTS_DIR

@pytest.fixture(scope="module")
def shared_service():
    """Provides a singleton DocumentQAService for the entire module test session."""
    return get_document_qa_service()

def test_stage1_environment_ready():
    """Step 1: Verify data folders and project layout."""
    assert DOCUMENTS_DIR.exists(), f"ERROR: DOCUMENTS_DIR not found at {DOCUMENTS_DIR}"
    print(f"\n[Environment] Documents root verified: {DOCUMENTS_DIR}")

def test_stage2_ingestion_and_chunking(shared_service):
    """Step 2: Verify PDF text extraction and chunk splitting."""
    summaries = shared_service.ingest_directory()
    
    assert len(shared_service.documents) > 0, "ERROR: No PDF documents were found or loaded."
    assert len(shared_service.chunks) > 0, "ERROR: Document chunking failed (0 chunks created)."
    
    # Check for non-empty text
    assert shared_service.chunks[0].text.strip(), "ERROR: First chunk has no text content."
    
    print(f"\n[Ingestion] Successfully processed {len(shared_service.documents)} files into {len(shared_service.chunks)} chunks.")

def test_stage3_semantic_search(shared_service):
    """Step 3: Verify vector store (FAISS) can perform semantic lookup."""
    if not shared_service.chunks:
        pytest.fail("Skipping search: Stage 2 (Ingestion) failed.")

    query = "evaluation"
    results = shared_service.search(query, k=3)
    
    assert len(results) > 0, f"ERROR: Semantic search for '{query}' returned no matches."
    assert results[0].score > 0, "ERROR: Search result score is zero or invalid."
    
    print(f"\n[Search] Query '{query}' matched best with: {results[0].source_name} (Score: {results[0].score:.4f})")

@pytest.mark.skipif(not os.getenv("MINIMAX_API_KEY"), reason="MINIMAX_API_KEY environment variable not set")
def test_stage4_llm_integration(shared_service):
    """Step 4: Verify connection to MiniMax and RAG prompt generation."""
    if not shared_service.chunks:
        pytest.fail("Skipping LLM: Stage 2 (Ingestion) failed.")

    question = "What is the grading policy of this course?"
    result = shared_service.answer_question(question)
    
    assert result.answerable is True, "ERROR: LLM indicated it could not find an answer in provided context."
    assert "AI 模型服务" not in result.answer, f"ERROR: Backend returned service error message: {result.answer}"
    assert len(result.citations) > 0, "ERROR: Answer returned without any document citations."
    
    print(f"\n[LLM] Answer generated successfully: {result.answer[:120]}...")

if __name__ == "__main__":
    # Fallback for manual execution without pytest runner
    print("Running RAG Diagnostic Suite...")
    import os
    os.system(f"pytest {__file__} -v -s")
