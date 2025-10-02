# backend/app/services/langgraph/llm_factory.py
from __future__ import annotations
import os
from typing import Any
from langchain_openai import ChatOpenAI


# env:
# OPENAI_API_KEY, OPENAI_BASE_URL (optional), OPENAI_MODEL (default gpt-5-mini)
# OPENAI_TIMEOUT_S (default 90)

def get_llm(*, streaming: bool = True) -> Any:
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    timeout = float(os.getenv("OPENAI_TIMEOUT_S", "90"))
    api_key = os.getenv("OPENAI_API_KEY")  # falls per Env gesetzt (empfohlen)
    base_url = os.getenv("OPENAI_BASE_URL")  # optional, z.B. Proxy/Gateway

    kwargs = dict(
        model=model,
        streaming=streaming,
        temperature=0.2,
        timeout=timeout,
        max_retries=2,
        output_version="responses/v1",
        use_responses_api=True,
    )
    if api_key:
        kwargs["api_key"] = api_key  # type: ignore[assignment]
    if base_url:
        kwargs["base_url"] = base_url  # type: ignore[assignment]

    llm = ChatOpenAI(**kwargs)
    return llm
