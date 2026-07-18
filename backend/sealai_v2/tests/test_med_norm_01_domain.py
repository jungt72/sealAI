from __future__ import annotations

from dataclasses import replace
import itertools
import json
from pathlib import Path

import pytest

from sealai_v2.core.contracts import (
    EvaluationState,
    InputResolutionState,
    MaterialConstraintMatch,
    MaterialConstraintQuery,
    MaterialConstraintVerdict,
    MediumCardinality,
    RelationState,
    VerifiedIdentity,
)
from sealai_v2.core.material_constraints import resolve_material_constraint_matches
from sealai_v2.core.medium_catalog import (
    CanonicalMediumComponentV1,
    CatalogEvidenceProvenanceV1,
    EvidenceVerifiedMediumCatalogSnapshotV1,
    MediumCatalogEntryV1,
    MediumCatalogErrorCode,
    MediumCatalogSnapshotV1,
    MediumCatalogValidationError,
    MediumClassificationCandidateV1,
    MediumIdentityKind,
    MediumRelationshipKind,
    MediumRelationshipV1,
    NormalizedMaterialEvaluationV1,
    UserConfirmationProvenanceV1,
    _bind_evidence_verified_medium_catalog,
    create_user_confirmed_component,
    evaluate_normalized_media,
    parse_catalog_payload,
    derive_media_id,
    resolve_exact_catalog_values,
)


CATALOG_ID = "mcf_" + "1" * 32
REVIEW_ID = "mrv_" + "2" * 64
CLAIM_A = "mec_" + "3" * 64
CLAIM_B = "mec_" + "4" * 64
MEDIA_A = derive_media_id("Synthetic A", MediumIdentityKind.CHEMICAL_SUBSTANCE)
MEDIA_B = derive_media_id("Synthetic B", MediumIdentityKind.CHEMICAL_SUBSTANCE)
MEDIA_C = derive_media_id("Synthetic C", MediumIdentityKind.CHEMICAL_SUBSTANCE)
REF_A = "mcmp_" + "a" * 32
REF_B = "mcmp_" + "b" * 32
REF_C = "mcmp_" + "c" * 32
IDENTITY = VerifiedIdentity("tenant-a", "session-a", "subject-a")
GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures/med_norm_01_golden.json").read_text(
        encoding="utf-8"
    )
)


def _entry(
    media_id: str,
    name: str,
    *,
    kind: str = "chemical_substance",
    aliases: list[str] | None = None,
    claim_ref: str = CLAIM_A,
) -> dict:
    return {
        "media_id": media_id,
        "canonical_name": name,
        "identity_kind": kind,
        "aliases": aliases or [],
        "evidence_review_snapshot_id": REVIEW_ID,
        "evidence_review_content_sha256": "5" * 64,
        "claim_refs": [claim_ref],
    }


def _payload(entries: list[dict] | None = None) -> dict:
    return {
        "media_catalog_schema_version": 1,
        "canonicalization_version": 1,
        "med_norm_contract_version": "MED-NORM-01.v1",
        "domain_pack_id": "material.test.v1",
        "entries": entries or [],
    }


def _raw_snapshot(entries: list[dict] | None = None) -> MediumCatalogSnapshotV1:
    ordered = sorted(entries or [], key=lambda item: item["media_id"])
    return MediumCatalogSnapshotV1.from_json(CATALOG_ID, json.dumps(_payload(ordered)))


def _snapshot(
    entries: list[dict] | None = None,
) -> EvidenceVerifiedMediumCatalogSnapshotV1:
    return _bind_evidence_verified_medium_catalog(
        _raw_snapshot(entries), tenant_id=IDENTITY.tenant_id
    )


def _relationship(
    left: str = REF_A,
    right: str = REF_B,
    kind: MediumRelationshipKind = MediumRelationshipKind.CO_CONTACT,
) -> MediumRelationshipV1:
    return MediumRelationshipV1(kind, left, right)


def _result(media_id: str, verdict: MaterialConstraintVerdict, rule_ref: str):
    query = MaterialConstraintQuery(
        material="SYNTHETIC-MATERIAL",
        medium=media_id,
        material_state=InputResolutionState.KNOWN,
        medium_state=InputResolutionState.KNOWN,
        medium_cardinality=MediumCardinality.SINGLE,
        relation_state=RelationState.NOT_APPLICABLE,
    )
    match = MaterialConstraintMatch(
        rule_ref=rule_ref,
        verdict=verdict,
        statement="Synthetic test statement.",
        source_ref=f"matrix-cell:{rule_ref}",
    )
    return resolve_material_constraint_matches((match,), query=query)


def test_empty_catalog_is_valid_and_contains_no_media_facts() -> None:
    snapshot = _snapshot()
    assert snapshot.payload.entries == ()
    assert snapshot.payload.to_dict()["entries"] == []
    assert snapshot.snapshot_id.startswith("mcs_")


def test_catalog_and_entry_hashes_match_frozen_golden_contract() -> None:
    empty = _snapshot()
    single = _snapshot([_entry(MEDIA_A, "Synthetic A", aliases=["Synthetic Alpha"])])
    assert (empty.content_sha256, empty.snapshot_id) == (
        GOLDEN["empty"]["content_sha256"],
        GOLDEN["empty"]["snapshot_id"],
    )
    assert (single.content_sha256, single.snapshot_id) == (
        GOLDEN["single_entry"]["content_sha256"],
        GOLDEN["single_entry"]["snapshot_id"],
    )
    assert (
        single.payload.entries[0].entry_sha256 == GOLDEN["single_entry"]["entry_sha256"]
    )


def test_snapshot_identity_is_canonical_and_content_addressed() -> None:
    entries = [
        _entry(MEDIA_A, "Synthetic A", aliases=["Synthetic Alpha"]),
        _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
    ]
    left = _snapshot(entries)
    right = _snapshot(list(reversed(entries)))
    assert left == right
    assert left.canonical_bytes == right.canonical_bytes


def test_raw_inconsistent_or_unverified_snapshot_cannot_classify() -> None:
    raw = _raw_snapshot([_entry(MEDIA_A, "Synthetic A")])
    with pytest.raises(MediumCatalogValidationError) as inconsistent:
        MediumCatalogSnapshotV1(
            catalog_id=raw.catalog_id,
            payload=raw.payload,
            canonical_bytes=b"{}",
            content_sha256="0" * 64,
            snapshot_id="mcs_" + "1" * 64,
        )
    assert inconsistent.value.code is MediumCatalogErrorCode.HASH_MISMATCH
    with pytest.raises(TypeError, match="repository and Evidence verified"):
        resolve_exact_catalog_values(
            ("Synthetic A",),
            snapshot=raw,
            identity=IDENTITY,  # type: ignore[arg-type]
        )
    with pytest.raises(MediumCatalogValidationError, match="repository-issued"):
        EvidenceVerifiedMediumCatalogSnapshotV1(raw, IDENTITY.tenant_id)


def test_verified_catalog_rejects_foreign_tenant_and_duck_type() -> None:
    snapshot = _snapshot([_entry(MEDIA_A, "Synthetic A")])
    with pytest.raises(MediumCatalogValidationError, match="another tenant"):
        resolve_exact_catalog_values(
            ("Synthetic A",),
            snapshot=snapshot,
            identity=VerifiedIdentity("tenant-b", "session-b", "subject-b"),
        )
    with pytest.raises(TypeError, match="repository and Evidence verified"):
        resolve_exact_catalog_values(
            ("Synthetic A",),
            snapshot=object(),
            identity=IDENTITY,  # type: ignore[arg-type]
        )
    foreign_entry = _snapshot(
        [_entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B)]
    ).payload.entries[0]
    with pytest.raises(MediumCatalogValidationError, match="absent"):
        CatalogEvidenceProvenanceV1(snapshot, foreign_entry)


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda value: value.update(extra=True), MediumCatalogErrorCode.UNKNOWN_FIELD),
        (
            lambda value: value.update(media_catalog_schema_version=True),
            MediumCatalogErrorCode.INVALID_TYPE,
        ),
        (
            lambda value: value.update(med_norm_contract_version="MED-NORM-01.v2"),
            MediumCatalogErrorCode.UNKNOWN_SCHEMA,
        ),
        (
            lambda value: value.update(domain_pack_id="Material Test"),
            MediumCatalogErrorCode.INVALID_ID,
        ),
    ],
)
def test_catalog_schema_fails_closed(mutation, code) -> None:
    value = _payload()
    mutation(value)
    with pytest.raises(MediumCatalogValidationError) as caught:
        parse_catalog_payload(json.dumps(value))
    assert caught.value.code is code


def test_duplicate_json_property_and_float_fail_closed() -> None:
    with pytest.raises(MediumCatalogValidationError) as duplicate:
        parse_catalog_payload(
            '{"media_catalog_schema_version":1,"media_catalog_schema_version":1,'
            '"canonicalization_version":1,"med_norm_contract_version":'
            '"MED-NORM-01.v1","domain_pack_id":"material.test.v1","entries":[]}'
        )
    assert duplicate.value.code is MediumCatalogErrorCode.DUPLICATE_PROPERTY
    value = _payload()
    value["entries"] = [
        {
            **_entry(MEDIA_A, "Synthetic A"),
            "aliases": [1.25],
        }
    ]
    with pytest.raises(MediumCatalogValidationError) as floating:
        parse_catalog_payload(json.dumps(value))
    assert floating.value.code is MediumCatalogErrorCode.FLOAT_FORBIDDEN


def test_every_entry_requires_exact_review_and_claim_provenance() -> None:
    entry = MediumCatalogEntryV1(
        media_id=derive_media_id("Synthetic A", MediumIdentityKind.TRADE_NAME),
        canonical_name="Synthetic A",
        identity_kind=MediumIdentityKind.TRADE_NAME,
        aliases=(),
        evidence_review_snapshot_id=REVIEW_ID,
        evidence_review_content_sha256="5" * 64,
        claim_refs=(CLAIM_A,),
    )
    assert entry.entry_sha256
    assert entry.identity_assertion_ref.startswith("med-norm-identity-sha256:")
    assert replace(entry, aliases=("Synthetic Alias",)).identity_assertion_ref != (
        entry.identity_assertion_ref
    )
    with pytest.raises(MediumCatalogValidationError):
        replace(entry, claim_refs=())
    with pytest.raises(MediumCatalogValidationError):
        replace(entry, evidence_review_snapshot_id="https://example.invalid/source")
    with pytest.raises(MediumCatalogValidationError):
        replace(entry, canonical_name="Redefined Synthetic Identity")


def test_missing_unknown_ambiguous_and_known_are_distinct() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A", aliases=["Shared Alias"]),
            _entry(MEDIA_B, "Synthetic B", aliases=["Shared Alias"], claim_ref=CLAIM_B),
        ]
    )
    missing = resolve_exact_catalog_values((), snapshot=snapshot, identity=IDENTITY)
    unknown = resolve_exact_catalog_values(
        ("Unlisted",), snapshot=snapshot, identity=IDENTITY
    )
    ambiguous = resolve_exact_catalog_values(
        ("Shared Alias",), snapshot=snapshot, identity=IDENTITY
    )
    known = resolve_exact_catalog_values(
        ("Synthetic A",),
        snapshot=snapshot,
        identity=IDENTITY,
        component_refs=(REF_A,),
    )
    assert (
        missing.medium_state,
        missing.medium_cardinality,
        missing.relation_state,
    ) == (
        InputResolutionState.MISSING,
        MediumCardinality.NONE,
        RelationState.UNDETERMINED,
    )
    assert unknown.medium_state is InputResolutionState.UNKNOWN
    assert ambiguous.medium_state is InputResolutionState.AMBIGUOUS
    assert known.medium_state is InputResolutionState.KNOWN
    assert known.medium_cardinality is MediumCardinality.SINGLE
    assert known.relation_state is RelationState.NOT_APPLICABLE


@pytest.mark.parametrize(
    "whole_value",
    (
        "Synthetic A + Synthetic B",
        "Synthetic A / Synthetic B",
        "Synthetic A, Synthetic B",
        "Synthetic A und Synthetic B",
    ),
)
def test_punctuation_and_conjunctions_never_prove_multiple_media(whole_value) -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
        ]
    )
    result = resolve_exact_catalog_values(
        (whole_value,), snapshot=snapshot, identity=IDENTITY
    )
    assert result.medium_state is InputResolutionState.UNKNOWN
    assert result.medium_cardinality is MediumCardinality.UNKNOWN
    assert result.components == ()


def test_structured_multiple_media_are_unresolved_without_explicit_relations() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
        ]
    )
    result = resolve_exact_catalog_values(
        ("Synthetic A", "Synthetic B"),
        snapshot=snapshot,
        identity=IDENTITY,
        component_refs=(REF_A, REF_B),
    )
    assert result.medium_state is InputResolutionState.KNOWN
    assert result.medium_cardinality is MediumCardinality.MULTIPLE
    assert result.relation_state is RelationState.UNRESOLVED
    assert not result.evaluable


def test_structured_multiple_media_require_complete_pairwise_relations() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
            _entry(MEDIA_C, "Synthetic C", claim_ref="mec_" + "6" * 64),
        ]
    )
    with pytest.raises(MediumCatalogValidationError) as caught:
        resolve_exact_catalog_values(
            ("Synthetic A", "Synthetic B", "Synthetic C"),
            snapshot=snapshot,
            identity=IDENTITY,
            component_refs=(REF_A, REF_B, REF_C),
            relationships=(_relationship(),),
        )
    assert caught.value.code is MediumCatalogErrorCode.RELATION_INCOMPLETE
    resolved = resolve_exact_catalog_values(
        ("Synthetic A", "Synthetic B", "Synthetic C"),
        snapshot=snapshot,
        identity=IDENTITY,
        component_refs=(REF_A, REF_B, REF_C),
        relationships=(
            _relationship(REF_A, REF_B),
            _relationship(REF_A, REF_C),
            _relationship(REF_B, REF_C),
        ),
    )
    assert resolved.relation_state is RelationState.RESOLVED
    assert resolved.evaluable


def test_resolved_pair_rejects_multiple_conflicting_relationship_assertions() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
        ]
    )
    with pytest.raises(MediumCatalogValidationError) as caught:
        resolve_exact_catalog_values(
            ("Synthetic A", "Synthetic B"),
            snapshot=snapshot,
            identity=IDENTITY,
            component_refs=(REF_A, REF_B),
            relationships=(
                _relationship(kind=MediumRelationshipKind.CO_CONTACT),
                _relationship(kind=MediumRelationshipKind.MIXTURE),
            ),
        )
    assert caught.value.code is MediumCatalogErrorCode.RELATION_INCOMPLETE


def test_generated_component_identity_is_media_order_invariant() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
        ]
    )
    left = resolve_exact_catalog_values(
        ("Synthetic A", "Synthetic B"), snapshot=snapshot, identity=IDENTITY
    )
    right = resolve_exact_catalog_values(
        ("Synthetic B", "Synthetic A"), snapshot=snapshot, identity=IDENTITY
    )
    assert tuple(
        (item.component_ref, item.media_id) for item in left.components
    ) == tuple((item.component_ref, item.media_id) for item in right.components)


def test_llm_candidate_can_never_become_canonical_provenance() -> None:
    candidate = MediumClassificationCandidateV1((MEDIA_A,))
    assert candidate.authoritative is False
    with pytest.raises(MediumCatalogValidationError):
        replace(candidate, authoritative=True)
    with pytest.raises(MediumCatalogValidationError):
        CanonicalMediumComponentV1(REF_A, MEDIA_A, candidate)  # type: ignore[arg-type]


def test_user_confirmation_still_pins_exact_catalog_evidence() -> None:
    snapshot = _snapshot([_entry(MEDIA_A, "Synthetic A")])
    confirmed = create_user_confirmed_component(
        snapshot=snapshot,
        media_id=MEDIA_A,
        component_ref=REF_A,
        confirmation_ref="mconf_" + "7" * 32,
        identity=IDENTITY,
        hmac_key=b"synthetic-test-key-material-32b!",
        hmac_key_id="medium-confirmation.v1",
    )
    assert isinstance(confirmed.provenance, UserConfirmationProvenanceV1)
    assert confirmed.provenance.catalog.media_id == MEDIA_A
    assert confirmed.provenance.tenant_ref_hmac != confirmed.provenance.subject_ref_hmac
    with pytest.raises(MediumCatalogValidationError):
        create_user_confirmed_component(
            snapshot=snapshot,
            media_id=MEDIA_A,
            component_ref=REF_A,
            confirmation_ref="mconf_" + "7" * 32,
            identity=VerifiedIdentity("tenant-b", "session-b", "subject-b"),
            hmac_key=b"synthetic-test-key-material-32b!",
            hmac_key_id="medium-confirmation.v1",
        )
    with pytest.raises(MediumCatalogValidationError):
        UserConfirmationProvenanceV1(
            catalog=confirmed.provenance.catalog,
            confirmation_ref="mconf_" + "7" * 32,
            tenant_ref_hmac="8" * 64,
            subject_ref_hmac="9" * 64,
            hmac_key_id="medium-confirmation.v1",
        )


def test_unresolved_input_blocks_without_calling_component_evaluator() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
        ]
    )
    medium_input = resolve_exact_catalog_values(
        ("Synthetic A", "Synthetic B"),
        snapshot=snapshot,
        identity=IDENTITY,
        component_refs=(REF_A, REF_B),
    )

    def forbidden(_component):
        raise AssertionError("unresolved media reached evaluator")

    result = evaluate_normalized_media(medium_input, evaluate_component=forbidden)
    assert result.evaluation_state is EvaluationState.BLOCKED
    assert result.verdict is None
    assert result.positive_statement_allowed is False


def test_direct_blocked_result_requires_stable_blocker() -> None:
    missing = resolve_exact_catalog_values((), snapshot=_snapshot(), identity=IDENTITY)
    with pytest.raises(ValueError, match="requires a stable blocker"):
        NormalizedMaterialEvaluationV1(missing, EvaluationState.BLOCKED)


def test_each_resolved_medium_is_evaluated_and_attributed() -> None:
    snapshot = _snapshot(
        [
            _entry(MEDIA_A, "Synthetic A"),
            _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
        ]
    )
    medium_input = resolve_exact_catalog_values(
        ("Synthetic A", "Synthetic B"),
        snapshot=snapshot,
        identity=IDENTITY,
        component_refs=(REF_A, REF_B),
        relationships=(_relationship(),),
    )
    called: list[str] = []

    def evaluator(component):
        called.append(component.media_id)
        if component.media_id == MEDIA_A:
            return _result(MEDIA_A, MaterialConstraintVerdict.BEDINGT, "MR-A")
        return _result(MEDIA_B, MaterialConstraintVerdict.UNVERTRAEGLICH, "MR-B")

    result = evaluate_normalized_media(medium_input, evaluate_component=evaluator)
    assert set(called) == {MEDIA_A, MEDIA_B}
    assert result.evaluation_state is EvaluationState.EVALUATED
    assert result.verdict is MaterialConstraintVerdict.UNVERTRAEGLICH
    assert result.decisive_ref == f"{REF_B}:MR-B"
    assert {(item.component_ref, item.media_id) for item in result.matches} == {
        (REF_A, MEDIA_A),
        (REF_B, MEDIA_B),
    }
    assert len(result.conditions) == 1
    assert result.positive_statement_allowed is False


def test_component_and_relationship_order_do_not_change_evaluation() -> None:
    entries = [
        _entry(MEDIA_A, "Synthetic A"),
        _entry(MEDIA_B, "Synthetic B", claim_ref=CLAIM_B),
    ]
    snapshot = _snapshot(entries)
    projections = set()
    for values in itertools.permutations(
        (("Synthetic A", REF_A), ("Synthetic B", REF_B))
    ):
        observed = tuple(item[0] for item in values)
        refs = tuple(item[1] for item in values)
        relation = MediumRelationshipV1(
            MediumRelationshipKind.CO_CONTACT, min(refs), max(refs)
        )
        medium_input = resolve_exact_catalog_values(
            observed,
            snapshot=snapshot,
            identity=IDENTITY,
            component_refs=refs,
            relationships=(relation,),
        )

        def evaluator(component):
            return _result(
                component.media_id,
                MaterialConstraintVerdict.BEDINGT,
                "MR-A" if component.media_id == MEDIA_A else "MR-B",
            )

        result = evaluate_normalized_media(medium_input, evaluate_component=evaluator)
        projections.add(
            (
                result.verdict,
                result.decisive_ref,
                tuple(item.decisive_ref for item in result.matches),
            )
        )
    assert len(projections) == 1
