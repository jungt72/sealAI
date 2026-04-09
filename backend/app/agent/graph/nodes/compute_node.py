"""
compute_node — Phase F-C.1, Zone 5

Deterministic domain calculations.

Responsibility:
    Read AssertedState, build typed calc inputs, run the domain calc functions
    (rwdr_calc.py), and store results as dicts in state.compute_results.

Architecture invariants enforced here:
    - No LLM call. No I/O. No side effects.
    - Reads exclusively from state.asserted.assertions.
    - Writes exclusively to state.compute_results.
    - ObservedState, NormalizedState, AssertedState, GovernanceState unchanged.
    - Fails open: on any calc error, compute_results stays [] and the error
      is logged — never raises to the caller.

Dispatch logic (Phase F):
    RWDR calc — triggered when BOTH of these are asserted:
        shaft_diameter_mm   (required: DIN 3760 formula needs diameter)
        speed_rpm           (required: DIN 3760 formula needs rotational speed)
    All other asserted fields (pressure, temperature, material, medium) are
    forwarded as optional inputs to enrich the calculation.

    Phase G will extend this with geometry checks, extrusion-gap calc, and
    thermal expansion — each guarded by their own field presence checks.

Result shape:
    Each entry in state.compute_results is a dict:
        calc_type       — "rwdr" (identifies the calc for output_contract_node)
        status          — "ok" | "warning" | "critical" | "insufficient_data"
        v_surface_m_s   — Umfangsgeschwindigkeit [m/s]
        pv_value_mpa_m_s — PV-Wert [MPa·m/s]
        ... (all RwdrCalcResult fields serialised to plain types)
        notes           — list[str] of engineering notes
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from langgraph.config import get_stream_writer

from app.agent.domain.rwdr_calc import RwdrCalcInput, calculate_rwdr
from app.agent.graph import GraphState

log = logging.getLogger(__name__)


def _emit_progress_event(payload: dict) -> None:
    try:
        get_stream_writer()(payload)
    except RuntimeError:
        return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _float_or_none(assertions: dict, field: str) -> float | None:
    """Extract a float asserted value or return None."""
    claim = assertions.get(field)
    if claim is None:
        return None
    try:
        return float(claim.asserted_value)
    except (TypeError, ValueError):
        return None


def _str_or_none(assertions: dict, field: str) -> str | None:
    """Extract a string asserted value or return None."""
    claim = assertions.get(field)
    if claim is None:
        return None
    val = claim.asserted_value
    return str(val).strip() if val is not None else None


def _build_rwdr_input(assertions: dict) -> RwdrCalcInput:
    """Build a typed RwdrCalcInput from AssertedState assertions."""
    return RwdrCalcInput(
        shaft_diameter_mm=float(assertions["shaft_diameter_mm"].asserted_value),
        rpm=float(assertions["speed_rpm"].asserted_value),
        pressure_bar=_float_or_none(assertions, "pressure_bar"),
        temperature_max_c=_float_or_none(assertions, "temperature_c"),
        surface_hardness_hrc=_float_or_none(assertions, "surface_hardness_hrc"),
        runout_mm=_float_or_none(assertions, "runout_mm"),
        clearance_gap_mm=_float_or_none(assertions, "clearance_gap_mm"),
        elastomer_material=_str_or_none(assertions, "material"),
        medium=_str_or_none(assertions, "medium"),
    )


def _rwdr_result_to_dict(result: Any) -> dict[str, Any]:
    """Serialise RwdrCalcResult (dataclass) to a plain dict.

    Adds calc_type="rwdr" so output_contract_node can identify it.
    """
    d = dataclasses.asdict(result)
    d["calc_type"] = "rwdr"
    return d


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def compute_node(state: GraphState) -> GraphState:
    """Zone 5 — Deterministic domain calculations.

    Dispatches RWDR calc when shaft_diameter_mm + speed_rpm are asserted.
    Skips silently if required inputs are absent.
    Fails open on any calculation error.
    """
    assertions = state.asserted.assertions
    results: list[dict[str, Any]] = []

    # ── RWDR calc: requires shaft_diameter_mm AND speed_rpm ───────────────
    if "shaft_diameter_mm" in assertions and "speed_rpm" in assertions:
        try:
            inp = _build_rwdr_input(assertions)
            rwdr_result = calculate_rwdr(inp)
            result_dict = _rwdr_result_to_dict(rwdr_result)
            results.append(result_dict)
            log.debug(
                "[compute_node] RWDR calc: status=%s v_surface=%.2f pv=%.3f notes=%d",
                rwdr_result.status,
                rwdr_result.v_surface_m_s or 0.0,
                rwdr_result.pv_value_mpa_m_s or 0.0,
                len(rwdr_result.notes),
            )
            _emit_progress_event(
                {
                    "event_type": "compute_complete",
                    "calc_type": "rwdr",
                    "status": result_dict.get("status"),
                }
            )
        except Exception as exc:
            log.warning(
                "[compute_node] RWDR calc failed (%s: %s) — skipping",
                type(exc).__name__,
                exc,
            )
    else:
        log.debug(
            "[compute_node] RWDR skipped — shaft_diameter_mm=%s speed_rpm=%s",
            "shaft_diameter_mm" in assertions,
            "speed_rpm" in assertions,
        )

    if not results:
        return state

    return state.model_copy(update={"compute_results": results})
