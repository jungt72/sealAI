"""Create/read-only persistence for additive MAT-EVID-01A.v2 manifests.

Version 1 remains in ``material_evidence.py``.  This repository stores only
the closed v2 target union and revalidates canonical bytes, target identity,
ruleset scope (when applicable), and append-only technical evidence on every
read.  It exposes no conversion, seed, review, activation, or public API.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.material_evidence_v2 import (
    MAT_EVID_CONTRACT_VERSION_V2,
    EvidenceManifestSnapshotV2,
    EvidenceManifestTargetV2,
    MaterialEvidenceV2ErrorCode,
    MaterialEvidenceV2IntegrityError,
    MaterialEvidenceV2ValidationError,
    MaterialRelationTargetV2,
    MediaIdentityTargetV2,
    canonicalize_payload_v2,
    compute_audit_sha256_v2,
    compute_validation_sha256_v2,
    parse_manifest_payload_v2,
    validate_domain_pack_id_v2,
    validate_manifest_id_v2,
    validate_snapshot_id_v2,
)
from sealai_v2.core.material_rulesets import (
    MaterialRulesetIntegrityError,
    MaterialRulesetSnapshotV1,
    MaterialRulesetValidationError,
    canonicalize_payload as canonicalize_ruleset_payload,
    parse_snapshot_payload as parse_ruleset_payload,
)
from sealai_v2.db.models import (
    V2MaterialEvidenceAuditEventV2,
    V2MaterialEvidenceManifestV2,
    V2MaterialEvidenceSnapshotV2,
    V2MaterialEvidenceValidationEventV2,
    V2MaterialRuleset,
    V2MaterialRulesetSnapshot,
)


@dataclass(frozen=True, slots=True)
class MaterialEvidenceManifestFamilyV2:
    manifest_id: str
    target: EvidenceManifestTargetV2
    domain_pack_id: str
    created_by_subject: str
    created_at: str


def _metadata(value: str, *, field: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        raise ValueError(f"{field} must contain a non-whitespace string")
    return value


def _identity(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _target_from_row(row: V2MaterialEvidenceManifestV2) -> EvidenceManifestTargetV2:
    if row.target_type == "material_relation":
        if (
            row.ruleset_snapshot_id is None
            or row.media_ref is not None
            or row.target_ref != row.ruleset_snapshot_id
        ):
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "persisted material target columns are incomplete",
            )
        return MaterialRelationTargetV2(row.ruleset_snapshot_id)
    if row.target_type == "media_identity":
        if (
            row.media_ref is None
            or row.ruleset_snapshot_id is not None
            or row.target_ref != row.media_ref
        ):
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "persisted media target columns are incomplete",
            )
        return MediaIdentityTargetV2(row.media_ref)
    raise MaterialEvidenceV2IntegrityError(
        MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
        "persisted manifest has an unknown target type",
    )


class MaterialEvidenceRepositoryV2:
    """Isolated create/read-only adapter for MAT-EVID-01A.v2."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create_manifest(
        self,
        *,
        target: EvidenceManifestTargetV2,
        domain_pack_id: str,
        created_by_subject: str,
        created_at: str,
        manifest_id: str | None = None,
    ) -> MaterialEvidenceManifestFamilyV2:
        if type(target) not in {MaterialRelationTargetV2, MediaIdentityTargetV2}:
            raise TypeError("target must be an exact MAT-EVID-01A.v2 target")
        validate_domain_pack_id_v2(domain_pack_id)
        actor = _metadata(created_by_subject, field="created_by_subject")
        timestamp = _metadata(created_at, field="created_at")
        identifier = manifest_id or _identity("mef")
        validate_manifest_id_v2(identifier)
        with self._session_factory() as session, session.begin():
            if session.get(V2MaterialEvidenceManifestV2, identifier) is not None:
                raise ValueError("manifest_id already exists")
            if type(target) is MaterialRelationTargetV2:
                ruleset_row, ruleset_payload = self._validated_ruleset_snapshot(
                    session, target.ruleset_snapshot_id
                )
                ruleset = session.get(V2MaterialRuleset, ruleset_row.ruleset_id)
                if ruleset is None or ruleset.domain_pack_id != domain_pack_id:
                    raise MaterialEvidenceV2ValidationError(
                        MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                        "domain pack differs from the exact ruleset snapshot",
                        path="$.domain_pack_id",
                    )
                if ruleset_payload.domain_pack_id != domain_pack_id:
                    raise MaterialEvidenceV2IntegrityError(
                        MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                        "ruleset family and payload domain packs differ",
                    )
                duplicate = session.scalar(
                    select(V2MaterialEvidenceManifestV2).where(
                        V2MaterialEvidenceManifestV2.target_type == "material_relation",
                        V2MaterialEvidenceManifestV2.ruleset_snapshot_id
                        == target.ruleset_snapshot_id,
                        V2MaterialEvidenceManifestV2.domain_pack_id == domain_pack_id,
                    )
                )
                ruleset_snapshot_id = target.ruleset_snapshot_id
                media_ref = None
            else:
                duplicate = session.scalar(
                    select(V2MaterialEvidenceManifestV2).where(
                        V2MaterialEvidenceManifestV2.target_type == "media_identity",
                        V2MaterialEvidenceManifestV2.media_ref == target.media_ref,
                        V2MaterialEvidenceManifestV2.domain_pack_id == domain_pack_id,
                    )
                )
                ruleset_snapshot_id = None
                media_ref = target.media_ref
            if duplicate is not None:
                raise ValueError("manifest target already exists")
            session.add(
                V2MaterialEvidenceManifestV2(
                    manifest_id=identifier,
                    target_type=target.target_type.value,
                    target_ref=(
                        target.ruleset_snapshot_id
                        if type(target) is MaterialRelationTargetV2
                        else target.media_ref
                    ),
                    ruleset_snapshot_id=ruleset_snapshot_id,
                    media_ref=media_ref,
                    domain_pack_id=domain_pack_id,
                    created_by_subject=actor,
                    created_at=timestamp,
                )
            )
        return MaterialEvidenceManifestFamilyV2(
            identifier, target, domain_pack_id, actor, timestamp
        )

    def store_snapshot(
        self,
        *,
        manifest_id: str,
        raw_payload: str | bytes,
        created_by_subject: str,
        created_at: str,
    ) -> EvidenceManifestSnapshotV2:
        validate_manifest_id_v2(manifest_id)
        actor = _metadata(created_by_subject, field="created_by_subject")
        timestamp = _metadata(created_at, field="created_at")
        snapshot = EvidenceManifestSnapshotV2.from_json(manifest_id, raw_payload)
        with self._session_factory() as session, session.begin():
            family = session.get(V2MaterialEvidenceManifestV2, manifest_id)
            if family is None:
                raise KeyError(manifest_id)
            ruleset = self._ruleset_for_family(session, family)
            self._validate_cross_bindings(snapshot, family=family, ruleset=ruleset)
            existing = session.get(V2MaterialEvidenceSnapshotV2, snapshot.snapshot_id)
            if existing is not None:
                return self._validated_snapshot(
                    existing, family=family, ruleset=ruleset, session=session
                )
            session.add(
                V2MaterialEvidenceSnapshotV2(
                    snapshot_id=snapshot.snapshot_id,
                    manifest_id=manifest_id,
                    evidence_manifest_schema_version=(
                        snapshot.payload.evidence_manifest_schema_version
                    ),
                    canonicalization_version=snapshot.payload.canonicalization_version,
                    mat_evid_contract_version=(
                        snapshot.payload.mat_evid_contract_version
                    ),
                    content_sha256=snapshot.content_sha256,
                    canonical_payload_json=snapshot.payload.to_dict(),
                    canonical_bytes=snapshot.canonical_bytes,
                    created_by_subject=actor,
                    created_at=timestamp,
                )
            )
            session.flush()
            validation_event_id = _identity("mev")
            session.add(
                V2MaterialEvidenceValidationEventV2(
                    event_id=validation_event_id,
                    snapshot_id=snapshot.snapshot_id,
                    validator_contract_version=MAT_EVID_CONTRACT_VERSION_V2,
                    validation_state="valid",
                    error_code="none",
                    validation_sha256=compute_validation_sha256_v2(snapshot),
                    created_at=timestamp,
                )
            )
            audit_payload = {
                "content_sha256": snapshot.content_sha256,
                "snapshot_id": snapshot.snapshot_id,
                "target": snapshot.payload.target.to_dict(),
                "validation_event_id": validation_event_id,
            }
            session.add(
                V2MaterialEvidenceAuditEventV2(
                    event_id=_identity("mea"),
                    snapshot_id=snapshot.snapshot_id,
                    event_type="snapshot_created",
                    actor_subject=actor,
                    event_payload_json=audit_payload,
                    event_sha256=compute_audit_sha256_v2(audit_payload),
                    created_at=timestamp,
                )
            )
        return snapshot

    def load_snapshot(self, snapshot_id: str) -> EvidenceManifestSnapshotV2:
        validate_snapshot_id_v2(snapshot_id)
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceSnapshotV2, snapshot_id)
            if row is None:
                raise KeyError(snapshot_id)
            family = session.get(V2MaterialEvidenceManifestV2, row.manifest_id)
            if family is None:
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "snapshot references a missing manifest family",
                )
            ruleset = self._ruleset_for_family(session, family)
            return self._validated_snapshot(
                row, family=family, ruleset=ruleset, session=session
            )

    @staticmethod
    def _validated_ruleset_snapshot(session, snapshot_id: str):
        row = session.get(V2MaterialRulesetSnapshot, snapshot_id)
        if row is None:
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "bound MAT-GOV-03A snapshot is absent",
            )
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_ruleset_payload(canonical_bytes)
            if (
                canonicalize_ruleset_payload(payload) != canonical_bytes
                or row.canonical_payload_json != payload.to_dict()
                or row.snapshot_schema_version != payload.snapshot_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.mat_gov_contract_version != payload.mat_gov_contract_version
            ):
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "bound MAT-GOV-03A snapshot columns or bytes drifted",
                )
            MaterialRulesetSnapshotV1(
                ruleset_id=row.ruleset_id,
                snapshot_id=row.snapshot_id,
                content_sha256=row.content_sha256,
                canonical_bytes=canonical_bytes,
                payload=payload,
            )
            ruleset = session.get(V2MaterialRuleset, row.ruleset_id)
            if ruleset is None or ruleset.domain_pack_id != payload.domain_pack_id:
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "bound MAT-GOV-03A family and payload domain packs differ",
                )
        except MaterialEvidenceV2IntegrityError:
            raise
        except (MaterialRulesetValidationError, MaterialRulesetIntegrityError) as exc:
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "bound MAT-GOV-03A snapshot failed validation",
            ) from exc
        return row, payload

    @classmethod
    def _ruleset_for_family(cls, session, family):
        target = _target_from_row(family)
        if type(target) is MediaIdentityTargetV2:
            return None
        return cls._validated_ruleset_snapshot(session, target.ruleset_snapshot_id)

    @staticmethod
    def _validate_cross_bindings(snapshot, *, family, ruleset) -> None:
        payload = snapshot.payload
        target = _target_from_row(family)
        if payload.target != target or payload.domain_pack_id != family.domain_pack_id:
            raise MaterialEvidenceV2ValidationError(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "payload target or domain pack differs from its manifest family",
                path="$.target",
            )
        if type(target) is MediaIdentityTargetV2:
            if ruleset is not None:
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "media identity family unexpectedly resolved a ruleset",
                )
            return
        if ruleset is None:
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "material relation family lacks its ruleset",
            )
        ruleset_row, ruleset_payload = ruleset
        if (
            ruleset_row.snapshot_id != target.ruleset_snapshot_id
            or ruleset_payload.domain_pack_id != family.domain_pack_id
        ):
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "ruleset target or domain pack drifted",
            )
        known_rules = {rule.rule_ref for rule in ruleset_payload.rules}
        binding_rules = {item.rule_ref for item in payload.rule_claim_bindings}
        if binding_rules - known_rules:
            raise MaterialEvidenceV2ValidationError(
                MaterialEvidenceV2ErrorCode.DANGLING_REF,
                "manifest references rules absent from the exact ruleset snapshot",
                path="$.rule_claim_bindings",
            )

    @classmethod
    def _validated_snapshot(cls, row, *, family, ruleset, session):
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_manifest_payload_v2(canonical_bytes)
            if (
                canonicalize_payload_v2(payload) != canonical_bytes
                or row.canonical_payload_json != payload.to_dict()
                or row.evidence_manifest_schema_version
                != payload.evidence_manifest_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.mat_evid_contract_version != payload.mat_evid_contract_version
            ):
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "persisted v2 payload bytes, projection, or versions drifted",
                )
            snapshot = EvidenceManifestSnapshotV2(
                manifest_id=row.manifest_id,
                snapshot_id=row.snapshot_id,
                content_sha256=row.content_sha256,
                canonical_bytes=canonical_bytes,
                payload=payload,
            )
            cls._validate_cross_bindings(snapshot, family=family, ruleset=ruleset)
            validations = session.scalars(
                select(V2MaterialEvidenceValidationEventV2).where(
                    V2MaterialEvidenceValidationEventV2.snapshot_id == row.snapshot_id
                )
            ).all()
            audits = session.scalars(
                select(V2MaterialEvidenceAuditEventV2).where(
                    V2MaterialEvidenceAuditEventV2.snapshot_id == row.snapshot_id
                )
            ).all()
            if len(validations) != 1 or len(audits) != 1:
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "snapshot requires one validation and one creation audit",
                )
            validation = validations[0]
            if (
                validation.validator_contract_version != MAT_EVID_CONTRACT_VERSION_V2
                or validation.validation_state != "valid"
                or validation.error_code != "none"
                or validation.validation_sha256
                != compute_validation_sha256_v2(snapshot)
            ):
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "snapshot validation event drifted",
                )
            audit_payload = {
                "content_sha256": snapshot.content_sha256,
                "snapshot_id": snapshot.snapshot_id,
                "target": snapshot.payload.target.to_dict(),
                "validation_event_id": validation.event_id,
            }
            audit = audits[0]
            if (
                audit.event_type != "snapshot_created"
                or audit.actor_subject != row.created_by_subject
                or audit.event_payload_json != audit_payload
                or audit.event_sha256 != compute_audit_sha256_v2(audit_payload)
            ):
                raise MaterialEvidenceV2IntegrityError(
                    MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                    "snapshot creation audit drifted",
                )
            return snapshot
        except MaterialEvidenceV2IntegrityError:
            raise
        except MaterialEvidenceV2ValidationError as exc:
            raise MaterialEvidenceV2IntegrityError(
                exc.code, "persisted v2 evidence snapshot failed validation"
            ) from exc
        except Exception as exc:
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.DB_INTEGRITY,
                "persisted v2 evidence snapshot failed strict revalidation",
            ) from exc


__all__ = ["MaterialEvidenceManifestFamilyV2", "MaterialEvidenceRepositoryV2"]
