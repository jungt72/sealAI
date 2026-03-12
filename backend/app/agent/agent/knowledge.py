import json
import logging
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.agent.domain.material import normalize_fact_card_evidence
from app.services.rag.rag_orchestrator import hybrid_retrieve

logger = logging.getLogger(__name__)

# Pfad zur Knowledge Base (Verschoben aus graph.py für Zentralisierung)
_KB_DIR = os.getenv("RAG_KB_DIR", "app/data/kb")
_KB_FILENAME = "SEALAI_KB_PTFE_factcards_gates_v1_3.json"
_KB_PATH = Path(_KB_DIR) / _KB_FILENAME
_CARDS_CACHE: Optional[List["FactCard"]] = None
_SOURCES_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _load_sources(path: Path) -> Dict[str, Dict[str, Any]]:
    cache_key = str(path.resolve())
    if cache_key in _SOURCES_CACHE:
        return _SOURCES_CACHE[cache_key]
    if not path.exists():
        _SOURCES_CACHE[cache_key] = {}
        return _SOURCES_CACHE[cache_key]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        _SOURCES_CACHE[cache_key] = {}
        return _SOURCES_CACHE[cache_key]
    sources = data.get("sources") or {}
    _SOURCES_CACHE[cache_key] = sources if isinstance(sources, dict) else {}
    return _SOURCES_CACHE[cache_key]


def _enrich_card_payload(data: Dict[str, Any], sources: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    card = dict(data)
    metadata = dict(card.get("metadata") or {})
    source_id = card.get("source") or metadata.get("source")
    source_entry = sources.get(str(source_id), {}) if source_id else {}

    if source_id and not card.get("source_ref"):
        card["source_ref"] = source_id

    card_overrides = (
        ("type", "source_type"),
        ("rank", "source_rank"),
        ("title", "title"),
        ("url", "url"),
        ("edition", "edition"),
        ("revision_date", "revision_date"),
        ("published_at", "published_at"),
        ("edition_year", "edition_year"),
        ("document_revision", "document_revision"),
        ("manufacturer_name", "manufacturer_name"),
        ("product_line", "product_line"),
        ("grade_name", "grade_name"),
        ("material_family", "material_family"),
        ("evidence_scope", "evidence_scope"),
        ("scope_of_validity", "scope_of_validity"),
    )
    for source_key, target_key in card_overrides:
        if card.get(target_key) in (None, "") and source_entry.get(source_key) not in (None, ""):
            card[target_key] = source_entry.get(source_key)
        if metadata.get(target_key) in (None, "") and source_entry.get(source_key) not in (None, ""):
            metadata[target_key] = source_entry.get(source_key)

    additional_metadata = metadata.get("additional_metadata")
    if isinstance(additional_metadata, dict):
        for key in (
            "manufacturer_name",
            "product_line",
            "grade_name",
            "material_family",
            "revision_date",
            "published_at",
            "edition_year",
            "document_revision",
            "evidence_scope",
            "scope_of_validity",
        ):
            if additional_metadata.get(key) not in (None, "") and metadata.get(key) in (None, ""):
                metadata[key] = additional_metadata.get(key)

    if metadata.get("effective_date") not in (None, "") and metadata.get("published_at") in (None, ""):
        metadata["published_at"] = metadata.get("effective_date")
    if metadata.get("source_version") not in (None, "") and metadata.get("document_revision") in (None, ""):
        metadata["document_revision"] = metadata.get("source_version")

    card["metadata"] = metadata
    if source_entry:
        card["source_registry_entry"] = source_entry
    return card

class FactCard:
    """Repräsentiert eine technische Wissenseinheit (FactCard)."""
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.evidence_id = data.get("evidence_id") or data.get("id")
        self.source_ref = data.get("source_ref") or data.get("source")
        self.topic = data.get("topic", "")
        self.content = data.get("content", "")
        self.tags = data.get("topic_tags", []) or data.get("tags", [])
        self.retrieval_rank = data.get("retrieval_rank")
        self.retrieval_score = data.get("retrieval_score")
        self.metadata = data.get("metadata", {})
        self.normalized_evidence = normalize_fact_card_evidence(data)

def load_fact_cards(path: Path) -> List[FactCard]:
    """Lädt die Knowledge Base aus einer JSON-Datei."""
    if not path.exists():
        logger.warning(f"Knowledge Base nicht gefunden: {path}")
        return []
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            cards_data = data.get("factcards", [])
            sources = _load_sources(path)
            return [FactCard(_enrich_card_payload(c, sources)) for c in cards_data]
    except Exception as e:
        logger.error(f"Fehler beim Laden der FactCards: {e}")
        return []

def get_fact_cards_cached() -> List[FactCard]:
    """Lazy Loader für die Knowledge Base."""
    global _CARDS_CACHE
    if _CARDS_CACHE is None:
        _CARDS_CACHE = load_fact_cards(_KB_PATH)
    return _CARDS_CACHE

def retrieve_fact_cards_fallback(query: str, limit: int = 3) -> List[FactCard]:
    """
    Simuliert eine RAG-Suche (Phase D1).
    Sucht nach Übereinstimmungen in Topic, Content oder Tags.
    Verbessert: Prüft auf einzelne Wörter der Query (mind. 3 Zeichen oder Ziffern).
    """
    cards = get_fact_cards_cached()
    query_lower = query.lower()
    # Behalte Wörter ab 3 Zeichen ODER Wörter, die Ziffern enthalten (z.B. "10", "80")
    query_words = [w for w in query_lower.split() if len(w) >= 3 or any(c.isdigit() for c in w)]
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

async def retrieve_rag_context(query: str, tenant_id: Optional[str] = None, limit: int = 3) -> List[FactCard]:
    """
    Adapter für den echten RAG-Stack (Phase K19).
    Ruft hybrid_retrieve auf und mappt die Treffer in das FactCard-Format.
    Nutzt asyncio.to_thread für den synchronen hybrid_retrieve Aufruf.
    """
    try:
        # hybrid_retrieve ist synchron, daher in Thread auslagern
        hits = await asyncio.to_thread(
            hybrid_retrieve, 
            query=query, 
            tenant=tenant_id, 
            k=limit
        )
        
        if not hits:
            return []
            
        fact_cards = []
        for index, hit in enumerate(hits, start=1):
            meta = hit.get("metadata") or {}
            additional_metadata = meta.get("additional_metadata") or {}
            document_meta = hit.get("document_meta") or {}
            merged_metadata = dict(meta)
            if isinstance(additional_metadata, dict):
                for key, value in additional_metadata.items():
                    merged_metadata.setdefault(key, value)
            if isinstance(document_meta, dict):
                for key in (
                    "revision_date",
                    "published_at",
                    "edition_year",
                    "document_revision",
                    "scope_of_validity",
                    "evidence_scope",
                ):
                    if document_meta.get(key) not in (None, ""):
                        merged_metadata.setdefault(key, document_meta.get(key))
                if document_meta.get("version_id") not in (None, ""):
                    merged_metadata.setdefault("document_revision", str(document_meta.get("version_id")))
            if merged_metadata.get("effective_date") not in (None, ""):
                merged_metadata.setdefault("published_at", merged_metadata.get("effective_date"))
            if merged_metadata.get("source_version") not in (None, ""):
                merged_metadata.setdefault("document_revision", merged_metadata.get("source_version"))
            # Defensives Mapping
            topic = merged_metadata.get("topic") or merged_metadata.get("filename") or hit.get("source") or "RAG Context"
            content = hit.get("text") or ""
            tags = merged_metadata.get("topic_tags") or merged_metadata.get("tags") or []
            
            if content.strip():
                fact_cards.append(FactCard({
                    "id": hit.get("id") or meta.get("id") or meta.get("chunk_id") or f"rag_hit_{index}",
                    "evidence_id": hit.get("id") or meta.get("id") or meta.get("chunk_id") or f"rag_hit_{index}",
                    "source_ref": hit.get("source") or meta.get("filename") or topic,
                    "topic": topic,
                    "content": content,
                    "topic_tags": tags,
                    "retrieval_rank": index,
                    "retrieval_score": hit.get("score"),
                    "metadata": merged_metadata,
                }))
                
        return fact_cards
    except Exception as e:
        logger.error(f"Fehler bei Real-RAG Retrieval: {e}", exc_info=True)
        return []
