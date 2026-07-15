from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from sealai_v2.db.models import V2IdentityAffiliationRevision
from sealai_v2.governance.affiliations import (
    AffiliationRecord,
    build_affiliation_record,
)
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
    ManufacturerCapabilityProfile,
)


def affiliation(
    subject_ref: str,
    organization_ref: str,
    *,
    relationship: str = "employee",
    revision: int = 1,
    status: str = "active",
) -> AffiliationRecord:
    record_id = sha256(
        f"{subject_ref}|{organization_ref}|{relationship}|{revision}".encode("utf-8")
    ).hexdigest()
    return build_affiliation_record(
        record_id=record_id,
        subject_ref=subject_ref,
        organization_ref=organization_ref,
        relationship=relationship,
        authority_source="owner_attested_identity_roster",
        authority_reference=f"test-roster:{record_id[:16]}",
        authority_version="test-roster-v1",
        effective_from="2020-01-01T00:00:00Z",
        effective_to="",
        status=status,
        revision=revision,
        recorded_at="2026-07-01T00:00:00Z",
        recorded_by="human-authority-owner",
    )


def governed_verified_capability_store(
    *profiles: ManufacturerCapabilityProfile,
) -> InProcessManufacturerCapabilityStore:
    """Build test profiles through the same governed submit/review path as runtime."""

    reviewer = "test-independent-capability-reviewer"
    records = tuple(
        affiliation(
            f"test-manufacturer:{profile.manufacturer_id}", profile.manufacturer_id
        )
        for profile in profiles
    ) + (affiliation(reviewer, "test-independent-review-board"),)
    store = InProcessManufacturerCapabilityStore(affiliation_records=records)
    for profile in profiles:
        manufacturer = f"test-manufacturer:{profile.manufacturer_id}"
        store.submit(
            replace(
                profile,
                status="draft",
                evidence=(),
                submitted_at="",
                updated_at="",
                verified_at="",
                verified_by="",
                review_expires_at="",
                version=1,
            ),
            actor=manufacturer,
            actor_roles=("manufacturer",),
            now="2026-07-15T08:00:00Z",
        )
        store.review(
            profile.manufacturer_id,
            to_status="verified",
            actor=reviewer,
            actor_roles=("capability_reviewer",),
            actor_relation="independent_reviewer",
            now="2026-07-15T09:00:00Z",
            evidence=profile.evidence or ({"citation": "test governance review"},),
            review_expires_at=profile.review_expires_at or "2099-01-01T00:00:00Z",
        )
    return store


def persist_affiliations(session_factory, *records: AffiliationRecord) -> None:
    with session_factory() as session:
        session.add_all(
            [
                V2IdentityAffiliationRevision(
                    id=record.record_id,
                    subject_ref=record.subject_ref,
                    organization_ref=record.organization_ref,
                    relationship=record.relationship,
                    authority_source=record.authority_source,
                    authority_reference=record.authority_reference,
                    authority_version=record.authority_version,
                    effective_from=record.effective_from,
                    effective_to=record.effective_to or None,
                    status=record.status,
                    revision=record.revision,
                    recorded_at=record.recorded_at,
                    recorded_by=record.recorded_by,
                    record_sha256=record.record_sha256,
                )
                for record in records
            ]
        )
        session.commit()
