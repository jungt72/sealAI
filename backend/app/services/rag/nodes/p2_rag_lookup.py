"""P2 RAG Material-Lookup Node for SEALAI v4.4.0 (Sprint 5).

Runs in parallel with P3 (Gap-Detection) after P1 (Context Extraction).

Responsibilities:
- Build a semantic search query from the WorkingProfile
- Call search_technical_docs() to retrieve relevant material/standard documents
- Skip RAG if the profile is too sparse (coverage < 0.2)
- Package results (context, sources, retrieval_meta) for downstream nodes

Does NOT modify RAG internals — only calls existing MCP/RAG search APIs.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional

import structlog

from app.langgraph_v2.state import SealAIState, Source, WorkingMemory
from app.observability.metrics import track_error, track_rag_retrieval
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.rag_cache import RAGCache
from app.mcp.knowledge_tool import query_deterministic_norms, search_technical_docs
from app.services.rag.bm25_store import bm25_repo
from app.services.rag.rag_orchestrator import QDRANT_COLLECTION_DEFAULT
from app.services.rag.state import WorkingProfile

logger = structlog.get_logger("rag.nodes.p2_rag_lookup")
rag_cache = RAGCache()

# Minimum coverage to justify a RAG call (below this, profile is too sparse)
_MIN_COVERAGE_FOR_RAG = 0.2
_FORCED_RAG_INTENT_CATEGORIES = {"MATERIAL_RESEARCH", "ENGINEERING_CALCULATION"}
_WIDE_SEARCH_TERMS = (
    "rührwerk",
    "ruehrwerk",
    "dichtungslösung",
    "dichtungsloesung",
    "dichtung loesung",
)
_MIN_WIDE_SEARCH_K = 8


def _is_qdrant_error(exc: BaseException) -> bool:
    """Return True when an exception indicates Qdrant is unreachable or timed out."""
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in ("connection refused", "timeout", "qdrant", "unavailable", "grpc")
    )


def _build_sources_from_hits(hits: List[Dict[str, Any]], panel: str = "p2_rag_lookup") -> List[Source]:
    """Convert raw RAG/BM25 hit dicts to Source objects."""
    sources: List[Source] = []
    for hit in hits:
        sources.append(
            Source(
                snippet=str(hit.get("snippet") or hit.get("text") or "")[:500],
                source=hit.get("source") or hit.get("filename"),
                metadata={
                    "panel": panel,
                    "score": hit.get("fused_score") or hit.get("vector_score") or hit.get("score"),
                    "page": hit.get("page"),
                },
            )
        )
    return sources


def _contains_wide_search_term(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    compact = re.sub(r"\s+", " ", normalized)
    return any(term in compact for term in _WIDE_SEARCH_TERMS)


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------


def _build_rag_query(profile: WorkingProfile) -> str:
    """Build a semantic-only search query for Qdrant from filled profile fields.

    GUARD: Deterministic fields (norms, material limits, flange standards,
    emission classes, numeric pressure/temperature) are intentionally excluded.
    Those are handled exclusively via query_deterministic_norms() (SQL).

    material is included as weak semantic context only when no normative
    context is present (flange_standard or emission_class set → SQL path).
    """
    parts: List[str] = ["Dichtungswerkstoff"]

    # material: semantic context for product docs/datasheets, but NOT when
    # a normative context (flange_standard, emission_class) is present.
    has_norm_context = bool(profile.flange_standard or profile.emission_class)
    if profile.material and not has_norm_context:
        parts.append(f"Werkstoff {profile.material}")

    if profile.product_name:
        parts.append(f"Produkt {profile.product_name}")

    if profile.medium:
        parts.append(f"für {profile.medium}")
        if profile.medium_detail:
            parts.append(f"({profile.medium_detail})")

    # pressure_max_bar, temperature_max_c → SQL via query_deterministic_norms()
    # flange_standard / flange_dn / flange_pn / flange_class → SQL
    # emission_class → SQL

    if profile.industry_sector:
        parts.append(f"Branche: {profile.industry_sector}")

    return " ".join(parts)


def _resolve_deterministic_norm_inputs(profile: Optional[WorkingProfile]) -> tuple[str | None, float | None, float | None]:
    if profile is None:
        return None, None, None
    material = str(profile.material or "").strip() or None
    temp = profile.temperature_max_c
    pressure = profile.pressure_max_bar
    return material, temp, pressure


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


async def node_p2_rag_lookup(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P2 RAG Material-Lookup — retrieve relevant documents based on WorkingProfile.

    Wired as a parallel worker after node_p1_context (via Send).
    Feeds into node_p3_5_merge.
    """
    profile: Optional[WorkingProfile] = getattr(state, "working_profile", None)
    node_start = time.perf_counter()

    logger.info(
        "p2_rag_lookup_start",
        has_profile=profile is not None,
        coverage=round(profile.coverage_ratio(), 3) if profile else 0.0,
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    # Determine if this is a knowledge query that should bypass the sparse profile check
    intent_goal = getattr(state.intent, "goal", None) if state.intent else None
    knowledge_type = getattr(state, "knowledge_type", None) or (
        getattr(state.intent, "knowledge_type", None) if state.intent else None
    )
    classification = getattr(state, "router_classification", None)
    intent_category = (
        getattr(state, "intent_category", None)
        or (state.flags or {}).get("frontdoor_intent_category")
    )
    user_text = latest_user_text(state.messages)
    has_wide_search_term = _contains_wide_search_term(user_text or "")
    force_rag_for_intent = intent_category in _FORCED_RAG_INTENT_CATEGORIES

    is_knowledge_intent = (
        intent_goal == "explanation_or_comparison"
        or knowledge_type in ("material", "lifetime", "norms")
        or classification in ("knowledge_query", "material_info")
        or state.requires_rag
        or force_rag_for_intent
    )

    # Bypass if knowledge intent OR specific fields are present (even if coverage is low)
    has_high_signal_fields = bool(
        profile and (profile.medium or profile.material or profile.product_name)
    )

    should_bypass = is_knowledge_intent or has_high_signal_fields or has_wide_search_term

    # Skip RAG if profile is too sparse AND it's not a knowledge bypass case
    if (profile is None or profile.coverage_ratio() < _MIN_COVERAGE_FOR_RAG) and not should_bypass:
        logger.info(
            "p2_rag_lookup_skip",
            reason="profile_too_sparse",
            coverage=round(profile.coverage_ratio(), 3) if profile else 0.0,
            run_id=state.run_id,
        )
        return {"last_node": "node_p2_rag_lookup"}

    if should_bypass and (profile is None or profile.coverage_ratio() < _MIN_COVERAGE_FOR_RAG):
        logger.info(
            "p2_rag_lookup_bypass_sparse_check",
            reason="knowledge_query_or_high_signal",
            is_knowledge_intent=is_knowledge_intent,
            has_high_signal_fields=has_high_signal_fields,
            force_rag_for_intent=force_rag_for_intent,
            intent_category=intent_category,
            has_wide_search_term=has_wide_search_term,
            run_id=state.run_id,
        )

    query = _build_rag_query(profile) if profile else "Dichtungstechnik"
    # If the profile is very sparse but we bypass, ensure we have a decent query
    if should_bypass and (not profile or not any(profile.model_dump().values())):
        if user_text:
            query = user_text
            logger.info("p2_rag_lookup_use_user_text", query=query, run_id=state.run_id)

    tenant_scope = (state.tenant_id or state.user_id or "global").strip()
    logger.info("p2_rag_lookup_query", query=query, tenant_id=tenant_scope, run_id=state.run_id)

    loop = asyncio.get_event_loop()
    deterministic_payload: Dict[str, Any] | None = None
    det_material, det_temp, det_pressure = _resolve_deterministic_norm_inputs(profile)
    if det_material and det_temp is not None and det_pressure is not None:
        try:
            deterministic_payload = await loop.run_in_executor(
                None,
                lambda: query_deterministic_norms(
                    material=det_material,
                    temp=float(det_temp),
                    pressure=float(det_pressure),
                    tenant_id=state.tenant_id or state.user_id,
                ),
            )
        except Exception as exc:
            logger.warning(
                "p2_rag_lookup_deterministic_norms_failed",
                material=det_material,
                temp=det_temp,
                pressure=det_pressure,
                error=f"{type(exc).__name__}: {exc}",
                run_id=state.run_id,
            )
            deterministic_payload = {
                "status": "error",
                "matches": {"din_norms": [], "material_limits": []},
                "retrieval_meta": {"error": f"{type(exc).__name__}: {exc}"},
            }

    cached_payload = rag_cache.get(tenant_scope, query)
    if cached_payload is not None:
        cached_hits: List[Dict[str, Any]] = []
        cached_context = ""
        if isinstance(cached_payload, dict):
            cached_hits = list(cached_payload.get("hits") or [])
            cached_context = str(cached_payload.get("context") or "").strip()
        elif isinstance(cached_payload, list):
            cached_hits = cached_payload

        sources = _build_sources_from_hits(cached_hits)
        panel_material: Dict[str, Any] = {
            "query": query,
            "technical_docs": cached_hits,
            "rag_context": cached_context,
            "source": "p2_rag_lookup",
            "rag_method": "cache_hit",
            "deterministic_norms": deterministic_payload,
        }
        wm = state.working_memory or WorkingMemory()
        wm = wm.model_copy(update={"panel_material": panel_material})

        retrieval_meta = {
            "rag_method": "cache_hit",
            "cache_hit": True,
            "cache_hit_count": len(cached_hits),
            "deterministic_norms": (
                deterministic_payload.get("retrieval_meta")
                if isinstance(deterministic_payload, dict)
                else None
            ),
        }
        logger.info(
            "p2_rag_lookup_cache_hit",
            tenant_id=tenant_scope,
            hit_count=len(cached_hits),
            run_id=state.run_id,
        )
        track_rag_retrieval(
            method="cache",
            tier=0,
            latency_seconds=time.perf_counter() - node_start,
            cache_hit=True,
        )
        return {
            "working_memory": wm,
            "sources": sources,
            "context": cached_context,
            "retrieval_meta": retrieval_meta,
            "last_node": "node_p2_rag_lookup",
        }

    logger.info("p2_rag_lookup_cache_miss", tenant_id=tenant_scope, run_id=state.run_id)
    track_rag_retrieval(method="cache", tier=0, latency_seconds=0.0, cache_hit=False)

    # ------------------------------------------------------------------
    # Tier 1: Full hybrid search (Qdrant dense + sparse + BM25 + rerank)
    # ------------------------------------------------------------------
    hits: List[Dict[str, Any]] = []
    retrieval_meta: Dict[str, Any] = {}
    rag_context: str = ""
    rag_method: str = "hybrid"
    requested_k = _MIN_WIDE_SEARCH_K if has_wide_search_term else 4

    try:
        tier_start = time.perf_counter()
        payload = await loop.run_in_executor(
            None,
            lambda: search_technical_docs(query=query, tenant_id=state.tenant_id or state.user_id, k=requested_k),
        )
        hits = payload.get("hits") or []
        retrieval_meta = dict(payload.get("retrieval_meta") or {})
        rag_context = str(payload.get("context") or "").strip()
        retrieval_meta["cache_hit"] = False
        retrieval_meta["requested_k"] = requested_k
        retrieval_meta["wide_search"] = has_wide_search_term
        rag_cache.set(
            tenant_scope,
            query,
            {"hits": hits, "context": rag_context, "retrieval_meta": retrieval_meta},
            ttl=3600,
        )
        track_rag_retrieval(
            method="qdrant_hybrid",
            tier=1,
            latency_seconds=time.perf_counter() - tier_start,
            cache_hit=False,
        )
        logger.info("p2_rag_lookup_tier1_ok", hit_count=len(hits), run_id=state.run_id)

    except Exception as exc:
        track_error("rag", type(exc).__name__)
        logger.warning(
            "p2_rag_lookup_tier1_failed",
            error=str(exc),
            run_id=state.run_id,
        )
        retrieval_meta = {"tier1_error": f"{type(exc).__name__}: {exc}"}

        if _is_qdrant_error(exc):
            # ----------------------------------------------------------------
            # Tier 2: BM25-only fallback (no vector store required)
            # ----------------------------------------------------------------
            try:
                tier_start = time.perf_counter()
                bm25_hits = await loop.run_in_executor(
                    None,
                    lambda: bm25_repo.search(
                        QDRANT_COLLECTION_DEFAULT, query, top_k=4
                    ),
                )
                hits = bm25_hits or []
                rag_method = "bm25_fallback"
                retrieval_meta["rag_method"] = rag_method
                retrieval_meta["cache_hit"] = False
                rag_cache.set(
                    tenant_scope,
                    query,
                    {"hits": hits, "context": "", "retrieval_meta": retrieval_meta},
                    ttl=3600,
                )
                track_rag_retrieval(
                    method="bm25",
                    tier=2,
                    latency_seconds=time.perf_counter() - tier_start,
                    cache_hit=False,
                )
                logger.info(
                    "p2_rag_lookup_tier2_bm25_ok",
                    hit_count=len(hits),
                    run_id=state.run_id,
                )
            except Exception as bm25_exc:
                track_error("rag", type(bm25_exc).__name__)
                # ------------------------------------------------------------
                # Tier 3: Graceful empty result — node completes without crash
                # ------------------------------------------------------------
                rag_method = "failed_gracefully"
                retrieval_meta["tier2_error"] = f"{type(bm25_exc).__name__}: {bm25_exc}"
                retrieval_meta["rag_method"] = rag_method
                logger.error(
                    "p2_rag_lookup_tier2_bm25_failed",
                    error=str(bm25_exc),
                    run_id=state.run_id,
                )
                return {
                    "retrieval_meta": retrieval_meta,
                    "last_node": "node_p2_rag_lookup",
                }
        else:
            # Non-Qdrant error — return error meta, don't crash graph
            track_error("rag", type(exc).__name__)
            retrieval_meta["rag_method"] = "failed_gracefully"
            logger.error(
                "p2_rag_lookup_non_qdrant_error",
                error=str(exc),
                run_id=state.run_id,
            )
            return {
                "retrieval_meta": retrieval_meta,
                "last_node": "node_p2_rag_lookup",
            }

    # Build sources from whichever tier succeeded
    sources = _build_sources_from_hits(hits)

    # Package into working_memory.panel_material
    panel_material: Dict[str, Any] = {
        "query": query,
        "technical_docs": hits,
        "rag_context": rag_context,
        "source": "p2_rag_lookup",
        "rag_method": rag_method,
        "deterministic_norms": deterministic_payload,
    }

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"panel_material": panel_material})

    logger.info(
        "p2_rag_lookup_done",
        hit_count=len(hits),
        context_len=len(rag_context),
        rag_method=rag_method,
        deterministic_status=(
            deterministic_payload.get("status")
            if isinstance(deterministic_payload, dict)
            else None
        ),
        run_id=state.run_id,
    )

    retrieval_meta["rag_method"] = rag_method
    retrieval_meta["deterministic_norms"] = (
        deterministic_payload.get("retrieval_meta")
        if isinstance(deterministic_payload, dict)
        else None
    )
    return {
        "working_memory": wm,
        "sources": sources,
        "context": rag_context,
        "retrieval_meta": retrieval_meta,
        "last_node": "node_p2_rag_lookup",
        "rag_turn_count": int(getattr(state, "rag_turn_count", 0) or 0) + 1,
    }


__all__ = ["node_p2_rag_lookup", "_build_rag_query"]
