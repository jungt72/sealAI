from __future__ import annotations

from app.services.capability_service import (
    ManufacturerCapabilityProfile,
    NumericRange,
    PartnerCapabilityProjection,
)
from app.services.manufacturer_fit_matrix_service import (
    PARTNER_NETWORK_DISCLOSURE,
    ManufacturerFitMatrixService,
)


def _profile(
    manufacturer_id: str,
    *,
    seal_types: tuple[str, ...] = ("rwdr",),
    material_families: tuple[str, ...] = ("ptfe_glass_filled",),
    atex_capable: bool | None = True,
    small_quantity_capable: bool | None = True,
    evidence_level: str = "verified",
    open_profile_gaps: tuple[str, ...] = (),
) -> ManufacturerCapabilityProfile:
    return ManufacturerCapabilityProfile(
        manufacturer_id=manufacturer_id,
        supported_asset_types=("pump",),
        supported_seal_types=seal_types,
        supported_material_families=material_families,
        diameter_range_mm=NumericRange(10, 120, "mm"),
        pressure_range_bar=NumericRange(0, 12, "bar"),
        temperature_range_c=NumericRange(-20, 180, "degC"),
        atex_capable=atex_capable,
        small_quantity_capable=small_quantity_capable,
        geographic_scope=("DE",),
        response_model="quote_after_engineering_review",
        evidence_level=evidence_level,
        source_claim_ids=(f"claim-{manufacturer_id}",),
        open_profile_gaps=open_profile_gaps,
    )


def _projection(
    manufacturer_id: str,
    *,
    active_paid: bool = True,
    profile: ManufacturerCapabilityProfile | None = None,
    verification_level: str = "verified",
) -> PartnerCapabilityProjection:
    capability_profile = profile or _profile(manufacturer_id, evidence_level=verification_level)
    return PartnerCapabilityProjection(
        manufacturer_id=manufacturer_id,
        display_name=manufacturer_id.title(),
        account_status="active",
        active_paid=active_paid,
        verification_level=capability_profile.evidence_level,
        capability_profile=capability_profile,
        capability_count=len(capability_profile.source_claim_ids),
        source_claim_ids=capability_profile.source_claim_ids,
        open_profile_gaps=capability_profile.open_profile_gaps,
    )


def _case() -> dict:
    return {
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_glass_filled",
        "quantity_requested": 2,
        "atex_required": True,
    }


def test_unpaid_perfect_partner_is_excluded() -> None:
    matrix = ManufacturerFitMatrixService().compute(
        _case(),
        [
            _projection("unpaid-perfect", active_paid=False),
            _projection("paid-fit", active_paid=True),
        ],
    )

    assert [row.manufacturer_id for row in matrix.rows] == ["paid-fit"]
    assert matrix.eligible_partner_count == 1


def test_active_paid_non_fit_is_not_returned_as_fit_row() -> None:
    matrix = ManufacturerFitMatrixService().compute(
        _case(),
        [
            _projection(
                "paid-non-fit",
                profile=_profile("paid-non-fit", seal_types=("mechanical_seal",)),
            ),
        ],
    )

    assert matrix.status == "no_suitable_partner"
    assert matrix.rows == ()
    assert matrix.no_suitable_partner_reason == "missing:engineering_path"


def test_no_fit_state_is_supported_with_disclosure() -> None:
    matrix = ManufacturerFitMatrixService().compute(_case(), [])

    assert matrix.status == "no_suitable_partner"
    assert matrix.no_suitable_partner_reason == "no_active_paid_partner"
    assert matrix.disclosure == PARTNER_NETWORK_DISCLOSURE


def test_payment_tier_does_not_change_fit_score() -> None:
    low_tier = _projection("same-fit-low-tier")
    high_tier = _projection("same-fit-high-tier")

    matrix = ManufacturerFitMatrixService().compute(_case(), [low_tier, high_tier])

    assert len(matrix.rows) == 2
    assert matrix.rows[0].fit_score == matrix.rows[1].fit_score


def test_fit_matrix_surfaces_reasons_gaps_verification_and_disclosure() -> None:
    matrix = ManufacturerFitMatrixService().compute(
        _case(),
        [_projection("paid-fit", verification_level="documented")],
    )

    assert matrix.status == "fit_computed"
    assert matrix.disclosure == PARTNER_NETWORK_DISCLOSURE
    row = matrix.rows[0]
    assert row.manufacturer_id == "paid-fit"
    assert row.verification_level == "documented"
    assert "seal_type:rwdr" in row.fit_reasons
    assert "material_family:ptfe_glass_filled" in row.fit_reasons
    assert row.gaps == ()
    assert row.missing_requirements == ()
    assert row.source_claim_ids == ("claim-paid-fit",)
