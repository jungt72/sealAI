"""RAG helpers for LangGraph v2 (thin Qdrant stub)."""

from __future__ import annotations

from typing import Any

from app.services import rag  # type: ignore
from app.langgraph_v2.constants import QDRANT_DEFAULT_COLLECTION


def get_default_retriever(*, collection: str | None = None) -> Any:
    """
    Return a default RAG retriever for the v2 graph.

    Currently delegates to the existing rag orchestrator; will be refined later.
    """
    target_collection = (collection or QDRANT_DEFAULT_COLLECTION).strip()
    if hasattr(rag, "get_default_retriever"):
        return rag.get_default_retriever(collection=target_collection)  # type: ignore[attr-defined]
    # Fallback: return a stub callable to keep graph wiring intact.
    def _stub_retrieve(_query: str, *_args: Any, **_kwargs: Any) -> list[dict]:
        return []

    return _stub_retrieve


__all__ = ["get_default_retriever"]
