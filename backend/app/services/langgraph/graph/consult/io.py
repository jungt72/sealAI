# backend/app/services/langgraph/graph/consult/io.py
from __future__ import annotations

from typing import Any, AsyncIterator, Dict

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
    payload = state or {}

    config: Dict[str, Any] | None = None
    thread_id = str(payload.get("chat_id") or payload.get("thread_id") or "").strip()
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}

    if config:
        result = _GRAPH.invoke(payload, config=config)
    else:
        result = _GRAPH.invoke(payload)

    try:
        return dict(result or {})
    except TypeError:
        # Fallback for LangGraph states that expose .items() but are not dicts.
        return {**(result or {})}


async def stream_consult(
    state: Dict[str, Any],
    *,
    config: Dict[str, Any] | None = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Asynchroner Event-Stream des Consult-Graphs (für Streaming-Ausgaben)."""

    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _make_graph()

    payload = state or {}
    run_config = dict(config or {})

    thread_id = str(payload.get("chat_id") or payload.get("thread_id") or "").strip()
    if thread_id:
        conf = dict(run_config.get("configurable") or {})
        conf.setdefault("thread_id", thread_id)
        run_config["configurable"] = conf

    async for event in _GRAPH.astream_events(payload, config=run_config, mode="updates"):
        yield event
