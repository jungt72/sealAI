from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.config.settings import Settings
from sealai_v2.db.models import V2ProviderAdmission, V2ProviderQuotaWindow
from sealai_v2.security.cost_control import (
    CostControlPolicy,
    EmbeddingServiceAdmission,
    EmbeddingWorkloadTooLarge,
    InMemoryCostControlStore,
    PostgresCostControlStore,
    ProviderServiceUnavailable,
    REMOTE_EMBEDDING_MAX_INPUT_BYTES,
    build_embedding_service_admission,
    embed_with_service_admission,
    validate_embedding_worker_limits,
)

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def test_provider_activation_requires_shared_database_and_reviewed_budget_contract():
    with pytest.raises(ValidationError, match="shared Postgres"):
        Settings(provider_requests_enabled=True)
    with pytest.raises(ValidationError, match="budget contract digest"):
        Settings(provider_requests_enabled=True, database_url="postgresql://quota")
    with pytest.raises(ValidationError, match="externally validated"):
        Settings(
            provider_requests_enabled=True,
            database_url="postgresql://quota",
            provider_budget_contract_sha256="sha256:" + "a" * 64,
        )


def policy(**overrides) -> CostControlPolicy:
    values = dict(
        subject_per_minute=100,
        tenant_per_minute=100,
        subject_per_day=100,
        tenant_per_day=100,
        tenant_per_month=1000,
        subject_max_concurrent=100,
        tenant_max_concurrent=100,
        lease_s=60,
        reservation_micros=100,
        daily_budget_micros=10_000,
        monthly_budget_micros=100_000,
    )
    values.update(overrides)
    return CostControlPolicy(**values)


def identity(subject="user-a", tenant="tenant-a") -> VerifiedIdentity:
    return VerifiedIdentity(tenant, "session", subject, email_verified=True)


def test_parallel_requests_cannot_oversubscribe_subject_concurrency():
    store = InMemoryCostControlStore()
    current_policy = policy(subject_max_concurrent=2)
    with ThreadPoolExecutor(max_workers=24) as pool:
        decisions = list(
            pool.map(
                lambda _: store.admit(identity(), current_policy, now=NOW),
                range(24),
            )
        )
    allowed = [decision for decision in decisions if decision.allowed]
    denied = [decision for decision in decisions if not decision.allowed]
    assert len(allowed) == 2
    assert {decision.reason for decision in denied} == {"subject_concurrency"}


def test_layered_subject_and_tenant_rate_quotas_return_429():
    store = InMemoryCostControlStore()
    current_policy = policy(subject_per_minute=2, tenant_per_minute=3)
    first = store.admit(identity("a"), current_policy, now=NOW)
    second = store.admit(identity("a"), current_policy, now=NOW)
    for decision in (first, second):
        store.release(decision.admission.request_id, outcome="success", now=NOW)  # type: ignore[union-attr]
    subject_denied = store.admit(identity("a"), current_policy, now=NOW)
    assert (subject_denied.status_code, subject_denied.reason) == (429, "subject_rate")

    other = store.admit(identity("b"), current_policy, now=NOW)
    store.release(other.admission.request_id, outcome="success", now=NOW)  # type: ignore[union-attr]
    tenant_denied = store.admit(identity("c"), current_policy, now=NOW)
    assert (tenant_denied.status_code, tenant_denied.reason) == (429, "tenant_rate")


def test_hard_daily_and_monthly_budgets_reserve_before_provider_work():
    store = InMemoryCostControlStore()
    current_policy = policy(
        reservation_micros=400,
        daily_budget_micros=800,
        monthly_budget_micros=5_000,
    )
    for subject in ("a", "b"):
        admitted = store.admit(identity(subject), current_policy, now=NOW)
        assert admitted.allowed
        store.release(admitted.admission.request_id, outcome="error", now=NOW)  # type: ignore[union-attr]
    denied = store.admit(identity("c"), current_policy, now=NOW)
    assert (denied.status_code, denied.reason) == (402, "provider_daily_budget")
    # Failed provider work never refunds a reservation, preserving the hard upper bound.
    assert store.summary(now=NOW)["day"]["reserved_cost_micros"] == 800


def test_expired_concurrency_lease_recovers_but_does_not_refund_budget():
    store = InMemoryCostControlStore()
    current_policy = policy(subject_max_concurrent=1, lease_s=10)
    assert store.admit(identity(), current_policy, now=NOW).allowed
    assert (
        store.admit(identity(), current_policy, now=NOW).reason == "subject_concurrency"
    )
    after_crash_lease = NOW + timedelta(seconds=11)
    assert store.admit(identity(), current_policy, now=after_crash_lease).allowed
    assert store.summary(now=after_crash_lease)["day"]["reserved_cost_micros"] == 200


def test_postgres_adapter_persists_aggregate_state_and_release():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    V2ProviderQuotaWindow.__table__.create(engine)
    V2ProviderAdmission.__table__.create(engine)
    store = PostgresCostControlStore(sessionmaker(bind=engine, expire_on_commit=False))
    decision = store.admit(identity(), policy(), now=NOW)
    assert decision.allowed
    assert store.summary(now=NOW)["active_requests"] == 1
    store.release(decision.admission.request_id, outcome="success", now=NOW)  # type: ignore[union-attr]
    assert store.summary(now=NOW)["active_requests"] == 0
    assert store.summary(now=NOW)["day"] == {
        "admitted_requests": 1,
        "denied_requests": 0,
        "reserved_cost_micros": 100,
    }


class _EmbeddingAdapter:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.error = error

    def embed(self, inputs):
        batch = tuple(inputs)
        self.calls.append(batch)
        if self.error is not None:
            raise self.error
        return [[0.1, 0.2] for _ in batch]


def test_remote_embedding_call_has_one_non_refundable_service_admission():
    store = InMemoryCostControlStore()
    gate = EmbeddingServiceAdmission(store, policy(), service="memory_outbox")
    embedder = _EmbeddingAdapter()

    assert embed_with_service_admission(
        embedder,
        ("one", "two"),
        remote=True,
        admission=gate,
    ) == [[0.1, 0.2], [0.1, 0.2]]

    assert embedder.calls == [("one", "two")]
    summary = store.summary()
    assert summary["active_requests"] == 0
    assert summary["day"]["admitted_requests"] == 1
    assert summary["day"]["reserved_cost_micros"] == 100


def test_failed_embedding_attempt_is_not_retried_or_refunded_inside_admission():
    store = InMemoryCostControlStore()
    gate = EmbeddingServiceAdmission(store, policy(), service="knowledge_outbox")
    embedder = _EmbeddingAdapter(error=ConnectionError("provider unavailable"))

    with pytest.raises(ConnectionError, match="provider unavailable"):
        embed_with_service_admission(
            embedder,
            ("one",),
            remote=True,
            admission=gate,
        )

    assert embedder.calls == [("one",)]
    summary = store.summary()
    assert summary["active_requests"] == 0
    assert summary["day"]["admitted_requests"] == 1
    assert summary["day"]["reserved_cost_micros"] == 100


def test_empty_or_local_embedding_work_never_consumes_service_admission():
    store = InMemoryCostControlStore()
    gate = EmbeddingServiceAdmission(store, policy(), service="memory_outbox")
    embedder = _EmbeddingAdapter()

    assert embed_with_service_admission(embedder, (), remote=True, admission=gate) == []
    assert embed_with_service_admission(
        embedder, ("local",), remote=False, admission=None
    ) == [[0.1, 0.2]]
    assert embedder.calls == [("local",)]
    assert store.summary()["day"]["admitted_requests"] == 0


def test_remote_embedding_limits_and_missing_gate_fail_before_provider_io():
    embedder = _EmbeddingAdapter()
    with pytest.raises(EmbeddingWorkloadTooLarge, match="not scalar text"):
        embed_with_service_admission(
            embedder, "not-a-batch", remote=True, admission=None
        )
    with pytest.raises(ProviderServiceUnavailable, match="no shared"):
        embed_with_service_admission(embedder, ("remote",), remote=True, admission=None)
    store = InMemoryCostControlStore()
    gate = EmbeddingServiceAdmission(store, policy(), service="memory_outbox")
    with pytest.raises(EmbeddingWorkloadTooLarge, match="byte limit"):
        embed_with_service_admission(
            embedder,
            ("x" * (REMOTE_EMBEDDING_MAX_INPUT_BYTES + 1),),
            remote=True,
            admission=gate,
        )
    assert embedder.calls == []
    assert store.summary()["day"]["admitted_requests"] == 0

    embedder.provider_is_remote = True
    with pytest.raises(ProviderServiceUnavailable, match="local outbox path"):
        embed_with_service_admission(
            embedder, ("mislabeled",), remote=False, admission=None
        )
    assert embedder.calls == []


def test_remote_worker_limits_and_kill_switch_are_fail_closed():
    with pytest.raises(ProviderServiceUnavailable, match="batch size"):
        validate_embedding_worker_limits(51, 5, remote=True)
    with pytest.raises(ProviderServiceUnavailable, match="retry count"):
        validate_embedding_worker_limits(50, 6, remote=True)
    with pytest.raises(ProviderServiceUnavailable, match="disabled"):
        build_embedding_service_admission(
            SimpleNamespace(
                embed_provider="openai",
                provider_requests_enabled=False,
                database_url="postgresql://quota",
            ),
            object(),
            service="memory_outbox",
        )
    with pytest.raises(ProviderServiceUnavailable, match="Postgres"):
        build_embedding_service_admission(
            SimpleNamespace(
                embed_provider="openai",
                provider_requests_enabled=True,
                database_url="sqlite://",
            ),
            object(),
            service="memory_outbox",
        )
    with pytest.raises(ProviderServiceUnavailable, match="unsupported"):
        build_embedding_service_admission(
            SimpleNamespace(embed_provider="unknown"),
            object(),
            service="memory_outbox",
        )
    assert (
        build_embedding_service_admission(
            SimpleNamespace(embed_provider="fastembed"),
            object(),
            service="memory_outbox",
        )
        is None
    )
