"""
Memory Core: Kapselt Long-Term-Memory (Qdrant) für Export/Löschen.
Kurz-/Mittelzeit (Redis/Summary) laufen separat über LangGraph-Checkpointer.

Payload-Felder pro Eintrag:
- user: str                  (Pflicht für Filterung pro Benutzer)
- chat_id: str               (optional; für Export/Löschen pro Chat)
- kind: str                  (z. B. "preference", "fact", "note", …)
- text: str                  (Inhalt)
- created_at: float|int|str  (optional: Unix-Zeit oder ISO)
Weitere Felder erlaubt – werden unverändert mit exportiert.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import FilterSelector

from app.core.config import settings


# ---------------------------------------------------------------------------
# Qdrant Client & Collection
# ---------------------------------------------------------------------------

def _get_qdrant_client() -> QdrantClient:
    kwargs = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


def _ltm_collection_name() -> str:
    """
    Eigene LTM-Collection verwenden, um keine Vektorgrößen-Konflikte mit der
    RAG-Collection zu riskieren. Fallback: "<qdrant_collection>-ltm".
    """
    return (settings.qdrant_collection_ltm or f"{settings.qdrant_collection}-ltm").strip()


def ensure_ltm_collection(client: QdrantClient) -> None:
    """
    Stellt sicher, dass die LTM-Collection existiert. Wir verwenden einen
    Dummy-Vektor (size=1), da wir nur Payload-basierte Scroll/Filter-Operationen
    benötigen. (Qdrant verlangt einen Vektorspace pro Collection.)
    """
    coll = _ltm_collection_name()
    try:
        client.get_collection(coll)
    except Exception:
        client.recreate_collection(
            collection_name=coll,
            vectors_config=models.VectorParams(size=1, distance=models.Distance.COSINE),
        )


# ---------------------------------------------------------------------------
# Export / Delete
# ---------------------------------------------------------------------------

def _build_user_filter(user: str, chat_id: Optional[str] = None) -> models.Filter:
    must: List[models.FieldCondition] = [
        models.FieldCondition(key="user", match=models.MatchValue(value=user))
    ]
    if chat_id:
        must.append(models.FieldCondition(key="chat_id", match=models.MatchValue(value=chat_id)))
    return models.Filter(must=must)


def ltm_export_all(
    user: str,
    chat_id: Optional[str] = None,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    """
    Exportiert bis zu `limit` LTM-Items für den User (optional gefiltert nach chat_id).
    Liefert Liste aus {id, payload}.
    """
    if not settings.ltm_enable:
        return []

    client = _get_qdrant_client()
    ensure_ltm_collection(client)

    flt = _build_user_filter(user, chat_id)
    out: List[Dict[str, Any]] = []

    next_page = None
    fetched = 0
    page_size = 512
    coll = _ltm_collection_name()

    while fetched < limit:
        points, next_page = client.scroll(
            collection_name=coll,
            scroll_filter=flt,
            with_payload=True,
            with_vectors=False,
            limit=min(page_size, limit - fetched),
            offset=next_page,
        )
        if not points:
            break
        for p in points:
            out.append({
                "id": str(p.id),
                "payload": dict(p.payload or {}),
            })
        fetched += len(points)
        if next_page is None:
            break

    return out


def ltm_delete_all(
    user: str,
    chat_id: Optional[str] = None,
) -> int:
    """
    Löscht alle LTM-Items für User (optional gefiltert nach chat_id).
    Gibt die Anzahl der gelöschten Punkte (approx.) zurück.
    """
    if not settings.ltm_enable:
        return 0

    client = _get_qdrant_client()
    ensure_ltm_collection(client)

    flt = _build_user_filter(user, chat_id)
    coll = _ltm_collection_name()

    # Vorab zählen (für Response)
    to_delete = 0
    next_page = None
    while True:
        points, next_page = client.scroll(
            collection_name=coll,
            scroll_filter=flt,
            with_payload=False,
            with_vectors=False,
            limit=1024,
            offset=next_page,
        )
        if not points:
            break
        to_delete += len(points)
        if next_page is None:
            break

    # Delete via Filter (serverseitig)
    client.delete(
        collection_name=coll,
        points_selector=FilterSelector(filter=flt),
        wait=True,
    )
    return to_delete
