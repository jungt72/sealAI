"""Fail-closed, shared admission control for provider-backed product requests.

Production uses :class:`PostgresCostControlStore`; there is deliberately no automatic in-memory
fallback. Every accepted request consumes a conservative, non-refundable cost reservation before
provider work starts. This makes daily/monthly ceilings hard even if telemetry, settlement, a
worker, or the provider later fails. Concurrency is represented by expiring leases so a crashed
worker cannot block a tenant forever.
"""

from __future__ import annotations

import logging
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Iterator, Protocol

from sqlalchemy import func, select, text

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.models import V2ProviderAdmission, V2ProviderQuotaWindow

_LOG = logging.getLogger("sealai_v2.provider_admission")
_POSTGRES_ADVISORY_LOCK_ID = 7_214_407_061_401_001

# One paid embedding admission covers exactly one bounded provider API call.  The values are code
# invariants, not pricing assumptions: the still-blocked budget contract must prove that the shared
# reservation covers this complete shape before the global provider switch can ever be opened.
REMOTE_EMBEDDING_MAX_BATCH_ITEMS = 50
REMOTE_EMBEDDING_MAX_INPUT_BYTES = 24_000
REMOTE_EMBEDDING_MAX_BATCH_BYTES = (
    REMOTE_EMBEDDING_MAX_BATCH_ITEMS * REMOTE_EMBEDDING_MAX_INPUT_BYTES
)
REMOTE_EMBEDDING_MAX_WORKER_ATTEMPTS = 5
_EMBEDDING_SERVICE_IDENTITIES = {
    "memory_outbox": VerifiedIdentity(
        "sealai-system", "memory-outbox", "memory-outbox", email_verified=True
    ),
    "knowledge_outbox": VerifiedIdentity(
        "sealai-system", "knowledge-outbox", "knowledge-outbox", email_verified=True
    ),
}


class ProviderServiceUnavailable(RuntimeError):
    """Paid background work cannot prove a valid shared admission."""


class EmbeddingWorkloadTooLarge(ValueError):
    """A remote embedding input exceeds the mechanically budgetable workload."""


_CONTROL_FAILURE_CODES = {
    "shared provider admission authority unavailable": "provider_admission_store_unavailable",
    "unsupported embedding provider": "embedding_provider_unsupported",
    "outbox batch size must be positive": "outbox_batch_size_invalid",
    "outbox max attempts must be positive": "outbox_attempt_limit_invalid",
    "remote outbox batch size exceeds the budget-contract limit": "outbox_batch_limit_exceeded",
    "remote outbox retry count exceeds the budget-contract limit": "outbox_retry_limit_exceeded",
    "provider requests are disabled": "provider_requests_disabled",
    "remote embeddings require the shared Postgres admission authority": "provider_postgres_required",
    "remote embedding adapter cannot use the local outbox path": "remote_adapter_path_mismatch",
    "remote embedding call has no shared provider admission": "provider_admission_missing",
    "outbox embedding adapter is unavailable": "embedding_adapter_unavailable",
}
_WORKLOAD_FAILURE_CODES = {
    "remote embedding batch exceeds the hard item limit": "embedding_item_limit_exceeded",
    "remote embedding inputs must be text": "embedding_input_type_invalid",
    "remote embedding inputs must be non-empty": "embedding_input_empty",
    "remote embedding input exceeds the hard byte limit": "embedding_input_bytes_exceeded",
    "remote embedding batch exceeds the hard byte limit": "embedding_batch_bytes_exceeded",
    "embedding batch must be an iterable of text inputs, not scalar text": "embedding_batch_type_invalid",
}
_ADMISSION_DENIAL_CODES = {
    "subject_rate",
    "tenant_rate",
    "subject_daily_quota",
    "tenant_daily_quota",
    "tenant_monthly_quota",
    "subject_concurrency",
    "tenant_concurrency",
    "provider_daily_budget",
    "provider_monthly_budget",
    "denied",
}


def classify_outbox_failure(exc: BaseException) -> str:
    """Return a bounded metadata-only code; never persist an exception message or traceback."""
    if isinstance(exc, ProviderServiceUnavailable):
        message = str(exc)
        if message in _CONTROL_FAILURE_CODES:
            return _CONTROL_FAILURE_CODES[message]
        prefix = "provider service admission denied: "
        if message.startswith(prefix):
            reason = message.removeprefix(prefix)
            if reason in _ADMISSION_DENIAL_CODES:
                return f"provider_admission_denied:{reason}"
        return "provider_control_unavailable"
    if isinstance(exc, EmbeddingWorkloadTooLarge):
        return _WORKLOAD_FAILURE_CODES.get(str(exc), "embedding_workload_rejected")
    if isinstance(exc, RuntimeError) and str(exc).startswith(
        "embedding provider returned an incomplete"
    ):
        return "embedding_response_incomplete"
    type_name = type(exc).__name__
    safe_type = "".join(
        character
        for character in type_name
        if character.isascii() and (character.isalnum() or character == "_")
    )[:64]
    return f"infrastructure_error:{safe_type or 'Exception'}"


def _scope_ref(kind: str, value: str) -> str:
    return sha256(f"sealai-provider-{kind}-v1\x00{value}".encode()).hexdigest()


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
        "month": utc.strftime("%Y-%m"),
    }


def _retry_after(now: datetime, window: str) -> int:
    utc = now.astimezone(timezone.utc)
    if window == "minute":
        end = utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
    elif window == "day":
        end = utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        if utc.month == 12:
            end = utc.replace(
                year=utc.year + 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        else:
            end = utc.replace(
                month=utc.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
    return max(1, int((end - utc).total_seconds()))


@dataclass(frozen=True)
class CostControlPolicy:
    subject_per_minute: int
    tenant_per_minute: int
    subject_per_day: int
    tenant_per_day: int
    tenant_per_month: int
    subject_max_concurrent: int
    tenant_max_concurrent: int
    lease_s: int
    reservation_micros: int
    daily_budget_micros: int
    monthly_budget_micros: int

    @classmethod
    def from_settings(cls, settings) -> "CostControlPolicy":
        return cls(
            subject_per_minute=settings.provider_subject_requests_per_minute,
            tenant_per_minute=settings.provider_tenant_requests_per_minute,
            subject_per_day=settings.provider_subject_requests_per_day,
            tenant_per_day=settings.provider_tenant_requests_per_day,
            tenant_per_month=settings.provider_tenant_requests_per_month,
            subject_max_concurrent=settings.provider_subject_max_concurrent,
            tenant_max_concurrent=settings.provider_tenant_max_concurrent,
            lease_s=settings.provider_request_lease_s,
            reservation_micros=settings.provider_request_reservation_micros,
            daily_budget_micros=settings.provider_daily_budget_micros,
            monthly_budget_micros=settings.provider_monthly_budget_micros,
        )


@dataclass(frozen=True)
class Admission:
    request_id: str
    tenant_ref: str
    subject_ref: str
    reserved_cost_micros: int


@dataclass(frozen=True)
class AdmissionDecision:
    admission: Admission | None
    reason: str | None = None
    status_code: int = 429
    retry_after_s: int | None = None

    @property
    def allowed(self) -> bool:
        return self.admission is not None


class CostControlStore(Protocol):
    def admit(
        self,
        identity: VerifiedIdentity,
        policy: CostControlPolicy,
        *,
        now: datetime | None = None,
    ) -> AdmissionDecision: ...

    def release(
        self, request_id: str, *, outcome: str, now: datetime | None = None
    ) -> None: ...

    def summary(self, *, now: datetime | None = None) -> dict: ...


class EmbeddingServiceAdmission:
    """Reserve one non-refundable shared-budget slot around one remote embedding call.

    The service identity is server-owned and deliberately shares the same global day/month rows as
    interactive product requests.  Releasing the lease never changes the reserved-cost counters.
    """

    def __init__(
        self,
        store: CostControlStore,
        policy: CostControlPolicy,
        *,
        service: str,
    ) -> None:
        try:
            identity = _EMBEDDING_SERVICE_IDENTITIES[service]
        except KeyError as exc:
            raise ValueError("unknown provider service identity") from exc
        self._store = store
        self._policy = policy
        self._service = service
        self._identity = identity

    @contextmanager
    def reserve(self, inputs: tuple[str, ...]) -> Iterator[Admission | None]:
        """Validate the complete call shape, then reserve before yielding to provider I/O."""
        if not inputs:
            # The OpenAI adapter also treats an empty input as a local no-op.  Do not consume quota
            # or budget when no provider request can occur.
            yield None
            return
        validate_remote_embedding_inputs(inputs)
        try:
            decision = self._store.admit(self._identity, self._policy)
        except Exception as exc:  # noqa: BLE001 - authority loss must deny provider I/O
            raise ProviderServiceUnavailable(
                "shared provider admission authority unavailable"
            ) from exc
        if not decision.allowed or decision.admission is None:
            reason = decision.reason or "denied"
            raise ProviderServiceUnavailable(
                f"provider service admission denied: {reason}"
            )

        admission = decision.admission
        outcome = "error"
        try:
            yield admission
            outcome = "success"
        finally:
            try:
                # release() only closes the concurrency lease; the cost reservation is deliberately
                # non-refundable.  A release failure must not turn a completed provider call into a
                # retry (and a second paid call); the short lease expires on its own.
                self._store.release(admission.request_id, outcome=outcome)
            except Exception:  # noqa: BLE001 - reservation is already durable and remains charged
                _LOG.error(
                    "provider_admission event=service_release_failed service=%s",
                    self._service,
                )


def validate_remote_embedding_inputs(inputs: tuple[str, ...]) -> None:
    """Pure preflight for the exact texts later bound to one paid embedding admission."""
    if len(inputs) > REMOTE_EMBEDDING_MAX_BATCH_ITEMS:
        raise EmbeddingWorkloadTooLarge(
            "remote embedding batch exceeds the hard item limit"
        )
    total_bytes = 0
    for value in inputs:
        if not isinstance(value, str):
            raise EmbeddingWorkloadTooLarge("remote embedding inputs must be text")
        size = len(value.encode("utf-8"))
        if size <= 0:
            raise EmbeddingWorkloadTooLarge("remote embedding inputs must be non-empty")
        if size > REMOTE_EMBEDDING_MAX_INPUT_BYTES:
            raise EmbeddingWorkloadTooLarge(
                "remote embedding input exceeds the hard byte limit"
            )
        total_bytes += size
    if total_bytes > REMOTE_EMBEDDING_MAX_BATCH_BYTES:
        raise EmbeddingWorkloadTooLarge(
            "remote embedding batch exceeds the hard byte limit"
        )


def remote_embedding_enabled(settings) -> bool:
    """Classify the configured embedding path; unknown values fail closed."""
    provider = str(getattr(settings, "embed_provider", "") or "").strip().lower()
    if provider == "openai":
        return True
    if provider == "fastembed":
        return False
    raise ProviderServiceUnavailable("unsupported embedding provider")


def validate_embedding_worker_limits(
    batch_size: int, max_attempts: int, *, remote: bool
) -> None:
    if batch_size <= 0:
        raise ProviderServiceUnavailable("outbox batch size must be positive")
    if max_attempts <= 0:
        raise ProviderServiceUnavailable("outbox max attempts must be positive")
    if remote and batch_size > REMOTE_EMBEDDING_MAX_BATCH_ITEMS:
        raise ProviderServiceUnavailable(
            "remote outbox batch size exceeds the budget-contract limit"
        )
    if remote and max_attempts > REMOTE_EMBEDDING_MAX_WORKER_ATTEMPTS:
        raise ProviderServiceUnavailable(
            "remote outbox retry count exceeds the budget-contract limit"
        )


def build_embedding_service_admission(
    settings,
    session_factory,
    *,
    service: str,
) -> EmbeddingServiceAdmission | None:
    """Build the production gate, or no gate for the explicitly local FastEmbed path."""
    if not remote_embedding_enabled(settings):
        return None
    if not bool(getattr(settings, "provider_requests_enabled", False)):
        raise ProviderServiceUnavailable("provider requests are disabled")
    database_url = str(getattr(settings, "database_url", "") or "")
    if not database_url.startswith(("postgresql://", "postgresql+")):
        raise ProviderServiceUnavailable(
            "remote embeddings require the shared Postgres admission authority"
        )
    return EmbeddingServiceAdmission(
        PostgresCostControlStore(session_factory),
        CostControlPolicy.from_settings(settings),
        service=service,
    )


def embed_with_service_admission(
    embedder,
    inputs,
    *,
    remote: bool,
    admission: EmbeddingServiceAdmission | None,
):
    """The only outbox seam allowed to invoke a paid embedding adapter."""
    if isinstance(inputs, (str, bytes)):
        raise EmbeddingWorkloadTooLarge(
            "embedding batch must be an iterable of text inputs, not scalar text"
        )
    batch = tuple(inputs)
    if not batch:
        return []
    if bool(getattr(embedder, "provider_is_remote", False)) and not remote:
        raise ProviderServiceUnavailable(
            "remote embedding adapter cannot use the local outbox path"
        )
    if not remote:
        return list(embedder.embed(batch))
    if admission is None:
        raise ProviderServiceUnavailable(
            "remote embedding call has no shared provider admission"
        )
    with admission.reserve(batch):
        return list(embedder.embed(batch))


def _reason(
    *,
    policy: CostControlPolicy,
    counts: dict[str, int],
    subject_active: int,
    tenant_active: int,
) -> tuple[str, int, str] | None:
    checks = (
        (
            counts["subject_minute"] >= policy.subject_per_minute,
            "subject_rate",
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
            counts["subject_day"] >= policy.subject_per_day,
            "subject_daily_quota",
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
            counts["tenant_month"] >= policy.tenant_per_month,
            "tenant_monthly_quota",
            429,
            "month",
        ),
        (
            subject_active >= policy.subject_max_concurrent,
            "subject_concurrency",
            429,
            "minute",
        ),
        (
            tenant_active >= policy.tenant_max_concurrent,
            "tenant_concurrency",
            429,
            "minute",
        ),
        (
            counts["global_day_cost"] + policy.reservation_micros
            > policy.daily_budget_micros,
            "provider_daily_budget",
            402,
            "day",
        ),
        (
            counts["global_month_cost"] + policy.reservation_micros
            > policy.monthly_budget_micros,
            "provider_monthly_budget",
            402,
            "month",
        ),
    )
    for denied, reason, status, window in checks:
        if denied:
            return reason, status, window
    return None


class PostgresCostControlStore:
    """Durable multi-worker store. Postgres serializes admission with one transaction lock."""

    def __init__(self, session_factory) -> None:
        self._sessions = session_factory
        self._local_lock = threading.Lock()

    @staticmethod
    def _window(session, kind: str, ref: str, window: str, start: str, now_s: str):
        key = (kind, ref, window, start)
        row = session.get(V2ProviderQuotaWindow, key)
        if row is None:
            row = V2ProviderQuotaWindow(
                scope_kind=kind,
                scope_ref=ref,
                window_kind=window,
                window_start=start,
                admitted_count=0,
                denied_count=0,
                reserved_cost_micros=0,
                updated_at=now_s,
            )
            session.add(row)
            session.flush()
        return row

    def admit(
        self,
        identity: VerifiedIdentity,
        policy: CostControlPolicy,
        *,
        now: datetime | None = None,
    ) -> AdmissionDecision:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_s = _iso(current)
        buckets = _buckets(current)
        tenant_ref = _scope_ref("tenant", identity.tenant_id)
        subject_ref = _scope_ref(
            "subject", f"{identity.tenant_id}\x00{identity.subject}"
        )
        global_ref = "global"

        with self._local_lock, self._sessions() as session, session.begin():
            if session.get_bind().dialect.name == "postgresql":
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": _POSTGRES_ADVISORY_LOCK_ID},
                )

            rows = {
                "subject_minute": self._window(
                    session, "subject", subject_ref, "minute", buckets["minute"], now_s
                ),
                "tenant_minute": self._window(
                    session, "tenant", tenant_ref, "minute", buckets["minute"], now_s
                ),
                "subject_day": self._window(
                    session, "subject", subject_ref, "day", buckets["day"], now_s
                ),
                "tenant_day": self._window(
                    session, "tenant", tenant_ref, "day", buckets["day"], now_s
                ),
                "tenant_month": self._window(
                    session, "tenant", tenant_ref, "month", buckets["month"], now_s
                ),
                "global_day": self._window(
                    session, "global", global_ref, "day", buckets["day"], now_s
                ),
                "global_month": self._window(
                    session, "global", global_ref, "month", buckets["month"], now_s
                ),
            }
            expires_filter = V2ProviderAdmission.expires_at > now_s
            subject_active = int(
                session.scalar(
                    select(func.count())
                    .select_from(V2ProviderAdmission)
                    .where(
                        V2ProviderAdmission.subject_ref == subject_ref,
                        V2ProviderAdmission.released_at.is_(None),
                        expires_filter,
                    )
                )
                or 0
            )
            tenant_active = int(
                session.scalar(
                    select(func.count())
                    .select_from(V2ProviderAdmission)
                    .where(
                        V2ProviderAdmission.tenant_ref == tenant_ref,
                        V2ProviderAdmission.released_at.is_(None),
                        expires_filter,
                    )
                )
                or 0
            )
            counts = {
                key: row.admitted_count
                for key, row in rows.items()
                if key not in {"global_day", "global_month"}
            }
            counts["global_day_cost"] = rows["global_day"].reserved_cost_micros
            counts["global_month_cost"] = rows["global_month"].reserved_cost_micros
            denied = _reason(
                policy=policy,
                counts=counts,
                subject_active=subject_active,
                tenant_active=tenant_active,
            )
            if denied is not None:
                reason, status, window = denied
                for row in rows.values():
                    row.denied_count += 1
                    row.updated_at = now_s
                _LOG.warning(
                    "provider_admission event=denied reason=%s tenant_ref=%s subject_ref=%s",
                    reason,
                    tenant_ref[:16],
                    subject_ref[:16],
                )
                return AdmissionDecision(
                    admission=None,
                    reason=reason,
                    status_code=status,
                    retry_after_s=_retry_after(current, window),
                )

            for row in rows.values():
                row.admitted_count += 1
                row.updated_at = now_s
            rows["global_day"].reserved_cost_micros += policy.reservation_micros
            rows["global_month"].reserved_cost_micros += policy.reservation_micros
            request_id = str(uuid.uuid4())
            session.add(
                V2ProviderAdmission(
                    request_id=request_id,
                    tenant_ref=tenant_ref,
                    subject_ref=subject_ref,
                    started_at=now_s,
                    expires_at=_iso(current + timedelta(seconds=policy.lease_s)),
                    released_at=None,
                    outcome="active",
                    reserved_cost_micros=policy.reservation_micros,
                )
            )
            admission = Admission(
                request_id=request_id,
                tenant_ref=tenant_ref,
                subject_ref=subject_ref,
                reserved_cost_micros=policy.reservation_micros,
            )
            _LOG.info(
                "provider_admission event=admitted request_id=%s tenant_ref=%s subject_ref=%s reserved_micros=%d",
                request_id,
                tenant_ref[:16],
                subject_ref[:16],
                policy.reservation_micros,
            )
            return AdmissionDecision(admission=admission)

    def release(
        self, request_id: str, *, outcome: str, now: datetime | None = None
    ) -> None:
        if outcome not in {"success", "error", "cancelled"}:
            raise ValueError("invalid provider admission outcome")
        now_s = _iso(now or datetime.now(timezone.utc))
        with self._sessions() as session, session.begin():
            row = session.get(V2ProviderAdmission, request_id)
            if row is None or row.released_at is not None:
                return
            row.released_at = now_s
            row.outcome = outcome
        _LOG.info(
            "provider_admission event=released request_id=%s outcome=%s",
            request_id,
            outcome,
        )

    def summary(self, *, now: datetime | None = None) -> dict:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_s = _iso(current)
        buckets = _buckets(current)
        with self._sessions() as session:
            day = session.get(
                V2ProviderQuotaWindow, ("global", "global", "day", buckets["day"])
            )
            month = session.get(
                V2ProviderQuotaWindow, ("global", "global", "month", buckets["month"])
            )
            active = int(
                session.scalar(
                    select(func.count())
                    .select_from(V2ProviderAdmission)
                    .where(
                        V2ProviderAdmission.released_at.is_(None),
                        V2ProviderAdmission.expires_at > now_s,
                    )
                )
                or 0
            )

        def window(row) -> dict:
            return {
                "admitted_requests": row.admitted_count if row else 0,
                "denied_requests": row.denied_count if row else 0,
                "reserved_cost_micros": row.reserved_cost_micros if row else 0,
            }

        return {"active_requests": active, "day": window(day), "month": window(month)}


class InMemoryCostControlStore:
    """Explicit hermetic test double. Production dependency construction never returns this class."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str, str, str], dict[str, int]] = {}
        self._admissions: dict[str, dict] = {}

    def _window(self, key: tuple[str, str, str, str]) -> dict[str, int]:
        return self._windows.setdefault(key, {"admitted": 0, "denied": 0, "cost": 0})

    def admit(self, identity, policy, *, now=None) -> AdmissionDecision:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_s, buckets = _iso(current), _buckets(current)
        tenant_ref = _scope_ref("tenant", identity.tenant_id)
        subject_ref = _scope_ref(
            "subject", f"{identity.tenant_id}\x00{identity.subject}"
        )
        with self._lock:
            rows = {
                "subject_minute": self._window(
                    ("subject", subject_ref, "minute", buckets["minute"])
                ),
                "tenant_minute": self._window(
                    ("tenant", tenant_ref, "minute", buckets["minute"])
                ),
                "subject_day": self._window(
                    ("subject", subject_ref, "day", buckets["day"])
                ),
                "tenant_day": self._window(
                    ("tenant", tenant_ref, "day", buckets["day"])
                ),
                "tenant_month": self._window(
                    ("tenant", tenant_ref, "month", buckets["month"])
                ),
                "global_day": self._window(("global", "global", "day", buckets["day"])),
                "global_month": self._window(
                    ("global", "global", "month", buckets["month"])
                ),
            }
            active = [
                row
                for row in self._admissions.values()
                if row["released_at"] is None and row["expires_at"] > now_s
            ]
            counts = {
                key: row["admitted"]
                for key, row in rows.items()
                if key not in {"global_day", "global_month"}
            }
            counts["global_day_cost"] = rows["global_day"]["cost"]
            counts["global_month_cost"] = rows["global_month"]["cost"]
            denied = _reason(
                policy=policy,
                counts=counts,
                subject_active=sum(row["subject_ref"] == subject_ref for row in active),
                tenant_active=sum(row["tenant_ref"] == tenant_ref for row in active),
            )
            if denied:
                reason, status, window = denied
                for row in rows.values():
                    row["denied"] += 1
                return AdmissionDecision(
                    None, reason, status, _retry_after(current, window)
                )
            for row in rows.values():
                row["admitted"] += 1
            rows["global_day"]["cost"] += policy.reservation_micros
            rows["global_month"]["cost"] += policy.reservation_micros
            request_id = str(uuid.uuid4())
            self._admissions[request_id] = {
                "tenant_ref": tenant_ref,
                "subject_ref": subject_ref,
                "expires_at": _iso(current + timedelta(seconds=policy.lease_s)),
                "released_at": None,
                "outcome": "active",
            }
            return AdmissionDecision(
                Admission(
                    request_id, tenant_ref, subject_ref, policy.reservation_micros
                )
            )

    def release(self, request_id, *, outcome, now=None) -> None:
        if outcome not in {"success", "error", "cancelled"}:
            raise ValueError("invalid provider admission outcome")
        with self._lock:
            row = self._admissions.get(request_id)
            if row and row["released_at"] is None:
                row["released_at"] = _iso(now or datetime.now(timezone.utc))
                row["outcome"] = outcome

    def summary(self, *, now=None) -> dict:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        buckets = _buckets(current)
        now_s = _iso(current)
        with self._lock:
            day = self._window(("global", "global", "day", buckets["day"]))
            month = self._window(("global", "global", "month", buckets["month"]))
            active = sum(
                row["released_at"] is None and row["expires_at"] > now_s
                for row in self._admissions.values()
            )
            return {
                "active_requests": active,
                "day": {
                    "admitted_requests": day["admitted"],
                    "denied_requests": day["denied"],
                    "reserved_cost_micros": day["cost"],
                },
                "month": {
                    "admitted_requests": month["admitted"],
                    "denied_requests": month["denied"],
                    "reserved_cost_micros": month["cost"],
                },
            }
