# backend/app/langgraph_v2/utils/llm_factory.py
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from threading import Lock
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterator, List, Optional, Sequence

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from app.langgraph_v2.constants import MODEL_PRO

logger = logging.getLogger(__name__)

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
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._streaming = streaming
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._client: ChatOpenAI | None = None
        self._lock = Lock()

    def _get_client(self) -> ChatOpenAI:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    kwargs: Dict[str, Any] = {
                        "model": self._model,
                        "streaming": self._streaming,
                        "max_retries": 2,
                    }
                    if self._temperature is not None:
                        kwargs["temperature"] = float(self._temperature)
                    if self._max_tokens is not None:
                        kwargs["max_tokens"] = int(self._max_tokens)
                    if self._max_retries is not None:
                        kwargs["max_retries"] = int(self._max_retries)
                    self._client = ChatOpenAI(**kwargs)
        return self._client

    def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        return self._get_client().invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        return await self._get_client().ainvoke(input, config=config, **kwargs)

    def stream(self, input: Any, config: Any | None = None, **kwargs: Any) -> Iterator[Any]:
        return self._get_client().stream(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Any | None = None, **kwargs: Any) -> AsyncIterator[Any]:
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
    temp = float(temperature) if temperature is not None else 0.0
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
    temp = float(temperature) if temperature is not None else 0.0
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
    t = (tier or "").lower().strip()

    if t == "pro":
        return MODEL_PRO or os.getenv("OPENAI_MODEL_PRO", "gpt-4.1")

    if t in {"mini", "fast"}:
        return os.getenv("OPENAI_MODEL_MINI", "gpt-4.1-mini")

    if t == "nano":
        return os.getenv("OPENAI_MODEL_NANO", "gpt-4.1-mini")

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
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and "text" in part:
                    parts.append(str(part["text"]))
                elif "text" in part:
                    parts.append(str(part["text"]))
                else:
                    parts.append(str(part))
            else:
                parts.append(str(part))
        return "".join(parts)

    return str(content)


def _build_messages(system: str, prompt: str) -> List[BaseMessage]:
    # Zentraler Helper: falls später mehr Normalisierung/Filtering nötig wird.
    return [
        SystemMessage(content=system or ""),
        HumanMessage(content=prompt or ""),
    ]


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

    if "coverage" in lower_system or "json" in lower_system:
        summary = (prompt or "").strip()
        payload = {"summary": summary[:160] or "Stub summary", "coverage": 0.92, "missing": []}
        return json.dumps(payload)

    prefix = "[FAKE_LLM_RESPONSE]"
    snippet = (prompt or "").strip()[:200]
    return f"{prefix} {snippet}".strip()


def _fake_stream_parts(text: str) -> List[str]:
    """
    Zerlegt Fake-LLM-Antworten in mehrere Teile für Streaming-Tests,
    ohne Inhalt zu verlieren.
    """
    if not text:
        return []
    size = 60
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


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
    metadata: Dict[str, Any] | None = None,
) -> str:
    """
    Führt einen Chat-Completion-Call über LangChain aus und gibt den normalisierten Text zurück.

    Wichtige Regeln:
    - Übergibt metadata NICHT als invoke-kwargs (LangChain API-Änderungen).
    - Nutzt stattdessen config={"metadata": ...} (LangChain-konformer).
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
        messages = _build_messages(system, prompt)

        extra_kwargs: Dict[str, Any] = {}
        if max_tokens is not None:
            extra_kwargs["max_tokens"] = int(max_tokens)

        config: Dict[str, Any] | None = None
        if metadata:
            config = {"metadata": metadata}

        response = chat.invoke(messages, config=config, **extra_kwargs)
        text = _normalize_lc_content(getattr(response, "content", ""))

        return text.strip()

    except Exception as e:
        logger.exception("run_llm: Fehler beim Aufruf des LLM (model=%s): %s", model, e)
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
    metadata: Dict[str, Any] | None = None,
) -> str:
    """
    Streaming-Variante des LLM-Aufrufs.

    - Nutzt ChatOpenAI(streaming=True) + astream
    - on_chunk wird bei jedem Text-Snippet (Token/Delta) aufgerufen
    - Gibt den kompletten zusammengefügten Text zurück
    """
    if _use_fake_llm():
        text = _run_fake_llm(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        for part in _fake_stream_parts(text):
            if part and on_chunk is not None:
                await on_chunk(part)
        return text.strip()

    messages = _build_messages(system, prompt)

    extra_kwargs: Dict[str, Any] = {}
    if max_tokens is not None:
        extra_kwargs["max_tokens"] = int(max_tokens)

    config: Dict[str, Any] | None = None
    if metadata:
        config = {"metadata": metadata}

    collected: List[str] = []

    try:
        chat = _get_streaming_chat_model(model, temperature)
        async for resp in chat.astream(messages, config=config, **extra_kwargs):
            text_part = _normalize_lc_content(getattr(resp, "content", ""))
            if not text_part:
                continue
            collected.append(text_part)
            if on_chunk is not None:
                await on_chunk(text_part)
    except Exception as e:
        logger.exception("run_llm_stream: Fehler beim Streaming-LLM (model=%s): %s", model, e)
        raise

    return "".join(collected).strip()


__all__ = ["LazyChatOpenAI", "get_model_tier", "run_llm", "run_llm_stream"]
