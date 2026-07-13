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

Patch 9c reconciliation (against "sealingAI Memory Architecture V1.0 — Finales Konzept", §12): adds
``GET /items/{id}`` and a proper ``DELETE /items/{id}`` verb (additive — the existing
``POST .../delete`` stays, since nothing has ever depended on only one of the two existing), plus an
admin-gated ``GET /outbox-health`` wrapping the already-built ``outbox_worker.outbox_health()``.
Deliberately NOT built here: ``GET /context-sources?message_id=...`` — the final doc's §11 Right Rail
wants to look up which memory items were used for a SPECIFIC PAST turn, but nothing today persists a
message_id -> memory_context mapping (Patch 8's ``MemoryContextBundle`` is computed per-request and
returned inline in that same response, never stored keyed by message_id). Building this endpoint
would mean inventing a new persistence decision, not reconciling existing code against the spec —
left for the Patch 10/11 UX work that will actually consume it, where that design choice belongs.

Patch 10 (Purge & Compliance): both delete routes now compute a ``purge_after`` (now +
``settings.memory_purge_grace_days``) and pass it into ``transition_status`` — giving
``memory/purge.py``'s periodic reap job a concrete eligibility timestamp instead of a
``deleted_pending_purge`` item that would otherwise sit forever with no purge schedule at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import current_identity, get_settings, require_admin
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


@lru_cache(maxsize=1)
def get_memory_outbox_session_factory():
    """A separate DB-session-factory accessor for the outbox-health admin endpoint (Patch 9c) —
    distinct from ``get_memory_store()`` because only the Postgres path has an outbox to report on;
    ``None`` when no ``database_url`` is configured (in-process/eval mode has no outbox at all),
    which the route below turns into an empty-but-valid health payload rather than a 500."""
    settings = get_settings()
    if not getattr(settings, "database_url", None):
        return None
    try:
        from sealai_v2.db.engine import make_engine, make_sessionmaker

        return make_sessionmaker(make_engine(settings.database_url))
    except Exception:  # noqa: BLE001 — fail safe; never crash the endpoint on startup
        return None


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
                "source_ref": s.source_ref,
                "message_id": s.message_id,
                "document_id": s.document_id,
                "case_snapshot_id": s.case_snapshot_id,
            }
            for s in item.sources
        ],
        "version": item.version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "deleted_at": item.deleted_at,
        "purge_after": item.purge_after,
        "confidence": item.confidence,
        "sensitivity": item.sensitivity,
        "subject_hash": item.subject_hash,
        "supersedes_memory_id": item.supersedes_memory_id,
        "deprecated_by_memory_id": item.deprecated_by_memory_id,
    }


@router.get("/summary")
def summary(
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    return store.summary(tenant_id=identity.tenant_id, owner_subject=identity.subject)


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
        owner_subject=identity.subject,
    )
    return {"items": [_item_dict(it) for it in items]}


@router.get("/items/{item_id}")
def get_item(
    item_id: str,
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    item = store.get_item(
        tenant_id=identity.tenant_id,
        item_id=item_id,
        owner_subject=identity.subject,
    )
    if item is None:
        # Same 404 whether the id doesn't exist or belongs to another tenant (P0 — see
        # test_status_action_never_leaks_existence_across_tenants for the established precedent).
        raise HTTPException(status_code=404, detail="memory item not found")
    return _item_dict(item)


class MemorySourceIn(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    session_id: str | None = None
    turn_id: str | None = None
    note: str = ""
    source_ref: str | None = None
    message_id: str | None = None
    document_id: str | None = None
    case_snapshot_id: str | None = None


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
                kind=s.kind,
                session_id=s.session_id,
                turn_id=s.turn_id,
                note=s.note,
                source_ref=s.source_ref,
                message_id=s.message_id,
                document_id=s.document_id,
                case_snapshot_id=s.case_snapshot_id,
            )
            for s in body.sources
        ),
        owner_subject=identity.subject,
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
    *,
    purge_after: str | None = None,
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
            purge_after=purge_after,
            owner_subject=identity.subject,
        )
    except MemoryItemNotFound:
        raise HTTPException(status_code=404, detail="memory item not found") from None
    except InvalidMemoryTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _item_dict(updated)


def _purge_after_now() -> str:
    """Patch 10: the grace-period eligibility timestamp for a DELETED_PENDING_PURGE transition —
    computed here (the API layer), never inside the store, matching this codebase's "now/derived
    timestamps are always caller-supplied" discipline."""
    grace_days = get_settings().memory_purge_grace_days
    return (datetime.now(timezone.utc) + timedelta(days=grace_days)).isoformat()


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
        item_id,
        MemoryStatus.DELETED_PENDING_PURGE,
        body,
        identity,
        store,
        purge_after=_purge_after_now(),
    )


@router.delete("/items/{item_id}")
def delete_item_verb(
    item_id: str,
    identity: VerifiedIdentity = Depends(current_identity),
    store: MemoryStore = Depends(get_memory_store),
) -> dict:
    """The final concept doc's §12 literal ``DELETE /items/{id}`` verb — additive alongside
    ``POST .../delete`` above (same soft-delete transition, no request body needed for a DELETE)."""
    return _transition(
        item_id,
        MemoryStatus.DELETED_PENDING_PURGE,
        MemoryTransitionRequest(),
        identity,
        store,
        purge_after=_purge_after_now(),
    )


@router.get("/outbox-health")
def outbox_health_endpoint(
    _identity: VerifiedIdentity = Depends(require_admin),
) -> dict:
    """Admin-only (Patch 9c): wraps the already-built ``outbox_worker.outbox_health()``. Global
    across all tenants by design — this is Qdrant-sync-pipeline observability, not user data."""
    from sealai_v2.memory.outbox_worker import outbox_health

    session_factory = get_memory_outbox_session_factory()
    if session_factory is None:
        return {"total": 0, "by_status": {}, "oldest_pending_outbox_id": None}
    return outbox_health(session_factory)
