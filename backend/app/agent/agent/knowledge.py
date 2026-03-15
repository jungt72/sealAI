import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
_KB_SOURCE_PATH = Path(__file__).resolve().parents[2] / "data" / "kb" / "SEALAI_KB_PTFE_factcards_gates_v1_3.json"
_DEFAULT_RAG_LIMIT = 3

class FactCard:
    """Repräsentiert eine technische Wissenseinheit (FactCard)."""
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.evidence_id = data.get("evidence_id", self.id)
        self.source_ref = data.get("source_ref")
        self.topic = data.get("topic", "")
        self.content = data.get("content", "")
        self.tags = data.get("topic_tags", [])
        self.retrieval_rank = data.get("retrieval_rank")
        self.retrieval_score = data.get("retrieval_score")
        self.metadata = data.get("metadata", {})
        self.normalized_evidence = data.get("normalized_evidence")

def load_fact_cards(path: str) -> List[FactCard]:
    """Lädt die Knowledge Base aus einer JSON-Datei."""
    kb_path = Path(path)
    if not kb_path.exists():
        logger.warning(f"Knowledge Base nicht gefunden: {path}")
        return []
    
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            cards_data = data.get("factcards", [])
            return [FactCard(c) for c in cards_data]
    except Exception as e:
        logger.error(f"Fehler beim Laden der FactCards: {e}")
        return []

def retrieve_fact_cards(query: str, cards: List[FactCard], limit: int = 3) -> List[FactCard]:
    """
    Simuliert eine RAG-Suche (Phase D1).
    Sucht nach Übereinstimmungen in Topic, Content oder Tags.
    Verbessert: Prüft auf einzelne Wörter der Query.
    """
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) >= 3]
    if not query_words:
        query_words = [query_lower]

    results = []
    
    for card in cards:
        score = 0
        topic_lower = card.topic.lower()
        content_lower = card.content.lower()
        tags_lower = [t.lower() for t in card.tags]

        for word in query_words:
            if word in topic_lower:
                score += 10
            if word in content_lower:
                score += 5
            if any(word in tag for tag in tags_lower):
                score += 3
            
        if score > 0:
            results.append((score, card))
            
    # Nach Score sortieren und Limit anwenden
    results.sort(key=lambda x: x[0], reverse=True)
    return [card for score, card in results[:limit]]


def retrieve_fact_cards_fallback(query: str, limit: int = _DEFAULT_RAG_LIMIT) -> List[FactCard]:
    """Load the local fact-card KB and run the lightweight fallback retrieval."""
    cards = load_fact_cards(str(_KB_SOURCE_PATH))
    return retrieve_fact_cards(query, cards, limit=limit)


def _hit_to_fact_card(hit: Dict[str, Any], rank: int) -> FactCard:
    """Map a single hybrid_retrieve result hit to a FactCard for use in the agent graph."""
    metadata = hit.get("metadata") or {}
    doc_id = (
        metadata.get("id")
        or metadata.get("doc_id")
        or hit.get("source")
        or f"rag_hit_{rank}"
    )
    return FactCard({
        "id": doc_id,
        "evidence_id": metadata.get("evidence_id") or doc_id,
        "source_ref": hit.get("source"),
        "topic": metadata.get("topic") or metadata.get("title") or "",
        "content": hit.get("text") or "",
        "topic_tags": metadata.get("tags") or metadata.get("topic_tags") or [],
        "retrieval_rank": rank,
        "retrieval_score": hit.get("fused_score") or hit.get("vector_score"),
        "metadata": metadata,
        "normalized_evidence": None,
    })


async def retrieve_rag_context(
    query: str,
    tenant_id: Optional[str] = None,
    limit: int = _DEFAULT_RAG_LIMIT,
    *,
    owner_id: Optional[str] = None,
) -> List[FactCard]:
    """Tenant-safe async retrieval using the canonical hybrid_retrieve infrastructure.

    Parameters
    ----------
    tenant_id:
        Organizational/session scope passed as `tenant` to hybrid_retrieve.
        May be an org-level JWT claim or fall back to the individual user identity.
    owner_id:
        Individual document-ownership identity — canonical_user_id (user.user_id or sub).
        This is the value stored in Qdrant as `tenant_id` at ingest time and used by
        the visibility `should`-clause to unlock private documents.
        Falls back to tenant_id when not provided.

    Raises on retrieval failure so the caller (_retrieve_relevant_cards_async in
    graph.py) can apply the controlled local-KB fallback with explicit path labeling.
    The local fallback is never invoked silently from within this function.
    """
    if not query or not query.strip():
        return []
    # Lazy import avoids circular import at module load time and keeps the
    # rag_orchestrator (with its heavy fastembed/qdrant deps) out of agent tests.
    from app.services.rag import hybrid_retrieve  # noqa: PLC0415
    effective_owner_id = owner_id or tenant_id
    hits: List[Dict[str, Any]] = await asyncio.to_thread(
        hybrid_retrieve,
        query=query,
        tenant=tenant_id,
        k=limit,
        user_id=effective_owner_id,
    )
    logger.debug(
        "[RAG:knowledge] hybrid_retrieve: %d hits, tenant=%s, owner=%s",
        len(hits), tenant_id, effective_owner_id,
    )
    return [_hit_to_fact_card(h, rank) for rank, h in enumerate(hits)]
