import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from langchain_core.messages import AIMessage

from app.agent.api.models import (
    ReviewRequest,
    ReviewResponse,
    ReviewSeedResponse,
    OverrideRequest,
    OverrideResponse,
    OverrideGovernanceResult,
    build_public_response_core,
)
from app.agent.state.agent_state import AgentState
from app.agent.state.models import UserOverride
from app.agent.state.reducers import (
    reduce_observed_to_normalized,
    reduce_normalized_to_asserted,
    reduce_asserted_to_governance,
)
from app.agent.api.deps import (
    _canonical_scope,
    _canonical_state_revision,
    SESSION_STORE,
    RequestUser,
    get_current_request_user,
)
from app.agent.api.loaders import (
    require_structured_review_state,
    persist_structured_review_commit,
    _persist_review_outcome_to_live_governed_state,
)
from app.agent.api.utils import (
    _governed_release_status_snapshot,
    _overlay_live_governed_snapshot,
)
from app.agent.domain.critical_review import (
    CriticalReviewRecommendationPackage,
    CriticalReviewMatchingPackage,
    CriticalReviewSpecialistInput,
    run_critical_review_specialist,
    critical_review_result_to_dict,
)
from app.agent.state.case_state import build_visible_case_narrative, PROJECTION_VERSION
from app.agent.state.projections import project_for_ui

_log = logging.getLogger(__name__)

router = APIRouter()

def _find_session(session_id: str) -> AgentState | None:
    return SESSION_STORE.get(session_id)

def _save_session(session_id: str, state: AgentState) -> None:
    SESSION_STORE[session_id] = state

def _build_review_handover_response(
    state: AgentState,
    *,
    session_id: str,
    outcome: Optional[CriticalReviewRecommendationPackage | CriticalReviewMatchingPackage] = None,
) -> ReviewResponse:
    reply = "Die technische Überprüfung wurde abgeschlossen."
    if isinstance(outcome, CriticalReviewRecommendationPackage):
        reply = outcome.recommendation_text
    elif isinstance(outcome, CriticalReviewMatchingPackage):
        reply = f"Passender Hersteller identifiziert: {outcome.manufacturer_id}"

    case_state = state.get("case_state") or {}
    return ReviewResponse(
        session_id=session_id,
        **build_public_response_core(
            reply=reply,
            structured_state={
                "view": project_for_ui(state.get("working_profile") or {}),
                "narrative": build_visible_case_narrative(
                    state=state,
                    case_state=case_state,
                    binding_level="CERTIFIED",
                    policy_context={"policy_path": "review", "phase": "review_complete"},
                ),
            },
            policy_path="review",
            run_meta={
                "review_outcome": critical_review_result_to_dict(outcome) if outcome else None,
                "projection_version": PROJECTION_VERSION,
            },
        ),
    )

def _is_review_handover_releasable(
    outcome: Optional[CriticalReviewRecommendationPackage | CriticalReviewMatchingPackage],
) -> bool:
    if isinstance(outcome, CriticalReviewRecommendationPackage):
        return outcome.is_releasable
    return False

def _apply_review_decision(state: AgentState, request: ReviewRequest) -> AgentState:
    from copy import deepcopy # noqa: PLC0415
    new_state = deepcopy(state)
    case_state = new_state.get("case_state") or {}
    case_meta = case_state.get("case_meta") or {}
    case_meta["lifecycle_status"] = "review_completed"
    case_state["case_meta"] = case_meta
    new_state["case_state"] = case_state
    return new_state

def _governed_native_review_commit(state: AgentState) -> tuple[AgentState, str]:
    from copy import deepcopy # noqa: PLC0415
    new_state = deepcopy(state)
    case_state = new_state.get("case_state") or {}
    case_meta = case_state.get("case_meta") or {}
    case_meta["runtime_path"] = "governed_graph"
    case_state["case_meta"] = case_meta
    new_state["case_state"] = case_state
    return new_state, "governed_graph"

@router.post("/review", response_model=ReviewResponse)
async def review_endpoint(
    request: ReviewRequest,
    current_user: RequestUser = Depends(get_current_request_user),
):
    state = await require_structured_review_state(current_user=current_user, session_id=request.session_id)

    outcome = None
    if request.decision == "approve":
        specialist_input = CriticalReviewSpecialistInput(
            comment=request.comment or "Approved by engineering review",
            reviewer_id=current_user.user_id or "human_reviewer",
        )
        outcome = await run_critical_review_specialist(state, specialist_input)

        if outcome:
            await _persist_review_outcome_to_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                case_state=state.get("case_state"),
                sealing_state=state,
                assistant_reply=outcome.recommendation_text if isinstance(outcome, CriticalReviewRecommendationPackage) else None,
            )
            # Re-load or overlay if needed, but the contract just needs to persist it

    updated_state = _apply_review_decision(state, request)
    await persist_structured_review_commit(
        current_user=current_user,
        session_id=request.session_id,
        state=updated_state,
    )

    return _build_review_handover_response(
        updated_state,
        session_id=request.session_id,
        outcome=outcome,
    )

@router.post("/review/seed", response_model=ReviewSeedResponse)
async def review_seed_endpoint() -> ReviewSeedResponse:
    return ReviewSeedResponse(status="ok")

@router.patch("/session/{session_id}/override", response_model=OverrideResponse)
async def session_override_endpoint(
    request: OverrideRequest,
    session_id: str = Path(...),
    current_user: RequestUser = Depends(get_current_request_user),
):
    from app.agent.api.loaders import _load_live_governed_state # noqa: PLC0415
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=True,
    )
    if not governed:
        raise HTTPException(status_code=404, detail="Session not found")

    rev_before = governed.case_meta.state_revision

    if request.target == "parameters":
        # 1. Update Observed extractions (the additive basis)
        new_extractions = list(governed.observed.extractions)
        for field_name, val in request.payload.items():
            # Remove existing for this field if present
            new_extractions = [e for e in new_extractions if e.field_name != field_name]
            if val is not None:
                new_extractions.append(UserOverride(field_name=field_name, value=val))

        governed.observed.extractions = new_extractions

        # 2. Re-run deterministic reducer chain
        governed.normalized = reduce_observed_to_normalized(governed.observed)
        governed.asserted = reduce_normalized_to_asserted(governed.normalized)
        governed.governance = reduce_asserted_to_governance(governed.asserted)

    # 3. Persist
    governed.case_meta.state_revision += 1
    from app.agent.api.loaders import _persist_live_governed_state # noqa: PLC0415
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=governed,
    )

    return OverrideResponse(
        session_id=session_id,
        revision_before=rev_before,
        revision_after=governed.case_meta.state_revision,
        governance=OverrideGovernanceResult(
            gov_class=governed.governance.gov_class,
            rfq_admissible=governed.governance.rfq_admissible,
            release_status=_governed_release_status_snapshot(governed),
        ),
    )
