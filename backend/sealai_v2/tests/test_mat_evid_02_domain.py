from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from sealai_v2.core.material_evidence import (
    EvidenceClaimScopeV1,
    derive_claim_ref as derive_claim_ref_v1,
    derive_source_ref as derive_source_ref_v1,
)
from sealai_v2.core.material_evidence_v2 import (
    AtomicEvidenceClaimV2,
    EvidenceManifestPayloadV2,
    EvidenceManifestSnapshotV2,
    EvidenceScopeTypeV2,
    EvidenceSourceV2,
    MaterialEvidenceV2ErrorCode,
    MaterialEvidenceV2ValidationError,
    MaterialRelationClaimScopeV2,
    MaterialRelationTargetV2,
    MediaIdentityClaimScopeV2,
    MediaIdentityTargetV2,
    RuleClaimBindingV2,
    canonicalize_payload_v2,
    compute_audit_sha256_v2,
    compute_validation_sha256_v2,
    derive_claim_ref_v2,
    derive_source_ref_v2,
    parse_manifest_payload_v2,
)


MANIFEST_ID = "mef_" + "1" * 32
RULESET_SNAPSHOT_ID = "mss_" + "2" * 64
MEDIA_REF = "med_" + "3" * 64
IDENTITY_ASSERTION_REF = "med-norm-identity-sha256:" + "4" * 64
SOURCE_IDENTITY = {
    "document_id": "DOC-V2-TEST",
    "document_revision": "rev-2",
    "publication_edition": "edition-2",
    "content_sha256": "5" * 64,
}
GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures/mat_evid_02_golden.json").read_text(
        encoding="utf-8"
    )
)


def _source() -> EvidenceSourceV2:
    return EvidenceSourceV2(
        source_ref=derive_source_ref_v2(**SOURCE_IDENTITY), **SOURCE_IDENTITY
    )


def _material_scope() -> MaterialRelationClaimScopeV2:
    return MaterialRelationClaimScopeV2(
        materials=("SYNTHETIC-MATERIAL",),
        media=(MEDIA_REF,),
        conditions=("synthetic-condition",),
    )


def _media_scope() -> MediaIdentityClaimScopeV2:
    return MediaIdentityClaimScopeV2(
        media_ref=MEDIA_REF,
        identity_assertion_ref=IDENTITY_ASSERTION_REF,
    )


def _claim(scope, text: str) -> AtomicEvidenceClaimV2:
    return AtomicEvidenceClaimV2(
        claim_ref=derive_claim_ref_v2(claim_text=text, scope=scope),
        claim_text=text,
        scope=scope,
        source_refs=(_source().source_ref,),
    )


def _material_payload() -> EvidenceManifestPayloadV2:
    claim = _claim(_material_scope(), "Synthetic material relation claim.")
    return EvidenceManifestPayloadV2(
        domain_pack_id="material.test.v2",
        target=MaterialRelationTargetV2(RULESET_SNAPSHOT_ID),
        sources=(_source(),),
        claims=(claim,),
        rule_claim_bindings=(RuleClaimBindingV2("MR-SYNTHETIC", claim.claim_ref),),
    )


def _media_payload() -> EvidenceManifestPayloadV2:
    claim = _claim(_media_scope(), "Synthetic media identity claim.")
    return EvidenceManifestPayloadV2(
        domain_pack_id="material.test.v2",
        target=MediaIdentityTargetV2(MEDIA_REF),
        sources=(_source(),),
        claims=(claim,),
        rule_claim_bindings=(),
    )


def _raw(payload: EvidenceManifestPayloadV2) -> str:
    return json.dumps(payload.to_dict(), ensure_ascii=False)


def test_v2_golden_hash_domains_are_frozen_and_distinct_from_v1() -> None:
    material = EvidenceManifestSnapshotV2.create(MANIFEST_ID, _material_payload())
    media = EvidenceManifestSnapshotV2.create(MANIFEST_ID, _media_payload())
    manifest_golden = {
        key: value for key, value in GOLDEN.items() if not key.startswith("runtime_")
    }
    assert {
        "source_ref": _source().source_ref,
        "material_claim_ref": _material_payload().claims[0].claim_ref,
        "material_content_sha256": material.content_sha256,
        "material_snapshot_id": material.snapshot_id,
        "material_validation_sha256": compute_validation_sha256_v2(material),
        "media_claim_ref": _media_payload().claims[0].claim_ref,
        "media_content_sha256": media.content_sha256,
        "media_snapshot_id": media.snapshot_id,
        "media_validation_sha256": compute_validation_sha256_v2(media),
        "audit_sha256": compute_audit_sha256_v2(
            {"event_type": "snapshot_created", "snapshot_id": media.snapshot_id}
        ),
    } == manifest_golden

    v1_scope = EvidenceClaimScopeV1(
        materials=("SYNTHETIC-MATERIAL",),
        media=(MEDIA_REF,),
        conditions=("synthetic-condition",),
    )
    assert _source().source_ref != derive_source_ref_v1(**SOURCE_IDENTITY)
    assert _material_payload().claims[0].claim_ref != derive_claim_ref_v1(
        claim_text="Synthetic material relation claim.", scope=v1_scope
    )


def test_both_closed_scope_variants_roundtrip_canonically() -> None:
    for payload in (_material_payload(), _media_payload()):
        parsed = parse_manifest_payload_v2(_raw(payload))
        assert parsed == payload
        assert canonicalize_payload_v2(parsed) == canonicalize_payload_v2(payload)
        assert EvidenceManifestSnapshotV2.from_json(MANIFEST_ID, _raw(payload)) == (
            EvidenceManifestSnapshotV2.create(MANIFEST_ID, payload)
        )

    assert (
        _material_payload().claims[0].scope.scope_type
        is EvidenceScopeTypeV2.MATERIAL_RELATION
    )
    assert (
        _media_payload().claims[0].scope.scope_type
        is EvidenceScopeTypeV2.MEDIA_IDENTITY
    )
    assert "materials" not in _media_payload().claims[0].scope.to_dict()
    assert _media_payload().claims[0].scope.to_dict()["media_ref"] == MEDIA_REF


@pytest.mark.parametrize(
    ("mutate", "code"),
    (
        (
            lambda value: value["claims"][0]["scope"].__setitem__(
                "materials", ["PLACEHOLDER"]
            ),
            MaterialEvidenceV2ErrorCode.UNKNOWN_FIELD,
        ),
        (
            lambda value: value["claims"][0]["scope"].__setitem__(
                "media_ref", [MEDIA_REF]
            ),
            MaterialEvidenceV2ErrorCode.INVALID_TYPE,
        ),
        (
            lambda value: value["claims"][0]["scope"].__setitem__(
                "scope_type", "material_relation"
            ),
            MaterialEvidenceV2ErrorCode.UNKNOWN_FIELD,
        ),
        (
            lambda value: value["target"].__setitem__("media_ref", "med_" + "9" * 64),
            MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
        ),
        (
            lambda value: value.__setitem__(
                "rule_claim_bindings",
                [
                    {
                        "rule_ref": "MR-SYNTHETIC",
                        "claim_ref": value["claims"][0]["claim_ref"],
                    }
                ],
            ),
            MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
        ),
        (
            lambda value: value.__setitem__("evidence_manifest_schema_version", 1),
            MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
        ),
        (
            lambda value: value.__setitem__("canonicalization_version", 1),
            MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
        ),
        (
            lambda value: value.__setitem__(
                "mat_evid_contract_version", "MAT-EVID-01A.v1"
            ),
            MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
        ),
        (
            lambda value: value.__setitem__("unknown", True),
            MaterialEvidenceV2ErrorCode.UNKNOWN_FIELD,
        ),
    ),
)
def test_media_identity_unknown_fields_and_impossible_combinations_fail_closed(
    mutate, code
) -> None:
    value = _media_payload().to_dict()
    mutate(value)
    with pytest.raises(MaterialEvidenceV2ValidationError) as captured:
        parse_manifest_payload_v2(json.dumps(value))
    assert captured.value.code is code


@pytest.mark.parametrize(
    "scope",
    (
        MaterialRelationClaimScopeV2(
            materials=("SYNTHETIC-MATERIAL",), media=(MEDIA_REF,), conditions=()
        ),
        MediaIdentityClaimScopeV2(
            media_ref=MEDIA_REF, identity_assertion_ref=IDENTITY_ASSERTION_REF
        ),
    ),
)
def test_scope_dataclasses_are_deeply_immutable(scope) -> None:
    with pytest.raises((AttributeError, TypeError)):
        scope.scope_type = EvidenceScopeTypeV2.MEDIA_IDENTITY


def test_material_target_rejects_media_claim_and_incomplete_bindings() -> None:
    material = _material_payload()
    media_claim = _claim(_media_scope(), "Synthetic media identity claim.")
    with pytest.raises(MaterialEvidenceV2ValidationError) as wrong_scope:
        replace(material, claims=(media_claim,))
    assert wrong_scope.value.code is MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH

    with pytest.raises(MaterialEvidenceV2ValidationError) as unbound:
        replace(material, rule_claim_bindings=())
    assert unbound.value.code is MaterialEvidenceV2ErrorCode.EMPTY_COLLECTION


def test_media_target_rejects_material_claim_without_placeholder_fallback() -> None:
    media = _media_payload()
    material_claim = _claim(_material_scope(), "Synthetic material relation claim.")
    with pytest.raises(MaterialEvidenceV2ValidationError) as captured:
        replace(media, claims=(material_claim,))
    assert captured.value.code is MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH


def test_duplicate_properties_non_nfc_and_floats_fail_closed() -> None:
    raw = _raw(_media_payload())
    duplicate = raw.replace(
        '"canonicalization_version": 2',
        '"canonicalization_version": 2, "canonicalization_version": 2',
        1,
    )
    with pytest.raises(MaterialEvidenceV2ValidationError) as duplicated:
        parse_manifest_payload_v2(duplicate)
    assert duplicated.value.code is MaterialEvidenceV2ErrorCode.DUPLICATE_PROPERTY

    value = _media_payload().to_dict()
    value["claims"][0]["claim_text"] = "e\u0301"
    with pytest.raises(MaterialEvidenceV2ValidationError) as non_nfc:
        parse_manifest_payload_v2(json.dumps(value, ensure_ascii=False))
    assert non_nfc.value.code is MaterialEvidenceV2ErrorCode.NON_NFC

    with pytest.raises(MaterialEvidenceV2ValidationError) as floating:
        parse_manifest_payload_v2(
            raw.replace(
                '"canonicalization_version": 2', '"canonicalization_version": 2.0'
            )
        )
    assert floating.value.code is MaterialEvidenceV2ErrorCode.FLOAT_FORBIDDEN
