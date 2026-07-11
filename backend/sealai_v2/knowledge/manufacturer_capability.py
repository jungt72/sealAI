"""Manufacturer capability domain contract, independent from billing metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

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
        now: str,
    ) -> ManufacturerCapabilityProfile: ...

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
    ) -> ManufacturerCapabilityProfile: ...


class InProcessManufacturerCapabilityStore:
    def __init__(
        self, profiles: tuple[ManufacturerCapabilityProfile, ...] = ()
    ) -> None:
        self._profiles = {profile.manufacturer_id: profile for profile in profiles}
        self.events: list[dict] = []

    def get(self, manufacturer_id: str) -> ManufacturerCapabilityProfile | None:
        return self._profiles.get(manufacturer_id)

    def list_all(self) -> tuple[ManufacturerCapabilityProfile, ...]:
        return tuple(
            sorted(self._profiles.values(), key=lambda item: item.company_name)
        )

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
        previous = self._profiles.get(profile.manufacturer_id)
        submitted = replace(
            profile,
            status="submitted",
            submitted_at=now,
            updated_at=now,
            verified_at="",
            verified_by="",
            review_expires_at="",
            evidence=(),
            version=(previous.version + 1 if previous else 1),
        )
        self._profiles[profile.manufacturer_id] = submitted
        self.events.append(
            {
                "manufacturer_id": profile.manufacturer_id,
                "from_status": previous.status if previous else "unsubmitted",
                "to_status": "submitted",
                "actor": actor,
                "actor_relation": "manufacturer",
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
        actor_relation: str,
        now: str,
        note: str = "",
        evidence: tuple[dict, ...] = (),
        review_expires_at: str = "",
        conflict_of_interest: str = "not_assessed",
        reviewer_manufacturer_id: str = "",
    ) -> ManufacturerCapabilityProfile:
        profile = self._profiles.get(manufacturer_id)
        if profile is None:
            raise ManufacturerCapabilityError("capability profile not found")
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
        self.events.append(
            {
                "manufacturer_id": manufacturer_id,
                "from_status": profile.status,
                "to_status": to_status,
                "actor": actor,
                "actor_relation": actor_relation,
                "note": note,
                "evidence": list(evidence),
                "conflict_of_interest": conflict_of_interest,
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
    conflict_of_interest: str,
) -> None:
    if to_status not in REVIEW_STATUSES:
        raise ManufacturerCapabilityError(f"invalid review status: {to_status}")
    if not actor.strip() or not actor_relation.strip():
        raise ManufacturerCapabilityError("review actor and relation are required")
    if to_status == "verified":
        if actor_relation != "independent_reviewer":
            raise ManufacturerCapabilityError("a manufacturer cannot self-verify")
        if conflict_of_interest != "none_declared":
            raise ManufacturerCapabilityError(
                "verification requires a no-conflict attestation"
            )
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
