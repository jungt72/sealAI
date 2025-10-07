# backend/app/services/langgraph/llm_router.py
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.services.langgraph.config.runtime import get_runtime_config


def _mk_router_llm(model: str) -> ChatOpenAI:
    cfg = get_runtime_config()
    return ChatOpenAI(
        model=model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        streaming=False,
        max_retries=1,
        timeout=5,
        output_version="responses/v1",
        use_responses_api=True,
    )


@lru_cache(maxsize=1)
def get_router_llm() -> ChatOpenAI:
    cfg = get_runtime_config()
    return _mk_router_llm(cfg.router_model)


@lru_cache(maxsize=1)
def get_router_fallback_llm() -> ChatOpenAI:
    cfg = get_runtime_config()
    return _mk_router_llm(cfg.router_fallback_model)
