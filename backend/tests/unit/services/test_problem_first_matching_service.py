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
