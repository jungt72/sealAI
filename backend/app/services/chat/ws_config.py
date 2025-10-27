# backend/app/services/chat/ws_config.py
from __future__ import annotations
import os
from dataclasses import dataclass

# Bewährte Defaults (breit verfügbar)
_DEFAULT_MODEL = "gpt-4o-mini"
_SUPPORTED_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "o4-mini",
]

# einfache Alias/Normalisierungstabelle
_MODEL_ALIASES = {
    "gpt-5": "gpt-5-mini",
    "gpt5": "gpt-5-mini",
    "gpt-5-large": "gpt-5-mini",
    "gpt5-large": "gpt-5-mini",
    "gpt-4.1": "gpt-4o",  # falls jemand 4.1 ohne Suffix setzt
    "gpt-4.1-large": "gpt-4o",
    "gpt-4o-mini-2024-xx": "gpt-4o-mini",
}

def _normalize_model(name: str | None) -> str:
    if not name:
        return _DEFAULT_MODEL
    raw = name.strip()
    if raw in _SUPPORTED_MODELS:
        return raw
    alias = _MODEL_ALIASES.get(raw.lower())
    if alias:
        return alias
    # Fallback auf das Default, wenn unbekannt
    return _DEFAULT_MODEL

def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

def _get_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except Exception:
        return default

@dataclass
class WSConfig:
    # Auth / Transport
    auth_optional: bool = True
    streaming_enabled: bool = True

    # Modell
    model: str = _DEFAULT_MODEL

    # Routing / Graph
    default_route_mode: str = "supervisor"   # "supervisor" | "llm"
    graph_builder: str = "supervisor"        # "supervisor" | "mvp"

    # UX-Limits
    input_max_chars: int = 2000

    # Sonstiges
    allow_plain_llm: bool = True


def get_ws_config() -> WSConfig:
    # Priorität: CHAT_MODEL > GENERATION_MODEL
    env_model = os.getenv("CHAT_MODEL") or os.getenv("GENERATION_MODEL")
    norm_model = _normalize_model(env_model)

    return WSConfig(
        auth_optional=_get_bool("WS_AUTH_OPTIONAL", True),
        streaming_enabled=_get_bool("WS_STREAMING_ENABLED", True),
        model=norm_model,
        default_route_mode=(os.getenv("DEFAULT_ROUTE_MODE") or "supervisor").strip().lower(),
        graph_builder=(os.getenv("GRAPH_BUILDER") or "supervisor").strip().lower(),
        input_max_chars=_get_int("CHAT_INPUT_MAX_CHARS", 2000),
        allow_plain_llm=_get_bool("ALLOW_PLAIN_LLM", True),
    )
