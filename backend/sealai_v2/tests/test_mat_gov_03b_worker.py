from __future__ import annotations

import json

from sqlalchemy import select

from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.models import (
    V2MaterialShadowEvaluation,
    V2MaterialShadowEvaluationMatch,
    V2MaterialShadowEvaluationRef,
    V2MaterialShadowOutbox,
)
from sealai_v2.material_shadow.cache import (
    RedisShadowCache,
    ShadowCacheUnavailable,
    cache_key,
)
from sealai_v2.material_shadow.hmac_refs import ShadowHmacKeyring
from sealai_v2.material_shadow.worker import MaterialShadowWorker
from sealai_v2.tests.test_mat_gov_03b_persistence import (
    IDENTITY,
    NOW,
    _binding,
    _database,
    _input,
    _keyring,
)


class DictCache:
    def __init__(self, *, fail=False) -> None:
        self.values: dict[str, dict] = {}
        self.fail = fail

    def get(self, key: str):
        if self.fail:
            raise ShadowCacheUnavailable("synthetic cache outage")
        return self.values.get(key)

    def put(self, key: str, value: dict, *, ttl_s: int) -> None:
        if self.fail:
            raise ShadowCacheUnavailable("synthetic cache outage")
        assert ttl_s == 90 * 86400
        self.values[key] = value


def _two_jobs(tmp_path, *, name="worker.db"):
    _engine, factory, _rulesets, snapshot = _database(tmp_path, name)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    first = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="session-a",
        correlation_id="request-1",
        case_id="case-raw-1",
        decision_id="decision-raw-1",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
    )
    second = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="session-a",
        correlation_id="request-2",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:06:00.000000Z",
    )
    return factory, first, second


def test_worker_preserves_session_order_and_persists_reference_only_results(
    tmp_path,
) -> None:
    factory, first, second = _two_jobs(tmp_path)
    cache = DictCache()
    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=cache,
        keyring=_keyring(),
    )
    first_pass = worker.drain_once(now="2026-07-17T12:07:00.000000Z", batch_size=50)
    assert first_pass.claimed == first_pass.evaluated == 1
    with factory() as session:
        first_row = session.get(V2MaterialShadowOutbox, first.job_id)
        second_row = session.get(V2MaterialShadowOutbox, second.job_id)
        assert first_row.status == "done"
        assert second_row.status == "pending"
    second_pass = worker.drain_once(now="2026-07-17T12:08:00.000000Z", batch_size=50)
    assert second_pass.claimed == second_pass.evaluated == 1
    with factory() as session:
        evaluations = session.scalars(
            select(V2MaterialShadowEvaluation).order_by(
                V2MaterialShadowEvaluation.created_at
            )
        ).all()
        matches = session.scalars(select(V2MaterialShadowEvaluationMatch)).all()
        refs = session.scalars(select(V2MaterialShadowEvaluationRef)).all()
    assert len(evaluations) == 2
    assert evaluations[0].cache_hit is False
    assert evaluations[1].cache_hit is True
    assert all(item.authority == "SHADOW_NON_AUTHORITATIVE" for item in evaluations)
    assert all(item.positive_statement_allowed is False for item in evaluations)
    assert [match.rule_ref for match in matches] == ["MR-TEST-001", "MR-TEST-001"]
    assert sorted(ref.ref_kind for ref in refs) == [
        "CASE",
        "DECISION",
        "REQUEST",
        "REQUEST",
        "SESSION",
        "SESSION",
    ]
    assert all(ref.authority == "SHADOW_NON_AUTHORITATIVE" for ref in refs)
    assert all(ref.hmac_key_id == "key-v1" for ref in refs)
    persisted = json.dumps(
        [
            {
                "rule_ref": match.rule_ref,
                "verdict": match.verdict,
                "source_ref": match.source_ref,
            }
            for match in matches
        ]
    )
    assert "Synthetic condition" not in persisted
    assert "statement" not in persisted
    assert "case-raw-1" not in json.dumps([ref.ref_hmac for ref in refs])
    assert "decision-raw-1" not in json.dumps([ref.ref_hmac for ref in refs])


def test_cache_outage_retries_first_job_without_reordering_second(tmp_path) -> None:
    factory, first, second = _two_jobs(tmp_path, name="cache-outage.db")
    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(fail=True),
        keyring=_keyring(),
        max_attempts=3,
    )
    outcome = worker.drain_once(now="2026-07-17T12:07:00.000000Z", batch_size=50)
    assert outcome.claimed == 1
    assert outcome.retried == 1
    with factory() as session:
        first_row = session.get(V2MaterialShadowOutbox, first.job_id)
        second_row = session.get(V2MaterialShadowOutbox, second.job_id)
        assert first_row.status == "pending"
        assert first_row.stable_error_code == "SHADOW_CACHE_UNAVAILABLE"
        assert first_row.next_attempt_at == "2026-07-17T12:07:05.000000Z"
        assert second_row.status == "pending"
        assert second_row.attempts == 0


def test_unknown_hmac_key_id_fails_closed_without_exception_text(tmp_path) -> None:
    factory, first, _second = _two_jobs(tmp_path, name="missing-key.db")
    rotated = ShadowHmacKeyring({"key-v2": "c" * 32}, active_key_id="key-v2")
    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=rotated,
    )
    outcome = worker.drain_once(now="2026-07-17T12:07:00.000000Z", batch_size=1)
    assert outcome.failed == 1
    with factory() as session:
        row = session.get(V2MaterialShadowOutbox, first.job_id)
        assert row.status == "failed"
        assert row.stable_error_code == "SHADOW_HMAC_KEY_UNAVAILABLE"
        assert "unknown" not in row.stable_error_code.lower()


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value


def test_cache_namespace_is_snapshot_tenant_key_version_bound_and_text_free(
    tmp_path,
) -> None:
    _factory, first, _second = _two_jobs(tmp_path, name="cache-contract.db")
    key = cache_key(pin=first.pin, input_fingerprint="f" * 64)
    assert key.startswith("sealai:material-shadow:v1:key-v1:")
    assert first.pin.snapshot_id in key
    assert first.pin.content_sha256 in key
    assert "session-a" not in key
    redis = FakeRedis()
    cache = RedisShadowCache(redis)
    value = {
        "evaluation_state": "evaluated",
        "verdict": "bedingt",
        "decisive_ref": "MR-TEST-001",
        "matches": [
            {
                "rule_ref": "MR-TEST-001",
                "verdict": "bedingt",
                "source_ref": "matrix-cell:MR-TEST-001",
            }
        ],
        "result_sha256": "a" * 64,
        "stable_error_code": "none",
    }
    cache.put(key, value, ttl_s=60)
    assert cache.get(key) == value
    assert "prompt" not in next(iter(redis.values.values())).lower()
    forbidden = {**value, "matches": [{**value["matches"][0], "statement": "raw"}]}
    try:
        cache.put(key, forbidden, ttl_s=60)
    except ShadowCacheUnavailable:
        pass
    else:
        raise AssertionError("cache accepted a rule statement")

    invalid_values = (
        {**value, "verdict": "unknown"},
        {
            **value,
            "matches": [{**value["matches"][0], "source_ref": "matrix-cell:OTHER"}],
        },
        {**value, "decisive_ref": "OTHER"},
        {**value, "result_sha256": "not-a-hash"},
        {**value, "stable_error_code": "SHADOW_INTERNAL_ERROR"},
    )
    for invalid in invalid_values:
        try:
            cache.put(key, invalid, ttl_s=60)
        except ShadowCacheUnavailable:
            continue
        raise AssertionError("cache accepted a non-canonical shadow projection")
