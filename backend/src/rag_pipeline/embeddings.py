"""Embedding model helpers for document QA.

All remote API configuration (api_key, base_url, model) is sourced from the
global ``LLMConfig`` singleton.  Falls back to a local hash-based embedder
when no remote client is available.
"""

from __future__ import annotations

import hashlib
import os
from typing import Sequence, List
import numpy as np

from ..services.llm_config import LLMConfig

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment]


class HashEmbeddings:
    """Lightweight local hash-based embedder (no API key required)."""

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        payload = [texts] if isinstance(texts, str) else list(texts)
        vectors: list[np.ndarray] = []

        for text in payload:
            vector = np.zeros(self.dimension, dtype=np.float32)
            for token in str(text).lower().split():
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimension
                vector[index] += 1.0

            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector /= norm
            vectors.append(vector)

        return np.asarray(vectors, dtype=np.float32)


class SentenceTransformerEmbeddings:
    """Remote-API-based embeddings with a local hash fallback.

    Configuration is read from the global ``LLMConfig`` singleton
    (``embedding`` tier).  Supports a two-level cascade:
    primary provider -> fallback provider -> local ``HashEmbeddings``.
    """

    def __init__(self) -> None:
        self._client: OpenAI | None = None
        self._fallback_client: OpenAI | None = None
        self._model: str = ""
        self._fallback_model: str = ""
        self._config_version: int = -1
        self._hash_fallback = HashEmbeddings()

        self._init_clients()

    def _init_clients(self) -> None:
        """(Re)build embedding clients if LLMConfig has changed."""
        cfg = LLMConfig.get_instance()
        if cfg.get_version() == self._config_version and self._client is not None:
            return  # already up-to-date

        # Primary
        self._client = cfg.build_openai_client(use_fallback=False)
        self._model = cfg.get_tier_model("embedding", use_fallback=False)

        # Fallback (different provider, e.g. OpenAI if primary is DashScope)
        self._fallback_client = None
        self._fallback_model = ""
        if cfg.is_fallback_available():
            self._fallback_client = cfg.build_openai_client(use_fallback=True)
            self._fallback_model = cfg.get_tier_model("embedding", use_fallback=True)

        self._config_version = cfg.get_version()

        if self._client:
            print(f"✅ Embedding primary client initialized (model: {self._model})")
        if self._fallback_client:
            print(f"✅ Embedding fallback client available (model: {self._fallback_model})")
        if not self._client and not self._fallback_client:
            print("⚠️ No remote embedding client — using local hash fallback")

    def _remote_embed(self, texts: List[str]) -> np.ndarray:
        """Call remote embeddings API, cascading through primary → fallback."""
        texts = [t if t and t.strip() else " " for t in texts]

        out: List[np.ndarray] = []
        batch_size = int(os.getenv("DOCUMENT_QA_EMBED_BATCH", "16"))
        total_batches = (len(texts) + batch_size - 1) // batch_size

        print(f"📊 总计: {len(texts)} 条文本, {total_batches} 个批次, 批次大小={batch_size}")

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            print(f"  🔄 批次 {batch_num}/{total_batches} ({len(batch)} 条)...", end=" ", flush=True)

            embeddings = self._embed_batch(batch)
            out.extend(embeddings)
            print(f"✅ (已完成 {len(out)}/{len(texts)} 条)")

        return np.asarray(out, dtype=np.float32)

    def _embed_batch(self, batch: List[str]) -> List[np.ndarray]:
        """Try primary client first, then fallback client."""
        # Attempt 1: primary client
        if self._client:
            try:
                return self._call_embed(self._client, self._model, batch)
            except Exception as e:
                print(f"❌ Primary embedding failed: {e}")

        # Attempt 2: fallback client
        if self._fallback_client:
            try:
                print(f"  ↪ 切换到备用 embedding 服务 ({self._fallback_model})...")
                return self._call_embed(self._fallback_client, self._fallback_model, batch)
            except Exception as e:
                print(f"❌ Fallback embedding also failed: {e}")

        raise RuntimeError("No remote embedding client available")

    @staticmethod
    def _call_embed(client: OpenAI, model: str, batch: List[str]) -> List[np.ndarray]:
        """Single embedding API call."""
        response = client.embeddings.create(
            model=model,
            input=batch,
            encoding_format="float",
        )
        return [np.asarray(item.embedding, dtype=np.float32) for item in response.data]
        
        print(f"🎉 全部 {len(texts)} 条文本嵌入完成！")
        return np.vstack(out)
    

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        # Re-check config in case API key was set at runtime.
        self._init_clients()

        payload = [texts] if isinstance(texts, str) else list(texts)

        # 使用远程 embedding API
        if self._client:
            try:
                print(f"🌐 使用嵌入模型 ({self._model}) 处理 {len(payload)} 条文本...")
                emb = self._remote_embed(payload)
                norms = np.linalg.norm(emb, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                emb = emb / norms
                return emb
            except Exception as e:
                print(f"⚠️ Remote embedding failed: {e}")

        # 回退到 hash
        print(f"⚠️ Using HashEmbeddings fallback for {len(payload)} texts")
        return self._hash_fallback.encode(payload)