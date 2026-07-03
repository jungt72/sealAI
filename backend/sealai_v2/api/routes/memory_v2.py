"""/api/v2/memory — sealingAI Memory Architecture V1.0, Patch 3 (API Basics).

Every op derives ``tenant_id`` ONLY from the verified token (P0, same discipline as
``conversations.py``) — a tenant's token can never read or write another tenant's memory.
``project_id``/``case_id`` ARE accepted as client-supplied query/body params: they only NARROW an
already tenant-scoped query, never widen it or bypass the tenant boundary (there is no scope claim
in the token for project/case yet — the caller, e.g. the dashboard's current case context, supplies
it; the hard isolation boundary stays server-derived tenant_id).

This is the CURATED memory tier (distinct from ``/api/v2/conversations/current/memory``, which is
the existing Layer 1-3 session working-window/case-state — untouched by this patch).

Status-action endpoints (Patch 4: confirm/reject/deprecate/delete) live here too — each writes a
``memory_events`` row (audit trail) and enqueues a ``memory_outbox`` row (Qdrant sync) atomically
with the status change, and is rejected (409) if the transition isn't legal from the item's current
status (``memory.curated.is_valid_transition`` — e.g. a REJECTED item can't be re-confirmed).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import current_identity, get_settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.memory_store import (
    InvalidMemoryTransition,
    MemoryItemNotFound,
    MemoryStore,
    build_memory_store,
)
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)

router = APIRouter(prefix="/api/v2/memory", tags=["memory-v2"])


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryStore:
    # Cached (mirrors deps.get_lead_store/get_partner_registry): the in-process fallback holds
    # state in-memory, so an uncached factory would silently reset it on every single request.
    return build_memory_store(get_settings())


def _item_dict(item: MemoryItem) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "scope": item.scope.value,
        "scope_id": item.scope_id,
        "type": item.type.value,
        "status": item.status.value,
        "content": item.content,
        "semantic_key": item.semantic_key,
        "sources": [
            {
                "kind": s.kind,
                "session_id": s.session_id,
                "turn_id": s.turn_id,
                "note": s.note,
            }
            for s in item.sources
        ],
        "version": item.version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "deleted_at": item.deleted_at,
        "purge_after": item.purge_after,
    }


@router.get("/summary")
def summary(
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    return store.summary(tenant_id=identity.tenant_id)


@router.get("/items")
def list_items(
    scope: MemoryScope | None = None,
    status: MemoryStatus | None = None,
    project_id: str | None = None,
    case_id: str | None = None,
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    items = store.list_items(
        tenant_id=identity.tenant_id,
        scope=scope,
        status=status,
        project_id=project_id,
        case_id=case_id,
    )
    return {"items": [_item_dict(it) for it in items]}


class MemorySourceIn(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    session_id: str | None = None
    turn_id: str | None = None
    note: str = ""


class MemoryCandidateCreate(BaseModel):
    """Doctrine: "keine Memory-Schreibvorgänge ohne Source/Provenance" — ``sources`` is required and
    non-empty (enforced below, not by a pydantic min_length on the list, so the error message is
    explicit about WHY rather than a generic length-validation message)."""

    scope: MemoryScope
    scope_id: str = Field(min_length=1, max_length=255)
    type: MemoryType
    content: str = Field(min_length=1)
    semantic_key: str = Field(min_length=1, max_length=512)
    sources: list[MemorySourceIn] = Field(default_factory=list)


@router.post("/candidates", status_code=201)
def create_candidate(
    body: MemoryCandidateCreate,
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    if not body.sources:
        raise HTTPException(
            status_code=422,
            detail="at least one source is required (keine Memory-Schreibvorgänge ohne Source/Provenance)",
        )
    now = datetime.now(timezone.utc).isoformat()
    item = MemoryItem(
        id=str(uuid.uuid4()),
        tenant_id=identity.tenant_id,
        scope=body.scope,
        scope_id=body.scope_id,
        type=body.type,
        status=MemoryStatus.CANDIDATE,
        content=body.content,
        semantic_key=body.semantic_key,
        sources=tuple(
            MemorySource(
                kind=s.kind, session_id=s.session_id, turn_id=s.turn_id, note=s.note
            )
            for s in body.sources
        ),
        created_at=now,
        updated_at=now,
    )
    created = store.create_candidate(item)
    return _item_dict(created)


class MemoryTransitionRequest(BaseModel):
    note: str = ""


def _transition(
    item_id: str,
    to_status: MemoryStatus,
    body: MemoryTransitionRequest,
    identity: VerifiedIdentity,
    store: MemoryStore,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    try:
        updated = store.transition_status(
            tenant_id=identity.tenant_id,
            item_id=item_id,
            to_status=to_status,
            actor=identity.subject,
            now=now,
            note=body.note,
        )
    except MemoryItemNotFound:
        raise HTTPException(status_code=404, detail="memory item not found") from None
    except InvalidMemoryTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _item_dict(updated)


@router.post("/items/{item_id}/confirm")
def confirm_item(
    item_id: str,
    body: MemoryTransitionRequest = MemoryTransitionRequest(),
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    return _transition(item_id, MemoryStatus.CONFIRMED, body, identity, store)


@router.post("/items/{item_id}/reject")
def reject_item(
    item_id: str,
    body: MemoryTransitionRequest = MemoryTransitionRequest(),
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    return _transition(item_id, MemoryStatus.REJECTED, body, identity, store)


@router.post("/items/{item_id}/deprecate")
def deprecate_item(
    item_id: str,
    body: MemoryTransitionRequest = MemoryTransitionRequest(),
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    return _transition(item_id, MemoryStatus.DEPRECATED, body, identity, store)


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: str,
    body: MemoryTransitionRequest = MemoryTransitionRequest(),
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    return _transition(
        item_id, MemoryStatus.DELETED_PENDING_PURGE, body, identity, store
    )
