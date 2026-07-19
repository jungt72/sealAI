from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from threading import Barrier, Event
import time

import pytest
from sqlalchemy import func, inspect, select, text
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
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.material_shadow.hmac_refs import TENANT_REF_DOMAIN
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
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_mat_gov_03b_test")


def _clear_database(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


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


def _attempt_cross_tenant_capture(
    repository,
    binding,
    identity: VerifiedIdentity,
    barrier: Barrier,
):
    barrier.wait(timeout=10)
    return repository.persist_pin_and_job(
        binding=binding,
        identity=identity,
        session_id="same-cross-tenant-session",
        correlation_id=f"request-{identity.tenant_id}",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:36:00.000000Z",
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


def _attempt_worker_claim(worker: MaterialShadowWorker, barrier: Barrier):
    barrier.wait(timeout=10)
    return worker._claim(batch_size=1)


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
    _clear_database(engine)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0019", "20260718_0019")

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

    orphan = repository.persist_pin_and_job(
        binding=winning,
        identity=IDENTITY,
        session_id="shared-concurrent-session",
        correlation_id="request-orphan",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:42:00.000000Z",
    )
    crashed_worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
        max_attempts=2,
        claim_timeout_s=1,
        worker_id="postgres-worker-crashed",
    )
    assert crashed_worker._claim(batch_size=1) == ([orphan.job_id], 0)
    time.sleep(1.1)

    reclaimers = (
        MaterialShadowWorker(
            session_factory=factory,
            cache=DictCache(),
            keyring=_keyring(),
            max_attempts=2,
            claim_timeout_s=1,
            worker_id="postgres-reclaimer-a",
        ),
        MaterialShadowWorker(
            session_factory=factory,
            cache=DictCache(),
            keyring=_keyring(),
            max_attempts=2,
            claim_timeout_s=1,
            worker_id="postgres-reclaimer-b",
        ),
    )
    reclaim_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        reclaim_results = list(
            executor.map(
                lambda worker: _attempt_worker_claim(worker, reclaim_barrier),
                reclaimers,
            )
        )
    assert sum(len(job_ids) for job_ids, _exhausted in reclaim_results) == 1
    assert all(exhausted == 0 for _job_ids, exhausted in reclaim_results)
    with factory() as session:
        reclaimed = session.get(V2MaterialShadowOutbox, orphan.job_id)
    assert reclaimed is not None
    assert reclaimed.status == "processing"
    assert reclaimed.attempts == 2
    assert reclaimed.lease_owner in {
        "postgres-reclaimer-a",
        "postgres-reclaimer-b",
    }

    time.sleep(1.1)
    terminal = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
        max_attempts=2,
        claim_timeout_s=1,
        worker_id="postgres-terminalizer",
    ).drain_once(now="2026-07-17T12:43:00.000000Z", batch_size=1)
    assert terminal.claimed == 0
    assert terminal.failed == 1
    with factory() as session:
        exhausted = session.get(V2MaterialShadowOutbox, orphan.job_id)
    assert exhausted is not None
    assert exhausted.status == "failed"
    assert exhausted.attempts == 2
    assert exhausted.stable_error_code == "SHADOW_LEASE_ATTEMPTS_EXHAUSTED"
    assert exhausted.lease_owner is None
    assert exhausted.lease_expires_at is None

    canary_old = _binding(
        snapshot,
        suffix="8",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,), key_id="key-old"
        ),
        hmac_key_id="key-old",
    )
    canary_active = _binding(
        snapshot,
        suffix="9",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,), key_id="key-v1"
        ),
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

    cross_tenant_barrier = Barrier(2)
    cross_tenant_identities = (
        VerifiedIdentity("tenant-cross-a", "session-a", "subject:cross-a"),
        VerifiedIdentity("tenant-cross-b", "session-b", "subject:cross-b"),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        cross_tenant = list(
            executor.map(
                lambda identity: _attempt_cross_tenant_capture(
                    repository, winning, identity, cross_tenant_barrier
                ),
                cross_tenant_identities,
            )
        )
    assert len({item.session_version_id for item in cross_tenant}) == 2
    assert [item.sequence_no for item in cross_tenant] == [1, 1]


def test_real_postgres_adoption_is_exact_and_never_rewrites_functions() -> None:
    _assert_dedicated_local_database(POSTGRES_URL)
    engine = make_engine(POSTGRES_URL)
    _clear_database(engine)
    _upgrade_engine(engine)
    with engine.begin() as connection:
        before = (
            connection.execute(
                text(
                    "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' AND p.proname LIKE 'sealai_mat_gov_%' "
                    "ORDER BY p.proname"
                )
            )
            .scalars()
            .all()
        )
        connection.execute(text("DROP TABLE alembic_version"))
    _upgrade_engine(engine)
    with engine.connect() as connection:
        after = (
            connection.execute(
                text(
                    "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' AND p.proname LIKE 'sealai_mat_gov_%' "
                    "ORDER BY p.proname"
                )
            )
            .scalars()
            .all()
        )
    assert after == before

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
        connection.execute(
            text(
                "CREATE FUNCTION sealai_mat_gov_03b_reject_mutation(integer) "
                "RETURNS integer AS $$ SELECT $1 $$ LANGUAGE sql IMMUTABLE"
            )
        )
    with pytest.raises(RuntimeError, match="structural adoption fingerprint mismatch"):
        _upgrade_engine(engine)

    with engine.begin() as connection:
        connection.execute(
            text("DROP FUNCTION sealai_mat_gov_03b_reject_mutation(integer)")
        )
    _upgrade_engine(engine)

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION sealai_mat_gov_03b_reject_mutation() "
                "RETURNS trigger AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql"
            )
        )
    with pytest.raises(RuntimeError, match="structural adoption fingerprint mismatch"):
        _upgrade_engine(engine)
