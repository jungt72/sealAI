"""LangGraph v2 Fast-Brain Runtime.

This module provides the Fast-Brain orchestration logic, allowing the chat
endpoint to handle simple turns quickly without activating the full LangGraph
Slow-Brain runtime.
"""
from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache
from typing import Any, AsyncIterator, Dict

from fastapi import Request
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.api.v1.utils.state_access import (
    _conversation_value,
    _working_profile_value,
    _reasoning_value,
    _merge_state_like,
    _state_values_to_dict,
)
from app.api.v1.sse_runtime import (
    _build_state_update_payload,
    _eventsource_event,
)

logger = logging.getLogger(__name__)

SSE_DEBUG = os.getenv("SEALAI_SSE_DEBUG") == "1"
PARAM_SYNC_DEBUG = os.getenv("SEALAI_PARAM_SYNC_DEBUG") == "1"
PARAMETERS_PATCH_AS_NODE = "node_p1_context"


def sanitize_v2_parameter_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Strip None and empty-string values from a parameter patch dict."""
    return {k: v for k, v in (patch or {}).items() if v is not None and v != ""}


def stage_extracted_parameter_patch(
    existing_extracted: Dict[str, Any],
    parameter_patch: Dict[str, Any],
    existing_extracted_provenance: Dict[str, Any],
    existing_extracted_identity: Dict[str, Any],
    source: str = "fast_brain_extracted",
    *,
    existing_observed_inputs: Dict[str, Any] | None = None,
) -> tuple:
    """Merge an extracted parameter patch into the existing extracted profile."""
    merged = dict(existing_extracted)
    merged.update(parameter_patch)
    applied = list(parameter_patch.keys())
    return (
        merged,
        existing_extracted_provenance,
        existing_extracted_identity,
        applied,
        existing_observed_inputs or {},
    )


@lru_cache(maxsize=1)
def _get_fast_brain_router() -> Any:
    # Residual compat only: FastBrain is constructed lazily so the productive
    # stack does not depend on it at module-import time.
    from app.services.fast_brain.router import FastBrainRouter  # noqa: PLC0415

    model = os.getenv("SEALAI_FAST_BRAIN_MODEL", "gpt-4o-mini")
    try:
        temperature = float(os.getenv("SEALAI_FAST_BRAIN_TEMPERATURE", "0"))
    except ValueError:
        temperature = 0.0
    return FastBrainRouter(model=model, temperature=temperature)


def _extract_fast_brain_history(state_values: Dict[str, Any]) -> list[Any]:
    history = _conversation_value(state_values, "messages")
    return list(history) if isinstance(history, list) else []


def _normalize_fast_brain_status(result: Dict[str, Any]) -> str:
    status = str(result.get("status") or "").strip()
    if status in {"chat_continue", "handoff_to_langgraph"}:
        return status
    if result.get("handoff_to_slow_brain"):
        return "handoff_to_langgraph"
    return "chat_continue"


def _coerce_fast_brain_state_patch(result: Dict[str, Any]) -> Dict[str, Any]:
    raw_patch = result.get("state_patch")
    if not isinstance(raw_patch, dict):
        return {}

    patch: Dict[str, Any] = {}
    raw_parameters = raw_patch.get("parameters")
    if isinstance(raw_parameters, dict):
        try:
            parameters = sanitize_v2_parameter_patch(raw_parameters)
        except ValueError:
            logger.exception("fast_brain_state_patch_invalid_parameters", extra={"parameters": raw_parameters})
        else:
            if parameters:
                patch["parameters"] = parameters

    raw_working_profile = raw_patch.get("working_profile")
    if isinstance(raw_working_profile, dict):
        working_profile_patch: Dict[str, Any] = {}
        live_calc_tile = raw_working_profile.get("live_calc_tile")
        if isinstance(live_calc_tile, dict):
            working_profile_patch["live_calc_tile"] = dict(live_calc_tile)
        calc_results = raw_working_profile.get("calc_results")
        if isinstance(calc_results, dict):
            working_profile_patch["calc_results"] = dict(calc_results)
        if working_profile_patch:
            patch["working_profile"] = working_profile_patch

    return patch


def _fast_brain_profile_mirrors(parameters: Dict[str, Any]) -> Dict[str, Any]:
    mirrors: Dict[str, Any] = {}
    if "medium" in parameters:
        mirrors["medium"] = parameters.get("medium")
    if "pressure_bar" in parameters:
        mirrors["pressure_bar"] = parameters.get("pressure_bar")
    temperature_value = parameters.get("temperature_c")
    if temperature_value is None:
        temperature_value = parameters.get("temperature_C")
    if temperature_value is not None:
        mirrors["temperature_c"] = temperature_value
    return mirrors


async def _get_graph_state_values_for_stream(graph: Any, config: Any) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    try:
        snapshot = await graph.aget_state(config)
        if hasattr(snapshot, "values"):
            values = _state_values_to_dict(snapshot.values)
    except Exception:
        logger.exception("langgraph_v2_stream_aget_state_failed")
    return values


async def _sync_fast_brain_checkpoint_state(
    *,
    graph: Any,
    config: Dict[str, Any],
    user_input: str,
    fast_brain_result: Dict[str, Any],
    request_id: str | None,
    persist_transcript: bool,
) -> Dict[str, Any]:
    """Merge Fast-Brain discoveries into the LangGraph checkpoint before handoff.

    This is the state bridge between the two execution speeds.
    """
    state_values = await _get_graph_state_values_for_stream(graph, config)
    patch = _coerce_fast_brain_state_patch(fast_brain_result)
    parameter_patch = patch.get("parameters") if isinstance(patch.get("parameters"), dict) else {}
    existing_extracted = (
        _working_profile_value(state_values, "normalized_profile")
        or _working_profile_value(state_values, "extracted_params")
        or {}
    )
    existing_extracted_provenance = _reasoning_value(state_values, "extracted_parameter_provenance") or {}
    existing_extracted_identity = _reasoning_value(state_values, "extracted_parameter_identity") or {}
    existing_observed_inputs = _reasoning_value(state_values, "observed_inputs") or {}

    merged_extracted = dict(existing_extracted)
    merged_extracted_provenance = dict(existing_extracted_provenance)
    merged_extracted_identity = dict(existing_extracted_identity)
    merged_observed_inputs = dict(existing_observed_inputs)
    applied_fields: list[str] = []
    rejected_fields: list[Dict[str, Any]] = []

    if parameter_patch:
        (
            merged_extracted,
            merged_extracted_provenance,
            merged_extracted_identity,
            applied_fields,
            merged_observed_inputs,
        ) = stage_extracted_parameter_patch(
            existing_extracted,
            parameter_patch,
            existing_extracted_provenance,
            existing_extracted_identity,
            source="fast_brain_extracted",
            existing_observed_inputs=existing_observed_inputs,
        )

    updates: Dict[str, Any] = {}
    working_profile_patch = patch.get("working_profile") if isinstance(patch.get("working_profile"), dict) else {}
    working_profile_update: Dict[str, Any] = {}
    if parameter_patch:
        working_profile_update["normalized_profile"] = merged_extracted
        working_profile_update["extracted_params"] = merged_extracted
    if isinstance(working_profile_patch.get("live_calc_tile"), dict):
        working_profile_update["live_calc_tile"] = dict(working_profile_patch["live_calc_tile"])
    if isinstance(working_profile_patch.get("calc_results"), dict):
        working_profile_update["calc_results"] = dict(working_profile_patch["calc_results"])
    if working_profile_update:
        updates["working_profile"] = working_profile_update
    if parameter_patch:
        updates["reasoning"] = {
            "extracted_parameter_provenance": merged_extracted_provenance,
            "extracted_parameter_identity": merged_extracted_identity,
            "observed_inputs": merged_observed_inputs,
        }

    if persist_transcript:
        transcript_messages: list[BaseMessage] = []
        user_text = str(user_input or "").strip()
        if user_text:
            transcript_messages.append(HumanMessage(content=user_text))
        assistant_text = str(fast_brain_result.get("content") or "").strip()
        if assistant_text:
            transcript_messages.append(AIMessage(content=assistant_text))
        if transcript_messages:
            updates["conversation"] = {"messages": transcript_messages}

    if not updates:
        return state_values

    await graph.aupdate_state(config, updates, as_node=PARAMETERS_PATCH_AS_NODE)

    if parameter_patch and (PARAM_SYNC_DEBUG or SSE_DEBUG):
        configurable = config.get("configurable") if isinstance(config, dict) else {}
        logger.info(
            "fast_brain_checkpoint_sync",
            extra={
                "request_id": request_id,
                "thread_id": configurable.get("thread_id") if isinstance(configurable, dict) else None,
                "applied_fields": applied_fields,
                "rejected_fields": rejected_fields,
            },
        )

    merged_state = _merge_state_like(state_values, updates)
    return _state_values_to_dict(merged_state)


async def _fast_brain_sse_stream(
    *,
    request: Request,
    thread_id: str,
    fast_brain_result: Dict[str, Any],
    state_values: Dict[str, Any],
) -> AsyncIterator[Dict[str, Any]]:
    """Stream a completed Fast-Brain answer as SSE without activating LangGraph."""
    try:
        payload = _build_state_update_payload(state_values)
        payload_data = payload.get("data") if isinstance(payload, dict) else None
        should_emit_state = False
        if isinstance(payload_data, dict):
            should_emit_state = bool(
                payload_data.get("working_profile")
                or payload_data.get("live_calc_tile")
                or payload_data.get("calc_results")
            )
        if should_emit_state and not await request.is_disconnected():
            yield _eventsource_event("state_update", payload)

        text = str(fast_brain_result.get("content") or "").strip()
        if not await request.is_disconnected():
            yield _eventsource_event("turn_complete", {"type": "turn_complete"})
            done_payload = {"type": "done", "chat_id": thread_id}
            if text:
                done_payload["final_text"] = text
                done_payload["final_answer"] = text
            yield _eventsource_event("done", done_payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("fast_brain_sse_stream_failed", extra={"thread_id": thread_id})
        if not await request.is_disconnected():
            yield _eventsource_event("error", {"type": "error", "message": "internal_error"})
            yield _eventsource_event("turn_complete", {"type": "turn_complete"})
            yield _eventsource_event("done", {"type": "done", "chat_id": thread_id})
    finally:
        from app.api.v1.endpoints.langgraph_v2 import _release_thread_lock
        await _release_thread_lock(thread_id)
