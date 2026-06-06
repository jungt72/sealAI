"""V1.8 §5.6 deterministic Operating-Window check (P2-L1).

Margin + flag per limit field; missing limits become a manufacturer question
(never silent); flags are screening signals, never a release.
"""

from __future__ import annotations

from app.agent.state.models import SolutionField, SolutionProfile
from app.agent.state.operating_window import (
    RWDR_OPERATING_WINDOW_COMPARISONS,
    LimitComparison,
    compute_operating_window,
)

_TEMP = (
    LimitComparison(
        limit_field="temp_max_continuous_c",
        requirement_field="temperature_c",
        label="Dauertemperatur",
        direction="req_le_limit",
    ),
)


def _solution(**limits: object) -> SolutionProfile:
    return SolutionProfile(
        solution_id="sol_x",
        state="selected",
        fields=[
            SolutionField(
                field=k,
                value=v,
                origin="datasheet_extracted",
                source_doc="doc_1",
                source_page=2,
            )
            for k, v in limits.items()
        ],
    )


def _row(ow, field):
    return next(r for r in ow.rows if r.field == field)


def test_within_limit_confirmed_is_ok() -> None:
    ow = compute_operating_window(
        {"temperature_c": 120},
        {"temperature_c": "confirmed"},
        _solution(temp_max_continuous_c=150),
        _TEMP,
    )
    row = _row(ow, "temp_max_continuous_c")
    assert row.flag == "ok"
    assert row.margin == 30.0
    assert (row.limit_source_doc, row.limit_source_page) == ("doc_1", 2)
    assert not ow.has_critical


def test_requirement_exceeds_limit_is_critical_with_question() -> None:
    ow = compute_operating_window(
        {"temperature_c": 180},
        {"temperature_c": "confirmed"},
        _solution(temp_max_continuous_c=150),
        _TEMP,
    )
    row = _row(ow, "temp_max_continuous_c")
    assert row.flag == "critical"
    assert row.suggested_manufacturer_question  # never silent
    assert ow.has_critical


def test_tight_margin_is_clarify() -> None:
    ow = compute_operating_window(
        {"temperature_c": 145},
        {"temperature_c": "confirmed"},
        _solution(temp_max_continuous_c=150),
        _TEMP,
    )
    assert _row(ow, "temp_max_continuous_c").flag == "clarify"  # 5 < 10% of 150


def test_unconfirmed_requirement_is_clarify_even_within_limit() -> None:
    ow = compute_operating_window(
        {"temperature_c": 100},
        {"temperature_c": "candidate"},
        _solution(temp_max_continuous_c=150),
        _TEMP,
    )
    assert _row(ow, "temp_max_continuous_c").flag == "clarify"


def test_missing_limit_yields_manufacturer_question_not_silence() -> None:
    ow = compute_operating_window(
        {"temperature_c": 100},
        {"temperature_c": "confirmed"},
        _solution(),  # no temp limit on the datasheet
        _TEMP,
    )
    row = _row(ow, "temp_max_continuous_c")
    assert row.flag == "limit_unknown"
    assert "Datenblatt" in (row.suggested_manufacturer_question or "")
    assert ow.has_unknown_limit


def test_missing_requirement_is_clarify_open() -> None:
    ow = compute_operating_window({}, {}, _solution(temp_max_continuous_c=150), _TEMP)
    row = _row(ow, "temp_max_continuous_c")
    assert row.flag == "clarify"
    assert row.note == "Anforderung offen"


def test_none_solution_makes_every_row_limit_unknown() -> None:
    ow = compute_operating_window(
        {"temperature_c": 100}, {"temperature_c": "confirmed"}, None, _TEMP
    )
    assert _row(ow, "temp_max_continuous_c").flag == "limit_unknown"


def test_dry_run_required_but_not_capable_is_critical() -> None:
    comp = (
        LimitComparison(
            limit_field="dry_run_capable",
            requirement_field="dry_running_required",
            label="Trockenlauf",
            direction="capability_required",
        ),
    )
    ow = compute_operating_window(
        {"dry_running_required": True},
        {"dry_running_required": "confirmed"},
        _solution(dry_run_capable=False),
        comp,
    )
    row = _row(ow, "dry_run_capable")
    assert row.flag == "critical"
    assert row.suggested_manufacturer_question


def test_min_temperature_below_limit_is_critical() -> None:
    comp = (
        LimitComparison(
            limit_field="temp_min_continuous_c",
            requirement_field="temperature_min_c",
            label="Min. Dauertemperatur",
            direction="req_ge_limit",
        ),
    )
    ow = compute_operating_window(
        {"temperature_min_c": -50},
        {"temperature_min_c": "confirmed"},
        _solution(temp_min_continuous_c=-40),
        comp,
    )
    assert _row(ow, "temp_min_continuous_c").flag == "critical"  # -50 < -40


def test_rwdr_spec_is_usable_end_to_end() -> None:
    ow = compute_operating_window(
        {"temperature_c": 120, "v_surface_m_s": 8.0, "pressure_bar": 0.3},
        {
            "temperature_c": "confirmed",
            "v_surface_m_s": "calculated",
            "pressure_bar": "confirmed",
        },
        _solution(temp_max_continuous_c=150, v_max_m_s=12.0, p_max_bar=0.5),
        RWDR_OPERATING_WINDOW_COMPARISONS,
    )
    # 5 comparisons in the RWDR spec → 5 rows; the two unfilled limits are unknown
    assert len(ow.rows) == len(RWDR_OPERATING_WINDOW_COMPARISONS)
    assert ow.has_unknown_limit  # temp_min + dry_run not on this datasheet
    assert not ow.has_critical
    # a deterministic "calculated" v_surface within limit reads ok (confident)
    assert _row(ow, "v_max_m_s").flag == "ok"
