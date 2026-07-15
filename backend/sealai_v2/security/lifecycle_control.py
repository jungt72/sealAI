"""Fail-closed API lifecycle admission, quotas, concurrency, and idempotency.

Production construction accepts only the transaction-scoped PostgreSQL session factory. Rate,
daily, storage, and active-lease decisions are serialized by a fixed PostgreSQL transaction lock.
Storage reservations are deliberately non-refundable: a failed downstream write can reduce future
capacity but can never let repeated failures exceed the configured storage ceiling.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import func, select, text

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.models import V2ApiLifecycleAdmission, V2ApiLifecycleWindow

_POSTGRES_ADVISORY_LOCK_ID = 7_214_407_061_401_002
_ACTION_GROUPS = {
    "contribution.create": "content_create",
    "lead.create": "content_create",
    "contribution.withdraw": "lifecycle_transition",
    "lead.cancel": "lifecycle_transition",
}


class LifecycleControlUnavailable(RuntimeError):
    """The shared lifecycle authority could not prove admission."""


def canonical_request_digest(payload: Any) -> str:
    """Hash a canonical JSON-compatible request without retaining its content in quota tables."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def lifecycle_scope_ref(kind: str, value: str) -> str:
    if kind not in {"tenant", "actor"}:
        raise ValueError("invalid lifecycle scope kind")
    return sha256(f"sealai-api-lifecycle-{kind}-v1\x00{value}".encode()).hexdigest()


def identity_scope_refs(identity: VerifiedIdentity) -> tuple[str, str]:
    tenant_ref = lifecycle_scope_ref("tenant", identity.tenant_id)
    actor_ref = lifecycle_scope_ref(
        "actor", f"{identity.tenant_id}\x00{identity.subject}"
    )
    return tenant_ref, actor_ref


def idempotency_key_hash(action: str, key: str) -> str:
    return sha256(
        f"sealai-api-idempotency-v1\x00{action}\x00{key}".encode()
    ).hexdigest()


def _iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _buckets(now: datetime) -> dict[str, str]:
    utc = now.astimezone(timezone.utc)
    return {
        "minute": _iso(utc.replace(second=0, microsecond=0)),
        "day": utc.strftime("%Y-%m-%d"),
        "lifetime": "all",
    }


def _retry_after(now: datetime, window: str, *, lease_s: int) -> int | None:
    utc = now.astimezone(timezone.utc)
    if window == "minute":
        end = utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
    elif window == "day":
        end = utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    elif window == "lease":
        return lease_s
    else:
        return None
    return max(1, int((end - utc).total_seconds()))


@dataclass(frozen=True)
class LifecyclePolicy:
    actor_per_minute: int
    tenant_per_minute: int
    actor_per_day: int
    tenant_per_day: int
    actor_storage_bytes: int
    tenant_storage_bytes: int
    actor_max_concurrent: int
    tenant_max_concurrent: int
    lease_s: int

    @classmethod
    def from_settings(cls, settings) -> "LifecyclePolicy":
        return cls(
            actor_per_minute=settings.api_lifecycle_actor_requests_per_minute,
            tenant_per_minute=settings.api_lifecycle_tenant_requests_per_minute,
            actor_per_day=settings.api_lifecycle_actor_requests_per_day,
            tenant_per_day=settings.api_lifecycle_tenant_requests_per_day,
            actor_storage_bytes=settings.api_lifecycle_actor_storage_bytes,
            tenant_storage_bytes=settings.api_lifecycle_tenant_storage_bytes,
            actor_max_concurrent=settings.api_lifecycle_actor_max_concurrent,
            tenant_max_concurrent=settings.api_lifecycle_tenant_max_concurrent,
            lease_s=settings.api_lifecycle_request_lease_s,
        )


@dataclass(frozen=True)
class LifecycleAdmission:
    request_id: str
    tenant_ref: str
    actor_ref: str
    estimated_bytes: int
    completion_token: str
    replay: bool = False
    resource_type: str | None = None
    resource_id: str | None = None


@dataclass(frozen=True)
class LifecycleDecision:
    admission: LifecycleAdmission | None
    reason: str | None = None
    status_code: int = 429
    retry_after_s: int | None = None

    @property
    def allowed(self) -> bool:
        return self.admission is not None


class LifecycleControlStore(Protocol):
    def admit(
        self,
        identity: VerifiedIdentity,
        policy: LifecyclePolicy,
        *,
        action: str,
        idempotency_key: str,
        request_digest: str,
        estimated_bytes: int,
        now: datetime | None = None,
    ) -> LifecycleDecision: ...

    def complete(
        self,
        request_id: str,
        *,
        completion_token: str,
        outcome: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        now: datetime | None = None,
    ) -> None: ...


def _denial(
    *,
    policy: LifecyclePolicy,
    counts: dict[str, int],
    actor_active: int,
    tenant_active: int,
    estimated_bytes: int,
) -> tuple[str, int, str] | None:
    checks = (
        (
            counts["actor_minute"] >= policy.actor_per_minute,
            "actor_rate",
            429,
            "minute",
        ),
        (
            counts["tenant_minute"] >= policy.tenant_per_minute,
            "tenant_rate",
            429,
            "minute",
        ),
        (
            counts["actor_day"] >= policy.actor_per_day,
            "actor_daily_quota",
            429,
            "day",
        ),
        (
            counts["tenant_day"] >= policy.tenant_per_day,
            "tenant_daily_quota",
            429,
            "day",
        ),
        (
            counts["actor_storage"] + estimated_bytes > policy.actor_storage_bytes,
            "actor_storage_quota",
            507,
            "lifetime",
        ),
        (
            counts["tenant_storage"] + estimated_bytes > policy.tenant_storage_bytes,
            "tenant_storage_quota",
            507,
            "lifetime",
        ),
        (
            actor_active >= policy.actor_max_concurrent,
            "actor_concurrency",
            429,
            "lease",
        ),
        (
            tenant_active >= policy.tenant_max_concurrent,
            "tenant_concurrency",
            429,
            "lease",
        ),
    )
    for denied, reason, status, window in checks:
        if denied:
            return reason, status, window
    return None


class PostgresLifecycleControlStore:
    """Shared multi-worker lifecycle authority; no production in-memory fallback exists."""

    def __init__(self, session_factory) -> None:
        self._sessions = session_factory
        self._local_lock = threading.Lock()

    @staticmethod
    def _window(
        session,
        group: str,
        kind: str,
        ref: str,
        window: str,
        start: str,
        now_s: str,
    ):
        key = (group, kind, ref, window, start)
        row = session.get(V2ApiLifecycleWindow, key)
        if row is None:
            row = V2ApiLifecycleWindow(
                quota_group=group,
                scope_kind=kind,
                scope_ref=ref,
                window_kind=window,
                window_start=start,
                admitted_count=0,
                denied_count=0,
                reserved_bytes=0,
                updated_at=now_s,
            )
            session.add(row)
            session.flush()
        return row

    def admit(
        self,
        identity: VerifiedIdentity,
        policy: LifecyclePolicy,
        *,
        action: str,
        idempotency_key: str,
        request_digest: str,
        estimated_bytes: int,
        now: datetime | None = None,
    ) -> LifecycleDecision:
        try:
            group = _ACTION_GROUPS[action]
        except KeyError as exc:
            raise ValueError("unsupported lifecycle action") from exc
        if estimated_bytes < 0:
            raise ValueError("estimated lifecycle bytes must be non-negative")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_s = _iso(current)
        buckets = _buckets(current)
        tenant_ref, actor_ref = identity_scope_refs(identity)
        key_hash = idempotency_key_hash(action, idempotency_key)

        with self._local_lock, self._sessions() as session, session.begin():
            if session.get_bind().dialect.name != "postgresql":
                raise LifecycleControlUnavailable(
                    "API lifecycle authority requires PostgreSQL"
                )
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": _POSTGRES_ADVISORY_LOCK_ID},
            )
            existing = session.scalar(
                select(V2ApiLifecycleAdmission).where(
                    V2ApiLifecycleAdmission.action == action,
                    V2ApiLifecycleAdmission.tenant_ref == tenant_ref,
                    V2ApiLifecycleAdmission.actor_ref == actor_ref,
                    V2ApiLifecycleAdmission.idempotency_key_hash == key_hash,
                )
            )
            if existing is not None:
                if existing.request_digest != request_digest:
                    return LifecycleDecision(None, "idempotency_conflict", 409)
                if (
                    existing.outcome == "success"
                    and existing.resource_type
                    and existing.resource_id
                ):
                    return LifecycleDecision(
                        LifecycleAdmission(
                            request_id=existing.request_id,
                            tenant_ref=tenant_ref,
                            actor_ref=actor_ref,
                            estimated_bytes=existing.estimated_bytes,
                            completion_token=existing.started_at,
                            replay=True,
                            resource_type=existing.resource_type,
                            resource_id=existing.resource_id,
                        )
                    )
                if existing.outcome == "active" and existing.expires_at > now_s:
                    return LifecycleDecision(
                        None,
                        "idempotency_in_progress",
                        409,
                        policy.lease_s,
                    )
                if existing.outcome == "active":
                    # Recover an interrupted downstream write after its lease expires. Quota and
                    # storage reservations were already charged; reusing this admission cannot
                    # widen capacity. Resource stores key their write by this request id.
                    existing.started_at = now_s
                    existing.expires_at = _iso(
                        current + timedelta(seconds=policy.lease_s)
                    )
                    return LifecycleDecision(
                        LifecycleAdmission(
                            request_id=existing.request_id,
                            tenant_ref=tenant_ref,
                            actor_ref=actor_ref,
                            estimated_bytes=existing.estimated_bytes,
                            completion_token=now_s,
                        )
                    )
                return LifecycleDecision(None, "idempotency_finalized", 409)

            rows = {
                "actor_minute": self._window(
                    session,
                    group,
                    "actor",
                    actor_ref,
                    "minute",
                    buckets["minute"],
                    now_s,
                ),
                "tenant_minute": self._window(
                    session,
                    group,
                    "tenant",
                    tenant_ref,
                    "minute",
                    buckets["minute"],
                    now_s,
                ),
                "actor_day": self._window(
                    session,
                    group,
                    "actor",
                    actor_ref,
                    "day",
                    buckets["day"],
                    now_s,
                ),
                "tenant_day": self._window(
                    session,
                    group,
                    "tenant",
                    tenant_ref,
                    "day",
                    buckets["day"],
                    now_s,
                ),
                "actor_lifetime": self._window(
                    session,
                    group,
                    "actor",
                    actor_ref,
                    "lifetime",
                    buckets["lifetime"],
                    now_s,
                ),
                "tenant_lifetime": self._window(
                    session,
                    group,
                    "tenant",
                    tenant_ref,
                    "lifetime",
                    buckets["lifetime"],
                    now_s,
                ),
            }
            active_filter = (
                V2ApiLifecycleAdmission.released_at.is_(None),
                V2ApiLifecycleAdmission.expires_at > now_s,
            )
            actor_active = int(
                session.scalar(
                    select(func.count())
                    .select_from(V2ApiLifecycleAdmission)
                    .where(
                        V2ApiLifecycleAdmission.actor_ref == actor_ref,
                        *active_filter,
                    )
                )
                or 0
            )
            tenant_active = int(
                session.scalar(
                    select(func.count())
                    .select_from(V2ApiLifecycleAdmission)
                    .where(
                        V2ApiLifecycleAdmission.tenant_ref == tenant_ref,
                        *active_filter,
                    )
                )
                or 0
            )
            counts = {
                "actor_minute": rows["actor_minute"].admitted_count,
                "tenant_minute": rows["tenant_minute"].admitted_count,
                "actor_day": rows["actor_day"].admitted_count,
                "tenant_day": rows["tenant_day"].admitted_count,
                "actor_storage": rows["actor_lifetime"].reserved_bytes,
                "tenant_storage": rows["tenant_lifetime"].reserved_bytes,
            }
            denied = _denial(
                policy=policy,
                counts=counts,
                actor_active=actor_active,
                tenant_active=tenant_active,
                estimated_bytes=estimated_bytes,
            )
            if denied is not None:
                reason, status, window = denied
                for row in rows.values():
                    row.denied_count += 1
                    row.updated_at = now_s
                return LifecycleDecision(
                    None,
                    reason,
                    status,
                    _retry_after(current, window, lease_s=policy.lease_s),
                )

            for row in rows.values():
                row.admitted_count += 1
                row.updated_at = now_s
            rows["actor_lifetime"].reserved_bytes += estimated_bytes
            rows["tenant_lifetime"].reserved_bytes += estimated_bytes
            request_id = str(uuid.uuid4())
            session.add(
                V2ApiLifecycleAdmission(
                    request_id=request_id,
                    quota_group=group,
                    action=action,
                    tenant_ref=tenant_ref,
                    actor_ref=actor_ref,
                    idempotency_key_hash=key_hash,
                    request_digest=request_digest,
                    estimated_bytes=estimated_bytes,
                    started_at=now_s,
                    expires_at=_iso(current + timedelta(seconds=policy.lease_s)),
                    released_at=None,
                    outcome="active",
                    resource_type=None,
                    resource_id=None,
                )
            )
            return LifecycleDecision(
                LifecycleAdmission(
                    request_id,
                    tenant_ref,
                    actor_ref,
                    estimated_bytes,
                    now_s,
                )
            )

    def complete(
        self,
        request_id: str,
        *,
        completion_token: str,
        outcome: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if outcome not in {"success", "error", "cancelled"}:
            raise ValueError("invalid lifecycle admission outcome")
        if outcome == "success" and (not resource_type or not resource_id):
            raise ValueError("successful lifecycle admission requires a resource")
        now_s = _iso(now or datetime.now(timezone.utc))
        with self._sessions() as session, session.begin():
            row = session.get(V2ApiLifecycleAdmission, request_id)
            if (
                row is None
                or row.released_at is not None
                or row.outcome != "active"
                or row.started_at != completion_token
            ):
                return
            row.released_at = now_s
            row.outcome = outcome
            row.resource_type = resource_type
            row.resource_id = resource_id


class InMemoryLifecycleControlStore:
    """Explicit hermetic test double; production dependency construction never returns it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str, str, str, str], dict[str, int]] = {}
        self._admissions: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[tuple[str, str, str, str], str] = {}

    def _window(self, key: tuple[str, str, str, str, str]) -> dict[str, int]:
        return self._windows.setdefault(key, {"admitted": 0, "denied": 0, "bytes": 0})

    def admit(
        self,
        identity: VerifiedIdentity,
        policy: LifecyclePolicy,
        *,
        action: str,
        idempotency_key: str,
        request_digest: str,
        estimated_bytes: int,
        now: datetime | None = None,
    ) -> LifecycleDecision:
        try:
            group = _ACTION_GROUPS[action]
        except KeyError as exc:
            raise ValueError("unsupported lifecycle action") from exc
        if estimated_bytes < 0:
            raise ValueError("estimated lifecycle bytes must be non-negative")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_s, buckets = _iso(current), _buckets(current)
        tenant_ref, actor_ref = identity_scope_refs(identity)
        key_hash = idempotency_key_hash(action, idempotency_key)
        idem_key = (action, tenant_ref, actor_ref, key_hash)
        with self._lock:
            existing_id = self._idempotency.get(idem_key)
            if existing_id is not None:
                existing = self._admissions[existing_id]
                if existing["request_digest"] != request_digest:
                    return LifecycleDecision(None, "idempotency_conflict", 409)
                if (
                    existing["outcome"] == "success"
                    and existing["resource_type"]
                    and existing["resource_id"]
                ):
                    return LifecycleDecision(
                        LifecycleAdmission(
                            existing_id,
                            tenant_ref,
                            actor_ref,
                            existing["estimated_bytes"],
                            existing["started_at"],
                            True,
                            existing["resource_type"],
                            existing["resource_id"],
                        )
                    )
                if existing["outcome"] == "active" and existing["expires_at"] > now_s:
                    return LifecycleDecision(
                        None, "idempotency_in_progress", 409, policy.lease_s
                    )
                if existing["outcome"] == "active":
                    existing["started_at"] = now_s
                    existing["expires_at"] = _iso(
                        current + timedelta(seconds=policy.lease_s)
                    )
                    return LifecycleDecision(
                        LifecycleAdmission(
                            existing_id,
                            tenant_ref,
                            actor_ref,
                            existing["estimated_bytes"],
                            now_s,
                        )
                    )
                return LifecycleDecision(None, "idempotency_finalized", 409)

            rows = {
                "actor_minute": self._window(
                    (group, "actor", actor_ref, "minute", buckets["minute"])
                ),
                "tenant_minute": self._window(
                    (group, "tenant", tenant_ref, "minute", buckets["minute"])
                ),
                "actor_day": self._window(
                    (group, "actor", actor_ref, "day", buckets["day"])
                ),
                "tenant_day": self._window(
                    (group, "tenant", tenant_ref, "day", buckets["day"])
                ),
                "actor_lifetime": self._window(
                    (group, "actor", actor_ref, "lifetime", "all")
                ),
                "tenant_lifetime": self._window(
                    (group, "tenant", tenant_ref, "lifetime", "all")
                ),
            }
            active = [
                row
                for row in self._admissions.values()
                if row["released_at"] is None and row["expires_at"] > now_s
            ]
            counts = {
                "actor_minute": rows["actor_minute"]["admitted"],
                "tenant_minute": rows["tenant_minute"]["admitted"],
                "actor_day": rows["actor_day"]["admitted"],
                "tenant_day": rows["tenant_day"]["admitted"],
                "actor_storage": rows["actor_lifetime"]["bytes"],
                "tenant_storage": rows["tenant_lifetime"]["bytes"],
            }
            denied = _denial(
                policy=policy,
                counts=counts,
                actor_active=sum(row["actor_ref"] == actor_ref for row in active),
                tenant_active=sum(row["tenant_ref"] == tenant_ref for row in active),
                estimated_bytes=estimated_bytes,
            )
            if denied is not None:
                reason, status, window = denied
                for row in rows.values():
                    row["denied"] += 1
                return LifecycleDecision(
                    None,
                    reason,
                    status,
                    _retry_after(current, window, lease_s=policy.lease_s),
                )
            for row in rows.values():
                row["admitted"] += 1
            rows["actor_lifetime"]["bytes"] += estimated_bytes
            rows["tenant_lifetime"]["bytes"] += estimated_bytes
            request_id = str(uuid.uuid4())
            self._admissions[request_id] = {
                "tenant_ref": tenant_ref,
                "actor_ref": actor_ref,
                "request_digest": request_digest,
                "estimated_bytes": estimated_bytes,
                "started_at": now_s,
                "expires_at": _iso(current + timedelta(seconds=policy.lease_s)),
                "released_at": None,
                "outcome": "active",
                "resource_type": None,
                "resource_id": None,
            }
            self._idempotency[idem_key] = request_id
            return LifecycleDecision(
                LifecycleAdmission(
                    request_id,
                    tenant_ref,
                    actor_ref,
                    estimated_bytes,
                    now_s,
                )
            )

    def complete(
        self,
        request_id: str,
        *,
        completion_token: str,
        outcome: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if outcome not in {"success", "error", "cancelled"}:
            raise ValueError("invalid lifecycle admission outcome")
        if outcome == "success" and (not resource_type or not resource_id):
            raise ValueError("successful lifecycle admission requires a resource")
        with self._lock:
            row = self._admissions.get(request_id)
            if (
                row is None
                or row["released_at"] is not None
                or row["outcome"] != "active"
                or row["started_at"] != completion_token
            ):
                return
            row["released_at"] = _iso(now or datetime.now(timezone.utc))
            row["outcome"] = outcome
            row["resource_type"] = resource_type
            row["resource_id"] = resource_id
