"""Postgres adapter for independently reviewed manufacturer capabilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.governance import capture_snapshot, load_snapshot, record_decision
from sealai_v2.db.models import (
    V2GovernanceDecision,
    V2ManufacturerCapabilityProfile,
    V2ManufacturerCapabilityReview,
)
from sealai_v2.governance.affiliations import (
    AffiliationGovernanceError,
    require_governed_role,
    resolve_independence,
)
from sealai_v2.knowledge.manufacturer_capability import (
    ManufacturerCapabilityError,
    ManufacturerCapabilityProfile,
    _validate_review,
)

_LIST_FIELDS = (
    "regions",
    "contacts",
    "seal_types",
    "materials",
    "compounds",
    "size_ranges",
    "manufacturing_processes",
    "tolerances",
    "special_capabilities",
    "industries",
    "certificates",
    "test_capabilities",
    "approvals",
    "documents",
    "services",
    "application_limits",
    "exclusions",
)


def _to_domain(
    row: V2ManufacturerCapabilityProfile, *, server_governed: bool = False
) -> ManufacturerCapabilityProfile:
    values = {
        field: tuple(getattr(row, f"{field}_json") or ()) for field in _LIST_FIELDS
    }
    profile = ManufacturerCapabilityProfile(
        manufacturer_id=row.manufacturer_id,
        company_name=row.company_name,
        status=row.status,
        evidence=tuple(row.evidence_json or ()),
        submitted_at=row.submitted_at or "",
        updated_at=row.updated_at,
        verified_at=row.verified_at or "",
        verified_by=row.verified_by or "",
        review_expires_at=row.review_expires_at or "",
        change_reason=row.change_reason,
        version=row.version,
        **values,
    )
    if profile.status == "verified" and not server_governed:
        return ManufacturerCapabilityProfile(
            **{
                **profile.__dict__,
                "status": "quarantined",
                "verified_at": "",
                "verified_by": "",
                "review_expires_at": "",
            }
        )
    return profile


def _write_fields(row: V2ManufacturerCapabilityProfile, profile) -> None:
    row.company_name = profile.company_name
    for field in _LIST_FIELDS:
        setattr(row, f"{field}_json", list(getattr(profile, field)))


class PostgresManufacturerCapabilityStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def get(self, manufacturer_id: str) -> ManufacturerCapabilityProfile | None:
        with self._sf() as session:
            row = session.get(V2ManufacturerCapabilityProfile, manufacturer_id)
            if row is None:
                return None
            governed = self._has_governance_decision(session, row)
            return _to_domain(row, server_governed=governed)

    def list_all(self) -> tuple[ManufacturerCapabilityProfile, ...]:
        with self._sf() as session:
            rows = session.scalars(
                select(V2ManufacturerCapabilityProfile).order_by(
                    V2ManufacturerCapabilityProfile.company_name
                )
            ).all()
            governed = {
                (item.resource_ref, item.resource_version)
                for item in session.scalars(
                    select(V2GovernanceDecision).where(
                        V2GovernanceDecision.decision_type == "capability_verification",
                        V2GovernanceDecision.resource_type == "manufacturer_capability",
                        V2GovernanceDecision.outcome == "allow",
                    )
                ).all()
            }
            return tuple(
                _to_domain(
                    row,
                    server_governed=(row.manufacturer_id, row.version) in governed,
                )
                for row in rows
            )

    @staticmethod
    def _has_governance_decision(session, row) -> bool:
        if row.status != "verified":
            return True
        return (
            session.scalar(
                select(V2GovernanceDecision.id).where(
                    V2GovernanceDecision.decision_type == "capability_verification",
                    V2GovernanceDecision.resource_type == "manufacturer_capability",
                    V2GovernanceDecision.resource_ref == row.manufacturer_id,
                    V2GovernanceDecision.resource_version == row.version,
                    V2GovernanceDecision.outcome == "allow",
                )
            )
            is not None
        )

    def submit(
        self,
        profile: ManufacturerCapabilityProfile,
        *,
        actor: str,
        actor_roles: tuple[str, ...],
        now: str,
    ) -> ManufacturerCapabilityProfile:
        if (
            not profile.manufacturer_id.strip()
            or not profile.company_name.strip()
            or not actor.strip()
        ):
            raise ManufacturerCapabilityError(
                "manufacturer_id, company_name, and actor are required"
            )
        with self._sf() as session:
            row = session.scalar(
                select(V2ManufacturerCapabilityProfile)
                .where(
                    V2ManufacturerCapabilityProfile.manufacturer_id
                    == profile.manufacturer_id
                )
                .with_for_update()
            )
            previous = row.status if row is not None else "unsubmitted"
            if row is None:
                row = V2ManufacturerCapabilityProfile(
                    manufacturer_id=profile.manufacturer_id,
                    updated_at=now,
                )
                session.add(row)
                version = 1
            else:
                version = row.version + 1
            try:
                submission_snapshot = capture_snapshot(
                    session,
                    subject_ref=actor,
                    roles=actor_roles,
                    captured_at=now,
                    purpose="capability_submission",
                    resource_type="manufacturer_capability",
                    resource_ref=profile.manufacturer_id,
                    resource_version=version,
                    expected_organization=profile.manufacturer_id,
                )
                require_governed_role(
                    submission_snapshot,
                    required_role="manufacturer",
                    incompatible_roles=(
                        "capability_reviewer",
                        "tenant_admin",
                        "platform_owner",
                        "system_operator",
                    ),
                )
            except AffiliationGovernanceError as exc:
                raise ManufacturerCapabilityError(
                    "manufacturer submission authority is unavailable or incompatible"
                ) from exc
            _write_fields(row, profile)
            row.status = "submitted"
            row.evidence_json = []
            row.submitted_at = now
            row.updated_at = now
            row.verified_at = None
            row.verified_by = None
            row.review_expires_at = None
            row.change_reason = profile.change_reason
            row.version = version
            session.add(
                V2ManufacturerCapabilityReview(
                    manufacturer_id=profile.manufacturer_id,
                    from_status=previous,
                    to_status="submitted",
                    actor=actor,
                    actor_relation="manufacturer",
                    conflict_of_interest="submission_authority_bound",
                    note=profile.change_reason,
                    evidence_json=[],
                    created_at=now,
                )
            )
            session.commit()
            return _to_domain(row)

    def review(
        self,
        manufacturer_id: str,
        *,
        to_status: str,
        actor: str,
        actor_roles: tuple[str, ...],
        actor_relation: str,
        now: str,
        note: str = "",
        evidence: tuple[dict, ...] = (),
        review_expires_at: str = "",
        required_reviewer_role: str = "capability_reviewer",
        incompatible_reviewer_roles: tuple[str, ...] = (
            "manufacturer",
            "tenant_admin",
            "platform_owner",
            "system_operator",
        ),
    ) -> ManufacturerCapabilityProfile:
        _validate_review(
            to_status=to_status,
            actor=actor,
            actor_relation=actor_relation,
            now=now,
            evidence=evidence,
            review_expires_at=review_expires_at,
        )
        with self._sf() as session:
            row = session.scalar(
                select(V2ManufacturerCapabilityProfile)
                .where(
                    V2ManufacturerCapabilityProfile.manufacturer_id == manufacturer_id
                )
                .with_for_update()
            )
            if row is None:
                raise ManufacturerCapabilityError("capability profile not found")
            previous = row.status
            conflict_resolution = "not_applicable"
            if to_status == "verified":
                try:
                    submission_snapshot = load_snapshot(
                        session,
                        resource_type="manufacturer_capability",
                        resource_ref=manufacturer_id,
                        resource_version=row.version,
                        purpose="capability_submission",
                    )
                    reviewer_snapshot = capture_snapshot(
                        session,
                        subject_ref=actor,
                        roles=actor_roles,
                        captured_at=now,
                        purpose="capability_reviewer",
                        resource_type="manufacturer_capability",
                        resource_ref=manufacturer_id,
                        resource_version=row.version + 1,
                    )
                    resolution = resolve_independence(
                        submission_snapshot,
                        reviewer_snapshot,
                        required_second_role=required_reviewer_role,
                        incompatible_second_roles=incompatible_reviewer_roles,
                    )
                    if not resolution.allowed:
                        raise ManufacturerCapabilityError(
                            "server conflict check blocked capability verification"
                        )
                    record_decision(
                        session,
                        decision_type="capability_verification",
                        resource_type="manufacturer_capability",
                        resource_ref=manufacturer_id,
                        resource_version=row.version + 1,
                        resolution=resolution,
                        created_at=now,
                    )
                    conflict_resolution = resolution.reason_code
                except AffiliationGovernanceError as exc:
                    raise ManufacturerCapabilityError(
                        "human-authoritative conflict resolution is unavailable"
                    ) from exc
            row.status = to_status
            row.evidence_json = list(evidence)
            row.verified_at = now if to_status == "verified" else None
            row.verified_by = actor if to_status == "verified" else None
            row.review_expires_at = (
                review_expires_at if to_status == "verified" else None
            )
            row.updated_at = now
            row.change_reason = note
            row.version += 1
            session.add(
                V2ManufacturerCapabilityReview(
                    manufacturer_id=manufacturer_id,
                    from_status=previous,
                    to_status=to_status,
                    actor=actor,
                    actor_relation=actor_relation,
                    conflict_of_interest=conflict_resolution,
                    note=note,
                    evidence_json=list(evidence),
                    created_at=now,
                )
            )
            session.commit()
            return _to_domain(row, server_governed=to_status == "verified")
