"""P4b MCP Calc + Jinja2 Render Node for SEALAI v4.4.0 (Sprint 6).

Calls the MCP calc engine (pure Python, no LLM — R1 enforced) and renders
the engineering report via Jinja2 StrictUndefined (R2 enforced).
"""

from __future__ import annotations

import time
from typing import Any, Dict

import structlog
from jinja2 import UndefinedError
from pydantic import ValidationError
from langchain_core.messages import AIMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import CalcResults, SealAIState
from app.langgraph_v2.utils.jinja import render_template
from app.mcp.calc_engine import mcp_calc_gasket
from app.mcp.calc_schemas import CalcInput, CalcOutput
from app.services.rag.nodes.p4_live_calc import (
    calc_tribology,
    calc_extrusion,
    calc_geometry,
    calc_thermal,
    _collect_parameter_payload,
)

logger = structlog.get_logger("rag.nodes.p4b_calc_render")

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 0.1
_TEMPLATE_NAME = "engineering_report.j2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_float(value: Any) -> float | None:
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


def _intent_allows_calc_bypass(state: SealAIState) -> bool:
    goal = str(getattr(getattr(state, "intent", None), "goal", "") or "").strip().lower()
    flags = getattr(state, "flags", {}) or {}
    category = str(
        getattr(state, "intent_category", None)
        or flags.get("frontdoor_intent_category")
        or ""
    ).strip().upper()
    return goal == "explanation_or_comparison" or category == "MATERIAL_RESEARCH"


def _merge_required_calc_fields(state: SealAIState, extracted_params: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(extracted_params or {})

    pressure = _coerce_float(merged.get("pressure_max_bar"))
    if pressure is None:
        pressure = _coerce_float(merged.get("pressure_bar"))
    if pressure is None:
        wp = getattr(state, "working_profile", None)
        pressure = _coerce_float(getattr(wp, "pressure_max_bar", None))
    if pressure is None:
        params = getattr(state, "parameters", None)
        pressure = _coerce_float(getattr(params, "pressure_bar", None))
    if pressure is not None:
        merged["pressure_max_bar"] = pressure

    temperature = _coerce_float(merged.get("temperature_max_c"))
    if temperature is None:
        temperature = _coerce_float(merged.get("temperature_c"))
    if temperature is None:
        wp = getattr(state, "working_profile", None)
        temperature = _coerce_float(getattr(wp, "temperature_max_c", None))
    if temperature is None:
        params = getattr(state, "parameters", None)
        temperature = _coerce_float(getattr(params, "temperature_C", None))
    if temperature is not None:
        merged["temperature_max_c"] = temperature

    return merged


def _build_template_context(
    calc_input: CalcInput,
    calc_output: CalcOutput,
    state: SealAIState,
) -> Dict[str, Any]:
    """Build Jinja2 template context from CalcInput + CalcOutput + WorkingProfile."""
    ctx = calc_output.model_dump()

    # Add input parameters (needed by template for operating conditions section)
    ctx["pressure_max_bar"] = calc_input.pressure_max_bar
    ctx["temperature_max_c"] = calc_input.temperature_max_c

    # Add WorkingProfile fields for template rendering
    wp = state.working_profile
    if wp is not None:
        ctx["medium"] = wp.medium or calc_input.medium or "nicht angegeben"
        ctx["flange_standard"] = wp.flange_standard or calc_input.flange_standard or "nicht angegeben"
        ctx["flange_dn"] = wp.flange_dn or calc_input.flange_dn
        ctx["flange_pn"] = wp.flange_pn or calc_input.flange_pn
        ctx["flange_class"] = wp.flange_class or calc_input.flange_class
        ctx["bolt_count"] = wp.bolt_count or calc_input.bolt_count
        ctx["bolt_size"] = wp.bolt_size or calc_input.bolt_size or "nicht angegeben"
        ctx["cyclic_load"] = wp.cyclic_load
        ctx["emission_class"] = wp.emission_class
        ctx["industry_sector"] = wp.industry_sector
    else:
        ctx["medium"] = calc_input.medium or "nicht angegeben"
        ctx["flange_standard"] = calc_input.flange_standard or "nicht angegeben"
        ctx["flange_dn"] = calc_input.flange_dn
        ctx["flange_pn"] = calc_input.flange_pn
        ctx["flange_class"] = calc_input.flange_class
        ctx["bolt_count"] = calc_input.bolt_count
        ctx["bolt_size"] = calc_input.bolt_size or "nicht angegeben"
        ctx["cyclic_load"] = calc_input.cyclic_load

    # --- Physics (RWDR Expert / Sprint 8) ---
    tile = state.live_calc_tile
    # If tile is empty (first turn of fast path), compute deterministic physics once for rendering
    if not tile or tile.status == "insufficient_data":
        payload = _collect_parameter_payload(state)
        tribo = calc_tribology(payload, prev=tile)
        ctx["v_surface_m_s"] = tribo.get("v_surface_m_s")
        ctx["pv_value_mpa_m_s"] = tribo.get("pv_value_mpa_m_s")
        ctx["friction_power_watts"] = tribo.get("friction_power_watts")
        ctx["hrc_warning"] = tribo.get("hrc_warning")
        ctx["hrc_value"] = tribo.get("hrc_value")
        # Ensure RWDR-specific notes (M6 limits) are added to the list of notes for rendering
        if tribo.get("notes"):
             ctx["notes"] = list(ctx.get("notes") or []) + list(tribo["notes"])
    elif tile.status != "insufficient_data":
        ctx["v_surface_m_s"] = tile.v_surface_m_s
        ctx["pv_value_mpa_m_s"] = tile.pv_value_mpa_m_s
        ctx["friction_power_watts"] = tile.friction_power_watts
        ctx["hrc_warning"] = tile.hrc_warning
        ctx["hrc_value"] = tile.hrc_value
        if tile.parameters:
            ctx.update(tile.parameters)

    return ctx


def _calc_output_to_calc_results(calc_output: CalcOutput, state: Optional[SealAIState] = None) -> CalcResults:
    """Map CalcOutput to the existing CalcResults model for final-answer compatibility."""
    res = CalcResults(
        safety_factor=calc_output.safety_factor,
        temperature_margin=calc_output.temperature_margin_c,
        pressure_margin=calc_output.pressure_margin_bar,
        notes=list(calc_output.notes) + list(calc_output.warnings),
    )
    # Enrich with physics if available in state
    if state and state.live_calc_tile:
        tile = state.live_calc_tile
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


def node_p4b_calc_render(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P4b Calc + Render — call MCP calc engine and render Jinja2 report.

    Skips if extracted_params is empty (P4a determined calculation is not possible),
    UNLESS we are in Fast-Path (physics data available).
    """
    extracted_params = _merge_required_calc_fields(state, state.extracted_params or {})

    logger.info(
        "p4b_calc_render_start",
        has_params=bool(extracted_params),
        param_keys=sorted(extracted_params.keys()) if extracted_params else [],
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    # Fast-Path check: do we already have physics or calc results?
    tile = state.live_calc_tile
    is_fast_path = bool(
        (tile and tile.v_surface_m_s is not None) or state.calc_results
    )

    if not extracted_params and not is_fast_path:
        logger.info(
            "p4b_calc_render_skip",
            reason="empty_extracted_params_no_fast_path",
            run_id=state.run_id,
        )
        return {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
        }

    has_required_inputs = (
        extracted_params.get("pressure_max_bar") is not None
        and extracted_params.get("temperature_max_c") is not None
    )

    # --- Build CalcInput & Output ---
    calc_input: CalcInput | None = None
    calc_output: CalcOutput | None = None

    if not has_required_inputs and is_fast_path:
        # Partial extraction in Fast-Path: create dummy objects for Jinja2 compatibility
        calc_input = CalcInput(
            pressure_max_bar=extracted_params.get("pressure_max_bar") or 0.0,
            temperature_max_c=extracted_params.get("temperature_max_c") or 0.0,
            medium=extracted_params.get("medium"),
        )
        calc_output = CalcOutput(
            gasket_inner_d_mm=0.0,
            gasket_outer_d_mm=0.0,
            required_gasket_stress_mpa=0.0,
            safety_factor=0.0,
            temperature_margin_c=0.0,
            pressure_margin_bar=0.0,
            is_critical_application=False,
            notes=["RWDR Fast-Path: Anzeige von physikalischen Kennwerten ohne Gasket-Berechnung."],
        )
    else:
        if _intent_allows_calc_bypass(state) and not has_required_inputs:
            logger.info(
                "p4b_calc_render_skip",
                reason="non_calculation_intent_missing_required_fields",
                run_id=state.run_id,
            )
            return {
                "phase": PHASE.CALCULATION,
                "last_node": "node_p4b_calc_render",
            }

        try:
            calc_input = CalcInput.model_validate(extracted_params)
        except ValidationError as exc:
            logger.warning(
                "p4b_calc_input_invalid",
                error=str(exc),
                run_id=state.run_id,
            )
            return {
                "phase": PHASE.CALCULATION,
                "last_node": "node_p4b_calc_render",
                "error": f"P4b: invalid calc input: {exc}",
            }

        # --- Call MCP calc engine with retry ---
        last_error: str | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                calc_output = mcp_calc_gasket(calc_input)
                break
            except Exception as exc:
                last_error = f"MCP calc attempt {attempt}/{_MAX_RETRIES} failed: {exc}"
                logger.warning(
                    "p4b_calc_retry",
                    attempt=attempt,
                    error=str(exc),
                    run_id=state.run_id,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF_S * attempt)

    if calc_output is None:
        logger.error(
            "p4b_calc_failed",
            error=last_error,
            run_id=state.run_id,
        )
        return {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
            "error": f"P4b: MCP calc engine failed after {_MAX_RETRIES} attempts: {last_error}",
        }

    # --- Render engineering report via Jinja2 StrictUndefined (R2) ---
    template_context = _build_template_context(calc_input, calc_output, state)
    rendered_report: str | None = None

    try:
        rendered_report = render_template(_TEMPLATE_NAME, template_context)
    except UndefinedError as exc:
        logger.error(
            "p4b_jinja_undefined",
            error=str(exc),
            template=_TEMPLATE_NAME,
            run_id=state.run_id,
        )
        return {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
            "error": f"P4b: Jinja2 template error: {exc}",
            "is_critical_application": calc_output.is_critical_application,
            "calc_results": _calc_output_to_calc_results(calc_output, state),
        }
    except FileNotFoundError:
        logger.error(
            "p4b_template_not_found",
            template=_TEMPLATE_NAME,
            run_id=state.run_id,
        )
        return {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
            "error": f"P4b: template '{_TEMPLATE_NAME}' not found",
            "is_critical_application": calc_output.is_critical_application,
            "calc_results": _calc_output_to_calc_results(calc_output, state),
        }

    # --- Build result ---
    calculation_result = calc_output.model_dump()
    calculation_result["rendered_report"] = rendered_report

    logger.info(
        "p4b_calc_render_done",
        safety_factor=calc_output.safety_factor,
        is_critical=calc_output.is_critical_application,
        report_len=len(rendered_report) if rendered_report else 0,
        warning_count=len(calc_output.warnings),
        run_id=state.run_id,
    )

    return {
        "calculation_result": calculation_result,
        "calc_results": _calc_output_to_calc_results(calc_output, state),
        "is_critical_application": calc_output.is_critical_application,
        "phase": PHASE.CALCULATION,
        "last_node": "node_p4b_calc_render",
        "final_text": rendered_report,
        "final_answer": rendered_report,
        "messages": [AIMessage(content=rendered_report)],
    }



__all__ = ["node_p4b_calc_render"]
