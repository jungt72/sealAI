from __future__ import annotations

from typing import Any

from app.agent.evidence.evidence_query import EvidenceQuery
from app.agent.services.real_rag import retrieve_with_tenant


async def retrieve_evidence(
    query: EvidenceQuery,
    *,
    tenant_id: str,
    return_metrics: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Tenant-safe evidence retrieval via the existing production RAG entry point."""

    return await retrieve_with_tenant(
        query=query.topic,
        tenant_id=tenant_id,
        k=query.max_results,
        return_metrics=return_metrics,
    )
