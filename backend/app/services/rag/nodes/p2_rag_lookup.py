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

from typing import Any, Dict, List, Optional

import structlog

from app.langgraph_v2.state import SealAIState, Source, WorkingMemory
from app.mcp.knowledge_tool import search_technical_docs
from app.services.rag.state import WorkingProfile

logger = structlog.get_logger("rag.nodes.p2_rag_lookup")

# Minimum coverage to justify a RAG call (below this, profile is too sparse)
_MIN_COVERAGE_FOR_RAG = 0.2


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------


def _build_rag_query(profile: WorkingProfile) -> str:
    """Build a German-language semantic search query from filled profile fields."""
    parts: List[str] = ["Dichtungswerkstoff"]

    if profile.medium:
        parts.append(f"für {profile.medium}")
        if profile.medium_detail:
            parts.append(f"({profile.medium_detail})")

    conditions: List[str] = []
    if profile.pressure_max_bar is not None:
        conditions.append(f"{profile.pressure_max_bar} bar")
    if profile.temperature_max_c is not None:
        conditions.append(f"{profile.temperature_max_c}°C")
    if conditions:
        parts.append(f"bei {', '.join(conditions)}")

    if profile.flange_standard:
        spec = profile.flange_standard
        if profile.flange_dn is not None:
            spec += f" DN{profile.flange_dn}"
        if profile.flange_pn is not None:
            spec += f" PN{profile.flange_pn}"
        elif profile.flange_class is not None:
            spec += f" Class {profile.flange_class}"
        parts.append(spec)

    if profile.emission_class:
        parts.append(f"Emissionsklasse {profile.emission_class}")

    if profile.industry_sector:
        parts.append(f"Branche: {profile.industry_sector}")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p2_rag_lookup(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P2 RAG Material-Lookup — retrieve relevant documents based on WorkingProfile.

    Wired as a parallel worker after node_p1_context (via Send).
    Feeds into node_p3_5_merge.
    """
    profile: Optional[WorkingProfile] = getattr(state, "working_profile", None)

    logger.info(
        "p2_rag_lookup_start",
        has_profile=profile is not None,
        coverage=round(profile.coverage_ratio(), 3) if profile else 0.0,
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    # Skip RAG if profile is too sparse
    if profile is None or profile.coverage_ratio() < _MIN_COVERAGE_FOR_RAG:
        logger.info(
            "p2_rag_lookup_skip",
            reason="profile_too_sparse",
            coverage=round(profile.coverage_ratio(), 3) if profile else 0.0,
            run_id=state.run_id,
        )
        return {}

    query = _build_rag_query(profile)
    logger.info("p2_rag_lookup_query", query=query, run_id=state.run_id)

    try:
        payload = search_technical_docs(
            query=query,
            tenant_id=state.user_id,
            k=4,
        )
    except Exception as exc:
        logger.warning(
            "p2_rag_lookup_failed",
            error=str(exc),
            run_id=state.run_id,
        )
        return {
            "retrieval_meta": {"error": f"{type(exc).__name__}: {exc}"},
        }

    hits: List[Dict[str, Any]] = payload.get("hits") or []
    retrieval_meta = dict(payload.get("retrieval_meta") or {})
    rag_context = str(payload.get("context") or "").strip()

    # Build sources from hits
    sources: List[Source] = []
    for hit in hits:
        sources.append(
            Source(
                snippet=str(hit.get("snippet") or hit.get("text") or "")[:500],
                source=hit.get("source") or hit.get("filename"),
                metadata={
                    "panel": "p2_rag_lookup",
                    "score": hit.get("fused_score") or hit.get("vector_score"),
                    "page": hit.get("page"),
                },
            )
        )

    # Package into working_memory.panel_material
    panel_material: Dict[str, Any] = {
        "query": query,
        "technical_docs": hits,
        "rag_context": rag_context,
        "source": "p2_rag_lookup",
    }

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"panel_material": panel_material})

    logger.info(
        "p2_rag_lookup_done",
        hit_count=len(hits),
        context_len=len(rag_context),
        run_id=state.run_id,
    )

    return {
        "working_memory": wm,
        "sources": sources,
        "context": rag_context,
        "retrieval_meta": retrieval_meta,
    }


__all__ = ["node_p2_rag_lookup", "_build_rag_query"]
