"""
compute_node — Phase F-C.1, Zone 5

Deterministic domain calculations.

Responsibility:
    Read AssertedState, adapt current graph assertions into the canonical
    cascading calculation engine input shape, and store results as dicts in
    state.compute_results.

Architecture invariants enforced here:
    - No LLM call. No I/O. No side effects.
    - Reads exclusively from state.asserted.assertions.
    - Writes exclusively to state.compute_results.
    - ObservedState, NormalizedState, AssertedState, GovernanceState unchanged.
    - Fails open: on any calc error, compute_results stays [] and the error
      is logged — never raises to the caller.

Dispatch logic (Phase F):
    RWDR cascade — triggered when BOTH of these are asserted:
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

import logging
from typing import Any

from langgraph.config import get_stream_writer

from app.agent.graph import GraphState
from app.services.calculation_engine import (
    CascadingCalculationEngine,
    CalcExecutionRecord,
)

log = logging.getLogger(__name__)


def _emit_progress_event(payload: dict) -> None:
    try:
        get_stream_writer()(payload)
    except RuntimeError:
        return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_usable(assertions: dict, field: str) -> bool:
    """True only when the field is asserted at a calc-usable confidence.

    Conflicting / unconfirmed fields (``requires_confirmation``) are excluded so
    they never drive deterministic calculations (§12.6).
    """
    claim = assertions.get(field)
    if claim is None:
        return False
    return getattr(claim, "confidence", None) in ("confirmed", "estimated")


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


def _material_family(assertions: dict) -> str:
    material = (
        (
            _str_or_none(assertions, "sealing_material_family")
            or _str_or_none(assertions, "material_family")
            or _str_or_none(assertions, "compound_family")
            or _str_or_none(assertions, "material")
            or ""
        )
        .strip()
        .lower()
    )
    if material.startswith("ptfe"):
        return material if material != "ptfe" else "ptfe_mixed_filled"
    return material or "unknown"


def _build_canonical_case(assertions: dict) -> dict[str, Any]:
    """Adapt current asserted graph fields to CascadingCalculationEngine input."""
    case: dict[str, Any] = {
        "engineering_path": "rwdr",
        "sealing_material_family": _material_family(assertions),
        "shaft": {
            "diameter_mm": float(assertions["shaft_diameter_mm"].asserted_value),
        },
        "operating": {
            "shaft_speed": {
                "rpm_nom": float(assertions["speed_rpm"].asserted_value),
            },
        },
    }

    pressure = _float_or_none(assertions, "pressure_at_seal_bar")
    if pressure is None:
        pressure = _float_or_none(assertions, "pressure_delta_bar")
    if pressure is not None:
        case["operating"]["pressure"] = {"max_bar": pressure}

    sealing_type = _str_or_none(assertions, "sealing_type")
    if sealing_type:
        case["sealing_type"] = sealing_type

    temperature = _float_or_none(assertions, "temperature_c")
    if temperature is not None:
        case["operating"]["temperature"] = {
            "max_c": temperature,
            "nom_c": temperature,
        }

    return case


def _records_payload(records: list[CalcExecutionRecord]) -> list[dict[str, Any]]:
    return [
        {
            "calc_id": record.calc_id,
            "version": record.version,
            "inputs_used": dict(record.inputs_used),
            "outputs_produced": dict(record.outputs_produced),
            "provenance": record.provenance,
        }
        for record in records
    ]


def _status_from_derived(assertions: dict, derived: dict[str, Any]) -> str:
    speed = derived.get("surface_speed_ms")
    material = (_str_or_none(assertions, "material") or "").upper()
    if speed is None:
        return "insufficient_data"
    if material == "NBR" and float(speed) > 12.0:
        return "warning"
    return "ok"


def _notes_from_derived(assertions: dict, derived: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    speed = derived.get("surface_speed_ms")
    material = (_str_or_none(assertions, "material") or "").upper()
    if material == "NBR" and speed is not None and float(speed) > 12.0:
        notes.append("Surface speed exceeds the current NBR orientation limit.")
    return notes


def _canonical_result_to_compute_result(
    *,
    assertions: dict,
    state_after_cascade: dict[str, Any],
    records: list[CalcExecutionRecord],
) -> dict[str, Any]:
    derived = dict(state_after_cascade.get("derived") or {})
    return {
        "calc_type": "rwdr",
        "status": _status_from_derived(assertions, derived),
        "v_surface_m_s": derived.get("surface_speed_ms"),
        "pv_value_mpa_m_s": derived.get("pv_value_mpa_m_s"),
        "dn_value": derived.get("dn_value"),
        "temperature_headroom_c": derived.get("temperature_headroom_c"),
        "pressure_window": derived.get("pressure_window"),
        "notes": _notes_from_derived(assertions, derived),
        "calculation_records": _records_payload(records),
        "provenance": "calculated",
        "calculation_engine": "CascadingCalculationEngine",
    }


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
    # Only usable (confirmed/estimated) values drive the deterministic cascade;
    # a conflicting field carries confidence "requires_confirmation" and must
    # not feed calculations (§12.6 — conflicts stay open points).
    if _is_usable(assertions, "shaft_diameter_mm") and _is_usable(
        assertions, "speed_rpm"
    ):
        try:
            case = _build_canonical_case(assertions)
            calculated_state, records = CascadingCalculationEngine().execute_cascade(
                case
            )
            result_dict = _canonical_result_to_compute_result(
                assertions=assertions,
                state_after_cascade=calculated_state,
                records=records,
            )
            results.append(result_dict)
            log.debug(
                "[compute_node] RWDR calc: status=%s v_surface=%.2f pv=%.3f notes=%d",
                result_dict.get("status"),
                result_dict.get("v_surface_m_s") or 0.0,
                result_dict.get("pv_value_mpa_m_s") or 0.0,
                len(result_dict.get("notes") or []),
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
            _is_usable(assertions, "shaft_diameter_mm"),
            _is_usable(assertions, "speed_rpm"),
        )

    if not results:
        return state

    return state.model_copy(update={"compute_results": results})
