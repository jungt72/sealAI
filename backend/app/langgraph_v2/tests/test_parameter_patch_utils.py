import pytest

from app.langgraph_v2.utils.parameter_patch import (
    _build_observed_inputs,
    apply_parameter_patch_to_state_layers,
    build_asserted_parameter_patch_from_normalized,
    build_normalized_parameter_patch,
    stage_extracted_parameter_patch,
    stage_parameter_identity_metadata,
    merge_parameters,
    promote_parameter_patch_to_asserted,
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

    assert identity["medium"]["identity_class"] == "identity_confirmed"
    assert identity["medium"]["lookup_allowed"] is True
    assert identity["material"]["identity_class"] == "identity_family_only"
    assert identity["material"]["lookup_allowed"] is False
    assert identity["product_name"]["identity_class"] == "identity_probable"
    assert identity["trade_name"]["identity_class"] == "identity_unresolved"
    assert identity["flange_standard"]["identity_class"] == "identity_confirmed"


# ---------------------------------------------------------------------------
# Regression: observed_inputs capture via stage_extracted_parameter_patch
# ---------------------------------------------------------------------------


def test_stage_extracted_populates_observed_inputs_for_applied_fields() -> None:
    """observed_inputs must record raw values for every newly applied field."""
    merged, prov, identity, applied, observed = stage_extracted_parameter_patch(
        {},
        {"pressure_bar": 120.0, "medium": "Wasser"},
        {},
        {},
        source="frontdoor_extracted",
    )
    assert "pressure_bar" in observed
    assert observed["pressure_bar"]["raw"] == 120.0
    assert observed["pressure_bar"]["source"] == "frontdoor_extracted"
    assert "medium" in observed
    assert observed["medium"]["raw"] == "Wasser"
    assert observed["medium"]["identity_class_at_capture"] == "identity_confirmed"


def test_stage_extracted_observed_inputs_are_append_only() -> None:
    """An earlier observation must never be overwritten by a later extraction."""
    existing_observed = {
        "pressure_bar": {"raw": 80.0, "source": "p1_context_extracted", "identity_class_at_capture": "identity_confirmed"},
    }
    _, _, _, _, observed = stage_extracted_parameter_patch(
        {"pressure_bar": 80.0},
        {"pressure_bar": 120.0, "medium": "Dampf"},
        {},
        {},
        source="frontdoor_extracted",
        existing_observed_inputs=existing_observed,
    )
    # pressure_bar must keep the original observation
    assert observed["pressure_bar"]["raw"] == 80.0
    assert observed["pressure_bar"]["source"] == "p1_context_extracted"
    # medium is new, so it should be captured
    assert observed["medium"]["raw"] == "Dampf"
    assert observed["medium"]["source"] == "frontdoor_extracted"


def test_stage_extracted_observed_inputs_records_identity_class() -> None:
    """identity_class_at_capture must reflect the staging-time classification."""
    _, _, _, _, observed = stage_extracted_parameter_patch(
        {},
        {"material": "PTFE"},
        {},
        {},
        source="frontdoor_extracted",
    )
    assert observed["material"]["identity_class_at_capture"] == "identity_family_only"


def test_stage_extracted_observed_inputs_empty_when_no_fields_applied() -> None:
    """If no fields change, observed_inputs must remain empty."""
    _, _, _, applied, observed = stage_extracted_parameter_patch(
        {"pressure_bar": 120.0},
        {"pressure_bar": 120.0},
        {},
        {},
        source="frontdoor_extracted",
    )
    assert applied == []
    assert observed == {}


def test_observed_inputs_skips_none_values() -> None:
    """None values in the patch should not produce observed_inputs entries."""
    _, _, _, _, observed = stage_extracted_parameter_patch(
        {},
        {"pressure_bar": None, "medium": "Wasser"},
        {},
        {},
        source="frontdoor_extracted",
    )
    assert "pressure_bar" not in observed
    assert "medium" in observed


# ---------------------------------------------------------------------------
# Regression: confirmed inputs pass through contract identity gate
# ---------------------------------------------------------------------------


def test_identity_confirmed_passes_stage_filter() -> None:
    """identity_confirmed fields should always survive the staging pipeline."""
    merged, _, identity, applied, observed = stage_extracted_parameter_patch(
        {},
        {"medium": "Wasser", "pressure_bar": 250.0, "shaft_diameter": 55.0},
        {},
        {},
        source="frontdoor_extracted",
    )
    assert merged["medium"] == "Wasser"
    assert merged["pressure_bar"] == 250.0
    assert identity["medium"]["identity_class"] == "identity_confirmed"
    assert identity["pressure_bar"]["identity_class"] == "identity_confirmed"
    assert "medium" in applied
    assert observed["medium"]["raw"] == "Wasser"


def test_build_normalized_parameter_patch_uses_identity_normalized_values() -> None:
    identity = stage_parameter_identity_metadata(
        {},
        {"medium": "Hydraulikoel", "pressure_bar": 10.0},
        source="user_patch",
    )
    normalized = build_normalized_parameter_patch(
        {"medium": "Hydraulikoel", "pressure_bar": 10.0},
        identity,
        applied_fields=["medium", "pressure_bar"],
    )
    assert normalized["medium"] == "oil"
    assert normalized["pressure_bar"] == 10.0


def test_build_asserted_parameter_patch_from_normalized_blocks_unconfirmed_identity() -> None:
    identity = stage_parameter_identity_metadata({}, {"material": "PTFE"}, source="user_patch")
    asserted = build_asserted_parameter_patch_from_normalized(
        {"material": "PTFE"},
        identity,
        applied_fields=["material"],
    )
    assert asserted == {}


def test_apply_parameter_patch_to_state_layers_keeps_observed_normalized_and_asserted_separate() -> None:
    (
        merged_asserted,
        merged_asserted_provenance,
        merged_versions,
        _merged_updated_at,
        merged_normalized,
        merged_normalized_provenance,
        merged_identity,
        merged_observed_inputs,
        staged_fields,
        asserted_fields,
        rejected_fields,
    ) = apply_parameter_patch_to_state_layers(
        {},
        {},
        {"medium": "Hydraulikoel", "pressure_bar": 12.0, "material": "PTFE"},
        {},
        {},
        {},
        {},
        source="user",
    )

    assert merged_observed_inputs["medium"]["raw"] == "Hydraulikoel"
    assert merged_normalized["medium"] == "oil"
    assert merged_asserted["medium"] == "oil"
    assert merged_observed_inputs["material"]["raw"] == "PTFE"
    assert merged_normalized["material"] == "PTFE"
    assert "material" not in merged_asserted
    assert staged_fields == ["medium", "pressure_bar", "material"]
    assert asserted_fields == ["medium", "pressure_bar"]
    assert merged_asserted_provenance["medium"] == "user"
    assert merged_normalized_provenance["material"] == "user"
    assert merged_versions["pressure_bar"] == 1
    assert merged_identity["material"]["identity_class"] == "identity_family_only"
    assert rejected_fields == []


def test_promote_parameter_patch_to_asserted_direct_path_is_disabled() -> None:
    with pytest.raises(ValueError, match="Direct raw patch promotion"):
        promote_parameter_patch_to_asserted({}, {"pressure_bar": 5}, {}, source="user")
