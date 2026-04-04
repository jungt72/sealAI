"""
evidence_node — Phase F-C.1, Zone 4

Structured evidence retrieval from RAG.

Responsibility:
    Build a structured query from AssertedState and retrieve matching
    evidence cards via the 3-tier RAG cascade. Store results in
    state.rag_evidence for downstream nodes.

Architecture invariants enforced here:
    - Invariant 5: RAG is NEVER called on raw user text.
      The query is built deterministically from asserted parameters.
    - Invariant 4: No LLM call in this node. (RAG pipeline may use
      vector embeddings internally, but this node does not call OpenAI.)
    - If no parameters are asserted (empty AssertedState), skip retrieval.
    - tenant_id is mandatory for RAG. Missing → skip retrieval (fail-open).
    - All I/O errors are caught; rag_evidence stays [] on failure.
    - ObservedState, NormalizedState, AssertedState, GovernanceState unchanged.

Query construction (deterministic):
    Asserted values are joined into a natural-language phrase that can
    drive vector search. Example:
        medium=Dampf, pressure_bar=12.0, temperature_c=180.0
        → "Dampf 12.0 bar 180.0 °C Dichtung"
    Phase G evidence layer will replace this with a full EvidenceQuery model.

Retrieval:
    Delegates to services/real_rag.retrieve_with_tenant() — the existing
    3-tier cascade (Tier 1 hybrid, Tier 2 BM25, Tier 3 empty).
    Returns list[dict] FactCard-compatible evidence cards.
"""
from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.services.real_rag import retrieve_with_tenant

log = logging.getLogger(__name__)

# Maximum number of evidence cards to retrieve per cycle.
_EVIDENCE_K: int = 5

# Core fields and their display units for query assembly.
_FIELD_UNIT: dict[str, str] = {
    "pressure_bar":     "bar",
    "temperature_c":    "°C",
    "shaft_diameter_mm": "mm",
    "speed_rpm":        "rpm",
}


def _build_retrieval_audit(
    *,
    query: str,
    cards: list[dict],
    metrics: dict | None,
) -> dict:
    top_documents = []
    for card in cards[:3]:
        top_documents.append(
            {
                "id": card.get("id"),
                "evidence_id": card.get("evidence_id"),
                "source_ref": card.get("source_ref"),
                "retrieval_rank": card.get("retrieval_rank"),
                "retrieval_score": card.get("retrieval_score"),
            }
        )
    return {
        "query": query,
        "k_requested": metrics.get("k_requested") if isinstance(metrics, dict) else None,
        "k_returned": metrics.get("k_returned") if isinstance(metrics, dict) else len(cards),
        "threshold": metrics.get("threshold") if isinstance(metrics, dict) else None,
        "configured_threshold": metrics.get("configured_threshold") if isinstance(metrics, dict) else None,
        "threshold_applied": bool(metrics.get("threshold_applied")) if isinstance(metrics, dict) else False,
        "tier": metrics.get("tier") if isinstance(metrics, dict) else None,
        "top_scores": list(metrics.get("top_scores") or [])[:3] if isinstance(metrics, dict) else [],
        "top_documents": top_documents,
    }


def _build_evidence_query(state: GraphState) -> str | None:
    """Build a structured query string from AssertedState.

    Returns None if there are no asserted parameters to query on.
    The query is deterministic — no LLM, no randomness.
    """
    assertions = state.asserted.assertions
    if not assertions:
        return None

    parts: list[str] = []

    # Medium / material first (most discriminating for sealing domain)
    for field in ("medium", "material"):
        if field in assertions:
            parts.append(str(assertions[field].asserted_value))

    # Numeric parameters with units
    for field, unit in _FIELD_UNIT.items():
        if field in assertions:
            parts.append(f"{assertions[field].asserted_value} {unit}")

    # Other asserted fields not covered above
    covered = {"medium", "material"} | set(_FIELD_UNIT)
    for field, claim in assertions.items():
        if field not in covered:
            parts.append(str(claim.asserted_value))

    if not parts:
        return None

    query = " ".join(parts) + " Dichtung"
    log.debug("[evidence_node] built query: %r (from %d assertions)", query, len(assertions))
    return query


async def evidence_node(state: GraphState) -> GraphState:
    """Zone 4 — Retrieve structured evidence from RAG.

    Builds a query from AssertedState, calls retrieve_with_tenant(), and
    stores results in state.rag_evidence.

    Guards:
        - Skip if AssertedState is empty (nothing to query on).
        - Skip if tenant_id is missing (RAG enforces this itself, but we log).
        - Fail-open on any I/O error (rag_evidence remains []).
    """
    # Guard: nothing to query on
    if not state.asserted.assertions:
        log.debug("[evidence_node] no assertions — skipping retrieval")
        return state

    # Guard: tenant_id required
    if not state.tenant_id:
        log.warning(
            "[evidence_node] tenant_id missing — skipping retrieval "
            "(Blueprint §10: cross-tenant risk)"
        )
        return state

    query = _build_evidence_query(state)
    if query is None:
        log.debug("[evidence_node] empty query — skipping retrieval")
        return state

    try:
        cards, metrics = await retrieve_with_tenant(
            query=query,
            tenant_id=state.tenant_id,
            k=_EVIDENCE_K,
            return_metrics=True,
        )
        audit = _build_retrieval_audit(query=query, cards=cards, metrics=metrics)
        log.debug(
            "[evidence_node] retrieved %d evidence cards (tenant=%s)",
            len(cards),
            state.tenant_id,
        )
        return state.model_copy(update={"rag_evidence": cards, "rag_evidence_audit": audit})

    except Exception as exc:
        log.warning(
            "[evidence_node] retrieval failed (%s: %s) — continuing without evidence",
            type(exc).__name__,
            exc,
        )
        return state.model_copy(
            update={
                "rag_evidence": [],
                "rag_evidence_audit": {
                    "query": query,
                    "error": f"{type(exc).__name__}: {exc}",
                    "k_requested": _EVIDENCE_K,
                    "k_returned": 0,
                },
            }
        )
