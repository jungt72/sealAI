from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from pydantic import ValidationError

from sealai_v2.config.runtime_profile import runtime_profile
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import (
    InputResolutionState,
    MaterialConstraintQuery,
    MediumCardinality,
    RelationState,
)
from sealai_v2.core.material_shadow import (
    ServerVerifiedCanonicalId,
    ShadowAuthority,
    ShadowBinding,
    ShadowContractError,
    ShadowEnvironment,
    ShadowErrorCode,
    ShadowMaterialRulesetPin,
    ShadowPurpose,
    ShadowReadinessState,
    ShadowScopeKind,
    assess_shadow_input_eligibility,
)
from sealai_v2.material_shadow.hmac_refs import (
    SESSION_REF_DOMAIN,
    TENANT_REF_DOMAIN,
    ShadowHmacKeyring,
    encode_hmac_fields,
)
from sealai_v2.material_shadow.sampling import decide_sampling


NOW = "2026-07-17T12:00:00.000000Z"
LATER = "2026-07-17T13:00:00.000000Z"
SNAPSHOT_ID = "mss_" + "1" * 64
HASH = "2" * 64
GIT = "3" * 40
TREE = "4" * 40


def _query(
    *,
    material_state=InputResolutionState.KNOWN,
    medium_state=InputResolutionState.KNOWN,
    cardinality=MediumCardinality.SINGLE,
    relation=RelationState.NOT_APPLICABLE,
    material="MAT.NBR",
    medium="MED.OIL",
) -> MaterialConstraintQuery:
    return MaterialConstraintQuery(
        material=material,
        medium=medium,
        material_state=material_state,
        medium_state=medium_state,
        medium_cardinality=cardinality,
        relation_state=relation,
    )


def _canonical(value: str) -> ServerVerifiedCanonicalId:
    return ServerVerifiedCanonicalId(value, "registry.material.v1")


def _binding(**changes) -> ShadowBinding:
    values = {
        "binding_id": "mshb_" + "5" * 32,
        "snapshot_id": SNAPSHOT_ID,
        "content_sha256": HASH,
        "environment": ShadowEnvironment.STAGING,
        "purpose": ShadowPurpose.MATERIAL_RULESET_SHADOW,
        "scope_kind": ShadowScopeKind.GLOBAL,
        "tenant_ref_hmac": None,
        "hmac_key_id": None,
        "domain_pack_id": "material.test.v1",
        "domain_pack_version": "1.0.0",
        "evaluator_version": "MAT-GOV-03B.eval.v1",
        "kernel_version": "MAT-GOV-02.kernel.v1",
        "runtime_profile_sha256": "6" * 64,
        "build_git_sha": GIT,
        "build_tree_hash": TREE,
        "valid_from": NOW,
        "valid_until": LATER,
        "creator_subject": "subject:owner",
        "reason": "MAT-GOV-03B.synthetic-binding",
        "sampling_policy_version": "MAT-GOV-03B.shadow.v1",
        "sampling_basis_points": 0,
    }
    values.update(changes)
    return ShadowBinding(**values)


def test_only_server_verified_single_medium_input_is_eligible() -> None:
    eligibility = assess_shadow_input_eligibility(
        _query(),
        material_id=_canonical("MAT.NBR"),
        medium_id=_canonical("MED.OIL"),
        domain_pack_id="material.test.v1",
        domain_pack_version="1.0.0",
    )
    assert eligibility.state is ShadowReadinessState.READY
    assert eligibility.eligible_input is not None
    assert eligibility.eligible_input.material_id.canonical_id == "MAT.NBR"


@pytest.mark.parametrize(
    "query",
    [
        _query(
            material_state=InputResolutionState.MISSING,
            material="",
        ),
        _query(
            material_state=InputResolutionState.UNKNOWN,
            material="unbekannt",
        ),
        _query(
            material_state=InputResolutionState.AMBIGUOUS,
            material="NBR oder FKM",
        ),
        _query(
            medium_state=InputResolutionState.MISSING,
            cardinality=MediumCardinality.NONE,
            relation=RelationState.UNDETERMINED,
            medium="",
        ),
        _query(
            medium_state=InputResolutionState.UNKNOWN,
            cardinality=MediumCardinality.UNKNOWN,
            relation=RelationState.UNDETERMINED,
            medium="Öl/Wasser",
        ),
        _query(
            cardinality=MediumCardinality.MULTIPLE,
            relation=RelationState.UNRESOLVED,
            medium="MED.OIL MED.WATER",
        ),
    ],
)
def test_unresolved_or_multi_media_inputs_never_become_shadow_jobs(query) -> None:
    outcome = assess_shadow_input_eligibility(
        query,
        material_id=None,
        medium_id=None,
        domain_pack_id=None,
        domain_pack_version=None,
    )
    assert outcome.state is ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT
    assert outcome.eligible_input is None


def test_resolved_multi_medium_input_is_still_ineligible_before_med_norm() -> None:
    outcome = assess_shadow_input_eligibility(
        _query(
            cardinality=MediumCardinality.MULTIPLE,
            relation=RelationState.RESOLVED,
            medium="MED.RESOLVED.SET",
        ),
        material_id=_canonical("MAT.NBR"),
        medium_id=_canonical("MED.RESOLVED.SET"),
        domain_pack_id="material.test.v1",
        domain_pack_version="1.0.0",
    )
    assert outcome.state is ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT
    assert outcome.eligible_input is None


@pytest.mark.parametrize("identifier", ["NBR/FKM", "OIL+WATER", "ÖL", "A B", ""])
def test_separator_or_free_text_is_not_a_canonical_id(identifier: str) -> None:
    with pytest.raises(ValueError, match="canonical structured identifier"):
        ServerVerifiedCanonicalId(identifier, "registry.material.v1")


def test_binding_scope_lifetime_and_sampling_are_closed() -> None:
    assert _binding().sampling_basis_points == 0
    with pytest.raises(ValueError, match="GLOBAL"):
        _binding(tenant_ref_hmac="8" * 64)
    canary = _binding(
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac="8" * 64,
        hmac_key_id="shadow-key-v1",
    )
    assert canary.tenant_ref_hmac == "8" * 64
    assert canary.hmac_key_id == "shadow-key-v1"
    with pytest.raises(ValueError, match="owner-frozen"):
        _binding(sampling_basis_points=1)
    with pytest.raises(ValueError, match="lifetime"):
        _binding(valid_until="2026-07-18T13:00:00.000000Z")
    with pytest.raises(ValueError, match="canonical structured identifier"):
        _binding(reason="free text or operator@example.invalid")


def test_shadow_pin_cannot_become_authoritative_or_positive() -> None:
    pin = ShadowMaterialRulesetPin(
        pin_id="mshp_" + "7" * 32,
        binding_id=_binding().binding_id,
        snapshot_id=SNAPSHOT_ID,
        content_sha256=HASH,
        environment=ShadowEnvironment.STAGING,
        purpose=ShadowPurpose.MATERIAL_RULESET_SHADOW,
        scope_kind=ShadowScopeKind.GLOBAL,
        tenant_ref_hmac="8" * 64,
        hmac_key_id="shadow-key-v1",
        domain_pack_id="material.test.v1",
        domain_pack_version="1.0.0",
        evaluator_version="MAT-GOV-03B.eval.v1",
        kernel_version="MAT-GOV-02.kernel.v1",
        runtime_profile_sha256="6" * 64,
        build_git_sha=GIT,
        build_tree_hash=TREE,
        sampling_policy_version="MAT-GOV-03B.shadow.v1",
        sampled=False,
        acquired_at=NOW,
        binding_valid_until=LATER,
    )
    assert pin.authority is ShadowAuthority.NON_AUTHORITATIVE
    assert pin.positive_statement_allowed is False
    with pytest.raises(TypeError):
        ShadowMaterialRulesetPin(**{**asdict(pin), "authority": "AUTHORITATIVE"})
    import sealai_v2.core.material_shadow as module

    assert not hasattr(module, "AuthoritativeMaterialRulesetPin")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("pin_id", "mshp_bad"),
        ("binding_id", "mshb_bad"),
        ("snapshot_id", "mss_bad"),
        ("content_sha256", "A" * 64),
        ("environment", "staging"),
        ("purpose", "MATERIAL_RULESET_SHADOW"),
        ("scope_kind", "GLOBAL"),
        ("tenant_ref_hmac", "8" * 63),
        ("hmac_key_id", ""),
        ("domain_pack_id", "invalid domain"),
        ("domain_pack_version", ""),
        ("evaluator_version", ""),
        ("kernel_version", ""),
        ("runtime_profile_sha256", "6" * 63),
        ("build_git_sha", "3" * 39),
        ("build_tree_hash", "4" * 41),
        ("sampling_policy_version", ""),
        ("sampled", True),
        ("sampled", 0),
        ("acquired_at", "2026-07-17T12:00:00+01:00"),
        ("binding_valid_until", NOW),
        ("pin_schema_version", True),
        ("pin_schema_version", 2),
    ),
)
def test_shadow_pin_direct_constructor_rejects_every_invalid_field(
    field: str, value: object
) -> None:
    valid = asdict(
        ShadowMaterialRulesetPin(
            pin_id="mshp_" + "7" * 32,
            binding_id=_binding().binding_id,
            snapshot_id=SNAPSHOT_ID,
            content_sha256=HASH,
            environment=ShadowEnvironment.STAGING,
            purpose=ShadowPurpose.MATERIAL_RULESET_SHADOW,
            scope_kind=ShadowScopeKind.GLOBAL,
            tenant_ref_hmac="8" * 64,
            hmac_key_id="shadow-key-v1",
            domain_pack_id="material.test.v1",
            domain_pack_version="1.0.0",
            evaluator_version="MAT-GOV-03B.eval.v1",
            kernel_version="MAT-GOV-02.kernel.v1",
            runtime_profile_sha256="6" * 64,
            build_git_sha=GIT,
            build_tree_hash=TREE,
            sampling_policy_version="MAT-GOV-03B.shadow.v1",
            sampled=False,
            acquired_at=NOW,
            binding_valid_until=LATER,
        )
    )
    with pytest.raises(ShadowContractError) as exc:
        ShadowMaterialRulesetPin(**{**valid, field: value})
    assert exc.value.code is ShadowErrorCode.INVALID_PIN


def test_shadow_pin_storage_parser_uses_the_closed_constructor_contract() -> None:
    pin = ShadowMaterialRulesetPin(
        pin_id="mshp_" + "7" * 32,
        binding_id=_binding().binding_id,
        snapshot_id=SNAPSHOT_ID,
        content_sha256=HASH,
        environment=ShadowEnvironment.STAGING,
        purpose=ShadowPurpose.MATERIAL_RULESET_SHADOW,
        scope_kind=ShadowScopeKind.GLOBAL,
        tenant_ref_hmac="8" * 64,
        hmac_key_id="shadow-key-v1",
        domain_pack_id="material.test.v1",
        domain_pack_version="1.0.0",
        evaluator_version="MAT-GOV-03B.eval.v1",
        kernel_version="MAT-GOV-02.kernel.v1",
        runtime_profile_sha256="6" * 64,
        build_git_sha=GIT,
        build_tree_hash=TREE,
        sampling_policy_version="MAT-GOV-03B.shadow.v1",
        sampled=False,
        acquired_at=NOW,
        binding_valid_until=LATER,
    )
    stored = asdict(pin)
    stored["environment"] = pin.environment.value
    stored["purpose"] = pin.purpose.value
    stored["scope_kind"] = pin.scope_kind.value
    assert ShadowMaterialRulesetPin.from_storage(stored) == pin
    for invalid in (
        {**stored, "environment": "unknown"},
        {**stored, "purpose": "unknown"},
        {**stored, "scope_kind": "unknown"},
        {**stored, "extra": "state"},
        {key: value for key, value in stored.items() if key != "pin_id"},
    ):
        with pytest.raises(ShadowContractError) as exc:
            ShadowMaterialRulesetPin.from_storage(invalid)
        assert exc.value.code is ShadowErrorCode.INVALID_PIN


def test_versioned_hmac_keyring_retains_old_keys_without_exposing_secrets() -> None:
    keyring = ShadowHmacKeyring(
        {"key-v1": "a" * 32, "key-v2": "b" * 32}, active_key_id="key-v2"
    )
    assert keyring.digest_fields(
        TENANT_REF_DOMAIN, ("tenant-a",), key_id="key-v1"
    ) != keyring.digest_fields(TENANT_REF_DOMAIN, ("tenant-a",), key_id="key-v2")
    assert keyring.contains("key-v1")
    with pytest.raises(ValueError, match="SHADOW_HMAC_KEY_UNAVAILABLE"):
        keyring.digest_fields(TENANT_REF_DOMAIN, ("tenant-a",), key_id="deleted-key")
    with pytest.raises(ValueError, match="SHADOW_HMAC_KEY_UNAVAILABLE"):
        keyring.digest_fields(TENANT_REF_DOMAIN, ("tenant-a",), key_id="")


def test_hmac_tuple_encoding_is_injective_for_empty_nul_and_unicode_fields() -> None:
    pairs = (
        (("tenant-A", "session-X\x00tail"), ("tenant-A\x00session-X", "tail")),
        (("", "a"), ("a", "")),
        (("tenant", "ä"), ("tenantä", "")),
    )
    for left, right in pairs:
        assert encode_hmac_fields(SESSION_REF_DOMAIN, left) != encode_hmac_fields(
            SESSION_REF_DOMAIN, right
        )
    assert encode_hmac_fields(SESSION_REF_DOMAIN, ("e\u0301",)) != encode_hmac_fields(
        SESSION_REF_DOMAIN, ("é",)
    )


def test_hmac_domains_and_input_types_are_closed() -> None:
    assert encode_hmac_fields(TENANT_REF_DOMAIN, ("tenant",)) != encode_hmac_fields(
        SESSION_REF_DOMAIN, ("tenant",)
    )
    with pytest.raises(TypeError, match="tuple of strings"):
        encode_hmac_fields(TENANT_REF_DOMAIN, (1,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown"):
        encode_hmac_fields(b"unregistered", ("tenant",))


def test_hmac_encoder_rejects_uint32_overflow_before_packing(monkeypatch) -> None:
    import sealai_v2.material_shadow.hmac_refs as hmac_module

    monkeypatch.setattr(hmac_module, "_UINT32_MAX", 3)
    with pytest.raises(ValueError, match="uint32"):
        encode_hmac_fields(TENANT_REF_DOMAIN, ("four",))


def test_hmac_keyring_json_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="SHADOW_HMAC_KEY_UNAVAILABLE"):
        ShadowHmacKeyring.from_json(
            '{"key-v1":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            '"key-v1":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
            active_key_id="key-v1",
        )


def test_sampling_is_deterministic_and_owner_frozen_at_zero() -> None:
    keyring = ShadowHmacKeyring({"key-v1": "a" * 32}, active_key_id="key-v1")
    first = decide_sampling(
        tenant_id="tenant-a",
        session_ref="session-hmac",
        policy_version="MAT-GOV-03B.shadow.v1",
        basis_points=0,
        keyring=keyring,
    )
    second = decide_sampling(
        tenant_id="tenant-a",
        session_ref="session-hmac",
        policy_version="MAT-GOV-03B.shadow.v1",
        basis_points=0,
        keyring=keyring,
    )
    assert first == second
    assert first.sampled is False
    with pytest.raises(ValueError, match="owner-frozen"):
        decide_sampling(
            tenant_id="tenant-a",
            session_ref="session-hmac",
            policy_version="MAT-GOV-03B.shadow.v1",
            basis_points=1,
            keyring=keyring,
        )


def _enabled_settings(**changes) -> Settings:
    values = {
        "material_ruleset_shadow_enabled": True,
        "material_ruleset_shadow_persistence_enabled": True,
        "material_ruleset_shadow_environment": "staging",
        "material_ruleset_shadow_redis_url": "redis://cache.invalid/1",
        "material_ruleset_shadow_hmac_active_key_id": "key-v1",
        "material_ruleset_shadow_hmac_keyring_json": json.dumps(
            {"key-v1": "a" * 32, "key-old": "b" * 32}
        ),
        "database_url": "postgresql://db.invalid/shadow",
    }
    values.update(changes)
    return Settings(**values)


def test_shadow_settings_are_independent_default_off_and_fail_closed() -> None:
    settings = Settings()
    assert settings.material_ruleset_shadow_enabled is False
    assert settings.material_ruleset_shadow_persistence_enabled is False
    assert settings.material_ruleset_shadow_sampling_enabled is False
    assert settings.material_ruleset_shadow_sampling_basis_points == 0
    assert settings.material_constraints_enabled is False
    with pytest.raises(ValidationError, match="persistence requires"):
        Settings(material_ruleset_shadow_persistence_enabled=True)
    with pytest.raises(ValidationError, match="server-side configuration"):
        Settings(material_ruleset_shadow_enabled=True)
    with pytest.raises(ValidationError, match="owner-frozen"):
        _enabled_settings(material_ruleset_shadow_sampling_basis_points=1)


def test_shadow_secrets_and_urls_are_absent_from_runtime_profile() -> None:
    settings = _enabled_settings()
    profile = runtime_profile(settings)
    encoded = json.dumps(profile, default=str)
    assert "redis://cache.invalid" not in encoded
    assert "a" * 32 not in encoded
    assert "key-v1" in encoded
