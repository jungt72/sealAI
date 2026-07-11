from __future__ import annotations

import pytest
from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.hersteller_partner import PostgresPartnerRegistry
from sealai_v2.db.manufacturer_capability import (
    PostgresManufacturerCapabilityStore,
)
from sealai_v2.db.models import V2ManufacturerCapabilityReview
from sealai_v2.knowledge.hersteller_partner import HerstellerPartner
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
    ManufacturerCapabilityError,
    ManufacturerCapabilityProfile,
)
from sealai_v2.knowledge.verified_partner_registry import (
    VerifiedCapabilityPartnerRegistry,
)

NOW = "2026-07-11T20:00:00Z"
EXPIRY = "2027-07-11T20:00:00Z"


def _profile() -> ManufacturerCapabilityProfile:
    return ManufacturerCapabilityProfile(
        manufacturer_id="acme",
        company_name="ACME",
        contacts=(
            {"name": "A. Engineer", "role": "Application", "email": "a@acme.test"},
        ),
        seal_types=("RWDR",),
        materials=("FKM",),
        application_limits=("No oxygen service without separate review",),
        change_reason="initial submission",
    )


def test_manufacturer_submission_cannot_preserve_verified_state() -> None:
    store = InProcessManufacturerCapabilityStore()
    submitted = store.submit(_profile(), actor="manufacturer-user", now=NOW)

    assert submitted.status == "submitted"
    assert not submitted.is_verified()
    with pytest.raises(ManufacturerCapabilityError, match="self-verify"):
        store.review(
            "acme",
            to_status="verified",
            actor="manufacturer-user",
            actor_relation="manufacturer",
            now=NOW,
            evidence=({"citation": "datasheet"},),
            review_expires_at=EXPIRY,
        )


def test_independent_review_creates_time_bounded_verified_profile() -> None:
    store = InProcessManufacturerCapabilityStore()
    store.submit(_profile(), actor="manufacturer-user", now=NOW)
    verified = store.review(
        "acme",
        to_status="verified",
        actor="reviewer-user",
        actor_relation="independent_reviewer",
        now=NOW,
        evidence=({"citation": "audit report", "document_version": 1},),
        review_expires_at=EXPIRY,
        conflict_of_interest="none_declared",
    )

    assert verified.is_verified()
    assert verified.verified_by == "reviewer-user"
    assert [event["to_status"] for event in store.events] == [
        "submitted",
        "verified",
    ]


def test_verification_rejects_empty_evidence_objects() -> None:
    store = InProcessManufacturerCapabilityStore()
    store.submit(_profile(), actor="manufacturer-user", now=NOW)

    with pytest.raises(ManufacturerCapabilityError, match="citation"):
        store.review(
            "acme",
            to_status="verified",
            actor="reviewer-user",
            actor_relation="independent_reviewer",
            now=NOW,
            evidence=({},),
            review_expires_at=EXPIRY,
            conflict_of_interest="none_declared",
        )


def test_technical_pool_does_not_depend_on_commercial_activation(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'capabilities.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    capabilities = PostgresManufacturerCapabilityStore(sf)
    commercial = PostgresPartnerRegistry(sf)
    commercial.upsert(
        HerstellerPartner(
            hersteller="acme",
            firmenname="ACME commercial",
            aktiv=False,
            lead_email="",
            plan="",
        )
    )
    capabilities.submit(_profile(), actor="manufacturer-user", now=NOW)
    capabilities.review(
        "acme",
        to_status="verified",
        actor="reviewer-user",
        actor_relation="independent_reviewer",
        now=NOW,
        evidence=({"citation": "audit report"},),
        review_expires_at=EXPIRY,
        conflict_of_interest="none_declared",
    )

    pool = VerifiedCapabilityPartnerRegistry(capabilities)
    partners = pool.list_active()
    assert [partner.hersteller for partner in partners] == ["acme"]
    assert partners[0].aktiv is True
    assert partners[0].werkstoffe == ("FKM",)
    assert partners[0].lead_email == ""
    assert partners[0].plan == ""
    with sf() as session:
        reviews = session.scalars(
            select(V2ManufacturerCapabilityReview).order_by(
                V2ManufacturerCapabilityReview.id
            )
        ).all()
        assert [(row.from_status, row.to_status) for row in reviews] == [
            ("unsubmitted", "submitted"),
            ("submitted", "verified"),
        ]


def test_verification_requires_future_expiry_and_no_conflict() -> None:
    store = InProcessManufacturerCapabilityStore()
    store.submit(_profile(), actor="manufacturer-user", now=NOW)

    with pytest.raises(ManufacturerCapabilityError, match="no-conflict"):
        store.review(
            "acme",
            to_status="verified",
            actor="reviewer-user",
            actor_relation="independent_reviewer",
            now=NOW,
            evidence=({"citation": "audit report"},),
            review_expires_at=EXPIRY,
            conflict_of_interest="unknown",
        )
    with pytest.raises(ManufacturerCapabilityError, match="future"):
        store.review(
            "acme",
            to_status="verified",
            actor="reviewer-user",
            actor_relation="independent_reviewer",
            now=NOW,
            evidence=({"citation": "audit report"},),
            review_expires_at=NOW,
            conflict_of_interest="none_declared",
        )


def test_corrupt_or_timezone_less_expiry_fails_closed() -> None:
    base = _profile()
    for expiry in ("not-a-date", "2099-07-11T10:00:00"):
        profile = ManufacturerCapabilityProfile(
            **{
                **base.__dict__,
                "status": "verified",
                "evidence": ({"citation": "audit report"},),
                "review_expires_at": expiry,
            }
        )
        assert not profile.is_verified()
