# MIGRATION: Phase-2 – material RAG selector node with caching
"""Selects evidence references for the material domain on demand with Redis caching."""
from __future__ import annotations

import os
from typing import Any, Dict

from ....state import ContextRef
from ....utils.logging import log_event
from ....utils.rag_cache import get_rag_cache
from ..state import MaterialPartialState, MaterialState, MaterialStateModel, merge_material_state


class MaterialRAGSelectNode:
    def __init__(self):
        # Load config from agents.yaml - in real implementation, inject via dependency
        self.config = {
            "index_id": "materials",
            "top_k": 5,
            "hybrid": True,
            "filters": {"domain": "material"},
            "cache_ttl_seconds": 3600,
        }

    def _retrieve_rag(self, query: str, filters: Dict[str, Any], index_id: str, top_k: int) -> list[ContextRef]:
        """Perform actual RAG retrieval with caching."""
        cache = get_rag_cache()

        # Try cache first
        cached_results = cache.get(query, filters, index_id, top_k)
        if cached_results:
            return cached_results

        # Perform actual retrieval (mock for now - integrate real RAG)
        try:
            # Import and use real RAG orchestrator
            from app.services.rag.rag_orchestrator import hybrid_retrieve

            results = hybrid_retrieve(
                query=query,
                filters=filters,
                index_id=index_id,
                top_k=top_k,
                hybrid=self.config["hybrid"]
            )

            # Convert to ContextRef format
            context_refs = []
            for doc in results:
                ref = ContextRef(
                    kind="rag",
                    id=doc.get("id", f"doc-{hash(doc.get('content', ''))[:8]}"),
                    meta={
                        "score": doc.get("score", 0.0),
                        "source": doc.get("source", "unknown"),
                        "title": doc.get("title", ""),
                    }
                )
                context_refs.append(ref)

            # Cache results
            cache.set(query, filters, index_id, top_k, context_refs, self.config["cache_ttl_seconds"])
            return context_refs

        except Exception as e:
            log_event(
                "rag_retrieval_error",
                trace_id="unknown",
                node="material_rag_select",
                error=str(e),
            )
            # Fallback to empty results
            return []

    def __call__(self, state: MaterialState) -> MaterialState:
        validated = merge_material_state(state, {})
        model = MaterialStateModel.model_validate(validated)

        # Extract query from latest user message
        query = ""
        for msg in reversed(model.messages):
            if msg.role == "user":
                query = msg.content
                break

        # Get domain-specific filters from slots
        filters = dict(self.config["filters"])
        if "domain_filters" in model.slots:
            filters.update(model.slots["domain_filters"])

        # Perform RAG retrieval with caching
        context_refs = self._retrieve_rag(
            query=query,
            filters=filters,
            index_id=self.config["index_id"],
            top_k=self.config["top_k"]
        )

        update: MaterialPartialState = {
            "context_refs": context_refs,
        }

        log_event(
            "material_rag_select",
            trace_id=model.meta.trace_id,
            node="material_rag_select",
            query_length=len(query),
            results_count=len(context_refs),
        )

        return merge_material_state(model.model_dump(), update)


__all__ = ["MaterialRAGSelectNode"]