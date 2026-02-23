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

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import CalcResults, SealAIState
from app.langgraph_v2.utils.jinja import render_template
from app.mcp.calc_engine import mcp_calc_gasket
from app.mcp.calc_schemas import CalcInput, CalcOutput

logger = structlog.get_logger("rag.nodes.p4b_calc_render")

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 0.1
_TEMPLATE_NAME = "engineering_report.j2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    return ctx


def _calc_output_to_calc_results(calc_output: CalcOutput) -> CalcResults:
    """Map CalcOutput to the existing CalcResults model for final-answer compatibility."""
    return CalcResults(
        safety_factor=calc_output.safety_factor,
        temperature_margin=calc_output.temperature_margin_c,
        pressure_margin=calc_output.pressure_margin_bar,
        notes=list(calc_output.notes) + list(calc_output.warnings),
    )


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p4b_calc_render(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P4b Calc + Render — call MCP calc engine and render Jinja2 report.

    Skips if extracted_params is empty (P4a determined calculation is not possible).
    """
    extracted_params = state.extracted_params or {}

    logger.info(
        "p4b_calc_render_start",
        has_params=bool(extracted_params),
        param_keys=sorted(extracted_params.keys()) if extracted_params else [],
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    if not extracted_params:
        logger.info(
            "p4b_calc_render_skip",
            reason="empty_extracted_params",
            run_id=state.run_id,
        )
        return {
            "phase": PHASE.CALCULATION,
            "last_node": "node_p4b_calc_render",
        }

    # --- Build CalcInput ---
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
    calc_output: CalcOutput | None = None
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
            "calc_results": _calc_output_to_calc_results(calc_output),
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
            "calc_results": _calc_output_to_calc_results(calc_output),
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
        "calc_results": _calc_output_to_calc_results(calc_output),
        "is_critical_application": calc_output.is_critical_application,
        "phase": PHASE.CALCULATION,
        "last_node": "node_p4b_calc_render",
    }


__all__ = ["node_p4b_calc_render"]
