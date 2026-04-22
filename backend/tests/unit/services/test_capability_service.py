from __future__ import annotations

import inspect
from datetime import date

import pytest
import sqlalchemy as sa

from app.services import capability_service as service_module
from app.services.capability_service import (
    CapabilityClaimCreate,
    CapabilityClaimUpdate,
    CapabilityService,
    CapabilityValidationError,
)


@pytest.fixture
def db():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        _create_schema(conn)
        _seed_profiles(conn)
    with engine.begin() as conn:
        yield conn


@pytest.fixture
def service() -> CapabilityService:
    return CapabilityService()


def _create_schema(conn) -> None:
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


def _seed_profiles(conn) -> None:
    rows = [
        ("mfr-a", "Alpha Seals GmbH", "Alpha Seals", "alpha-seals", "DE", "small", "active"),
        ("mfr-b", "Beta Seals GmbH", "Beta Seals", "beta-seals", "DE", "medium", "active"),
        ("mfr-c", "Gamma Seals GmbH", "Gamma Seals", "gamma-seals", "DE", "small", "active"),
    ]
    for row in rows:
        conn.execute(
            sa.text(
                """
                INSERT INTO manufacturer_profiles (
                    manufacturer_id, legal_name, display_name, slug, country,
                    size_category, account_status
                ) VALUES (
                    :manufacturer_id, :legal_name, :display_name, :slug,
                    :country, :size_category, :account_status
                )
                """
            ),
            {
                "manufacturer_id": row[0],
                "legal_name": row[1],
                "display_name": row[2],
                "slug": row[3],
                "country": row[4],
                "size_category": row[5],
                "account_status": row[6],
            },
        )


def _base_claim(**overrides) -> CapabilityClaimCreate:
    values = {
        "claim_id": "claim-base",
        "manufacturer_id": "mfr-a",
        "capability_type": "material_expertise",
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_glass_filled",
        "capability_payload": {"scope": "ptfe_rwdr"},
        "source_type": "self_declared",
        "source_reference": "test:base",
        "confidence": 4,
        "validity_from": date(2026, 4, 20),
        "status": "active",
    }
    values.update(overrides)
    return CapabilityClaimCreate(**values)


def _lot_claim(claim_id: str, manufacturer_id: str, **overrides) -> CapabilityClaimCreate:
    values = {
        "claim_id": claim_id,
        "manufacturer_id": manufacturer_id,
        "capability_type": "lot_size_capability",
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_glass_filled",
        "capability_payload": {"lot": "capability"},
        "source_type": "self_declared",
        "source_reference": f"test:{claim_id}",
        "confidence": 4,
        "validity_from": date(2026, 4, 20),
        "status": "active",
        "minimum_order_pieces": 1,
        "typical_minimum_pieces": 4,
        "maximum_order_pieces": 100,
        "preferred_batch_min_pieces": 1,
        "preferred_batch_max_pieces": 10,
        "accepts_single_pieces": True,
    }
    values.update(overrides)
    return CapabilityClaimCreate(**values)


def _seed_claims(service: CapabilityService, db) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-material-a", manufacturer_id="mfr-a"))
    service.create_claim(db, _base_claim(claim_id="claim-material-b", manufacturer_id="mfr-b", sealing_material_family="elastomer_fkm"))
    service.create_claim(db, _base_claim(claim_id="claim-geometry-a", manufacturer_id="mfr-a", capability_type="geometry_range", source_reference="test:geometry"))
    service.create_claim(db, _lot_claim("claim-single-a", "mfr-a", minimum_order_pieces=1, typical_minimum_pieces=4, maximum_order_pieces=100, accepts_single_pieces=True))
    service.create_claim(db, _lot_claim("claim-single-b", "mfr-b", minimum_order_pieces=1, typical_minimum_pieces=8, maximum_order_pieces=20, accepts_single_pieces=True))
    service.create_claim(db, _lot_claim("claim-min-25", "mfr-c", minimum_order_pieces=25, typical_minimum_pieces=50, maximum_order_pieces=500, accepts_single_pieces=False))
    service.create_claim(db, _lot_claim("claim-max-5", "mfr-a", minimum_order_pieces=1, typical_minimum_pieces=2, maximum_order_pieces=5, accepts_single_pieces=True, source_reference="test:max5"))
    service.create_claim(db, _lot_claim("claim-draft-single", "mfr-c", status="draft", source_reference="test:draft"))


def test_create_claim_success(service: CapabilityService, db) -> None:
    claim = service.create_claim(db, _base_claim())

    assert claim.claim_id == "claim-base"
    assert claim.manufacturer_id == "mfr-a"
    assert claim.status == "active"
    assert claim.capability_payload == {"scope": "ptfe_rwdr"}
    assert claim.atex_capable is None


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("manufacturer_id", "", "manufacturer_id is required"),
        ("capability_type", "", "capability_type is required"),
        ("source_type", "", "source_type is required"),
        ("source_reference", "", "source_reference is required"),
        ("confidence", 0, "confidence must be between"),
        ("confidence", 6, "confidence must be between"),
        ("capability_type", "marketing_superiority", "unknown capability_type"),
        ("source_type", "web_scraped_guess", "unknown source_type"),
        ("status", "approved", "unknown status"),
        ("validity_to", date(2020, 1, 1), "validity_to must be"),
    ],
)
def test_create_claim_invalid_input(
    service: CapabilityService,
    db,
    field_name: str,
    bad_value,
    message: str,
) -> None:
    with pytest.raises(CapabilityValidationError, match=message):
        service.create_claim(db, _base_claim(**{field_name: bad_value}))


def test_create_lot_size_claim_requires_small_quantity_fields(
    service: CapabilityService,
    db,
) -> None:
    with pytest.raises(CapabilityValidationError, match="lot_size_capability requires"):
        service.create_claim(
            db,
            _base_claim(
                claim_id="claim-bad-lot",
                capability_type="lot_size_capability",
                source_reference="test:bad-lot",
            ),
        )


def test_get_claim_success(service: CapabilityService, db) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-get"))

    claim = service.get_claim(db, "claim-get")

    assert claim is not None
    assert claim.claim_id == "claim-get"


def test_get_claim_missing_returns_none(service: CapabilityService, db) -> None:
    assert service.get_claim(db, "missing-claim") is None


def test_list_claims_by_manufacturer(service: CapabilityService, db) -> None:
    _seed_claims(service, db)

    claims = service.list_claims(db, manufacturer_id="mfr-a")

    assert {claim.claim_id for claim in claims} == {
        "claim-geometry-a",
        "claim-material-a",
        "claim-single-a",
        "claim-max-5",
    }


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        ({"engineering_path": "rwdr"}, {"claim-material-a", "claim-material-b", "claim-geometry-a", "claim-single-a", "claim-single-b", "claim-min-25", "claim-max-5", "claim-draft-single"}),
        ({"sealing_material_family": "elastomer_fkm"}, {"claim-material-b"}),
        ({"capability_type": "geometry_range"}, {"claim-geometry-a"}),
        ({"status": "draft"}, {"claim-draft-single"}),
        ({"manufacturer_id": "mfr-a", "capability_type": "lot_size_capability"}, {"claim-single-a", "claim-max-5"}),
        ({"engineering_path": "static"}, set()),
    ],
)
def test_list_claims_filtered(
    service: CapabilityService,
    db,
    filters: dict[str, str],
    expected_ids: set[str],
) -> None:
    _seed_claims(service, db)

    claims = service.list_claims(db, **filters)

    assert {claim.claim_id for claim in claims} == expected_ids


def test_create_claim_persists_atex_capability_flag(
    service: CapabilityService,
    db,
) -> None:
    claim = service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-create",
            capability_type="certification",
            source_reference="atex:cert:create",
            atex_capable=True,
        ),
    )

    assert claim.atex_capable is True


def test_update_claim_can_set_atex_capability_flag(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-atex-update"))

    updated = service.update_claim(
        db,
        "claim-atex-update",
        CapabilityClaimUpdate(atex_capable=True),
    )

    assert updated is not None
    assert updated.atex_capable is True


def test_list_claims_filters_atex_capable_true(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-yes",
            capability_type="certification",
            source_reference="atex:yes",
            atex_capable=True,
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-no",
            source_reference="atex:no",
            atex_capable=False,
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-unknown",
            source_reference="atex:unknown",
        ),
    )

    claims = service.list_claims(db, atex_capable=True)

    assert {claim.claim_id for claim in claims} == {"claim-atex-yes"}


def test_list_claims_filters_atex_capable_false(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-false",
            source_reference="atex:false",
            atex_capable=False,
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-null",
            source_reference="atex:null",
        ),
    )

    claims = service.list_claims(db, atex_capable=False)

    assert {claim.claim_id for claim in claims} == {"claim-atex-false"}


def test_list_claims_combines_atex_with_status_path_material(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-active-rwdr",
            capability_type="certification",
            source_reference="atex:active-rwdr",
            atex_capable=True,
            status="active",
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-draft-rwdr",
            capability_type="certification",
            source_reference="atex:draft-rwdr",
            atex_capable=True,
            status="draft",
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-active-static",
            capability_type="certification",
            source_reference="atex:active-static",
            atex_capable=True,
            status="active",
            engineering_path="static",
        ),
    )

    claims = service.list_claims(
        db,
        atex_capable=True,
        status="active",
        engineering_path="rwdr",
        sealing_material_family="ptfe_glass_filled",
    )

    assert {claim.claim_id for claim in claims} == {"claim-atex-active-rwdr"}


def test_get_claim_returns_atex_capability_false(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-get-false",
            source_reference="atex:get-false",
            atex_capable=False,
        ),
    )

    claim = service.get_claim(db, "claim-atex-get-false")

    assert claim is not None
    assert claim.atex_capable is False


def test_update_claim_can_set_atex_capability_false(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-update-false",
            source_reference="atex:update-false",
            atex_capable=True,
        ),
    )

    updated = service.update_claim(
        db,
        "claim-atex-update-false",
        CapabilityClaimUpdate(atex_capable=False),
    )

    assert updated is not None
    assert updated.atex_capable is False


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        ({"manufacturer_id": "mfr-a", "atex_capable": True}, {"claim-atex-mfr-a"}),
        (
            {"capability_type": "certification", "atex_capable": True},
            {"claim-atex-mfr-a", "claim-atex-mfr-b", "claim-atex-static", "claim-atex-fkm"},
        ),
        ({"engineering_path": "static", "atex_capable": True}, {"claim-atex-static"}),
        ({"sealing_material_family": "elastomer_fkm", "atex_capable": True}, {"claim-atex-fkm"}),
    ],
)
def test_list_claims_atex_filter_composes_with_core_filters(
    service: CapabilityService,
    db,
    filters: dict[str, object],
    expected_ids: set[str],
) -> None:
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-mfr-a",
            manufacturer_id="mfr-a",
            capability_type="certification",
            source_reference="atex:mfr-a",
            atex_capable=True,
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-mfr-b",
            manufacturer_id="mfr-b",
            capability_type="certification",
            source_reference="atex:mfr-b",
            atex_capable=True,
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-static",
            manufacturer_id="mfr-c",
            capability_type="certification",
            engineering_path="static",
            source_reference="atex:static",
            atex_capable=True,
        ),
    )
    service.create_claim(
        db,
        _base_claim(
            claim_id="claim-atex-fkm",
            manufacturer_id="mfr-c",
            capability_type="certification",
            sealing_material_family="elastomer_fkm",
            source_reference="atex:fkm",
            atex_capable=True,
        ),
    )

    claims = service.list_claims(db, **filters)

    assert {claim.claim_id for claim in claims} == expected_ids


def test_update_claim_success(service: CapabilityService, db) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-update", status="draft"))

    updated = service.update_claim(
        db,
        "claim-update",
        CapabilityClaimUpdate(
            status="active",
            confidence=5,
            capability_payload={"updated": True},
        ),
    )

    assert updated is not None
    assert updated.status == "active"
    assert updated.confidence == 5
    assert updated.capability_payload == {"updated": True}


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        (CapabilityClaimUpdate(confidence=8), "confidence must be between"),
        (CapabilityClaimUpdate(status="approved"), "unknown status"),
        (CapabilityClaimUpdate(source_type="crawler"), "unknown source_type"),
        (CapabilityClaimUpdate(capability_type="ranking_claim"), "unknown capability_type"),
        (CapabilityClaimUpdate(minimum_order_pieces=0), "minimum_order_pieces must be positive"),
        (CapabilityClaimUpdate(minimum_order_pieces=5, accepts_single_pieces=True), "accepts_single_pieces requires"),
    ],
)
def test_update_claim_invalid_input(
    service: CapabilityService,
    db,
    patch: CapabilityClaimUpdate,
    message: str,
) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-update-invalid"))

    with pytest.raises(CapabilityValidationError, match=message):
        service.update_claim(db, "claim-update-invalid", patch)


def test_update_claim_missing_returns_none(service: CapabilityService, db) -> None:
    updated = service.update_claim(db, "missing-claim", CapabilityClaimUpdate(status="active"))

    assert updated is None


def test_update_claim_empty_patch_returns_current_claim(service: CapabilityService, db) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-empty-update"))

    updated = service.update_claim(db, "claim-empty-update", CapabilityClaimUpdate())

    assert updated is not None
    assert updated.claim_id == "claim-empty-update"


def test_delete_claim_success(service: CapabilityService, db) -> None:
    service.create_claim(db, _base_claim(claim_id="claim-delete"))

    assert service.delete_claim(db, "claim-delete") is True
    assert service.get_claim(db, "claim-delete") is None


def test_delete_claim_missing_returns_false(service: CapabilityService, db) -> None:
    assert service.delete_claim(db, "missing-claim") is False


def test_hard_filter_accepts_single_pieces_true_for_small_quantity(
    service: CapabilityService,
    db,
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(db, quantity_requested=1)

    assert {claim.claim_id for claim in claims} == {
        "claim-max-5",
        "claim-single-a",
        "claim-single-b",
    }
    assert all(claim.accepts_single_pieces is True for claim in claims)


@pytest.mark.parametrize(
    ("quantity", "expected_ids"),
    [
        (1, {"claim-max-5", "claim-single-a", "claim-single-b"}),
        (4, {"claim-max-5", "claim-single-a", "claim-single-b"}),
        (6, {"claim-single-a", "claim-single-b"}),
        (10, {"claim-single-a", "claim-single-b"}),
        (11, {"claim-single-a", "claim-single-b"}),
        (25, {"claim-single-a", "claim-min-25"}),
        (101, {"claim-min-25"}),
        (501, set()),
    ],
)
def test_quantity_filter_cases(
    service: CapabilityService,
    db,
    quantity: int,
    expected_ids: set[str],
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(db, quantity_requested=quantity)

    assert {claim.claim_id for claim in claims} == expected_ids


@pytest.mark.parametrize("bad_quantity", [0, -1])
def test_quantity_filter_rejects_nonpositive_quantity(
    service: CapabilityService,
    db,
    bad_quantity: int,
) -> None:
    with pytest.raises(CapabilityValidationError, match="quantity_requested must be positive"):
        service.filter_claims_for_quantity(db, quantity_requested=bad_quantity)


def test_quantity_filter_excludes_higher_minimum_order(
    service: CapabilityService,
    db,
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(db, quantity_requested=10)

    assert "claim-min-25" not in {claim.claim_id for claim in claims}


def test_quantity_filter_respects_maximum_order(
    service: CapabilityService,
    db,
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(db, quantity_requested=6)

    assert "claim-max-5" not in {claim.claim_id for claim in claims}


def test_quantity_filter_can_filter_by_path_material_and_manufacturer(
    service: CapabilityService,
    db,
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(
        db,
        quantity_requested=4,
        manufacturer_id="mfr-a",
        engineering_path="rwdr",
        sealing_material_family="ptfe_glass_filled",
    )

    assert {claim.claim_id for claim in claims} == {"claim-max-5", "claim-single-a"}


def test_quantity_filter_combines_small_quantity_with_atex_flag(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-yes",
            "mfr-a",
            atex_capable=True,
            source_reference="test:qty-atex-yes",
        ),
    )
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-no",
            "mfr-b",
            atex_capable=False,
            source_reference="test:qty-atex-no",
        ),
    )
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-unknown",
            "mfr-c",
            source_reference="test:qty-atex-unknown",
        ),
    )

    claims = service.filter_claims_for_quantity(
        db,
        quantity_requested=4,
        atex_capable=True,
    )

    assert {claim.claim_id for claim in claims} == {"claim-qty-atex-yes"}
    assert all(claim.accepts_single_pieces is True for claim in claims)


def test_quantity_filter_combines_atex_with_path_material_status(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-active-rwdr",
            "mfr-a",
            atex_capable=True,
            status="active",
            source_reference="test:qty-atex-active-rwdr",
        ),
    )
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-draft-rwdr",
            "mfr-a",
            atex_capable=True,
            status="draft",
            source_reference="test:qty-atex-draft-rwdr",
        ),
    )
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-active-static",
            "mfr-b",
            atex_capable=True,
            status="active",
            engineering_path="static",
            source_reference="test:qty-atex-active-static",
        ),
    )

    claims = service.filter_claims_for_quantity(
        db,
        quantity_requested=4,
        atex_capable=True,
        status="active",
        engineering_path="rwdr",
        sealing_material_family="ptfe_glass_filled",
    )

    assert {claim.claim_id for claim in claims} == {"claim-qty-atex-active-rwdr"}


def test_quantity_filter_can_select_explicitly_non_atex_claims(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-no-atex",
            "mfr-a",
            atex_capable=False,
            source_reference="test:qty-no-atex",
        ),
    )
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-yes-atex",
            "mfr-b",
            atex_capable=True,
            source_reference="test:qty-yes-atex",
        ),
    )

    claims = service.filter_claims_for_quantity(
        db,
        quantity_requested=4,
        atex_capable=False,
    )

    assert {claim.claim_id for claim in claims} == {"claim-qty-no-atex"}


def test_quantity_filter_atex_still_honors_single_piece_hard_filter(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-small-ok",
            "mfr-a",
            atex_capable=True,
            minimum_order_pieces=1,
            typical_minimum_pieces=4,
            maximum_order_pieces=100,
            accepts_single_pieces=True,
            source_reference="test:qty-atex-small-ok",
        ),
    )
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-min-25",
            "mfr-b",
            atex_capable=True,
            minimum_order_pieces=25,
            typical_minimum_pieces=50,
            maximum_order_pieces=500,
            accepts_single_pieces=False,
            source_reference="test:qty-atex-min-25",
        ),
    )

    claims = service.filter_claims_for_quantity(
        db,
        quantity_requested=4,
        atex_capable=True,
    )

    assert {claim.claim_id for claim in claims} == {"claim-qty-atex-small-ok"}


def test_quantity_filter_atex_can_include_draft_when_status_disabled(
    service: CapabilityService,
    db,
) -> None:
    service.create_claim(
        db,
        _lot_claim(
            "claim-qty-atex-draft",
            "mfr-a",
            atex_capable=True,
            status="draft",
            source_reference="test:qty-atex-draft",
        ),
    )

    claims = service.filter_claims_for_quantity(
        db,
        quantity_requested=4,
        atex_capable=True,
        status=None,
    )

    assert {claim.claim_id for claim in claims} == {"claim-qty-atex-draft"}


def test_quantity_filter_default_status_active_excludes_draft(
    service: CapabilityService,
    db,
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(db, quantity_requested=1)

    assert "claim-draft-single" not in {claim.claim_id for claim in claims}


def test_quantity_filter_can_include_draft_when_status_filter_disabled(
    service: CapabilityService,
    db,
) -> None:
    _seed_claims(service, db)

    claims = service.filter_claims_for_quantity(db, quantity_requested=1, status=None)

    assert "claim-draft-single" in {claim.claim_id for claim in claims}


def test_service_has_no_langgraph_agent_or_fastapi_imports() -> None:
    source = inspect.getsource(service_module)

    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
