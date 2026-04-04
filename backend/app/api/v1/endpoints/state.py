# backend/app/api/v1/endpoints/state.py
"""State management endpoints for LangGraph."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.v1.projections.case_workspace import (
    project_case_workspace,
    project_case_workspace_from_ssot,
    synthesize_workspace_state_from_ssot,
)
from app.api.v1.schemas.case_workspace import CaseWorkspaceProjection
from app.api.v1.renderers.rfq_html import render_rfq_html
from app.common.errors import error_detail
from app.services.auth.dependencies import RequestUser, get_current_request_user
from app.services.rag.state import WorkingProfile

logger = logging.getLogger(__name__)

router = APIRouter()


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




@router.get("/state")
async def get_state(
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Legacy LangGraph state endpoint — not available in SSoT architecture."""
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="Use /state/{chat_id} for SSoT state hydration.",
        ),
    )


@router.post("/state")
async def update_state(
    body: StateUpdate,
    raw_request: Request,
    thread_id: str = Query(..., description="Thread ID"),
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="State mutation is only supported on the canonical /api/agent runtime path.",
        ),
    )


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

    from app.agent.api.router import load_canonical_state

    ssot_state = await load_canonical_state(current_user=user, session_id=thread_id)
    if ssot_state is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("session_not_found", request_id=request_id),
        )
    projection = project_case_workspace_from_ssot(ssot_state, chat_id=thread_id)
    logger.info(
        "state_workspace_get_success_ssot",
        extra={
            "thread_id": thread_id,
            "user_id": user.user_id,
            "release_status": projection.governance_status.release_status,
        },
    )
    return projection



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

    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="RFQ confirmation is not available on the compatibility v1 state facade.",
        ),
    )


# ---------------------------------------------------------------------------
# POST /state/workspace/partner-select — select a partner/material
# ---------------------------------------------------------------------------


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
    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="Partner selection is not available in SSoT architecture.",
        ),
    )


# ---------------------------------------------------------------------------
# POST /state/workspace/rfq-handover — initiate RFQ handover
# ---------------------------------------------------------------------------


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

    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="RFQ handover is not available on the compatibility v1 state facade.",
        ),
    )


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

    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="RFQ document generation is not available on the compatibility v1 state facade.",
        ),
    )


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

    from app.agent.api.router import load_canonical_state

    ssot_state = await load_canonical_state(current_user=user, session_id=thread_id)
    if ssot_state is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("session_not_found", request_id=request_id),
        )
    sealing = dict(ssot_state.get("sealing_state") or {})
    handover = dict(sealing.get("handover") or {})
    html_report = handover.get("rfq_html_report")
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


# ---------------------------------------------------------------------------
# GET /state/{chat_id} — UI hydration after F5 page reload (Blueprint §12)
# ---------------------------------------------------------------------------

def _synthesize_state_response_from_ssot(state: Any, *, chat_id: str) -> Dict[str, Any]:
    """Build a legacy-format state response dict from an SSoT AgentState."""
    working_profile: Dict[str, Any] = dict(state.get("working_profile") or {})
    sealing_state: Dict[str, Any] = dict(state.get("sealing_state") or {})
    case_state: Dict[str, Any] = dict(state.get("case_state") or {})
    governance: Dict[str, Any] = dict(sealing_state.get("governance") or {})
    cycle: Dict[str, Any] = dict(sealing_state.get("cycle") or {})
    handover: Dict[str, Any] = dict(sealing_state.get("handover") or {})
    review: Dict[str, Any] = dict(sealing_state.get("review") or {})
    selection: Dict[str, Any] = dict(sealing_state.get("selection") or {})
    parameter_meta: Dict[str, Any] = dict(case_state.get("parameter_meta") or {})
    governance_state: Dict[str, Any] = dict(case_state.get("governance_state") or {})
    matching_state: Dict[str, Any] = dict(case_state.get("matching_state") or {})
    rfq_state: Dict[str, Any] = dict(case_state.get("rfq_state") or {})
    manufacturer_state: Dict[str, Any] = dict(case_state.get("manufacturer_state") or {})
    result_contract: Dict[str, Any] = dict(case_state.get("result_contract") or {})
    sealing_requirement_spec: Dict[str, Any] = dict(case_state.get("sealing_requirement_spec") or {})
    requirement_class: Dict[str, Any] = dict(
        case_state.get("requirement_class")
        or result_contract.get("requirement_class")
        or {}
    )
    recipient_selection: Dict[str, Any] = dict(
        case_state.get("recipient_selection")
        or rfq_state.get("recipient_selection")
        or {}
    )
    case_meta: Dict[str, Any] = dict(case_state.get("case_meta") or {})

    release_status = governance.get("release_status")
    rfq_admissibility = governance.get("rfq_admissibility")
    phase = case_meta.get("phase") or cycle.get("phase")
    is_handover_ready = bool(rfq_state.get("handover_ready", handover.get("is_handover_ready", False)))
    governed_output_text = governance.get("governed_output_text") or ""
    required_disclaimers = list(
        governance_state.get("required_disclaimers")
        or governance.get("scope_of_validity")
        or []
    )

    governance_metadata: Dict[str, Any] = {
        "conflicts": governance.get("conflicts") or [],
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "state_revision": cycle.get("state_revision"),
        "specificity_level": governance.get("specificity_level"),
        "unknowns_release_blocking": governance.get("unknowns_release_blocking") or [],
        "unknowns_manufacturer_validation": governance.get("unknowns_manufacturer_validation") or [],
        "scope_of_validity": governance_state.get("scope_of_validity") or governance.get("scope_of_validity") or [],
        "required_disclaimers": required_disclaimers,
        "review_required": bool(governance_state.get("review_required", review.get("review_required", False))),
        "review_state": governance_state.get("review_state") or review.get("review_state"),
        "review_reason": review.get("review_reason"),
        "contract_obsolete": bool(result_contract.get("contract_obsolete", cycle.get("contract_obsolete", False))),
        "contract_obsolete_reason": (
            result_contract.get("invalidation_reasons")
            or ([cycle.get("contract_obsolete_reason")] if cycle.get("contract_obsolete_reason") else [])
        ),
    }

    # Synthesize nested state in the legacy pillar format so existing
    # frontend selectors can read it without modification.
    synthesized_state = synthesize_workspace_state_from_ssot(state, chat_id=chat_id)

    return {
        "state": synthesized_state,
        "working_profile": working_profile,
        "parameter_provenance": parameter_meta,
        "recommendation_contract": result_contract,
        "requirement_class": requirement_class or None,
        "recipient_selection": recipient_selection or None,
        "requirement_class_hint": result_contract.get("requirement_class_hint"),
        "matching_state": matching_state,
        "matching_outcome": matching_state.get("matching_outcome"),
        "rfq_state": rfq_state,
        "manufacturer_state": manufacturer_state,
        "sealing_requirement_spec": sealing_requirement_spec,
        "metadata": {
            "thread_id": chat_id,
            "phase": phase,
            "last_node": "facade_hydration",
            "recommendation_ready": release_status in ("approved", "rfq_ready"),
        },
        "governance_metadata": governance_metadata,
        "rfq_admissibility": rfq_admissibility,
        "is_handover_ready": is_handover_ready,
        "next": [],
        "config": {},
    }


@router.get("/state/{chat_id}")
async def get_graph_state_endpoint(
    chat_id: str,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    """Return graph state for a chat ID — supports F5 page-reload hydration.

    Response is synthesised from canonical persisted SSoT state.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")

    from app.agent.api.router import load_canonical_state

    ssot_state = await load_canonical_state(current_user=user, session_id=chat_id)
    if ssot_state is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail("session_not_found", request_id=request_id),
        )
    logger.info(
        "state_facade_hydration",
        extra={"chat_id": chat_id, "request_id": request_id},
    )
    return _synthesize_state_response_from_ssot(ssot_state, chat_id=chat_id)
