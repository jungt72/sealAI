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
from app.langgraph_v2.utils.threading import reset_current_tenant_id, set_current_tenant_id, resolve_checkpoint_thread_id
from app.services.auth.dependencies import (
    RequestUser,
    canonical_user_id,
    get_current_request_user_strict_tenant,
)

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


def _config_with_checkpoint_ns(config: Dict[str, Any], checkpoint_ns: str) -> Dict[str, Any]:
    copied = dict(config or {})
    configurable = dict(copied.get("configurable") or {})
    configurable["checkpoint_ns"] = checkpoint_ns
    copied["configurable"] = configurable
    return copied


async def _aget_state_with_checkpoint_ns_fallback(
    graph: Any,
    config: Dict[str, Any],
    *,
    request_id: str | None = None,
    thread_id: str | None = None,
    user_id: str | None = None,
) -> tuple[Any, Dict[str, Any]]:
    snapshot = await graph.aget_state(config)
    if _has_state_values(snapshot):
        return snapshot, config
    configurable = config.get("configurable") if isinstance(config, dict) else {}
    checkpoint_ns = configurable.get("checkpoint_ns") if isinstance(configurable, dict) else None
    if not checkpoint_ns:
        return snapshot, config
    fallback_config = _config_with_checkpoint_ns(config, "")
    fallback_snapshot = await graph.aget_state(fallback_config)
    if _has_state_values(fallback_snapshot):
        logger.warning(
            "state_get_checkpoint_ns_fallback",
            extra={
                "request_id": request_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "configured_ns": checkpoint_ns,
                "fallback_ns": "",
            },
        )
        return fallback_snapshot, fallback_config
    return snapshot, config



def _resolve_owner_ids(user: RequestUser) -> tuple[str, str | None]:
    """
    Resolve the owner_id (Keycloak sub) and legacy_owner_id (custom user_id claim).
    """
    owner_id = user.sub
    legacy_owner_id = user.user_id if user.user_id != user.sub else None
    return owner_id, legacy_owner_id


def _resolve_owner_ids(user: RequestUser) -> tuple[str, str | None]:
    """
    Resolve the owner_id (Keycloak sub) and legacy_owner_id (custom user_id claim).
    """
    owner_id = user.sub
    legacy_owner_id = user.user_id if user.user_id != user.sub else None
    return owner_id, legacy_owner_id

async def _resolve_state_snapshot(
    *,
    thread_id: str,
    user: RequestUser,
    request_id: str | None = None,
    checkpoint_thread_id: str | None = None,
) -> tuple[Any, Dict[str, Any], Any, bool]:
    scoped_user_id = canonical_user_id(user)
    tenant_id = user.tenant_id
    graph, config = await _build_state_config_with_checkpointer(
        thread_id=thread_id,
        user_id=scoped_user_id,
        tenant_id=tenant_id,
        username=user.username,
        checkpoint_thread_id=checkpoint_thread_id,
    )
    snapshot, effective_config = await _aget_state_with_checkpoint_ns_fallback(
        graph,
        config,
        request_id=request_id,
        thread_id=thread_id,
        user_id=scoped_user_id,
    )
    return graph, effective_config, snapshot, False


async def _build_state_config_with_checkpointer(
    thread_id: str,
    user_id: str,
    tenant_id: str,
    username: str | None = None,
    checkpoint_thread_id: str | None = None,
):
    """Return a v2 config that carries the graph's checkpointer to skip subgraph routing."""
    graph = await get_sealai_graph_v2()
    effective_thread_id = checkpoint_thread_id or thread_id
    tenant_token = set_current_tenant_id(tenant_id)
    try:
        config = build_v2_config(thread_id=effective_thread_id, user_id=user_id, tenant_id=tenant_id)
    finally:
        reset_current_tenant_id(tenant_token)
    configurable = config.setdefault("configurable", {})
    if checkpoint_thread_id:
        configurable["thread_id"] = checkpoint_thread_id
        # Keep external chat_id visible for clients while querying by scoped checkpoint key.
        metadata = config.setdefault("metadata", {})
        metadata["thread_id"] = thread_id
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    if username:
        metadata = config.setdefault("metadata", {})
        metadata["username"] = username
    return graph, config


@router.get("/state")
async def get_state(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user_strict_tenant),
) -> Dict[str, Any]:
    """Get current LangGraph state for a thread.

    Returns the complete state including parameters, messages, etc.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    try:
        scoped_user_id = canonical_user_id(user)

        try:
            resolved_key = resolve_checkpoint_thread_id(
                tenant_id=user.tenant_id,
                user_id=scoped_user_id,
                chat_id=thread_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
            checkpoint_thread_id=resolved_key,
        )
        if not _has_state_values(snapshot):
            raise HTTPException(
                status_code=404,
                detail=error_detail("state_not_found", request_id=request_id),
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
    except HTTPException:
        raise
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
    user: RequestUser = Depends(get_current_request_user_strict_tenant),
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
        scoped_user_id = canonical_user_id(user)
        try:
            resolved_key = resolve_checkpoint_thread_id(
                tenant_id=user.tenant_id,
                user_id=scoped_user_id,
                chat_id=thread_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
            checkpoint_thread_id=resolved_key,
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
    except HTTPException:
        raise
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
