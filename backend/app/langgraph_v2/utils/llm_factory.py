# backend/app/langgraph_v2/utils/llm_factory.py
from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache
from threading import Lock
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterator, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import Runnable
from openai import APIError, RateLimitError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.core.config import settings
from app.langgraph_v2.constants import MODEL_PRO

logger = logging.getLogger(__name__)


def _estimate_text_tokens(text: str) -> int:
    """Best-effort token estimate without additional runtime dependencies."""
    stripped = (text or "").strip()
    if not stripped:
        return 0
    # Approximation: ~4 chars per token in mixed EN/DE technical text.
    return max(1, len(stripped) // 4)


def _estimate_message_tokens(messages: list[Any]) -> int:
    total_chars = 0
    for msg in messages:
        content = getattr(msg, "content", "")
        total_chars += len(_normalize_lc_content(content))
    return max(0, total_chars // 4)


def bind_permitted_tools(chat: ChatOpenAI, user_scopes: List[str] | None = None) -> ChatOpenAI:
    """
    Bind MCP tools dynamically based on user scopes.

    Scope-to-tool mapping is centralized in `app.mcp.knowledge_tool.get_permitted_tools`.
    If no scopes are granted, returns the original model unmodified.
    """
    from app.mcp.knowledge_tool import get_permitted_tools

    tools = get_permitted_tools(list(user_scopes or []))
    if not tools:
        return chat
    return chat.bind_tools(tools)


def _global_temperature() -> float:
    try:
        return float(getattr(settings, "openai_temperature", 0.0) or 0.0)
    except Exception:
        return 0.0

# ---------------------------------------------------------------------------
# Singleton / Cache für Chat-Modelle
# ---------------------------------------------------------------------------


class LazyChatOpenAI(Runnable[Any, Any]):
    """Lazy wrapper to avoid ChatOpenAI init at graph build time."""

    def __init__(
        self,
        *,
        model: str,
        temperature: float | None = None,
        streaming: bool = False,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        cache: bool | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._streaming = streaming
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._cache = cache
        self._client: ChatOpenAI | None = None
        self._lock = Lock()

    def _get_client(self) -> ChatOpenAI:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    kwargs: Dict[str, Any] = {
                        "model": self._model,
                        "streaming": self._streaming,
                    }
                    kwargs["temperature"] = _global_temperature()
                    if self._max_tokens is not None:
                        kwargs["max_tokens"] = int(self._max_tokens)
                    if self._max_retries is not None:
                        kwargs["max_retries"] = int(self._max_retries)
                    if self._cache is not None:
                        kwargs["cache"] = bool(self._cache)
                    self._client = ChatOpenAI(**kwargs)
        return self._client

    def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        return self._get_client().invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        return await self._get_client().ainvoke(input, config=config, **kwargs)

    def stream(self, input: Any, config: Any | None = None, **kwargs: Any) -> Iterator[Any]:
        return self._get_client().stream(input, config=config, **kwargs)

    async def astream(
        self, input: Any, config: Any | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        async for chunk in self._get_client().astream(input, config=config, **kwargs):
            yield chunk


@lru_cache(maxsize=16)
def _get_chat_model(model: str, temperature: float | None) -> ChatOpenAI:
    """
    Erzeugt (und cached) ein LangChain-Chatmodell auf Basis von langchain-openai.

    Vorteile:
    - zentrale Konfiguration (Retry, Temperatur)
    - automatische Integration mit LangSmith/Telemetry, falls Umgebungsvariablen gesetzt sind
    """
    temp = _global_temperature()

    return ChatOpenAI(
        model=model,
        temperature=temp,
        streaming=False,
        max_retries=2,
    )


@lru_cache(maxsize=16)
def _get_streaming_chat_model(model: str, temperature: float | None) -> ChatOpenAI:
    """
    Streaming-fähiges Chat-Modell (streaming=True).
    Wird separat gecached, um parallele non-streaming Calls nicht zu beeinflussen.
    """
    temp = _global_temperature()
    return ChatOpenAI(
        model=model,
        temperature=temp,
        streaming=True,
        max_retries=2,
    )


# ---------------------------------------------------------------------------
# Modell-Tier Auswahl
# ---------------------------------------------------------------------------


def get_model_tier(tier: str | None) -> str:
    """
    Mappt logische Tiers auf konkrete Modellnamen.

    - "pro"   -> MODEL_PRO (aus constants) oder Fallback
    - "mini"  -> env OPENAI_MODEL_MINI oder gpt-4.1-mini
    - "nano"  -> env OPENAI_MODEL_NANO oder gpt-4.1-mini
    - andere (z.B. "fast") -> Default "mini"
    """
    t = (tier or "").lower()

    if t == "pro":
        return MODEL_PRO or os.getenv("OPENAI_MODEL_PRO", "gpt-4.1")

    if t == "mini" or t == "fast":
        # "fast" wird intern wie "mini" behandelt
        return os.getenv("OPENAI_MODEL_MINI", "gpt-4.1-mini")

    if t == "nano":
        # Ultra-günstig / klein – zur Not identisch zu mini
        return os.getenv("OPENAI_MODEL_NANO", "gpt-4.1-mini")

    # Default: mini
    return os.getenv("OPENAI_MODEL_MINI", "gpt-4.1-mini")


# ---------------------------------------------------------------------------
# Content-Normalisierung
# ---------------------------------------------------------------------------


def _normalize_lc_content(content: Any) -> str:
    """
    Normalisiert LangChain-/OpenAI-Message-Content zu einem einfachen String.

    Beispiele:
    - "Hallo" -> "Hallo"
    - [{"type": "text", "text": "Hallo"}, {"type": "text", "text": " Welt"}] -> "Hallo Welt"
    - Sonstige Strukturen werden best-effort stringifiziert.
    """
    # Einfacher String
    if isinstance(content, str):
        return content

    # Liste von Parts (new-style content)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                # Typisch: {"type": "text", "text": "..."}
                if part.get("type") == "text" and "text" in part:
                    parts.append(str(part["text"]))
                elif "text" in part:
                    parts.append(str(part["text"]))
                else:
                    parts.append(str(part))
            else:
                parts.append(str(part))
        return "".join(parts)

    # Fallback
    return str(content)


# ---------------------------------------------------------------------------
# Fake-LLM (für Offline-Tests / deterministische Runs)
# ---------------------------------------------------------------------------


def _use_fake_llm() -> bool:
    flag = os.getenv("LANGGRAPH_USE_FAKE_LLM", "")
    return flag.strip().lower() in {"1", "true", "yes", "on"}


def _run_fake_llm(
    *,
    model: str,
    prompt: str,
    system: str,
    temperature: float | None = 1.0,
    max_tokens: int | None = None,
) -> str:
    """Deterministische Offline-Antwort für Tests / CI."""
    lower_system = (system or "").lower()

    # Spezialfall: Coverage-/JSON-Prompts -> minimales JSON zurückgeben
    if "coverage" in lower_system or "json" in lower_system:
        summary = (prompt or "").strip()
        payload = {
            "summary": summary[:160] or "Stub summary",
            "coverage": 0.92,
            "missing": [],
        }
        return json.dumps(payload)

    prefix = "[FAKE_LLM_RESPONSE]"
    snippet = (prompt or "").strip()[:200]
    return f"{prefix} {snippet}".strip()


def _fake_stream_parts(text: str) -> List[str]:
    """
    Zerlegt Fake-LLM-Antworten in mehrere Teile für Streaming-Tests,
    ohne Inhalt zu verlieren.

    Wichtig: Alle Teile zusammen müssen wieder den vollständigen Text ergeben,
    damit Tests wie `assert "".join(chunks) == result` stabil bleiben.
    """
    if not text:
        return []

    # Ziel: „realistische“ Chunks (~60 Zeichen), aber vollständige Abdeckung.
    size = 60
    parts = [text[i : i + size] for i in range(0, len(text), size)]
    return parts or [text]


# ---------------------------------------------------------------------------
# Zentrale LLM-Hilfsfunktion (Best Practice: LangChain ChatOpenAI)
# ---------------------------------------------------------------------------


def run_llm(
    *,
    model: str,
    prompt: str,
    system: str,
    temperature: float | None = 1.0,
    max_tokens: int | None = None,
    metadata: Dict[str, Any] | None = None,  # wird nicht mehr direkt an invoke übergeben (LangChain API-Change)
) -> str:
    """
    Führt einen Chat-Completion-Call über LangChain aus und gibt den normalisierten Text zurück.

    - Nutzt langchain-openai.ChatOpenAI
    - Kombiniert System- und User-Message
    - Gibt immer einen plain String zurück (Content normalisiert)
    """
    if _use_fake_llm():
        return _run_fake_llm(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    try:
        chat = _get_chat_model(model, temperature)

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ]

        # LangChain 1.x: metadata wird intern bereits gehandhabt.
        # Wir übergeben hier *keine* metadata mehr via kwargs, um
        # "multiple values for keyword argument 'metadata'" zu vermeiden.
        extra_kwargs: Dict[str, Any] = {}
        if max_tokens is not None:
            extra_kwargs["max_tokens"] = int(max_tokens)
        # if metadata is not None:
        #     -> ggf. später über config nutzen, aber nicht direkt als kwargs

        response = chat.invoke(messages, **extra_kwargs)
        text = _normalize_lc_content(response.content)

        return text.strip()

    except Exception as e:
        logger.exception("run_llm: Fehler beim Aufruf des LLM (model=%s): %s", model, e)
        # Fallback: lieber eine kurze, ehrliche Fehlermeldung an den User weitergeben
        return (
            "Entschuldigung, bei der internen Modellabfrage ist ein Fehler aufgetreten. "
            "Bitte versuche es in Kürze erneut."
        )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIError, RateLimitError, APITimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _invoke_with_retry(chat: Any, messages: list, **kwargs: Any) -> Any:
    """Internal helper: calls chat.ainvoke() with exponential-backoff retry on transient API errors.

    Retry strategy:
    - Attempt 1: immediate
    - Attempt 2: wait 2 s
    - Attempt 3: wait 4 s (capped at 10 s)
    - Then re-raise to the caller for final fallback.
    """
    return await chat.ainvoke(messages, **kwargs)


async def run_llm_async(
    *,
    model: str,
    prompt: str,
    system: str,
    temperature: float | None = 1.0,
    max_tokens: int | None = None,
    metadata: Dict[str, Any] | None = None,
) -> str:
    """Async variant of run_llm — uses ChatOpenAI.ainvoke() with 3× retry on transient errors."""
    from app.observability.metrics import track_error, track_llm_call

    start_time = time.perf_counter()
    if _use_fake_llm():
        text = _run_fake_llm(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        duration = time.perf_counter() - start_time
        tokens = _estimate_text_tokens(text)
        track_llm_call(model=model, latency_seconds=duration, input_tokens=tokens, output_tokens=tokens, success=True)
        return text
    try:
        chat = _get_chat_model(model, temperature)
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ]
        extra_kwargs: Dict[str, Any] = {}
        if max_tokens is not None:
            extra_kwargs["max_tokens"] = int(max_tokens)
        response = await _invoke_with_retry(chat, messages, **extra_kwargs)
        text = _normalize_lc_content(response.content).strip()
        duration = time.perf_counter() - start_time
        track_llm_call(
            model=model,
            latency_seconds=duration,
            input_tokens=_estimate_message_tokens(messages),
            output_tokens=_estimate_text_tokens(text),
            success=True,
        )
        return text
    except Exception as e:
        duration = time.perf_counter() - start_time
        track_llm_call(model=model, latency_seconds=duration, input_tokens=0, output_tokens=0, success=False)
        track_error("llm", type(e).__name__)
        logger.exception("run_llm_async: Fehler nach allen Retries (model=%s): %s", model, e)
        return (
            "Entschuldigung, bei der internen Modellabfrage ist ein Fehler aufgetreten. "
            "Bitte versuche es in Kürze erneut."
        )


async def run_llm_stream(
    *,
    model: str,
    prompt: str,
    system: str,
    temperature: float | None = 1.0,
    max_tokens: int | None = None,
    on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    metadata: Dict[str, Any] | None = None,  # ebenfalls nur noch für spätere config-Nutzung
) -> str:
    """
    Streaming-Variante des LLM-Aufrufs.

    - Nutzt ChatOpenAI(streaming=True) + astream
    - on_chunk wird bei jedem Text-Snippet (Token/Delta) aufgerufen
    - Gibt den kompletten zusammengefügten Text zurück
    """
    from app.observability.metrics import track_error, track_llm_call

    start_time = time.perf_counter()
    if _use_fake_llm():
        text = _run_fake_llm(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parts = _fake_stream_parts(text)
        for part in parts:
            if part and on_chunk is not None:
                await on_chunk(part)
        duration = time.perf_counter() - start_time
        tokens = _estimate_text_tokens(text)
        track_llm_call(model=model, latency_seconds=duration, input_tokens=tokens, output_tokens=tokens, success=True)
        return text.strip()

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ]

    extra_kwargs: Dict[str, Any] = {}
    if max_tokens is not None:
        extra_kwargs["max_tokens"] = int(max_tokens)
    # Auch hier keine metadata in kwargs → sonst TypeError in LangChain:
    # if metadata is not None: ...

    collected: List[str] = []

    try:
        chat = _get_streaming_chat_model(model, temperature)
        async for resp in chat.astream(messages, **extra_kwargs):
            text_part = _normalize_lc_content(resp.content)
            if not text_part:
                continue
            collected.append(text_part)
            if on_chunk is not None:
                await on_chunk(text_part)
    except Exception as e:
        duration = time.perf_counter() - start_time
        track_llm_call(model=model, latency_seconds=duration, input_tokens=0, output_tokens=0, success=False)
        track_error("llm", type(e).__name__)
        logger.exception("run_llm_stream: Fehler beim Streaming-LLM (model=%s): %s", model, e)
        raise

    full_text = "".join(collected).strip()
    duration = time.perf_counter() - start_time
    track_llm_call(
        model=model,
        latency_seconds=duration,
        input_tokens=_estimate_message_tokens(messages),
        output_tokens=_estimate_text_tokens(full_text),
        success=True,
    )
    return full_text


__all__ = ["LazyChatOpenAI", "bind_permitted_tools", "get_model_tier", "run_llm", "run_llm_async", "run_llm_stream"]
