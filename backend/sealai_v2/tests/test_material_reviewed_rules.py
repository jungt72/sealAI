from __future__ import annotations

from dataclasses import replace
import json
import pickle

import pytest

from sealai_v2.core.contracts import MaterialConstraintVerdict, VerifiedIdentity
from sealai_v2.core.material_evidence import (
    EvidenceClaimScopeV1,
    EvidenceManifestSnapshotV1,
    derive_claim_ref,
    derive_source_ref,
)
from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    EvidenceRuntimeBindingV1,
)
from sealai_v2.core.material_evidence_review import (
    EvidenceReviewProjection,
    EvidenceReviewSnapshotV1,
    FactualApprovalState,
    FactualReviewState,
)
from sealai_v2.core.material_reviewed_rules import (
    EvidenceReviewedMaterialRulesV1,
    ReviewedMaterialRulesErrorCode,
    ReviewedMaterialRulesIntegrityError,
    ReviewedMaterialRulesValidationError,
    _bind_evidence_reviewed_material_rules,
    _validate_reviewed_material_rules,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.medium_catalog import (
    MediumCatalogSnapshotV1,
    MediumIdentityKind,
    _bind_evidence_verified_medium_catalog,
    derive_media_id,
)
from sealai_v2.db.material_reviewed_rules import ReviewedMaterialRulesRepository


RULESET_ID = "mrs_" + "1" * 32
MANIFEST_ID = "mef_" + "2" * 32
REVIEW_ID = "mer_" + "3" * 32
CATALOG_ID = "mcf_" + "4" * 32
RULE_REF = "MR-SYNTHETIC-INCOMPATIBILITY"
MATERIAL = "SYNTHETIC-COMPOUND-70"
CONDITION = "condition:static-25c"
STATEMENT = "Synthetic reviewed incompatibility claim."
MEDIA_ID = derive_media_id(
    "Synthetic Test Medium", MediumIdentityKind.CHEMICAL_SUBSTANCE
)


def _dependencies(
    *,
    verdict: str = "unvertraeglich",
    rule_statement: str = STATEMENT,
    claim_text: str = STATEMENT,
    claim_type: str = "incompatibility",
    scope_materials: list[str] | None = None,
    catalog_contains_medium: bool = True,
    approved: bool = True,
):
    scope = EvidenceClaimScopeV1(
        materials=tuple(scope_materials or [MATERIAL]),
        media=(MEDIA_ID,),
        conditions=(CONDITION,),
    )
    ruleset = MaterialRulesetSnapshotV1.from_json(
        RULESET_ID,
        json.dumps(
            {
                "snapshot_schema_version": 1,
                "canonicalization_version": 1,
                "mat_gov_contract_version": "MAT-GOV-03A.v1",
                "domain_pack_id": "material.test.v1",
                "positive_statement_allowed": False,
                "rules": [
                    {
                        "rule_ref": RULE_REF,
                        "material": MATERIAL,
                        "medium": MEDIA_ID,
                        "condition": CONDITION,
                        "verdict": verdict,
                        "statement": rule_statement,
                        "scope": scope.to_dict(),
                        "evidence_binding": {"state": "unbound"},
                    }
                ],
            }
        ),
    )
    source_identity = {
        "document_id": "SYNTHETIC-DOC",
        "document_revision": "rev-1",
        "publication_edition": "test-edition",
        "content_sha256": "5" * 64,
    }
    source_ref = derive_source_ref(**source_identity)
    claim_ref = derive_claim_ref(claim_text=claim_text, scope=scope)
    evidence = EvidenceManifestSnapshotV1.from_json(
        MANIFEST_ID,
        json.dumps(
            {
                "evidence_manifest_schema_version": 1,
                "canonicalization_version": 1,
                "mat_evid_contract_version": "MAT-EVID-01A.v1",
                "ruleset_snapshot_id": ruleset.snapshot_id,
                "domain_pack_id": "material.test.v1",
                "sources": [{"source_ref": source_ref, **source_identity}],
                "claims": [
                    {
                        "claim_ref": claim_ref,
                        "claim_text": claim_text,
                        "scope": scope.to_dict(),
                        "source_refs": [source_ref],
                    }
                ],
                "rule_claim_bindings": [{"rule_ref": RULE_REF, "claim_ref": claim_ref}],
            }
        ),
    )
    review = EvidenceReviewSnapshotV1.from_json(
        REVIEW_ID,
        json.dumps(
            {
                "review_schema_version": 1,
                "canonicalization_version": 1,
                "mat_evid_review_contract_version": "MAT-EVID-01C.v1",
                "evidence_snapshot_id": evidence.snapshot_id,
                "evidence_content_sha256": evidence.content_sha256,
                "evidence_manifest_schema_version": 1,
                "evidence_contract_version": "MAT-EVID-01A.v1",
                "sources": [
                    {
                        "source_ref": source_ref,
                        "document_id": "SYNTHETIC-DOC",
                        "document_title": "Synthetic test document",
                        "publisher": "Synthetic Test Publisher",
                        "document_type": "manufacturer_datasheet",
                        "document_revision": "rev-1",
                        "publication_edition": "test-edition",
                        "content_sha256": "5" * 64,
                        "locator": {"state": "exact", "value": "test section"},
                        "rights_state": "permitted",
                        "rights_basis": "Synthetic test permission",
                        "excerpt": {"state": "omitted"},
                    }
                ],
                "claims": [
                    {
                        "claim_ref": claim_ref,
                        "claim_type": claim_type,
                        "scope": scope.to_dict(),
                        "required_source_types": ["manufacturer_datasheet"],
                    }
                ],
                "claim_relations": [],
            }
        ),
    )
    projection = EvidenceReviewProjection(
        FactualReviewState.REVIEWED,
        (
            FactualApprovalState.APPROVED
            if approved
            else FactualApprovalState.NOT_APPROVED
        ),
        "subject:reviewer",
        "subject:approver" if approved else "UNASSIGNED",
        2 if approved else 1,
        "6" * 64,
    )
    binding = EvidenceRuntimeBindingV1(
        binding_id="mshb_" + "7" * 32,
        state=EvidenceRuntimeBindingState.BOUND_UNREVIEWED,
        ruleset_snapshot_id=ruleset.snapshot_id,
        ruleset_content_sha256=ruleset.content_sha256,
        evidence_snapshot_id=evidence.snapshot_id,
        evidence_content_sha256=evidence.content_sha256,
        evidence_manifest_schema_version=1,
        evidence_canonicalization_version=1,
        evidence_contract_version="MAT-EVID-01A.v1",
        domain_pack_id="material.test.v1",
        domain_pack_version="material.test.v1",
        evaluator_version="test-evaluator.v1",
        kernel_version="test-kernel.v1",
    )
    entries = []
    if catalog_contains_medium:
        entries.append(
            {
                "media_id": MEDIA_ID,
                "canonical_name": "Synthetic Test Medium",
                "identity_kind": "chemical_substance",
                "aliases": [],
                "evidence_review_snapshot_id": "mrv_" + "8" * 64,
                "evidence_review_content_sha256": "9" * 64,
                "claim_refs": ["mec_" + "a" * 64],
            }
        )
    raw_catalog = MediumCatalogSnapshotV1.from_json(
        CATALOG_ID,
        json.dumps(
            {
                "media_catalog_schema_version": 1,
                "canonicalization_version": 1,
                "med_norm_contract_version": "MED-NORM-01.v1",
                "domain_pack_id": "material.test.v1",
                "entries": entries,
            }
        ),
    )
    catalog_state = {"current": True}

    catalog = _bind_evidence_verified_medium_catalog(
        raw_catalog,
        tenant_id="tenant-a",
        revalidate=lambda: (
            None
            if catalog_state["current"]
            else (_ for _ in ()).throw(RuntimeError("catalog approval revoked"))
        ),
    )
    return binding, ruleset, evidence, review, projection, catalog, catalog_state


def _two_rule_dependencies(*, reverse: bool):
    binding, base_ruleset, base_evidence, base_review, projection, catalog, state = (
        _dependencies()
    )
    second_rule_ref = "MR-SYNTHETIC-CONDITIONAL"
    second_material = "SYNTHETIC-COMPOUND-80"
    second_condition = "condition:dynamic-40c"
    second_statement = "Synthetic reviewed conditional claim."
    second_scope = EvidenceClaimScopeV1(
        materials=(second_material,),
        media=(MEDIA_ID,),
        conditions=(second_condition,),
    )
    ruleset_value = base_ruleset.payload.to_dict()
    ruleset_value["rules"].append(
        {
            "rule_ref": second_rule_ref,
            "material": second_material,
            "medium": MEDIA_ID,
            "condition": second_condition,
            "verdict": "bedingt",
            "statement": second_statement,
            "scope": second_scope.to_dict(),
            "evidence_binding": {"state": "unbound"},
        }
    )
    if reverse:
        ruleset_value["rules"].reverse()
    ruleset = MaterialRulesetSnapshotV1.from_json(RULESET_ID, json.dumps(ruleset_value))

    source_identity = {
        "document_id": "SYNTHETIC-DOC-2",
        "document_revision": "rev-1",
        "publication_edition": "test-edition",
        "content_sha256": "b" * 64,
    }
    source_ref = derive_source_ref(**source_identity)
    claim_ref = derive_claim_ref(
        claim_text=second_statement,
        scope=second_scope,
    )
    evidence_value = base_evidence.payload.to_dict()
    evidence_value["ruleset_snapshot_id"] = ruleset.snapshot_id
    evidence_value["sources"].append({"source_ref": source_ref, **source_identity})
    evidence_value["sources"].sort(key=lambda item: item["source_ref"])
    evidence_value["claims"].append(
        {
            "claim_ref": claim_ref,
            "claim_text": second_statement,
            "scope": second_scope.to_dict(),
            "source_refs": [source_ref],
        }
    )
    evidence_value["claims"].sort(key=lambda item: item["claim_ref"])
    evidence_value["rule_claim_bindings"].append(
        {"rule_ref": second_rule_ref, "claim_ref": claim_ref}
    )
    evidence_value["rule_claim_bindings"].sort(
        key=lambda item: (item["rule_ref"], item["claim_ref"])
    )
    evidence = EvidenceManifestSnapshotV1.from_json(
        MANIFEST_ID, json.dumps(evidence_value)
    )

    review_value = base_review.payload.to_dict()
    review_value["evidence_snapshot_id"] = evidence.snapshot_id
    review_value["evidence_content_sha256"] = evidence.content_sha256
    review_value["sources"].append(
        {
            "source_ref": source_ref,
            "document_id": "SYNTHETIC-DOC-2",
            "document_title": "Synthetic test document 2",
            "publisher": "Synthetic Test Publisher",
            "document_type": "manufacturer_datasheet",
            "document_revision": "rev-1",
            "publication_edition": "test-edition",
            "content_sha256": "b" * 64,
            "locator": {"state": "exact", "value": "test section 2"},
            "rights_state": "permitted",
            "rights_basis": "Synthetic test permission",
            "excerpt": {"state": "omitted"},
        }
    )
    review_value["sources"].sort(key=lambda item: item["source_ref"])
    review_value["claims"].append(
        {
            "claim_ref": claim_ref,
            "claim_type": "conditional_compatibility",
            "scope": second_scope.to_dict(),
            "required_source_types": ["manufacturer_datasheet"],
        }
    )
    review_value["claims"].sort(key=lambda item: item["claim_ref"])
    review = EvidenceReviewSnapshotV1.from_json(REVIEW_ID, json.dumps(review_value))
    return (
        replace(
            binding,
            ruleset_snapshot_id=ruleset.snapshot_id,
            ruleset_content_sha256=ruleset.content_sha256,
            evidence_snapshot_id=evidence.snapshot_id,
            evidence_content_sha256=evidence.content_sha256,
        ),
        ruleset,
        evidence,
        review,
        projection,
        catalog,
        state,
    )


def test_exact_reviewed_nonpositive_rule_pack_is_accepted() -> None:
    dependencies = _dependencies()
    references = _validate_reviewed_material_rules(
        binding=dependencies[0],
        ruleset=dependencies[1],
        evidence=dependencies[2],
        review=dependencies[3],
        projection=dependencies[4],
        catalog=dependencies[5],
    )
    assert len(references) == 1
    assert references[0].rule_ref == RULE_REF
    assert references[0].verdict is MaterialConstraintVerdict.UNVERTRAEGLICH
    assert references[0].statement_claim_ref in references[0].claim_refs


def test_exact_reviewed_conditional_rule_pack_is_accepted() -> None:
    dependencies = _dependencies(
        verdict="bedingt", claim_type="conditional_compatibility"
    )
    references = _validate_reviewed_material_rules(
        binding=dependencies[0],
        ruleset=dependencies[1],
        evidence=dependencies[2],
        review=dependencies[3],
        projection=dependencies[4],
        catalog=dependencies[5],
    )
    assert references[0].verdict is MaterialConstraintVerdict.BEDINGT


def test_multiple_reviewed_rules_are_complete_and_permutation_invariant() -> None:
    results = []
    for reverse in (False, True):
        dependencies = _two_rule_dependencies(reverse=reverse)
        results.append(
            _validate_reviewed_material_rules(
                binding=dependencies[0],
                ruleset=dependencies[1],
                evidence=dependencies[2],
                review=dependencies[3],
                projection=dependencies[4],
                catalog=dependencies[5],
            )
        )
    assert results[0] == results[1]
    assert tuple(item.rule_ref for item in results[0]) == (
        "MR-SYNTHETIC-CONDITIONAL",
        RULE_REF,
    )


def test_reviewed_rule_reference_requires_exact_canonical_verdict_type() -> None:
    dependencies = _dependencies()
    reference = _validate_reviewed_material_rules(
        binding=dependencies[0],
        ruleset=dependencies[1],
        evidence=dependencies[2],
        review=dependencies[3],
        projection=dependencies[4],
        catalog=dependencies[5],
    )[0]
    with pytest.raises(ValueError, match="disqualify-only"):
        replace(reference, verdict="unvertraeglich")  # type: ignore[arg-type]


def test_repository_capability_is_nonpositive_live_and_nonserializable() -> None:
    dependencies = _dependencies()
    state = {"current": True}

    def revalidate() -> None:
        if not state["current"]:
            raise RuntimeError("review revoked")

    capability = _bind_evidence_reviewed_material_rules(
        binding=dependencies[0],
        ruleset=dependencies[1],
        evidence=dependencies[2],
        review=dependencies[3],
        projection=dependencies[4],
        catalog=dependencies[5],
        tenant_id="tenant-a",
        revalidate=revalidate,
    )
    assert capability.positive_statement_allowed is False
    assert capability.authority == "FACTUAL_REVIEWED_DISQUALIFY_ONLY"
    issued_references = capability.references
    capability.assert_current()
    state["current"] = False
    with pytest.raises(RuntimeError, match="revoked"):
        capability.references
    with pytest.raises(RuntimeError, match="revoked"):
        capability.authority
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(capability)
    with pytest.raises(ReviewedMaterialRulesValidationError, match="repository-issued"):
        EvidenceReviewedMaterialRulesV1(
            binding=dependencies[0],
            ruleset=dependencies[1],
            evidence=dependencies[2],
            review=dependencies[3],
            catalog=dependencies[5],
            references=issued_references,
            tenant_id="tenant-a",
            revalidate=lambda: None,
        )


@pytest.mark.parametrize(
    "overrides,code",
    [
        (
            {"verdict": "vertraeglich", "claim_type": "conditional_compatibility"},
            ReviewedMaterialRulesErrorCode.POSITIVE_RULE_FORBIDDEN,
        ),
        (
            {"rule_statement": "Different rule statement."},
            ReviewedMaterialRulesErrorCode.STATEMENT_UNBOUND,
        ),
        (
            {"claim_type": "other_technical"},
            ReviewedMaterialRulesErrorCode.CLAIM_TYPE_MISMATCH,
        ),
        (
            {"verdict": "bedingt", "claim_type": "incompatibility"},
            ReviewedMaterialRulesErrorCode.CLAIM_TYPE_MISMATCH,
        ),
        (
            {"scope_materials": [MATERIAL, "SYNTHETIC-FAMILY"]},
            ReviewedMaterialRulesErrorCode.NON_ATOMIC_SCOPE,
        ),
        (
            {"catalog_contains_medium": False},
            ReviewedMaterialRulesErrorCode.CATALOG_DRIFT,
        ),
        (
            {"approved": False},
            ReviewedMaterialRulesErrorCode.EVIDENCE_UNREVIEWED,
        ),
    ],
)
def test_reviewed_rule_pack_rejects_authority_gaps(overrides, code) -> None:
    dependencies = _dependencies(**overrides)
    with pytest.raises(ReviewedMaterialRulesValidationError) as caught:
        _validate_reviewed_material_rules(
            binding=dependencies[0],
            ruleset=dependencies[1],
            evidence=dependencies[2],
            review=dependencies[3],
            projection=dependencies[4],
            catalog=dependencies[5],
        )
    assert caught.value.code is code


def test_reviewed_rule_pack_revalidates_catalog_before_returning_references() -> None:
    dependencies = _dependencies()
    dependencies[6]["current"] = False
    with pytest.raises(RuntimeError, match="catalog approval revoked"):
        _validate_reviewed_material_rules(
            binding=dependencies[0],
            ruleset=dependencies[1],
            evidence=dependencies[2],
            review=dependencies[3],
            projection=dependencies[4],
            catalog=dependencies[5],
        )


def test_binding_identity_drift_fails_closed() -> None:
    dependencies = _dependencies()
    drifted = replace(dependencies[0], evidence_content_sha256="f" * 64)
    with pytest.raises(Exception, match="EVIDENCE_DRIFT"):
        _validate_reviewed_material_rules(
            binding=drifted,
            ruleset=dependencies[1],
            evidence=dependencies[2],
            review=dependencies[3],
            projection=dependencies[4],
            catalog=dependencies[5],
        )


class _StaticLoader:
    def __init__(self, value) -> None:
        self.value = value

    def load_snapshot(self, *_args, **_kwargs):
        return self.value


class _StaticBindingLoader:
    def __init__(self, value) -> None:
        self.value = value

    def load_binding(self, *_args, **_kwargs):
        return self.value


class _MutableReviewLoader(_StaticLoader):
    def __init__(self, snapshot, projection) -> None:
        super().__init__(snapshot)
        self.projection = projection

    def load_projection(self, *_args, **_kwargs):
        return self.projection


def test_repository_capability_reloads_review_before_every_use() -> None:
    binding, ruleset, evidence, review, projection, catalog, _state = _dependencies()
    repository = object.__new__(ReviewedMaterialRulesRepository)
    repository._bindings = _StaticBindingLoader(binding)
    repository._rulesets = _StaticLoader(ruleset)
    repository._evidence = _StaticLoader(evidence)
    repository._reviews = _MutableReviewLoader(review, projection)
    repository._catalogs = _StaticLoader(catalog)
    capability = repository.load_capability(
        binding_id=binding.binding_id,
        review_snapshot_id=review.review_snapshot_id,
        catalog_snapshot_id=catalog.snapshot_id,
        identity=VerifiedIdentity("tenant-a", "session-a", "subject-a"),
    )
    capability.assert_current()
    repository._reviews.projection = replace(
        projection,
        review_state=FactualReviewState.REVOKED,
        approval_state=FactualApprovalState.REVOKED,
    )
    with pytest.raises(ReviewedMaterialRulesIntegrityError) as caught:
        capability.assert_current()
    assert caught.value.code is ReviewedMaterialRulesErrorCode.DB_INTEGRITY


def test_repository_capability_rejects_same_id_binding_retarget() -> None:
    binding, ruleset, evidence, review, projection, catalog, _state = _dependencies()
    repository = object.__new__(ReviewedMaterialRulesRepository)
    repository._bindings = _StaticBindingLoader(binding)
    repository._rulesets = _StaticLoader(ruleset)
    repository._evidence = _StaticLoader(evidence)
    repository._reviews = _MutableReviewLoader(review, projection)
    repository._catalogs = _StaticLoader(catalog)
    capability = repository.load_capability(
        binding_id=binding.binding_id,
        review_snapshot_id=review.review_snapshot_id,
        catalog_snapshot_id=catalog.snapshot_id,
        identity=VerifiedIdentity("tenant-a", "session-a", "subject-a"),
    )
    repository._bindings.value = replace(binding, evaluator_version="test-evaluator.v2")
    with pytest.raises(ReviewedMaterialRulesIntegrityError) as caught:
        capability.assert_current()
    assert caught.value.code is ReviewedMaterialRulesErrorCode.IDENTITY_DRIFT


def test_repository_rejects_non_verified_identity() -> None:
    repository = object.__new__(ReviewedMaterialRulesRepository)
    with pytest.raises(TypeError, match="VerifiedIdentity"):
        repository.load_capability(
            binding_id="mshb_" + "1" * 32,
            review_snapshot_id="mrv_" + "2" * 64,
            catalog_snapshot_id="mcs_" + "3" * 64,
            identity=object(),  # type: ignore[arg-type]
        )


def test_repository_rejects_cross_tenant_capability_join() -> None:
    binding, ruleset, evidence, review, projection, catalog, _state = _dependencies()
    repository = object.__new__(ReviewedMaterialRulesRepository)
    repository._bindings = _StaticBindingLoader(binding)
    repository._rulesets = _StaticLoader(ruleset)
    repository._evidence = _StaticLoader(evidence)
    repository._reviews = _MutableReviewLoader(review, projection)
    repository._catalogs = _StaticLoader(catalog)
    with pytest.raises(ReviewedMaterialRulesValidationError) as caught:
        repository.load_capability(
            binding_id=binding.binding_id,
            review_snapshot_id=review.review_snapshot_id,
            catalog_snapshot_id=catalog.snapshot_id,
            identity=VerifiedIdentity("tenant-b", "session-b", "subject-b"),
        )
    assert caught.value.code is ReviewedMaterialRulesErrorCode.IDENTITY_DRIFT
