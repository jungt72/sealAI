"""Manufacturer capability domain contract, independent from billing metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from sealai_v2.governance.affiliations import (
    AffiliationGovernanceError,
    AffiliationRecord,
    AffiliationSnapshot,
    capture_affiliation_snapshot,
    require_governed_role,
    resolve_independence,
)

CAPABILITY_STATUSES = frozenset(
    {"draft", "submitted", "verified", "quarantined", "expired", "rejected"}
)
REVIEW_STATUSES = frozenset({"verified", "quarantined", "expired", "rejected"})


class ManufacturerCapabilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManufacturerCapabilityProfile:
    manufacturer_id: str
    company_name: str = ""
    status: str = "draft"
    regions: tuple[str, ...] = ()
    contacts: tuple[dict, ...] = ()
    seal_types: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    compounds: tuple[str, ...] = ()
    size_ranges: tuple[str, ...] = ()
    manufacturing_processes: tuple[str, ...] = ()
    tolerances: tuple[str, ...] = ()
    special_capabilities: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    certificates: tuple[str, ...] = ()
    test_capabilities: tuple[str, ...] = ()
    approvals: tuple[str, ...] = ()
    documents: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    application_limits: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    evidence: tuple[dict, ...] = ()
    submitted_at: str = ""
    updated_at: str = ""
    verified_at: str = ""
    verified_by: str = ""
    review_expires_at: str = ""
    change_reason: str = ""
    version: int = 1

    def is_verified(self, *, now: datetime | None = None) -> bool:
        if self.status != "verified" or not self.evidence or not self.review_expires_at:
            return False
        instant = now or datetime.now(timezone.utc)
        try:
            expiry = datetime.fromisoformat(
                self.review_expires_at.replace("Z", "+00:00")
            )
        except ValueError:
            return False
        if expiry.tzinfo is None:
            return False
        return expiry > instant


class ManufacturerCapabilityStore(Protocol):
    def get(self, manufacturer_id: str) -> ManufacturerCapabilityProfile | None: ...

    def list_all(self) -> tuple[ManufacturerCapabilityProfile, ...]: ...

    def submit(
        self,
        profile: ManufacturerCapabilityProfile,
        *,
        actor: str,
        actor_roles: tuple[str, ...],
        now: str,
    ) -> ManufacturerCapabilityProfile: ...

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
    ) -> ManufacturerCapabilityProfile: ...


class InProcessManufacturerCapabilityStore:
    def __init__(
        self,
        profiles: tuple[ManufacturerCapabilityProfile, ...] = (),
        affiliation_records: tuple[AffiliationRecord, ...] = (),
    ) -> None:
        self._profiles = {profile.manufacturer_id: profile for profile in profiles}
        self._affiliation_records = affiliation_records
        self._snapshots: dict[tuple[str, int, str], AffiliationSnapshot] = {}
        self._verified_versions: set[tuple[str, int]] = set()
        self.events: list[dict] = []

    def _governed_profile(
        self, profile: ManufacturerCapabilityProfile
    ) -> ManufacturerCapabilityProfile:
        if (
            profile.status != "verified"
            or (
                profile.manufacturer_id,
                profile.version,
            )
            in self._verified_versions
        ):
            return profile
        return replace(
            profile,
            status="quarantined",
            verified_at="",
            verified_by="",
            review_expires_at="",
        )

    def _snapshot(
        self,
        *,
        subject_ref: str,
        roles: tuple[str, ...],
        captured_at: str,
        purpose: str,
        manufacturer_id: str,
        version: int,
        expected_organization: str = "",
    ) -> AffiliationSnapshot:
        key = (manufacturer_id, version, purpose)
        existing = self._snapshots.get(key)
        if existing is not None:
            if existing.subject_ref != subject_ref or set(existing.roles) != set(roles):
                raise ManufacturerCapabilityError(
                    "capability version is already bound to another governance actor"
                )
            return existing
        try:
            snapshot = capture_affiliation_snapshot(
                (
                    record
                    for record in self._affiliation_records
                    if record.subject_ref == subject_ref
                ),
                subject_ref=subject_ref,
                roles=roles,
                captured_at=captured_at,
                purpose=purpose,
                resource_type="manufacturer_capability",
                resource_ref=manufacturer_id,
                resource_version=version,
                expected_organization=expected_organization,
            )
        except AffiliationGovernanceError as exc:
            raise ManufacturerCapabilityError(
                "human-authoritative affiliation is unavailable"
            ) from exc
        self._snapshots[key] = snapshot
        return snapshot

    def get(self, manufacturer_id: str) -> ManufacturerCapabilityProfile | None:
        profile = self._profiles.get(manufacturer_id)
        return self._governed_profile(profile) if profile is not None else None

    def list_all(self) -> tuple[ManufacturerCapabilityProfile, ...]:
        return tuple(
            self._governed_profile(profile)
            for profile in sorted(
                self._profiles.values(), key=lambda item: item.company_name
            )
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
        previous = self._profiles.get(profile.manufacturer_id)
        version = previous.version + 1 if previous else 1
        submission_snapshot = self._snapshot(
            subject_ref=actor,
            roles=actor_roles,
            captured_at=now,
            purpose="capability_submission",
            manufacturer_id=profile.manufacturer_id,
            version=version,
            expected_organization=profile.manufacturer_id,
        )
        try:
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
            self._snapshots.pop(
                (profile.manufacturer_id, version, "capability_submission"), None
            )
            raise ManufacturerCapabilityError(
                "manufacturer submission authority is incompatible"
            ) from exc
        submitted = replace(
            profile,
            status="submitted",
            submitted_at=now,
            updated_at=now,
            verified_at="",
            verified_by="",
            review_expires_at="",
            evidence=(),
            version=version,
        )
        self._profiles[profile.manufacturer_id] = submitted
        self.events.append(
            {
                "manufacturer_id": profile.manufacturer_id,
                "from_status": previous.status if previous else "unsubmitted",
                "to_status": "submitted",
                "actor": actor,
                "actor_relation": "manufacturer",
                "submission_snapshot_sha256": submission_snapshot.snapshot_sha256,
                "created_at": now,
            }
        )
        return submitted

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
        profile = self._profiles.get(manufacturer_id)
        if profile is None:
            raise ManufacturerCapabilityError("capability profile not found")
        _validate_review(
            to_status=to_status,
            actor=actor,
            actor_relation=actor_relation,
            now=now,
            evidence=evidence,
            review_expires_at=review_expires_at,
        )
        resolution_reason = "not_applicable"
        reviewer_snapshot_sha256 = ""
        submission_snapshot_sha256 = ""
        if to_status == "verified":
            submission_snapshot = self._snapshots.get(
                (manufacturer_id, profile.version, "capability_submission")
            )
            if submission_snapshot is None:
                raise ManufacturerCapabilityError(
                    "immutable capability submission snapshot is unavailable"
                )
            reviewer_snapshot = self._snapshot(
                subject_ref=actor,
                roles=actor_roles,
                captured_at=now,
                purpose="capability_reviewer",
                manufacturer_id=manufacturer_id,
                version=profile.version + 1,
            )
            resolution = resolve_independence(
                submission_snapshot,
                reviewer_snapshot,
                required_second_role=required_reviewer_role,
                incompatible_second_roles=incompatible_reviewer_roles,
            )
            if not resolution.allowed:
                self._snapshots.pop(
                    (manufacturer_id, profile.version + 1, "capability_reviewer"),
                    None,
                )
                raise ManufacturerCapabilityError(
                    f"server conflict check blocked verification: {resolution.reason_code}"
                )
            resolution_reason = resolution.reason_code
            reviewer_snapshot_sha256 = reviewer_snapshot.snapshot_sha256
            submission_snapshot_sha256 = submission_snapshot.snapshot_sha256
        reviewed = replace(
            profile,
            status=to_status,
            evidence=evidence,
            verified_at=now if to_status == "verified" else "",
            verified_by=actor if to_status == "verified" else "",
            review_expires_at=(review_expires_at if to_status == "verified" else ""),
            updated_at=now,
            change_reason=note,
            version=profile.version + 1,
        )
        self._profiles[manufacturer_id] = reviewed
        if to_status == "verified":
            self._verified_versions.add((manufacturer_id, reviewed.version))
        self.events.append(
            {
                "manufacturer_id": manufacturer_id,
                "from_status": profile.status,
                "to_status": to_status,
                "actor": actor,
                "actor_relation": actor_relation,
                "note": note,
                "evidence": list(evidence),
                "conflict_resolution": resolution_reason,
                "submission_snapshot_sha256": submission_snapshot_sha256,
                "reviewer_snapshot_sha256": reviewer_snapshot_sha256,
                "created_at": now,
            }
        )
        return reviewed


def _validate_review(
    *,
    to_status: str,
    actor: str,
    actor_relation: str,
    now: str,
    evidence: tuple[dict, ...],
    review_expires_at: str,
) -> None:
    if to_status not in REVIEW_STATUSES:
        raise ManufacturerCapabilityError(f"invalid review status: {to_status}")
    if not actor.strip() or not actor_relation.strip():
        raise ManufacturerCapabilityError("review actor and relation are required")
    if to_status == "verified":
        if actor_relation != "independent_reviewer":
            raise ManufacturerCapabilityError("a manufacturer cannot self-verify")
        if not evidence:
            raise ManufacturerCapabilityError("verification requires evidence")
        if not review_expires_at:
            raise ManufacturerCapabilityError("verification requires review expiry")
        for item in evidence:
            if not isinstance(item, dict) or not any(
                str(item.get(key, "")).strip()
                for key in ("citation", "reference", "document_id")
            ):
                raise ManufacturerCapabilityError(
                    "each verification evidence item requires a citation or document reference"
                )
        try:
            expiry = datetime.fromisoformat(review_expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ManufacturerCapabilityError(
                "invalid review expiry timestamp"
            ) from exc
        if expiry.tzinfo is None:
            raise ManufacturerCapabilityError("review expiry must include a timezone")
        try:
            reviewed_at = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ManufacturerCapabilityError("invalid review timestamp") from exc
        if reviewed_at.tzinfo is None:
            raise ManufacturerCapabilityError(
                "review timestamp must include a timezone"
            )
        if expiry <= reviewed_at:
            raise ManufacturerCapabilityError("review expiry must be in the future")
