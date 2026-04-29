from __future__ import annotations

from app.domain.case_type import CaseType
from app.domain.seal_type import SealType
from app.services.next_best_question_service import (
    derive_needs_current_state_and_questions,
)


def _state(
    *,
    case_type: CaseType = CaseType.new_rfq,
    seal_type: SealType = SealType.unknown_seal,
    profile: dict | None = None,
    hints: list[str] | None = None,
    conflicts_open: int = 0,
) -> dict:
    return {
        "case_type": case_type.value,
        "profile": profile or {},
        "parameters": profile or {},
        "readiness": {"readiness_label": "precheck"},
        "governance_status": {"release_status": "precheck_only"},
        "rfq_status": {"open_points": []},
        "evidence_summary": {},
        "conflicts": {"open": conflicts_open, "items": []},
        "seal_application_profile": {
            "seal_type": seal_type.value,
            "seal_type_confidence": 0.9 if seal_type is not SealType.unknown_seal else 0.1,
            "ambiguous": False,
            "type_specific_missing_hints": hints or [],
        },
    }


def _focuses(result) -> list[str]:
    return [question.focus_key for question in result.next_best_questions]


def test_unknown_seal_type_in_new_rfq_asks_for_seal_type_first() -> None:
    result = derive_needs_current_state_and_questions(_state())

    assert _focuses(result)[0] == "seal_type"
    assert "Dichtungstyp" in result.next_best_questions[0].question


def test_radial_shaft_known_medium_temperature_asks_pressure_speed_surface_not_medium() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.radial_shaft_seal,
            profile={"medium": "Oel", "temperature_c": 80},
            hints=[
                "medium",
                "temperature",
                "pressure_or_pressure_difference",
                "speed_rpm",
                "shaft_surface",
            ],
        )
    )

    focuses = _focuses(result)
    assert focuses[:3] == ["pressure_or_pressure_difference", "speed", "shaft_surface"]
    assert "medium" not in focuses


def test_flat_gasket_asks_flange_pressure_material_style_question() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.flat_gasket,
            hints=["flange_standard", "pressure", "gasket_material"],
        )
    )

    assert _focuses(result)[:3] == ["flange_standard", "pressure", "gasket_material"]


def test_hydraulic_rod_seal_asks_pressure_fluid_groove_style_question() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.hydraulic_rod_seal,
            hints=["pressure", "hydraulic_fluid", "groove_dimensions"],
        )
    )

    assert _focuses(result)[:3] == ["pressure", "hydraulic_fluid", "groove_dimensions"]


def test_mechanical_seal_asks_medium_pressure_flush_or_solids_question() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.mechanical_seal,
            profile={"medium": "Wasser"},
            hints=["medium", "pressure", "flush_or_barrier_fluid", "solids_or_gas_content"],
        )
    )

    assert _focuses(result)[:3] == [
        "pressure",
        "flush_or_barrier_fluid",
        "solids_or_gas_content",
    ]


def test_o_ring_asks_dimensions_groove_material_style_question() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.o_ring,
            hints=["inner_diameter", "cross_section", "groove_dimensions", "material"],
        )
    )

    assert _focuses(result)[:3] == ["inner_diameter", "cross_section", "groove_dimensions"]


def test_general_knowledge_does_not_trigger_case_intake_question() -> None:
    result = derive_needs_current_state_and_questions(
        _state(case_type=CaseType.general_knowledge)
    )

    assert result.next_best_questions == []
    assert result.needs_analysis.primary_need == "general_technical_orientation"


def test_manufacturer_matching_asks_profile_readiness_not_partner_name() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            case_type=CaseType.manufacturer_matching,
            seal_type=SealType.radial_shaft_seal,
            profile={"sealing_type": "Wellendichtring"},
        )
    )

    question = result.next_best_questions[0]
    assert question.focus_key == "technical_profile_readiness"
    assert "Partnernamen" not in question.question
    assert "Hersteller-Fit" in question.reason


def test_compatibility_inquiry_oil_report_asks_values_units_and_oil_type() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            case_type=CaseType.compatibility_inquiry,
            seal_type=SealType.radial_shaft_seal,
            profile={"medium": "Oelanalyse mit Wasser Natrium Kalium"},
        )
    )

    assert _focuses(result)[:2] == ["oil_analysis_values", "oil_type"]
    assert "Messwerte" in result.next_best_questions[0].question


def test_complaint_failure_asks_seal_type_or_damage_evidence_without_root_cause() -> None:
    result = derive_needs_current_state_and_questions(
        _state(case_type=CaseType.failure_analysis)
    )

    text = " ".join(question.question for question in result.next_best_questions)
    assert _focuses(result)[0] == "seal_type"
    assert "finale Ursache" not in text
    assert "Root Cause" not in text


def test_replacement_legacy_asks_marking_dimensions_photo_without_identity_claim() -> None:
    result = derive_needs_current_state_and_questions(
        _state(case_type=CaseType.unknown_legacy_part)
    )

    text = " ".join(question.question for question in result.next_best_questions)
    assert _focuses(result)[:3] == ["marking", "dimensions", "photo_or_evidence"]
    assert "Identitaetsnachweis" in result.next_best_questions[0].reason
    assert "sicher identifiziert" not in text


def test_emergency_mro_returns_exactly_one_question() -> None:
    result = derive_needs_current_state_and_questions(
        _state(case_type=CaseType.emergency_mro)
    )

    assert len(result.next_best_questions) == 1
    assert result.next_best_questions[0].max_questions_policy == (
        "emergency_mro_exactly_one_question"
    )


def test_known_fields_are_not_repeated_and_max_three_questions_have_reason_and_focus() -> None:
    result = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.radial_shaft_seal,
            profile={"medium": "Oel", "pressure_bar": 1.0, "temperature_c": 80},
            hints=[
                "medium",
                "pressure_or_pressure_difference",
                "temperature",
                "speed_rpm",
                "shaft_surface",
                "shaft_diameter",
                "housing_bore",
            ],
        )
    )

    focuses = _focuses(result)
    assert len(focuses) <= 3
    assert "medium" not in focuses
    assert "pressure_or_pressure_difference" not in focuses
    assert all(question.reason and question.focus_key for question in result.next_best_questions)


def test_completeness_score_decreases_with_missing_and_conflicting_critical_fields() -> None:
    complete = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.radial_shaft_seal,
            profile={
                "medium": "Oel",
                "temperature_c": 80,
                "pressure_bar": 1,
                "speed_rpm": 1000,
                "shaft_surface": "Ra 0.3",
            },
        )
    )
    incomplete = derive_needs_current_state_and_questions(
        _state(
            seal_type=SealType.radial_shaft_seal,
            profile={"medium": "Oel"},
            hints=["pressure_or_pressure_difference", "speed_rpm", "shaft_surface"],
            conflicts_open=1,
        )
    )

    assert incomplete.completeness_score.score < complete.completeness_score.score
    assert incomplete.completeness_score.conflict_count == 1
