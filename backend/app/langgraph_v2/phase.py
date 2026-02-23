from __future__ import annotations

from types import SimpleNamespace

PHASE = SimpleNamespace(
    ROUTING="routing",
    ENTRY="entry",
    FRONTDOOR="frontdoor",
    SMALLTALK="smalltalk",
    INTENT="intent",
    SUPERVISOR="supervisor",
    AGGREGATION="aggregation",
    PANEL="panel",
    CONFIRM="confirm",
    PREFLIGHT_USE_CASE="preflight_use_case",
    PREFLIGHT_PARAMETERS="preflight_parameters",
    EXTRACTION="extraction",
    CALCULATION="calculation",
    QUALITY_GATE="quality_gate",
    PROCUREMENT="procurement",
    CONSULTING="consulting",
    KNOWLEDGE="knowledge",
    VALIDATION="validation",
    RAG="rag",
    FINAL="final",
    ERROR="error",
)

PHASE_VALUES = tuple(PHASE.__dict__.values())

__all__ = ["PHASE", "PHASE_VALUES"]
