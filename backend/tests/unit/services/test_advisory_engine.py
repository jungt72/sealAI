from __future__ import annotations

import inspect

import pytest

from app.services import advisory_engine as service_module
from app.services.advisory_engine import (
    ADVISORY_DISCLAIMER,
    INITIAL_ADVISORY_CATEGORIES,
    AdvisoryCategory,
    AdvisoryEngine,
    AdvisorySeverity,
    evaluate_advisories,
    evaluate_advisory_summary,
)
from app.services.norm_modules import NormCheckResult, NormCheckStatus


@pytest.fixture
def engine() -> AdvisoryEngine:
    return AdvisoryEngine()


def _by_reason(advisories, reason_code: str):
    return next(advisory for advisory in advisories if advisory.reason_code == reason_code)


def test_exactly_eight_initial_categories_are_defined() -> None:
    assert len(INITIAL_ADVISORY_CATEGORIES) == 8
    assert set(INITIAL_ADVISORY_CATEGORIES) == set(AdvisoryCategory)


def test_initial_categories_are_stable_and_authority_aligned() -> None:
    assert [category.value for category in INITIAL_ADVISORY_CATEGORIES] == [
        "material_suboptimal",
        "lifespan_expectation_mismatch",
        "shaft_requirements_concern",
        "norm_compliance_alert",
        "dry_run_risk",
        "medium_incompatibility_hint",
        "installation_concern",
        "quantity_economic_consideration",
    ]


def test_empty_context_returns_no_advisories(engine: AdvisoryEngine) -> None:
    assert engine.evaluate_advisories({}) == []


def test_uncritical_context_returns_no_advisories(engine: AdvisoryEngine) -> None:
    advisories = engine.evaluate_advisories(
        {
            "missing_critical_fields": [],
            "norm_results": [],
            "food_contact_required": False,
            "atex_required": False,
            "quantity_capability_available": True,
        }
    )
    assert advisories == []


def test_each_initial_category_is_emitted_by_rule_matrix(engine: AdvisoryEngine) -> None:
    contexts = [
        {"material_review_needed": True},
        {"manufacturer_review_required": True},
        {"missing_critical_fields": ["pressure_bar"]},
        {"norm_results": [{"module_id": "norm_x", "status": "review_required"}]},
        {"dry_run_possible": True, "dry_run_allowed": False},
        {"operating_envelope_review_required": True},
        {"installation_warnings": ["press_fit_tool_missing"]},
        {"quantity_requested": 4, "quantity_capability_available": False},
    ]

    categories = {
        engine.evaluate_advisories(context)[0].category
        for context in contexts
    }

    assert categories == set(INITIAL_ADVISORY_CATEGORIES)


@pytest.mark.parametrize(
    ("context", "expected_triggers"),
    [
        ({"material_suboptimal": True}, ("material_suboptimal",)),
        ({"material_review_needed": True}, ("material_review_needed",)),
        ({"material_suitability_hints": ["medium_uncertain"]}, ("material_suitability_hints",)),
        ({"material_suitability_status": "review_required"}, ("material_suitability_status",)),
    ],
)
def test_material_suboptimal_triggers_from_structured_signals(
    engine: AdvisoryEngine,
    context,
    expected_triggers: tuple[str, ...],
) -> None:
    advisory = _by_reason(engine.evaluate_advisories(context), "material_suboptimal")

    assert advisory.category is AdvisoryCategory.MATERIAL_SUBOPTIMAL
    assert advisory.severity is AdvisorySeverity.CAUTION
    assert advisory.blocking is False
    assert advisory.triggering_parameters == expected_triggers


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"material_suboptimal": False, "material_review_needed": False},
        {"material_suitability_hints": []},
        {"material_suitability_status": "suitable"},
    ],
)
def test_material_suboptimal_no_trigger_for_absent_or_positive_signals(
    engine: AdvisoryEngine,
    context,
) -> None:
    assert engine.evaluate_advisories(context) == []


@pytest.mark.parametrize(
    ("missing", "expected_triggers"),
    [
        (["shaft_diameter_mm"], ("shaft_diameter_mm",)),
        (("pressure_bar", "temperature_c"), ("pressure_bar", "temperature_c")),
        ("medium_name", ("medium_name",)),
    ],
)
def test_missing_critical_input_is_blocking(
    engine: AdvisoryEngine,
    missing,
    expected_triggers: tuple[str, ...],
) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories({"missing_critical_fields": missing}),
        "missing_critical_input",
    )
    assert advisory.category is AdvisoryCategory.SHAFT_REQUIREMENTS_CONCERN
    assert advisory.severity is AdvisorySeverity.WARNING
    assert advisory.blocking is True
    assert advisory.triggering_parameters == expected_triggers


def test_missing_fields_alias_triggers_missing_critical_input(engine: AdvisoryEngine) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories({"missing_fields": ["shaft_surface_finish"]}),
        "missing_critical_input",
    )
    assert advisory.triggering_parameters == ("shaft_surface_finish",)


@pytest.mark.parametrize(
    ("status", "expected_blocking", "expected_severity"),
    [
        (NormCheckStatus.REVIEW_REQUIRED, False, AdvisorySeverity.CAUTION),
        (NormCheckStatus.FAIL, True, AdvisorySeverity.WARNING),
        (NormCheckStatus.INSUFFICIENT_DATA, True, AdvisorySeverity.WARNING),
        ("review_required", False, AdvisorySeverity.CAUTION),
        ("fail", True, AdvisorySeverity.WARNING),
    ],
)
def test_norm_review_required_from_norm_results(
    engine: AdvisoryEngine,
    status,
    expected_blocking: bool,
    expected_severity: AdvisorySeverity,
) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories(
            {
                "norm_results": [
                    {
                        "module_id": "norm_din_3760_iso_6194",
                        "status": status,
                    }
                ]
            }
        ),
        "norm_review_required",
    )
    assert advisory.category is AdvisoryCategory.NORM_COMPLIANCE_ALERT
    assert advisory.blocking is expected_blocking
    assert advisory.severity is expected_severity
    assert advisory.triggering_parameters == ("norm_din_3760_iso_6194",)


def test_norm_pass_does_not_trigger_advisory(engine: AdvisoryEngine) -> None:
    assert engine.evaluate_advisories(
        {
            "norm_results": [
                NormCheckResult(
                    module_id="norm_din_3760_iso_6194",
                    version="1.0.0",
                    status=NormCheckStatus.PASS,
                    applies=True,
                )
            ]
        }
    ) == []


@pytest.mark.parametrize(
    "context",
    [
        {"food_contact_required": True},
        {"food_contact_required": True, "food_contact_evidence_complete": False},
    ],
)
def test_food_contact_review_required(engine: AdvisoryEngine, context) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories(context),
        "food_contact_review_required",
    )
    assert advisory.category is AdvisoryCategory.NORM_COMPLIANCE_ALERT
    assert advisory.severity is AdvisorySeverity.CAUTION
    assert advisory.blocking is False
    assert "food_contact" in advisory.evidence_tags


def test_food_contact_complete_evidence_does_not_trigger(engine: AdvisoryEngine) -> None:
    assert engine.evaluate_advisories(
        {"food_contact_required": True, "food_contact_evidence_complete": True}
    ) == []


@pytest.mark.parametrize(
    ("context", "expected_blocking"),
    [
        ({"atex_required": True, "has_atex_capable_claim": False}, True),
        ({"atex_required": True}, True),
    ],
)
def test_atex_capability_gap(engine: AdvisoryEngine, context, expected_blocking: bool) -> None:
    advisory = _by_reason(engine.evaluate_advisories(context), "atex_capability_gap")
    assert advisory.category is AdvisoryCategory.NORM_COMPLIANCE_ALERT
    assert advisory.severity is AdvisorySeverity.WARNING
    assert advisory.blocking is expected_blocking
    assert "manufacturer_capability_claims" in advisory.evidence_tags


def test_atex_capability_present_does_not_trigger(engine: AdvisoryEngine) -> None:
    assert engine.evaluate_advisories(
        {"atex_required": True, "has_atex_capable_claim": True}
    ) == []


@pytest.mark.parametrize(
    ("quantity", "expected_blocking", "expected_severity"),
    [
        (1, True, AdvisorySeverity.WARNING),
        (10, True, AdvisorySeverity.WARNING),
        (11, False, AdvisorySeverity.CAUTION),
        (100, False, AdvisorySeverity.CAUTION),
    ],
)
def test_quantity_capability_gap(
    engine: AdvisoryEngine,
    quantity: int,
    expected_blocking: bool,
    expected_severity: AdvisorySeverity,
) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories(
            {
                "quantity_requested": quantity,
                "quantity_capability_available": False,
                "minimum_order_pieces": 25,
            }
        ),
        "quantity_capability_gap",
    )
    assert advisory.category is AdvisoryCategory.QUANTITY_ECONOMIC_CONSIDERATION
    assert advisory.blocking is expected_blocking
    assert advisory.severity is expected_severity
    assert "small_quantity" in advisory.evidence_tags


def test_quantity_available_does_not_trigger_gap(engine: AdvisoryEngine) -> None:
    assert engine.evaluate_advisories(
        {"quantity_requested": 4, "quantity_capability_available": True}
    ) == []


@pytest.mark.parametrize(
    "context",
    [
        {"geometry_consistency_issue": True},
        {"shaft_diameter_mm": 50, "housing_bore_diameter_mm": 50},
        {"shaft_diameter_mm": "62", "housing_bore_diameter_mm": "40"},
    ],
)
def test_geometry_consistency_issue_is_blocking(engine: AdvisoryEngine, context) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories(context),
        "geometry_consistency_issue",
    )
    assert advisory.category is AdvisoryCategory.SHAFT_REQUIREMENTS_CONCERN
    assert advisory.severity is AdvisorySeverity.WARNING
    assert advisory.blocking is True


def test_valid_geometry_does_not_trigger_geometry_issue(engine: AdvisoryEngine) -> None:
    assert engine.evaluate_advisories(
        {"shaft_diameter_mm": 40, "housing_bore_diameter_mm": 62}
    ) == []


@pytest.mark.parametrize(
    ("context", "expected_triggers"),
    [
        ({"dry_run_risk": True}, ("dry_run_risk",)),
        (
            {"dry_run_possible": True, "dry_run_allowed": False},
            ("dry_run_possible", "dry_run_allowed"),
        ),
    ],
)
def test_dry_run_risk_triggers_from_structured_signals(
    engine: AdvisoryEngine,
    context,
    expected_triggers: tuple[str, ...],
) -> None:
    advisory = _by_reason(engine.evaluate_advisories(context), "dry_run_risk")

    assert advisory.category is AdvisoryCategory.DRY_RUN_RISK
    assert advisory.severity is AdvisorySeverity.WARNING
    assert advisory.blocking is False
    assert advisory.triggering_parameters == expected_triggers


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"dry_run_risk": False},
        {"dry_run_possible": True, "dry_run_allowed": True},
        {"dry_run_possible": False, "dry_run_allowed": False},
    ],
)
def test_dry_run_risk_no_trigger_without_risk_combination(
    engine: AdvisoryEngine,
    context,
) -> None:
    assert engine.evaluate_advisories(context) == []


@pytest.mark.parametrize(
    "context",
    [
        {"operating_envelope_review_required": True},
        {"extreme_operating_conditions": True},
        {"operating_envelope_warnings": ["pv_warning"]},
    ],
)
def test_operating_envelope_review(engine: AdvisoryEngine, context) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories(context),
        "operating_envelope_review",
    )
    assert advisory.category is AdvisoryCategory.MEDIUM_INCOMPATIBILITY_HINT
    assert advisory.severity is AdvisorySeverity.CAUTION
    assert advisory.blocking is False
    assert "calculation" in advisory.evidence_tags


@pytest.mark.parametrize(
    ("context", "expected_triggers"),
    [
        ({"installation_concern": True}, ("installation_concern",)),
        ({"mounting_concern": True}, ("mounting_concern",)),
        ({"installation_warnings": ["sharp_edge"]}, ("installation_warnings",)),
        ({"installation_difficulty": "high"}, ("installation_difficulty",)),
    ],
)
def test_installation_concern_triggers_from_structured_signals(
    engine: AdvisoryEngine,
    context,
    expected_triggers: tuple[str, ...],
) -> None:
    advisory = _by_reason(engine.evaluate_advisories(context), "installation_concern")

    assert advisory.category is AdvisoryCategory.INSTALLATION_CONCERN
    assert advisory.severity is AdvisorySeverity.CAUTION
    assert advisory.blocking is False
    assert advisory.triggering_parameters == expected_triggers


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"installation_concern": False, "mounting_concern": False},
        {"installation_warnings": []},
        {"installation_difficulty": "normal"},
    ],
)
def test_installation_concern_no_trigger_for_absent_or_normal_signals(
    engine: AdvisoryEngine,
    context,
) -> None:
    assert engine.evaluate_advisories(context) == []


@pytest.mark.parametrize(
    "reason",
    ["manual_review", "norm_escalation", ""],
)
def test_manufacturer_review_required(engine: AdvisoryEngine, reason: str) -> None:
    advisory = _by_reason(
        engine.evaluate_advisories(
            {
                "manufacturer_review_required": True,
                "manufacturer_review_reason": reason,
            }
        ),
        "manufacturer_review_required",
    )
    assert advisory.category is AdvisoryCategory.LIFESPAN_EXPECTATION_MISMATCH
    assert advisory.severity is AdvisorySeverity.CAUTION
    assert advisory.blocking is False


def test_summary_counts_blocking_and_highest_severity(engine: AdvisoryEngine) -> None:
    summary = engine.evaluate_advisory_summary(
        {
            "missing_critical_fields": ["pressure_bar"],
            "food_contact_required": True,
            "food_contact_evidence_complete": False,
        }
    )
    assert summary.blocking_count == 1
    assert summary.highest_severity is AdvisorySeverity.WARNING
    assert summary.categories_present == (
        AdvisoryCategory.SHAFT_REQUIREMENTS_CONCERN,
        AdvisoryCategory.NORM_COMPLIANCE_ALERT,
    )


def test_module_level_helpers_delegate_to_engine() -> None:
    advisories = evaluate_advisories({"atex_required": True})
    summary = evaluate_advisory_summary({"atex_required": True})
    assert advisories[0].reason_code == "atex_capability_gap"
    assert summary.advisories[0].reason_code == "atex_capability_gap"


def test_every_advisory_carries_required_output_fields(engine: AdvisoryEngine) -> None:
    advisories = engine.evaluate_advisories(
        {
            "missing_critical_fields": ["pressure_bar"],
            "norm_results": [{"module_id": "norm_x", "status": "review_required"}],
            "food_contact_required": True,
            "atex_required": True,
            "quantity_requested": 4,
            "quantity_capability_available": False,
            "geometry_consistency_issue": True,
            "dry_run_risk": True,
            "operating_envelope_review_required": True,
            "installation_concern": True,
            "manufacturer_review_required": True,
            "material_review_needed": True,
        }
    )
    assert len(advisories) == 11
    for advisory in advisories:
        assert advisory.advisory_id
        assert advisory.category in AdvisoryCategory
        assert advisory.severity in AdvisorySeverity
        assert advisory.title
        assert advisory.message
        assert advisory.reason_code
        assert advisory.recommended_action
        assert advisory.disclaimer == ADVISORY_DISCLAIMER


def test_service_has_no_langgraph_agent_or_fastapi_imports() -> None:
    source = inspect.getsource(service_module)
    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
