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

from langgraph.config import get_stream_writer

from app.agent.evidence.evidence_query import EvidenceQuery
from app.agent.evidence.retrieval import retrieve_evidence
from app.agent.graph import GraphState

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


def _emit_progress_event(payload: dict) -> None:
    try:
        get_stream_writer()(payload)
    except RuntimeError:
        return


def _build_retrieval_audit(
    *,
    query: EvidenceQuery,
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
        "query": query.topic,
        "query_contract": {
            "topic": query.topic,
            "detected_sts_codes": list(query.detected_sts_codes),
            "query_intent": query.query_intent,
            "language": query.language,
            "max_results": query.max_results,
        },
        "event": {
            "event_type": "evidence_retrieved",
            "sources_count": len(cards),
        },
        "k_requested": metrics.get("k_requested") if isinstance(metrics, dict) else None,
        "k_returned": metrics.get("k_returned") if isinstance(metrics, dict) else len(cards),
        "threshold": metrics.get("threshold") if isinstance(metrics, dict) else None,
        "configured_threshold": metrics.get("configured_threshold") if isinstance(metrics, dict) else None,
        "threshold_applied": bool(metrics.get("threshold_applied")) if isinstance(metrics, dict) else False,
        "tier": metrics.get("tier") if isinstance(metrics, dict) else None,
        "top_scores": list(metrics.get("top_scores") or [])[:3] if isinstance(metrics, dict) else [],
        "top_documents": top_documents,
    }


def _build_evidence_query(state: GraphState) -> EvidenceQuery | None:
    """Build a structured query contract from derived/asserted state.

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

    topic = " ".join(parts) + " Dichtung"
    detected_sts_codes: list[str] = []
    requirement_class = state.derived.requirement_class or state.governance.requirement_class
    if requirement_class is not None and requirement_class.class_id:
        detected_sts_codes.append(requirement_class.class_id)

    query = EvidenceQuery(
        topic=topic,
        detected_sts_codes=detected_sts_codes,
        query_intent="material_suitability",
        max_results=_EVIDENCE_K,
    )
    log.debug("[evidence_node] built EvidenceQuery topic=%r assertions=%d", topic, len(assertions))
    return query


def _extract_source_versions(cards: list[dict]) -> dict[str, str]:
    source_versions: dict[str, str] = {}
    for card in cards:
        metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        source_key = (
            card.get("evidence_id")
            or card.get("id")
            or card.get("source_ref")
            or metadata.get("doc_id")
            or metadata.get("id")
        )
        version_value = (
            metadata.get("checksum")
            or metadata.get("source_version")
            or metadata.get("doc_version")
            or metadata.get("version")
        )
        if source_key and version_value:
            source_versions[str(source_key)] = str(version_value)
    return source_versions


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

    evidence_query = _build_evidence_query(state)
    if evidence_query is None:
        log.debug("[evidence_node] empty query — skipping retrieval")
        return state

    try:
        cards, metrics = await retrieve_evidence(
            evidence_query,
            tenant_id=state.tenant_id,
            return_metrics=True,
        )
        audit = _build_retrieval_audit(query=evidence_query, cards=cards, metrics=metrics)
        source_versions = _extract_source_versions(cards)
        log.debug(
            "[evidence_node] retrieved %d evidence cards (tenant=%s)",
            len(cards),
            state.tenant_id,
        )
        _emit_progress_event(
            {
                "event_type": "evidence_retrieved",
                "sources_count": len(cards),
            }
        )
        return state.model_copy(
            update={
                "rag_evidence": cards,
                "rag_evidence_audit": audit,
                "evidence": state.evidence.model_copy(
                    update={
                        "evidence_results": cards,
                        "source_versions": source_versions,
                        "retrieval_query": evidence_query.topic,
                    }
                ),
            }
        )

    except Exception as exc:
        log.warning(
            "[evidence_node] retrieval failed (%s: %s) — continuing without evidence",
            type(exc).__name__,
            exc,
        )
        _emit_progress_event(
            {
                "event_type": "evidence_retrieved",
                "sources_count": 0,
            }
        )
        return state.model_copy(
            update={
                "rag_evidence": [],
                "evidence": state.evidence.model_copy(
                    update={
                        "evidence_results": [],
                        "source_versions": {},
                        "retrieval_query": evidence_query.topic,
                    }
                ),
                "rag_evidence_audit": {
                    "query": evidence_query.topic,
                    "query_contract": {
                        "topic": evidence_query.topic,
                        "detected_sts_codes": list(evidence_query.detected_sts_codes),
                        "query_intent": evidence_query.query_intent,
                        "language": evidence_query.language,
                        "max_results": evidence_query.max_results,
                    },
                    "event": {
                        "event_type": "evidence_retrieved",
                        "sources_count": 0,
                    },
                    "error": f"{type(exc).__name__}: {exc}",
                    "k_requested": evidence_query.max_results,
                    "k_returned": 0,
                },
            }
        )
