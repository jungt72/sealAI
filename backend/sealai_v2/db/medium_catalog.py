"""Create/read-only persistence for the inert MED-NORM-01 media catalog.

Every entry is checked against an exact, approved MAT-EVID-01C review snapshot
within the verified tenant.  Persistence exposes no update, delete, active
pointer, review, activation, seed, backfill, or public API surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence_review import (
    EvidenceClaimType,
    FactualApprovalState,
)
from sealai_v2.core.medium_catalog import (
    EvidenceVerifiedMediumCatalogSnapshotV1,
    MED_NORM_CONTRACT_VERSION,
    MediumCatalogErrorCode,
    MediumCatalogIntegrityError,
    MediumCatalogSnapshotV1,
    MediumCatalogValidationError,
    _bind_evidence_verified_medium_catalog,
    compute_audit_sha256,
    compute_validation_sha256,
    parse_catalog_payload,
)
from sealai_v2.db.material_evidence_review import MaterialEvidenceReviewRepository
from sealai_v2.db.models import (
    V2MediumCatalog,
    V2MediumCatalogAuditEvent,
    V2MediumCatalogSnapshot,
    V2MediumCatalogValidationEvent,
)


NORMALIZATION_ONLY_AUTHORITY = "NORMALIZATION_ONLY"


@dataclass(frozen=True, slots=True)
class MediumCatalogFamily:
    catalog_id: str
    tenant_id: str
    domain_pack_id: str
    created_by_subject: str
    created_at: str


def _identity(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _metadata(value: str, *, field: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        raise ValueError(f"{field} must be a non-whitespace string")
    return value


class MediumCatalogRepository:
    def __init__(
        self,
        session_factory: sessionmaker,
        evidence_review_repository: MaterialEvidenceReviewRepository,
    ) -> None:
        self._session_factory = session_factory
        self._reviews = evidence_review_repository

    def create_catalog(
        self,
        *,
        identity: VerifiedIdentity,
        domain_pack_id: str,
        created_at: str,
        catalog_id: str | None = None,
    ) -> MediumCatalogFamily:
        self._require_identity(identity)
        timestamp = _metadata(created_at, field="created_at")
        identifier = _identity("mcf") if catalog_id is None else catalog_id
        # The domain constructor provides the single ID grammar boundary.
        empty_payload = json.dumps(
            {
                "canonicalization_version": 1,
                "domain_pack_id": domain_pack_id,
                "entries": [],
                "med_norm_contract_version": MED_NORM_CONTRACT_VERSION,
                "media_catalog_schema_version": 1,
            }
        )
        snapshot = MediumCatalogSnapshotV1.from_json(identifier, empty_payload)
        with self._session_factory() as session, session.begin():
            if session.get(V2MediumCatalog, identifier) is not None:
                raise ValueError("catalog_id already exists")
            session.add(
                V2MediumCatalog(
                    catalog_id=identifier,
                    tenant_id=identity.tenant_id,
                    domain_pack_id=snapshot.payload.domain_pack_id,
                    created_by_subject=identity.subject,
                    created_at=timestamp,
                )
            )
        return MediumCatalogFamily(
            identifier,
            identity.tenant_id,
            snapshot.payload.domain_pack_id,
            identity.subject,
            timestamp,
        )

    def store_snapshot(
        self,
        *,
        catalog_id: str,
        raw_payload: str | bytes,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceVerifiedMediumCatalogSnapshotV1:
        self._require_identity(identity)
        timestamp = _metadata(created_at, field="created_at")
        snapshot = MediumCatalogSnapshotV1.from_json(catalog_id, raw_payload)
        self._validate_evidence(snapshot, identity=identity)
        with self._session_factory() as session, session.begin():
            family = session.get(V2MediumCatalog, catalog_id)
            if family is None:
                raise KeyError(catalog_id)
            self._require_tenant(family, identity)
            if family.domain_pack_id != snapshot.payload.domain_pack_id:
                raise MediumCatalogValidationError(
                    MediumCatalogErrorCode.INVALID_ID,
                    "catalog domain pack differs from family",
                    path="$.domain_pack_id",
                )
            existing = session.get(V2MediumCatalogSnapshot, snapshot.snapshot_id)
            if existing is not None:
                return self._validated_snapshot(
                    existing, family=family, identity=identity
                )
            session.add(
                V2MediumCatalogSnapshot(
                    snapshot_id=snapshot.snapshot_id,
                    catalog_id=catalog_id,
                    media_catalog_schema_version=(
                        snapshot.payload.media_catalog_schema_version
                    ),
                    canonicalization_version=snapshot.payload.canonicalization_version,
                    med_norm_contract_version=snapshot.payload.med_norm_contract_version,
                    content_sha256=snapshot.content_sha256,
                    canonical_payload_json=snapshot.payload.to_dict(),
                    canonical_bytes=snapshot.canonical_bytes,
                    runtime_authority=NORMALIZATION_ONLY_AUTHORITY,
                    positive_statement_allowed=False,
                    created_by_subject=identity.subject,
                    created_at=timestamp,
                )
            )
            session.flush()
            session.add(
                V2MediumCatalogValidationEvent(
                    event_id=_identity("mcv"),
                    snapshot_id=snapshot.snapshot_id,
                    validator_contract_version=MED_NORM_CONTRACT_VERSION,
                    validation_state="valid",
                    error_code="none",
                    validation_sha256=compute_validation_sha256(snapshot),
                    created_at=timestamp,
                )
            )
            audit_payload = {
                "catalog_id": catalog_id,
                "content_sha256": snapshot.content_sha256,
                "runtime_authority": NORMALIZATION_ONLY_AUTHORITY,
                "snapshot_id": snapshot.snapshot_id,
            }
            session.add(
                V2MediumCatalogAuditEvent(
                    event_id=_identity("mca"),
                    snapshot_id=snapshot.snapshot_id,
                    event_type="catalog_snapshot_created",
                    actor_subject=identity.subject,
                    event_payload_json=audit_payload,
                    event_sha256=compute_audit_sha256(audit_payload),
                    created_at=timestamp,
                )
            )
        return _bind_evidence_verified_medium_catalog(
            snapshot,
            tenant_id=identity.tenant_id,
            revalidate=lambda: self._validate_evidence(snapshot, identity=identity),
        )

    def load_snapshot(
        self, snapshot_id: str, *, identity: VerifiedIdentity
    ) -> EvidenceVerifiedMediumCatalogSnapshotV1:
        self._require_identity(identity)
        with self._session_factory() as session:
            row = session.get(V2MediumCatalogSnapshot, snapshot_id)
            if row is None:
                raise KeyError(snapshot_id)
            family = session.get(V2MediumCatalog, row.catalog_id)
            if family is None:
                raise MediumCatalogIntegrityError(
                    MediumCatalogErrorCode.DB_INTEGRITY,
                    "catalog snapshot references a missing family",
                )
            self._require_tenant(family, identity)
            return self._validated_snapshot(row, family=family, identity=identity)

    def _validated_snapshot(
        self, row, *, family, identity
    ) -> EvidenceVerifiedMediumCatalogSnapshotV1:
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_catalog_payload(canonical_bytes)
            rebuilt = MediumCatalogSnapshotV1.from_json(
                family.catalog_id, canonical_bytes
            )
            if (
                rebuilt.payload != payload
                or rebuilt.snapshot_id != row.snapshot_id
                or rebuilt.content_sha256 != row.content_sha256
                or rebuilt.canonical_bytes != canonical_bytes
                or row.canonical_payload_json != payload.to_dict()
                or row.media_catalog_schema_version
                != payload.media_catalog_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.med_norm_contract_version != payload.med_norm_contract_version
                or row.runtime_authority != NORMALIZATION_ONLY_AUTHORITY
                or row.positive_statement_allowed is not False
                or family.domain_pack_id != payload.domain_pack_id
                or not row.created_by_subject
            ):
                raise MediumCatalogIntegrityError(
                    MediumCatalogErrorCode.DB_INTEGRITY,
                    "catalog identity, payload, or authority drifted",
                )
            with self._session_factory() as session:
                validations = session.scalars(
                    select(V2MediumCatalogValidationEvent).where(
                        V2MediumCatalogValidationEvent.snapshot_id == row.snapshot_id
                    )
                ).all()
                audits = session.scalars(
                    select(V2MediumCatalogAuditEvent).where(
                        V2MediumCatalogAuditEvent.snapshot_id == row.snapshot_id
                    )
                ).all()
            if len(validations) != 1 or len(audits) != 1:
                raise MediumCatalogIntegrityError(
                    MediumCatalogErrorCode.DB_INTEGRITY,
                    "catalog requires one validation and one creation audit",
                )
            validation = validations[0]
            if (
                validation.validator_contract_version != MED_NORM_CONTRACT_VERSION
                or validation.validation_state != "valid"
                or validation.error_code != "none"
                or validation.validation_sha256 != compute_validation_sha256(rebuilt)
            ):
                raise MediumCatalogIntegrityError(
                    MediumCatalogErrorCode.DB_INTEGRITY,
                    "catalog validation event drifted",
                )
            audit_payload = {
                "catalog_id": family.catalog_id,
                "content_sha256": rebuilt.content_sha256,
                "runtime_authority": NORMALIZATION_ONLY_AUTHORITY,
                "snapshot_id": rebuilt.snapshot_id,
            }
            audit = audits[0]
            if (
                audit.event_type != "catalog_snapshot_created"
                or audit.actor_subject != row.created_by_subject
                or audit.event_payload_json != audit_payload
                or audit.event_sha256 != compute_audit_sha256(audit_payload)
            ):
                raise MediumCatalogIntegrityError(
                    MediumCatalogErrorCode.DB_INTEGRITY,
                    "catalog creation audit drifted",
                )
            self._validate_evidence(rebuilt, identity=identity)
            return _bind_evidence_verified_medium_catalog(
                rebuilt,
                tenant_id=identity.tenant_id,
                revalidate=lambda: self._validate_evidence(rebuilt, identity=identity),
            )
        except MediumCatalogIntegrityError:
            raise
        except Exception as exc:
            raise MediumCatalogIntegrityError(
                MediumCatalogErrorCode.DB_INTEGRITY,
                "persisted catalog failed strict revalidation",
            ) from exc

    def _validate_evidence(
        self, snapshot: MediumCatalogSnapshotV1, *, identity: VerifiedIdentity
    ) -> None:
        for entry in snapshot.payload.entries:
            review = self._reviews.load_snapshot(
                entry.evidence_review_snapshot_id, identity=identity
            )
            projection = self._reviews.load_projection(
                entry.evidence_review_snapshot_id, identity=identity
            )
            review_claims = {claim.claim_ref: claim for claim in review.payload.claims}
            selected_claims = [
                review_claims.get(claim_ref) for claim_ref in entry.claim_refs
            ]
            if (
                review.content_sha256 != entry.evidence_review_content_sha256
                or any(claim is None for claim in selected_claims)
                or any(
                    claim.claim_type is not EvidenceClaimType.OTHER_TECHNICAL
                    or claim.scope.media != (entry.media_id,)
                    or claim.scope.conditions != (entry.identity_assertion_ref,)
                    for claim in selected_claims
                    if claim is not None
                )
                or projection.approval_state is not FactualApprovalState.APPROVED
            ):
                raise MediumCatalogValidationError(
                    MediumCatalogErrorCode.DANGLING_REF,
                    "catalog entry lacks exact approved factual evidence",
                    path=f"$.entries[{entry.media_id}]",
                )

    @staticmethod
    def _require_identity(identity: VerifiedIdentity) -> None:
        if type(identity) is not VerifiedIdentity:
            raise TypeError("identity must be VerifiedIdentity")

    @staticmethod
    def _require_tenant(family, identity: VerifiedIdentity) -> None:
        if family.tenant_id != identity.tenant_id:
            raise MediumCatalogValidationError(
                MediumCatalogErrorCode.INVALID_ID,
                "catalog belongs to another verified tenant",
                path="$.tenant_id",
            )


__all__ = [
    "NORMALIZATION_ONLY_AUTHORITY",
    "MediumCatalogFamily",
    "MediumCatalogRepository",
]
