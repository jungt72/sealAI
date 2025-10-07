"""Helpers for LangSmith/LangChain tracing integration."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.services.langgraph.config.runtime import get_runtime_config


@lru_cache(maxsize=1)
def _tracing_switch() -> bool:
    cfg = get_runtime_config()
    return cfg.tracing_enabled


def tracing_callbacks(run_name: Optional[str] = None) -> List[Any]:
    if not _tracing_switch():
        return []
    try:
        from langchain_core.tracers.langchain import LangChainTracer
    except Exception:
        return []

    cfg = get_runtime_config()
    tracer = LangChainTracer(
        project_name=cfg.tracing_project,
        api_url=cfg.tracing_endpoint,
    )
    if run_name:
        try:
            tracer.run_name = run_name  # type: ignore[attr-defined]
        except Exception:
            pass
    return [tracer]


def with_tracing(config: Optional[Dict[str, Any]], *, run_name: str) -> Dict[str, Any]:
    """Merge tracing callbacks into the config payload expected by LangGraph."""
    callbacks = tracing_callbacks(run_name)
    if not callbacks:
        return dict(config or {})

    merged: Dict[str, Any] = dict(config or {})
    existing = list(merged.get("callbacks") or [])
    merged["callbacks"] = [*existing, *callbacks]
    return merged


__all__ = ["tracing_callbacks", "with_tracing"]
