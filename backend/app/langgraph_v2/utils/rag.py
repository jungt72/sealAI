"""RAG helpers for LangGraph v2 (thin Qdrant stub)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

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


def unpack_rag_payload(payload: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
    if isinstance(payload, dict):
        context = payload.get("context")
        meta = payload.get("retrieval_meta")
        text = (context or "").strip() if isinstance(context, str) else str(context or "")
        return text, meta if isinstance(meta, dict) else None
    text = (payload or "").strip() if isinstance(payload, str) else str(payload or "")
    return text, None


def apply_rag_quality_gate(
    text: str,
    meta: Optional[Dict[str, Any]],
    *,
    min_top_score: float,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    if not meta or meta.get("skipped"):
        return text, meta
    k_returned = meta.get("k_returned")
    try:
        if int(k_returned or 0) == 0:
            meta["skipped"] = True
            meta["reason"] = "no_hits"
            return "", meta
    except (TypeError, ValueError):
        pass
    top_scores = meta.get("top_scores")
    if isinstance(top_scores, list) and top_scores:
        try:
            top_score = float(top_scores[0])
        except (TypeError, ValueError):
            return text, meta
        if top_score < float(min_top_score):
            meta["skipped"] = True
            meta["reason"] = "low_score"
            return "", meta
    return text, meta


__all__ = ["get_default_retriever", "unpack_rag_payload", "apply_rag_quality_gate"]
