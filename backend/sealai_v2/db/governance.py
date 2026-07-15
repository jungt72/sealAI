"""Transactional persistence helpers for affiliation/COI governance."""

from __future__ import annotations

from hashlib import sha256
import json

from sqlalchemy import select

from sealai_v2.db.models import (
    V2GovernanceDecision,
    V2GovernanceSnapshot,
    V2IdentityAffiliationRevision,
)
from sealai_v2.governance.affiliations import (
    AffiliationGovernanceError,
    AffiliationRecord,
    AffiliationSnapshot,
    ConflictResolution,
    affiliation_snapshot_from_contract,
    capture_affiliation_snapshot,
)


def _record(row: V2IdentityAffiliationRevision) -> AffiliationRecord:
    return AffiliationRecord(
        record_id=row.id,
        subject_ref=row.subject_ref,
        organization_ref=row.organization_ref,
        relationship=row.relationship,
        authority_source=row.authority_source,
        authority_reference=row.authority_reference,
        authority_version=row.authority_version,
        effective_from=row.effective_from,
        effective_to=row.effective_to or "",
        status=row.status,
        revision=row.revision,
        recorded_at=row.recorded_at,
        recorded_by=row.recorded_by,
        record_sha256=row.record_sha256,
    )


def _stored_snapshot(row: V2GovernanceSnapshot) -> AffiliationSnapshot:
    snapshot = affiliation_snapshot_from_contract(dict(row.snapshot_json or {}))
    if (
        snapshot.snapshot_sha256 != row.id
        or snapshot.subject_ref != row.subject_ref
        or snapshot.purpose != row.purpose
        or snapshot.resource_type != row.resource_type
        or snapshot.resource_ref != row.resource_ref
        or snapshot.resource_version != row.resource_version
        or snapshot.captured_at != row.created_at
    ):
        raise AffiliationGovernanceError(
            "stored affiliation snapshot integrity mismatch"
        )
    return snapshot


def capture_snapshot(
    session,
    *,
    subject_ref: str,
    roles: tuple[str, ...],
    captured_at: str,
    purpose: str,
    resource_type: str,
    resource_ref: str,
    resource_version: int,
    expected_organization: str = "",
) -> AffiliationSnapshot:
    existing = session.scalar(
        select(V2GovernanceSnapshot)
        .where(
            V2GovernanceSnapshot.resource_type == resource_type,
            V2GovernanceSnapshot.resource_ref == resource_ref,
            V2GovernanceSnapshot.resource_version == resource_version,
            V2GovernanceSnapshot.purpose == purpose,
        )
        .with_for_update()
    )
    if existing is not None:
        snapshot = _stored_snapshot(existing)
        if snapshot.subject_ref != subject_ref or set(snapshot.roles) != set(roles):
            raise AffiliationGovernanceError(
                "resource version is already bound to a different governance actor"
            )
        return snapshot

    rows = session.scalars(
        select(V2IdentityAffiliationRevision)
        .where(V2IdentityAffiliationRevision.subject_ref == subject_ref)
        .order_by(
            V2IdentityAffiliationRevision.organization_ref,
            V2IdentityAffiliationRevision.relationship,
            V2IdentityAffiliationRevision.revision,
        )
        .with_for_update()
    ).all()
    snapshot = capture_affiliation_snapshot(
        (_record(row) for row in rows),
        subject_ref=subject_ref,
        roles=roles,
        captured_at=captured_at,
        purpose=purpose,
        resource_type=resource_type,
        resource_ref=resource_ref,
        resource_version=resource_version,
        expected_organization=expected_organization,
    )
    session.add(
        V2GovernanceSnapshot(
            id=snapshot.snapshot_sha256,
            subject_ref=snapshot.subject_ref,
            purpose=snapshot.purpose,
            resource_type=snapshot.resource_type,
            resource_ref=snapshot.resource_ref,
            resource_version=snapshot.resource_version,
            snapshot_json=snapshot.contract(),
            created_at=captured_at,
        )
    )
    session.flush()
    return snapshot


def load_snapshot(
    session,
    *,
    resource_type: str,
    resource_ref: str,
    resource_version: int,
    purpose: str,
) -> AffiliationSnapshot:
    row = session.scalar(
        select(V2GovernanceSnapshot)
        .where(
            V2GovernanceSnapshot.resource_type == resource_type,
            V2GovernanceSnapshot.resource_ref == resource_ref,
            V2GovernanceSnapshot.resource_version == resource_version,
            V2GovernanceSnapshot.purpose == purpose,
        )
        .with_for_update()
    )
    if row is None:
        raise AffiliationGovernanceError(
            "required immutable affiliation snapshot is unavailable"
        )
    return _stored_snapshot(row)


def record_decision(
    session,
    *,
    decision_type: str,
    resource_type: str,
    resource_ref: str,
    resource_version: int,
    resolution: ConflictResolution,
    created_at: str,
    binding_sha256: str = "",
) -> None:
    if binding_sha256 and (
        len(binding_sha256) != 64
        or any(character not in "0123456789abcdef" for character in binding_sha256)
    ):
        raise AffiliationGovernanceError("governance decision binding is invalid")
    decision = {
        **resolution.contract(),
        "decision_type": decision_type,
        "resource_type": resource_type,
        "resource_ref": resource_ref,
        "resource_version": resource_version,
        "created_at": created_at,
        "binding_sha256": binding_sha256,
    }
    decision_id = _decision_id(decision)
    existing = session.scalar(
        select(V2GovernanceDecision)
        .where(
            V2GovernanceDecision.decision_type == decision_type,
            V2GovernanceDecision.resource_type == resource_type,
            V2GovernanceDecision.resource_ref == resource_ref,
            V2GovernanceDecision.resource_version == resource_version,
        )
        .with_for_update()
    )
    if existing is not None:
        _stored_decision(existing, expected=decision)
        return
    colliding_id = session.get(V2GovernanceDecision, decision_id)
    if colliding_id is not None:
        raise AffiliationGovernanceError("governance decision identity collision")
    session.add(
        V2GovernanceDecision(
            id=decision_id,
            decision_type=decision_type,
            resource_type=resource_type,
            resource_ref=resource_ref,
            resource_version=resource_version,
            first_snapshot_id=resolution.first_snapshot_sha256,
            second_snapshot_id=resolution.second_snapshot_sha256,
            outcome=resolution.outcome,
            reason_code=resolution.reason_code,
            decision_json=decision,
            created_at=created_at,
        )
    )
    session.flush()


def _decision_id(decision: dict) -> str:
    return sha256(
        json.dumps(
            decision, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
    ).hexdigest()


def _stored_decision(
    row: V2GovernanceDecision, *, expected: dict | None = None
) -> dict:
    decision = dict(row.decision_json or {})
    if (
        (expected is not None and decision != expected)
        or _decision_id(decision) != row.id
        or decision.get("decision_type") != row.decision_type
        or decision.get("resource_type") != row.resource_type
        or decision.get("resource_ref") != row.resource_ref
        or decision.get("resource_version") != row.resource_version
        or decision.get("first_snapshot_sha256") != row.first_snapshot_id
        or decision.get("second_snapshot_sha256") != row.second_snapshot_id
        or decision.get("outcome") != row.outcome
        or decision.get("reason_code") != row.reason_code
        or decision.get("created_at") != row.created_at
        or not isinstance(decision.get("binding_sha256"), str)
        or not isinstance(decision.get("shared_organization_sha256"), list)
    ):
        raise AffiliationGovernanceError("governance decision integrity mismatch")
    return decision


def carry_forward_allow_decision(
    session,
    *,
    decision_type: str,
    resource_type: str,
    resource_ref: str,
    from_version: int,
    to_version: int,
    binding_sha256: str,
    created_at: str,
) -> bool:
    rows = session.scalars(
        select(V2GovernanceDecision)
        .where(
            V2GovernanceDecision.decision_type == decision_type,
            V2GovernanceDecision.resource_type == resource_type,
            V2GovernanceDecision.resource_ref == resource_ref,
            V2GovernanceDecision.resource_version == from_version,
            V2GovernanceDecision.outcome == "allow",
        )
        .with_for_update()
    ).all()
    if not rows:
        return False
    if len(rows) != 1:
        raise AffiliationGovernanceError("ambiguous governance decision history")
    previous = rows[0]
    contract = _stored_decision(previous)
    if contract["binding_sha256"] != binding_sha256:
        raise AffiliationGovernanceError(
            "governance decision binding changed during carry-forward"
        )
    if contract["shared_organization_sha256"]:
        raise AffiliationGovernanceError(
            "allow decision contains a shared-affiliation conflict"
        )
    if previous.first_snapshot_id == previous.second_snapshot_id:
        raise AffiliationGovernanceError(
            "allow decision does not contain two independent snapshots"
        )
    snapshot_rows = session.scalars(
        select(V2GovernanceSnapshot)
        .where(
            V2GovernanceSnapshot.id.in_(
                {previous.first_snapshot_id, previous.second_snapshot_id}
            )
        )
        .with_for_update()
    ).all()
    if {row.id for row in snapshot_rows} != {
        previous.first_snapshot_id,
        previous.second_snapshot_id,
    }:
        raise AffiliationGovernanceError(
            "governance decision snapshot history is incomplete"
        )
    expected_snapshot_versions = {
        previous.first_snapshot_id: from_version - 1,
        previous.second_snapshot_id: from_version,
    }
    for row in snapshot_rows:
        snapshot = _stored_snapshot(row)
        if (
            snapshot.resource_type != resource_type
            or snapshot.resource_ref != resource_ref
            or snapshot.resource_version != expected_snapshot_versions[row.id]
        ):
            raise AffiliationGovernanceError(
                "governance decision snapshot binding is invalid"
            )
    resolution = ConflictResolution(
        outcome="allow",
        reason_code="unchanged_authority_contract_carry_forward",
        first_snapshot_sha256=previous.first_snapshot_id,
        second_snapshot_sha256=previous.second_snapshot_id,
    )
    record_decision(
        session,
        decision_type=decision_type,
        resource_type=resource_type,
        resource_ref=resource_ref,
        resource_version=to_version,
        resolution=resolution,
        created_at=created_at,
        binding_sha256=binding_sha256,
    )
    return True
