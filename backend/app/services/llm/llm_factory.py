# backend/app/services/llm/llm_factory.py
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from app.core.config import settings
from langchain_openai import ChatOpenAI

log = logging.getLogger("app.services.llm.llm_factory")

# Defaults (robuster gegen Latenzspitzen)
_DEFAULT_MODEL = getattr(settings, "openai_model", None) or "gpt-4o-mini"
_DEFAULT_TEMP = 0.2
_DEFAULT_TIMEOUT = 60  # Sekunden
_DEFAULT_MAX_RETRIES = 3


@lru_cache(maxsize=8)
def _mk_llm_cached(model: str, streaming: bool, temperature: float) -> ChatOpenAI:
    """
    Erzeugt einen ChatOpenAI-Client (LangChain) mit sinnvollen Defaults:
    - timeout=60s (vermeidet fallback_failed)
    - max_retries=3
    - optional base_url (falls z. B. Azure/OAI-Proxy genutzt wird)
    """
    api_key = getattr(settings, "openai_api_key", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt in der Konfiguration")

    base_url = getattr(settings, "openai_base_url", None) or "https://api.openai.com/v1"
    org = getattr(settings, "openai_organization", None) or None

    llm = ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        base_url=base_url,
        organization=org,
        streaming=streaming,
        temperature=temperature,
        timeout=_DEFAULT_TIMEOUT,
        max_retries=_DEFAULT_MAX_RETRIES,
    )
    log.warning(
        "LLM-INIT: model=%s, streaming=%s, temp=%.2f, base_url=%s, org=%s",
        model, streaming, temperature, ("default" if not getattr(settings, "openai_base_url", None) else base_url), org
    )
    return llm


def get_llm(
    *,
    model: Optional[str] = None,
    streaming: bool = True,
    temperature: Optional[float] = None,
):
    """
    Öffentliche Fabrikfunktion (wird vom SSE-Endpoint genutzt).
    """
    active_model = model or _DEFAULT_MODEL
    temp = _DEFAULT_TEMP if temperature is None else float(temperature)
    return _mk_llm_cached(active_model, streaming, temp)


# Backwards-compat (einige Stellen rufen make_llm() auf)
make_llm = get_llm
