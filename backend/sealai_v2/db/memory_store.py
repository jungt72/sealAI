"""Memory store — sealingAI Memory Architecture V1.0, Patch 3 (API Basics' data-access layer).
In-process impl for CI/eval; Postgres for prod (build-spec §3 pattern, mirrors ``db/leads.py``).

P0: EVERY read/write is tenant-scoped — a store method takes ``tenant_id`` explicitly and filters on
it server-side; there is no method that returns cross-tenant data. This mirrors the ``memory/store.py``
Layer 1-4 discipline exactly.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import (
    V2MemoryEvent,
    V2MemoryItem,
    V2MemoryOutbox,
    V2MemorySource,
)
from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
    is_valid_transition,
)
from sealai_v2.security.tenant import TenantContext, require_tenant


class MemoryItemNotFound(LookupError):
    """No item with this id for this tenant — same error for "doesn't exist" and "belongs to
    another tenant" (P0: never reveal via a different error shape whether an id exists elsewhere)."""


class InvalidMemoryTransition(ValueError):
    """The requested status transition isn't legal from the item's current status
    (``memory.curated.is_valid_transition``) — the API layer maps this to HTTP 409."""


def _item_to_domain(row: V2MemoryItem, sources: tuple[MemorySource, ...]) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        tenant_id=row.tenant_id,
        scope=MemoryScope(row.scope),
        scope_id=row.scope_id,
        type=MemoryType(row.type),
        status=MemoryStatus(row.status),
        content=row.content,
        semantic_key=row.semantic_key,
        sources=sources,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        purge_after=row.purge_after,
    )


class MemoryStore(Protocol):
    def create_candidate(self, item: MemoryItem) -> MemoryItem: ...
    def list_items(
        self,
        *,
        tenant_id: str,
        scope: MemoryScope | None = None,
        status: MemoryStatus | None = None,
        project_id: str | None = None,
        case_id: str | None = None,
    ) -> tuple[MemoryItem, ...]: ...
    def summary(self, *, tenant_id: str) -> dict: ...
    def get_item(self, *, tenant_id: str, item_id: str) -> MemoryItem | None: ...
    def transition_status(
        self,
        *,
        tenant_id: str,
        item_id: str,
        to_status: MemoryStatus,
        actor: str,
        now: str,
        note: str = "",
    ) -> MemoryItem: ...


class InProcessMemoryStore:
    """CI/eval fallback (no DB) — mirrors ``InProcessLeadStore``'s shape."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    def create_candidate(self, item: MemoryItem) -> MemoryItem:
        require_tenant(TenantContext(item.tenant_id))
        self._items[item.id] = item
        return item

    def list_items(
        self,
        *,
        tenant_id: str,
        scope: MemoryScope | None = None,
        status: MemoryStatus | None = None,
        project_id: str | None = None,
        case_id: str | None = None,
    ) -> tuple[MemoryItem, ...]:
        require_tenant(TenantContext(tenant_id))
        out = [it for it in self._items.values() if it.tenant_id == tenant_id]
        if scope is not None:
            out = [it for it in out if it.scope == scope]
        if status is not None:
            out = [it for it in out if it.status == status]
        if project_id is not None:
            out = [
                it
                for it in out
                if it.scope == MemoryScope.PROJECT and it.scope_id == project_id
            ]
        if case_id is not None:
            out = [
                it
                for it in out
                if it.scope == MemoryScope.CASE and it.scope_id == case_id
            ]
        return tuple(out)

    def summary(self, *, tenant_id: str) -> dict:
        require_tenant(TenantContext(tenant_id))
        items = [it for it in self._items.values() if it.tenant_id == tenant_id]
        by_status: dict[str, int] = {}
        by_scope: dict[str, int] = {}
        for it in items:
            by_status[it.status.value] = by_status.get(it.status.value, 0) + 1
            by_scope[it.scope.value] = by_scope.get(it.scope.value, 0) + 1
        return {"total": len(items), "by_status": by_status, "by_scope": by_scope}

    def get_item(self, *, tenant_id: str, item_id: str) -> MemoryItem | None:
        require_tenant(TenantContext(tenant_id))
        item = self._items.get(item_id)
        if item is None or item.tenant_id != tenant_id:
            return None
        return item

    def transition_status(
        self,
        *,
        tenant_id: str,
        item_id: str,
        to_status: MemoryStatus,
        actor: str,
        now: str,
        note: str = "",
    ) -> MemoryItem:
        require_tenant(TenantContext(tenant_id))
        item = self.get_item(tenant_id=tenant_id, item_id=item_id)
        if item is None:
            raise MemoryItemNotFound(item_id)
        if not is_valid_transition(item.status, to_status):
            raise InvalidMemoryTransition(f"{item.status.value} -> {to_status.value}")
        updated = replace(
            item, status=to_status, updated_at=now, version=item.version + 1
        )
        self._items[item_id] = updated
        # events/outbox are Postgres-only observability here (no in-process audit trail needed for
        # CI/eval — the InProcess store's whole point is to be a hermetic behavior stand-in, not a
        # full audit-log implementation).
        return updated


class PostgresMemoryStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def create_candidate(self, item: MemoryItem) -> MemoryItem:
        require_tenant(TenantContext(item.tenant_id))
        with self._sf() as s:
            row = V2MemoryItem(
                id=item.id,
                tenant_id=item.tenant_id,
                scope=item.scope.value,
                scope_id=item.scope_id,
                # Read-path denormalization (Patch 2 design note): populated here at write time from
                # scope/scope_id, kept in sync by construction rather than a separate update step.
                project_id=item.scope_id if item.scope == MemoryScope.PROJECT else None,
                case_id=item.scope_id if item.scope == MemoryScope.CASE else None,
                type=item.type.value,
                status=item.status.value,
                content=item.content,
                semantic_key=item.semantic_key,
                version=item.version,
                created_at=item.created_at,
                updated_at=item.updated_at,
                deleted_at=item.deleted_at,
                purge_after=item.purge_after,
            )
            s.add(row)
            for src in item.sources:
                s.add(
                    V2MemorySource(
                        memory_item_id=item.id,
                        kind=src.kind,
                        session_id=src.session_id,
                        turn_id=src.turn_id,
                        note=src.note,
                        created_at=item.created_at,
                    )
                )
            # Patch 5 fix: a brand-new candidate must also reach Qdrant, not just later status
            # transitions (transition_status already enqueues on confirm/reject/deprecate/delete) —
            # even an unconfirmed candidate is surfaceable (e.g. implicit_context's clarifying-
            # question-only use, Patch 7), so it needs to be retrievable from the moment it exists.
            s.add(
                V2MemoryOutbox(
                    memory_item_id=item.id,
                    tenant_id=item.tenant_id,
                    operation="upsert",
                    created_at=item.created_at,
                )
            )
            s.commit()
            return item

    def _sources_for(self, s, memory_item_id: str) -> tuple[MemorySource, ...]:
        rows = s.scalars(
            select(V2MemorySource).where(
                V2MemorySource.memory_item_id == memory_item_id
            )
        ).all()
        return tuple(
            MemorySource(
                kind=r.kind, session_id=r.session_id, turn_id=r.turn_id, note=r.note
            )
            for r in rows
        )

    def list_items(
        self,
        *,
        tenant_id: str,
        scope: MemoryScope | None = None,
        status: MemoryStatus | None = None,
        project_id: str | None = None,
        case_id: str | None = None,
    ) -> tuple[MemoryItem, ...]:
        require_tenant(TenantContext(tenant_id))
        with self._sf() as s:
            q = select(V2MemoryItem).where(V2MemoryItem.tenant_id == tenant_id)
            if scope is not None:
                q = q.where(V2MemoryItem.scope == scope.value)
            if status is not None:
                q = q.where(V2MemoryItem.status == status.value)
            if project_id is not None:
                q = q.where(V2MemoryItem.project_id == project_id)
            if case_id is not None:
                q = q.where(V2MemoryItem.case_id == case_id)
            rows = s.scalars(q.order_by(V2MemoryItem.updated_at.desc())).all()
            return tuple(_item_to_domain(r, self._sources_for(s, r.id)) for r in rows)

    def summary(self, *, tenant_id: str) -> dict:
        require_tenant(TenantContext(tenant_id))
        with self._sf() as s:
            status_rows = s.execute(
                select(V2MemoryItem.status, func.count())
                .where(V2MemoryItem.tenant_id == tenant_id)
                .group_by(V2MemoryItem.status)
            ).all()
            scope_rows = s.execute(
                select(V2MemoryItem.scope, func.count())
                .where(V2MemoryItem.tenant_id == tenant_id)
                .group_by(V2MemoryItem.scope)
            ).all()
            by_status = {status: count for status, count in status_rows}
            by_scope = {scope: count for scope, count in scope_rows}
            return {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "by_scope": by_scope,
            }

    def get_item(self, *, tenant_id: str, item_id: str) -> MemoryItem | None:
        require_tenant(TenantContext(tenant_id))
        with self._sf() as s:
            row = s.get(V2MemoryItem, item_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return _item_to_domain(row, self._sources_for(s, row.id))

    def transition_status(
        self,
        *,
        tenant_id: str,
        item_id: str,
        to_status: MemoryStatus,
        actor: str,
        now: str,
        note: str = "",
    ) -> MemoryItem:
        require_tenant(TenantContext(tenant_id))
        # ONE transaction: the row update, the audit event, and the outbox enqueue all commit
        # together or not at all — a crash between them can't leave the outbox silently un-notified
        # of a real status change (the exact failure mode an outbox pattern exists to prevent).
        with self._sf() as s:
            row = s.get(V2MemoryItem, item_id)
            if row is None or row.tenant_id != tenant_id:
                raise MemoryItemNotFound(item_id)
            from_status = MemoryStatus(row.status)
            if not is_valid_transition(from_status, to_status):
                raise InvalidMemoryTransition(
                    f"{from_status.value} -> {to_status.value}"
                )
            row.status = to_status.value
            row.updated_at = now
            row.version += 1
            s.add(
                V2MemoryEvent(
                    memory_item_id=item_id,
                    tenant_id=tenant_id,
                    event_type=to_status.value,
                    from_status=from_status.value,
                    to_status=to_status.value,
                    actor=actor,
                    note=note,
                    created_at=now,
                )
            )
            s.add(
                V2MemoryOutbox(
                    memory_item_id=item_id,
                    tenant_id=tenant_id,
                    operation="upsert",  # the Postgres row persists with a new status; a physical
                    # Qdrant point removal is Patch 14's purge job, not a status transition.
                    created_at=now,
                )
            )
            s.commit()
            return _item_to_domain(row, self._sources_for(s, row.id))


def build_memory_store(settings) -> MemoryStore:
    """The Postgres memory store (durable, cross-session) when ``database_url`` is set, else the
    in-process store (eval/CI hermetic). Fail-safe: a missing dep / unreachable DB falls back to
    in-process rather than crashing the API — mirrors ``build_lead_store``."""
    if getattr(settings, "database_url", None):
        try:
            from sealai_v2.db.engine import make_engine, make_sessionmaker

            return PostgresMemoryStore(
                make_sessionmaker(make_engine(settings.database_url))
            )
        except Exception:  # noqa: BLE001 — fail safe to in-process; never crash on startup
            pass
    return InProcessMemoryStore()
