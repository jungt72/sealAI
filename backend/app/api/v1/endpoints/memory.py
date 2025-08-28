# backend/app/api/v1/endpoints/memory.py
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient, models as qmodels

from app.core.config import settings
from app.services.auth.dependencies import get_current_request_user
from app.services.memory.memory_core import (
    ltm_export_all,
    ltm_delete_all,
    ensure_ltm_collection,
    _get_qdrant_client,
)

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


def _ltm_collection() -> str:
    """Resolve the Qdrant collection name for LTM (Long-Term-Memory)."""
    return (settings.qdrant_collection_ltm or f"{settings.qdrant_collection}-ltm").strip()


# ----------------------------------------------------------------------
# Create Memory Item
# ----------------------------------------------------------------------
@router.post("", summary="Lege einen LTM-Eintrag in Qdrant an")
async def create_memory_item(
    payload: Dict[str, Any],
    username: str = Depends(get_current_request_user),
) -> JSONResponse:
    """
    Erwartet JSON:
    {
      "text": "…Pflicht…",
      "kind": "note|preference|fact|…",
      "chat_id": "optional"
    }
    """
    if not settings.ltm_enable:
        return JSONResponse({"ltm_enabled": False}, status_code=200)

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Field 'text' is required and must be non-empty")

    kind = (payload.get("kind") or "note").strip()
    chat_id = (payload.get("chat_id") or None) or None

    point_id = uuid.uuid4().hex
    q_payload: Dict[str, Any] = {
        "user": username,  # WICHTIG: Schlüssel = 'user' (wird für Filter verwendet!)
        "chat_id": chat_id,
        "kind": kind,
        "text": text,
        "created_at": time.time(),
    }
    # Zusatzfelder übernehmen (ohne Pflichtfelder zu überschreiben)
    for k, v in payload.items():
        if k not in q_payload:
            q_payload[k] = v

    try:
        client: QdrantClient = _get_qdrant_client()
        ensure_ltm_collection(client)

        # Dummy-Vektor, da nur Payload benötigt wird
        client.upsert(
            collection_name=_ltm_collection(),
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=[0.0],
                    payload=q_payload,
                )
            ],
            wait=True,
        )

        logger.info(f"[LTM] create_memory_item user={username} chat_id={chat_id} id={point_id}")
        return JSONResponse(
            {"id": point_id, "ltm_enabled": True, "success": True},
            status_code=200,
        )

    except Exception as exc:
        logger.exception(f"[LTM] Fehler beim Speichern für user={username}, chat_id={chat_id}: {exc}")
        raise HTTPException(status_code=500, detail="Speichern fehlgeschlagen") from exc


# ----------------------------------------------------------------------
# Export Memory Items
# ----------------------------------------------------------------------
@router.get("/export", summary="Exportiere Long-Term-Memory (Qdrant) des aktuellen Nutzers")
async def export_memory(
    chat_id: Optional[str] = Query(default=None, description="Optional: nur Einträge dieses Chats exportieren"),
    limit: int = Query(default=10000, ge=1, le=20000),
    username: str = Depends(get_current_request_user),
) -> JSONResponse:
    if not settings.ltm_enable:
        return JSONResponse({"items": [], "count": 0, "ltm_enabled": False}, status_code=200)

    try:
        items: List[Dict[str, Any]] = ltm_export_all(user=username, chat_id=chat_id, limit=limit)
        logger.info(f"[LTM] export_memory user={username} chat_id={chat_id} count={len(items)}")
        return JSONResponse(
            {"items": items, "count": len(items), "ltm_enabled": True, "success": True},
            status_code=200,
        )
    except Exception as exc:
        logger.exception(f"[LTM] Fehler beim Export für user={username}, chat_id={chat_id}: {exc}")
        raise HTTPException(status_code=500, detail="Export fehlgeschlagen") from exc


# ----------------------------------------------------------------------
# Delete Memory Items
# ----------------------------------------------------------------------
@router.delete("", summary="Lösche Long-Term-Memory des aktuellen Nutzers (optional pro Chat)")
async def delete_memory(
    chat_id: Optional[str] = Query(default=None, description="Optional: nur Einträge dieses Chats löschen"),
    username: str = Depends(get_current_request_user),
) -> JSONResponse:
    if not settings.ltm_enable:
        return JSONResponse({"deleted": 0, "ltm_enabled": False}, status_code=200)

    try:
        deleted = ltm_delete_all(user=username, chat_id=chat_id)
        logger.info(f"[LTM] delete_memory user={username} chat_id={chat_id} deleted={deleted}")
        return JSONResponse(
            {"deleted": deleted, "ltm_enabled": True, "success": True},
            status_code=200,
        )
    except Exception as exc:
        logger.exception(f"[LTM] Fehler beim Löschen für user={username}, chat_id={chat_id}: {exc}")
        raise HTTPException(status_code=500, detail="Löschen fehlgeschlagen") from exc
