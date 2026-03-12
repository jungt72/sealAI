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


async def retrieve_rag_context(query: str, tenant_id: Optional[str] = None, limit: int = _DEFAULT_RAG_LIMIT) -> List[FactCard]:
    """Best-effort async retrieval hook used by the active agent graph.

    The active agent path currently has no dedicated external RAG client here.
    This adapter preserves the expected async contract and falls back to the
    local fact-card KB until a canonical async retriever is wired in.
    """
    del tenant_id
    if not query or not query.strip():
        return []
    return retrieve_fact_cards_fallback(query, limit=limit)
