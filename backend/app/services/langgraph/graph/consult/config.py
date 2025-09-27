# backend/app/services/langgraph/graph/consult/config.py
from __future__ import annotations

import os
from typing import List, Optional
from langchain_openai import ChatOpenAI


# --- Domänen-Schalter ---------------------------------------------------------
# Kommagetrennte Liste via ENV z. B.: "rwdr,hydraulics_rod"
def _env_domains() -> List[str]:
    raw = (os.getenv("CONSULT_ENABLED_DOMAINS") or "").strip()
    if not raw:
        return ["rwdr", "hydraulics_rod"]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


ENABLED_DOMAINS: List[str] = _env_domains()


# --- LLM-Fabrik ---------------------------------------------------------------
def _model_name() -> str:
    """Default-Modellkürzel für Consult-LLMs."""
    # Mit "gpt-5-mini" als einzigem Standard, unabhängig von älteren ENV-Angaben.
    return (os.getenv("LLM_MODEL_DEFAULT") or "gpt-5-mini").strip() or "gpt-5-mini"


def _base_url() -> Optional[str]:
    # kompatibel zu llm_factory: neues Feld heißt base_url (nicht api_base)
    base = (os.getenv("OPENAI_API_BASE") or "").strip()
    return base or None


def create_llm(*, streaming: bool = True, model: str | None = None) -> ChatOpenAI:
    """
    Einheitliche LLM-Erzeugung für den Consult-Graph.
    Nutzt GPT-5-mini (Default) und übernimmt OPENAI_API_BASE, falls gesetzt,
    via base_url (kein api_base!).
    """
    kwargs = {
        "model": (model or _model_name()),
        "streaming": streaming,
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
        "max_retries": int(os.getenv("LLM_MAX_RETRIES", "2")),
        "output_version": "responses/v1",
        "use_responses_api": True,
    }
    base = _base_url()
    if base:
        kwargs["base_url"] = base
    return ChatOpenAI(**kwargs)
