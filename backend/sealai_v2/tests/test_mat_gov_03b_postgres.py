from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from threading import Barrier, Event

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.migrate import _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialShadowBinding,
    V2MaterialShadowBindingEvent,
    V2MaterialShadowOutbox,
)
from sealai_v2.core.material_shadow import ShadowScopeKind
from sealai_v2.material_shadow.worker import MaterialShadowWorker
from sealai_v2.tests.test_mat_gov_03b_persistence import (
    IDENTITY,
    NOW,
    RULESET_ID,
    _binding,
    _input,
    _keyring,
    _payload,
)
from sealai_v2.tests.test_mat_gov_03b_worker import DictCache


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def _assert_dedicated_local_database(url: str) -> None:
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert (parsed.database or "").startswith("sealai_mat_gov_03b_test")


def _attempt_binding(repository, binding, barrier: Barrier) -> str:
    barrier.wait(timeout=10)
    try:
        repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    except (IntegrityError, DBAPIError):
        return "rejected"
    return "created"


def _attempt_capture(repository, binding, correlation_id: str, barrier: Barrier):
    barrier.wait(timeout=10)
    return repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="shared-concurrent-session",
        correlation_id=correlation_id,
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:35:00.000000Z",
    )


def _attempt_canary_binding(repository, binding, barrier: Barrier) -> str:
    barrier.wait(timeout=10)
    try:
        repository.create_binding(
            binding,
            identity=IDENTITY,
            created_at=NOW,
            hmac_keyring=_keyring(),
        )
    except (ValueError, IntegrityError, DBAPIError):
        return "rejected"
    return "created"


class _BlockingCache(DictCache):
    def __init__(self) -> None:
        super().__init__()
        self.entered = Event()
        self.release = Event()

    def get(self, key: str):
        self.entered.set()
        assert self.release.wait(timeout=10)
        return super().get(key)


def test_real_postgres_16_serializes_overlap_and_session_sequence() -> None:
    _assert_dedicated_local_database(POSTGRES_URL)
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260717_0013", "20260717_0013")

    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    snapshot = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_payload(),
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    repository = MaterialShadowRepository(factory)

    first = _binding(snapshot, suffix="2")
    overlapping = _binding(
        snapshot,
        suffix="6",
        start="2026-07-17T12:30:00.000000Z",
        end="2026-07-17T13:30:00.000000Z",
    )
    binding_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: _attempt_binding(repository, item, binding_barrier),
                (first, overlapping),
            )
        )
    assert sorted(results) == ["created", "rejected"]
    with factory() as session:
        binding = session.scalar(select(V2MaterialShadowBinding))
        assert (
            session.scalar(select(func.count(V2MaterialShadowBinding.binding_id))) == 1
        )
        assert (
            session.scalar(select(func.count(V2MaterialShadowBindingEvent.event_id)))
            == 1
        )
    assert binding is not None
    winning = repository.binding_from_row(binding)

    capture_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        captures = list(
            executor.map(
                lambda correlation: _attempt_capture(
                    repository, winning, correlation, capture_barrier
                ),
                ("request-a", "request-b"),
            )
        )
    assert sorted(result.sequence_no for result in captures) == [1, 2]
    assert len({result.session_version_id for result in captures}) == 1
    with factory() as session:
        rows = session.scalars(
            select(V2MaterialShadowOutbox).order_by(V2MaterialShadowOutbox.sequence_no)
        ).all()
    assert [row.sequence_no for row in rows] == [1, 2]
    assert len({row.idempotency_key for row in rows}) == 2

    blocking_cache = _BlockingCache()
    first_worker = MaterialShadowWorker(
        session_factory=factory,
        cache=blocking_cache,
        keyring=_keyring(),
    )
    second_worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
    )
    with factory() as session:
        database_before_claim = session.scalar(select(func.clock_timestamp()))
    with ThreadPoolExecutor(max_workers=1) as executor:
        first_drain = executor.submit(
            first_worker.drain_once,
            now="2026-07-17T12:40:00.000000Z",
            batch_size=50,
        )
        assert blocking_cache.entered.wait(timeout=10)
        with factory() as session:
            leased = session.scalar(
                select(V2MaterialShadowOutbox).where(
                    V2MaterialShadowOutbox.status == "processing"
                )
            )
            database_after_claim = session.scalar(select(func.clock_timestamp()))
        assert leased is not None
        assert leased.status == "processing"
        assert leased.attempts == 1
        assert leased.lease_owner is not None
        assert leased.claimed_at is not None
        assert leased.lease_expires_at is not None
        claimed_at = leased.claimed_at.replace("Z", "+00:00")
        lease_expires_at = leased.lease_expires_at.replace("Z", "+00:00")
        claimed = datetime.fromisoformat(claimed_at)
        expires = datetime.fromisoformat(lease_expires_at)
        assert database_before_claim <= claimed <= database_after_claim
        assert (expires - claimed).total_seconds() == 60
        blocked_drain = second_worker.drain_once(
            now="2026-07-17T12:40:00.000000Z", batch_size=50
        )
        assert blocked_drain.claimed == 0
        blocking_cache.release.set()
        assert first_drain.result(timeout=10).evaluated == 1
    final_drain = second_worker.drain_once(
        now="2026-07-17T12:41:00.000000Z", batch_size=50
    )
    assert final_drain.claimed == final_drain.evaluated == 1
    with factory() as session:
        completed_jobs = session.scalars(
            select(V2MaterialShadowOutbox).order_by(V2MaterialShadowOutbox.sequence_no)
        ).all()
    assert [row.status for row in completed_jobs] == ["done", "done"]
    assert [row.attempts for row in completed_jobs] == [1, 1]
    assert all(row.lease_owner is None for row in completed_jobs)
    assert all(row.lease_expires_at is None for row in completed_jobs)

    tenant_value = f"tenant\x00{IDENTITY.tenant_id}"
    canary_old = _binding(
        snapshot,
        suffix="8",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest(tenant_value, key_id="key-old"),
        hmac_key_id="key-old",
    )
    canary_active = _binding(
        snapshot,
        suffix="9",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest(tenant_value, key_id="key-v1"),
        hmac_key_id="key-v1",
    )
    canary_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        canary_results = list(
            executor.map(
                lambda item: _attempt_canary_binding(repository, item, canary_barrier),
                (canary_old, canary_active),
            )
        )
    assert sorted(canary_results) == ["created", "rejected"]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(V2MaterialShadowBinding.binding_id)).where(
                    V2MaterialShadowBinding.scope_kind
                    == ShadowScopeKind.TENANT_CANARY.value
                )
            )
            == 1
        )
