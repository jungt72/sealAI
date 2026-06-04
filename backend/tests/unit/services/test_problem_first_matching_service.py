from app.services.capability_service import ManufacturerCapabilityProfile, NumericRange
from app.services.problem_first_matching_service import ManufacturerCapability, ProblemFirstMatchingService


def test_problem_first_matching_filters_by_case_requirements() -> None:
    matches = ProblemFirstMatchingService().match_manufacturers(
        {"engineering_path": "rwdr", "sealing_material_family": "ptfe_glass_filled", "quantity_requested": 4},
        [
            ManufacturerCapability("a", "engineering_path", {"engineering_path": "rwdr"}),
            ManufacturerCapability("a", "material_expertise", {"sealing_material_family": "ptfe_glass_filled"}),
            ManufacturerCapability("a", "lot_size_capability", {"minimum_order_pieces": 1, "maximum_order_pieces": 10, "accepts_single_pieces": True}),
            ManufacturerCapability("b", "engineering_path", {"engineering_path": "rwdr"}),
            ManufacturerCapability("b", "material_expertise", {"sealing_material_family": "ptfe_glass_filled"}),
            ManufacturerCapability("b", "lot_size_capability", {"minimum_order_pieces": 100, "accepts_single_pieces": False}),
        ],
    )
    assert [match.manufacturer_id for match in matches] == ["a"]
    assert matches[0].sponsored is False


def test_sponsoring_is_visible_but_never_changes_technical_sort_order() -> None:
    matches = ProblemFirstMatchingService().match_manufacturers(
        {"engineering_path": "rwdr"},
        [
            ManufacturerCapability("sponsored-low", "engineering_path", {"engineering_path": "rwdr"}, technical_score=70, sponsored=True),
            ManufacturerCapability("organic-high", "engineering_path", {"engineering_path": "rwdr"}, technical_score=90, sponsored=False),
        ],
    )

    assert [match.manufacturer_id for match in matches] == ["organic-high", "sponsored-low"]
    assert matches[1].sponsored is True
    assert matches[0].sponsored is False


def test_problem_first_matching_accepts_typed_manufacturer_profiles() -> None:
    service = ProblemFirstMatchingService()
    matches = service.match_manufacturer_profiles(
        {"engineering_path": "rwdr", "sealing_material_family": "ptfe_glass_filled", "quantity_requested": 2, "atex_required": True},
        [
            ManufacturerCapabilityProfile(
                manufacturer_id="complete",
                supported_asset_types=("pump",),
                supported_seal_types=("rwdr",),
                supported_material_families=("ptfe_glass_filled",),
                diameter_range_mm=NumericRange(10, 120, "mm"),
                pressure_range_bar=NumericRange(0, 12, "bar"),
                temperature_range_c=NumericRange(-20, 180, "degC"),
                atex_capable=True,
                small_quantity_capable=True,
                geographic_scope=("DE",),
                response_model="quote_after_engineering_review",
                evidence_level="verified",
            ),
            ManufacturerCapabilityProfile(
                manufacturer_id="missing-atex",
                supported_asset_types=("pump",),
                supported_seal_types=("rwdr",),
                supported_material_families=("ptfe_glass_filled",),
                small_quantity_capable=True,
                atex_capable=False,
                evidence_level="verified",
            ),
        ],
    )

    assert [match.manufacturer_id for match in matches] == ["complete"]
    assert matches[0].capability_coverage.met == (
        "engineering_path",
        "material_expertise",
        "lot_size_capability",
        "certification",
    )
