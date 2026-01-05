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
from app.langgraph_v2.state import SealAIState, SealParameterUpdate, TechnicalParameters
from app.langgraph_v2.contracts import error_detail, is_dependency_unavailable_error, pick_existing_node
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user

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

    parameters: SealParameterUpdate
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


def _serialize_parameters(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, TechnicalParameters):
        return raw.model_dump(exclude_none=True)
    if isinstance(raw, dict):
        return {key: value for key, value in raw.items() if value is not None}
    try:
        return {key: value for key, value in dict(raw).items() if value is not None}
    except Exception:
        return {}


def _collect_metadata(state_values: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    raw_metadata = state_values.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)
    for key in METADATA_FIELDS:
        value = state_values.get(key)
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
    candidate = state_values.get("last_node")
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
    graph, config = await _build_state_config_with_checkpointer(
        thread_id=thread_id, user_id=scoped_user_id, username=user.username
    )
    snapshot = await graph.aget_state(config)
    if not legacy_user_id or _has_state_values(snapshot):
        return graph, config, snapshot, False

    legacy_graph, legacy_config = await _build_state_config_with_checkpointer(
        thread_id=thread_id, user_id=legacy_user_id, username=user.username
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

    Returns the complete state including parameters, messages, etc.
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
        parameters = _serialize_parameters(state_values.get("parameters"))
        parameter_provenance = state_values.get("parameter_provenance") if isinstance(state_values, dict) else {}
        metadata = _collect_metadata(state_values)

        if PARAM_SYNC_DEBUG:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            param_keys = sorted(parameters.keys()) if isinstance(parameters, dict) else []
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
            "parameters": parameters,
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
    """Update parameters in LangGraph state.

    This allows the frontend to directly update parameters without
    sending a chat message. The state update will be reflected in
    the next graph run.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    sanitized_parameters = body.parameters.model_dump(exclude_none=True)
    if not sanitized_parameters:
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

        await graph.aupdate_state(
            config,
            {"parameters": sanitized_parameters},
            as_node=as_node,
        )

        logger.info(
            "state_update_success",
            extra={
            "thread_id": thread_id,
            "user_id": user.user_id,
            "parameters": sanitized_parameters,
            "as_node": as_node,
            "source": body.source,
                "timestamp": body.timestamp,
            },
        )

        return {"ok": True, "parameters": sanitized_parameters}
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
