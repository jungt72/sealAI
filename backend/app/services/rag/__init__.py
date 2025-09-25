# backend/app/services/rag/__init__.py
from __future__ import annotations

# Public surface für Altaufrufer: ro.prewarm(), ro.hybrid_retrieve, ro.FINAL_K
from .rag_orchestrator import (
    startup_warmup as prewarm,   # erwartet von Startup
    hybrid_retrieve,
    FINAL_K,
)

__all__ = ["prewarm", "hybrid_retrieve", "FINAL_K"]
