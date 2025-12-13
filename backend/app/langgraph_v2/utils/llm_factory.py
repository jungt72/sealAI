# backend/app/langgraph_v2/utils/llm_factory.py
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.langgraph_v2.constants import MODEL_PRO

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton / Cache für Chat-Modelle
# ---------------------------------------------------------------------------


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
        logger.exception("run_llm_stream: Fehler beim Streaming-LLM (model=%s): %s", model, e)
        raise

    return "".join(collected).strip()


__all__ = ["get_model_tier", "run_llm", "run_llm_stream"]
