from __future__ import annotations

import pytest
from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.hersteller_partner import PostgresPartnerRegistry
from sealai_v2.db.manufacturer_capability import (
    PostgresManufacturerCapabilityStore,
)
from sealai_v2.db.models import (
    V2GovernanceDecision,
    V2GovernanceSnapshot,
    V2ManufacturerCapabilityReview,
)
from sealai_v2.knowledge.hersteller_partner import HerstellerPartner
from sealai_v2.knowledge.manufacturer_capability import (
    InProcessManufacturerCapabilityStore,
    ManufacturerCapabilityError,
    ManufacturerCapabilityProfile,
)
from sealai_v2.knowledge.verified_partner_registry import (
    VerifiedCapabilityPartnerRegistry,
)
from sealai_v2.tests.affiliation_fixtures import affiliation, persist_affiliations

NOW = "2026-07-11T20:00:00Z"
EXPIRY = "2027-07-11T20:00:00Z"


def _records(*, reviewer_org: str = "reviewer-org"):
    return (
        affiliation("manufacturer-user", "acme"),
        affiliation("reviewer-user", reviewer_org),
    )


def _store(*, reviewer_org: str = "reviewer-org"):
    return InProcessManufacturerCapabilityStore(
        affiliation_records=_records(reviewer_org=reviewer_org)
    )


def _submit(store):
    return store.submit(
        _profile(),
        actor="manufacturer-user",
        actor_roles=("manufacturer",),
        now=NOW,
    )


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
    store = _store()
    submitted = _submit(store)

    assert submitted.status == "submitted"
    assert not submitted.is_verified()
    with pytest.raises(ManufacturerCapabilityError, match="self-verify"):
        store.review(
            "acme",
            to_status="verified",
            actor="manufacturer-user",
            actor_roles=("manufacturer",),
            actor_relation="manufacturer",
            now=NOW,
            evidence=({"citation": "datasheet"},),
            review_expires_at=EXPIRY,
        )


def test_independent_review_creates_time_bounded_verified_profile() -> None:
    store = _store()
    _submit(store)
    verified = store.review(
        "acme",
        to_status="verified",
        actor="reviewer-user",
        actor_roles=("capability_reviewer",),
        actor_relation="independent_reviewer",
        now=NOW,
        evidence=({"citation": "audit report", "document_version": 1},),
        review_expires_at=EXPIRY,
    )

    assert verified.is_verified()
    assert verified.verified_by == "reviewer-user"
    assert [event["to_status"] for event in store.events] == [
        "submitted",
        "verified",
    ]
    assert store.events[-1]["conflict_resolution"] == "no_shared_affiliation"
    assert len(store.events[-1]["reviewer_snapshot_sha256"]) == 64


def test_verification_rejects_empty_evidence_objects() -> None:
    store = _store()
    _submit(store)

    with pytest.raises(ManufacturerCapabilityError, match="citation"):
        store.review(
            "acme",
            to_status="verified",
            actor="reviewer-user",
            actor_roles=("capability_reviewer",),
            actor_relation="independent_reviewer",
            now=NOW,
            evidence=({},),
            review_expires_at=EXPIRY,
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
    persist_affiliations(sf, *_records())
    capabilities.submit(
        _profile(),
        actor="manufacturer-user",
        actor_roles=("manufacturer",),
        now=NOW,
    )
    capabilities.review(
        "acme",
        to_status="verified",
        actor="reviewer-user",
        actor_roles=("capability_reviewer",),
        actor_relation="independent_reviewer",
        now=NOW,
        evidence=({"citation": "audit report"},),
        review_expires_at=EXPIRY,
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
        assert len(session.scalars(select(V2GovernanceSnapshot)).all()) == 2
        decisions = session.scalars(select(V2GovernanceDecision)).all()
        assert [(item.outcome, item.reason_code) for item in decisions] == [
            ("allow", "no_shared_affiliation")
        ]

    with sf() as session:
        decision = session.scalar(select(V2GovernanceDecision))
        assert decision is not None
        decision.resource_version += 1
        session.commit()
    stale_projection = capabilities.get("acme")
    assert stale_projection is not None
    assert stale_projection.status == "quarantined"


def test_verification_requires_future_expiry_and_server_resolved_independence() -> None:
    store = _store(reviewer_org="acme")
    _submit(store)

    with pytest.raises(ManufacturerCapabilityError, match="server conflict"):
        store.review(
            "acme",
            to_status="verified",
            actor="reviewer-user",
            actor_roles=("capability_reviewer",),
            actor_relation="independent_reviewer",
            now=NOW,
            evidence=({"citation": "audit report"},),
            review_expires_at=EXPIRY,
        )

    store = _store()
    _submit(store)
    with pytest.raises(ManufacturerCapabilityError, match="future"):
        store.review(
            "acme",
            to_status="verified",
            actor="reviewer-user",
            actor_roles=("capability_reviewer",),
            actor_relation="independent_reviewer",
            now=NOW,
            evidence=({"citation": "audit report"},),
            review_expires_at=NOW,
        )


def test_legacy_verified_profile_without_server_decision_is_quarantined_on_read() -> (
    None
):
    legacy = ManufacturerCapabilityProfile(
        **{
            **_profile().__dict__,
            "status": "verified",
            "evidence": ({"citation": "legacy audit"},),
            "verified_at": NOW,
            "verified_by": "legacy-reviewer",
            "review_expires_at": EXPIRY,
            "version": 7,
        }
    )
    store = InProcessManufacturerCapabilityStore(
        profiles=(legacy,), affiliation_records=_records()
    )

    projected = store.get("acme")

    assert projected is not None
    assert projected.status == "quarantined"
    assert not projected.is_verified()


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
