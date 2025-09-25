# backend/app/services/langgraph/graph/consult/io.py
from __future__ import annotations

from typing import Any, Dict

# MemorySaver je nach LangGraph-Version importieren
try:
    from langgraph.checkpoint import MemorySaver  # neuere Versionen
except Exception:
    try:
        from langgraph.checkpoint.memory import MemorySaver  # ältere Versionen
    except Exception:
        MemorySaver = None  # Fallback: ohne Checkpointer

# Build-Funktion robust importieren
try:
    from .build import build_consult_graph as _build_graph
except ImportError:
    from .build import build_graph as _build_graph  # Fallback

from .state import ConsultState


def _make_graph():
    g = _build_graph()
    if MemorySaver is not None:
        g.checkpointer = MemorySaver()
    return g.compile()


_GRAPH = None


def invoke_consult(state: Dict[str, Any]) -> Dict[str, Any]:
    """Synchroner Invoke des Consult-Graphs mit einfachem Singleton-Caching."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _make_graph()
    result = _GRAPH.invoke(state or {})
    if isinstance(result, ConsultState):
        return dict(result)
    return dict(result or {})
