from __future__ import annotations

import json

from sealai_v2.config.runtime_profile import (
    canonical_profile_json,
    runtime_profile,
    runtime_profile_hash,
)
from sealai_v2.config.settings import Settings


def test_profile_is_stable_and_secret_free():
    settings = Settings(
        openai_api_key="do-not-leak",
        database_url="postgresql://user:password@db/name",
        qdrant_api_key="also-secret",
        legal_ip_hash_pepper="private-pepper",
    )
    rendered = canonical_profile_json(settings)
    assert "do-not-leak" not in rendered
    assert "password" not in rendered
    assert "also-secret" not in rendered
    assert "private-pepper" not in rendered
    assert json.loads(rendered) == runtime_profile(settings)
    assert runtime_profile_hash(settings) == runtime_profile_hash(settings)


def test_behavior_change_changes_hash_but_operational_change_does_not():
    baseline = runtime_profile_hash(Settings())
    assert runtime_profile_hash(Settings(verify_enabled=False)) != baseline
    assert runtime_profile_hash(Settings(l1_model="another-model")) != baseline
    assert runtime_profile_hash(Settings(request_timeout_s=42.0)) == baseline
    assert runtime_profile_hash(Settings(outbox_batch_size=5)) == baseline


def test_semantic_router_model_and_activation_are_release_bound():
    baseline = runtime_profile_hash(Settings())

    assert runtime_profile_hash(Settings(semantic_router_enabled=True)) != baseline
    assert runtime_profile_hash(Settings(router_model="another-router")) != baseline


def test_equivalent_provider_override_is_normalized():
    implicit = runtime_profile_hash(Settings(provider="openai", l1_provider=None))
    explicit = runtime_profile_hash(Settings(provider="openai", l1_provider="openai"))
    assert implicit == explicit
