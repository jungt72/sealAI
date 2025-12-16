# backend/app/api/v1/endpoints/state.py
"""State management endpoints for LangGraph."""

from __future__ import annotations

import traceback
from datetime import datetime
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState, SealParameterUpdate, TechnicalParameters
from app.services.auth.dependencies import get_current_request_user

logger = logging.getLogger(__name__)

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

DEFAULT_STATE_UPDATE_NODE = "supervisor_logic_node"


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


async def _build_state_config_with_checkpointer(thread_id: str, user_id: str):
    """Return a v2 config that carries the graph's checkpointer to skip subgraph routing."""
    graph = await get_sealai_graph_v2()
    config = build_v2_config(thread_id=thread_id, user_id=user_id)
    configurable = config.setdefault("configurable", {})
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    return graph, config


@router.get("/state")
async def get_state(
    thread_id: str = Query(..., description="Thread ID"),
    username: str = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Get current LangGraph state for a thread.

    Returns the complete state including parameters, messages, etc.
    """
    try:
        # user_id must always come from the authenticated Keycloak JWT (`current_user.sub`).
        graph, config = await _build_state_config_with_checkpointer(
            thread_id=thread_id, user_id=username
        )
        snapshot = await graph.aget_state(config)

        state_values = _state_to_dict(snapshot.values)
        parameters = _serialize_parameters(state_values.get("parameters"))
        metadata = _collect_metadata(state_values)

        logger.info(
            "state_get_success",
            extra={
            "thread_id": thread_id,
            "user_id": username,
            "has_values": bool(snapshot.values),
        },
        )

        return {
            "state": state_values,
            "parameters": parameters,
            "metadata": metadata,
            "next": snapshot.next,
            "config": _sanitize_config_for_client(snapshot.config),
        }
    except Exception as e:
        logger.error(
            "state_get_error",
            extra={
                "thread_id": thread_id,
                "user_id": username,
                "error": str(e),
            },
        )
        logger.error("Traceback: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get state: {str(e)}")


@router.post("/state")
async def update_state(
    body: StateUpdate,
    thread_id: str = Query(..., description="Thread ID"),
    username: str = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Update parameters in LangGraph state.

    This allows the frontend to directly update parameters without
    sending a chat message. The state update will be reflected in
    the next graph run.
    """
    sanitized_parameters = body.parameters.model_dump(exclude_none=True)
    if not sanitized_parameters:
        raise HTTPException(status_code=400, detail="No parameters provided")

    try:
        # Reuse the authenticated `sub` so the state update is scoped to the Keycloak user.
        graph, config = await _build_state_config_with_checkpointer(
            thread_id=thread_id, user_id=username
        )
        snapshot = await graph.aget_state(config)
        state_values = _state_to_dict(snapshot.values)
        as_node = _resolve_update_as_node(state_values) or DEFAULT_STATE_UPDATE_NODE

        await graph.aupdate_state(
            config,
            {"parameters": sanitized_parameters},
            as_node=as_node,
        )

        logger.info(
            "state_update_success",
            extra={
            "thread_id": thread_id,
            "user_id": username,
                "parameters": sanitized_parameters,
                "as_node": as_node,
                "source": body.source,
                "timestamp": body.timestamp,
            },
        )

        return {"ok": True, "parameters": sanitized_parameters}
    except Exception as e:
        logger.error(
            "state_update_error",
            extra={
                "thread_id": thread_id,
                "user_id": username,
                "error": str(e),
            },
        )
        logger.error("Traceback: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to update state: {str(e)}")
