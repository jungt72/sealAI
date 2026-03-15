# backend/app/services/rag/__init__.py
from __future__ import annotations

def __getattr__(name: str):
    if name not in {"prewarm", "hybrid_retrieve", "FINAL_K"}:
        raise AttributeError(name)

    from . import rag_orchestrator

    mapping = {
        "prewarm": rag_orchestrator.startup_warmup,
        "hybrid_retrieve": rag_orchestrator.hybrid_retrieve,
        "FINAL_K": rag_orchestrator.FINAL_K,
    }
    return mapping[name]

__all__ = ["prewarm", "hybrid_retrieve", "FINAL_K"]
