from __future__ import annotations

import logging
import os
import textwrap
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage

from app.langgraph.state import ContextRef, SealAIState

try:
    from app.services.rag import hybrid_retrieve
except Exception:  # pragma: no cover - rag optional during tests
    hybrid_retrieve = None  # type: ignore


logger = logging.getLogger(__name__)

RAG_TOP_K = int(os.getenv("GRAPH_RAG_TOP_K", os.getenv("RAG_FINAL_K", "6")))
RAG_INCLUDE_SCORES = os.getenv("GRAPH_RAG_INCLUDE_SCORES", "1").lower() in {"1", "true", "yes", "on"}


def _build_context_refs(
    docs: List[Dict[str, Any]],
    prior_refs: List[ContextRef],
) -> tuple[List[ContextRef], List[str]]:
    new_refs: List[ContextRef] = list(prior_refs)
    lines: List[str] = []

    for idx, doc in enumerate(docs, start=1):
        snippet = (doc.get("text") or "").strip()
        source = (doc.get("source") or doc.get("metadata", {}).get("source") or "").strip()
        score = float(doc.get("fused_score") or doc.get("vector_score") or 0.0)
        ref_id = source or f"rag:{idx}"

        new_refs.append(
            ContextRef(
                kind="rag",
                id=ref_id,
                meta={
                    "score": score,
                    "source": source,
                },
            )
        )

        header = f"[{idx}]"
        if source:
            header += f" Quelle: {source}"
        if RAG_INCLUDE_SCORES:
            header += f" (Score {score:.2f})"

        snippet_wrapped = textwrap.fill(snippet, width=120) if snippet else "–"
        lines.append(f"{header}\n{snippet_wrapped}")

    return new_refs, lines


def context_retrieval(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    user_query = str(slots.get("user_query") or "").strip()
    tenant = slots.get("tenant")
    metadata_filters = slots.get("rag_filters")

    if not user_query or hybrid_retrieve is None:
        return {}

    try:
        documents = hybrid_retrieve(query=user_query, tenant=tenant, k=RAG_TOP_K, metadata_filters=metadata_filters)
    except Exception as exc:
        slots["rag_status"] = "error"
        slots["rag_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "context_retrieval: retrieval failed for user_query=%s tenant=%s",
            user_query,
            tenant,
            exc_info=True,
        )
        return {"slots": slots}

    if not documents:
        slots["rag_status"] = "empty"
        slots.pop("rag_error", None)
        return {"slots": slots}

    slots["rag_status"] = "success"
    slots.pop("rag_error", None)

    context_refs, lines = _build_context_refs(documents, list(state.get("context_refs") or []))

    context_message = SystemMessage(
        content="Kontextwissen (RAG):\n" + "\n\n".join(lines),
        id="msg-rag-context",
    )

    slots["rag_sources"] = [ref["id"] for ref in context_refs if ref["kind"] == "rag"]
    return {"messages": [context_message], "context_refs": context_refs, "slots": slots}
