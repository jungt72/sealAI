# backend/app/services/langgraph/graph/consult/config.py
from __future__ import annotations

import os
from typing import List

from app.services.langgraph.config.runtime import get_runtime_config
from app.services.langgraph.llm_factory import get_llm


def _env_domains() -> List[str]:
    raw = (os.getenv("CONSULT_ENABLED_DOMAINS") or "").strip()
    if not raw:
        return ["rwdr", "hydraulics_rod"]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


ENABLED_DOMAINS: List[str] = _env_domains()


def _consult_temperature() -> float:
    cfg = get_runtime_config()
    return float(os.getenv("CONSULT_LLM_TEMPERATURE", os.getenv("LLM_TEMPERATURE", str(cfg.temperature))))


def create_llm(*, streaming: bool = True, model: str | None = None):
    cfg = get_runtime_config()
    chosen_model = model or cfg.default_model
    return get_llm(
        streaming=streaming,
        model=chosen_model,
        temperature=_consult_temperature(),
        max_retries=cfg.max_retries,
    )
