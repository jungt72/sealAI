# backend/app/services/langgraph/llm_factory.py
from __future__ import annotations
import os
from typing import Any
from langchain_openai import ChatOpenAI

# env:
# OPENAI_API_KEY, OPENAI_BASE_URL (optional), OPENAI_MODEL (default gpt-5-mini)
# OPENAI_TIMEOUT_S (default 60)

def get_llm(*, streaming: bool = True) -> Any:
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    timeout = float(os.getenv("OPENAI_TIMEOUT_S", "60"))
    llm = ChatOpenAI(
        model=model,
        streaming=streaming,
        temperature=0.2,
        timeout=timeout,
        max_retries=2,
        output_version="responses/v1",
        use_responses_api=True,
    )
    return llm
