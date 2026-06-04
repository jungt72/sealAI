from __future__ import annotations

from app.agent.domain.requirement_class import (
    RequirementClassSpecialistInput,
    run_requirement_class_specialist,
)
from app.agent.state.models import AssertedClaim, AssertedState


def _asserted(**fields) -> AssertedState:
    return AssertedState(
        assertions={
            field_name: AssertedClaim(
                field_name=field_name,
                asserted_value=value,
                confidence="confirmed",
            )
            for field_name, value in fields.items()
        }
    )


def test_clear_ptfe_steam_case_returns_preferred_requirement_class() -> None:
    result = run_requirement_class_specialist(
        RequirementClassSpecialistInput(
            asserted_state=_asserted(
                medium="Dampf",
                pressure_bar=12.0,
                temperature_c=180.0,
                material="PTFE",
            )
        )
    )

    assert [candidate.class_id for candidate in result.requirement_class_candidates] == ["PTFE10"]
    assert result.preferred_requirement_class is not None
    assert result.preferred_requirement_class.class_id == "PTFE10"
    assert result.preferred_requirement_class.seal_type == "gasket"
    assert result.open_points == ()
    assert any("asserted PTFE material family" in item for item in result.scope_of_validity)


def test_geometry_install_hints_shape_scope_without_changing_authority() -> None:
    result = run_requirement_class_specialist(
        RequirementClassSpecialistInput(
            asserted_state=_asserted(
                medium="Wasser",
                pressure_bar=6.0,
                temperature_c=80.0,
            ),
            geometry_install_hints={"shaft_diameter_mm": 45.0, "speed_rpm": 1450},
        )
    )

    assert result.preferred_requirement_class is not None
    assert result.preferred_requirement_class.class_id == "GENERAL-B1"
    assert result.open_points == ("material",)
    assert any("rotary installation context" in item for item in result.scope_of_validity)


def test_open_case_returns_open_points_without_artificial_certainty() -> None:
    result = run_requirement_class_specialist(
        RequirementClassSpecialistInput(
            asserted_state=_asserted(
                pressure_bar=6.0,
                temperature_c=80.0,
            )
        )
    )

    assert result.requirement_class_candidates == ()
    assert result.preferred_requirement_class is None
    assert result.open_points == ("medium",)
    assert result.scope_of_validity == ("Requirement-class derivation requires a resolved medium.",)


def test_steam_without_material_stays_bounded_and_requests_follow_up_material() -> None:
    result = run_requirement_class_specialist(
        RequirementClassSpecialistInput(
            asserted_state=_asserted(
                medium="Dampf",
                pressure_bar=12.0,
                temperature_c=180.0,
            )
        )
    )

    assert result.preferred_requirement_class is not None
    assert result.preferred_requirement_class.class_id == "PTFE10"
    assert result.open_points == ("material",)
    assert any("without a confirmed material family" in item for item in result.scope_of_validity)
