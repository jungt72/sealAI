# backend/app/services/llm/llm_factory.py

"""
LLM Factory: Erzeugt eine LangChain-kompatible ChatOpenAI-Instanz
für das gewünschte Modell und Streaming-Konfiguration.
Alle Modellparameter kommen aus der zentralen Config.
"""

import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings

log = logging.getLogger(__name__)

def get_llm(
    streaming: bool = True,
    temperature: float = 0.2,
    model: str = None
) -> ChatOpenAI:
    """
    Erstellt eine ChatOpenAI-Instanz, z. B. für GPT-4.1-mini.

    Args:
        streaming (bool): Tokenweises Streaming (empfohlen: True)
        temperature (float): Kreativität/Varianz der Antworten
        model (str): Optional, überschreibt Standardmodell aus den Settings

    Returns:
        ChatOpenAI: LangChain-LLM-Objekt
    """
    active_model = model or settings.openai_model
    api_key_short = (settings.openai_api_key or "")[:12] + "..."
    log.warning(f"LLM-INIT: Modell={active_model}, Streaming={streaming}, API-Key={api_key_short}")
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        model=active_model,
        streaming=streaming,
        temperature=temperature,
    )
