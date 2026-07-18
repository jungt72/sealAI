from __future__ import annotations

from alembic import command
import json
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

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
from sealai_v2.core.medium_catalog import (
    MediumCatalogEntryV1,
    MediumCatalogIntegrityError,
    MediumCatalogValidationError,
    MediumIdentityKind,
    derive_media_id,
    evaluate_normalized_media,
    resolve_exact_catalog_values,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_evidence_review import MaterialEvidenceReviewRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.medium_catalog import MediumCatalogRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import V2MediumCatalogValidationEvent
from sealai_v2.tests.test_mat_evid_01c_review import _actor


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


class _NoEvidenceEntries:
    def load_snapshot(self, *_args, **_kwargs):
        raise AssertionError("empty catalog cannot request evidence")

    def load_projection(self, *_args, **_kwargs):
        raise AssertionError("empty catalog cannot request evidence")


RULESET_ID = "mrs_" + "8" * 32
MANIFEST_ID = "mef_" + "7" * 32
REVIEW_ID = "mer_" + "6" * 32
MEDIA_ID = derive_media_id(
    "Synthetic PostgreSQL Medium", MediumIdentityKind.DEFINED_MIXTURE
)
CATALOG_ID = "mcf_" + "1" * 32
CREATED_AT = "2026-07-18T16:00:00Z"


def _identity_assertion_ref() -> str:
    return MediumCatalogEntryV1(
        media_id=MEDIA_ID,
        canonical_name="Synthetic PostgreSQL Medium",
        identity_kind=MediumIdentityKind.DEFINED_MIXTURE,
        aliases=("Synthetic PostgreSQL Alias",),
        evidence_review_snapshot_id="mrv_" + "5" * 64,
        evidence_review_content_sha256="4" * 64,
        claim_refs=("mec_" + "3" * 64,),
    ).identity_assertion_ref


def _ruleset_payload() -> str:
    return json.dumps(
        {
            "snapshot_schema_version": 1,
            "canonicalization_version": 1,
            "mat_gov_contract_version": "MAT-GOV-03A.v1",
            "domain_pack_id": "material.test.v1",
            "positive_statement_allowed": False,
            "rules": [
                {
                    "rule_ref": "MR-MEDIUM-IDENTITY-TEST",
                    "material": "TEST-MATERIAL",
                    "medium": MEDIA_ID,
                    "condition": _identity_assertion_ref(),
                    "verdict": "bedingt",
                    "statement": "Synthetic identity-binding test rule.",
                    "scope": {
                        "materials": ["TEST-MATERIAL"],
                        "media": [MEDIA_ID],
                        "conditions": [_identity_assertion_ref()],
                    },
                    "evidence_binding": {"state": "unbound"},
                }
            ],
        }
    )


def _evidence_payload(ruleset_snapshot_id: str) -> tuple[str, str, str]:
    source = {
        "document_id": "DOC-MEDIUM-ID-TEST",
        "document_revision": "rev-1",
        "publication_edition": "edition-test",
        "content_sha256": "4" * 64,
    }
    source_ref = derive_source_ref(**source)
    scope = EvidenceClaimScopeV1(
        materials=("TEST-MATERIAL",),
        media=(MEDIA_ID,),
        conditions=(_identity_assertion_ref(),),
    )
    claim_text = "Synthetic reviewed medium identity assertion."
    claim_ref = derive_claim_ref(claim_text=claim_text, scope=scope)
    return (
        json.dumps(
            {
                "evidence_manifest_schema_version": 1,
                "canonicalization_version": 1,
                "mat_evid_contract_version": "MAT-EVID-01A.v1",
                "ruleset_snapshot_id": ruleset_snapshot_id,
                "domain_pack_id": "material.test.v1",
                "sources": [{"source_ref": source_ref, **source}],
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
                        "rule_ref": "MR-MEDIUM-IDENTITY-TEST",
                        "claim_ref": claim_ref,
                    }
                ],
            }
        ),
        source_ref,
        claim_ref,
    )


def _review_payload(evidence, source_ref: str, claim_ref: str) -> str:
    return json.dumps(
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
                    "document_id": "DOC-MEDIUM-ID-TEST",
                    "document_title": "Synthetic medium identity source",
                    "publisher": "Synthetic Test Publisher",
                    "document_type": "manufacturer_datasheet",
                    "document_revision": "rev-1",
                    "publication_edition": "edition-test",
                    "content_sha256": "4" * 64,
                    "locator": {"state": "exact", "value": "test locator"},
                    "rights_state": "permitted",
                    "rights_basis": "Synthetic test permission",
                    "excerpt": {"state": "omitted"},
                }
            ],
            "claims": [
                {
                    "claim_ref": claim_ref,
                    "claim_type": "other_technical",
                    "scope": {
                        "materials": ["TEST-MATERIAL"],
                        "media": [MEDIA_ID],
                        "conditions": [_identity_assertion_ref()],
                    },
                    "required_source_types": ["manufacturer_datasheet"],
                }
            ],
            "claim_relations": [],
        }
    )


def test_real_postgres_catalog_fingerprint_fk_and_immutability() -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_med_norm_01_test")
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0018", "20260718_0018")
    factory = make_sessionmaker(engine)
    repository = MediumCatalogRepository(factory, _NoEvidenceEntries())
    identity = VerifiedIdentity("tenant-a", "session-a", "subject-a")
    family = repository.create_catalog(
        catalog_id="mcf_" + "1" * 32,
        identity=identity,
        domain_pack_id="material.test.v1",
        created_at="2026-07-18T16:00:00Z",
    )
    snapshot = repository.store_snapshot(
        catalog_id=family.catalog_id,
        raw_payload=json.dumps(
            {
                "media_catalog_schema_version": 1,
                "canonicalization_version": 1,
                "med_norm_contract_version": "MED-NORM-01.v1",
                "domain_pack_id": "material.test.v1",
                "entries": [],
            }
        ),
        identity=identity,
        created_at="2026-07-18T16:00:00Z",
    )
    assert repository.load_snapshot(snapshot.snapshot_id, identity=identity) == snapshot

    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    evidence_repository = MaterialEvidenceRepository(factory)
    evidence_repository.create_manifest(
        manifest_id=MANIFEST_ID,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    raw_evidence, source_ref, claim_ref = _evidence_payload(ruleset.snapshot_id)
    evidence = evidence_repository.store_snapshot(
        manifest_id=MANIFEST_ID,
        raw_payload=raw_evidence,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    reviews = MaterialEvidenceReviewRepository(factory)
    reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=evidence.snapshot_id,
        identity=_actor("subject:creator", CREATE_ROLE),
        created_at=CREATED_AT,
    )
    review = reviews.store_snapshot(
        review_id=REVIEW_ID,
        raw_payload=_review_payload(evidence, source_ref, claim_ref),
        identity=_actor("subject:creator", CREATE_ROLE),
        created_at=CREATED_AT,
    )
    reviews.record_review(
        review.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T16:01:00Z",
    )
    reviews.record_approval(
        review.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T16:02:00Z",
    )
    repository = MediumCatalogRepository(factory, reviews)
    reviewed_entry = {
        "media_id": MEDIA_ID,
        "canonical_name": "Synthetic PostgreSQL Medium",
        "identity_kind": "defined_mixture",
        "aliases": ["Synthetic PostgreSQL Alias"],
        "evidence_review_snapshot_id": review.review_snapshot_id,
        "evidence_review_content_sha256": review.content_sha256,
        "claim_refs": [claim_ref],
    }
    reviewed_catalog = repository.store_snapshot(
        catalog_id=family.catalog_id,
        raw_payload=json.dumps(
            {
                "media_catalog_schema_version": 1,
                "canonicalization_version": 1,
                "med_norm_contract_version": "MED-NORM-01.v1",
                "domain_pack_id": "material.test.v1",
                "entries": [reviewed_entry],
            }
        ),
        identity=identity,
        created_at="2026-07-18T16:03:00Z",
    )
    assert (
        repository.load_snapshot(reviewed_catalog.snapshot_id, identity=identity)
        == reviewed_catalog
    )
    normalized = resolve_exact_catalog_values(
        ("Synthetic PostgreSQL Medium",),
        snapshot=reviewed_catalog,
        identity=identity,
    )
    reviews.record_revocation(
        review.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T16:04:00Z",
    )
    with pytest.raises(MediumCatalogIntegrityError, match="strict revalidation"):
        repository.load_snapshot(reviewed_catalog.snapshot_id, identity=identity)
    with pytest.raises(MediumCatalogValidationError, match="approved factual evidence"):
        resolve_exact_catalog_values(
            ("Synthetic PostgreSQL Medium",),
            snapshot=reviewed_catalog,
            identity=identity,
        )

    def forbidden_evaluator(_component):
        raise AssertionError("revoked normalized input reached evaluator")

    with pytest.raises(MediumCatalogValidationError, match="approved factual evidence"):
        evaluate_normalized_media(
            normalized,
            evaluate_component=forbidden_evaluator,
        )

    with pytest.raises(IntegrityError):
        with factory() as session, session.begin():
            session.add(
                V2MediumCatalogValidationEvent(
                    event_id="mcv_" + "2" * 32,
                    snapshot_id="mcs_" + "3" * 64,
                    validator_contract_version="MED-NORM-01.v1",
                    validation_state="valid",
                    error_code="none",
                    validation_sha256="4" * 64,
                    created_at="2026-07-18T16:00:00Z",
                )
            )

    for statement in (
        "UPDATE v2_medium_catalog_snapshots SET created_at=created_at "
        "WHERE snapshot_id=:snapshot_id",
        "DELETE FROM v2_medium_catalog_audit_events WHERE snapshot_id=:snapshot_id",
    ):
        with pytest.raises(DBAPIError, match="MED-NORM-01 immutable table"):
            with engine.begin() as connection:
                connection.execute(
                    text(statement), {"snapshot_id": snapshot.snapshot_id}
                )

    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0016")
    assert migration_status(engine)[0] == "20260718_0018"
