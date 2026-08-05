"""Centralized LLM configuration manager.

LLMConfig is a singleton that provides a single source of truth for all
LLM-related configuration across the application: API keys, base URLs,
provider fallback, and per-tier model settings.

Architecture
------------
- One shared provider config (api_key + base_url)
- Optional fallback provider (different base URL, e.g. OpenAI when DashScope fails)
- Four tiers: lightweight, smart, embedding, vision
- Each tier has a model name + fallback model name + temperature
- No model rotation (removed — was for free-tier quota management, irrelevant with paid keys)

Usage
-----
    config = LLMConfig.get_instance()
    config.set_config(provider="dashscope", api_key="...", tiers={...})

    # For LangChain agents/tools:
    llm = config.build_chat_model(tier="lightweight")

    # For native OpenAI calls (LLMService / Embeddings):
    client = config.build_openai_client()
    model = config.get_tier_model("smart")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import SecretStr


# ---------------------------------------------------------------------------
# ChatModelProxy — hot-swappable ChatOpenAI wrapper
# ---------------------------------------------------------------------------

class ChatModelProxy:
    """A transparent proxy around ``ChatOpenAI`` that supports hot-swapping
    the inner model without recompiling LangGraph agent graphs.

    All attribute access and method calls (``invoke``, ``stream``,
    ``bind_tools``, ``model_name``, …) are delegated to the current inner
    model.  The only "own" method is :meth:`swap_model`.

    Usage::

        proxy = ChatModelProxy(ChatOpenAI(model="gpt-4o", api_key=...))
        agent = create_agent(model=proxy, tools=[...])   # graph holds proxy
        # Later, after user changes API key:
        proxy.swap_model(ChatOpenAI(model="gpt-4o", api_key=NEW_KEY))
        # Agent graph is unchanged, next request uses new key automatically.
    """

    def __init__(self, inner_model: ChatOpenAI, *, bound_tools: Optional[list] = None) -> None:
        self._inner = inner_model
        self._bound_tools = bound_tools

    # ── "own" methods (not delegated) ──────────────────────────────────

    def swap_model(self, new_model: ChatOpenAI) -> None:
        """Replace the inner model.  If tools were bound on the original,
        they are re-bound on the replacement automatically."""
        if self._bound_tools:
            new_model = new_model.bind_tools(self._bound_tools)
        self._inner = new_model
        print(f"[ChatModelProxy] Hot-swapped to model={new_model.model_name}")

    # ── bind_tools override — must re-wrap result in a proxy ──────────

    def bind_tools(self, tools: list, **kwargs: Any) -> "ChatModelProxy":
        """Bind tools to the inner model and return a *new* proxy
        wrapping the tool-bound result.  This ensures the graph always
        holds a proxy, never a bare ``ChatOpenAI``."""
        new_inner = self._inner.bind_tools(tools, **kwargs)
        return ChatModelProxy(new_inner, bound_tools=tools)

    # ── delegation for everything else ─────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        # __getattr__ is only called when the attribute is NOT found on
        # the instance itself, so swap_model / bind_tools / _inner /
        # _bound_tools are never routed here.
        return getattr(self._inner, name)

    def __repr__(self) -> str:
        return f"ChatModelProxy(inner={self._inner.model_name})"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_PERSIST_PATH = Path(__file__).resolve().parents[2] / "resources" / "llm_config.json"

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

DEFAULT_TIERS: Dict[str, Dict[str, Any]] = {
    "lightweight": {
        "model": "deepseek-v4-flash",
        "fallback_model": "gpt-4o-mini",
        "temperature": 0.1,
    },
    "smart": {
        "model": "deepseek-v4-flash",
        "fallback_model": "gpt-4o-mini",
        "temperature": 0,
    },
    "embedding": {
        "model": "text-embedding-v1",
        "fallback_model": "text-embedding-ada-002",
    },
    "vision": {
        "model": "qwen-vl-ocr-latest",
        "fallback_model": "gpt-4o",
        "temperature": 0.1,
    },
}


# ---------------------------------------------------------------------------
# LLMConfig singleton
# ---------------------------------------------------------------------------

class LLMConfig:
    """Centralised LLM configuration — singleton."""

    _instance: Optional[LLMConfig] = None

    def __init__(self) -> None:
        # Primary provider
        self.provider: str = "dashscope"
        self.api_key: Optional[str] = None
        self.base_url: str = DASHSCOPE_BASE_URL

        # Fallback provider (different base URL, for disaster recovery)
        self.fallback_provider: Optional[str] = None
        self.fallback_api_key: Optional[str] = None
        self.fallback_base_url: Optional[str] = None
        self.fallback_enabled: bool = False

        # Tier configs
        self.tiers: Dict[str, Dict[str, Any]] = {}

        # Change counter — incremented every time set_config() is called.
        # Used by lazy initialisers to detect when they need to rebuild.
        self._version: int = 0

        self._persist_path: Optional[Path] = None

        # Bootstrap from environment variables
        self._load_from_env()

    # ── Singleton ──────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> LLMConfig:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Environment bootstrap ──────────────────────────────────────────

    def _load_from_env(self) -> None:
        """Read provider/api_key/base_url from environment as initial defaults."""
        load_dotenv()

        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        # Primary: prefer DashScope
        if dashscope_key:
            self.provider = "dashscope"
            self.api_key = dashscope_key
            self.base_url = os.getenv("DASHSCOPE_BASE_URL", DASHSCOPE_BASE_URL)
        elif openai_key:
            self.provider = "openai"
            self.api_key = openai_key
            self.base_url = os.getenv("OPENAI_BASE_URL") or OPENAI_BASE_URL

        # Fallback: if both keys exist, use the other provider as fallback
        use_fallback = os.getenv("USE_LLM_FALLBACK", "false").lower() == "true"
        if use_fallback and dashscope_key and openai_key:
            self.fallback_enabled = True
            if self.provider == "dashscope":
                self.fallback_provider = "openai"
                self.fallback_api_key = openai_key
                self.fallback_base_url = os.getenv("OPENAI_BASE_URL") or OPENAI_BASE_URL
            else:
                self.fallback_provider = "dashscope"
                self.fallback_api_key = dashscope_key
                self.fallback_base_url = os.getenv("DASHSCOPE_BASE_URL", DASHSCOPE_BASE_URL)

        # Populate tiers with defaults
        self.tiers = {}
        for name, default in DEFAULT_TIERS.items():
            tier = dict(default)
            if name == "smart":
                tier["model"] = os.getenv("DASHSCOPE_MODEL") or tier["model"]
            self.tiers[name] = tier

    # ── Configuration ──────────────────────────────────────────────────

    def set_config(
        self,
        *,
        provider: str = "dashscope",
        api_key: str,
        base_url: Optional[str] = None,
        fallback_provider: Optional[str] = None,
        fallback_api_key: Optional[str] = None,
        fallback_base_url: Optional[str] = None,
        fallback_enabled: bool = True,
        tiers: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """Replace the current config and persist.

        Parameters
        ----------
        provider:
            Primary provider name (``"dashscope"``, ``"openai"``, or ``"custom"``).
        api_key:
            Primary API key.
        base_url:
            Primary base URL. If omitted, inferred from *provider*.
        fallback_provider, fallback_api_key, fallback_base_url:
            Optional secondary provider for disaster recovery.
        fallback_enabled:
            Whether to actually use the fallback when primary fails.
        tiers:
            Tier-level overrides. Missing tiers/fields fall back to defaults.
        """
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url or self._default_base_url(provider)

        self.fallback_provider = fallback_provider
        self.fallback_api_key = fallback_api_key
        if fallback_base_url:
            self.fallback_base_url = fallback_base_url
        elif fallback_provider:
            self.fallback_base_url = self._default_base_url(fallback_provider)
        self.fallback_enabled = fallback_enabled and bool(fallback_api_key)

        # Merge provided tiers with defaults
        merged_tiers: Dict[str, Dict[str, Any]] = {}
        for name, default in DEFAULT_TIERS.items():
            merged_tiers[name] = {**default, **((tiers or {}).get(name) or {})}
        self.tiers = merged_tiers

        self._version += 1
        self.save_persisted()

    @staticmethod
    def _default_base_url(provider: str) -> str:
        if provider == "dashscope":
            return DASHSCOPE_BASE_URL
        if provider == "openai":
            return OPENAI_BASE_URL
        # custom — caller must provide base_url explicitly
        return ""

    # ── Getters ────────────────────────────────────────────────────────

    def get_version(self) -> int:
        """Global version counter. Incremented on every ``set_config()`` call."""
        return self._version

    def is_fallback_available(self) -> bool:
        return self.fallback_enabled and bool(self.fallback_api_key)

    def get_tier_model(self, tier: str, use_fallback: bool = False) -> str:
        """Return the model name for *tier*, optionally from the fallback provider."""
        config = self.tiers.get(tier)
        if not config:
            raise ValueError(f"Unknown LLM tier: {tier!r}")
        if use_fallback:
            return config.get("fallback_model", config["model"])
        return config["model"]

    def get_tier_temperature(self, tier: str) -> float:
        config = self.tiers.get(tier)
        if not config:
            return 0.0
        return float(config.get("temperature", 0.0))

    # ── Client builders ────────────────────────────────────────────────

    def _active_config(self, use_fallback: bool = False) -> dict:
        """Return (api_key, base_url) for the active provider."""
        if use_fallback and self.is_fallback_available():
            return {
                "api_key": self.fallback_api_key,
                "base_url": self.fallback_base_url,
            }
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
        }

    def build_chat_model(
        self,
        tier: str,
        use_fallback: bool = False,
        **overrides: Any,
    ) -> Optional[ChatModelProxy]:
        """Build a LangChain ``ChatOpenAI`` wrapped in a hot-swappable proxy.

        Parameters
        ----------
        tier:
            Which tier to use (``"lightweight"``, ``"smart"``, etc.).
        use_fallback:
            If ``True``, use the fallback provider instead of the primary.
        **overrides:
            Passed through to ``ChatOpenAI``. Can override ``model``,
            ``temperature``, ``api_key``, ``base_url``, etc.

        Returns
        -------
        A ``ChatModelProxy`` wrapping the ``ChatOpenAI`` instance, or
        ``None`` if no API key is configured.
        """
        active = self._active_config(use_fallback)
        if not active["api_key"]:
            return None

        model = overrides.pop("model", self.get_tier_model(tier, use_fallback))
        temperature = overrides.pop("temperature", self.get_tier_temperature(tier))

        inner = ChatOpenAI(
            model=model,
            api_key=SecretStr(active["api_key"]),
            base_url=active["base_url"],
            temperature=temperature,
            **overrides,
        )
        return ChatModelProxy(inner)

    def build_openai_client(self, use_fallback: bool = False) -> Optional[OpenAI]:
        """Build a native ``OpenAI`` client for the active provider."""
        active = self._active_config(use_fallback)
        if not active["api_key"]:
            return None
        return OpenAI(
            api_key=active["api_key"],
            base_url=active["base_url"],
        )

    # ── Persistence ────────────────────────────────────────────────────

    def load_persisted(self, path: Optional[Path] = None) -> bool:
        """Load config from a JSON file.

        Returns ``True`` if a file was found and loaded, ``False`` otherwise.
        """
        path = path or DEFAULT_PERSIST_PATH
        self._persist_path = path
        if not path.exists():
            return False

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[LLMConfig] Failed to load {path}: {exc}")
            return False

        # Merge persisted data with current (env-bootstrapped) values so that
        # missing fields in the file fall back to env vars.
        self.set_config(
            provider=raw.get("provider", self.provider),
            api_key=raw.get("api_key") or self.api_key or "",
            base_url=raw.get("base_url"),
            fallback_provider=raw.get("fallback_provider"),
            fallback_api_key=raw.get("fallback_api_key"),
            fallback_base_url=raw.get("fallback_base_url"),
            fallback_enabled=raw.get("fallback_enabled", True),
            tiers=raw.get("tiers"),
        )
        # set_config increments _version; reset it to 0 so that a fresh
        # startup does not trigger unnecessary cache rebuilds.
        self._version = 0
        return True

    def save_persisted(self) -> None:
        """Write the current config to the JSON file."""
        path = self._persist_path or DEFAULT_PERSIST_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "provider": self.provider,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "fallback_provider": self.fallback_provider,
            "fallback_api_key": self.fallback_api_key,
            "fallback_base_url": self.fallback_base_url,
            "fallback_enabled": self.fallback_enabled,
            "tiers": self.tiers,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
