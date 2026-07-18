"""Create/read-only persistence for inert MAT-EVID-01A manifests.

No update, delete, review, approval, pointer, activation, seed, backfill, or
runtime-selection surface exists. Every load revalidates canonical bytes,
content identities, the exact MAT-GOV-03A snapshot binding, and rule refs.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.material_evidence import (
    MAT_EVID_CONTRACT_VERSION,
    EvidenceManifestSnapshotV1,
    MaterialEvidenceErrorCode,
    MaterialEvidenceIntegrityError,
    MaterialEvidenceValidationError,
    canonicalize_payload,
    compute_audit_sha256,
    compute_validation_sha256,
    parse_manifest_payload,
    validate_domain_pack_id,
    validate_manifest_id,
    validate_ruleset_snapshot_id,
    validate_snapshot_id,
)
from sealai_v2.core.material_rulesets import (
    MaterialRulesetIntegrityError,
    MaterialRulesetSnapshotV1,
    MaterialRulesetValidationError,
    canonicalize_payload as canonicalize_ruleset_payload,
    parse_snapshot_payload as parse_ruleset_payload,
)
from sealai_v2.db.models import (
    V2MaterialEvidenceAuditEvent,
    V2MaterialEvidenceManifest,
    V2MaterialEvidenceSnapshot,
    V2MaterialEvidenceValidationEvent,
    V2MaterialRuleset,
    V2MaterialRulesetSnapshot,
)


@dataclass(frozen=True, slots=True)
class MaterialEvidenceManifestFamily:
    manifest_id: str
    ruleset_snapshot_id: str
    domain_pack_id: str
    created_by_subject: str
    created_at: str


def _require_metadata(value: str, *, field: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        raise ValueError(f"{field} must contain a non-whitespace string")
    return value


def _identity(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


class MaterialEvidenceRepository:
    """Create/read-only adapter for the isolated MAT-EVID-01A aggregate."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create_manifest(
        self,
        *,
        ruleset_snapshot_id: str,
        domain_pack_id: str,
        created_by_subject: str,
        created_at: str,
        manifest_id: str | None = None,
    ) -> MaterialEvidenceManifestFamily:
        validate_ruleset_snapshot_id(ruleset_snapshot_id)
        validate_domain_pack_id(domain_pack_id)
        actor = _require_metadata(created_by_subject, field="created_by_subject")
        timestamp = _require_metadata(created_at, field="created_at")
        identity = manifest_id or _identity("mef")
        validate_manifest_id(identity)
        with self._session_factory() as session, session.begin():
            if session.get(V2MaterialEvidenceManifest, identity) is not None:
                raise ValueError("manifest_id already exists")
            ruleset_snapshot, _ruleset_payload = self._validated_ruleset_snapshot(
                session, ruleset_snapshot_id
            )
            ruleset = session.get(V2MaterialRuleset, ruleset_snapshot.ruleset_id)
            if ruleset is None or ruleset.domain_pack_id != domain_pack_id:
                raise MaterialEvidenceValidationError(
                    MaterialEvidenceErrorCode.INVALID_ID,
                    "domain_pack_id does not match the bound ruleset snapshot",
                    path="$.domain_pack_id",
                )
            session.add(
                V2MaterialEvidenceManifest(
                    manifest_id=identity,
                    ruleset_snapshot_id=ruleset_snapshot_id,
                    domain_pack_id=domain_pack_id,
                    created_by_subject=actor,
                    created_at=timestamp,
                )
            )
        return MaterialEvidenceManifestFamily(
            manifest_id=identity,
            ruleset_snapshot_id=ruleset_snapshot_id,
            domain_pack_id=domain_pack_id,
            created_by_subject=actor,
            created_at=timestamp,
        )

    def store_snapshot(
        self,
        *,
        manifest_id: str,
        raw_payload: str | bytes,
        created_by_subject: str,
        created_at: str,
    ) -> EvidenceManifestSnapshotV1:
        validate_manifest_id(manifest_id)
        actor = _require_metadata(created_by_subject, field="created_by_subject")
        timestamp = _require_metadata(created_at, field="created_at")
        snapshot = EvidenceManifestSnapshotV1.from_json(manifest_id, raw_payload)
        with self._session_factory() as session, session.begin():
            family = session.get(V2MaterialEvidenceManifest, manifest_id)
            if family is None:
                raise KeyError(manifest_id)
            ruleset_snapshot, ruleset_payload = self._validated_ruleset_snapshot(
                session, family.ruleset_snapshot_id
            )
            self._validate_cross_bindings(
                snapshot,
                family=family,
                ruleset_snapshot=ruleset_snapshot,
                ruleset_payload=ruleset_payload,
            )
            existing = session.get(V2MaterialEvidenceSnapshot, snapshot.snapshot_id)
            if existing is not None:
                return self._validated_snapshot(
                    existing,
                    family=family,
                    ruleset_snapshot=ruleset_snapshot,
                    ruleset_payload=ruleset_payload,
                )
            session.add(
                V2MaterialEvidenceSnapshot(
                    snapshot_id=snapshot.snapshot_id,
                    manifest_id=manifest_id,
                    evidence_manifest_schema_version=(
                        snapshot.payload.evidence_manifest_schema_version
                    ),
                    canonicalization_version=(
                        snapshot.payload.canonicalization_version
                    ),
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
                V2MaterialEvidenceValidationEvent(
                    event_id=validation_event_id,
                    snapshot_id=snapshot.snapshot_id,
                    validator_contract_version=MAT_EVID_CONTRACT_VERSION,
                    validation_state="valid",
                    error_code="none",
                    validation_sha256=compute_validation_sha256(snapshot),
                    created_at=timestamp,
                )
            )
            audit_payload = {
                "content_sha256": snapshot.content_sha256,
                "snapshot_id": snapshot.snapshot_id,
                "validation_event_id": validation_event_id,
            }
            session.add(
                V2MaterialEvidenceAuditEvent(
                    event_id=_identity("mea"),
                    snapshot_id=snapshot.snapshot_id,
                    event_type="snapshot_created",
                    actor_subject=actor,
                    event_payload_json=audit_payload,
                    event_sha256=compute_audit_sha256(audit_payload),
                    created_at=timestamp,
                )
            )
        return snapshot

    def load_snapshot(self, snapshot_id: str) -> EvidenceManifestSnapshotV1:
        validate_snapshot_id(snapshot_id)
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceSnapshot, snapshot_id)
            if row is None:
                raise KeyError(snapshot_id)
            family = session.get(V2MaterialEvidenceManifest, row.manifest_id)
            if family is None:
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.DB_INTEGRITY,
                    "snapshot references a missing manifest family",
                )
            ruleset_snapshot, ruleset_payload = self._validated_ruleset_snapshot(
                session, family.ruleset_snapshot_id
            )
            return self._validated_snapshot(
                row,
                family=family,
                ruleset_snapshot=ruleset_snapshot,
                ruleset_payload=ruleset_payload,
            )

    @staticmethod
    def _validated_ruleset_snapshot(session, snapshot_id: str):
        row = session.get(V2MaterialRulesetSnapshot, snapshot_id)
        if row is None:
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.DB_INTEGRITY,
                "bound MAT-GOV-03A snapshot is absent",
            )
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_ruleset_payload(canonical_bytes)
            if canonicalize_ruleset_payload(payload) != canonical_bytes:
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.DB_INTEGRITY,
                    "bound MAT-GOV-03A bytes are not canonical",
                )
            if row.canonical_payload_json != payload.to_dict():
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.DB_INTEGRITY,
                    "bound MAT-GOV-03A JSON projection differs from canonical bytes",
                )
            if (
                row.snapshot_schema_version != payload.snapshot_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.mat_gov_contract_version != payload.mat_gov_contract_version
            ):
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.DB_INTEGRITY,
                    "bound MAT-GOV-03A contract columns differ from its payload",
                )
            ruleset = session.get(V2MaterialRuleset, row.ruleset_id)
            if ruleset is None or ruleset.domain_pack_id != payload.domain_pack_id:
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.DB_INTEGRITY,
                    "bound MAT-GOV-03A family and payload domain packs differ",
                )
            MaterialRulesetSnapshotV1(
                ruleset_id=row.ruleset_id,
                snapshot_id=row.snapshot_id,
                content_sha256=row.content_sha256,
                canonical_bytes=canonical_bytes,
                payload=payload,
            )
        except (MaterialRulesetValidationError, MaterialRulesetIntegrityError) as exc:
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.DB_INTEGRITY,
                "bound MAT-GOV-03A snapshot failed validation",
            ) from exc
        return row, payload

    @staticmethod
    def _validate_cross_bindings(
        snapshot: EvidenceManifestSnapshotV1,
        *,
        family: V2MaterialEvidenceManifest,
        ruleset_snapshot: V2MaterialRulesetSnapshot,
        ruleset_payload,
    ) -> None:
        payload = snapshot.payload
        if payload.ruleset_snapshot_id != family.ruleset_snapshot_id:
            raise MaterialEvidenceValidationError(
                MaterialEvidenceErrorCode.INVALID_ID,
                "payload does not reference the manifest family's ruleset snapshot",
                path="$.ruleset_snapshot_id",
            )
        if ruleset_snapshot.snapshot_id != payload.ruleset_snapshot_id:
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.DB_INTEGRITY,
                "loaded ruleset snapshot identity drift",
            )
        if payload.domain_pack_id != family.domain_pack_id:
            raise MaterialEvidenceValidationError(
                MaterialEvidenceErrorCode.INVALID_ID,
                "payload domain_pack_id differs from manifest family",
                path="$.domain_pack_id",
            )
        if ruleset_payload.domain_pack_id != payload.domain_pack_id:
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.DB_INTEGRITY,
                "evidence and ruleset domain packs differ",
            )
        rules = {rule.rule_ref for rule in ruleset_payload.rules}
        unknown = sorted(
            {binding.rule_ref for binding in payload.rule_claim_bindings} - rules
        )
        if unknown:
            raise MaterialEvidenceValidationError(
                MaterialEvidenceErrorCode.DANGLING_REF,
                f"bindings reference absent MAT-GOV-03A rules: {unknown}",
                path="$.rule_claim_bindings",
            )

    @classmethod
    def _validated_snapshot(
        cls,
        row: V2MaterialEvidenceSnapshot,
        *,
        family: V2MaterialEvidenceManifest,
        ruleset_snapshot: V2MaterialRulesetSnapshot,
        ruleset_payload,
    ) -> EvidenceManifestSnapshotV1:
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_manifest_payload(canonical_bytes)
            if canonicalize_payload(payload) != canonical_bytes:
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.HASH_MISMATCH,
                    "persisted bytes are not canonical",
                )
            if row.canonical_payload_json != payload.to_dict():
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.DB_INTEGRITY,
                    "persisted JSON projection differs from canonical bytes",
                )
            if (
                row.evidence_manifest_schema_version
                != payload.evidence_manifest_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.mat_evid_contract_version != payload.mat_evid_contract_version
            ):
                raise MaterialEvidenceIntegrityError(
                    MaterialEvidenceErrorCode.UNKNOWN_SCHEMA,
                    "persisted contract columns differ from payload",
                )
            snapshot = EvidenceManifestSnapshotV1(
                manifest_id=row.manifest_id,
                snapshot_id=row.snapshot_id,
                content_sha256=row.content_sha256,
                canonical_bytes=canonical_bytes,
                payload=payload,
            )
            cls._validate_cross_bindings(
                snapshot,
                family=family,
                ruleset_snapshot=ruleset_snapshot,
                ruleset_payload=ruleset_payload,
            )
            return snapshot
        except MaterialEvidenceIntegrityError:
            raise
        except MaterialEvidenceValidationError as exc:
            raise MaterialEvidenceIntegrityError(
                exc.code,
                "persisted evidence snapshot failed validation",
            ) from exc

    def validation_event_count(self, snapshot_id: str) -> int:
        validate_snapshot_id(snapshot_id)
        with self._session_factory() as session:
            return len(
                session.scalars(
                    select(V2MaterialEvidenceValidationEvent).where(
                        V2MaterialEvidenceValidationEvent.snapshot_id == snapshot_id
                    )
                ).all()
            )

    def audit_event_count(self, snapshot_id: str) -> int:
        validate_snapshot_id(snapshot_id)
        with self._session_factory() as session:
            return len(
                session.scalars(
                    select(V2MaterialEvidenceAuditEvent).where(
                        V2MaterialEvidenceAuditEvent.snapshot_id == snapshot_id
                    )
                ).all()
            )
