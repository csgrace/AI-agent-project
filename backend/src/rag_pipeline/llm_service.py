import json
import re
from dataclasses import dataclass
from typing import Any, Generator, Optional, Sequence

from .models import SearchResult

from openai import OpenAI

from ..services.llm_config import LLMConfig
from .prompt import (
    build_answer_system_prompt,
    build_answerability_prompt,
    build_clarification_prompt,
    build_query_routing_prompt,
    build_rag_prompt,
)


@dataclass(slots=True)
class QueryRoutingDecision:
    intent: str
    confidence: float
    reason: str


@dataclass(slots=True)
class AnswerabilityDecision:
    answerable: bool
    confidence: float
    reason: str


class LLMService:
    """Lightweight wrapper around the OpenAI-compatible chat endpoint.

    All configuration (api_key, base_url, model names) is sourced from the
    global ``LLMConfig`` singleton.  A two-level fallback is supported:
    primary provider → fallback provider (e.g. DashScope → OpenAI).
    """

    def __init__(self) -> None:
        # Lazy-init: clients are built on first use so that runtime
        # LLMConfig changes (e.g. API key set via web UI) are picked up.
        self._client: Optional[OpenAI] = None
        self._model_name: Optional[str] = None
        self._fallback_client: Optional[OpenAI] = None
        self._fallback_model: Optional[str] = None
        self._lightweight_model_name: Optional[str] = None
        self._lightweight_fallback_model: Optional[str] = None
        self._config_version: int = -1

        self._ensure_clients()

    # ── Lazy client resolution ────────────────────────────────────

    def _ensure_clients(self) -> None:
        """(Re)build OpenAI clients if LLMConfig has changed since last build."""
        cfg = LLMConfig.get_instance()
        if cfg.get_version() == self._config_version and self._client is not None:
            return  # already up-to-date

        self._client = cfg.build_openai_client(use_fallback=False)
        self._model_name = cfg.get_tier_model("smart", use_fallback=False)

        self._fallback_client = None
        self._fallback_model = None
        if cfg.is_fallback_available():
            self._fallback_client = cfg.build_openai_client(use_fallback=True)
            self._fallback_model = cfg.get_tier_model("smart", use_fallback=True)

        # Lightweight tier (for routing, keyword extraction, etc.)
        self._lightweight_model_name = cfg.get_tier_model("lightweight", use_fallback=False)
        self._lightweight_fallback_model = None
        if cfg.is_fallback_available():
            self._lightweight_fallback_model = cfg.get_tier_model("lightweight", use_fallback=True)

        self._config_version = cfg.get_version()

        if self._client:
            print(f"LLMService: Main client initialized (smart={self._model_name}, lightweight={self._lightweight_model_name})")
        if self._fallback_client:
            print(f"LLMService: Fallback client available ({self._fallback_model})")
        if not self._client and not self._fallback_client:
            print("LLMService: No client available (no API keys configured)")

    @property
    def client(self) -> Optional[OpenAI]:
        self._ensure_clients()
        return self._client

    @property
    def model_name(self) -> Optional[str]:
        self._ensure_clients()
        return self._model_name

    @property
    def fallback_client(self) -> Optional[OpenAI]:
        self._ensure_clients()
        return self._fallback_client

    @property
    def fallback_model(self) -> Optional[str]:
        self._ensure_clients()
        return self._fallback_model

    @property
    def lightweight_model_name(self) -> Optional[str]:
        self._ensure_clients()
        return self._lightweight_model_name

    # ── Core chat completion with provider-level fallback ──────────

    def _chat_completion(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        label: str,
        system_prompt: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ) -> Optional[str]:
        """Send a chat prompt, returning the assistant reply.

        Cascade: primary model → fallback model → other DashScope models
        → fallback provider (e.g. OpenAI).  Multiple models are tried on
        the same API key / base URL; only the model name changes.
        """
        if not self.client and not self.fallback_client:
            print("LLMService: No client available (no API keys configured)")
            return None

        from ..services.llm_config import CHAT_MODEL_CASCADE

        # Build the ordered list of models to try
        primary = model or self.model_name
        fb = fallback_model or self.fallback_model or ""
        tried: set[str] = set()
        models_to_try: list[str] = []

        if primary:
            models_to_try.append(primary)
            tried.add(primary)
        if fb and fb not in tried:
            models_to_try.append(fb)
            tried.add(fb)
        for m in CHAT_MODEL_CASCADE:
            if m not in tried:
                models_to_try.append(m)
                tried.add(m)

        print(f"Prompt length: {len(prompt)} chars [{label}], cascade: {' → '.join(models_to_try[:4])}")

        # ── Attempt 1..N: primary client, multiple models ──────────
        if self.client:
            for m in models_to_try:
                phase = "primary" if m == primary else f"cascade/{m}"
                result = self._try_client(
                    self.client, m,
                    prompt=prompt, temperature=temperature,
                    max_tokens=max_tokens, label=label,
                    system_prompt=system_prompt, phase=phase,
                )
                if result is not None:
                    return result

        # ── Last resort: fallback provider ─────────────────────────
        if self.fallback_client:
            result = self._try_client(
                self.fallback_client, fb or self.fallback_model,
                prompt=prompt, temperature=temperature,
                max_tokens=max_tokens, label=label,
                system_prompt=system_prompt, phase="fallback",
            )
            if result is not None:
                return result

        print(f"LLMService: All LLM models + fallback failed ({label})")
        return None

    @staticmethod
    def _try_client(
        client,
        model: str,
        *,
        prompt: str,
        temperature: float,
        max_tokens: int,
        label: str,
        system_prompt: str | None,
        phase: str,
    ) -> Optional[str]:
        """Make a single chat-completion call; return the answer or None."""
        try:
            print(f"LLMService: Calling {phase} LLM with model '{model}' ({label})...")
            response = client.chat.completions.create(
                model=model,
                messages=(
                    ([{"role": "system", "content": system_prompt}] if system_prompt else [])
                    + [{"role": "user", "content": prompt}]
                ),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            answer = response.choices[0].message.content.strip()
            print(f"LLMService: {phase} LLM succeeded ({label}), answer length: {len(answer)}")
            return answer
        except Exception as e:
            print(f"LLMService: {phase} LLM failed ({label}): {type(e).__name__}: {e}")
            if hasattr(e, "response") and e.response:
                print(f"    Response body: {e.response.text}")
            return None

    def _chat_completion_stream(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        label: str,
        system_prompt: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ) -> Generator[str, None, None]:
        """Stream LLM response chunks with model-level cascade fallback.

        Cascade: primary model → tier fallback → CHAT_MODEL_CASCADE models
        → fallback provider (e.g. OpenAI).  Same logic as ``_chat_completion``.
        """
        if not self.client and not self.fallback_client:
            print("LLMService: No client available for streaming (no API keys configured)")
            return

        from ..services.llm_config import CHAT_MODEL_CASCADE

        # Build the ordered list of models to try (mirrors _chat_completion)
        primary = model or self.model_name
        fb = fallback_model or self.fallback_model or ""
        tried: set[str] = set()
        models_to_try: list[str] = []

        if primary:
            models_to_try.append(primary)
            tried.add(primary)
        if fb and fb not in tried:
            models_to_try.append(fb)
            tried.add(fb)
        for m in CHAT_MODEL_CASCADE:
            if m not in tried:
                models_to_try.append(m)
                tried.add(m)

        print(f"Prompt length: {len(prompt)} chars [stream/{label}], cascade: {' → '.join(models_to_try[:4])}")

        # ── Attempt 1..N: primary client, multiple models ──────────
        if self.client:
            for m in models_to_try:
                phase = "primary" if m == primary else f"cascade/{m}"
                try:
                    print(f"LLMService: Streaming from {phase} LLM '{m}' ({label})...")
                    stream = self.client.chat.completions.create(
                        model=m,
                        messages=(
                            ([{"role": "system", "content": system_prompt}] if system_prompt else [])
                            + [{"role": "user", "content": prompt}]
                        ),
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                    )
                    token_count = 0
                    for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            token_count += 1
                            yield delta.content
                    print(f"LLMService: {phase} LLM stream finished ({label}), {token_count} tokens")
                    return  # success — exit cascade
                except Exception as e:
                    print(f"LLMService: {phase} LLM stream failed ({label}): {type(e).__name__}: {e}")
                    # Continue to next model in cascade

        # ── Last resort: fallback provider ─────────────────────────
        if self.fallback_client:
            try:
                print(f"LLMService: Streaming from fallback LLM '{fb or self.fallback_model}' ({label})...")
                stream = self.fallback_client.chat.completions.create(
                    model=fb or self.fallback_model,
                    messages=(
                        ([{"role": "system", "content": system_prompt}] if system_prompt else [])
                        + [{"role": "user", "content": prompt}]
                    ),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                print(f"LLMService: Fallback LLM stream finished ({label})")
            except Exception as e:
                print(f"LLMService: Fallback LLM stream failed ({label}): {type(e).__name__}: {e}")

        print(f"LLMService: All streaming models exhausted ({label})")

    def _compact_answer(self, answer: str, *, query_kind: str | None = None) -> str:
        text = answer.strip()
        if not text:
            return text

        segments = [segment.strip() for segment in re.split(r"[。！？!?\n]+", text) if segment.strip()]
        if not segments:
            return text

        max_segments = 2 if (query_kind or "").strip().lower() == "chat" else 3
        compacted: list[str] = []
        seen: set[str] = set()

        for segment in segments:
            normalized = re.sub(r"\s+", "", segment.lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            compacted.append(segment)
            if len(compacted) >= max_segments:
                break

        if not compacted:
            return text

        return "。".join(compacted) + "。"

    def _looks_repetitive(self, answer: str) -> bool:
        text = answer.strip()
        if not text:
            return True

        normalized = re.sub(r"\s+", "", text)
        if len(normalized) > 120:
            return True

        segments = [segment.strip() for segment in re.split(r"[。！？!?\n]+", text) if segment.strip()]
        if len(segments) <= 1:
            return False

        unique_segments = {re.sub(r"\s+", "", segment.lower()) for segment in segments}
        if len(unique_segments) < len(segments):
            return True

        if any(segment.startswith(("1.", "2.", "3.", "4.")) for segment in segments):
            return True

        return False

    def classify_query_kind(self, question: str, *, max_score: float | None = None) -> QueryRoutingDecision:
        prompt = build_query_routing_prompt(question, max_score=max_score)
        response = self._chat_completion(
            prompt,
            temperature=0.0,
            max_tokens=256,
            label="routing",
            model=self.lightweight_model_name,
            fallback_model=self._lightweight_fallback_model,
            system_prompt=(
                "You are a strict routing classifier for a campus QA system. "
                "Do not answer the user's question. "
                "Only output the requested routing fields."
            ),
        )

        if not response:
            return QueryRoutingDecision(intent="unknown", confidence=0.0, reason="模型不可用，无法完成路由判断。")

        try:
            payload = json.loads(response)
            intent = str(payload.get("intent", "unknown")).strip().lower()
            confidence = float(payload.get("confidence", 0.0))
            reason = str(payload.get("reason", "")).strip()
            if intent not in {"chat", "document", "unknown"}:
                intent = "unknown"
            confidence = min(max(confidence, 0.0), 1.0)
            if not reason:
                reason = "模型未返回有效理由。"
            return QueryRoutingDecision(intent=intent, confidence=confidence, reason=reason)
        except Exception as e:
            text = response.strip()
            intent_match = re.search(r"(?im)^intent\s*[:=]\s*(chat|document|unknown)\s*$", text)
            confidence_match = re.search(r"(?im)^confidence\s*[:=]\s*([0-9]*\.?[0-9]+)\s*$", text)
            reason_match = re.search(r"(?im)^reason\s*[:=]\s*(.+)$", text)

            if intent_match or confidence_match or reason_match:
                intent = intent_match.group(1).lower() if intent_match else "unknown"
                confidence = float(confidence_match.group(1)) if confidence_match else 0.0
                reason = reason_match.group(1).strip() if reason_match else "模型返回了非结构化路由结果。"
                return QueryRoutingDecision(intent=intent, confidence=min(max(confidence, 0.0), 1.0), reason=reason)

            intent_match = re.search(r"\b(chat|document|unknown)\b", text, re.IGNORECASE)
            confidence_match = re.search(r"\b([0-9]*\.?[0-9]+)\b", text)
            if intent_match:
                intent = intent_match.group(1).lower()
                confidence = float(confidence_match.group(1)) if confidence_match else 0.0
                reason = text if len(text) <= 240 else text[:240]
                return QueryRoutingDecision(intent=intent, confidence=min(max(confidence, 0.0), 1.0), reason=reason)

            print(f"LLMService: Failed to parse routing response: {type(e).__name__}: {e}")
            return QueryRoutingDecision(intent="unknown", confidence=0.0, reason="路由结果解析失败。")

    def classify_intent(self, question: str, *, max_score: float | None = None) -> QueryRoutingDecision:
        """Backward-compatible alias for older callers."""
        return self.classify_query_kind(question, max_score=max_score)

    def assess_answerability(
        self,
        question: str,
        citations: Sequence[SearchResult],
    ) -> AnswerabilityDecision:
        prompt = build_answerability_prompt(question, citations)
        response = self._chat_completion(
            prompt,
            temperature=0.0,
            max_tokens=220,
            label="answerability",
            model=self.lightweight_model_name,
            fallback_model=self._lightweight_fallback_model,
            system_prompt=(
                "You are a strict evidence judge. "
                "Only judge whether the evidence is sufficient. "
                "Do not answer the question itself."
            ),
        )

        if not response:
            return AnswerabilityDecision(answerable=False, confidence=0.0, reason="模型不可用，无法确认证据是否足够。")

        text = response.strip()
        answerable_match = re.search(r"(?im)^answerable\s*[:=]\s*(true|false)\s*$", text)
        confidence_match = re.search(r"(?im)^confidence\s*[:=]\s*([0-9]*\.?[0-9]+)\s*$", text)
        reason_match = re.search(r"(?im)^reason\s*[:=]\s*(.+)$", text)

        if answerable_match or confidence_match or reason_match:
            answerable = answerable_match.group(1).lower() == "true" if answerable_match else False
            confidence = float(confidence_match.group(1)) if confidence_match else 0.0
            reason = reason_match.group(1).strip() if reason_match else "证据判断结果为结构化输出。"
            return AnswerabilityDecision(answerable=answerable, confidence=min(max(confidence, 0.0), 1.0), reason=reason)

        answerable_match = re.search(r"\b(true|false)\b", text, re.IGNORECASE)
        confidence_match = re.search(r"\b([0-9]*\.?[0-9]+)\b", text)
        if answerable_match:
            answerable = answerable_match.group(1).lower() == "true"
            confidence = float(confidence_match.group(1)) if confidence_match else 0.0
            return AnswerabilityDecision(answerable=answerable, confidence=min(max(confidence, 0.0), 1.0), reason=text[:240])

        return AnswerabilityDecision(answerable=False, confidence=0.0, reason="证据判断结果无法解析。")

    def generate_clarification(
        self,
        question: str,
        citations: Sequence[SearchResult],
        *,
        reason: str,
    ) -> Optional[str]:
        prompt = build_clarification_prompt(question, citations, reason)
        response = self._chat_completion(
            prompt,
            temperature=0.1,
            max_tokens=256,
            label="clarification",
            model=self.lightweight_model_name,
            fallback_model=self._lightweight_fallback_model,
            system_prompt=(
                "You are SUSTech Campus Assistant. "
                "Write a concise clarification reply only. "
                "Do not answer the original question directly."
            ),
        )
        if not response:
            return None
        return self._compact_answer(response, query_kind="chat")

def generate_answer(
        self,
        question: str,
        citations: Sequence[SearchResult],
        *,
        max_score: float | None = None,
        query_kind: str | None = None,
        mode: str | None = None,
        memory_context: str = "",
    ) -> Optional[str]:
        """生成回答，支持主备切换

        Args:
            memory_context: 对话历史上下文，注入到 prompt 中支持多轮对话
        """
        if query_kind is None and mode is not None:
            if mode == "chat":
                query_kind = "chat"
            elif mode == "grounded":
                query_kind = "document"
            elif mode == "clarify":
                query_kind = "unknown"

        prompt = build_rag_prompt(
            question,
            citations,
            max_score=max_score,
            query_kind=query_kind,
            memory_context=memory_context,
        )

        resolved_query_kind = (query_kind or mode or "unknown").strip().lower()
        if resolved_query_kind == "document":
            temperature = 0.1
        elif resolved_query_kind == "chat":
            temperature = 0.2
        else:
            temperature = 0.1

        max_tokens = 768 if resolved_query_kind == "document" else 1024

        answer = self._chat_completion(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            label="answer",
            system_prompt=build_answer_system_prompt(resolved_query_kind),
        )

        if not answer:
            return None

        compacted = self._compact_answer(answer, query_kind=resolved_query_kind)
        if resolved_query_kind == "document" and self._looks_repetitive(compacted):
            return self._compact_answer(compacted, query_kind="document")[:240]

        return compacted
    
    def test_connection(self) -> dict:
        """测试 LLM 连接是否正常"""
        result = {
            "main_client_available": self.client is not None,
            "fallback_client_available": self.fallback_client is not None,
            "main_model": self.model_name if self.client else None,
            "fallback_model": self.fallback_model if self.fallback_client else None,
        }
        
        # 简单测试调用
        test_prompt = "回复'OK'即可，不要有其他内容。"
        
        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": test_prompt}],
                    temperature=0.1,
                    max_tokens=10,
                )
                result["main_test"] = "success"
                result["main_test_response"] = response.choices[0].message.content.strip()
            except Exception as e:
                result["main_test"] = f"failed: {e}"
        
        if self.fallback_client and not result.get("main_test") == "success":
            try:
                response = self.fallback_client.chat.completions.create(
                    model=self.fallback_model,
                    messages=[{"role": "user", "content": test_prompt}],
                    temperature=0.1,
                    max_tokens=10,
                )
                result["fallback_test"] = "success"
                result["fallback_test_response"] = response.choices[0].message.content.strip()
            except Exception as e:
                result["fallback_test"] = f"failed: {e}"
        
        return result

    def extract_keywords(self, question: str, texts: list[str], limit: int = 3) -> list[str] | None:
        """Use the LLM to extract up to `limit` keywords or short phrases from `texts` that are most relevant to `question`.

        Returns a list of keywords (strings) or None on failure.
        """
        if not texts:
            return []

        sample = "\n---\n".join(texts[:3])
        prompt = (
            f"给定用户问题：\n{question}\n\n" +
            f"以及来自同一来源的文本片段（用\n---\n分隔）：\n{sample}\n\n" +
            f"请提取不超过 {limit} 个最能帮助回答该问题的关键词或短语，返回 JSON 数组，例如：[\"关键词1\", \"关键词2\"]。"
        )

        response = self._chat_completion(
            prompt,
            temperature=0.0,
            max_tokens=120,
            label="extract_keywords",
            model=self.lightweight_model_name,
            fallback_model=self._lightweight_fallback_model,
        )

        if not response:
            return None

        # try parse JSON
        try:
            import json as _json

            parsed = _json.loads(response)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed][:limit]
        except Exception:
            pass

        # fallback: split by commas/newlines
        parts = [p.strip() for p in re.split(r"[,\n;]+", response) if p.strip()]
        return parts[:limit]

    def extract_keywords_batch(
        self, question: str, grouped_texts: dict[str, list[str]], limit: int = 5
    ) -> dict[str, list[str]]:
        """Extract keywords from multiple sources in a single LLM call.

        Args:
            question: The user's question.
            grouped_texts: Mapping of source_name → list of text snippets.
            limit: Max keywords per source.

        Returns:
            Mapping of source_name → list of keywords (empty dict on failure).
        """
        if not grouped_texts:
            return {}

        # Build a single prompt listing all sources
        parts: list[str] = [f"用户问题：{question}\n"]
        parts.append("以下是从不同来源检索到的文档片段，请为每个来源提取关键词：\n")
        for source_name, texts in grouped_texts.items():
            sample = "\n---\n".join(texts[:3])
            parts.append(f"[来源: {source_name}]\n{sample}\n")

        parts.append(
            f"请为以上每个来源分别提取不超过 {limit} 个最能帮助回答该问题的关键词或短语。"
            f'返回一个 JSON 对象，格式为: {{"来源1": ["关键词1", "关键词2"], "来源2": ["关键词3"]}}。'
        )

        prompt = "\n".join(parts)

        response = self._chat_completion(
            prompt,
            temperature=0.0,
            max_tokens=256,
            label="extract_keywords_batch",
            model=self.lightweight_model_name,
            fallback_model=self._lightweight_fallback_model,
        )

        if not response:
            return {}

        try:
            import json as _json

            parsed = _json.loads(response)
            if isinstance(parsed, dict):
                result: dict[str, list[str]] = {}
                for key, val in parsed.items():
                    if isinstance(val, list):
                        result[str(key)] = [str(x).strip() for x in val][:limit]
                return result
        except Exception:
            pass

        return {}