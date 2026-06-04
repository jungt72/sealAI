from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from app.services.capability_service import (
    CapabilityClaimCreate,
    CapabilityService,
)


@pytest.fixture()
def service() -> CapabilityService:
    return CapabilityService()


@pytest.fixture()
def db():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE manufacturer_profiles (
                    manufacturer_id VARCHAR(36) PRIMARY KEY,
                    legal_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    slug VARCHAR(128) NOT NULL UNIQUE,
                    country VARCHAR(2) NOT NULL,
                    website_url TEXT,
                    size_category VARCHAR(32) NOT NULL,
                    account_status VARCHAR(32) NOT NULL DEFAULT 'pending_verification',
                    onboarded_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE manufacturer_capability_claims (
                    claim_id VARCHAR(36) PRIMARY KEY,
                    manufacturer_id VARCHAR(36) NOT NULL,
                    capability_type VARCHAR(64) NOT NULL,
                    engineering_path VARCHAR(64),
                    sealing_material_family VARCHAR(64),
                    capability_payload TEXT NOT NULL DEFAULT '{}',
                    source_type VARCHAR(64) NOT NULL,
                    source_reference TEXT NOT NULL,
                    confidence SMALLINT NOT NULL,
                    validity_from DATE NOT NULL,
                    validity_to DATE,
                    verified_at DATETIME,
                    verified_by VARCHAR(36),
                    status VARCHAR(32) NOT NULL DEFAULT 'draft',
                    minimum_order_pieces INTEGER,
                    typical_minimum_pieces INTEGER,
                    maximum_order_pieces INTEGER,
                    preferred_batch_min_pieces INTEGER,
                    preferred_batch_max_pieces INTEGER,
                    accepts_single_pieces BOOLEAN,
                    atex_capable BOOLEAN,
                    rapid_manufacturing_available BOOLEAN,
                    rapid_manufacturing_surcharge_percent SMALLINT,
                    rapid_manufacturing_leadtime_hours SMALLINT,
                    standard_leadtime_weeks SMALLINT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        yield conn


def _insert_profile(
    db, manufacturer_id: str, *, account_status: str = "active"
) -> None:
    db.execute(
        sa.text(
            """
            INSERT INTO manufacturer_profiles (
                manufacturer_id, legal_name, display_name, slug, country,
                size_category, account_status
            ) VALUES (
                :manufacturer_id, :legal_name, :display_name, :slug,
                'DE', 'small', :account_status
            )
            """
        ),
        {
            "manufacturer_id": manufacturer_id,
            "legal_name": f"{manufacturer_id} GmbH",
            "display_name": manufacturer_id.replace("-", " ").title(),
            "slug": manufacturer_id,
            "account_status": account_status,
        },
    )


def _claim(
    claim_id: str,
    manufacturer_id: str,
    *,
    confidence: int = 4,
    status: str = "active",
    payload: dict | None = None,
) -> CapabilityClaimCreate:
    return CapabilityClaimCreate(
        claim_id=claim_id,
        manufacturer_id=manufacturer_id,
        capability_type="product_family",
        source_type="self_declared",
        source_reference=f"partner:{manufacturer_id}",
        confidence=confidence,
        validity_from=date(2026, 1, 1),
        engineering_path="rwdr",
        sealing_material_family="ptfe_glass_filled",
        status=status,
        capability_payload={
            "supported_asset_types": ["pump"],
            "supported_seal_types": ["rwdr"],
            "supported_material_families": ["ptfe_glass_filled"],
            "diameter_min_mm": 10,
            "diameter_max_mm": 120,
            "pressure_min_bar": 0,
            "pressure_max_bar": 8,
            "temperature_min_degC": -20,
            "temperature_max_degC": 180,
            "geographic_scope": ["DE"],
            "response_model": "quote_after_engineering_review",
            **(payload or {}),
        },
    )


def test_partner_projection_excludes_inactive_manufacturer(
    service: CapabilityService, db
) -> None:
    _insert_profile(db, "inactive-paid", account_status="suspended")
    service.create_claim(
        db,
        _claim(
            "claim-inactive-paid", "inactive-paid", payload={"is_paid_partner": True}
        ),
    )

    assert service.list_partner_capability_projections(db) == []


def test_partner_projection_excludes_unpaid_active_manufacturer(
    service: CapabilityService, db
) -> None:
    _insert_profile(db, "active-unpaid")
    service.create_claim(db, _claim("claim-active-unpaid", "active-unpaid"))

    assert service.list_partner_capability_projections(db) == []


def test_partner_projection_includes_active_paid_manufacturer(
    service: CapabilityService, db
) -> None:
    _insert_profile(db, "active-paid")
    service.create_claim(
        db,
        _claim("claim-active-paid", "active-paid", payload={"is_paid_partner": True}),
    )

    projections = service.list_partner_capability_projections(db)

    assert [item.manufacturer_id for item in projections] == ["active-paid"]
    assert projections[0].active_paid is True
    assert projections[0].capability_profile.supported_seal_types == ("rwdr",)


def test_partner_projection_surfaces_verification_level(
    service: CapabilityService, db
) -> None:
    _insert_profile(db, "verified-paid")
    service.create_claim(
        db,
        _claim(
            "claim-verified-paid",
            "verified-paid",
            confidence=5,
            payload={"partner_network_status": "active_paid"},
        ),
    )

    projection = service.list_partner_capability_projections(db)[0]

    assert projection.verification_level == "verified"
    assert projection.capability_count == 1
    assert projection.source_claim_ids == ("claim-verified-paid",)
