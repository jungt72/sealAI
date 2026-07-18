from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from sealai_v2.core.material_shadow import (
    ShadowBindingEventType,
    ShadowEnvironment,
    ShadowReadinessState,
    ShadowScopeKind,
)
from sealai_v2.core.material_rulesets import (
    MaterialRulesetErrorCode,
    MaterialRulesetIntegrityError,
)
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.material_shadow.reconciliation import ShadowReconciler
from sealai_v2.material_shadow.hmac_refs import TENANT_REF_DOMAIN
from sealai_v2.material_shadow.resolver import (
    MaterialShadowResolver,
    ResolvedShadowSelection,
    ShadowRuntimeCompatibility,
)
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.tests.test_mat_gov_03b_persistence import (
    IDENTITY,
    NOW,
    _binding,
    _database,
    _keyring,
)


def _runtime(**changes) -> ShadowRuntimeCompatibility:
    values = {
        "environment": ShadowEnvironment.STAGING,
        "domain_pack_id": "material.test.v1",
        "domain_pack_version": "1.0.0",
        "evaluator_version": "MAT-GOV-03B.eval.v1",
        "kernel_version": "MAT-GOV-02.kernel.v1",
        "runtime_profile_sha256": "3" * 64,
        "build_git_sha": "4" * 40,
        "build_tree_hash": "5" * 40,
    }
    values.update(changes)
    return ShadowRuntimeCompatibility(**values)


def test_resolver_is_pointerless_and_returns_zero_or_exact_binding(tmp_path) -> None:
    _engine, factory, rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    resolver = MaterialShadowResolver(
        repository=repository, rulesets=rulesets, keyring=_keyring()
    )
    assert (
        resolver.resolve(
            enabled=False, identity=IDENTITY, runtime=_runtime(), now=NOW
        ).state
        is ShadowReadinessState.DISABLED
    )
    assert (
        resolver.resolve(
            enabled=True, identity=IDENTITY, runtime=_runtime(), now=NOW
        ).state
        is ShadowReadinessState.NO_BINDING
    )
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    resolved = resolver.resolve(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now="2026-07-17T12:05:00.000000Z",
    )
    assert resolved.state is ShadowReadinessState.READY
    assert resolved.binding == binding


def test_tenant_canary_precedes_global_and_invalid_canary_never_falls_back(
    tmp_path,
) -> None:
    _engine, factory, rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    global_binding = _binding(snapshot, suffix="2")
    canary = _binding(
        snapshot,
        suffix="6",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,), key_id="key-v1"
        ),
        hmac_key_id="key-v1",
        evaluator_version="incompatible.eval.v1",
    )
    repository.create_binding(global_binding, identity=IDENTITY, created_at=NOW)
    repository.create_binding(
        canary, identity=IDENTITY, created_at=NOW, hmac_keyring=_keyring()
    )
    resolver = MaterialShadowResolver(
        repository=repository, rulesets=rulesets, keyring=_keyring()
    )
    result = resolver.resolve(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now="2026-07-17T12:05:00.000000Z",
    )
    assert result.state is ShadowReadinessState.EVALUATOR_INCOMPATIBLE
    assert result.binding is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("domain_pack_version", "2.0.0"),
        ("evaluator_version", "other.eval.v1"),
        ("kernel_version", "other.kernel.v1"),
        ("runtime_profile_sha256", "9" * 64),
        ("build_git_sha", "8" * 40),
        ("build_tree_hash", "7" * 40),
    ],
)
def test_every_runtime_binding_drift_is_incompatible(tmp_path, field, value) -> None:
    _engine, factory, rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    repository.create_binding(_binding(snapshot), identity=IDENTITY, created_at=NOW)
    result = MaterialShadowResolver(
        repository=repository, rulesets=rulesets, keyring=_keyring()
    ).resolve(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(**{field: value}),
        now="2026-07-17T12:05:00.000000Z",
    )
    assert result.state is ShadowReadinessState.EVALUATOR_INCOMPATIBLE
    assert result.binding is None


def test_snapshot_hash_or_schema_integrity_drift_never_returns_a_binding(
    tmp_path,
) -> None:
    _engine, factory, rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    repository.create_binding(_binding(snapshot), identity=IDENTITY, created_at=NOW)

    class DriftedRulesets:
        def load_snapshot(self, _snapshot_id):
            return SimpleNamespace(
                content_sha256="9" * 64,
                payload=SimpleNamespace(domain_pack_id="material.test.v1"),
            )

    result = MaterialShadowResolver(
        repository=repository,
        rulesets=DriftedRulesets(),  # type: ignore[arg-type]
        keyring=_keyring(),
    ).resolve(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now="2026-07-17T12:05:00.000000Z",
    )
    assert result.state is ShadowReadinessState.SNAPSHOT_DRIFT
    assert result.binding is None

    class InvalidSchemaRulesets:
        def load_snapshot(self, _snapshot_id):
            raise MaterialRulesetIntegrityError(
                MaterialRulesetErrorCode.UNKNOWN_SCHEMA,
                "synthetic schema drift",
            )

    schema_result = MaterialShadowResolver(
        repository=repository,
        rulesets=InvalidSchemaRulesets(),  # type: ignore[arg-type]
        keyring=_keyring(),
    ).resolve(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now="2026-07-17T12:05:00.000000Z",
    )
    assert schema_result.state is ShadowReadinessState.SNAPSHOT_DRIFT
    assert schema_result.binding is None


def test_terminal_canary_never_falls_back_to_global(tmp_path) -> None:
    _engine, factory, rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    repository.create_binding(
        _binding(snapshot, suffix="2"), identity=IDENTITY, created_at=NOW
    )
    canary = _binding(
        snapshot,
        suffix="6",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,), key_id="key-v1"
        ),
        hmac_key_id="key-v1",
    )
    repository.create_binding(
        canary, identity=IDENTITY, created_at=NOW, hmac_keyring=_keyring()
    )
    repository.terminate_binding(
        canary.binding_id,
        event_type=ShadowBindingEventType.REVOKED,
        identity=IDENTITY,
        reason="MAT-GOV-03B.synthetic-canary-stop",
        effective_at="2026-07-17T12:01:00.000000Z",
        created_at="2026-07-17T12:01:00.000000Z",
        hmac_keyring=_keyring(),
    )
    result = MaterialShadowResolver(
        repository=repository, rulesets=rulesets, keyring=_keyring()
    ).resolve(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now="2026-07-17T12:05:00.000000Z",
    )
    assert result.state is ShadowReadinessState.NO_BINDING


def test_reconciliation_lease_expires_without_last_known_good(tmp_path) -> None:
    _engine, factory, rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    repository.create_binding(_binding(snapshot), identity=IDENTITY, created_at=NOW)
    clock = [100.0]
    reconciler = ShadowReconciler(
        MaterialShadowResolver(
            repository=repository, rulesets=rulesets, keyring=_keyring()
        ),
        keyring=_keyring(),
        poll_s=15,
        lease_s=60,
        process_ref="process-a",
        monotonic=lambda: clock[0],
    )
    first = reconciler.reconcile(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now_utc="2026-07-17T12:05:00.000000Z",
    )
    assert first.state is ShadowReadinessState.READY
    clock[0] = 170.0

    class FailingResolver:
        def resolve(self, **_kwargs):
            raise RuntimeError("database unavailable")

    reconciler._resolver = FailingResolver()  # type: ignore[assignment]
    outcome = reconciler.reconcile(
        enabled=True,
        identity=IDENTITY,
        runtime=_runtime(),
        now_utc="2026-07-17T12:06:10.000000Z",
    )
    assert outcome.state is ShadowReadinessState.EXPIRED_LEASE


class _RecordingResolver:
    def __init__(self, selection: ResolvedShadowSelection) -> None:
        self.selection = selection
        self.calls: list[tuple[str, ShadowRuntimeCompatibility]] = []

    def resolve(self, *, identity, runtime, **_kwargs):
        self.calls.append((identity.tenant_id, runtime))
        return self.selection


def test_reconciliation_lease_is_partitioned_by_tenant_and_runtime() -> None:
    resolver = _RecordingResolver(
        ResolvedShadowSelection(ShadowReadinessState.NO_BINDING)
    )
    reconciler = ShadowReconciler(
        resolver,  # type: ignore[arg-type]
        keyring=_keyring(),
        process_ref="partition-test",
        monotonic=lambda: 100.0,
    )
    tenant_b = VerifiedIdentity("tenant-b", "session-b", "subject:b")
    variants = (
        _runtime(runtime_profile_sha256="6" * 64),
        _runtime(build_git_sha="7" * 40),
        _runtime(build_tree_hash="8" * 40),
        _runtime(domain_pack_id="material.other.v1"),
        _runtime(domain_pack_version="2.0.0"),
        _runtime(evaluator_version="MAT-GOV-03B.eval.v2"),
        _runtime(kernel_version="MAT-GOV-02.kernel.v2"),
        _runtime(environment=ShadowEnvironment.PRODUCTION),
    )
    base = reconciler.reconcile(
        enabled=True, identity=IDENTITY, runtime=_runtime(), now_utc=NOW
    )
    assert base.state is ShadowReadinessState.NO_BINDING
    assert (
        reconciler.reconcile(
            enabled=True, identity=IDENTITY, runtime=_runtime(), now_utc=NOW
        )
        == base
    )
    reconciler.reconcile(
        enabled=True, identity=tenant_b, runtime=_runtime(), now_utc=NOW
    )
    for runtime in variants:
        reconciler.reconcile(
            enabled=True, identity=IDENTITY, runtime=runtime, now_utc=NOW
        )
    assert len(resolver.calls) == 2 + len(variants)


def test_reconciliation_reclaims_changed_scope_and_binding_after_poll() -> None:
    snapshot = SimpleNamespace(snapshot_id="mss_" + "1" * 64, content_sha256="2" * 64)
    global_binding = _binding(snapshot, suffix="3")
    canary_binding = _binding(
        snapshot,
        suffix="4",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=_keyring().digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,)
        ),
        hmac_key_id="key-v1",
    )
    resolver = _RecordingResolver(
        ResolvedShadowSelection(ShadowReadinessState.READY, global_binding)
    )
    clock = [100.0]
    reconciler = ShadowReconciler(
        resolver,  # type: ignore[arg-type]
        keyring=_keyring(),
        poll_s=15,
        lease_s=60,
        process_ref="binding-change",
        monotonic=lambda: clock[0],
    )
    first = reconciler.reconcile(
        enabled=True, identity=IDENTITY, runtime=_runtime(), now_utc=NOW
    )
    assert first.binding == global_binding
    resolver.selection = ResolvedShadowSelection(
        ShadowReadinessState.READY, canary_binding
    )
    clock[0] = 116.0
    second = reconciler.reconcile(
        enabled=True, identity=IDENTITY, runtime=_runtime(), now_utc=NOW
    )
    assert second.binding == canary_binding
    assert len(resolver.calls) == 2


def test_reconciliation_is_thread_safe_and_flag_off_creates_no_lease(
    monkeypatch,
) -> None:
    resolver = _RecordingResolver(
        ResolvedShadowSelection(ShadowReadinessState.NO_BINDING)
    )
    keyring = _keyring()
    reconciler = ShadowReconciler(
        resolver,  # type: ignore[arg-type]
        keyring=keyring,
        process_ref="parallel",
        monotonic=lambda: 100.0,
    )
    original = keyring.digest_fields
    monkeypatch.setattr(
        keyring,
        "digest_fields",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("flag-off touched HMAC")
        ),
    )
    assert (
        reconciler.reconcile(
            enabled=False, identity=IDENTITY, runtime=_runtime(), now_utc=NOW
        ).state
        is ShadowReadinessState.DISABLED
    )
    monkeypatch.setattr(keyring, "digest_fields", original)
    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(
            executor.map(
                lambda _index: reconciler.reconcile(
                    enabled=True,
                    identity=IDENTITY,
                    runtime=_runtime(),
                    now_utc=NOW,
                ),
                range(16),
            )
        )
    assert all(item.state is ShadowReadinessState.NO_BINDING for item in outcomes)
    assert len(resolver.calls) == 1
