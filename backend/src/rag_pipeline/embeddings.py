"""Embedding model helpers — shared by RAG QA and course recommendation.

Configuration from ``LLMConfig`` singleton (embedding tier).
Cascade: 17 models across 7 tiers, ordered by capability:
  qwen3.7-text-embedding → text-embedding-v4 → qwen3-vl-embedding →
  qwen2.5-vl-embedding → text-embedding-v3 → vision models →
  text-embedding-v2/v1 → async variants → rerank (last resort).
All models share the same API key / base URL, only the model name differs.
"""

from __future__ import annotations

import os
from typing import Sequence, List, Optional

import numpy as np

from ..services.llm_config import LLMConfig

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment]


# DashScope embedding models to try in order — ranked by capability.
# Text-embedding-specialist models come first (best at the text-search task we run),
# followed by vision / multimodal models, then older text models, async variants,
# and finally rerank models as last-resort fallback.
#
# Tier 1 — best-in-class text embedding
# Tier 2 — strong vision-language models (can embed text, slightly weaker on pure text)
# Tier 3 — specialised vision embedding
# Tier 4 — older / legacy text embedding
# Tier 5 — async-only models (may fail on sync calls)
# Tier 6 — rerank models (different task — will almost certainly fail for embedding,
#          included only as absolute last resort per operational policy)

_DASHSCOPE_EMBEDDING_MODELS = [
    # ── Tier 1: best text embedding (currently only model not overdue) ──
    "qwen3.7-text-embedding",          # Qwen3.7 series — latest & strongest
    "text-embedding-v4",               # DashScope flagship text embedding (overdue)

    # ── Tier 2: vision-language (good text, also handle images) ──
    "qwen3-vl-embedding",              # Qwen3 VL — strong multimodal
    "qwen2.5-vl-embedding",            # Qwen2.5 VL — proven multimodal

    # ── Tier 3: solid text embedding ──
    "text-embedding-v3",               # DashScope v3 — reliable workhorse

    # ── Tier 4: specialised vision embedding ──
    "tongyi-embedding-vision-plus",    # best vision quality
    "tongyi-embedding-vision-plus-2026-03-06",
    "tongyi-embedding-vision-flash",   # faster vision, slightly lower quality
    "tongyi-embedding-vision-flash-2026-03-06",
    "multimodal-embedding-v1",         # earliest multimodal

    # ── Tier 5: older text embedding ──
    "text-embedding-v2",
    "text-embedding-v1",

    # ── Tier 6: async-only (may fail on sync embedding calls) ──
    "text-embedding-async-v2",
    "text-embedding-async-v1",

    # ── Tier 7: rerank models (NOT embedding models — will almost certainly
    #     fail the embeddings.create() call; included as absolute last resort) ──
    "qwen3-rerank",
    "gte-rerank-v2",
    "qwen3-vl-rerank",
]


class SentenceTransformerEmbeddings:
    """DashScope embeddings with multi-model cascade.

    Fallback chain: text-embedding-v4 → v3 → v2 → v1.
    All models share the same DashScope API key / base URL.
    Different model versions provide redundancy against quota
    exhaustion or model-specific failures.
    """

    def __init__(self) -> None:
        self._client: Optional[OpenAI] = None
        self._models: list[str] = []
        self._config_version: int = -1
        self._init_clients()

    def _init_clients(self) -> None:
        """(Re)build embedding client if LLMConfig has changed."""
        cfg = LLMConfig.get_instance()
        if cfg.get_version() == self._config_version and self._client is not None:
            return

        self._client = cfg.build_openai_client(use_fallback=False)

        # Build the model list: primary model first, then alternates
        primary_model = cfg.get_tier_model("embedding", use_fallback=False)
        fallback_model = cfg.get_tier_model("embedding", use_fallback=True) if cfg.is_fallback_available() else ""

        self._models = []
        if primary_model:
            self._models.append(primary_model)
        if fallback_model and fallback_model != primary_model:
            self._models.append(fallback_model)
        # Add remaining DashScope models not already in the list
        for m in _DASHSCOPE_EMBEDDING_MODELS:
            if m not in self._models:
                self._models.append(m)

        self._config_version = cfg.get_version()

        if self._client:
            models_str = " -> ".join(self._models[:3])
            print(f"[OK] Embedding client ready (models: {models_str})")
        else:
            print("[WARN] No embedding client - API key not configured")

    @property
    def current_model(self) -> str:
        return self._models[0] if self._models else ""

    def _remote_embed(self, texts: List[str]) -> np.ndarray:
        """Call remote embeddings API, cascading through available models.

        Truncates texts to a safe max length before sending to avoid
        token-limit errors from the embedding API.
        """
        # Safe character limit (well under the 2048-token limit of most models)
        MAX_CHARS = 1500
        texts = [
            (t[:MAX_CHARS] if len(t) > MAX_CHARS else t)
            if (t and t.strip()) else " "
            for t in texts
        ]

        batch_size = int(os.getenv("DOCUMENT_QA_EMBED_BATCH", "16"))
        out: List[np.ndarray] = []

        print(f"[BATCH] 总计: {len(texts)} 条文本, 批次大小={batch_size}")

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1

            embeddings = self._embed_batch_with_fallback(batch, batch_num)
            out.extend(embeddings)

        return np.asarray(out, dtype=np.float32)

    def _embed_batch_with_fallback(
        self, batch: List[str], batch_num: int
    ) -> List[np.ndarray]:
        """Try each available model until one succeeds."""
        last_error = None

        for model in self._models:
            try:
                print(f"  [TRY] 批次 {batch_num}: 尝试 {model} ({len(batch)} 条)...", end=" ", flush=True)
                result = self._call_embed(model, batch)
                print(f"[OK]")
                return result
            except Exception as e:
                last_error = e
                print(f"[FAIL] {model} 失败: {e}")
                continue

        raise RuntimeError(
            f"所有 DashScope 嵌入模型均失败 (已尝试 {len(self._models)} 个): {last_error}"
        )

    def _call_embed(
        self, model: str, batch: List[str]
    ) -> List[np.ndarray]:
        """Single embedding API call."""
        assert self._client is not None, "Embedding client not initialized"
        response = self._client.embeddings.create(
            model=model,
            input=batch,
            encoding_format="float",
        )
        return [
            np.asarray(item.embedding, dtype=np.float32)
            for item in response.data
        ]

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        """Encode text(s) to embedding vectors."""
        self._init_clients()
        payload = [texts] if isinstance(texts, str) else list(texts)

        if not self._client:
            raise RuntimeError(
                "无法生成嵌入向量：未配置 DashScope API Key。"
                "请在 .env 中设置 DASHSCOPE_API_KEY。"
            )

        print(f"[EMBED] 使用嵌入模型 ({self.current_model}) 处理 {len(payload)} 条文本...")
        emb = self._remote_embed(payload)
        # L2 normalize
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        emb = emb / norms
        return emb
