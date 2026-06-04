from __future__ import annotations

from app.services.decision_understanding_service import (
    build_decision_understanding_projection,
)


def test_saline_water_unclear_keeps_application_or_motion_as_next_question() -> None:
    projection = build_decision_understanding_projection(
        {
            "case_state": {
                "medium_name": {"canonical_value": "Salzwasser"},
                "temperature_max": {"canonical_value": 80, "unit": "degC"},
            }
        }
    )

    assert "Medium: Salzwasser" in projection.understood_now
    assert "Temperatur max.: 80 degC" in projection.understood_now
    assert any(
        "Korrosion" in item or "Korros" in item for item in projection.technical_meaning
    )
    assert (
        projection.next_best_question
        == "In welcher Anlage oder Baugruppe sitzt die Dichtung?"
    )
    assert "asset_type" in projection.not_yet_decidable


def test_ethanol_pump_flags_mechanical_seal_direction_and_atex_context() -> None:
    projection = build_decision_understanding_projection(
        {
            "case_state": {
                "asset_type": "Pumpe",
                "medium_name": "Ethanol",
                "temperature_max": 150,
                "pressure_nominal": 10,
            }
        }
    )

    assert any("Gleitringdichtung" in item for item in projection.plausible_directions)
    assert any("ATEX" in item for item in projection.technical_meaning)
    assert "pressure_risk" in projection.key_risks
    assert "temperature_risk" in projection.key_risks
    assert any("ATEX" in item for item in projection.manufacturer_review_needs)


def test_material_question_does_not_make_final_ptfe_fkm_selection() -> None:
    projection = build_decision_understanding_projection(
        {
            "case_state": {
                "material_question": "Ist PTFE besser als FKM?",
            }
        }
    )

    assert any(
        "keine belastbare Auswahlentscheidung" in item
        for item in projection.technical_meaning
    )
    assert any("Herstellerfreigabe" in item for item in projection.confidence_notes)
    assert not any(
        "garantiert" in item.casefold() for item in projection.plausible_directions
    )


def test_agitator_case_surfaces_relevant_open_points() -> None:
    projection = build_decision_understanding_projection(
        {
            "case_state": {
                "asset_type": "Ruehrwerk",
                "motion_type": {"value": "rotary"},
                "missing_required_fields": ["seal_location", "medium_name"],
            }
        }
    )

    assert any("Ruehrwerke" in item for item in projection.technical_meaning)
    assert "seal_location" in projection.not_yet_decidable
    assert "medium_name" in projection.not_yet_decidable
    assert (
        projection.next_best_question
        == "An welcher Dichtstelle sitzt die Dichtung genau?"
    )


def test_document_candidates_remain_unconfirmed_review_needs() -> None:
    projection = build_decision_understanding_projection(
        {
            "document_input": {
                "extraction_status": "candidate",
                "extracted_candidates": [
                    {"field_name": "shaft_diameter", "value": 28},
                ],
                "evidence_gaps": ["Nutzerbestaetigung der Zeichnungswerte fehlt"],
            }
        }
    )

    assert any("Nutzerbestaetigung" in item for item in projection.confidence_notes)
    assert any("Herstellerfreigabe" in item for item in projection.confidence_notes)
