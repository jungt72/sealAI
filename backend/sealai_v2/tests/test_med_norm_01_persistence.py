from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence_review import (
    EvidenceClaimType,
    EvidenceDocumentType,
    FactualApprovalState,
    ReviewedClaimMetadataV1,
)
from sealai_v2.core.material_evidence_review_v2 import ReviewedClaimMetadataV2
from sealai_v2.core.material_evidence import EvidenceClaimScopeV1
from sealai_v2.core.material_evidence_v2 import MediaIdentityClaimScopeV2
from sealai_v2.core.medium_catalog import (
    MediumCatalogEntryV1,
    MediumIdentityKind,
    MediumCatalogIntegrityError,
    MediumCatalogValidationError,
    derive_media_id,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.medium_catalog import MediumCatalogRepository
from sealai_v2.db.migrate import _upgrade_engine
from sealai_v2.db.models import (
    V2MediumCatalog,
    V2MediumCatalogAuditEvent,
    V2MediumCatalogSnapshot,
    V2MediumCatalogValidationEvent,
)


CATALOG_ID = "mcf_" + "1" * 32
REVIEW_ID = "mrv_" + "2" * 64
CLAIM_REF = "mec_" + "3" * 64
REVIEW_ID_V2 = "mrv_" + "4" * 64
CLAIM_REF_V2 = "mec_" + "6" * 64
MEDIA_ID = derive_media_id(
    "Synthetic Catalog Medium", MediumIdentityKind.DEFINED_MIXTURE
)
MEDIA_ID_V2 = derive_media_id(
    "Synthetic V2 Catalog Medium", MediumIdentityKind.DEFINED_MIXTURE
)
IDENTITY_ASSERTION_REF = MediumCatalogEntryV1(
    media_id=MEDIA_ID,
    canonical_name="Synthetic Catalog Medium",
    identity_kind=MediumIdentityKind.DEFINED_MIXTURE,
    aliases=("Synthetic Catalog Alias",),
    evidence_review_snapshot_id=REVIEW_ID,
    evidence_review_content_sha256="5" * 64,
    claim_refs=(CLAIM_REF,),
).identity_assertion_ref
IDENTITY_ASSERTION_REF_V2 = MediumCatalogEntryV1(
    media_id=MEDIA_ID_V2,
    canonical_name="Synthetic V2 Catalog Medium",
    identity_kind=MediumIdentityKind.DEFINED_MIXTURE,
    aliases=("Synthetic V2 Catalog Alias",),
    evidence_review_snapshot_id=REVIEW_ID_V2,
    evidence_review_content_sha256="7" * 64,
    claim_refs=(CLAIM_REF_V2,),
).identity_assertion_ref
CREATED_AT = "2026-07-18T16:00:00Z"
TABLES = {
    "v2_medium_catalogs",
    "v2_medium_catalog_snapshots",
    "v2_medium_catalog_validation_events",
    "v2_medium_catalog_audit_events",
}


def _identity(tenant: str = "tenant-a") -> VerifiedIdentity:
    return VerifiedIdentity(tenant, f"session-{tenant}", f"subject-{tenant}")


def _payload(*, entries: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "media_catalog_schema_version": 1,
            "canonicalization_version": 1,
            "med_norm_contract_version": "MED-NORM-01.v1",
            "domain_pack_id": "material.test.v1",
            "entries": entries or [],
        }
    )


def _entry() -> dict:
    return {
        "media_id": MEDIA_ID,
        "canonical_name": "Synthetic Catalog Medium",
        "identity_kind": "defined_mixture",
        "aliases": ["Synthetic Catalog Alias"],
        "evidence_review_snapshot_id": REVIEW_ID,
        "evidence_review_content_sha256": "5" * 64,
        "claim_refs": [CLAIM_REF],
    }


class _ReviewRepository:
    def __init__(
        self,
        *,
        approved: bool = True,
        content_hash: str = "5" * 64,
        claim_type: EvidenceClaimType = EvidenceClaimType.OTHER_TECHNICAL,
        media_scope: tuple[str, ...] = (MEDIA_ID,),
        conditions: tuple[str, ...] = (IDENTITY_ASSERTION_REF,),
    ) -> None:
        self.approved = approved
        self.content_hash = content_hash
        self.claim_type = claim_type
        self.media_scope = media_scope
        self.conditions = conditions

    def load_snapshot(self, review_snapshot_id, *, identity):
        if review_snapshot_id != REVIEW_ID:
            raise KeyError(review_snapshot_id)
        assert identity.tenant_id == "tenant-a"
        return SimpleNamespace(
            content_sha256=self.content_hash,
            payload=SimpleNamespace(
                claims=(
                    ReviewedClaimMetadataV1(
                        claim_ref=CLAIM_REF,
                        claim_type=self.claim_type,
                        scope=EvidenceClaimScopeV1(
                            materials=("TEST-MATERIAL",),
                            media=self.media_scope,
                            conditions=self.conditions,
                        ),
                        required_source_types=(
                            EvidenceDocumentType.MANUFACTURER_DATASHEET,
                        ),
                    ),
                )
            ),
        )

    def load_projection(self, review_snapshot_id, *, identity):
        if review_snapshot_id != REVIEW_ID:
            raise KeyError(review_snapshot_id)
        assert identity.tenant_id == "tenant-a"
        return SimpleNamespace(
            approval_state=(
                FactualApprovalState.APPROVED
                if self.approved
                else FactualApprovalState.NOT_APPROVED
            )
        )


class _V2ReviewRepository:
    def load_snapshot(self, review_snapshot_id, *, identity):
        if review_snapshot_id != REVIEW_ID_V2:
            raise KeyError(review_snapshot_id)
        assert identity.tenant_id == "tenant-a"
        return SimpleNamespace(
            content_sha256="7" * 64,
            payload=SimpleNamespace(
                claims=(
                    ReviewedClaimMetadataV2(
                        claim_ref=CLAIM_REF_V2,
                        claim_type=EvidenceClaimType.OTHER_TECHNICAL,
                        scope=MediaIdentityClaimScopeV2(
                            MEDIA_ID_V2, IDENTITY_ASSERTION_REF_V2
                        ),
                        required_source_types=(
                            EvidenceDocumentType.MANUFACTURER_DATASHEET,
                        ),
                    ),
                )
            ),
        )

    def load_projection(self, review_snapshot_id, *, identity):
        if review_snapshot_id != REVIEW_ID_V2:
            raise KeyError(review_snapshot_id)
        assert identity.tenant_id == "tenant-a"
        return SimpleNamespace(approval_state=FactualApprovalState.APPROVED)


def _entry_v2() -> dict:
    return {
        "media_id": MEDIA_ID_V2,
        "canonical_name": "Synthetic V2 Catalog Medium",
        "identity_kind": "defined_mixture",
        "aliases": ["Synthetic V2 Catalog Alias"],
        "evidence_review_snapshot_id": REVIEW_ID_V2,
        "evidence_review_content_sha256": "7" * 64,
        "claim_refs": [CLAIM_REF_V2],
    }


def _repository(tmp_path, *, reviews=None):
    engine = make_engine(f"sqlite:///{tmp_path / 'med-norm.db'}")
    _upgrade_engine(engine, "20260718_0017")
    factory = make_sessionmaker(engine)
    return (
        engine,
        factory,
        MediumCatalogRepository(factory, reviews or _ReviewRepository()),
    )


def test_migration_is_additive_empty_and_repository_roundtrips(tmp_path) -> None:
    engine, factory, repository = _repository(tmp_path)
    assert TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert all(
            connection.exec_driver_sql(f'SELECT COUNT(*) FROM "{table}"').scalar_one()
            == 0
            for table in TABLES
        )

    family = repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    snapshot = repository.store_snapshot(
        catalog_id=family.catalog_id,
        raw_payload=_payload(entries=[_entry()]),
        identity=_identity(),
        created_at=CREATED_AT,
    )
    assert (
        repository.load_snapshot(snapshot.snapshot_id, identity=_identity()) == snapshot
    )
    with factory() as session:
        assert session.scalar(select(V2MediumCatalog)) is not None
        assert session.scalar(select(V2MediumCatalogSnapshot)) is not None
        assert session.scalar(select(V2MediumCatalogValidationEvent)) is not None
        assert session.scalar(select(V2MediumCatalogAuditEvent)) is not None


def test_catalog_routes_mixed_v1_v2_review_provenance_per_entry(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'mixed-review-versions.db'}")
    _upgrade_engine(engine)
    factory = make_sessionmaker(engine)
    repository = MediumCatalogRepository(
        factory,
        _ReviewRepository(),
        evidence_review_repository_v2=_V2ReviewRepository(),
    )
    repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    entries = sorted((_entry(), _entry_v2()), key=lambda item: item["media_id"])
    snapshot = repository.store_snapshot(
        catalog_id=CATALOG_ID,
        raw_payload=_payload(entries=entries),
        identity=_identity(),
        created_at=CREATED_AT,
    )
    assert len(snapshot.payload.entries) == 2
    assert (
        repository.load_snapshot(snapshot.snapshot_id, identity=_identity()) == snapshot
    )


def test_catalog_rejects_ambiguous_cross_version_review_identity(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'ambiguous-review-version.db'}")
    _upgrade_engine(engine)
    factory = make_sessionmaker(engine)
    repository = MediumCatalogRepository(
        factory,
        _ReviewRepository(),
        evidence_review_repository_v2=_ReviewRepository(),
    )
    repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    with pytest.raises(MediumCatalogValidationError, match="exactly one"):
        repository.store_snapshot(
            catalog_id=CATALOG_ID,
            raw_payload=_payload(entries=[_entry()]),
            identity=_identity(),
            created_at=CREATED_AT,
        )


def test_catalog_is_tenant_isolated(tmp_path) -> None:
    _engine, _factory, repository = _repository(tmp_path)
    repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    with pytest.raises(MediumCatalogValidationError):
        repository.store_snapshot(
            catalog_id=CATALOG_ID,
            raw_payload=_payload(),
            identity=_identity("tenant-b"),
            created_at=CREATED_AT,
        )


@pytest.mark.parametrize(
    "reviews",
    (
        _ReviewRepository(approved=False),
        _ReviewRepository(content_hash="6" * 64),
        _ReviewRepository(claim_type=EvidenceClaimType.INCOMPATIBILITY),
        _ReviewRepository(media_scope=("med_" + "9" * 64,)),
        _ReviewRepository(media_scope=(MEDIA_ID, "med_" + "9" * 64)),
        _ReviewRepository(conditions=("med-norm-identity-sha256:" + "0" * 64,)),
    ),
)
def test_inexact_or_unapproved_evidence_cannot_enter_catalog(tmp_path, reviews) -> None:
    _engine, _factory, repository = _repository(tmp_path, reviews=reviews)
    repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    with pytest.raises(MediumCatalogValidationError):
        repository.store_snapshot(
            catalog_id=CATALOG_ID,
            raw_payload=_payload(entries=[_entry()]),
            identity=_identity(),
            created_at=CREATED_AT,
        )


def test_all_catalog_tables_are_immutable(tmp_path) -> None:
    _engine, factory, repository = _repository(tmp_path)
    repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    snapshot = repository.store_snapshot(
        catalog_id=CATALOG_ID,
        raw_payload=_payload(entries=[_entry()]),
        identity=_identity(),
        created_at=CREATED_AT,
    )
    models = (
        (V2MediumCatalog, V2MediumCatalog.catalog_id == CATALOG_ID),
        (
            V2MediumCatalogSnapshot,
            V2MediumCatalogSnapshot.snapshot_id == snapshot.snapshot_id,
        ),
        (
            V2MediumCatalogValidationEvent,
            V2MediumCatalogValidationEvent.snapshot_id == snapshot.snapshot_id,
        ),
        (
            V2MediumCatalogAuditEvent,
            V2MediumCatalogAuditEvent.snapshot_id == snapshot.snapshot_id,
        ),
    )
    for model, predicate in models:
        with factory() as session:
            with pytest.raises(DBAPIError):
                with session.begin():
                    session.execute(
                        update(model).where(predicate).values(created_at="drift")
                    )
        with factory() as session:
            with pytest.raises(DBAPIError):
                with session.begin():
                    session.execute(delete(model).where(predicate))


def test_persisted_payload_drift_fails_closed(tmp_path) -> None:
    _engine, factory, repository = _repository(tmp_path)
    repository.create_catalog(
        identity=_identity(),
        domain_pack_id="material.test.v1",
        created_at=CREATED_AT,
        catalog_id=CATALOG_ID,
    )
    snapshot = repository.store_snapshot(
        catalog_id=CATALOG_ID,
        raw_payload=_payload(entries=[_entry()]),
        identity=_identity(),
        created_at=CREATED_AT,
    )
    # Test-only bypass removes the immutable trigger, then proves read-time
    # canonical revalidation catches storage drift.
    with factory() as session, session.begin():
        session.connection().exec_driver_sql(
            'DROP TRIGGER "trg_v2_medium_catalog_snapshots_update_immutable"'
        )
        session.execute(
            update(V2MediumCatalogSnapshot)
            .where(V2MediumCatalogSnapshot.snapshot_id == snapshot.snapshot_id)
            .values(content_sha256="0" * 64)
        )
    with pytest.raises(MediumCatalogIntegrityError):
        repository.load_snapshot(snapshot.snapshot_id, identity=_identity())
