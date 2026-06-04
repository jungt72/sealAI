"""P1-4 PR4 — characterization freeze for the O-Ring screening calculations
before they are relocated out of the v92 core orchestrator into
``app.agent.domain.oring_calc`` (gap-audit C9).

Locks the end-to-end ``build_calculation_state`` O-Ring output (the five
``oring.*`` CalculationResults + their key values/statuses) so the relocation
(orchestrator injects its calc primitives into the moved function) stays
byte-identical.
"""
from __future__ import annotations

import math

from app.agent.state.models import (
    GovernedSessionState,
    ObservedExtraction,
    ObservedState,
)
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)
from app.agent.v92.orchestrator import build_calculation_state


def _oring_state() -> GovernedSessionState:
    observed = ObservedState()
    for field_name, raw_value, raw_unit in (
        ("sealing_type", "o_ring", None),
        ("oring_cross_section_mm", 5.0, "mm"),
        ("groove_depth_mm", 4.0, "mm"),
        ("groove_width_mm", 6.5, "mm"),
        ("seal_inner_diameter_mm", 50.0, "mm"),
        ("shaft_diameter_mm", 52.0, "mm"),
        ("radial_gap_mm", 0.3, "mm"),
        ("pressure_at_seal_bar", 120.0, "bar"),
        ("motion_type", "statisch", None),
    ):
        observed = observed.with_extraction(
            ObservedExtraction(
                field_name=field_name,
                raw_value=raw_value,
                raw_unit=raw_unit,
                confidence=1.0,
                turn_index=1,
            )
        )
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    return GovernedSessionState(
        observed=observed, normalized=normalized, asserted=asserted
    )


def test_oring_calculations_freeze() -> None:
    calc = build_calculation_state(_oring_state())
    oring = {
        r.calculation_id: r
        for r in calc.results
        if r.calculation_id.startswith("oring.")
    }

    # All five O-Ring screening calcs present.
    assert set(oring) == {
        "oring.groove_screening",
        "oring.squeeze_pct",
        "oring.gland_fill_pct",
        "oring.stretch_pct",
        "oring.extrusion_gap_screening",
    }

    # Deterministic geometry values + statuses (frozen).
    assert oring["oring.groove_screening"].status == "ok"

    assert oring["oring.squeeze_pct"].outputs["squeeze_pct"] == 20.0
    assert oring["oring.squeeze_pct"].status == "ok"

    expected_gland_fill = round(
        (math.pi / 4.0 * 5.0**2) / (4.0 * 6.5) * 100.0, 2
    )
    assert oring["oring.gland_fill_pct"].outputs["gland_fill_pct"] == expected_gland_fill
    assert oring["oring.gland_fill_pct"].status == "ok"

    assert oring["oring.stretch_pct"].outputs["stretch_pct"] == 4.0
    assert oring["oring.stretch_pct"].status == "ok"

    extrusion = oring["oring.extrusion_gap_screening"]
    assert extrusion.status == "warning"
    assert extrusion.outputs["expert_review_required"] is True
    assert extrusion.validity_status == "requires_expert_review"
