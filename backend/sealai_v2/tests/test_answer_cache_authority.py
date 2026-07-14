from __future__ import annotations

import pytest
from pydantic import ValidationError

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Answer
from sealai_v2.orchestration.answer_cache import (
    InProcessExactAnswerCache,
    build_answer_cache_namespace,
    exact_answer_key,
)


EPOCH_A = "sha256:" + "a" * 64
EPOCH_B = "sha256:" + "b" * 64


def namespace(epoch: str) -> str:
    return build_answer_cache_namespace(
        authority_epoch=epoch,
        knowledge_version="knowledge.v1",
        policy_version="policy.v1",
        answer_contract_version="answer.v2",
        model_identity="provider/model",
        structured_answers=True,
    )


def answer(value: str) -> Answer:
    return Answer(text=value, model="synthetic")


def test_authority_lifecycle_rolls_namespace_and_forces_miss() -> None:
    cache = InProcessExactAnswerCache()
    tenant = "tenant-a"
    old_key = exact_answer_key(
        tenant_id=tenant, question="Was ist PTFE?", namespace=namespace(EPOCH_A)
    )
    cache.put(tenant_id=tenant, key=old_key, answer=answer("old authority"))

    for event in ("quarantine", "revocation", "expiry", "replacement"):
        new_key = exact_answer_key(
            tenant_id=tenant,
            question="Was ist PTFE?",
            namespace=namespace(EPOCH_B),
        )
        assert new_key != old_key, event
        assert cache.get(tenant_id=tenant, key=new_key) is None, event


@pytest.mark.parametrize(("first", "second"), [("Si", "SI"), ("Pu", "PU")])
def test_technical_case_distinctions_never_share_a_key(first: str, second: str) -> None:
    assert exact_answer_key(
        tenant_id="tenant-a", question=first, namespace=namespace(EPOCH_A)
    ) != exact_answer_key(
        tenant_id="tenant-a", question=second, namespace=namespace(EPOCH_A)
    )


def test_cache_has_mandatory_ttl_and_aggregate_metrics() -> None:
    now = [10.0]
    cache = InProcessExactAnswerCache(ttl_s=5, clock=lambda: now[0])
    cache.put(tenant_id="tenant-a", key="key-a", answer=answer("value"))
    assert cache.get(tenant_id="tenant-a", key="key-a") == answer("value")
    now[0] = 15.0
    assert cache.get(tenant_id="tenant-a", key="key-a") is None
    metrics = cache.metrics()
    assert metrics.entries == 0
    assert metrics.hits == 1
    assert metrics.misses == 1
    assert metrics.expirations == 1
    assert metrics.hit_rate == 0.5


def test_per_tenant_bound_prevents_uncontrolled_namespace_growth() -> None:
    cache = InProcessExactAnswerCache(max_entries=4, max_entries_per_tenant=2)
    for index in range(3):
        cache.put(
            tenant_id="tenant-a",
            key=f"key-{index}",
            answer=answer(str(index)),
        )
    cache.put(tenant_id="tenant-b", key="key-b", answer=answer("b"))

    assert cache.get(tenant_id="tenant-a", key="key-0") is None
    assert cache.get(tenant_id="tenant-a", key="key-1") is not None
    assert cache.get(tenant_id="tenant-a", key="key-2") is not None
    assert cache.get(tenant_id="tenant-b", key="key-b") is not None
    assert cache.metrics().entries == 3
    assert cache.metrics().capacity_evictions == 1


def test_tenant_invalidation_cannot_remove_another_tenant() -> None:
    cache = InProcessExactAnswerCache()
    cache.put(tenant_id="tenant-a", key="same", answer=answer("a"))
    cache.put(tenant_id="tenant-b", key="same", answer=answer("b"))

    assert cache.invalidate_tenant("tenant-a") == 1
    assert cache.get(tenant_id="tenant-a", key="same") is None
    assert cache.get(tenant_id="tenant-b", key="same") == answer("b")


@pytest.mark.parametrize("ttl", [0, -1, float("inf"), 86401])
def test_unbounded_or_invalid_ttl_is_rejected(ttl: float) -> None:
    with pytest.raises(ValueError, match="TTL"):
        InProcessExactAnswerCache(ttl_s=ttl)


@pytest.mark.parametrize("epoch", ["", "latest", "sha256:abc", "sha256:" + "G" * 64])
def test_namespace_rejects_noncanonical_authority_epoch(epoch: str) -> None:
    with pytest.raises(ValueError, match="authority_epoch"):
        namespace(epoch)


def test_settings_fail_closed_when_cache_has_no_authority_epoch() -> None:
    with pytest.raises(ValidationError, match="knowledge_authority_epoch"):
        Settings(execution_policy_enabled=True, exact_answer_cache_enabled=True)


def test_settings_reject_cache_without_execution_policy() -> None:
    with pytest.raises(ValidationError, match="execution_policy_enabled"):
        Settings(
            exact_answer_cache_enabled=True,
            knowledge_authority_epoch=EPOCH_A,
        )


def test_real_pipeline_refuses_even_a_well_formed_static_epoch() -> None:
    with pytest.raises(ValidationError, match="atomically coupled"):
        Settings(
            execution_policy_enabled=True,
            exact_answer_cache_enabled=True,
            knowledge_authority_epoch=EPOCH_A,
        )
