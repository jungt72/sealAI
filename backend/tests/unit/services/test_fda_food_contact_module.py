from __future__ import annotations

import inspect

import pytest

from app.services.norm_modules import (
    EscalationPolicy,
    FdaFoodContactModule,
    NormCheckStatus,
    build_default_registry,
)


def _fda_context(**overrides):
    context = {
        "application_domain": "food processing",
        "food_contact_required": True,
        "food_contact_region": "us",
        "intended_us_market": True,
        "medium_name": "chocolate",
        "sealing_material_family": "ptfe_virgin",
        "material_name": "PTFE virgin FDA grade",
        "temperature_c": 70,
    }
    context.update(overrides)
    return context


@pytest.mark.parametrize(
    "context",
    [
        {"food_contact_required": True, "food_contact_region": "us"},
        {"application_domain": "food processing", "market_region": "USA"},
        {"medium_name": "milk", "jurisdiction": "fda"},
        {"application_category": "pharma", "food_contact_region": "both"},
        {"medium_name": "chocolate", "intended_us_market": True},
    ],
)
def test_fda_applies_to_food_contact_us_contexts(context) -> None:
    assert FdaFoodContactModule().applies_to(context) is True


@pytest.mark.parametrize(
    "context",
    [
        {"application_domain": "chemical", "market_region": "us"},
        {"food_contact_required": False, "medium_name": "hydraulic oil", "market_region": "us"},
        {"application_domain": "food processing", "food_contact_region": "eu"},
    ],
)
def test_fda_applies_to_false_for_irrelevant_contexts(context) -> None:
    assert FdaFoodContactModule().applies_to(context) is False


def test_fda_required_fields_are_stable() -> None:
    assert FdaFoodContactModule().required_fields() == [
        "medium_name",
        "sealing_material_family",
        "material_name",
        "temperature_c",
        "intended_us_market",
    ]


def test_fda_escalation_policy_is_manufacturer_review() -> None:
    assert FdaFoodContactModule().escalation_policy() is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW


def test_fda_check_not_applicable_for_non_food_context() -> None:
    result = FdaFoodContactModule().check({"application_domain": "chemical"})
    assert result.status is NormCheckStatus.NOT_APPLICABLE
    assert result.escalation is EscalationPolicy.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "field",
    ["medium_name", "sealing_material_family", "material_name", "temperature_c", "intended_us_market"],
)
def test_fda_check_insufficient_data_for_missing_core_fields(field: str) -> None:
    context = _fda_context(**{field: None})
    result = FdaFoodContactModule().check(context)
    assert result.status is NormCheckStatus.INSUFFICIENT_DATA
    assert field in result.missing_required_fields
    assert result.escalation is EscalationPolicy.BLOCK_UNTIL_MISSING_FIELDS


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({}, "fda_food_contact_evidence_missing"),
        ({"certification_records": [{"standard": "FDA 21 CFR 177.1550", "valid": True}]}, "fda_food_contact_declaration_missing"),
        (
            {
                "certification_records": [{"standard": "FDA 21 CFR 177.1550", "valid": True}],
                "manufacturer_declaration_present": True,
            },
            "fda_food_contact_traceability_missing",
        ),
    ],
)
def test_fda_check_review_required_for_partial_evidence(override, expected_code: str) -> None:
    result = FdaFoodContactModule().check(_fda_context(**override))
    assert result.status is NormCheckStatus.REVIEW_REQUIRED
    assert result.escalation is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
    assert any(finding.code == expected_code for finding in result.findings)


def test_fda_check_fail_for_explicit_negative_certification_context() -> None:
    result = FdaFoodContactModule().check(
        _fda_context(explicitly_not_food_contact_certified=True)
    )
    assert result.status is NormCheckStatus.FAIL
    assert any(finding.code == "fda_food_contact_negative_evidence" for finding in result.findings)


def test_fda_check_pass_only_with_minimal_complete_evidence() -> None:
    result = FdaFoodContactModule().check(
        _fda_context(
            certification_records=[
                {
                    "standard": "FDA 21 CFR 177.1550",
                    "valid": True,
                    "source_reference": "cert-fda-1",
                    "manufacturer_declaration_present": True,
                    "traceability_present": True,
                }
            ]
        )
    )
    assert result.status is NormCheckStatus.PASS
    assert result.escalation is EscalationPolicy.NO_ESCALATION
    assert any("not a final regulatory" in finding.message for finding in result.findings)


def test_default_registry_contains_fda_food_contact_module() -> None:
    registry = build_default_registry()
    assert registry.get("norm_fda_food_contact") is not None


def test_registry_runs_eu_and_fda_for_both_region_food_context() -> None:
    registry = build_default_registry()
    results = registry.run_checks(
        {
            "application_domain": "food processing",
            "food_contact_region": "both",
            "intended_us_market": True,
            "medium_name": "milk",
            "sealing_material_family": "ptfe_virgin",
            "material_name": "PTFE",
            "temperature_c": 80,
            "cleaning_regime": "CIP",
        }
    )
    assert {result.module_id for result in results} == {
        "norm_eu_food_contact",
        "norm_fda_food_contact",
    }


def test_fda_module_source_has_no_forbidden_runtime_imports() -> None:
    import app.services.norm_modules.fda_food_contact as fda_food_contact

    source = inspect.getsource(fda_food_contact)
    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
