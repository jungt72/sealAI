from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence import (
    EvidenceClaimScopeV1,
    derive_claim_ref,
    derive_source_ref,
)
from sealai_v2.core.material_evidence_review import (
    APPROVE_ROLE,
    CREATE_ROLE,
    REVIEW_ROLE,
)
from sealai_v2.core.material_reviewed_rules import (
    ReviewedMaterialRulesErrorCode,
    ReviewedMaterialRulesIntegrityError,
)
from sealai_v2.core.medium_catalog import (
    MediumCatalogEntryV1,
    MediumIdentityKind,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_evidence_review import MaterialEvidenceReviewRepository
from sealai_v2.db.material_reviewed_rules import ReviewedMaterialRulesRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.medium_catalog import MediumCatalogRepository
from sealai_v2.db.migrate import _upgrade_engine, migration_status
from sealai_v2.tests.test_mat_evid_01c_review import _actor
from sealai_v2.tests.test_mat_gov_03b_persistence import _binding as _shadow_binding
from sealai_v2.tests.test_material_reviewed_rules import (
    CATALOG_ID,
    CONDITION,
    MEDIA_ID,
    RULE_REF,
    _dependencies,
)


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)

NOW = "2026-07-18T18:00:00Z"
IDENTITY = VerifiedIdentity("tenant-a", "session-owner", "subject:owner")
CATALOG_RULESET_ID = "mrs_" + "a" * 32
CATALOG_MANIFEST_ID = "mef_" + "b" * 32
CATALOG_REVIEW_ID = "mer_" + "c" * 32


def _store_reviewed_rule_chain(factory):
    binding, raw_ruleset, raw_evidence, raw_review, _, _, _ = _dependencies()
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=raw_ruleset.ruleset_id,
        domain_pack_id=raw_ruleset.payload.domain_pack_id,
        created_by_subject="subject:creator",
        created_at=NOW,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=raw_ruleset.ruleset_id,
        raw_payload=raw_ruleset.canonical_bytes,
        created_by_subject="subject:creator",
        created_at=NOW,
    )
    evidence_repository = MaterialEvidenceRepository(factory)
    evidence_repository.create_manifest(
        manifest_id=raw_evidence.manifest_id,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id=ruleset.payload.domain_pack_id,
        created_by_subject="subject:creator",
        created_at=NOW,
    )
    evidence = evidence_repository.store_snapshot(
        manifest_id=raw_evidence.manifest_id,
        raw_payload=raw_evidence.canonical_bytes,
        created_by_subject="subject:creator",
        created_at=NOW,
    )
    reviews = MaterialEvidenceReviewRepository(factory)
    reviews.create_review(
        review_id=raw_review.review_id,
        evidence_snapshot_id=evidence.snapshot_id,
        identity=_actor("subject:creator", CREATE_ROLE),
        created_at=NOW,
    )
    review = reviews.store_snapshot(
        review_id=raw_review.review_id,
        raw_payload=raw_review.canonical_bytes,
        identity=_actor("subject:creator", CREATE_ROLE),
        created_at=NOW,
    )
    reviews.record_review(
        review.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T18:01:00Z",
    )
    reviews.record_approval(
        review.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T18:02:00Z",
    )
    shadow = _shadow_binding(
        ruleset,
        suffix="7",
        domain_pack_version=binding.domain_pack_version,
        evaluator_version=binding.evaluator_version,
        kernel_version=binding.kernel_version,
        creator_subject=IDENTITY.subject,
    )
    assert shadow.binding_id == binding.binding_id
    MaterialShadowRepository(factory).create_binding(
        shadow,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=binding,
    )
    return binding, review, reviews


def _store_catalog(factory):
    placeholder = MediumCatalogEntryV1(
        media_id=MEDIA_ID,
        canonical_name="Synthetic Test Medium",
        identity_kind=MediumIdentityKind.CHEMICAL_SUBSTANCE,
        aliases=(),
        evidence_review_snapshot_id="mrv_" + "d" * 64,
        evidence_review_content_sha256="e" * 64,
        claim_refs=("mec_" + "f" * 64,),
    )
    scope = EvidenceClaimScopeV1(
        materials=("SYNTHETIC-MEDIA-IDENTITY",),
        media=(MEDIA_ID,),
        conditions=(placeholder.identity_assertion_ref,),
    )
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=CATALOG_RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:catalog-creator",
        created_at=NOW,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=CATALOG_RULESET_ID,
        raw_payload=json.dumps(
            {
                "snapshot_schema_version": 1,
                "canonicalization_version": 1,
                "mat_gov_contract_version": "MAT-GOV-03A.v1",
                "domain_pack_id": "material.test.v1",
                "positive_statement_allowed": False,
                "rules": [
                    {
                        "rule_ref": "MR-SYNTHETIC-MEDIA-IDENTITY",
                        "material": "SYNTHETIC-MEDIA-IDENTITY",
                        "medium": MEDIA_ID,
                        "condition": placeholder.identity_assertion_ref,
                        "verdict": "bedingt",
                        "statement": "Synthetic catalog identity test rule.",
                        "scope": scope.to_dict(),
                        "evidence_binding": {"state": "unbound"},
                    }
                ],
            }
        ),
        created_by_subject="subject:catalog-creator",
        created_at=NOW,
    )
    source_identity = {
        "document_id": "SYNTHETIC-CATALOG-DOC",
        "document_revision": "rev-1",
        "publication_edition": "test-edition",
        "content_sha256": "1" * 64,
    }
    source_ref = derive_source_ref(**source_identity)
    claim_text = "Synthetic catalog identity assertion."
    claim_ref = derive_claim_ref(claim_text=claim_text, scope=scope)
    evidence_repository = MaterialEvidenceRepository(factory)
    evidence_repository.create_manifest(
        manifest_id=CATALOG_MANIFEST_ID,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:catalog-creator",
        created_at=NOW,
    )
    evidence = evidence_repository.store_snapshot(
        manifest_id=CATALOG_MANIFEST_ID,
        raw_payload=json.dumps(
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
                "rule_claim_bindings": [
                    {
                        "rule_ref": "MR-SYNTHETIC-MEDIA-IDENTITY",
                        "claim_ref": claim_ref,
                    }
                ],
            }
        ),
        created_by_subject="subject:catalog-creator",
        created_at=NOW,
    )
    reviews = MaterialEvidenceReviewRepository(factory)
    reviews.create_review(
        review_id=CATALOG_REVIEW_ID,
        evidence_snapshot_id=evidence.snapshot_id,
        identity=_actor("subject:catalog-creator", CREATE_ROLE),
        created_at=NOW,
    )
    review = reviews.store_snapshot(
        review_id=CATALOG_REVIEW_ID,
        raw_payload=json.dumps(
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
                        "document_id": "SYNTHETIC-CATALOG-DOC",
                        "document_title": "Synthetic catalog test document",
                        "publisher": "Synthetic Test Publisher",
                        "document_type": "manufacturer_datasheet",
                        "document_revision": "rev-1",
                        "publication_edition": "test-edition",
                        "content_sha256": "1" * 64,
                        "locator": {"state": "exact", "value": "test section"},
                        "rights_state": "permitted",
                        "rights_basis": "Synthetic test permission",
                        "excerpt": {"state": "omitted"},
                    }
                ],
                "claims": [
                    {
                        "claim_ref": claim_ref,
                        "claim_type": "other_technical",
                        "scope": scope.to_dict(),
                        "required_source_types": ["manufacturer_datasheet"],
                    }
                ],
                "claim_relations": [],
            }
        ),
        identity=_actor("subject:catalog-creator", CREATE_ROLE),
        created_at=NOW,
    )
    reviews.record_review(
        review.review_snapshot_id,
        identity=_actor("subject:catalog-reviewer", REVIEW_ROLE),
        created_at="2026-07-18T18:03:00Z",
    )
    reviews.record_approval(
        review.review_snapshot_id,
        identity=_actor("subject:catalog-approver", APPROVE_ROLE),
        created_at="2026-07-18T18:04:00Z",
    )
    catalogs = MediumCatalogRepository(factory, reviews)
    catalogs.create_catalog(
        catalog_id=CATALOG_ID,
        identity=IDENTITY,
        domain_pack_id="material.test.v1",
        created_at=NOW,
    )
    return catalogs.store_snapshot(
        catalog_id=CATALOG_ID,
        raw_payload=json.dumps(
            {
                "media_catalog_schema_version": 1,
                "canonicalization_version": 1,
                "med_norm_contract_version": "MED-NORM-01.v1",
                "domain_pack_id": "material.test.v1",
                "entries": [
                    {
                        "media_id": MEDIA_ID,
                        "canonical_name": "Synthetic Test Medium",
                        "identity_kind": "chemical_substance",
                        "aliases": [],
                        "evidence_review_snapshot_id": review.review_snapshot_id,
                        "evidence_review_content_sha256": review.content_sha256,
                        "claim_refs": [claim_ref],
                    }
                ],
            }
        ),
        identity=IDENTITY,
        created_at="2026-07-18T18:05:00Z",
    )


def test_real_postgres_loads_exact_pack_and_revocation_invalidates_capability() -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_material_rules_01_test")
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0018", "20260718_0018")
    factory = make_sessionmaker(engine)
    binding, review, reviews = _store_reviewed_rule_chain(factory)
    catalog = _store_catalog(factory)
    repository = ReviewedMaterialRulesRepository(factory)
    capability = repository.load_capability(
        binding_id=binding.binding_id,
        review_snapshot_id=review.review_snapshot_id,
        catalog_snapshot_id=catalog.snapshot_id,
        identity=IDENTITY,
    )
    assert capability.references[0].rule_ref == RULE_REF
    assert capability.references[0].statement_claim_ref
    assert capability.ruleset.payload.rules[0].condition == CONDITION
    assert capability.positive_statement_allowed is False

    reviews.record_revocation(
        review.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T18:06:00Z",
    )
    with pytest.raises(ReviewedMaterialRulesIntegrityError) as caught:
        capability.references
    assert caught.value.code is ReviewedMaterialRulesErrorCode.DB_INTEGRITY
