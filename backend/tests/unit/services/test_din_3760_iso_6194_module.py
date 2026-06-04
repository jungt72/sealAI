from __future__ import annotations

import pytest

from app.services.norm_modules import (
    Din3760Iso6194Module,
    EscalationPolicy,
    NormCheckStatus,
)


def _valid_context(**overrides):
    context = {
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_carbon_filled",
        "shaft_diameter_mm": 40.0,
        "housing_bore_diameter_mm": 62.0,
        "seal_width_mm": 10.0,
        "seal_type": "A",
    }
    context.update(overrides)
    return context


def test_module_identity_and_references_are_stable() -> None:
    module = Din3760Iso6194Module()
    assert module.module_id == "norm_din_3760_iso_6194"
    assert module.version == "1.0.0"
    assert module.references == ("DIN 3760", "ISO 6194")


@pytest.mark.parametrize(
    "context",
    [
        {"engineering_path": "rwdr"},
        {"engineering_path": "RWDR"},
        {"seal_kind": "rwdr"},
        {"seal_kind": "radial_shaft_seal"},
        {"motion_type": "rotary"},
    ],
)
def test_applies_to_true_for_rwdr_or_rotary_contexts(context) -> None:
    assert Din3760Iso6194Module().applies_to(context) is True


@pytest.mark.parametrize(
    "context",
    [
        {"engineering_path": "ms_pump"},
        {"engineering_path": "static"},
        {"motion_type": "linear"},
        {"seal_kind": "o_ring"},
        {},
    ],
)
def test_applies_to_false_for_non_rwdr_contexts(context) -> None:
    assert Din3760Iso6194Module().applies_to(context) is False


def test_required_fields_are_conservative_and_stable() -> None:
    assert Din3760Iso6194Module().required_fields() == [
        "engineering_path",
        "shaft_diameter_mm",
        "housing_bore_diameter_mm",
        "seal_width_mm",
        "seal_type",
    ]


def test_escalation_policy_is_manufacturer_review() -> None:
    assert (
        Din3760Iso6194Module().escalation_policy()
        is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
    )


def test_check_not_applicable_for_static_case() -> None:
    result = Din3760Iso6194Module().check({"engineering_path": "static"})
    assert result.status is NormCheckStatus.NOT_APPLICABLE
    assert result.applies is False
    assert result.escalation is EscalationPolicy.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "field",
    [
        "engineering_path",
        "shaft_diameter_mm",
        "housing_bore_diameter_mm",
        "seal_width_mm",
        "seal_type",
    ],
)
def test_check_insufficient_data_for_each_missing_required_field(field: str) -> None:
    context = _valid_context()
    if field == "engineering_path":
        context["seal_kind"] = "rwdr"
    context[field] = None
    result = Din3760Iso6194Module().check(context)
    assert result.status is NormCheckStatus.INSUFFICIENT_DATA
    assert result.applies is True
    assert field in result.missing_required_fields
    assert result.escalation is EscalationPolicy.BLOCK_UNTIL_MISSING_FIELDS


@pytest.mark.parametrize(
    "seal_type",
    ["A", "AS", "B", "BS", "C", "CS", "as"],
)
def test_check_passes_basic_known_type_and_positive_geometry(seal_type: str) -> None:
    result = Din3760Iso6194Module().check(_valid_context(seal_type=seal_type))
    assert result.status is NormCheckStatus.PASS
    assert result.applies is True
    assert result.escalation is EscalationPolicy.NO_ESCALATION
    assert any(finding.code == "din_iso_basic_precheck_passed" for finding in result.findings)


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("shaft_diameter_mm", 0, "din_iso_dimension_not_positive"),
        ("shaft_diameter_mm", -1, "din_iso_dimension_not_positive"),
        ("housing_bore_diameter_mm", 0, "din_iso_dimension_not_positive"),
        ("seal_width_mm", 0, "din_iso_dimension_not_positive"),
        ("shaft_diameter_mm", "abc", "din_iso_numeric_field_invalid"),
        ("housing_bore_diameter_mm", "abc", "din_iso_numeric_field_invalid"),
        ("seal_width_mm", "abc", "din_iso_numeric_field_invalid"),
    ],
)
def test_check_fails_invalid_numeric_geometry(field: str, value, expected_code: str) -> None:
    result = Din3760Iso6194Module().check(_valid_context(**{field: value}))
    assert result.status is NormCheckStatus.FAIL
    assert result.escalation is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
    assert any(finding.code == expected_code for finding in result.findings)


def test_check_fails_when_housing_is_not_larger_than_shaft() -> None:
    result = Din3760Iso6194Module().check(
        _valid_context(shaft_diameter_mm=50, housing_bore_diameter_mm=50)
    )
    assert result.status is NormCheckStatus.FAIL
    assert any(
        finding.code == "din_iso_housing_not_larger_than_shaft"
        for finding in result.findings
    )


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({"seal_type": "custom-x"}, "din_iso_unknown_type_designation"),
        ({"pressure_bar": 1.0}, "din_iso_pressure_requires_review"),
        ({"shaft_surface_finish": "grooved"}, "din_iso_counterface_condition_review"),
        ({"shaft_surface_finish": "corroded"}, "din_iso_counterface_condition_review"),
        ({"temperature_c": 300}, "din_iso_temperature_extreme_review"),
        ({"temperature_c": -300}, "din_iso_temperature_extreme_review"),
    ],
)
def test_check_review_required_for_conservative_red_flags(override, expected_code: str) -> None:
    result = Din3760Iso6194Module().check(_valid_context(**override))
    assert result.status is NormCheckStatus.REVIEW_REQUIRED
    assert result.escalation is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
    assert any(finding.code == expected_code for finding in result.findings)


def test_review_findings_can_accumulate_without_becoming_silent_pass() -> None:
    result = Din3760Iso6194Module().check(
        _valid_context(
            seal_type="custom-x",
            pressure_bar=2.0,
            shaft_surface_finish="damaged",
        )
    )
    codes = {finding.code for finding in result.findings}
    assert result.status is NormCheckStatus.REVIEW_REQUIRED
    assert "din_iso_unknown_type_designation" in codes
    assert "din_iso_pressure_requires_review" in codes
    assert "din_iso_counterface_condition_review" in codes


def test_fail_takes_precedence_over_review_findings() -> None:
    result = Din3760Iso6194Module().check(
        _valid_context(
            housing_bore_diameter_mm=30,
            pressure_bar=1.0,
        )
    )
    assert result.status is NormCheckStatus.FAIL
    assert any(
        finding.code == "din_iso_housing_not_larger_than_shaft"
        for finding in result.findings
    )
    assert any(
        finding.code == "din_iso_pressure_requires_review"
        for finding in result.findings
    )
