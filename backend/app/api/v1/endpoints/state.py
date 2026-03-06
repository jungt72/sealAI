# backend/app/api/v1/endpoints/state.py
"""State management endpoints for LangGraph."""

from __future__ import annotations

from datetime import datetime
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.contracts import error_detail, is_dependency_unavailable_error, pick_existing_node
from app.langgraph_v2.utils.assertion_cycle import build_assertion_cycle_update
from app.langgraph_v2.utils.parameter_patch import promote_parameter_patch_to_asserted
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.rag.state import WorkingProfile

logger = logging.getLogger(__name__)
PARAM_SYNC_DEBUG = os.getenv("SEALAI_PARAM_SYNC_DEBUG") == "1"

router = APIRouter()

METADATA_FIELDS = (
    "thread_id",
    "user_id",
    "run_id",
    "phase",
    "last_node",
    "awaiting_user_input",
    "recommendation_ready",
)

DEFAULT_STATE_UPDATE_NODE = "supervisor_policy_node"


class StateUpdate(BaseModel):
    """Request body for state updates."""

    working_profile: WorkingProfile
    source: str | None = Field(
        default=None,
        description="Optional source flag (e.g., 'ui' or 'tool').",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="Optional ISO timestamp provided by the client.",
    )


def _state_to_dict(values: Any) -> Dict[str, Any]:
    if values is None:
        return {}
    if isinstance(values, SealAIState):
        return values.model_dump(exclude_none=True)
    if isinstance(values, dict):
        return dict(values)
    try:
        return dict(values)
    except Exception:
        return {}


def _pillar_dict(state_values: Dict[str, Any], pillar: str) -> Dict[str, Any]:
    raw = state_values.get(pillar)
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(exclude_none=True)
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _state_field(state_values: Dict[str, Any], pillar: str, key: str) -> Any:
    pillar_values = _pillar_dict(state_values, pillar)
    if key in pillar_values:
        return pillar_values.get(key)
    return state_values.get(key)


def _serialize_working_profile(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, WorkingProfile):
        return raw.model_dump(exclude_none=True)
    if isinstance(raw, dict):
        return {key: value for key, value in raw.items() if value is not None}
    try:
        return {key: value for key, value in dict(raw).items() if value is not None}
    except Exception:
        return {}


def _deep_merge_updates(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (update or {}).items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_updates(existing, value)
        else:
            merged[key] = value
    return merged


def _collect_metadata(state_values: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    raw_metadata = state_values.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)
    for key in METADATA_FIELDS:
        if key in {"thread_id", "user_id"}:
            value = _state_field(state_values, "conversation", key)
        elif key == "run_id":
            value = _state_field(state_values, "system", key)
        else:
            value = _state_field(state_values, "reasoning", key)
        if value is not None:
            metadata[key] = value
    return metadata


def _sanitize_config_for_client(config: Any) -> Dict[str, Any]:
    """Expose the config to clients without attaching non-serializable objects."""
    if not config:
        return {}
    try:
        sanitized_config: Dict[str, Any] = dict(config)
    except Exception:
        return {}

    configurable = sanitized_config.get("configurable")
    if isinstance(configurable, dict):
        sanitized_config["configurable"] = {
            key: value
            for key, value in configurable.items()
            if key != CONFIG_KEY_CHECKPOINTER
        }
    return sanitized_config


def _resolve_update_as_node(state_values: Dict[str, Any]) -> str | None:
    """Pick a known node name that last mutated the state."""
    candidate = _state_field(state_values, "reasoning", "last_node")
    if isinstance(candidate, str) and candidate:
        return candidate
    metadata = state_values.get("metadata")
    if isinstance(metadata, dict):
        candidate = (
            metadata.get("last_node")
            or metadata.get("as_node")
            or metadata.get("node")
        )
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _has_state_values(snapshot: Any) -> bool:
    values = _state_to_dict(getattr(snapshot, "values", None))
    return bool(values)


async def _resolve_state_snapshot(
    *,
    thread_id: str,
    user: RequestUser,
    request_id: str | None = None,
) -> tuple[Any, Dict[str, Any], Any, bool]:
    scoped_user_id = canonical_user_id(user)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None
    try:
        graph, config = await _build_state_config_with_checkpointer(
            thread_id=thread_id, user_id=scoped_user_id, username=user.username
        )
    except TypeError:
        graph, config = await _build_state_config_with_checkpointer(
            thread_id=thread_id, user_id=scoped_user_id
        )
    snapshot = await graph.aget_state(config)
    if not legacy_user_id or _has_state_values(snapshot):
        return graph, config, snapshot, False

    try:
        legacy_graph, legacy_config = await _build_state_config_with_checkpointer(
            thread_id=thread_id, user_id=legacy_user_id, username=user.username
        )
    except TypeError:
        legacy_graph, legacy_config = await _build_state_config_with_checkpointer(
            thread_id=thread_id, user_id=legacy_user_id
        )
    legacy_snapshot = await legacy_graph.aget_state(legacy_config)
    if _has_state_values(legacy_snapshot):
        if PARAM_SYNC_DEBUG:
            logger.warning(
                "langgraph_v2_legacy_state_fallback",
                extra={
                    "request_id": request_id,
                    "thread_id": thread_id,
                    "user_id": scoped_user_id,
                    "legacy_user_id": legacy_user_id,
                },
            )
        return legacy_graph, legacy_config, legacy_snapshot, True
    return graph, config, snapshot, False


async def _build_state_config_with_checkpointer(
    thread_id: str, user_id: str, username: str | None = None
):
    """Return a v2 config that carries the graph's checkpointer to skip subgraph routing."""
    graph = await get_sealai_graph_v2()
    config = build_v2_config(thread_id=thread_id, user_id=user_id)
    configurable = config.setdefault("configurable", {})
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    if username:
        metadata = config.setdefault("metadata", {})
        metadata["username"] = username
    return graph, config


@router.get("/state")
async def get_state(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Get current LangGraph state for a thread.

    Returns the complete state including working profile, messages, etc.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    try:
        # user_id must always come from the authenticated Keycloak JWT.
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )

        state_values = _state_to_dict(snapshot.values)
        working_profile = _serialize_working_profile(_state_field(state_values, "working_profile", "engineering_profile"))
        parameter_provenance = _state_field(state_values, "reasoning", "parameter_provenance") if isinstance(state_values, dict) else {}
        metadata = _collect_metadata(state_values)

        if PARAM_SYNC_DEBUG:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            param_keys = sorted(working_profile.keys()) if isinstance(working_profile, dict) else []
            logger.info(
                "langgraph_v2_state_debug",
                extra={
                    "request_id": request_id,
                    "thread_id": thread_id,
                    "user_id": user.user_id,
                    "parameter_count": len(param_keys),
                    "parameter_keys": param_keys,
                    "checkpoint_thread_id": configurable.get("thread_id"),
                    "checkpoint_ns": configurable.get("checkpoint_ns"),
                },
            )

        logger.info(
            "state_get_success",
            extra={
            "thread_id": thread_id,
            "user_id": user.user_id,
            "has_values": bool(snapshot.values),
        },
        )

        return {
            "state": state_values,
            "working_profile": working_profile,
            "parameter_provenance": parameter_provenance,
            "metadata": metadata,
            "next": snapshot.next,
            "config": _sanitize_config_for_client(snapshot.config),
        }
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "state_get_error",
            extra={
                "request_id": request_id,
                "thread_id": thread_id,
                "user_id": user.user_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc


@router.post("/state")
async def update_state(
    body: StateUpdate,
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Update working profile in LangGraph state.

    This allows the frontend to directly update parameters without
    sending a chat message. The state update will be reflected in
    the next graph run.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    sanitized_working_profile = body.working_profile.model_dump(exclude_none=True)
    if not sanitized_working_profile:
        raise HTTPException(
            status_code=400,
            detail=error_detail("missing_parameters", request_id=request_id),
        )

    try:
        # Reuse the authenticated user_id so the state update is scoped to the Keycloak user.
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        resolved = _resolve_update_as_node(state_values)
        as_node = pick_existing_node(graph, resolved, fallback=DEFAULT_STATE_UPDATE_NODE)
        if resolved and as_node != resolved:
            logger.warning(
                "state_update_invalid_as_node_fallback",
                extra={
                    "request_id": request_id,
                    "thread_id": thread_id,
                    "user_id": user.user_id,
                    "resolved_as_node": resolved,
                    "fallback_as_node": as_node,
                },
        )

        existing_profile = _state_field(state_values, "working_profile", "engineering_profile") if isinstance(state_values, dict) else {}
        existing_provenance = _state_field(state_values, "reasoning", "parameter_provenance") if isinstance(state_values, dict) else {}
        existing_extracted = _state_field(state_values, "working_profile", "extracted_params") if isinstance(state_values, dict) else {}
        existing_extracted_provenance = _state_field(state_values, "reasoning", "extracted_parameter_provenance") if isinstance(state_values, dict) else {}
        existing_versions = _state_field(state_values, "reasoning", "parameter_versions") if isinstance(state_values, dict) else {}
        existing_updated_at = _state_field(state_values, "reasoning", "parameter_updated_at") if isinstance(state_values, dict) else {}
        (
            merged_profile,
            merged_provenance,
            merged_versions,
            merged_updated_at,
            remaining_extracted,
            remaining_extracted_provenance,
            _applied_fields,
            _rejected_fields,
        ) = promote_parameter_patch_to_asserted(
            existing_profile,
            sanitized_working_profile,
            existing_provenance,
            source="user",
            existing_extracted=existing_extracted,
            extracted_provenance=existing_extracted_provenance,
            parameter_versions=existing_versions,
            parameter_updated_at=existing_updated_at,
        )
        cycle_update = build_assertion_cycle_update(state_values, applied_fields=_applied_fields)

        updates = {
            "working_profile": {
                "engineering_profile": merged_profile,
                "extracted_params": remaining_extracted,
            },
            "reasoning": {
                "parameter_provenance": merged_provenance,
                "extracted_parameter_provenance": remaining_extracted_provenance,
                "parameter_versions": merged_versions,
                "parameter_updated_at": merged_updated_at,
            },
        }
        if cycle_update:
            updates = _deep_merge_updates(updates, cycle_update)

        await graph.aupdate_state(
            config,
            updates,
            as_node=as_node,
        )

        logger.info(
            "state_update_success",
            extra={
            "thread_id": thread_id,
            "user_id": user.user_id,
            "working_profile": merged_profile,
            "as_node": as_node,
            "source": body.source,
                "timestamp": body.timestamp,
            },
        )

        return {"ok": True, "working_profile": merged_profile}
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "state_update_error",
            extra={
                "request_id": request_id,
                "thread_id": thread_id,
                "user_id": user.user_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc
