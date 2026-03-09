# backend/app/api/v1/endpoints/state.py
"""State management endpoints for LangGraph."""

from __future__ import annotations

from datetime import datetime
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.contracts import error_detail, is_dependency_unavailable_error, pick_existing_node
from app.langgraph_v2.utils.assertion_cycle import build_assertion_cycle_update
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_to_state_layers
from app.langgraph_v2.projections.case_workspace import project_case_workspace
from app.api.v1.schemas.case_workspace import CaseWorkspaceProjection
from app.api.v1.renderers.rfq_html import render_rfq_html
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


# Shared state-access helpers — definitions live in app.api.v1.utils.state_access
# to avoid duplication with langgraph_v2.py.
from app.api.v1.utils.state_access import _pillar_dict, _state_to_dict  # noqa: E402


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
        existing_normalized = (
            _state_field(state_values, "working_profile", "normalized_profile")
            or _state_field(state_values, "working_profile", "extracted_params")
            if isinstance(state_values, dict)
            else {}
        )
        existing_normalized_provenance = _state_field(state_values, "reasoning", "extracted_parameter_provenance") if isinstance(state_values, dict) else {}
        existing_identity = _state_field(state_values, "reasoning", "extracted_parameter_identity") if isinstance(state_values, dict) else {}
        existing_observed_inputs = _state_field(state_values, "reasoning", "observed_inputs") if isinstance(state_values, dict) else {}
        existing_versions = _state_field(state_values, "reasoning", "parameter_versions") if isinstance(state_values, dict) else {}
        existing_updated_at = _state_field(state_values, "reasoning", "parameter_updated_at") if isinstance(state_values, dict) else {}
        (
            merged_profile,
            merged_provenance,
            merged_versions,
            merged_updated_at,
            merged_normalized,
            merged_normalized_provenance,
            merged_identity,
            merged_observed_inputs,
            _staged_fields,
            _asserted_fields,
            _rejected_fields,
        ) = apply_parameter_patch_to_state_layers(
            existing_profile,
            existing_normalized,
            sanitized_working_profile,
            existing_provenance,
            existing_normalized_provenance,
            existing_identity,
            existing_observed_inputs,
            source="user",
            parameter_versions=existing_versions,
            parameter_updated_at=existing_updated_at,
        )
        cycle_update = build_assertion_cycle_update(state_values, applied_fields=_asserted_fields)

        updates = {
            "working_profile": {
                "normalized_profile": merged_normalized,
                "engineering_profile": merged_profile,
                "extracted_params": merged_normalized,
            },
            "reasoning": {
                "parameter_provenance": merged_provenance,
                "extracted_parameter_provenance": merged_normalized_provenance,
                "extracted_parameter_identity": merged_identity,
                "observed_inputs": merged_observed_inputs,
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


@router.get("/state/workspace", response_model=CaseWorkspaceProjection)
async def get_case_workspace(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> CaseWorkspaceProjection:
    """UI-facing read model projection of the current case state.

    Returns a structured, stable workspace view without exposing internal
    orchestration details, prompt traces, or raw LLM artifacts.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    try:
        _graph, _config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        projection = project_case_workspace(state_values)

        logger.info(
            "state_workspace_get_success",
            extra={
                "thread_id": thread_id,
                "user_id": user.user_id,
                "release_status": projection.governance_status.release_status,
            },
        )
        return projection
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "state_workspace_get_error",
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


RFQ_CONFIRM_AS_NODE = "supervisor_policy_node"


@router.post("/state/workspace/rfq-confirm", response_model=CaseWorkspaceProjection)
async def confirm_rfq_package(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> CaseWorkspaceProjection:
    """Confirm the RFQ package for the current case.

    Sets ``system.rfq_confirmed = True`` in graph state when the case
    has a valid RFQ draft and is not in an inadmissible or stale state.
    Returns the updated workspace projection.
    """
    request_id = (
        raw_request.headers.get("X-Request-Id")
        or raw_request.headers.get("X-Request-ID")
    )
    try:
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        projection = project_case_workspace(state_values)

        # Gate 1: RFQ draft must exist
        if not projection.rfq_package.has_draft:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_no_draft",
                    request_id=request_id,
                    message="No RFQ draft available for confirmation.",
                ),
            )

        # Gate 2: Must not be inadmissible
        effective_status = (
            projection.rfq_status.release_status
            or projection.governance_status.release_status
        )
        if effective_status == "inadmissible":
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_inadmissible",
                    request_id=request_id,
                    message="Case is inadmissible — cannot confirm RFQ package.",
                ),
            )

        # Gate 3: Must not be stale
        if projection.cycle_info.derived_artifacts_stale:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_stale",
                    request_id=request_id,
                    message="Artifacts are stale — recalculation required before confirmation.",
                ),
            )

        # Gate 4: Must not already be confirmed
        if projection.rfq_status.rfq_confirmed:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_already_confirmed",
                    request_id=request_id,
                    message="RFQ package is already confirmed.",
                ),
            )

        # Resolve as_node for state update
        resolved = _resolve_update_as_node(state_values)
        as_node = pick_existing_node(graph, resolved, fallback=RFQ_CONFIRM_AS_NODE)

        await graph.aupdate_state(
            config,
            {"system": {"rfq_confirmed": True}},
            as_node=as_node,
        )

        # Re-read and project to return fresh state
        updated_snapshot = await graph.aget_state(config)
        updated_values = _state_to_dict(updated_snapshot.values)
        updated_projection = project_case_workspace(updated_values)

        logger.info(
            "rfq_confirm_success",
            extra={
                "thread_id": thread_id,
                "user_id": user.user_id,
                "release_status": updated_projection.governance_status.release_status,
            },
        )
        return updated_projection
    except HTTPException:
        raise
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "rfq_confirm_error",
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


# ---------------------------------------------------------------------------
# POST /state/workspace/partner-select — select a partner/material
# ---------------------------------------------------------------------------

PARTNER_SELECT_AS_NODE = "supervisor_policy_node"


@router.post("/state/workspace/partner-select", response_model=CaseWorkspaceProjection)
async def select_partner(
    raw_request: Request,
    partner_id: str = Query(..., description="ID/Name of the selected partner/material"),
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> CaseWorkspaceProjection:
    """Select a partner/material for the current case.

    Sets ``reasoning.selected_partner_id = partner_id`` in graph state.
    Returns the updated workspace projection.

    Gates (all must pass):
    1. RFQ must be confirmed
    2. Matching must be ready (not stale, etc.)
    3. Selected partner must exist in material_fit_items
    """
    request_id = (
        raw_request.headers.get("X-Request-Id")
        or raw_request.headers.get("X-Request-ID")
    )
    try:
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        projection = project_case_workspace(state_values)

        # Gate 1: Matching must be ready (this includes rfq_confirmed, not stale etc)
        if not projection.partner_matching.matching_ready:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "matching_not_ready",
                    request_id=request_id,
                    message=f"Partner matching is not ready: {', '.join(projection.partner_matching.not_ready_reasons)}",
                ),
            )

        # Gate 2: Selected partner must exist in material_fit_items
        valid_partners = [item.material for item in projection.partner_matching.material_fit_items]
        if partner_id not in valid_partners:
            raise HTTPException(
                status_code=400,
                detail=error_detail(
                    "invalid_partner",
                    request_id=request_id,
                    message=f"Selected partner '{partner_id}' is not in the list of valid matches.",
                ),
            )

        # Update state
        resolved = _resolve_update_as_node(state_values)
        as_node = pick_existing_node(graph, resolved, fallback=PARTNER_SELECT_AS_NODE)

        await graph.aupdate_state(
            config,
            {"reasoning": {"selected_partner_id": partner_id}},
            as_node=as_node,
        )

        # Re-read and project
        updated_snapshot = await graph.aget_state(config)
        updated_values = _state_to_dict(updated_snapshot.values)
        updated_projection = project_case_workspace(updated_values)

        logger.info(
            "partner_select_success",
            extra={
                "thread_id": thread_id,
                "user_id": user.user_id,
                "partner_id": partner_id,
            },
        )
        return updated_projection
    except HTTPException:
        raise
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "partner_select_error",
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


# ---------------------------------------------------------------------------
# POST /state/workspace/rfq-handover — initiate RFQ handover
# ---------------------------------------------------------------------------

RFQ_HANDOVER_AS_NODE = "supervisor_policy_node"


@router.post("/state/workspace/rfq-handover", response_model=CaseWorkspaceProjection)
async def initiate_rfq_handover(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> CaseWorkspaceProjection:
    """Initiate the RFQ handover for the current case.

    Sets ``system.rfq_handover_initiated = True`` in graph state.
    Returns the updated workspace projection.

    Gates (all must pass):
    1. RFQ confirmed
    2. RFQ document generated
    3. Partner selected
    4. Not stale
    5. Not inadmissible
    6. Not already initiated
    """
    request_id = (
        raw_request.headers.get("X-Request-Id")
        or raw_request.headers.get("X-Request-ID")
    )
    try:
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        projection = project_case_workspace(state_values)

        # Gate 1: Check readiness via projection
        if not projection.rfq_status.handover_ready:
            reasons = []
            if not projection.rfq_status.rfq_confirmed:
                reasons.append("RFQ not confirmed")
            if not projection.rfq_status.has_html_report:
                reasons.append("RFQ document not generated")
            if not projection.partner_matching.selected_partner_id:
                reasons.append("No partner selected")
            if projection.cycle_info.derived_artifacts_stale:
                reasons.append("Artifacts are stale")
            
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "handover_not_ready",
                    request_id=request_id,
                    message=f"RFQ handover is not ready: {', '.join(reasons)}",
                ),
            )

        # Gate 2: Already initiated?
        if projection.rfq_status.handover_initiated:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "handover_already_initiated",
                    request_id=request_id,
                    message="RFQ handover has already been initiated.",
                ),
            )

        # Update state
        resolved = _resolve_update_as_node(state_values)
        as_node = pick_existing_node(graph, resolved, fallback=RFQ_HANDOVER_AS_NODE)

        await graph.aupdate_state(
            config,
            {"system": {"rfq_handover_initiated": True}},
            as_node=as_node,
        )

        # Re-read and project
        updated_snapshot = await graph.aget_state(config)
        updated_values = _state_to_dict(updated_snapshot.values)
        updated_projection = project_case_workspace(updated_values)

        logger.info(
            "rfq_handover_success",
            extra={
                "thread_id": thread_id,
                "user_id": user.user_id,
            },
        )
        return updated_projection
    except HTTPException:
        raise
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "rfq_handover_error",
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


# ---------------------------------------------------------------------------
# POST /state/workspace/rfq-generate-pdf — generate RFQ HTML document
# ---------------------------------------------------------------------------

@router.post("/state/workspace/rfq-generate-pdf", response_model=CaseWorkspaceProjection)
async def generate_rfq_pdf(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> CaseWorkspaceProjection:
    """Generate an RFQ HTML document from the confirmed workspace state.

    Stores the generated HTML in ``system.rfq_html_report``.
    Returns the updated workspace projection (``has_html_report`` becomes true).

    Gates (all must pass):
    1. RFQ draft must exist
    2. Must not be inadmissible
    3. Must not be stale
    4. RFQ must be confirmed
    """
    request_id = (
        raw_request.headers.get("X-Request-Id")
        or raw_request.headers.get("X-Request-ID")
    )
    try:
        graph, config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        projection = project_case_workspace(state_values)

        # Gate 1: RFQ draft must exist
        if not projection.rfq_package.has_draft:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_no_draft",
                    request_id=request_id,
                    message="No RFQ draft available for document generation.",
                ),
            )

        # Gate 2: Must not be inadmissible
        effective_status = (
            projection.rfq_status.release_status
            or projection.governance_status.release_status
        )
        if effective_status == "inadmissible":
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_inadmissible",
                    request_id=request_id,
                    message="Case is inadmissible — cannot generate RFQ document.",
                ),
            )

        # Gate 3: Must not be stale
        if projection.cycle_info.derived_artifacts_stale:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_stale",
                    request_id=request_id,
                    message="Artifacts are stale — recalculation required before document generation.",
                ),
            )

        # Gate 4: RFQ must be confirmed
        if not projection.rfq_status.rfq_confirmed:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "rfq_not_confirmed",
                    request_id=request_id,
                    message="RFQ package must be confirmed before generating document.",
                ),
            )

        # Render HTML document from projection
        html_report = render_rfq_html(projection)

        # Store in graph state
        resolved = _resolve_update_as_node(state_values)
        as_node = pick_existing_node(graph, resolved, fallback=RFQ_CONFIRM_AS_NODE)

        await graph.aupdate_state(
            config,
            {"system": {"rfq_html_report": html_report}},
            as_node=as_node,
        )

        # Re-read and project to return fresh state
        updated_snapshot = await graph.aget_state(config)
        updated_values = _state_to_dict(updated_snapshot.values)
        updated_projection = project_case_workspace(updated_values)

        logger.info(
            "rfq_generate_pdf_success",
            extra={
                "thread_id": thread_id,
                "user_id": user.user_id,
                "html_length": len(html_report),
            },
        )
        return updated_projection
    except HTTPException:
        raise
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "rfq_generate_pdf_error",
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


# ---------------------------------------------------------------------------
# GET /state/workspace/rfq-document — download generated RFQ HTML
# ---------------------------------------------------------------------------

@router.get("/state/workspace/rfq-document")
async def get_rfq_document(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> HTMLResponse:
    """Return the stored RFQ HTML document for download/display.

    Returns 404 if no document has been generated yet.
    """
    request_id = (
        raw_request.headers.get("X-Request-Id")
        or raw_request.headers.get("X-Request-ID")
    )
    try:
        _graph, _config, snapshot, _used_legacy = await _resolve_state_snapshot(
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
        state_values = _state_to_dict(snapshot.values)
        system = _pillar_dict(state_values, "system")
        html_report = system.get("rfq_html_report")

        if not html_report:
            raise HTTPException(
                status_code=404,
                detail=error_detail(
                    "rfq_no_document",
                    request_id=request_id,
                    message="No RFQ document has been generated yet.",
                ),
            )

        return HTMLResponse(
            content=html_report,
            headers={
                "Content-Disposition": "inline; filename=\"sealai-rfq-document.html\"",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "rfq_document_get_error",
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
