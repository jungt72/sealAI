"""Tenant-isolated append-only persistence for MAT-EVID-01C.

This repository has no public route, pointer, activation, deployment, seed, or
runtime-binding integration.  Every read revalidates both the 01C dossier and
its exact immutable MAT-EVID-01A dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence_review import (
    APPROVE_ROLE,
    CREATE_ROLE,
    HUMAN_ROLE,
    MAT_EVID_REVIEW_CONTRACT_VERSION,
    NO_RUNTIME_AUTHORITY,
    REVIEW_ROLE,
    EvidenceReviewErrorCode,
    EvidenceReviewIntegrityError,
    EvidenceReviewProjection,
    EvidenceReviewSnapshotV1,
    EvidenceReviewValidationError,
    ReviewEventType,
    canonicalize_review_payload,
    compute_audit_sha256,
    compute_lifecycle_sha256,
    compute_validation_sha256,
    parse_review_payload,
    transition_review_projection,
    validate_review_id,
    validate_review_snapshot_id,
)
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.models import (
    V2MaterialEvidenceReviewAuditEvent,
    V2MaterialEvidenceReviewDossier,
    V2MaterialEvidenceReviewLifecycleEvent,
    V2MaterialEvidenceReviewSnapshot,
    V2MaterialEvidenceReviewValidationEvent,
)


@dataclass(frozen=True, slots=True)
class MaterialEvidenceReviewFamily:
    review_id: str
    tenant_id: str
    evidence_snapshot_id: str
    creator_subject: str
    created_at: str


def _identity(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _metadata(value: str, *, field: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        raise ValueError(f"{field} must be a non-whitespace string")
    return value


def _require_actor(identity: VerifiedIdentity, role: str) -> VerifiedIdentity:
    if type(identity) is not VerifiedIdentity:
        raise EvidenceReviewValidationError(
            EvidenceReviewErrorCode.ROLE_REQUIRED,
            "actor must be an exact VerifiedIdentity",
        )
    _metadata(identity.tenant_id, field="tenant_id")
    _metadata(identity.subject, field="subject")
    if (
        type(identity.roles) is not tuple
        or HUMAN_ROLE not in identity.roles
        or role not in identity.roles
    ):
        raise EvidenceReviewValidationError(
            EvidenceReviewErrorCode.ROLE_REQUIRED,
            f"verified human role and {role} are required",
        )
    return identity


class MaterialEvidenceReviewRepository:
    """Immutable dossier storage plus an append-only human lifecycle stream."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._evidence = MaterialEvidenceRepository(session_factory)

    def create_review(
        self,
        *,
        evidence_snapshot_id: str,
        identity: VerifiedIdentity,
        created_at: str,
        review_id: str | None = None,
    ) -> MaterialEvidenceReviewFamily:
        actor = _require_actor(identity, CREATE_ROLE)
        timestamp = _metadata(created_at, field="created_at")
        identifier = review_id or _identity("mer")
        validate_review_id(identifier)
        evidence = self._evidence.load_snapshot(evidence_snapshot_id)
        with self._session_factory() as session, session.begin():
            if session.get(V2MaterialEvidenceReviewDossier, identifier) is not None:
                raise ValueError("review_id already exists")
            session.add(
                V2MaterialEvidenceReviewDossier(
                    review_id=identifier,
                    tenant_id=actor.tenant_id,
                    evidence_snapshot_id=evidence.snapshot_id,
                    creator_subject=actor.subject,
                    creator_identity_kind="verified_human",
                    created_at=timestamp,
                )
            )
        return MaterialEvidenceReviewFamily(
            review_id=identifier,
            tenant_id=actor.tenant_id,
            evidence_snapshot_id=evidence.snapshot_id,
            creator_subject=actor.subject,
            created_at=timestamp,
        )

    def store_snapshot(
        self,
        *,
        review_id: str,
        raw_payload: str | bytes,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceReviewSnapshotV1:
        validate_review_id(review_id)
        actor = _require_actor(identity, CREATE_ROLE)
        timestamp = _metadata(created_at, field="created_at")
        snapshot = EvidenceReviewSnapshotV1.from_json(review_id, raw_payload)
        with self._session_factory() as session, session.begin():
            family = self._family_for_actor(session, review_id, actor)
            if family.creator_subject != actor.subject:
                raise EvidenceReviewValidationError(
                    EvidenceReviewErrorCode.ROLE_REQUIRED,
                    "only the verified dossier creator may store its snapshot",
                )
            evidence = self._evidence.load_snapshot(family.evidence_snapshot_id)
            snapshot.payload.validate_against_evidence(evidence)
            existing = session.get(
                V2MaterialEvidenceReviewSnapshot, snapshot.review_snapshot_id
            )
            if existing is not None:
                return self._validated_snapshot(
                    existing, family=family, session=session
                )
            session.add(
                V2MaterialEvidenceReviewSnapshot(
                    review_snapshot_id=snapshot.review_snapshot_id,
                    review_id=review_id,
                    evidence_snapshot_id=snapshot.payload.evidence_snapshot_id,
                    evidence_content_sha256=snapshot.payload.evidence_content_sha256,
                    evidence_manifest_schema_version=(
                        snapshot.payload.evidence_manifest_schema_version
                    ),
                    evidence_contract_version=(
                        snapshot.payload.evidence_contract_version
                    ),
                    review_schema_version=snapshot.payload.review_schema_version,
                    canonicalization_version=(
                        snapshot.payload.canonicalization_version
                    ),
                    mat_evid_review_contract_version=(
                        snapshot.payload.mat_evid_review_contract_version
                    ),
                    content_sha256=snapshot.content_sha256,
                    canonical_payload_json=snapshot.payload.to_dict(),
                    canonical_bytes=snapshot.canonical_bytes,
                    runtime_authority=NO_RUNTIME_AUTHORITY,
                    positive_statement_allowed=False,
                    created_by_subject=actor.subject,
                    created_at=timestamp,
                )
            )
            session.flush()
            session.add(
                V2MaterialEvidenceReviewValidationEvent(
                    event_id=_identity("mvv"),
                    review_snapshot_id=snapshot.review_snapshot_id,
                    validator_contract_version=MAT_EVID_REVIEW_CONTRACT_VERSION,
                    validation_state="valid",
                    error_code="none",
                    validation_sha256=compute_validation_sha256(snapshot),
                    created_at=timestamp,
                )
            )
            audit_payload = {
                "content_sha256": snapshot.content_sha256,
                "evidence_snapshot_id": snapshot.payload.evidence_snapshot_id,
                "review_snapshot_id": snapshot.review_snapshot_id,
                "runtime_authority": NO_RUNTIME_AUTHORITY,
            }
            session.add(
                V2MaterialEvidenceReviewAuditEvent(
                    event_id=_identity("mra"),
                    review_snapshot_id=snapshot.review_snapshot_id,
                    event_type="review_snapshot_created",
                    actor_tenant_id=actor.tenant_id,
                    actor_subject=actor.subject,
                    event_payload_json=audit_payload,
                    event_sha256=compute_audit_sha256(audit_payload),
                    created_at=timestamp,
                )
            )
        return snapshot

    def load_snapshot(
        self, review_snapshot_id: str, *, identity: VerifiedIdentity
    ) -> EvidenceReviewSnapshotV1:
        validate_review_snapshot_id(review_snapshot_id)
        if type(identity) is not VerifiedIdentity:
            raise EvidenceReviewValidationError(
                EvidenceReviewErrorCode.ROLE_REQUIRED,
                "identity must be verified",
            )
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceReviewSnapshot, review_snapshot_id)
            if row is None:
                raise KeyError(review_snapshot_id)
            family = session.get(V2MaterialEvidenceReviewDossier, row.review_id)
            if family is None:
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review snapshot references a missing dossier",
                )
            self._require_tenant(family, identity)
            return self._validated_snapshot(row, family=family, session=session)

    def record_review(
        self,
        review_snapshot_id: str,
        *,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceReviewProjection:
        return self._append_event(
            review_snapshot_id,
            event_type=ReviewEventType.REVIEWED,
            identity=identity,
            required_role=REVIEW_ROLE,
            created_at=created_at,
        )

    def record_rejection(
        self,
        review_snapshot_id: str,
        *,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceReviewProjection:
        return self._append_event(
            review_snapshot_id,
            event_type=ReviewEventType.REJECTED,
            identity=identity,
            required_role=REVIEW_ROLE,
            created_at=created_at,
        )

    def record_approval(
        self,
        review_snapshot_id: str,
        *,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceReviewProjection:
        return self._append_event(
            review_snapshot_id,
            event_type=ReviewEventType.APPROVED,
            identity=identity,
            required_role=APPROVE_ROLE,
            created_at=created_at,
        )

    def record_revocation(
        self,
        review_snapshot_id: str,
        *,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceReviewProjection:
        return self._append_event(
            review_snapshot_id,
            event_type=ReviewEventType.REVOKED,
            identity=identity,
            required_role=APPROVE_ROLE,
            created_at=created_at,
        )

    def record_quarantine(
        self,
        review_snapshot_id: str,
        *,
        identity: VerifiedIdentity,
        created_at: str,
    ) -> EvidenceReviewProjection:
        return self._append_event(
            review_snapshot_id,
            event_type=ReviewEventType.QUARANTINED,
            identity=identity,
            required_role=APPROVE_ROLE,
            created_at=created_at,
        )

    def load_projection(
        self, review_snapshot_id: str, *, identity: VerifiedIdentity
    ) -> EvidenceReviewProjection:
        validate_review_snapshot_id(review_snapshot_id)
        if type(identity) is not VerifiedIdentity:
            raise EvidenceReviewValidationError(
                EvidenceReviewErrorCode.ROLE_REQUIRED,
                "identity must be verified",
            )
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceReviewSnapshot, review_snapshot_id)
            if row is None:
                raise KeyError(review_snapshot_id)
            family = session.get(V2MaterialEvidenceReviewDossier, row.review_id)
            if family is None:
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "missing review dossier",
                )
            self._require_tenant(family, identity)
            self._validated_snapshot(row, family=family, session=session)
            return self._replay(session, row, family)

    def _append_event(
        self,
        review_snapshot_id: str,
        *,
        event_type: ReviewEventType,
        identity: VerifiedIdentity,
        required_role: str,
        created_at: str,
    ) -> EvidenceReviewProjection:
        validate_review_snapshot_id(review_snapshot_id)
        actor = _require_actor(identity, required_role)
        timestamp = _metadata(created_at, field="created_at")
        with self._session_factory() as session, session.begin():
            row = session.get(
                V2MaterialEvidenceReviewSnapshot,
                review_snapshot_id,
                with_for_update=True,
            )
            if row is None:
                raise KeyError(review_snapshot_id)
            family = session.get(V2MaterialEvidenceReviewDossier, row.review_id)
            if family is None:
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "missing review dossier",
                )
            self._require_tenant(family, actor)
            snapshot = self._validated_snapshot(row, family=family, session=session)
            projection = self._replay(session, row, family)
            next_projection = transition_review_projection(
                projection,
                event_type=event_type,
                actor_subject=actor.subject,
                creator_subject=family.creator_subject,
            )
            if event_type is ReviewEventType.APPROVED:
                evidence = self._evidence.load_snapshot(family.evidence_snapshot_id)
                snapshot.payload.validate_for_approval(evidence)
            sequence = projection.last_sequence + 1
            event_payload = {
                "actor_identity_kind": "verified_human",
                "actor_role": required_role,
                "actor_subject": actor.subject,
                "actor_tenant_id": actor.tenant_id,
                "approval_state": next_projection.approval_state.value,
                "created_at": timestamp,
                "event_type": event_type.value,
                "previous_event_sha256": projection.last_event_sha256,
                "review_snapshot_id": review_snapshot_id,
                "review_state": next_projection.review_state.value,
                "sequence_no": sequence,
            }
            event_hash = compute_lifecycle_sha256(event_payload)
            session.add(
                V2MaterialEvidenceReviewLifecycleEvent(
                    event_id=_identity("mrl"),
                    review_snapshot_id=review_snapshot_id,
                    sequence_no=sequence,
                    event_type=event_type.value,
                    review_state=next_projection.review_state.value,
                    approval_state=next_projection.approval_state.value,
                    actor_tenant_id=actor.tenant_id,
                    actor_subject=actor.subject,
                    actor_role=required_role,
                    actor_identity_kind="verified_human",
                    previous_event_sha256=projection.last_event_sha256,
                    event_sha256=event_hash,
                    created_at=timestamp,
                )
            )
        return EvidenceReviewProjection(
            review_state=next_projection.review_state,
            approval_state=next_projection.approval_state,
            reviewer_subject=next_projection.reviewer_subject,
            approver_subject=next_projection.approver_subject,
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )

    def _validated_snapshot(
        self,
        row: V2MaterialEvidenceReviewSnapshot,
        *,
        family: V2MaterialEvidenceReviewDossier,
        session,
    ) -> EvidenceReviewSnapshotV1:
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_review_payload(canonical_bytes)
            if canonicalize_review_payload(payload) != canonical_bytes:
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review bytes are not canonical",
                )
            if row.canonical_payload_json != payload.to_dict():
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review JSON projection differs from canonical bytes",
                )
            snapshot = EvidenceReviewSnapshotV1(
                review_id=row.review_id,
                review_snapshot_id=row.review_snapshot_id,
                content_sha256=row.content_sha256,
                canonical_bytes=canonical_bytes,
                payload=payload,
            )
            evidence = self._evidence.load_snapshot(family.evidence_snapshot_id)
            snapshot.payload.validate_against_evidence(evidence)
            if (
                row.evidence_snapshot_id != family.evidence_snapshot_id
                or row.evidence_snapshot_id != payload.evidence_snapshot_id
                or row.evidence_content_sha256 != payload.evidence_content_sha256
                or row.evidence_manifest_schema_version
                != payload.evidence_manifest_schema_version
                or row.evidence_contract_version != payload.evidence_contract_version
                or row.review_schema_version != payload.review_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.mat_evid_review_contract_version
                != payload.mat_evid_review_contract_version
                or row.runtime_authority != NO_RUNTIME_AUTHORITY
                or row.positive_statement_allowed is not False
                or row.created_by_subject != family.creator_subject
            ):
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review identity or authority columns drifted",
                )
            validation_events = session.scalars(
                select(V2MaterialEvidenceReviewValidationEvent).where(
                    V2MaterialEvidenceReviewValidationEvent.review_snapshot_id
                    == row.review_snapshot_id
                )
            ).all()
            audit_events = session.scalars(
                select(V2MaterialEvidenceReviewAuditEvent).where(
                    V2MaterialEvidenceReviewAuditEvent.review_snapshot_id
                    == row.review_snapshot_id
                )
            ).all()
            if len(validation_events) != 1 or len(audit_events) != 1:
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review requires exactly one validation and creation audit event",
                )
            validation = validation_events[0]
            if (
                validation.validator_contract_version
                != MAT_EVID_REVIEW_CONTRACT_VERSION
                or validation.validation_state != "valid"
                or validation.error_code != "none"
                or validation.validation_sha256 != compute_validation_sha256(snapshot)
            ):
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review validation event drifted",
                )
            audit = audit_events[0]
            audit_payload = {
                "content_sha256": snapshot.content_sha256,
                "evidence_snapshot_id": snapshot.payload.evidence_snapshot_id,
                "review_snapshot_id": snapshot.review_snapshot_id,
                "runtime_authority": NO_RUNTIME_AUTHORITY,
            }
            if (
                audit.event_type != "review_snapshot_created"
                or audit.actor_tenant_id != family.tenant_id
                or audit.actor_subject != family.creator_subject
                or audit.event_payload_json != audit_payload
                or audit.event_sha256 != compute_audit_sha256(audit_payload)
            ):
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review creation audit event drifted",
                )
            return snapshot
        except EvidenceReviewIntegrityError:
            raise
        except Exception as exc:
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.DB_INTEGRITY,
                "persisted review failed strict revalidation",
            ) from exc

    @staticmethod
    def _family_for_actor(session, review_id: str, actor: VerifiedIdentity):
        family = session.get(V2MaterialEvidenceReviewDossier, review_id)
        if family is None:
            raise KeyError(review_id)
        MaterialEvidenceReviewRepository._require_tenant(family, actor)
        if family.creator_identity_kind != "verified_human":
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.DB_INTEGRITY,
                "creator identity kind is not verified human",
            )
        return family

    @staticmethod
    def _require_tenant(
        family: V2MaterialEvidenceReviewDossier, identity: VerifiedIdentity
    ) -> None:
        if family.tenant_id != identity.tenant_id:
            raise EvidenceReviewValidationError(
                EvidenceReviewErrorCode.TENANT_MISMATCH,
                "review dossier belongs to another verified tenant",
            )

    @staticmethod
    def _replay(session, row, family) -> EvidenceReviewProjection:
        events = session.scalars(
            select(V2MaterialEvidenceReviewLifecycleEvent)
            .where(
                V2MaterialEvidenceReviewLifecycleEvent.review_snapshot_id
                == row.review_snapshot_id
            )
            .order_by(V2MaterialEvidenceReviewLifecycleEvent.sequence_no)
        ).all()
        projection = EvidenceReviewProjection()
        for expected_sequence, event in enumerate(events, start=1):
            if (
                event.sequence_no != expected_sequence
                or event.previous_event_sha256 != projection.last_event_sha256
                or event.actor_tenant_id != family.tenant_id
                or event.actor_identity_kind != "verified_human"
            ):
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "review lifecycle sequence, tenant, or identity drift",
                )
            try:
                event_type = ReviewEventType(event.event_type)
                required_role = (
                    REVIEW_ROLE
                    if event_type
                    in {ReviewEventType.REVIEWED, ReviewEventType.REJECTED}
                    else APPROVE_ROLE
                )
                if event.actor_role != required_role:
                    raise EvidenceReviewIntegrityError(
                        EvidenceReviewErrorCode.DB_INTEGRITY,
                        "lifecycle actor role drift",
                    )
                next_projection = transition_review_projection(
                    projection,
                    event_type=event_type,
                    actor_subject=event.actor_subject,
                    creator_subject=family.creator_subject,
                )
                payload = {
                    "actor_identity_kind": event.actor_identity_kind,
                    "actor_role": event.actor_role,
                    "actor_subject": event.actor_subject,
                    "actor_tenant_id": event.actor_tenant_id,
                    "approval_state": next_projection.approval_state.value,
                    "created_at": event.created_at,
                    "event_type": event.event_type,
                    "previous_event_sha256": event.previous_event_sha256,
                    "review_snapshot_id": event.review_snapshot_id,
                    "review_state": next_projection.review_state.value,
                    "sequence_no": event.sequence_no,
                }
                if (
                    event.review_state != next_projection.review_state.value
                    or event.approval_state != next_projection.approval_state.value
                    or event.event_sha256 != compute_lifecycle_sha256(payload)
                ):
                    raise EvidenceReviewIntegrityError(
                        EvidenceReviewErrorCode.DB_INTEGRITY,
                        "lifecycle state or hash drift",
                    )
            except EvidenceReviewIntegrityError:
                raise
            except Exception as exc:
                raise EvidenceReviewIntegrityError(
                    EvidenceReviewErrorCode.DB_INTEGRITY,
                    "invalid lifecycle event",
                ) from exc
            projection = EvidenceReviewProjection(
                review_state=next_projection.review_state,
                approval_state=next_projection.approval_state,
                reviewer_subject=next_projection.reviewer_subject,
                approver_subject=next_projection.approver_subject,
                last_sequence=event.sequence_no,
                last_event_sha256=event.event_sha256,
            )
        return projection
