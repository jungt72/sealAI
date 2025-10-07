# backend/app/services/langgraph/llm_factory.py
from __future__ import annotations

from typing import Any, Optional

from langchain_openai import ChatOpenAI

from app.services.langgraph.config.runtime import get_runtime_config


def get_llm(
    *,
    streaming: bool = True,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Any:
    """Return a preconfigured ChatOpenAI client for LangGraph usage."""

    cfg = get_runtime_config()
    chosen_model = (model or cfg.default_model).strip()

    kwargs = {
        "model": chosen_model,
        "streaming": streaming,
        "temperature": temperature if temperature is not None else cfg.temperature,
        "timeout": timeout if timeout is not None else cfg.timeout,
        "max_retries": max_retries if max_retries is not None else cfg.max_retries,
        "output_version": "responses/v1",
        "use_responses_api": True,
    }
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key  # type: ignore[assignment]
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url  # type: ignore[assignment]

    return ChatOpenAI(**kwargs)
