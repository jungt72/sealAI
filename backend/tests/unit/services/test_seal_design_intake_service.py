from __future__ import annotations

from app.services.seal_design_intake_service import build_seal_design_intake


def _missing_keys(bundle) -> list[str]:
    return [field.key for field in bundle.missing_fields]


def _trigger_ids(bundle) -> set[str]:
    return {trigger.trigger_id for trigger in bundle.escalation_triggers}


def _check(bundle, check_id: str):
    return next(
        check for check in bundle.screening_checks if check.check_id == check_id
    )


def test_empty_new_design_payload_marks_minimum_dataset_missing() -> None:
    bundle = build_seal_design_intake("")

    assert bundle.schema_version == "seal_design_intake_v0.8.3"
    assert bundle.status == "no_design_dataset"
    assert "leakage_target" in _missing_keys(bundle)
    assert "medium" in _missing_keys(bundle)
    assert "verification_criteria" in _missing_keys(bundle)
    assert "finale Auslegungsfreigabe" in bundle.boundary_notice
    assert "DesignRequiredFieldGapIdentified" in bundle.event_names


def test_design_payload_with_required_fields_is_ready_for_review_not_released() -> None:
    bundle = build_seal_design_intake(
        {
            "profile": {
                "sealing_function": "Aussenleckage verhindern",
                "leakage_target": "keine sichtbare Leckage",
                "safety_context": "nicht sicherheitskritisch",
                "medium": "HLP 46",
                "motion_type": "hubend",
                "pressure_bar": 160,
                "temperature_min": -20,
                "temperature_max": 90,
                "geometry": "Stange 40 mm, radialer Bauraum 3,5 mm",
                "radial_gap_mm": 0.15,
                "surface_roughness_ra_um": 0.3,
                "verification_criteria": "Druck- und Lebensdauertest",
                "target_lifetime_cycles": 2_000_000,
                "lubrication": "Hydraulikoel",
                "contamination": "normal gefiltert",
                "mounting_path": "Montagehuelse vorhanden",
            }
        }
    )

    assert bundle.status == "design_review_ready_not_released"
    assert bundle.missing_fields == ()
    assert bundle.next_required_fields == ()
    assert "keine finale" in bundle.boundary_notice


def test_oring_screening_computes_squeeze_groove_fill_and_stretch() -> None:
    bundle = build_seal_design_intake(
        {
            "cross_section_mm": 3.53,
            "groove_depth_mm": 2.70,
            "groove_width_mm": 4.30,
            "seal_inner_diameter_mm": 47.22,
            "shaft_diameter_mm": 48.0,
        }
    )

    assert _check(bundle, "oring.squeeze_pct").value == 23.51
    assert _check(bundle, "oring.groove_fill_pct").value == 84.3
    assert _check(bundle, "oring.groove_fill_pct").status == "screening_ok"
    assert _check(bundle, "oring.stretch_pct").value == 1.65
    assert "DesignScreeningComputed" in bundle.event_names


def test_high_groove_fill_and_temperature_trigger_escalation() -> None:
    bundle = build_seal_design_intake(
        {
            "cross_section_mm": 3.53,
            "groove_depth_mm": 2.70,
            "groove_width_mm": 4.0,
            "temperature_max_c": 130,
        }
    )

    assert _check(bundle, "oring.groove_fill_pct").status == "warning"
    assert "hot_high_groove_fill" in _trigger_ids(bundle)


def test_high_pressure_gap_and_gas_decompression_trigger_escalation() -> None:
    bundle = build_seal_design_intake(
        {
            "medium": "Stickstoff Gas",
            "pressure_bar": 160,
            "radial_gap_mm": 0.35,
            "decompression_rate_bar_per_s": 20,
        }
    )

    assert {"high_pressure_large_gap", "gas_decompression_review"} <= _trigger_ids(
        bundle
    )
    assert "DesignEscalationTriggerIdentified" in bundle.event_names


def test_text_payload_extracts_best_practice_design_hints_without_release() -> None:
    bundle = build_seal_design_intake(
        "Leckageziel keine sichtbare Leckage, Medium HLP-46, hubend, "
        "ATEX nein, Dichtfunktion Schmierstoff halten."
    )

    known = {field.key for field in bundle.known_fields}
    assert {"leakage_target", "medium", "motion_type", "safety_context"} <= known
    assert "verification_criteria" in _missing_keys(bundle)
