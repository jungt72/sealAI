"""Postgres adapter for independently reviewed manufacturer capabilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import (
    V2ManufacturerCapabilityProfile,
    V2ManufacturerCapabilityReview,
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


def _to_domain(row: V2ManufacturerCapabilityProfile) -> ManufacturerCapabilityProfile:
    values = {
        field: tuple(getattr(row, f"{field}_json") or ()) for field in _LIST_FIELDS
    }
    return ManufacturerCapabilityProfile(
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
            return _to_domain(row) if row is not None else None

    def list_all(self) -> tuple[ManufacturerCapabilityProfile, ...]:
        with self._sf() as session:
            rows = session.scalars(
                select(V2ManufacturerCapabilityProfile).order_by(
                    V2ManufacturerCapabilityProfile.company_name
                )
            ).all()
            return tuple(_to_domain(row) for row in rows)

    def submit(
        self,
        profile: ManufacturerCapabilityProfile,
        *,
        actor: str,
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
                    conflict_of_interest="not_applicable",
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
        actor_relation: str,
        now: str,
        note: str = "",
        evidence: tuple[dict, ...] = (),
        review_expires_at: str = "",
        conflict_of_interest: str = "not_assessed",
        reviewer_manufacturer_id: str = "",
    ) -> ManufacturerCapabilityProfile:
        if reviewer_manufacturer_id and reviewer_manufacturer_id == manufacturer_id:
            raise ManufacturerCapabilityError("a manufacturer cannot self-verify")
        _validate_review(
            to_status=to_status,
            actor=actor,
            actor_relation=actor_relation,
            now=now,
            evidence=evidence,
            review_expires_at=review_expires_at,
            conflict_of_interest=conflict_of_interest,
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
                    conflict_of_interest=conflict_of_interest,
                    note=note,
                    evidence_json=list(evidence),
                    created_at=now,
                )
            )
            session.commit()
            return _to_domain(row)
