from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sealai_v2.core.material_rulesets import (
    CONTENT_HASH_DOMAIN,
    EvidenceBindingV1,
    MaterialRuleScopeV1,
    MaterialRulesetErrorCode,
    MaterialRulesetSnapshotV1,
    MaterialRulesetValidationError,
    canonicalize_payload,
    derive_snapshot_id,
    generate_ruleset_id,
    validate_ruleset_id,
    validate_snapshot_id,
)


FIXTURE = Path(__file__).parent / "fixtures" / "mat_gov_03a_golden.json"
RULESET_ID = "mrs_11111111111111111111111111111111"


def _base_payload() -> dict:
    return {
        "snapshot_schema_version": 1,
        "canonicalization_version": 1,
        "mat_gov_contract_version": "MAT-GOV-03A.v1",
        "domain_pack_id": "material.test.v1",
        "positive_statement_allowed": False,
        "rules": [
            {
                "rule_ref": "MR-TEST-001",
                "material": "TEST-MATERIAL",
                "medium": "TEST-MEDIUM",
                "condition": "TEST-CONDITION",
                "verdict": "bedingt",
                "statement": "Synthetischer Vertragstest – keine Werkstoffaussage.",
                "scope": {
                    "materials": ["TEST-A", "TEST-B"],
                    "media": ["MEDIUM-A", "MEDIUM-B"],
                    "conditions": ["CONDITION-A"],
                },
                "evidence_binding": {"state": "unbound"},
            }
        ],
    }


def _raw(payload: dict, **kwargs) -> str:
    return json.dumps(payload, ensure_ascii=False, **kwargs)


def _error(raw: str | bytes, *, ruleset_id: str = RULESET_ID) -> str:
    with pytest.raises(MaterialRulesetValidationError) as exc:
        MaterialRulesetSnapshotV1.from_json(ruleset_id, raw)
    return exc.value.code.value


def test_repository_fixed_golden_fixtures() -> None:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert cases
    for case in cases:
        required = {
            "name",
            "ruleset_id",
            "input_json",
            "expected_payload",
            "expected_canonical_bytes_hex",
            "expected_content_sha256",
            "expected_snapshot_id",
            "valid",
            "error_code",
        }
        assert set(case) == required, case["name"]
        if not case["valid"]:
            assert (
                _error(case["input_json"], ruleset_id=case["ruleset_id"])
                == case["error_code"]
            ), case["name"]
            continue
        snapshot = MaterialRulesetSnapshotV1.from_json(
            case["ruleset_id"], case["input_json"]
        )
        assert snapshot.payload.to_dict() == case["expected_payload"], case["name"]
        assert (
            snapshot.canonical_bytes.hex() == case["expected_canonical_bytes_hex"]
        ), case["name"]
        assert snapshot.content_sha256 == case["expected_content_sha256"], case["name"]
        assert snapshot.snapshot_id == case["expected_snapshot_id"], case["name"]
        assert case["error_code"] == "none"


def test_key_order_and_input_whitespace_do_not_change_canonical_bytes() -> None:
    payload = _base_payload()
    keys = list(payload)
    variants = []
    for order in itertools.islice(itertools.permutations(keys), 30):
        ordered = {key: payload[key] for key in order}
        variants.append(_raw(ordered, separators=(",", ":")))
        variants.append(_raw(ordered, indent=3))
    snapshots = [
        MaterialRulesetSnapshotV1.from_json(RULESET_ID, raw) for raw in variants
    ]
    assert len({snapshot.canonical_bytes for snapshot in snapshots}) == 1
    assert len({snapshot.content_sha256 for snapshot in snapshots}) == 1
    assert len({snapshot.snapshot_id for snapshot in snapshots}) == 1


def test_only_typed_scope_sets_are_order_independent() -> None:
    first = _base_payload()
    second = _base_payload()
    second["rules"][0]["scope"] = {
        "materials": ["TEST-B", "TEST-A", "TEST-A"],
        "media": ["MEDIUM-B", "MEDIUM-A", "MEDIUM-A"],
        "conditions": ["CONDITION-A", "CONDITION-A"],
    }
    first_snapshot = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(first))
    second_snapshot = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(second))
    assert first_snapshot == second_snapshot
    assert second_snapshot.payload.rules[0].scope.materials == (
        "TEST-A",
        "TEST-B",
    )


def test_ordered_rule_array_changes_content_identity() -> None:
    first = _base_payload()
    second_rule = json.loads(json.dumps(first["rules"][0]))
    second_rule["rule_ref"] = "MR-TEST-002"
    second_rule["statement"] = "Zweiter synthetischer Vertragstest."
    first["rules"].append(second_rule)
    reversed_rules = {**first, "rules": list(reversed(first["rules"]))}
    a = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(first))
    b = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(reversed_rules))
    assert a.content_sha256 != b.content_sha256
    assert a.snapshot_id != b.snapshot_id


def test_content_hash_uses_exact_domain_separated_canonical_bytes() -> None:
    snapshot = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(_base_payload()))
    assert (
        snapshot.content_sha256
        == hashlib.sha256(CONTENT_HASH_DOMAIN + snapshot.canonical_bytes).hexdigest()
    )
    assert snapshot.canonical_bytes == canonicalize_payload(snapshot.payload)
    assert not snapshot.canonical_bytes.startswith(b"\xef\xbb\xbf")


def test_unicode_homoglyphs_are_not_casefolded_or_collapsed() -> None:
    latin = _base_payload()
    cyrillic = _base_payload()
    latin["rules"][0]["material"] = "A-MATERIAL"
    cyrillic["rules"][0]["material"] = "А-MATERIAL"  # Cyrillic U+0410.
    a = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(latin))
    b = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(cyrillic))
    assert a.content_sha256 != b.content_sha256
    assert a.payload.rules[0].material != b.payload.rules[0].material


def test_non_nfc_and_lone_surrogates_fail_closed() -> None:
    non_nfc = _base_payload()
    non_nfc["rules"][0]["statement"] = "e\u0301"
    assert _error(_raw(non_nfc)) == MaterialRulesetErrorCode.NON_NFC.value
    lone_surrogate = _raw(_base_payload()).replace(
        "Synthetischer Vertragstest – keine Werkstoffaussage.", "\\ud800"
    )
    assert _error(lone_surrogate) == MaterialRulesetErrorCode.INVALID_UNICODE.value
    assert (
        _error(b'{"snapshot_schema_version":1,"bad":"\xff"}')
        == MaterialRulesetErrorCode.INVALID_UNICODE.value
    )


@pytest.mark.parametrize("token", ["1.0", "NaN", "Infinity", "-Infinity"])
def test_floats_and_non_finite_numbers_are_rejected_before_schema(token) -> None:
    raw = _raw(_base_payload()).replace(
        '"snapshot_schema_version": 1', f'"snapshot_schema_version": {token}'
    )
    assert _error(raw) == MaterialRulesetErrorCode.FLOAT_FORBIDDEN.value


def test_boolean_and_string_types_are_not_coerced() -> None:
    string_boolean = _base_payload()
    string_boolean["positive_statement_allowed"] = "false"
    assert _error(_raw(string_boolean)) == MaterialRulesetErrorCode.INVALID_TYPE.value
    boolean_string = _base_payload()
    boolean_string["rules"][0]["material"] = False
    assert _error(_raw(boolean_string)) == MaterialRulesetErrorCode.INVALID_TYPE.value


@pytest.mark.parametrize("state", ["bound", "reviewed", "approved", "grounded"])
def test_evidence_state_is_exactly_unbound(state) -> None:
    payload = _base_payload()
    payload["rules"][0]["evidence_binding"] = {"state": state}
    assert _error(_raw(payload)) == MaterialRulesetErrorCode.INVALID_EVIDENCE.value


def test_evidence_null_and_additional_references_are_rejected() -> None:
    for value in (
        None,
        {"state": "unbound", "claim_id": "claim-1"},
        {"state": "unbound", "source_ref": "source-1"},
        {"state": "unbound", "review_ref": "review-1"},
        {"state": "unbound", "authority_ref": "authority-1"},
    ):
        payload = _base_payload()
        payload["rules"][0]["evidence_binding"] = value
        assert _error(_raw(payload)) == MaterialRulesetErrorCode.INVALID_EVIDENCE.value


def test_duplicate_properties_are_rejected_before_object_construction() -> None:
    raw = _raw(_base_payload())
    raw = raw.replace(
        '"domain_pack_id": "material.test.v1"',
        '"domain_pack_id":"material.test.v1","domain_pack_id":"material.other.v1"',
    )
    assert _error(raw) == MaterialRulesetErrorCode.DUPLICATE_PROPERTY.value


def test_unknown_fields_and_duplicate_rule_refs_fail_closed() -> None:
    unknown = _base_payload()
    unknown["reviewed"] = False
    assert _error(_raw(unknown)) == MaterialRulesetErrorCode.UNKNOWN_FIELD.value
    duplicate = _base_payload()
    duplicate["rules"].append(json.loads(json.dumps(duplicate["rules"][0])))
    assert _error(_raw(duplicate)) == MaterialRulesetErrorCode.DUPLICATE_RULE_REF.value


def test_domain_values_are_deeply_immutable_and_export_fresh_containers() -> None:
    snapshot = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(_base_payload()))
    with pytest.raises(FrozenInstanceError):
        snapshot.payload.domain_pack_id = "material.other.v1"  # type: ignore[misc]
    with pytest.raises(TypeError):
        snapshot.payload.rules[0] = snapshot.payload.rules[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.payload.rules[0].scope.materials[0] = "OTHER"  # type: ignore[index]
    assert isinstance(snapshot.payload.rules[0].evidence_binding, EvidenceBindingV1)
    exported = snapshot.payload.to_dict()
    exported["rules"][0]["scope"]["materials"].append("MUTATION")
    assert "MUTATION" not in snapshot.payload.rules[0].scope.materials
    assert (
        "MUTATION" not in snapshot.payload.to_dict()["rules"][0]["scope"]["materials"]
    )


def test_direct_domain_construction_rejects_mutable_or_noncanonical_scope() -> None:
    with pytest.raises(TypeError):
        MaterialRuleScopeV1(  # type: ignore[arg-type]
            materials=["A"], media=("M",), conditions=()
        )
    with pytest.raises(ValueError):
        MaterialRuleScopeV1(materials=("B", "A"), media=("M",), conditions=())


def test_identity_prefixes_empty_values_and_hash_binding() -> None:
    generated = generate_ruleset_id()
    assert validate_ruleset_id(generated) == generated
    for invalid in ("", "ruleset_" + "1" * 32, "mrs_" + "G" * 32):
        with pytest.raises(MaterialRulesetValidationError):
            validate_ruleset_id(invalid)
    snapshot = MaterialRulesetSnapshotV1.from_json(RULESET_ID, _raw(_base_payload()))
    assert validate_snapshot_id(snapshot.snapshot_id) == snapshot.snapshot_id
    with pytest.raises(MaterialRulesetValidationError):
        validate_snapshot_id("snapshot_" + "1" * 64)
    assert (
        derive_snapshot_id(RULESET_ID, snapshot.content_sha256) == snapshot.snapshot_id
    )
    assert (
        derive_snapshot_id("mrs_" + "2" * 32, snapshot.content_sha256)
        != snapshot.snapshot_id
    )


def test_repeated_processes_produce_the_same_identity() -> None:
    raw = _raw(_base_payload(), separators=(",", ":"))
    script = (
        "import sys;"
        "from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1;"
        f"s=MaterialRulesetSnapshotV1.from_json('{RULESET_ID}',sys.stdin.read());"
        "print(s.content_sha256+'|'+s.snapshot_id+'|'+s.canonical_bytes.hex())"
    )
    outputs = {
        subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            input=raw,
            text=True,
        ).strip()
        for _ in range(3)
    }
    assert len(outputs) == 1
