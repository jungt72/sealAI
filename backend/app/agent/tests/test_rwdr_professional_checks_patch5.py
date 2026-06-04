from __future__ import annotations

from app.agent.domain.checks_registry import build_registered_check_results
from app.agent.domain.normalization import extract_parameters
from app.agent.runtime.clarification_priority import select_clarification_priority
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    MediumClassificationState,
)
from app.api.v1.projections.case_workspace import project_case_workspace


def _checks(profile: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["calc_id"]: item
        for item in build_registered_check_results(
            profile={"sealing_type": "rwdr", **profile},
            engineering_path="rwdr",
            technical_derivations=[],
        )
    }


def _workspace(profile: dict[str, object]) -> dict[str, object]:
    return {
        "conversation": {"thread_id": "patch5-rwdr-professional-checks"},
        "working_profile": {
            "engineering_profile": {
                "movement_type": "rotary",
                "installation": "Radialwellendichtring",
                **profile,
            },
            "completeness": {"missing_critical_parameters": []},
        },
        "reasoning": {"phase": "clarification", "state_revision": 1},
        "system": {
            "governance_metadata": {"release_status": "precheck_only"},
            "rfq_admissibility": {
                "release_status": "precheck_only",
                "status": "precheck_only",
            },
            "matching_state": {},
            "rfq_state": {},
            "manufacturer_state": {},
        },
    }


def _state(assertions: dict[str, object]) -> GovernedSessionState:
    return GovernedSessionState(
        asserted=AssertedState(
            assertions={
                key: AssertedClaim(field_name=key, asserted_value=value)
                for key, value in assertions.items()
            }
        ),
        medium_classification=MediumClassificationState(
            canonical_label=str(assertions.get("medium") or ""),
            family="oelhaltig",
            confidence="medium",
            status="recognized",
        ),
    )


def test_rwdr_required_fields_include_surface_runout_lubrication() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "Oel",
                "temperature_c": 80,
                "pressure_at_seal_bar": 1.0,
                "shaft_diameter_mm": 50,
                "speed_rpm": 1500,
                "sealing_type": "RWDR",
            }
        )
    )
    fields = {
        item.field_id: item
        for item in projection.cockpit_view.completeness_metrics.required_fields
    }
    check_ids = {check.calc_id for check in projection.cockpit_view.checks}

    assert "counterface_surface_condition" in fields
    assert "runout_mm" in fields
    assert "lubrication_condition" in fields
    assert fields["counterface_surface_condition"].requirement_tier == "recommended_for_professional_review"
    assert fields["counterface_surface_condition"].blocks_next_step is False
    assert "rwdr_surface_condition_check" in check_ids
    assert "rwdr_runout_eccentricity_check" in check_ids
    assert "rwdr_lubrication_check" in check_ids


def test_rwdr_surface_condition_unknown_creates_missing_input_risk() -> None:
    check = _checks({})["rwdr_surface_condition_check"]

    assert check["status"] == "pending"
    assert check["claim_type"] == "missing_input_risk"
    assert "counterface_surface_condition" in check["missing_fields"]


def test_rwdr_surface_condition_damaged_creates_evidenced_risk() -> None:
    check = _checks({"counterface_surface_condition": "damaged"})[
        "rwdr_surface_condition_check"
    ]

    assert check["status"] == "failed"
    assert "counterface_surface_condition" in check["evidence_fields"]
    assert "ungeeignet" not in str(check["allowed_user_wording"]).casefold()
    assert "freigabe" not in str(check["allowed_user_wording"]).casefold()


def test_rwdr_roughness_value_enables_roughness_check() -> None:
    params = extract_parameters("Rauheit Ra 0,8 µm")
    check = _checks({"shaft_roughness_ra_um": params["shaft_roughness_ra_um"]})[
        "rwdr_roughness_check"
    ]

    assert params["shaft_roughness_ra_um"] == 0.8
    assert check["status"] == "passed"
    assert "shaft_roughness_ra_um" in check["evidence_fields"]
    assert "vorcheck" in str(check["allowed_user_wording"]).casefold()
    assert "freigabe" not in str(check["allowed_user_wording"]).casefold()


def test_rwdr_hardness_value_enables_hardness_check() -> None:
    params = extract_parameters("Härte 60 HRC")
    check = _checks({"shaft_hardness_hrc": params["shaft_hardness_hrc"]})[
        "rwdr_hardness_check"
    ]

    assert params["shaft_hardness_hrc"] == 60.0
    assert check["status"] == "passed"
    assert "shaft_hardness_hrc" in check["evidence_fields"]


def test_rwdr_runout_missing_is_missing_input_not_high_runout() -> None:
    check = _checks({})["rwdr_runout_eccentricity_check"]

    assert check["claim_type"] == "missing_input_risk"
    assert "runout_mm" in check["missing_fields"]
    assert "hoch" not in str(check["allowed_user_wording"]).casefold()
    assert "Der Wellenschlag ist hoch." in check["forbidden_user_wording"]


def test_rwdr_runout_value_can_create_measured_risk() -> None:
    check = _checks({"runout_mm": 0.35})["rwdr_runout_eccentricity_check"]

    assert check["status"] == "failed"
    assert check["claim_type"] == "measured_risk"
    assert check["subject_field"] == "runout_mm"
    assert "runout_mm" in check["evidence_fields"]


def test_rwdr_lubrication_dry_run_creates_evidenced_risk() -> None:
    params = extract_parameters("Trockenlauf moeglich")
    check = _checks({"lubrication_condition": params["lubrication_condition"]})[
        "rwdr_lubrication_check"
    ]

    assert check["status"] == "failed"
    assert "lubrication_condition" in check["evidence_fields"]
    assert "versagt" not in str(check["allowed_user_wording"]).casefold()


def test_rwdr_question_planner_asks_surface_question_with_reason() -> None:
    priority = select_clarification_priority(
        _state(
            {
                "sealing_type": "rwdr",
                "medium": "Oel",
                "pressure_at_seal_bar": 1.0,
                "temperature_c": 80,
                "speed_rpm": 1500,
                "shaft_diameter_mm": 50,
            }
        ),
        ["counterface_surface_condition", "shaft_roughness_ra_um"],
    )

    assert priority is not None
    assert priority.focus_key == "counterface_surface_condition"
    assert "gegenlaufflaeche" in priority.question.casefold()
    assert priority.reason


def test_rwdr_checks_do_not_use_system_pressure_as_seal_pressure() -> None:
    checks = _checks({"pressure_system_bar": 5.0})
    pressure = checks["rwdr_pressure_role_check"]

    assert pressure["status"] == "blocked"
    assert pressure["claim_type"] == "missing_input_risk"
    assert "pressure_system_bar" in pressure["evidence_fields"]
    assert "pressure_at_seal_bar" in pressure["missing_fields"]
    assert pressure["claim_type"] != "measured_risk"
