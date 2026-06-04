from __future__ import annotations

import inspect

import pytest

from app.services.norm_modules import (
    EscalationPolicy,
    EuFoodContactModule,
    NormCheckStatus,
    build_default_registry,
)


def _eu_context(**overrides):
    context = {
        "application_domain": "food processing",
        "food_contact_required": True,
        "food_contact_region": "eu",
        "medium_name": "milk",
        "sealing_material_family": "ptfe_virgin",
        "material_name": "PTFE virgin food grade",
        "temperature_c": 80,
        "cleaning_regime": "CIP caustic",
    }
    context.update(overrides)
    return context


@pytest.mark.parametrize(
    "context",
    [
        {"food_contact_required": True, "food_contact_region": "eu"},
        {"application_domain": "food processing", "market_region": "EU"},
        {"medium_name": "chocolate", "jurisdiction": "europe"},
        {"application_category": "pharma", "food_contact_region": "both"},
    ],
)
def test_eu_applies_to_food_contact_eu_contexts(context) -> None:
    assert EuFoodContactModule().applies_to(context) is True


@pytest.mark.parametrize(
    "context",
    [
        {"application_domain": "chemical", "food_contact_region": "eu"},
        {"food_contact_required": False, "medium_name": "hydraulic oil", "market_region": "eu"},
        {"application_domain": "food processing", "food_contact_region": "us"},
    ],
)
def test_eu_applies_to_false_for_irrelevant_contexts(context) -> None:
    assert EuFoodContactModule().applies_to(context) is False


def test_eu_required_fields_are_stable() -> None:
    assert EuFoodContactModule().required_fields() == [
        "medium_name",
        "sealing_material_family",
        "material_name",
        "temperature_c",
        "cleaning_regime",
    ]


def test_eu_escalation_policy_is_manufacturer_review() -> None:
    assert EuFoodContactModule().escalation_policy() is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW


def test_eu_check_not_applicable_for_non_food_context() -> None:
    result = EuFoodContactModule().check({"application_domain": "chemical"})
    assert result.status is NormCheckStatus.NOT_APPLICABLE
    assert result.escalation is EscalationPolicy.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "field",
    ["medium_name", "sealing_material_family", "material_name", "temperature_c", "cleaning_regime"],
)
def test_eu_check_insufficient_data_for_missing_core_fields(field: str) -> None:
    context = _eu_context(**{field: None})
    result = EuFoodContactModule().check(context)
    assert result.status is NormCheckStatus.INSUFFICIENT_DATA
    assert field in result.missing_required_fields
    assert result.escalation is EscalationPolicy.BLOCK_UNTIL_MISSING_FIELDS


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({}, "eu_food_contact_evidence_missing"),
        ({"certification_records": [{"standard": "EU 10/2011", "valid": True}]}, "eu_food_contact_declaration_missing"),
        (
            {
                "certification_records": [{"standard": "EU 10/2011", "valid": True}],
                "manufacturer_declaration_present": True,
            },
            "eu_food_contact_traceability_missing",
        ),
        (
            {
                "certification_records": [{"standard": "EU 10/2011", "valid": True}],
                "manufacturer_declaration_present": True,
                "traceability_present": True,
            },
            "eu_food_contact_migration_test_missing",
        ),
    ],
)
def test_eu_check_review_required_for_partial_evidence(override, expected_code: str) -> None:
    result = EuFoodContactModule().check(_eu_context(**override))
    assert result.status is NormCheckStatus.REVIEW_REQUIRED
    assert result.escalation is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
    assert any(finding.code == expected_code for finding in result.findings)


def test_eu_check_fail_for_explicit_negative_certification_context() -> None:
    result = EuFoodContactModule().check(
        _eu_context(
            certification_records=[
                {"standard": "EU 10/2011", "valid": False, "source_reference": "expired-cert"}
            ]
        )
    )
    assert result.status is NormCheckStatus.FAIL
    assert any(finding.code == "eu_food_contact_negative_evidence" for finding in result.findings)


def test_eu_check_pass_only_with_minimal_complete_evidence() -> None:
    result = EuFoodContactModule().check(
        _eu_context(
            certification_records=[
                {
                    "standard": "EU 10/2011",
                    "valid": True,
                    "source_reference": "cert-1",
                    "manufacturer_declaration_present": True,
                    "traceability_present": True,
                    "migration_test_available": True,
                }
            ]
        )
    )
    assert result.status is NormCheckStatus.PASS
    assert result.escalation is EscalationPolicy.NO_ESCALATION
    assert any("not a final legal" in finding.message for finding in result.findings)


def test_default_registry_contains_eu_food_contact_module() -> None:
    registry = build_default_registry()
    assert registry.get("norm_eu_food_contact") is not None


def test_eu_module_source_has_no_forbidden_runtime_imports() -> None:
    import app.services.norm_modules.eu_food_contact as eu_food_contact

    source = inspect.getsource(eu_food_contact)
    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
