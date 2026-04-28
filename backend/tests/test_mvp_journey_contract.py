from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace
from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.services.rfq_preview_service import (
    RFQ_PREVIEW_SECTIONS,
    build_rfq_preview_payload,
    normalize_consent_scope,
)


def _phase_1_journey_source() -> dict:
    return {
        "conversation": {"thread_id": "journey-salzwasser-001"},
        "working_profile": {
            "engineering_profile": {
                "asset_type": "agitator",
                "asset_function": "shaft sealing",
                "seal_location": "vessel shaft entry",
                "motion_type": "rotary",
                "medium": "Salzwasser",
                "temperature_c": 80,
                "pressure_bar": 4,
                "shaft_diameter_mm": 42,
                "speed_rpm": 1450,
                "shaft_material": "1.4404",
                "counterface_surface": "unknown",
                "requested_seal_type": "PTFE-RWDR",
                "installation": "Radialwellendichtring",
                "engineering_path": "rwdr",
                "top_risks": ["corrosion_risk", "unknowns_risk"],
                "missing_required_fields": ["shaft_surface_finish"],
                "manufacturer_review_needs": [
                    "Federwerkstoff und Gegenlaufflaeche bestaetigen",
                    "Druckangabe direkt an der Dichtstelle pruefen",
                ],
            },
            "completeness": {
                "coverage_score": 0.74,
                "missing_critical_parameters": ["shaft_surface_finish"],
            },
            "live_calc_tile": {
                "status": "ok",
                "v_surface_m_s": 3.19,
                "pv_value_mpa_m_s": 1.28,
                "dn_value": 60900,
                "notes": ["Orientierende RWDR-Vorpruefung, keine Freigabe."],
            },
        },
        "reasoning": {
            "phase": "rfq_preview",
            "state_revision": 6,
            "extracted_parameter_provenance": {
                "asset_type": {"origin": "user_stated", "confidence": "confirmed"},
                "medium": {"origin": "user_stated", "confidence": "confirmed"},
                "temperature_c": {"origin": "user_stated", "confidence": "confirmed"},
                "pressure_bar": {"origin": "user_stated", "confidence": "requires_confirmation"},
                "shaft_diameter_mm": {"origin": "documented", "confidence": "confirmed"},
                "speed_rpm": {"origin": "user_stated", "confidence": "confirmed"},
            },
        },
        "system": {
            "governance_metadata": {
                "release_status": "manufacturer_validation_required",
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": ["shaft_surface_finish"],
                "assumptions_active": ["PTFE-RWDR nur als Kandidatenrichtung"],
            },
            "rfq_admissibility": {
                "release_status": "manufacturer_validation_required",
                "status": "manufacturer_validation_required",
                "blockers": [],
                "open_points": ["shaft_surface_finish"],
                "rfq_ready": False,
            },
            "medium_context": {
                "medium_label": "Salzwasser",
                "status": "available",
                "scope": "orientierend",
                "summary": "Salzhaltige Medien koennen Korrosion, Ablagerungen und Abrasion treiben.",
                "properties": ["wasserbasiert", "chloridhaltig"],
                "challenges": ["Korrosion metallischer Bauteile"],
                "followup_points": ["Salzkonzentration", "Benetzung"],
                "confidence": "medium",
                "source_type": "curated_table",
                "not_for_release_decisions": True,
                "disclaimer": "Medium-Kontext ist keine Werkstofffreigabe.",
            },
            "matching_state": {},
            "rfq_state": {},
            "manufacturer_state": {},
        },
    }


def _rfq_case() -> CaseRecord:
    return CaseRecord(
        id="journey-salzwasser-001",
        case_number="CASE-JOURNEY-001",
        user_id="user-1",
        tenant_id="tenant-1",
        case_revision=6,
        request_type="new_design",
        engineering_path="rwdr",
        sealing_material_family="ptfe",
        application_pattern_id="agitator",
    )


def _rfq_snapshot() -> CaseStateSnapshot:
    return CaseStateSnapshot(
        case_id="journey-salzwasser-001",
        revision=6,
        state_json={
            "case_state": {
                "case_fields": {
                    "asset_type": {
                        "field_name": "asset_type",
                        "value": "agitator",
                        "status": "confirmed",
                        "provenance": "user_stated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "medium_name": {
                        "field_name": "medium_name",
                        "value": "Salzwasser",
                        "status": "confirmed",
                        "provenance": "user_stated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "motion_type": {
                        "field_name": "motion_type",
                        "value": "rotary",
                        "status": "confirmed",
                        "provenance": "user_stated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "temperature_max": {
                        "field_name": "temperature_max",
                        "value": 80,
                        "engineering_value": {
                            "raw_value": "80 Grad",
                            "canonical_value": 80,
                            "unit": "degC",
                            "quantity_kind": "temperature",
                        },
                        "status": "confirmed",
                        "provenance": "user_stated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "pressure_nominal": {
                        "field_name": "pressure_nominal",
                        "value": 4,
                        "engineering_value": {
                            "raw_value": "4 bar",
                            "canonical_value": 4,
                            "unit": "bar",
                            "quantity_kind": "pressure",
                            "interpretation": "unknown",
                        },
                        "status": "candidate",
                        "provenance": "user_stated",
                        "confidence": "requires_confirmation",
                        "confirmation_required": True,
                        "evidence_refs": ["chat:turn-1"],
                    },
                    "shaft_diameter_mm": {
                        "field_name": "shaft_diameter_mm",
                        "value": 42,
                        "engineering_value": {
                            "canonical_value": 42,
                            "unit": "mm",
                            "quantity_kind": "length",
                        },
                        "status": "documented",
                        "provenance": "documented",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                        "evidence_refs": ["upload:drawing-1#dim-A"],
                    },
                    "speed_rpm": {
                        "field_name": "speed_rpm",
                        "value": 1450,
                        "engineering_value": {
                            "canonical_value": 1450,
                            "unit": "rpm",
                            "quantity_kind": "rotational_speed",
                        },
                        "status": "confirmed",
                        "provenance": "user_stated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                    },
                    "calculated_speed_m_s": {
                        "field_name": "calculated_speed_m_s",
                        "value": 3.19,
                        "engineering_value": {
                            "canonical_value": 3.19,
                            "unit": "m/s",
                            "quantity_kind": "surface_speed",
                        },
                        "status": "calculated",
                        "provenance": "calculated",
                        "confidence": "confirmed",
                        "confirmation_required": False,
                        "source_revision": 6,
                    },
                },
                "missing_required_fields": ["shaft_surface_finish"],
                "top_risks": ["corrosion_risk", "unknowns_risk"],
                "plausible_directions": [
                    "PTFE-RWDR als Kandidatenrichtung mit Herstellerpruefung fuehren."
                ],
                "manufacturer_review_needs": [
                    "Federwerkstoff und Gegenlaufflaeche bestaetigen",
                    "Druckangabe direkt an der Dichtstelle pruefen",
                ],
            }
        },
    )


def test_phase_1_mvp_journey_projects_decision_cockpit_and_tabs() -> None:
    projection = project_case_workspace(_phase_1_journey_source())

    assert projection.case_summary.thread_id == "journey-salzwasser-001"
    assert projection.decision_understanding.case_summary
    assert "Medium: Salzwasser" in projection.decision_understanding.understood_now
    assert any(
        "Korrosion" in item or "Salzhaltige" in item
        for item in projection.decision_understanding.technical_meaning
    )
    assert projection.decision_understanding.next_best_question
    assert projection.medium_context.not_for_release_decisions is True

    cockpit = projection.cockpit_view
    assert [section.title for section in cockpit.sections] == [
        "1. Anlage & Funktion",
        "2. Medium & Umgebung",
        "3. Betriebsdaten & Geometrie",
        "4. Risiken & Anfrage-Reife",
    ]
    assert cockpit.readiness.readiness_level >= 3
    assert cockpit.readiness.readiness_level < 5
    assert cockpit.readiness.rfq_possible is False
    assert cockpit.readiness.missing_required_fields
    assert any(check.calc_id == "rwdr_circumferential_speed" for check in cockpit.checks)

    tabs_by_id = {tab.tab_id: tab for tab in projection.deep_dive_tabs}
    assert {"analysis", "medium", "material", "seal_type"}.issubset(tabs_by_id)


def test_phase_1_mvp_journey_builds_frozen_rfq_preview_without_dispatch() -> None:
    payload = build_rfq_preview_payload(case_row=_rfq_case(), snapshot=_rfq_snapshot())

    assert payload["meta"] == {
        "schema_version": "rfq_preview_v0.7.0",
        "artifact_type": "rfq_preview",
        "case_id": "journey-salzwasser-001",
        "case_revision": 6,
        "source_snapshot_revision": 6,
        "source_kind": "case_revision",
        "rfq_freeze": True,
    }
    assert payload["consent_boundary"] == {
        "status": "not_requested",
        "automatic_dispatch_allowed": False,
        "requires_explicit_user_consent_before_sharing": True,
        "open_points_acknowledgement_required": True,
        "no_final_release_acknowledgement_required": True,
    }

    sections = payload["rfq_preview"]["sections"]
    assert [section["title"] for section in sections] == list(RFQ_PREVIEW_SECTIONS)
    assert len(sections) == 13
    assert sections[10]["title"] == "Offene Punkte / unbestaetigte Annahmen"
    assert sections[10]["status"] == "available"
    assert sections[11]["title"] == "Fragen an den Hersteller"
    assert sections[11]["status"] == "available"

    groups = {
        group["key"]: {field["field"] for field in group["fields"]}
        for group in payload["rfq_preview"]["technical_field_groups"]
    }
    assert "shaft_diameter_mm" in groups["documented"]
    assert "calculated_speed_m_s" in groups["calculated"]
    assert "pressure_bar" in groups["needs_confirmation"]
    assert "shaft_surface_finish" in groups["missing"]
    assert "shaft_surface_finish" in payload["rfq_preview"][
        "confirmation_required_fields"
    ]
    assert "pressure_bar" in payload["rfq_preview"][
        "confirmation_required_fields"
    ]

    consent = normalize_consent_scope(
        {
            "shared_sections": ["RFQ-Preview"],
            "intended_recipients": ["manual-review-only"],
            "user_acknowledged_open_points": True,
            "user_acknowledged_no_final_release": True,
        },
        open_points_acknowledgement_required=True,
    )
    assert consent["shared_sections"] == ("RFQ-Preview",)
    assert consent["intended_recipients"] == ("manual-review-only",)
