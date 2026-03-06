import pytest

from app.langgraph_v2.utils.parameter_patch import (
    stage_parameter_identity_metadata,
    merge_parameters,
    sanitize_v2_parameter_patch,
)


def test_sanitize_v2_parameter_patch_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError):
        sanitize_v2_parameter_patch({"unknown_key": 1})


def test_sanitize_v2_parameter_patch_accepts_core_keys_and_primitives() -> None:
    sanitized = sanitize_v2_parameter_patch(
        {
            "pressure_bar": 1.2,
            "temperature_C": 80,
            "speed_rpm": 1500,
            "shaft_diameter": 50,
            "medium": "Hydraulikoel",
        }
    )
    assert sanitized["pressure_bar"] == 1.2
    assert sanitized["temperature_C"] == 80
    assert sanitized["speed_rpm"] == 1500
    assert sanitized["shaft_diameter"] == 50
    assert sanitized["medium"] == "Hydraulikoel"


def test_merge_parameters_merges_instead_of_replacing() -> None:
    existing = {"medium": "Hydraulikoel", "pressure_bar": 10}
    patch = {"temperature_C": 80}
    merged = merge_parameters(existing, patch)
    assert merged["medium"] == "Hydraulikoel"
    assert merged["pressure_bar"] == 10
    assert merged["temperature_C"] == 80


def test_stage_parameter_identity_metadata_classifies_critical_fields() -> None:
    identity = stage_parameter_identity_metadata(
        {},
        {
            "medium": "Wasser",
            "material": "PTFE",
            "product_name": "Kyrolon",
            "trade_name": "Produkt",
            "flange_standard": "EN 1092-1",
        },
        source="frontdoor_extracted",
    )

    assert identity["medium"]["identity_class"] == "confirmed"
    assert identity["medium"]["lookup_allowed"] is True
    assert identity["material"]["identity_class"] == "family_only"
    assert identity["material"]["lookup_allowed"] is False
    assert identity["product_name"]["identity_class"] == "probable"
    assert identity["trade_name"]["identity_class"] == "unresolved"
    assert identity["flange_standard"]["identity_class"] == "confirmed"
