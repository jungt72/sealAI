"""MAT-GOV-03A persistence adapter for immutable technical snapshots.

The repository intentionally has no update, delete, review, approval, pointer,
pinning, or activation method.  Every database read reconstructs and validates
the immutable domain snapshot before returning it.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.material_rulesets import (
    MAT_GOV_CONTRACT_VERSION,
    MaterialRulesetErrorCode,
    MaterialRulesetIntegrityError,
    MaterialRulesetSnapshotV1,
    MaterialRulesetValidationError,
    canonicalize_payload,
    compute_audit_sha256,
    compute_validation_sha256,
    generate_ruleset_id,
    parse_snapshot_payload,
    validate_domain_pack_id,
    validate_ruleset_id,
    validate_snapshot_id,
)
from sealai_v2.db.models import (
    V2MaterialRuleset,
    V2MaterialRulesetSnapshot,
    V2MaterialSnapshotAuditEvent,
    V2MaterialSnapshotValidationEvent,
)


@dataclass(frozen=True, slots=True)
class MaterialRulesetFamily:
    ruleset_id: str
    domain_pack_id: str
    created_by_subject: str
    created_at: str


def _require_metadata(value: str, *, field: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        raise ValueError(f"{field} must contain a non-whitespace string")
    return value


def _event_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


class MaterialRulesetRepository:
    """Create/read-only adapter for the isolated MAT-GOV-03A aggregate."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create_ruleset(
        self,
        *,
        domain_pack_id: str,
        created_by_subject: str,
        created_at: str,
        ruleset_id: str | None = None,
    ) -> MaterialRulesetFamily:
        validate_domain_pack_id(domain_pack_id)
        actor = _require_metadata(created_by_subject, field="created_by_subject")
        timestamp = _require_metadata(created_at, field="created_at")
        identity = ruleset_id or generate_ruleset_id()
        validate_ruleset_id(identity)
        with self._session_factory() as session, session.begin():
            if session.get(V2MaterialRuleset, identity) is not None:
                raise ValueError("ruleset_id already exists")
            session.add(
                V2MaterialRuleset(
                    ruleset_id=identity,
                    domain_pack_id=domain_pack_id,
                    created_by_subject=actor,
                    created_at=timestamp,
                )
            )
        return MaterialRulesetFamily(
            ruleset_id=identity,
            domain_pack_id=domain_pack_id,
            created_by_subject=actor,
            created_at=timestamp,
        )

    def get_ruleset(self, ruleset_id: str) -> MaterialRulesetFamily:
        validate_ruleset_id(ruleset_id)
        with self._session_factory() as session:
            row = session.get(V2MaterialRuleset, ruleset_id)
            if row is None:
                raise KeyError(ruleset_id)
            return MaterialRulesetFamily(
                ruleset_id=row.ruleset_id,
                domain_pack_id=row.domain_pack_id,
                created_by_subject=row.created_by_subject,
                created_at=row.created_at,
            )

    def store_snapshot(
        self,
        *,
        ruleset_id: str,
        raw_payload: str | bytes,
        created_by_subject: str,
        created_at: str,
    ) -> MaterialRulesetSnapshotV1:
        validate_ruleset_id(ruleset_id)
        actor = _require_metadata(created_by_subject, field="created_by_subject")
        timestamp = _require_metadata(created_at, field="created_at")
        snapshot = MaterialRulesetSnapshotV1.from_json(ruleset_id, raw_payload)
        with self._session_factory() as session, session.begin():
            family = session.get(V2MaterialRuleset, ruleset_id)
            if family is None:
                raise KeyError(ruleset_id)
            if family.domain_pack_id != snapshot.payload.domain_pack_id:
                raise MaterialRulesetValidationError(
                    MaterialRulesetErrorCode.INVALID_ID,
                    "payload domain_pack_id does not match the ruleset family",
                    path="$.domain_pack_id",
                )
            existing = session.get(V2MaterialRulesetSnapshot, snapshot.snapshot_id)
            if existing is not None:
                return self._validated_snapshot(existing, family)

            session.add(
                V2MaterialRulesetSnapshot(
                    snapshot_id=snapshot.snapshot_id,
                    ruleset_id=ruleset_id,
                    snapshot_schema_version=snapshot.payload.snapshot_schema_version,
                    canonicalization_version=(
                        snapshot.payload.canonicalization_version
                    ),
                    mat_gov_contract_version=(
                        snapshot.payload.mat_gov_contract_version
                    ),
                    content_sha256=snapshot.content_sha256,
                    canonical_payload_json=snapshot.payload.to_dict(),
                    canonical_bytes=snapshot.canonical_bytes,
                    created_by_subject=actor,
                    created_at=timestamp,
                )
            )
            session.flush()

            validation_event_id = _event_id("mtv")
            session.add(
                V2MaterialSnapshotValidationEvent(
                    event_id=validation_event_id,
                    snapshot_id=snapshot.snapshot_id,
                    validator_contract_version=MAT_GOV_CONTRACT_VERSION,
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
                V2MaterialSnapshotAuditEvent(
                    event_id=_event_id("mta"),
                    snapshot_id=snapshot.snapshot_id,
                    event_type="snapshot_created",
                    actor_subject=actor,
                    event_payload_json=audit_payload,
                    event_sha256=compute_audit_sha256(audit_payload),
                    created_at=timestamp,
                )
            )
        return snapshot

    def load_snapshot(self, snapshot_id: str) -> MaterialRulesetSnapshotV1:
        validate_snapshot_id(snapshot_id)
        with self._session_factory() as session:
            row = session.get(V2MaterialRulesetSnapshot, snapshot_id)
            if row is None:
                raise KeyError(snapshot_id)
            family = session.get(V2MaterialRuleset, row.ruleset_id)
            if family is None:
                raise MaterialRulesetIntegrityError(
                    MaterialRulesetErrorCode.DB_INTEGRITY,
                    "snapshot references a missing ruleset family",
                )
            return self._validated_snapshot(row, family)

    @staticmethod
    def _validated_snapshot(
        row: V2MaterialRulesetSnapshot, family: V2MaterialRuleset
    ) -> MaterialRulesetSnapshotV1:
        try:
            canonical_bytes = bytes(row.canonical_bytes)
            payload = parse_snapshot_payload(canonical_bytes)
            if canonicalize_payload(payload) != canonical_bytes:
                raise MaterialRulesetIntegrityError(
                    MaterialRulesetErrorCode.HASH_MISMATCH,
                    "persisted bytes are not the canonical encoding",
                )
            if row.canonical_payload_json != payload.to_dict():
                raise MaterialRulesetIntegrityError(
                    MaterialRulesetErrorCode.DB_INTEGRITY,
                    "persisted JSON projection differs from canonical bytes",
                )
            if (
                row.snapshot_schema_version != payload.snapshot_schema_version
                or row.canonicalization_version != payload.canonicalization_version
                or row.mat_gov_contract_version != payload.mat_gov_contract_version
            ):
                raise MaterialRulesetIntegrityError(
                    MaterialRulesetErrorCode.UNKNOWN_SCHEMA,
                    "persisted contract columns differ from the payload",
                )
            if family.domain_pack_id != payload.domain_pack_id:
                raise MaterialRulesetIntegrityError(
                    MaterialRulesetErrorCode.DB_INTEGRITY,
                    "ruleset family and snapshot domain pack differ",
                )
            return MaterialRulesetSnapshotV1(
                ruleset_id=row.ruleset_id,
                snapshot_id=row.snapshot_id,
                content_sha256=row.content_sha256,
                canonical_bytes=canonical_bytes,
                payload=payload,
            )
        except MaterialRulesetIntegrityError:
            raise
        except MaterialRulesetValidationError as exc:
            raise MaterialRulesetIntegrityError(
                exc.code,
                "persisted snapshot failed schema validation",
            ) from exc

    def validation_event_count(self, snapshot_id: str) -> int:
        validate_snapshot_id(snapshot_id)
        with self._session_factory() as session:
            return len(
                session.scalars(
                    select(V2MaterialSnapshotValidationEvent).where(
                        V2MaterialSnapshotValidationEvent.snapshot_id == snapshot_id
                    )
                ).all()
            )

    def audit_event_count(self, snapshot_id: str) -> int:
        validate_snapshot_id(snapshot_id)
        with self._session_factory() as session:
            return len(
                session.scalars(
                    select(V2MaterialSnapshotAuditEvent).where(
                        V2MaterialSnapshotAuditEvent.snapshot_id == snapshot_id
                    )
                ).all()
            )
