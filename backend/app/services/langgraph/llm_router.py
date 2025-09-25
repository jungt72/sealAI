# backend/app/services/langgraph/llm_router.py
from __future__ import annotations

import os
from functools import lru_cache
from langchain_openai import ChatOpenAI

def _mk_router_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        streaming=False,
        max_retries=1,
        timeout=5,
    )

@lru_cache(maxsize=1)
def get_router_llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_INTENT_MODEL", "gpt-5-mini")
    return _mk_router_llm(model)

@lru_cache(maxsize=1)
def get_router_fallback_llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_INTENT_FALLBACK_MODEL", "gpt-5-mini")
    return _mk_router_llm(model)
