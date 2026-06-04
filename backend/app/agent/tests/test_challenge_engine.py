from __future__ import annotations

from app.agent.domain.challenge_engine import build_challenge_state
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    MediumClassificationState,
    NormalizedParameter,
    NormalizedState,
)


def _state(
    assertions: dict[str, object], *, blocking: list[str] | None = None
) -> GovernedSessionState:
    return GovernedSessionState(
        asserted=AssertedState(
            assertions={
                key: AssertedClaim(field_name=key, asserted_value=value)
                for key, value in assertions.items()
            },
            blocking_unknowns=list(blocking or []),
        ),
        medium_classification=MediumClassificationState(
            canonical_label=str(assertions.get("medium") or ""),
            family="waessrig_salzhaltig",
            confidence="medium",
            status="recognized",
        ),
    )


def test_challenge_engine_builds_saltwater_hypotheses_without_release_claims() -> None:
    challenge = build_challenge_state(
        _state(
            {
                "medium": "Salzwasser",
                "sealing_type": "Radialwellendichtring",
                "motion_type": "rotierend",
                "shaft_diameter_mm": 80,
                "speed_rpm": 4000,
            },
            blocking=["pressure_bar", "temperature_c"],
        ),
        compute_results=[
            {
                "calc_type": "rwdr",
                "status": "ok",
                "v_surface_m_s": 16.76,
                "notes": ["Hohe Umfangsgeschwindigkeit braucht Gegenlaufprüfung."],
            }
        ],
    )

    assert challenge.status == "available"
    assert challenge.next_best_question is not None
    assert challenge.next_best_question.focus_key in {"pressure_bar", "temperature_c"}
    assert any(item.kind == "medium_challenge" for item in challenge.findings)
    assert any(item.kind == "derived_signal" for item in challenge.findings)
    assert {item.label for item in challenge.hypotheses} & {
        "EPDM als Prüfhypothese",
        "PTFE als Prüfhypothese",
    }
    joined = " ".join(
        [item.summary for item in challenge.findings]
        + [item.label for item in challenge.hypotheses]
        + [text for item in challenge.hypotheses for text in item.basis]
    ).casefold()
    assert "garantiert" not in joined
    assert "freigegeben" not in joined
    assert "beste lösung" not in joined
    assert "geeignet" not in joined


def test_challenge_engine_asks_medium_first_when_core_context_missing() -> None:
    challenge = build_challenge_state(
        _state(
            {"sealing_type": "O-Ring"},
            blocking=["medium", "temperature_c", "pressure_bar"],
        )
    )

    assert challenge.next_best_question is not None
    assert challenge.next_best_question.focus_key == "medium"
    assert challenge.findings[0].severity == "blocking"
    assert "ASK_NEXT_BEST_QUESTION" in challenge.action_modes_run


def test_challenge_engine_does_not_repeat_normalized_temperature_as_missing() -> None:
    state = _state(
        {"medium": "Salzsäure"},
        blocking=["pressure_bar", "temperature_c"],
    ).model_copy(
        update={
            "normalized": NormalizedState(
                parameters={
                    "temperature_c": NormalizedParameter(
                        field_name="temperature_c",
                        value=120.0,
                        unit="degC",
                        confidence="confirmed",
                    )
                }
            )
        }
    )

    challenge = build_challenge_state(state)

    assert challenge.next_best_question is not None
    assert challenge.next_best_question.focus_key == "pressure_bar"
    assert all(
        "temperature_c" not in finding.related_fields
        for finding in challenge.findings
        if finding.kind == "missing_information"
    )


def test_challenge_engine_challenges_aggressive_rotary_nbr_case() -> None:
    challenge = build_challenge_state(
        _state(
            {
                "medium": "Salzsäure",
                "medium_qualifiers": ["chemistry_detail"],
                "material": "NBR",
                "sealing_type": "Radialwellendichtring",
                "motion_type": "rotierend",
                "shaft_diameter_mm": 40,
                "speed_rpm": 3000,
                "temperature_c": 120,
            },
            blocking=["pressure_bar"],
        )
    )

    titles = {finding.title for finding in challenge.findings}
    assert "Aggressives Medium braucht Konzentration und Nebenmedien" in titles
    assert "NBR wirkt im bekannten Chemiefenster als Gegenindikator" in titles
    assert "Gegenfläche fehlt bei dynamisch relevanter Umfangsgeschwindigkeit" in titles
    assert "Schmierfilm, Flush oder Trockenlauf sind noch nicht beschrieben" in titles
    assert challenge.next_best_question is not None
    assert challenge.next_best_question.focus_key == "pressure_bar"
    assert "RUN_COUNTERINDICATOR_CHALLENGE" in challenge.action_modes_run
    assert "RUN_SURFACE_SPEED_CHALLENGE" in challenge.action_modes_run


def test_challenge_engine_flags_rwdr_pressure_direction_context() -> None:
    challenge = build_challenge_state(
        _state(
            {
                "medium": "Mineralöl",
                "sealing_type": "RWDR",
                "pressure_bar": 2,
            }
        )
    )

    pressure_finding = next(
        finding
        for finding in challenge.findings
        if finding.title == "RWDR-Druck muss als Dichtstellendruck verifiziert werden"
    )
    assert pressure_finding.severity == "watch"
    assert "pressure_direction" in pressure_finding.related_fields


# ---------------------------------------------------------------------------
# P1-4 PR2 — characterization freeze: engineering_path routing
#
# Locks the four `engineering_path == "rwdr"` sites (the :574 rotary_context leg
# + the :719/:755/:787 pressure findings) BEFORE they are routed through
# pack_for_engineering_path(...). The rwdr-gated findings must fire on an rwdr
# path and stay absent on a matched non-rwdr (static) path — the routing change
# is 1:1, so these results must be byte-identical pre/post.
# ---------------------------------------------------------------------------

_T_PRESSURE_AT_SEAL = "RWDR-Druck muss als Dichtstellendruck verifiziert werden"
_T_SYSTEM_PRESSURE = "Systemdruck ist nicht der Dichtstellendruck"
_T_AMBIGUOUS_PRESSURE = "Druckrolle ist unklar"
_T_ROTARY_COUNTERFACE = (
    "Gegenfläche fehlt bei dynamisch relevanter Umfangsgeschwindigkeit"
)
_T_LUBRICATION = "Schmierfilm, Flush oder Trockenlauf sind noch nicht beschrieben"


def _finding_titles(challenge) -> set[str]:
    return {finding.title for finding in challenge.findings}


class TestEngineeringPathRoutingFreeze:
    def test_rwdr_pressure_at_seal_finding_fires(self) -> None:
        titles = _finding_titles(
            build_challenge_state(
                _state(
                    {"medium": "Mineralöl", "sealing_type": "RWDR", "pressure_bar": 2}
                )
            )
        )
        assert _T_PRESSURE_AT_SEAL in titles

    def test_rwdr_system_pressure_finding_fires(self) -> None:
        titles = _finding_titles(
            build_challenge_state(
                _state(
                    {
                        "medium": "Mineralöl",
                        "sealing_type": "RWDR",
                        "pressure_system_bar": 5,
                    }
                )
            )
        )
        assert _T_SYSTEM_PRESSURE in titles
        assert _T_PRESSURE_AT_SEAL not in titles  # if/elif chain — only one fires

    def test_rwdr_ambiguous_pressure_finding_fires(self) -> None:
        titles = _finding_titles(
            build_challenge_state(
                _state(
                    {
                        "medium": "Mineralöl",
                        "sealing_type": "RWDR",
                        "ambiguous_pressure_bar": 5,
                    }
                )
            )
        )
        assert _T_AMBIGUOUS_PRESSURE in titles

    def test_rwdr_rotary_context_findings_fire(self) -> None:
        titles = _finding_titles(
            build_challenge_state(
                _state(
                    {
                        "medium": "Salzsäure",
                        "medium_qualifiers": ["chemistry_detail"],
                        "material": "NBR",
                        "sealing_type": "Radialwellendichtring",
                        "motion_type": "rotierend",
                        "shaft_diameter_mm": 40,
                        "speed_rpm": 3000,
                        "temperature_c": 120,
                    },
                    blocking=["pressure_bar"],
                )
            )
        )
        assert _T_ROTARY_COUNTERFACE in titles
        assert _T_LUBRICATION in titles

    def test_non_rwdr_static_path_suppresses_rwdr_findings(self) -> None:
        # Same pressure/speed inputs but a static sealing type → engineering_path
        # != "rwdr" (and no rotary text markers); none of the rwdr-gated findings
        # may fire. This is the discriminating freeze for the routing change.
        titles = _finding_titles(
            build_challenge_state(
                _state(
                    {
                        "medium": "Mineralöl",
                        "sealing_type": "Flachdichtung",
                        "motion_type": "statisch",
                        "pressure_bar": 2,
                        "shaft_diameter_mm": 40,
                        "speed_rpm": 3000,
                    }
                )
            )
        )
        assert _T_PRESSURE_AT_SEAL not in titles
        assert _T_SYSTEM_PRESSURE not in titles
        assert _T_AMBIGUOUS_PRESSURE not in titles
        assert _T_ROTARY_COUNTERFACE not in titles
        assert _T_LUBRICATION not in titles
