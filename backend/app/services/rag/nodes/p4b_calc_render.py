"""P4b MCP Calc + Jinja2 Render Node for SEALAI v4.4.0 (Sprint 6/8).

Calls the MCP calc engine (pure Python, no LLM — R1 enforced) and renders
the engineering report via Jinja2 StrictUndefined (R2 enforced).
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from jinja2 import UndefinedError
from pydantic import ValidationError
from langchain_core.messages import AIMessage

from app._legacy_v2.phase import PHASE
from app._legacy_v2.state import CalcResults, SealAIState, LiveCalcTile
from app._legacy_v2.utils.assertion_cycle import stamp_patch_with_assertion_binding
from app._legacy_v2.utils.jinja import render_template
from app.mcp.calc_engine import mcp_calc_gasket
from app.mcp.calc_schemas import CalcInput, CalcOutput
from app.services.rag.nodes.p4_live_calc import (
    calc_tribology,
    calc_chemical_resistance,
    _collect_parameter_payload,
    _collect_captured_parameters,
)

logger = structlog.get_logger("rag.nodes.p4b_calc_render")

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 0.1
_TEMPLATE_NAME = "engineering_report.j2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_float(value: Any) -> float | None:
    """Safely cast incoming variables to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None

def _build_template_context(
    calc_input: CalcInput,
    calc_output: CalcOutput,
    state: SealAIState,
    tribo: dict[str, Any],
    chem: dict[str, Any],
) -> dict[str, Any]:
    """Build Jinja2 template context from single-source-of-truth variables."""
    ctx = calc_output.model_dump()

    # Add core input parameters
    ctx["pressure_max_bar"] = calc_input.pressure_max_bar
    ctx["temperature_max_c"] = calc_input.temperature_max_c

    # Add WorkingProfile fields (Single Source of Truth)
    wp = state.working_profile.engineering_profile
    wp_data = wp.model_dump(exclude_none=True) if wp is not None else {}

    ctx["shaft_diameter"] = wp_data.get("shaft_diameter") or wp_data.get("shaft_d1") or wp_data.get("d1") or calc_output.gasket_inner_d_mm
    ctx["speed_rpm"] = wp_data.get("speed_rpm") or wp_data.get("rpm") or wp_data.get("n") or wp_data.get("n_max")
    ctx["medium"] = wp_data.get("medium") or calc_input.medium or "nicht angegeben"
    ctx["flange_standard"] = wp_data.get("flange_standard") or calc_input.flange_standard or "nicht angegeben"
    ctx["flange_dn"] = wp_data.get("flange_dn") or calc_input.flange_dn
    ctx["flange_pn"] = wp_data.get("flange_pn") or calc_input.flange_pn
    ctx["flange_class"] = wp_data.get("flange_class") or calc_input.flange_class
    ctx["bolt_count"] = wp_data.get("bolt_count") or calc_input.bolt_count
    ctx["bolt_size"] = wp_data.get("bolt_size") or calc_input.bolt_size or "nicht angegeben"
    ctx["cyclic_load"] = wp_data.get("cyclic_load") or calc_input.cyclic_load
    ctx["emission_class"] = wp_data.get("emission_class")
    ctx["industry_sector"] = wp_data.get("industry_sector")

    # Inject freshly calculated Physics & Chemistry (prevents state race-conditions)
    ctx["v_surface_m_s"] = tribo.get("v_surface_m_s")
    ctx["pv_value_mpa_m_s"] = tribo.get("pv_value_mpa_m_s")
    ctx["friction_power_watts"] = tribo.get("friction_power_watts")
    ctx["hrc_warning"] = tribo.get("hrc_warning", False)
    ctx["hrc_value"] = tribo.get("hrc_value")
    
    ctx["chem_warning"] = chem.get("chem_warning", False)
    ctx["chem_message"] = chem.get("chem_message", "")

    # Consolidate notes from calc output, tribology, and chemistry
    ctx["notes"] = (
        list(ctx.get("notes") or []) 
        + list(tribo.get("notes", [])) 
        + list(chem.get("notes", []))
    )

    # Make raw parameters available for template flexibility
    ctx.update(_collect_captured_parameters(state))

    return ctx


def _calc_output_to_calc_results(calc_output: CalcOutput, state: SealAIState | None = None) -> CalcResults:
    """Map CalcOutput to the existing CalcResults model for final-answer compatibility."""
    res = CalcResults(
        safety_factor=calc_output.safety_factor,
        temperature_margin=calc_output.temperature_margin_c,
        pressure_margin=calc_output.pressure_margin_bar,
        notes=list(calc_output.notes) + list(calc_output.warnings),
    )
    
    # Enrich with physics if available in state
    if state and state.working_profile.live_calc_tile:
        tile = state.working_profile.live_calc_tile
        if tile.v_surface_m_s is not None:
            res.v_surface_m_s = tile.v_surface_m_s
        if tile.pv_value_mpa_m_s is not None:
            res.pv_value_mpa_m_s = tile.pv_value_mpa_m_s
        if tile.friction_power_watts is not None:
            res.friction_power_watts = tile.friction_power_watts
        if tile.hrc_warning:
            res.hrc_warning = True
    return res


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def node_p4b_calc_render(state: SealAIState, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """P4b Calc + Render — call MCP calc engine and render Jinja2 report."""
    
    # 1. FORCE physics and chemistry calculation first
    payload = _collect_parameter_payload(state)
    tile = state.working_profile.live_calc_tile

    wp_data = _collect_parameter_payload(state)
    has_tech_params = bool(
        wp_data.get("speed_rpm") or wp_data.get("rpm") or wp_data.get("n") or
        wp_data.get("shaft_diameter") or wp_data.get("shaft_d1") or wp_data.get("d1")
    )

    # Always compute to have 100% synchronous data for both tile and context
    tribo = calc_tribology(payload, prev=tile)
    chem = calc_chemical_resistance(payload)
    v_surface = tribo.get("v_surface_m_s")

    # 2. Determine execution path
    extracted_params = wp_data
    is_fast_path = bool(
        v_surface is not None
        or state.working_profile.calc_results
        or (tile and tile.status != "insufficient_data")
    )

    logger.info(
        "p4b_calc_render_start",
        has_params=bool(extracted_params),
        is_fast_path=is_fast_path,
        has_tech_params=has_tech_params,
        run_id=state.system.run_id,
    )

    # Only skip if we have absolutely nothing
    if not extracted_params and not is_fast_path and not has_tech_params:
        logger.info("p4b_calc_render_skip", reason="no_data_at_all", run_id=state.system.run_id)
        return {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
            "reasoning": {
                "phase": PHASE.CALCULATION,
                "last_node": "node_p4b_calc_render",
            },
        }

    has_required_inputs = (
        extracted_params.get("pressure_max_bar") is not None
        and extracted_params.get("temperature_max_c") is not None
    )

    calc_input: CalcInput | None = None
    calc_output: CalcOutput | None = None

    # --- Build CalcInput & Output ---
    if (is_fast_path or has_tech_params) and not has_required_inputs:
        # Fast-Path Mock Output
        calc_input = CalcInput(
            pressure_max_bar=extracted_params.get("pressure_max_bar") or 0.0,
            temperature_max_c=extracted_params.get("temperature_max_c") or 0.0,
            medium=extracted_params.get("medium"),
        )
        calc_output = CalcOutput(
            gasket_inner_d_mm=_coerce_float(extracted_params.get("shaft_diameter") or extracted_params.get("shaft_d1") or extracted_params.get("d1") or 0.0),
            gasket_outer_d_mm=0.0,
            required_gasket_stress_mpa=0.0,
            safety_factor=0.0,
            temperature_margin_c=0.0,
            pressure_margin_bar=0.0,
            is_critical_application=False,
            notes=["RWDR Fast-Path: Anzeige von physikalischen Kennwerten ohne Gasket-Berechnung."],
        )
    else:
        # Normal calculation path
        try:
            calc_input = CalcInput.model_validate(extracted_params)
        except ValidationError as exc:
            if is_fast_path or has_tech_params:
                calc_input = CalcInput(
                    pressure_max_bar=extracted_params.get("pressure_max_bar") or 0.0,
                    temperature_max_c=extracted_params.get("temperature_max_c") or 0.0,
                    medium=extracted_params.get("medium"),
                )
                calc_output = CalcOutput(
                    gasket_inner_d_mm=_coerce_float(extracted_params.get("shaft_diameter") or extracted_params.get("shaft_d1") or extracted_params.get("d1") or 0.0),
                    gasket_outer_d_mm=0.0,
                    required_gasket_stress_mpa=0.0,
                    safety_factor=0.0,
                    temperature_margin_c=0.0,
                    pressure_margin_bar=0.0,
                    is_critical_application=False,
                    notes=[f"Eingabewarnung: {exc}. Anzeige von Basis-Kennwerten."],
                )
            else:
                logger.warning("p4b_calc_input_invalid", error=str(exc))
                return {
                    "phase": PHASE.CALCULATION,
                    "last_node": "node_p4b_calc_render",
                    "error": f"P4b: invalid calc input: {exc}",
                    "reasoning": {
                        "phase": PHASE.CALCULATION,
                        "last_node": "node_p4b_calc_render",
                    },
                    "system": {"error": f"P4b: invalid calc input: {exc}"},
                }

        if calc_output is None:
            # Call MCP calc engine with retry
            last_error: str | None = None
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    calc_output = mcp_calc_gasket(calc_input)
                    break
                except Exception as exc:
                    last_error = str(exc)
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_BACKOFF_S * attempt)

            if calc_output is None:
                if is_fast_path or has_tech_params:
                    calc_output = CalcOutput(
                        gasket_inner_d_mm=_coerce_float(extracted_params.get("shaft_diameter") or extracted_params.get("shaft_d1") or extracted_params.get("d1") or 0.0),
                        gasket_outer_d_mm=0.0,
                        required_gasket_stress_mpa=0.0, safety_factor=0.0,
                        temperature_margin_c=0.0, pressure_margin_bar=0.0,
                        is_critical_application=False,
                        notes=[f"Berechnungsfehler: {last_error}. Zeige physikalische Kennwerte."],
                    )
                else:
                    logger.error("p4b_calc_failed", error=last_error, run_id=state.system.run_id)
                    return {
                        "phase": PHASE.CALCULATION,
                        "last_node": "node_p4b_calc_render",
                        "error": f"P4b: MCP calc engine failed after {_MAX_RETRIES} attempts: {last_error}",
                        "reasoning": {
                            "phase": PHASE.CALCULATION,
                            "last_node": "node_p4b_calc_render",
                        },
                        "system": {
                            "error": f"P4b: MCP calc engine failed after {_MAX_RETRIES} attempts: {last_error}",
                        },
                    }

    # --- Render engineering report via Jinja2 StrictUndefined (R2) ---
    template_context = _build_template_context(calc_input, calc_output, state, tribo, chem)
    rendered_report: str | None = None

    try:
        rendered_report = render_template(_TEMPLATE_NAME, template_context)
    except UndefinedError as exc:
        logger.error("p4b_jinja_undefined", error=str(exc), template=_TEMPLATE_NAME, run_id=state.system.run_id)
        calc_results = _calc_output_to_calc_results(calc_output, state)
        return stamp_patch_with_assertion_binding(state, {
            "is_critical_application": calc_output.is_critical_application,
            "calc_results": calc_results,
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
            "error": f"P4b: Jinja2 template error: {exc}",
            "working_profile": {
                "is_critical_application": calc_output.is_critical_application,
                "calc_results": calc_results,
            },
            "reasoning": {
                "phase": PHASE.CALCULATION,
                "last_node": "node_p4b_calc_render",
            },
            "system": {"error": f"P4b: Jinja2 template error: {exc}"},
        })
    except FileNotFoundError:
        logger.error("p4b_template_not_found", template=_TEMPLATE_NAME, run_id=state.system.run_id)
        calc_results = _calc_output_to_calc_results(calc_output, state)
        return stamp_patch_with_assertion_binding(state, {
            "is_critical_application": calc_output.is_critical_application,
            "calc_results": calc_results,
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
            "error": f"P4b: template '{_TEMPLATE_NAME}' not found",
            "working_profile": {
                "is_critical_application": calc_output.is_critical_application,
                "calc_results": calc_results,
            },
            "reasoning": {
                "phase": PHASE.CALCULATION,
                "last_node": "node_p4b_calc_render",
            },
            "system": {"error": f"P4b: template '{_TEMPLATE_NAME}' not found"},
        })

    # --- Build Output Result ---
    calculation_result = calc_output.model_dump()
    calculation_result["rendered_report"] = rendered_report

    # Update state tile with EXACT same data injected into the template
    if tile is None:
        tile = LiveCalcTile()

    tile.v_surface_m_s = tribo.get("v_surface_m_s")
    tile.pv_value_mpa_m_s = tribo.get("pv_value_mpa_m_s")
    tile.friction_power_watts = tribo.get("friction_power_watts")
    tile.hrc_warning = bool(tribo.get("hrc_warning"))
    tile.hrc_value = tribo.get("hrc_value")
    
    tile.chem_warning = chem.get("chem_warning", False)
    tile.chem_message = chem.get("chem_message", "")
    
    tile.parameters = _collect_captured_parameters(state)
    
    if tile.v_surface_m_s is not None:
        tile.status = "ok"

    logger.info(
        "p4b_calc_render_done",
        safety_factor=calc_output.safety_factor,
        is_critical=calc_output.is_critical_application,
        report_len=len(rendered_report) if rendered_report else 0,
        warning_count=len(calc_output.warnings),
        run_id=state.system.run_id,
    )

    calc_results = _calc_output_to_calc_results(calc_output, state)
    return stamp_patch_with_assertion_binding(state, {
        "calculation_result": calculation_result,
        "calc_results": calc_results,
        "live_calc_tile": tile,
        "is_critical_application": calc_output.is_critical_application,
        "phase": PHASE.CALCULATION,
        "last_node": "node_p4b_calc_render",
        "final_text": rendered_report,
        "final_answer": rendered_report,
        "working_profile": {
            "calculation_result": calculation_result,
            "calc_results": calc_results,
            "live_calc_tile": tile,
            "is_critical_application": calc_output.is_critical_application,
        },
        "reasoning": {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
        },
        "system": {
            "final_text": rendered_report,
            "final_answer": rendered_report,
        },
        "conversation": {"messages": [AIMessage(content=rendered_report)]},
    })

__all__ = ["node_p4b_calc_render"]
