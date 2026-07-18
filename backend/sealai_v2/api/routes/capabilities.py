"""Submission and independent review of manufacturer capability profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    get_capability_store,
    get_settings,
    require_admin,
    require_capability_reviewer,
    require_manufacturer,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.knowledge.manufacturer_capability import (
    ManufacturerCapabilityError,
    ManufacturerCapabilityProfile,
)

router = APIRouter(prefix="/api/v2", tags=["manufacturer-capabilities"])


class CapabilityContact(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)


class CapabilitySubmission(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    regions: list[str] = Field(default_factory=list)
    contacts: list[CapabilityContact] = Field(default_factory=list)
    seal_types: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    compounds: list[str] = Field(default_factory=list)
    size_ranges: list[str] = Field(default_factory=list)
    manufacturing_processes: list[str] = Field(default_factory=list)
    tolerances: list[str] = Field(default_factory=list)
    special_capabilities: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    test_capabilities: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    application_limits: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    change_reason: str = ""


class CapabilityReview(BaseModel):
    to_status: Literal["verified", "quarantined", "expired", "rejected"]
    note: str = ""
    evidence: list[dict] = Field(default_factory=list)
    review_expires_at: str = ""
    conflict_of_interest: Literal["none_declared", "connected", "unknown"]


def _profile_dict(profile: ManufacturerCapabilityProfile) -> dict:
    return {
        "manufacturer_id": profile.manufacturer_id,
        "company_name": profile.company_name,
        "status": profile.status,
        "regions": list(profile.regions),
        "contacts": [dict(contact) for contact in profile.contacts],
        "seal_types": list(profile.seal_types),
        "materials": list(profile.materials),
        "compounds": list(profile.compounds),
        "size_ranges": list(profile.size_ranges),
        "manufacturing_processes": list(profile.manufacturing_processes),
        "tolerances": list(profile.tolerances),
        "special_capabilities": list(profile.special_capabilities),
        "industries": list(profile.industries),
        "certificates": list(profile.certificates),
        "test_capabilities": list(profile.test_capabilities),
        "approvals": list(profile.approvals),
        "documents": list(profile.documents),
        "services": list(profile.services),
        "application_limits": list(profile.application_limits),
        "exclusions": list(profile.exclusions),
        "evidence": list(profile.evidence),
        "submitted_at": profile.submitted_at,
        "updated_at": profile.updated_at,
        "verified_at": profile.verified_at,
        "verified_by": profile.verified_by,
        "review_expires_at": profile.review_expires_at,
        "change_reason": profile.change_reason,
        "version": profile.version,
    }


def _require_capability_profiles(settings: Settings) -> None:
    if not settings.capability_profiles_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "product_mode_unavailable",
                "mode": "capability_profiles",
                "maturity": "pilot_not_activated",
            },
        )


@router.get("/partner/me/capability")
def get_own_capability(
    identity: VerifiedIdentity = Depends(require_manufacturer),
    store=Depends(get_capability_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_capability_profiles(settings)
    profile = store.get(identity.hersteller_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="kein Fähigkeitsprofil angelegt")
    return _profile_dict(profile)


@router.put("/partner/me/capability")
def submit_own_capability(
    body: CapabilitySubmission,
    identity: VerifiedIdentity = Depends(require_manufacturer),
    store=Depends(get_capability_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_capability_profiles(settings)
    now = datetime.now(timezone.utc).isoformat()
    profile = ManufacturerCapabilityProfile(
        manufacturer_id=identity.hersteller_id,
        company_name=body.company_name,
        regions=tuple(body.regions),
        contacts=tuple(contact.model_dump() for contact in body.contacts),
        seal_types=tuple(body.seal_types),
        materials=tuple(body.materials),
        compounds=tuple(body.compounds),
        size_ranges=tuple(body.size_ranges),
        manufacturing_processes=tuple(body.manufacturing_processes),
        tolerances=tuple(body.tolerances),
        special_capabilities=tuple(body.special_capabilities),
        industries=tuple(body.industries),
        certificates=tuple(body.certificates),
        test_capabilities=tuple(body.test_capabilities),
        approvals=tuple(body.approvals),
        documents=tuple(body.documents),
        services=tuple(body.services),
        application_limits=tuple(body.application_limits),
        exclusions=tuple(body.exclusions),
        change_reason=body.change_reason,
    )
    try:
        submitted = store.submit(profile, actor=identity.subject, now=now)
    except ManufacturerCapabilityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profile_dict(submitted)


@router.get("/admin/manufacturer-capabilities")
def list_capabilities(
    _: VerifiedIdentity = Depends(require_admin),
    store=Depends(get_capability_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_capability_profiles(settings)
    return {"profiles": [_profile_dict(profile) for profile in store.list_all()]}


@router.post("/admin/manufacturer-capabilities/{manufacturer_id}/review")
def review_capability(
    manufacturer_id: str,
    body: CapabilityReview,
    identity: VerifiedIdentity = Depends(require_capability_reviewer),
    store=Depends(get_capability_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    _require_capability_profiles(settings)
    if identity.hersteller_id and identity.hersteller_id == manufacturer_id:
        raise HTTPException(
            status_code=403,
            detail="a manufacturer cannot review its own capability profile",
        )
    try:
        reviewed = store.review(
            manufacturer_id,
            to_status=body.to_status,
            actor=identity.subject,
            actor_relation="independent_reviewer",
            now=datetime.now(timezone.utc).isoformat(),
            note=body.note,
            evidence=tuple(body.evidence),
            review_expires_at=body.review_expires_at,
            conflict_of_interest=body.conflict_of_interest,
            reviewer_manufacturer_id=identity.hersteller_id,
        )
    except ManufacturerCapabilityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profile_dict(reviewed)
