from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from sealai_v2.core.material_evidence import (
    AtomicEvidenceClaimV1,
    EvidenceClaimScopeV1,
    EvidenceManifestPayloadV1,
    EvidenceManifestSnapshotV1,
    EvidenceSourceV1,
    MaterialEvidenceErrorCode,
    MaterialEvidenceIntegrityError,
    MaterialEvidenceValidationError,
    RuleClaimBindingV1,
    canonicalize_payload,
    compute_audit_sha256,
    compute_validation_sha256,
    derive_claim_ref,
    derive_source_ref,
    parse_manifest_payload,
)


MANIFEST_ID = "mef_11111111111111111111111111111111"
RULESET_SNAPSHOT_ID = "mss_" + "2" * 64
CONTENT_SHA = "3" * 64


def _source(*, revision: str = "rev-1", digest: str = CONTENT_SHA) -> EvidenceSourceV1:
    values = {
        "document_id": "DOC-TEST-001",
        "document_revision": revision,
        "publication_edition": "edition-2026-01",
        "content_sha256": digest,
    }
    return EvidenceSourceV1(
        source_ref=derive_source_ref(**values),
        **values,
    )


def _scope() -> EvidenceClaimScopeV1:
    return EvidenceClaimScopeV1(
        materials=("MAT-TEST",),
        media=("MEDIUM-TEST",),
        conditions=("CONDITION-TEST",),
    )


def _claim(
    source: EvidenceSourceV1, *, text: str = "Synthetic atomic claim."
) -> AtomicEvidenceClaimV1:
    scope = _scope()
    return AtomicEvidenceClaimV1(
        claim_ref=derive_claim_ref(claim_text=text, scope=scope),
        claim_text=text,
        scope=scope,
        source_refs=(source.source_ref,),
    )


def _payload() -> EvidenceManifestPayloadV1:
    source = _source()
    claim = _claim(source)
    return EvidenceManifestPayloadV1(
        ruleset_snapshot_id=RULESET_SNAPSHOT_ID,
        domain_pack_id="material.test.v1",
        sources=(source,),
        claims=(claim,),
        rule_claim_bindings=(
            RuleClaimBindingV1(rule_ref="MR-TEST-001", claim_ref=claim.claim_ref),
        ),
    )


def _raw_payload() -> str:
    return json.dumps(_payload().to_dict(), ensure_ascii=False)


def test_manifest_contract_is_versioned_canonical_and_deeply_immutable() -> None:
    payload = _payload()
    snapshot = EvidenceManifestSnapshotV1.create(MANIFEST_ID, payload)
    assert payload.evidence_manifest_schema_version == 1
    assert payload.canonicalization_version == 1
    assert payload.mat_evid_contract_version == "MAT-EVID-01A.v1"
    assert snapshot.snapshot_id.startswith("mes_")
    assert len(snapshot.content_sha256) == 64
    assert snapshot.canonical_bytes == canonicalize_payload(payload)
    assert parse_manifest_payload(snapshot.canonical_bytes) == payload
    with pytest.raises(FrozenInstanceError):
        payload.domain_pack_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        payload.claims[0].claim_text = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        payload.sources[0] = payload.sources[0]  # type: ignore[index]


@pytest.mark.parametrize("mutable_type", [bytearray, memoryview])
def test_snapshot_rejects_mutable_or_non_exact_canonical_bytes(
    mutable_type: type,
) -> None:
    snapshot = EvidenceManifestSnapshotV1.create(MANIFEST_ID, _payload())
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        EvidenceManifestSnapshotV1(
            manifest_id=snapshot.manifest_id,
            snapshot_id=snapshot.snapshot_id,
            content_sha256=snapshot.content_sha256,
            canonical_bytes=mutable_type(snapshot.canonical_bytes),  # type: ignore[arg-type]
            payload=snapshot.payload,
        )
    assert exc.value.code is MaterialEvidenceErrorCode.INVALID_TYPE


@pytest.mark.parametrize(
    "field", ["evidence_manifest_schema_version", "canonicalization_version"]
)
@pytest.mark.parametrize("invalid_version", [True, 1.0])
def test_direct_payload_constructor_rejects_non_exact_integer_versions(
    field: str, invalid_version: object
) -> None:
    values = {
        "ruleset_snapshot_id": RULESET_SNAPSHOT_ID,
        "domain_pack_id": "material.test.v1",
        "sources": _payload().sources,
        "claims": _payload().claims,
        "rule_claim_bindings": _payload().rule_claim_bindings,
        field: invalid_version,
    }
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        EvidenceManifestPayloadV1(**values)  # type: ignore[arg-type]
    assert exc.value.code is MaterialEvidenceErrorCode.INVALID_TYPE


@pytest.mark.parametrize("member", ["", " ", "\t"])
@pytest.mark.parametrize("axis", ["materials", "media", "conditions"])
def test_direct_scope_constructor_rejects_empty_or_whitespace_members(
    axis: str, member: str
) -> None:
    values = {
        "materials": ("MAT-TEST",),
        "media": ("MEDIUM-TEST",),
        "conditions": ("CONDITION-TEST",),
    }
    values[axis] = (member,)
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        EvidenceClaimScopeV1(**values)
    assert exc.value.code is MaterialEvidenceErrorCode.INVALID_TYPE


def test_direct_domain_construction_round_trips_through_canonical_parser() -> None:
    payload = _payload()
    assert parse_manifest_payload(canonicalize_payload(payload)) == payload


def test_claim_identity_excludes_source_revision_but_includes_text_and_scope() -> None:
    first = _source(revision="rev-1", digest="4" * 64)
    second = _source(revision="rev-2", digest="5" * 64)
    first_claim = _claim(first)
    second_claim = _claim(second)
    assert first.source_ref != second.source_ref
    assert first_claim.claim_ref == second_claim.claim_ref
    assert (
        _claim(first, text="Changed atomic claim.").claim_ref != first_claim.claim_ref
    )
    changed_scope = EvidenceClaimScopeV1(
        materials=("MAT-OTHER",),
        media=("MEDIUM-TEST",),
        conditions=("CONDITION-TEST",),
    )
    assert (
        derive_claim_ref(claim_text=first_claim.claim_text, scope=changed_scope)
        != first_claim.claim_ref
    )


def test_source_identity_requires_document_revision_edition_and_digest() -> None:
    baseline = _source()
    assert baseline.source_ref != _source(revision="rev-2").source_ref
    assert baseline.source_ref != _source(digest="6" * 64).source_ref
    for field in ("document_id", "document_revision", "publication_edition"):
        values = {
            "document_id": "DOC-TEST-001",
            "document_revision": "rev-1",
            "publication_edition": "edition-2026-01",
            "content_sha256": CONTENT_SHA,
        }
        values[field] = ""
        with pytest.raises(MaterialEvidenceValidationError):
            derive_source_ref(**values)


def test_input_order_does_not_change_canonical_manifest_identity() -> None:
    source_a = _source(revision="rev-a", digest="a" * 64)
    source_b = _source(revision="rev-b", digest="b" * 64)
    claim_a = _claim(source_a, text="Synthetic claim A.")
    claim_b = _claim(source_b, text="Synthetic claim B.")
    base = {
        "evidence_manifest_schema_version": 1,
        "canonicalization_version": 1,
        "mat_evid_contract_version": "MAT-EVID-01A.v1",
        "ruleset_snapshot_id": RULESET_SNAPSHOT_ID,
        "domain_pack_id": "material.test.v1",
        "sources": [source_a.to_dict(), source_b.to_dict()],
        "claims": [claim_a.to_dict(), claim_b.to_dict()],
        "rule_claim_bindings": [
            {"rule_ref": "MR-TEST-001", "claim_ref": claim_a.claim_ref},
            {"rule_ref": "MR-TEST-001", "claim_ref": claim_b.claim_ref},
        ],
    }
    reversed_payload = {
        **base,
        "sources": list(reversed(base["sources"])),
        "claims": list(reversed(base["claims"])),
        "rule_claim_bindings": list(reversed(base["rule_claim_bindings"])),
    }
    first = EvidenceManifestSnapshotV1.from_json(MANIFEST_ID, json.dumps(base))
    second = EvidenceManifestSnapshotV1.from_json(
        MANIFEST_ID, json.dumps(reversed_payload)
    )
    assert first == second


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_manifest_schema_version", 2),
        ("canonicalization_version", 2),
        ("mat_evid_contract_version", "MAT-EVID-01A.v2"),
    ],
)
def test_unknown_contract_versions_fail_closed(field: str, value: object) -> None:
    raw = _payload().to_dict()
    raw[field] = value
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        parse_manifest_payload(json.dumps(raw))
    assert exc.value.code is MaterialEvidenceErrorCode.UNKNOWN_SCHEMA


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "url",
        "review_state",
        "approval_state",
        "deployment_state",
        "active",
        "positive_statement_allowed",
    ],
)
def test_unknown_authority_or_url_fields_fail_closed(forbidden_field: str) -> None:
    raw = _payload().to_dict()
    raw[forbidden_field] = "forbidden"
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        parse_manifest_payload(json.dumps(raw))
    assert exc.value.code is MaterialEvidenceErrorCode.UNKNOWN_FIELD


@pytest.mark.parametrize(
    ("collection", "forbidden_field"),
    [
        ("sources", "url"),
        ("sources", "review_state"),
        ("claims", "approval_state"),
        ("rule_claim_bindings", "authority"),
    ],
)
def test_nested_url_and_authority_fields_fail_closed(
    collection: str, forbidden_field: str
) -> None:
    raw = _payload().to_dict()
    raw[collection][0][forbidden_field] = "forbidden"
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        parse_manifest_payload(json.dumps(raw))
    assert exc.value.code is MaterialEvidenceErrorCode.UNKNOWN_FIELD


def test_duplicate_properties_floats_and_non_nfc_fail_closed() -> None:
    with pytest.raises(MaterialEvidenceValidationError) as duplicate:
        parse_manifest_payload(
            '{"evidence_manifest_schema_version":1,"evidence_manifest_schema_version":1}'
        )
    assert duplicate.value.code is MaterialEvidenceErrorCode.DUPLICATE_PROPERTY
    raw = _payload().to_dict()
    raw["unexpected"] = 1.2
    with pytest.raises(MaterialEvidenceValidationError) as floating:
        parse_manifest_payload(json.dumps(raw))
    assert floating.value.code is MaterialEvidenceErrorCode.FLOAT_FORBIDDEN
    raw = _payload().to_dict()
    raw["claims"][0]["claim_text"] = "Cafe\u0301"
    with pytest.raises(MaterialEvidenceValidationError) as non_nfc:
        parse_manifest_payload(json.dumps(raw, ensure_ascii=False))
    assert non_nfc.value.code is MaterialEvidenceErrorCode.NON_NFC


def test_dangling_or_orphan_sources_claims_and_bindings_fail_closed() -> None:
    cases: list[tuple[dict, MaterialEvidenceErrorCode]] = []
    dangling_source = _payload().to_dict()
    dangling_source["claims"][0]["source_refs"] = ["msr_" + "f" * 64]
    cases.append((dangling_source, MaterialEvidenceErrorCode.DANGLING_REF))
    orphan_source = _payload().to_dict()
    extra = _source(revision="other", digest="d" * 64)
    orphan_source["sources"].append(extra.to_dict())
    cases.append((orphan_source, MaterialEvidenceErrorCode.ORPHAN_REF))
    dangling_claim = _payload().to_dict()
    dangling_claim["rule_claim_bindings"][0]["claim_ref"] = "mec_" + "f" * 64
    cases.append((dangling_claim, MaterialEvidenceErrorCode.DANGLING_REF))
    orphan_claim = _payload().to_dict()
    orphan_claim["rule_claim_bindings"] = []
    cases.append((orphan_claim, MaterialEvidenceErrorCode.EMPTY_COLLECTION))
    for raw, code in cases:
        with pytest.raises(MaterialEvidenceValidationError) as exc:
            parse_manifest_payload(json.dumps(raw))
        assert exc.value.code is code


def test_claim_and_source_ref_mismatches_fail_closed() -> None:
    raw = _payload().to_dict()
    raw["sources"][0]["source_ref"] = "msr_" + "f" * 64
    with pytest.raises(MaterialEvidenceValidationError) as source_error:
        parse_manifest_payload(json.dumps(raw))
    assert source_error.value.code is MaterialEvidenceErrorCode.HASH_MISMATCH
    raw = _payload().to_dict()
    raw["claims"][0]["claim_ref"] = "mec_" + "f" * 64
    raw["rule_claim_bindings"][0]["claim_ref"] = "mec_" + "f" * 64
    with pytest.raises(MaterialEvidenceValidationError) as claim_error:
        parse_manifest_payload(json.dumps(raw))
    assert claim_error.value.code is MaterialEvidenceErrorCode.HASH_MISMATCH


def test_snapshot_integrity_and_event_hashes_are_deterministic() -> None:
    snapshot = EvidenceManifestSnapshotV1.create(MANIFEST_ID, _payload())
    assert compute_validation_sha256(snapshot) == compute_validation_sha256(snapshot)
    event = {
        "content_sha256": snapshot.content_sha256,
        "snapshot_id": snapshot.snapshot_id,
        "validation_event_id": "mev_" + "7" * 32,
    }
    assert compute_audit_sha256(event) == compute_audit_sha256(
        dict(reversed(list(event.items())))
    )
    with pytest.raises(MaterialEvidenceValidationError) as floating:
        compute_audit_sha256({"nested": {"value": 1.5}})
    assert floating.value.code is MaterialEvidenceErrorCode.FLOAT_FORBIDDEN
    with pytest.raises(MaterialEvidenceIntegrityError):
        EvidenceManifestSnapshotV1(
            manifest_id=MANIFEST_ID,
            snapshot_id=snapshot.snapshot_id,
            content_sha256="0" * 64,
            canonical_bytes=snapshot.canonical_bytes,
            payload=snapshot.payload,
        )


def test_fixed_golden_hash_contract() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "mat_evid_01a_golden.json").read_text(
            encoding="utf-8"
        )
    )
    snapshot = EvidenceManifestSnapshotV1.from_json(
        fixture["manifest_id"], fixture["input_json"]
    )
    assert snapshot.payload.sources[0].source_ref == fixture["expected_source_ref"]
    assert snapshot.payload.claims[0].claim_ref == fixture["expected_claim_ref"]
    assert snapshot.canonical_bytes.hex() == fixture["expected_canonical_bytes_hex"]
    assert snapshot.content_sha256 == fixture["expected_content_sha256"]
    assert snapshot.snapshot_id == fixture["expected_snapshot_id"]
    assert compute_validation_sha256(snapshot) == fixture["expected_validation_sha256"]
    assert (
        compute_audit_sha256(fixture["audit_event"]) == fixture["expected_audit_sha256"]
    )
