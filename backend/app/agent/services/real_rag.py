"""
Agent Real-RAG Bridge — Phase 1A (Domain Data Layer)

3-Tier Fallback Cascade — Blueprint Section 11 / 10.

  Tier 1 — Hybrid (Qdrant dense + sparse vectors + BM25 fusion + rerank)
            Strict: requires ≥ 2 hits to be considered successful.
  Tier 2 — BM25-only (no vector store required)
            Triggered when Tier 1 throws OR returns < 2 results.
  Tier 3 — Graceful empty return + WARNING log
            Triggered when Tier 2 also throws.

TENANT CONTRACT (Blueprint Section 10):
  tenant_id is NEVER dropped across all three tiers.
  A missing tenant_id is always logged as a WARNING — never silently accepted.

Returns FactCard-compatible dicts (same shape as graph.py cards_data).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Minimum number of hits from Tier 1 to skip Tier 2.
_TIER1_MIN_HITS = 2


def _hit_to_card_dict(hit: dict[str, Any], rank: int) -> dict[str, Any]:
    """Convert a hybrid_retrieve or BM25 hit dict to the FactCard dict shape."""
    meta = hit.get("metadata") or {}
    return {
        "id": meta.get("id") or meta.get("doc_id") or hit.get("id") or f"rag_{rank}",
        "evidence_id": meta.get("evidence_id") or meta.get("id"),
        "source_ref": hit.get("source") or meta.get("source") or meta.get("filename"),
        "topic": meta.get("topic") or meta.get("title") or meta.get("section", ""),
        "content": hit.get("text") or hit.get("content") or "",
        "tags": meta.get("tags") or meta.get("topic_tags") or [],
        "retrieval_rank": rank,
        "retrieval_score": (
            hit.get("fused_score")
            or hit.get("vector_score")
            or hit.get("sparse_score")
            or 0.0
        ),
        "metadata": meta,
        "normalized_evidence": None,
    }


async def retrieve_with_tenant(
    query: str,
    tenant_id: str | None,
    *,
    k: int = 5,
    user_id: Optional[str] = None,
    return_metrics: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    3-Tier RAG cascade with mandatory tenant_id enforcement.

    Tier 1 — hybrid_retrieve (Qdrant hybrid + BM25 fusion):
      Returns if ≥ _TIER1_MIN_HITS results found.

    Tier 2 — bm25_repo.search (pure BM25, tenant-filtered):
      Activated when Tier 1 throws or returns < _TIER1_MIN_HITS hits.

    Tier 3 — Empty result + WARNING (graceful degradation):
      Activated when Tier 2 also throws.

    Blueprint Section 10: tenant_id is enforced in every tier.
    """
    # Phase 0C.3: tenant_id is mandatory — hard-abort instead of warn-and-proceed.
    # Returning [] is safe; the caller (graph.py) uses an empty list gracefully.
    if not (tenant_id and tenant_id.strip()):
        logger.error(
            "[real_rag] ABORT — tenant_id is None. "
            "Cross-tenant data leakage risk (Blueprint Section 10). "
            "Returning empty result set."
        )
        if return_metrics:
            return [], {"tier": "tenant_abort", "k_requested": k, "k_returned": 0}
        return []

    loop = asyncio.get_event_loop()
    t_start = time.monotonic()

    # ─────────────────────────────────────────────────────────────────────────
    # Tier 1: Full hybrid retrieval (Qdrant dense + sparse + BM25 + rerank)
    # ─────────────────────────────────────────────────────────────────────────
    tier1_hits: list[dict[str, Any]] = []
    tier1_error: str | None = None
    try:
        from app.services.rag.rag_orchestrator import hybrid_retrieve

        raw: list[dict[str, Any]] = await loop.run_in_executor(
            None,
            lambda: hybrid_retrieve(
                query=query,
                tenant=tenant_id,
                k=k,
                user_id=user_id,
                return_metrics=return_metrics,
            ),
        )
        tier1_meta: dict[str, Any] = {}
        if return_metrics:
            tier1_hits, tier1_meta = raw or ([], {})
        else:
            tier1_hits = raw or []
        logger.info(
            "[real_rag] tier1_hybrid: %d hits (%.2fs) tenant=%s",
            len(tier1_hits),
            time.monotonic() - t_start,
            tenant_id,
        )
    except Exception as exc:
        tier1_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "[real_rag] tier1_hybrid FAILED (%.2fs) tenant=%s error=%s",
            time.monotonic() - t_start,
            tenant_id,
            tier1_error,
        )

    # Tier 1 succeeds if it returned enough hits without an exception.
    if tier1_error is None and len(tier1_hits) >= _TIER1_MIN_HITS:
        cards = [_hit_to_card_dict(h, i) for i, h in enumerate(tier1_hits)]
        logger.info(
            "[real_rag] tier1 OK → returning %d cards, tenant=%s",
            len(cards),
            tenant_id,
        )
        if return_metrics:
            return cards, {
                "tier": "tier1_hybrid",
                "k_requested": k,
                "k_returned": len(cards),
                "hybrid": tier1_meta,
            }
        return cards

    # Log why we are cascading to Tier 2.
    if tier1_error:
        logger.warning(
            "[real_rag] → cascading to tier2 (tier1 exception: %s)", tier1_error
        )
    else:
        logger.warning(
            "[real_rag] → cascading to tier2 (tier1 returned only %d/%d hits, "
            "below threshold %d), tenant=%s",
            len(tier1_hits),
            k,
            _TIER1_MIN_HITS,
            tenant_id,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Tier 2: BM25-only fallback (no Qdrant required, tenant-filtered)
    # ─────────────────────────────────────────────────────────────────────────
    tier2_start = time.monotonic()
    try:
        from app.services.rag.bm25_store import bm25_repo
        from app.services.rag.rag_orchestrator import QDRANT_COLLECTION_DEFAULT

        # tenant_id is guaranteed non-None here (hard-abort above).
        bm25_filters: dict[str, Any] = {"tenant_id": tenant_id}

        bm25_hits: list[dict[str, Any]] = await loop.run_in_executor(
            None,
            lambda: bm25_repo.search(
                QDRANT_COLLECTION_DEFAULT,
                query,
                top_k=k,
                metadata_filters=bm25_filters,
            ),
        )
        bm25_hits = bm25_hits or []
        logger.info(
            "[real_rag] tier2_bm25: %d hits (%.2fs) tenant=%s",
            len(bm25_hits),
            time.monotonic() - tier2_start,
            tenant_id,
        )

        if bm25_hits:
            cards = [_hit_to_card_dict(h, i) for i, h in enumerate(bm25_hits)]
            logger.info(
                "[real_rag] tier2 OK → returning %d cards, tenant=%s",
                len(cards),
                tenant_id,
            )
            if return_metrics:
                return cards, {
                    "tier": "tier2_bm25",
                    "k_requested": k,
                    "k_returned": len(cards),
                }
            return cards

        # Tier 2 returned no hits either — fall through to Tier 3.
        logger.warning(
            "[real_rag] tier2_bm25 returned 0 hits, tenant=%s — graceful degradation",
            tenant_id,
        )

    except Exception as bm25_exc:
        logger.error(
            "[real_rag] tier2_bm25 FAILED (%.2fs) tenant=%s error=%s — graceful degradation",
            time.monotonic() - tier2_start,
            tenant_id,
            f"{type(bm25_exc).__name__}: {bm25_exc}",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Tier 3: Graceful degradation — empty result, clear WARNING
    # ─────────────────────────────────────────────────────────────────────────
    logger.warning(
        "[real_rag] TIER3 graceful degradation: all retrieval tiers exhausted "
        "for query=%r tenant=%s — returning empty list",
        query[:80],
        tenant_id,
    )
    if return_metrics:
        return [], {"tier": "tier3_empty", "k_requested": k, "k_returned": 0}
    return []
