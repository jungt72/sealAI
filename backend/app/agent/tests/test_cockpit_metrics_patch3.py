from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace


def _workspace(profile: dict) -> dict:
    return {
        "conversation": {"thread_id": "patch3-cockpit-metrics"},
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


def _field_status(projection, field_id: str) -> str:
    fields = {
        item.field_id: item
        for item in projection.cockpit_view.completeness_metrics.required_fields
    }
    return fields[field_id].status


def test_backend_check_metrics_are_registry_derived() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "Oel",
                "shaft_diameter_mm": 50.0,
                "speed_rpm": 1500.0,
                "pressure_at_seal_bar": 1.0,
                "sealing_type": "RWDR",
            }
        )
    )

    metrics = projection.cockpit_view.check_metrics
    statuses = [check.status for check in projection.cockpit_view.checks]

    assert metrics.check_total == len(projection.cockpit_view.checks) == 13
    assert metrics.check_passed_count == statuses.count("passed")
    assert metrics.check_blocked_count == statuses.count("blocked")
    assert (
        metrics.check_available_count
        == metrics.check_passed_count + metrics.check_failed_count
    )


def test_system_pressure_does_not_make_pressure_check_available() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "Oel",
                "shaft_diameter_mm": 50.0,
                "speed_rpm": 1500.0,
                "pressure_system_bar": 5.0,
                "sealing_type": "RWDR",
            }
        )
    )
    checks = {check.calc_id: check for check in projection.cockpit_view.checks}

    assert checks["rwdr_pv_precheck"].status == "blocked"
    assert "pressure_at_seal_bar" in checks["rwdr_pv_precheck"].missing_fields
    assert checks["rwdr_pressure_window"].status == "blocked"
    assert projection.cockpit_view.check_metrics.check_available_count == 2


def test_ambiguous_pressure_does_not_count_as_known_seal_pressure() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "Oel",
                "shaft_diameter_mm": 50.0,
                "speed_rpm": 1500.0,
                "ambiguous_pressure_bar": 5.0,
                "sealing_type": "RWDR",
            }
        )
    )
    fields = {
        item.field_id: item
        for item in projection.cockpit_view.completeness_metrics.required_fields
    }

    assert fields["pressure_at_seal_bar"].status == "ambiguous"
    assert fields["pressure_at_seal_bar"].blocks_next_step is True
    assert (
        "pressure_at_seal_bar"
        in projection.cockpit_view.completeness_metrics.required_missing
    )


def test_placeholder_medium_reduces_completeness() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "das medium",
                "shaft_diameter_mm": 50.0,
                "speed_rpm": 1500.0,
                "pressure_at_seal_bar": 1.0,
                "sealing_type": "RWDR",
            }
        )
    )
    metrics = projection.cockpit_view.completeness_metrics

    assert _field_status(projection, "medium") == "invalid"
    assert "medium" in metrics.required_invalid
    assert metrics.required_known < metrics.required_total
    assert metrics.completeness_percent < 100


def test_rwdr_sealing_type_counts_as_known() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "Oel",
                "shaft_diameter_mm": 50.0,
                "speed_rpm": 1500.0,
                "pressure_at_seal_bar": 1.0,
                "sealing_type": "RWDR",
            }
        )
    )

    assert _field_status(projection, "sealing_type") == "known"
    assert (
        "sealing_type"
        not in projection.cockpit_view.completeness_metrics.required_missing
    )
