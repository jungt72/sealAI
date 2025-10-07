"""Runtime configuration helpers for LangGraph services."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LangGraphRuntimeConfig:
    """Centralised knobs for LangGraph execution."""

    default_model: str
    lite_model: str
    router_model: str
    router_fallback_model: str
    temperature: float
    timeout: float
    max_retries: int
    api_key: Optional[str]
    base_url: Optional[str]
    tracing_enabled: bool
    tracing_project: Optional[str]
    tracing_endpoint: Optional[str]
    checkpoint_required: bool
    hybrid_routing_enabled: bool
    routing_conf_path: str


@lru_cache(maxsize=1)
def get_runtime_config() -> LangGraphRuntimeConfig:
    default_model = (os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL_DEFAULT") or "gpt-5-mini").strip()
    lite_model = (os.getenv("OPENAI_LITE_MODEL") or "gpt-5-nano").strip()
    router_model = (os.getenv("OPENAI_INTENT_MODEL") or default_model).strip()
    router_fallback_model = (os.getenv("OPENAI_INTENT_FALLBACK_MODEL") or default_model).strip()

    temperature = float(os.getenv("LLM_TEMPERATURE", os.getenv("OPENAI_TEMPERATURE", "0.2")))
    timeout = float(os.getenv("OPENAI_TIMEOUT_S", "90"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", os.getenv("OPENAI_MAX_RETRIES", "2")))

    api_key = os.getenv("OPENAI_API_KEY") or None
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or None

    tracing_enabled = _truthy(os.getenv("LANGCHAIN_TRACING_V2")) and bool(os.getenv("LANGCHAIN_API_KEY"))
    tracing_project = os.getenv("LANGCHAIN_PROJECT") or None
    tracing_endpoint = os.getenv("LANGCHAIN_ENDPOINT") or None

    checkpoint_required = _truthy(os.getenv("LANGGRAPH_CHECKPOINT_REQUIRED", "1"))
    hybrid_routing_enabled = _truthy(os.getenv("HYBRID_ROUTING_ENABLED", "0"))
    routing_conf_path = (
        os.getenv("ROUTING_CONF_PATH")
        or os.getenv("ROUTING_CONFIG_PATH")
        or os.path.join(os.getcwd(), "config", "routing.yml")
    )

    return LangGraphRuntimeConfig(
        default_model=default_model,
        lite_model=lite_model,
        router_model=router_model,
        router_fallback_model=router_fallback_model,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        api_key=api_key,
        base_url=base_url,
        tracing_enabled=tracing_enabled,
        tracing_project=tracing_project,
        tracing_endpoint=tracing_endpoint,
        checkpoint_required=checkpoint_required,
        hybrid_routing_enabled=hybrid_routing_enabled,
        routing_conf_path=routing_conf_path,
    )
