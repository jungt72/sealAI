"""P4a Parameter-Extraction Node for SEALAI v4.4.0 (Sprint 6).

Deterministic type-safe mapping from WorkingProfile to CalcInput fields.
No LLM — WorkingProfile already has typed values from P1 (LLM extraction).
P4a validates and transforms the profile into calculation-ready parameters.
"""

from __future__ import annotations

from typing import Any, Dict

import structlog
from pydantic import ValidationError

from app._legacy_v2.phase import PHASE
from app._legacy_v2.state import SealAIState
from app._legacy_v2.utils.messages import latest_user_text
from app.mcp.calc_schemas import CalcInput

logger = structlog.get_logger("rag.nodes.p4a_extract")


# ---------------------------------------------------------------------------
# Mapping helper
# ---------------------------------------------------------------------------


def _map_profile_to_calc_input(state: SealAIState) -> Dict[str, Any]:
    """Map WorkingProfile fields to CalcInput-compatible dict.

    Direct field mapping — no LLM involved.
    """
    wp = state.working_profile.engineering_profile
    if wp is None:
        return {}

    params: Dict[str, Any] = {}

    # Required fields
    if wp.pressure_max_bar is not None:
        params["pressure_max_bar"] = wp.pressure_max_bar
    if wp.temperature_max_c is not None:
        params["temperature_max_c"] = wp.temperature_max_c

    # Optional fields — direct mapping
    if wp.flange_standard is not None:
        params["flange_standard"] = wp.flange_standard
    if wp.flange_dn is not None:
        params["flange_dn"] = wp.flange_dn
    if wp.flange_pn is not None:
        params["flange_pn"] = wp.flange_pn
    if wp.flange_class is not None:
        params["flange_class"] = wp.flange_class
    if wp.bolt_count is not None:
        params["bolt_count"] = wp.bolt_count
    if wp.bolt_size is not None:
        params["bolt_size"] = wp.bolt_size
    if wp.medium is not None:
        params["medium"] = wp.medium
    params["cyclic_load"] = wp.cyclic_load

    return params


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p4a_extract(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P4a Parameter-Extraction — deterministic mapping from WorkingProfile to CalcInput.

    Skips extraction if gap_report indicates critical fields are missing
    (recommendation_ready == False).
    """
    gap_report = state.reasoning.gap_report or {}
    recommendation_ready = gap_report.get("recommendation_ready", state.reasoning.recommendation_ready)
    user_text = (latest_user_text(state.conversation.messages) or "").strip()

    logger.info(
        "p4a_extract_start",
        has_working_profile=state.working_profile.engineering_profile is not None,
        recommendation_ready=recommendation_ready,
        user_text_len=len(user_text),
        run_id=state.system.run_id,
        thread_id=state.conversation.thread_id,
    )
    existing_normalized_params = dict(
        state.working_profile.normalized_profile
        or state.working_profile.extracted_params
        or {}
    )
    params_dict = _map_profile_to_calc_input(state)
    merged_extracted_params = dict(existing_normalized_params)
    merged_extracted_params.update({key: value for key, value in params_dict.items() if value is not None})

    # Skip if critical fields are missing
    if not recommendation_ready:
        logger.info(
            "p4a_extract_skip",
            reason="recommendation_not_ready",
            run_id=state.system.run_id,
        )
        return {
            "working_profile": {
                "engineering_profile": state.working_profile.engineering_profile,
                "normalized_profile": merged_extracted_params,
                "extracted_params": merged_extracted_params,
            },
            "reasoning": {
                "phase": PHASE.EXTRACTION,
                "last_node": "node_p4a_extract",
            },
        }

    # Check we have the required fields for CalcInput
    if "pressure_max_bar" not in params_dict or "temperature_max_c" not in params_dict:
        logger.info(
            "p4a_extract_skip",
            reason="missing_required_fields",
            available_keys=sorted(params_dict.keys()),
            run_id=state.system.run_id,
        )
        return {
            "working_profile": {
                "engineering_profile": state.working_profile.engineering_profile,
                "normalized_profile": merged_extracted_params,
                "extracted_params": merged_extracted_params,
            },
            "reasoning": {
                "phase": PHASE.EXTRACTION,
                "last_node": "node_p4a_extract",
            },
            "system": {
                "error": "P4a: pressure_max_bar and temperature_max_c required for calculation.",
            },
        }

    # Validate via CalcInput Pydantic model
    try:
        validated = CalcInput.model_validate(params_dict)
        validated_dict = validated.model_dump(exclude_none=True)
    except ValidationError as exc:
        logger.warning(
            "p4a_extract_validation_error",
            error=str(exc),
            params_keys=sorted(params_dict.keys()),
            run_id=state.system.run_id,
        )
        return {
            "working_profile": {
                "engineering_profile": state.working_profile.engineering_profile,
                "normalized_profile": merged_extracted_params,
                "extracted_params": merged_extracted_params,
            },
            "reasoning": {
                "phase": PHASE.EXTRACTION,
                "last_node": "node_p4a_extract",
            },
            "system": {"error": f"P4a validation error: {exc}"},
        }

    logger.info(
        "p4a_extract_done",
        extracted_keys=sorted(validated_dict.keys()),
        run_id=state.system.run_id,
    )

    merged_extracted_params.update(validated_dict)

    return {
        "working_profile": {
            "engineering_profile": state.working_profile.engineering_profile,
            "normalized_profile": merged_extracted_params,
            "extracted_params": merged_extracted_params,
        },
        "reasoning": {
            "phase": PHASE.EXTRACTION,
            "last_node": "node_p4a_extract",
        },
    }


__all__ = ["node_p4a_extract"]
