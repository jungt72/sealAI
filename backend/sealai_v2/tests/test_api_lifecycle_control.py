"""Atomic API lifecycle quota, concurrency, storage, and idempotency authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.security.lifecycle_control import (
    InMemoryLifecycleControlStore,
    LifecycleControlUnavailable,
    LifecyclePolicy,
    PostgresLifecycleControlStore,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _identity(subject="alice", tenant="tenant-a") -> VerifiedIdentity:
    return VerifiedIdentity(tenant, f"session-{subject}", subject)


def _policy(**overrides) -> LifecyclePolicy:
    values = {
        "actor_per_minute": 10,
        "tenant_per_minute": 20,
        "actor_per_day": 100,
        "tenant_per_day": 200,
        "actor_storage_bytes": 10_000,
        "tenant_storage_bytes": 100_000,
        "actor_max_concurrent": 2,
        "tenant_max_concurrent": 5,
        "lease_s": 60,
    }
    values.update(overrides)
    return LifecyclePolicy(**values)


def _admit(store, identity, policy, key, *, digest="digest-a", size=1):
    return store.admit(
        identity,
        policy,
        action="contribution.create",
        idempotency_key=key,
        request_digest=digest,
        estimated_bytes=size,
        now=NOW,
    )


def test_actor_and_tenant_rate_limits_are_independent_and_atomic():
    store = InMemoryLifecycleControlStore()
    policy = _policy(actor_per_minute=1, tenant_per_minute=2)

    alice = _admit(store, _identity("alice"), policy, "rate-key-alice-01")
    assert alice.allowed
    store.complete(
        alice.admission.request_id,
        completion_token=alice.admission.completion_token,
        outcome="error",
        now=NOW,
    )
    assert (
        _admit(store, _identity("alice"), policy, "rate-key-alice-02").reason
        == "actor_rate"
    )

    bob = _admit(store, _identity("bob"), policy, "rate-key-bob-0001")
    assert bob.allowed
    store.complete(
        bob.admission.request_id,
        completion_token=bob.admission.completion_token,
        outcome="error",
        now=NOW,
    )
    assert (
        _admit(store, _identity("carol"), policy, "rate-key-carol-01").reason
        == "tenant_rate"
    )


def test_storage_reservation_is_conservative_and_non_refundable_on_error():
    store = InMemoryLifecycleControlStore()
    policy = _policy(actor_storage_bytes=10, tenant_storage_bytes=100)
    first = _admit(store, _identity(), policy, "storage-key-0001", size=6)
    assert first.allowed
    store.complete(
        first.admission.request_id,
        completion_token=first.admission.completion_token,
        outcome="error",
        now=NOW,
    )
    denied = _admit(store, _identity(), policy, "storage-key-0002", size=5)
    assert denied.reason == "actor_storage_quota"
    assert denied.status_code == 507


def test_idempotency_replays_success_and_rejects_payload_change():
    store = InMemoryLifecycleControlStore()
    policy = _policy()
    first = _admit(store, _identity(), policy, "idempotency-key-0001")
    assert first.allowed and not first.admission.replay
    store.complete(
        first.admission.request_id,
        completion_token=first.admission.completion_token,
        outcome="success",
        resource_type="contribution",
        resource_id="42",
        now=NOW,
    )
    replay = _admit(store, _identity(), policy, "idempotency-key-0001")
    assert replay.allowed and replay.admission.replay
    assert replay.admission.resource_id == "42"
    conflict = _admit(
        store,
        _identity(),
        policy,
        "idempotency-key-0001",
        digest="digest-b",
    )
    assert conflict.reason == "idempotency_conflict"
    assert conflict.status_code == 409


def test_expired_active_admission_recovers_without_charging_quota_twice():
    store = InMemoryLifecycleControlStore()
    policy = _policy(actor_per_day=1, lease_s=60)
    first = _admit(store, _identity(), policy, "recovery-key-0001")
    assert first.allowed
    recovered = store.admit(
        _identity(),
        policy,
        action="contribution.create",
        idempotency_key="recovery-key-0001",
        request_digest="digest-a",
        estimated_bytes=1,
        now=NOW + timedelta(seconds=61),
    )
    assert recovered.allowed
    assert recovered.admission.request_id == first.admission.request_id
    store.complete(
        recovered.admission.request_id,
        completion_token=recovered.admission.completion_token,
        outcome="success",
        resource_type="contribution",
        resource_id="42",
        now=NOW + timedelta(seconds=61),
    )
    denied = store.admit(
        _identity(),
        policy,
        action="contribution.create",
        idempotency_key="recovery-key-0002",
        request_digest="digest-b",
        estimated_bytes=1,
        now=NOW + timedelta(seconds=61),
    )
    assert denied.reason == "actor_daily_quota"


def test_recovered_admission_fences_a_late_completion_from_the_expired_lease():
    store = InMemoryLifecycleControlStore()
    policy = _policy(lease_s=60)
    first = _admit(store, _identity(), policy, "fenced-recovery-key-0001")
    recovered = store.admit(
        _identity(),
        policy,
        action="contribution.create",
        idempotency_key="fenced-recovery-key-0001",
        request_digest="digest-a",
        estimated_bytes=1,
        now=NOW + timedelta(seconds=61),
    )
    assert recovered.allowed
    assert recovered.admission.request_id == first.admission.request_id
    assert recovered.admission.completion_token != first.admission.completion_token

    store.complete(
        first.admission.request_id,
        completion_token=first.admission.completion_token,
        outcome="error",
        now=NOW + timedelta(seconds=62),
    )
    store.complete(
        recovered.admission.request_id,
        completion_token=recovered.admission.completion_token,
        outcome="success",
        resource_type="contribution",
        resource_id="42",
        now=NOW + timedelta(seconds=63),
    )
    replay = store.admit(
        _identity(),
        policy,
        action="contribution.create",
        idempotency_key="fenced-recovery-key-0001",
        request_digest="digest-a",
        estimated_bytes=1,
        now=NOW + timedelta(seconds=64),
    )
    assert replay.allowed and replay.admission.replay
    assert replay.admission.resource_id == "42"


def test_concurrency_race_admits_exactly_one_actor_lease():
    store = InMemoryLifecycleControlStore()
    policy = _policy(actor_max_concurrent=1)
    barrier = Barrier(2)

    def compete(index: int):
        barrier.wait()
        return _admit(
            store,
            _identity(),
            policy,
            f"race-concurrency-{index:04d}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(compete, range(2)))
    assert sum(decision.allowed for decision in decisions) == 1
    denied = next(decision for decision in decisions if not decision.allowed)
    assert denied.reason == "actor_concurrency"


def test_production_authority_rejects_sqlite_false_evidence(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'control.db'}")
    Base.metadata.create_all(engine)
    store = PostgresLifecycleControlStore(make_sessionmaker(engine))
    with pytest.raises(LifecycleControlUnavailable, match="requires PostgreSQL"):
        _admit(store, _identity(), _policy(), "sqlite-false-evidence")


def test_activation_requires_postgres_rls_external_refs_and_runtime_secret():
    assert Settings().api_lifecycle_enabled is False
    with pytest.raises(ValueError, match="requires PostgreSQL"):
        Settings(api_lifecycle_enabled=True)
    with pytest.raises(ValueError, match="transaction-scoped"):
        Settings(
            api_lifecycle_enabled=True,
            database_url="postgresql+psycopg2://api@localhost/db",
        )
    with pytest.raises(ValueError, match="external policy references"):
        Settings(
            api_lifecycle_enabled=True,
            database_url="postgresql+psycopg2://api@localhost/db",
            database_rls_scope_enabled=True,
        )
    with pytest.raises(ValueError, match="HMAC secret"):
        Settings(
            api_lifecycle_enabled=True,
            database_url="postgresql+psycopg2://api@localhost/db",
            database_rls_scope_enabled=True,
            api_lifecycle_policy_authority_ref="authority:test-v1",
            api_lifecycle_purpose_version="purpose:test-v1",
            api_lifecycle_consent_version="consent:test-v1",
        )
    configured = Settings(
        api_lifecycle_enabled=True,
        database_url="postgresql+psycopg2://api@localhost/db",
        database_rls_scope_enabled=True,
        api_lifecycle_policy_authority_ref="authority:test-v1",
        api_lifecycle_purpose_version="purpose:test-v1",
        api_lifecycle_consent_version="consent:test-v1",
        api_lifecycle_receipt_hmac_secret="x" * 32,
        api_lifecycle_retention_days="",
    )
    assert configured.api_lifecycle_retention_days is None
