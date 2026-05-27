import logging
import os
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path

from app.agent.api.models import (
    ReviewRequest,
    ReviewResponse,
    ReviewSeedResponse,
    HumanReviewDecisionRequest,
    HumanReviewWorkflowResponse,
    OverrideRequest,
    OverrideResponse,
    OverrideGovernanceResult,
    CaseDeltaDecisionRequest,
    CaseDeltaDecisionResponse,
)
from app.agent.state.agent_state import AgentState
from app.agent.state.models import GovernedPersistenceMarker, UserOverride
from app.agent.state.reducers import (
    reduce_observed_to_normalized,
    reduce_normalized_to_asserted,
    reduce_asserted_to_governance,
)
from app.agent.api.deps import (
    SESSION_STORE,
    RequestUser,
    get_current_request_user,
)
from app.agent.api.loaders import (
    _load_live_governed_state,
    _persist_live_governed_state,
    require_structured_review_state,
    persist_structured_review_commit,
    _persist_review_outcome_to_live_governed_state,
)
from app.agent.api.utils import (
    _with_case_event,
)
from app.agent.domain.critical_review import (
    CriticalReviewGovernanceSummary,
    CriticalReviewRfqBasis,
    CriticalReviewRecommendationPackage,
    CriticalReviewMatchingPackage,
    CriticalReviewSpecialistInput,
    CriticalReviewSpecialistResult,
    run_critical_review_specialist,
    critical_review_result_to_dict,
)
from app.agent.state.case_state import PROJECTION_VERSION
from app.agent.domain.case_delta import (
    acceptance_block_reason,
    build_assistant_delta_event,
    build_case_delta_decision_event,
    latest_proposed_delta_event,
    select_delta_fields,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.agent.domain.dependency_graph import mark_stale_derived_values
from app.agent.v92.review_workflow import (
    apply_human_review_decision,
    build_review_workflow_contract,
)

_log = logging.getLogger(__name__)

router = APIRouter()


def _override_analysis_message(applied_fields: list[str]) -> str:
    field_list = ", ".join(applied_fields) if applied_fields else "Parameter"
    return (
        "Direkteingabe wurde als Nutzerangabe übernommen. "
        f"Aktualisierte Felder: {field_list}. "
        "Bitte analysiere den aktuellen Dichtungsfall mit diesen bekannten Angaben, "
        "benenne kritische Punkte, fehlende Blocker und die nächste sinnvolle Rückfrage. "
        "Keine finale Freigabe und keine Materialentscheidung."
    )


async def _run_override_analysis_turn(
    *,
    current_user: RequestUser,
    session_id: str,
    applied_fields: list[str],
) -> dict[str, Any]:
    from app.agent.api.assembly import (  # noqa: PLC0415
        _assemble_governed_stream_payload,
        _build_governed_reply_context,
    )
    from app.agent.api.governed_runtime import run_governed_graph_turn  # noqa: PLC0415
    from app.agent.api.loaders import _persist_live_governed_state  # noqa: PLC0415
    from app.agent.api.utils import (  # noqa: PLC0415
        _with_case_event,
        _with_governed_conversation_turn,
    )

    graph_request = SimpleNamespace(
        session_id=session_id,
        message=_override_analysis_message(applied_fields),
    )
    turn_result = await run_governed_graph_turn(
        request=graph_request,
        current_user=current_user,
        pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY.value,
        append_user_message=False,
    )
    context = _build_governed_reply_context(
        result_state=turn_result.result_state,
        persisted_state=turn_result.persisted_state,
    )
    payload = _assemble_governed_stream_payload(context=context)
    assistant_message = str(
        payload.get("assistant_message")
        or payload.get("answer_markdown")
        or payload.get("reply")
        or ""
    ).strip()
    if assistant_message:
        updated_state = _with_governed_conversation_turn(
            turn_result.persisted_state,
            role="assistant",
            content=assistant_message,
        )
        case_event = build_assistant_delta_event(
            case_id=session_id,
            turn_index=int(
                getattr(turn_result.result_state, "user_turn_index", 0)
                or turn_result.result_state.analysis_cycle
                or 0
            ),
            assistant_message=assistant_message,
            delta=context.proposed_case_delta,
            persistence_marker=turn_result.persisted_state.persistence_marker,
        )
        updated_state = _with_case_event(updated_state, event=case_event)
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=session_id,
            state=updated_state,
            pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY.value,
        )
    return payload

def _find_session(session_id: str) -> AgentState | None:
    return SESSION_STORE.get(session_id)

def _save_session(session_id: str, state: AgentState) -> None:
    SESSION_STORE[session_id] = state

def _build_review_handover_response(
    state: AgentState,
    *,
    session_id: str,
    action: str,
    outcome: Optional[CriticalReviewSpecialistResult] = None,
) -> ReviewResponse:
    passed = bool(outcome and outcome.critical_review_passed)
    review_state = (
        "approved_scope"
        if passed
        else ("changes_required" if action == "approve" else "rejected")
    )
    release_status = "inquiry_ready" if passed else "inadmissible"
    reply = (
        "Die technische Überprüfung ist für den definierten Anfrageumfang vorbereitet."
        if passed
        else "Die technische Überprüfung ist noch nicht abgeschlossen; offene Punkte bleiben sichtbar."
    )
    return ReviewResponse(
        session_id=session_id,
        action=action,
        review_state=review_state,
        release_status=release_status,
        is_handover_ready=passed,
        handover={
            "critical_review": (
                critical_review_result_to_dict(outcome) if outcome is not None else None
            ),
            "projection_version": PROJECTION_VERSION,
        },
        reply=reply,
    )

def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item is not None and str(item).strip())
    if value is None or value == "":
        return ()
    return (str(value),)


def _build_critical_review_input(
    state: AgentState,
    *,
    review_required: bool,
) -> CriticalReviewSpecialistInput:
    case_state = _as_dict(state.get("case_state"))
    governance_state = _as_dict(
        state.get("governance_state")
        or case_state.get("governance_state")
        or case_state.get("governance")
    )
    rfq_state = _as_dict(
        state.get("rfq_state") or case_state.get("rfq_state") or case_state.get("rfq")
    )
    matching_state = _as_dict(
        state.get("matching_state")
        or case_state.get("matching_state")
        or case_state.get("matching")
    )
    requirement_class = _as_dict(
        case_state.get("requirement_class")
        or (case_state.get("result_contract") or {}).get("requirement_class")
        or rfq_state.get("requirement_class")
    )
    selected_manufacturer = _as_dict(
        matching_state.get("selected_manufacturer_ref")
        or rfq_state.get("selected_manufacturer_ref")
    )
    rfq_admissibility = str(
        governance_state.get("rfq_admissibility")
        or rfq_state.get("rfq_admissibility")
        or ("ready" if rfq_state.get("rfq_ready") is True else "inadmissible")
    )
    release_status = str(
        governance_state.get("release_status")
        or ("inquiry_ready" if rfq_admissibility == "ready" else "inadmissible")
    )
    return CriticalReviewSpecialistInput(
        governance_summary=CriticalReviewGovernanceSummary(
            release_status=release_status,
            rfq_admissibility=rfq_admissibility,
            unknowns_release_blocking=_as_tuple(
                governance_state.get("unknowns_release_blocking")
                or rfq_state.get("unknowns_release_blocking")
            ),
            unknowns_manufacturer_validation=_as_tuple(
                governance_state.get("unknowns_manufacturer_validation")
                or rfq_state.get("open_points")
            ),
            scope_of_validity=_as_tuple(
                governance_state.get("scope_of_validity")
                or governance_state.get("validity_limits")
            ),
            conflicts=_as_tuple(governance_state.get("conflicts")),
            review_required=review_required,
        ),
        recommendation_package=CriticalReviewRecommendationPackage(
            requirement_class=requirement_class or None,
        ),
        matching_package=CriticalReviewMatchingPackage(
            status=str(
                matching_state.get("status")
                or rfq_state.get("matching_status")
                or ""
            ),
            selected_manufacturer_ref=selected_manufacturer or None,
        ),
        rfq_basis=CriticalReviewRfqBasis(
            rfq_object=_as_dict(rfq_state.get("rfq_object")) or None,
            recipient_refs=tuple(
                ref
                for ref in (
                    _as_dict(item)
                    for item in list(rfq_state.get("recipient_refs") or [])
                    if isinstance(item, dict)
                )
                if ref
            ),
        ),
    )

def _apply_review_decision(state: AgentState, request: ReviewRequest) -> AgentState:
    from copy import deepcopy # noqa: PLC0415
    new_state = deepcopy(state)
    case_state = new_state.get("case_state") or {}
    case_meta = case_state.get("case_meta") or {}
    case_meta["lifecycle_status"] = "review_completed" if request.action == "approve" else "review_rejected"
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
    if request.action == "approve":
        specialist_input = _build_critical_review_input(
            state,
            review_required=False,
        )
        outcome = run_critical_review_specialist(specialist_input)

        if outcome:
            await _persist_review_outcome_to_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                case_state=state.get("case_state"),
                sealing_state=state,
                assistant_reply=(
                    "Die technische Überprüfung ist abgeschlossen."
                    if outcome.critical_review_passed
                    else "Die technische Überprüfung ist blockiert; Korrekturen bleiben offen."
                ),
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
        action=request.action,
        outcome=outcome,
    )

@router.post("/review/seed", response_model=ReviewSeedResponse)
async def review_seed_endpoint() -> ReviewSeedResponse:
    return ReviewSeedResponse(
        session_id="seed",
        review_state="none",
        release_status="inadmissible",
        review_reason="seed_endpoint_available",
    )


@router.get("/review/workflow/{session_id}", response_model=HumanReviewWorkflowResponse)
async def review_workflow_endpoint(
    session_id: str = Path(...),
    current_user: RequestUser = Depends(get_current_request_user),
) -> HumanReviewWorkflowResponse:
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=False,
    )
    if governed is None:
        raise HTTPException(status_code=404, detail="Session not found")
    workflow = build_review_workflow_contract(
        governed,
        session_id=session_id,
        turn_id="review-workflow",
    )
    return HumanReviewWorkflowResponse(
        session_id=session_id,
        workflow=workflow,
        review_state=governed.review_state.model_dump(mode="json"),
        v92_dashboard=dict(workflow.get("dashboard_contract") or {}),
        reply="Review workflow loaded.",
    )


@router.post("/review/workflow/{session_id}/decision", response_model=HumanReviewWorkflowResponse)
async def review_workflow_decision_endpoint(
    request: HumanReviewDecisionRequest,
    session_id: str = Path(...),
    current_user: RequestUser = Depends(get_current_request_user),
) -> HumanReviewWorkflowResponse:
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=False,
    )
    if governed is None:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = apply_human_review_decision(
        governed,
        session_id=session_id,
        reviewer_id=request.reviewer_id,
        action=request.action,
        scope=request.scope,
        notes=request.reviewer_notes,
    )
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=updated,
        pre_gate_classification="EXPERT_REVIEW",
    )
    workflow = build_review_workflow_contract(
        updated,
        session_id=session_id,
        turn_id="review-workflow",
    )
    return HumanReviewWorkflowResponse(
        session_id=session_id,
        workflow=workflow,
        review_state=updated.review_state.model_dump(mode="json"),
        v92_dashboard=dict(workflow.get("dashboard_contract") or {}),
        reply="Review decision persisted.",
    )

@router.patch("/session/{session_id}/override", response_model=OverrideResponse)
async def session_override_endpoint(
    request: OverrideRequest,
    session_id: str = Path(...),
    current_user: RequestUser = Depends(get_current_request_user),
):
    if not os.getenv("REDIS_URL"):
        raise HTTPException(status_code=503, detail="Live governed state store is not configured")

    from app.agent.api.loaders import _load_live_governed_state # noqa: PLC0415
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=True,
    )
    if not governed:
        raise HTTPException(status_code=404, detail="Session not found")

    rev_before = 0
    marker = governed.persistence_marker
    if marker is not None and marker.postgres_snapshot_revision is not None:
        rev_before = marker.postgres_snapshot_revision

    observed = governed.observed
    applied_fields: list[str] = []
    for override in request.overrides:
        observed = observed.with_override(
            UserOverride(
                field_name=override.field_name,
                override_value=override.value,
                override_unit=override.unit,
                turn_index=request.turn_index,
            )
        )
        applied_fields.append(override.field_name)

    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    governance = reduce_asserted_to_governance(asserted)
    revision_after = rev_before + 1
    governed = governed.model_copy(
        update={
            "observed": observed,
            "normalized": normalized,
            "asserted": asserted,
            "governance": governance,
            "persistence_marker": GovernedPersistenceMarker(
                postgres_snapshot_revision=revision_after,
            ),
        }
    )

    from app.agent.api.loaders import _persist_live_governed_state # noqa: PLC0415
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=governed,
    )

    analysis_payload: dict[str, Any] = {}
    response_governed = governed
    if request.run_analysis:
        analysis_payload = await _run_override_analysis_turn(
            current_user=current_user,
            session_id=session_id,
            applied_fields=applied_fields,
        )
        from app.agent.api.loaders import _load_live_governed_state  # noqa: PLC0415

        analyzed_governed = await _load_live_governed_state(
            current_user=current_user,
            session_id=session_id,
            create_if_missing=False,
        )
        if analyzed_governed is not None:
            response_governed = analyzed_governed

    return OverrideResponse(
        session_id=session_id,
        applied_fields=applied_fields,
        governance=OverrideGovernanceResult(
            gov_class=response_governed.governance.gov_class,
            rfq_admissible=response_governed.governance.rfq_admissible,
            blocking_unknowns=list(response_governed.asserted.blocking_unknowns),
            conflict_flags=list(response_governed.asserted.conflict_flags),
            validity_limits=list(response_governed.governance.validity_limits),
            open_validation_points=list(response_governed.governance.open_validation_points),
        ),
        reply=analysis_payload.get("reply") if analysis_payload else None,
        answer_markdown=analysis_payload.get("answer_markdown") if analysis_payload else None,
        response_class=analysis_payload.get("response_class") if analysis_payload else None,
        structured_state=analysis_payload.get("structured_state") if analysis_payload else None,
        run_meta=analysis_payload.get("run_meta") if analysis_payload else None,
    )

@router.post("/session/{session_id}/case-delta", response_model=CaseDeltaDecisionResponse)
async def session_case_delta_decision_endpoint(
    request: CaseDeltaDecisionRequest,
    session_id: str = Path(...),
    current_user: RequestUser = Depends(get_current_request_user),
):
    if not os.getenv("REDIS_URL"):
        raise HTTPException(status_code=503, detail="Live governed state store is not configured")

    from app.agent.api.loaders import _load_live_governed_state # noqa: PLC0415
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        create_if_missing=False,
    )
    if not governed:
        raise HTTPException(status_code=404, detail="Session not found")

    proposal_event = latest_proposed_delta_event(governed)
    if proposal_event is None:
        raise HTTPException(status_code=404, detail="No proposed case delta found")

    selected_fields = select_delta_fields(
        proposal_event.proposed_case_delta,
        field_names=request.field_names or None,
    )
    if not selected_fields:
        raise HTTPException(status_code=422, detail="No matching proposed fields selected")

    rev_before = 0
    marker = governed.persistence_marker
    if marker is not None and marker.postgres_snapshot_revision is not None:
        rev_before = marker.postgres_snapshot_revision

    observed = governed.observed
    applied_fields: list[str] = []
    rejected_fields: list[str] = []
    decision_fields = selected_fields
    if request.action == "accept":
        acceptable_fields = []
        blocked_reasons: dict[str, str] = {}
        for field in selected_fields:
            block_reason = acceptance_block_reason(field)
            if block_reason is not None:
                rejected_fields.append(field.field_name)
                blocked_reasons[field.field_name] = block_reason
                continue
            acceptable_fields.append(field)

        if not acceptable_fields:
            reason_text = "; ".join(
                f"{name}: {reason}" for name, reason in blocked_reasons.items()
            )
            raise HTTPException(
                status_code=422,
                detail=f"No proposed fields can be accepted yet. {reason_text}",
            )

        decision_fields = acceptable_fields
        for field in acceptable_fields:
            turn_index = request.turn_index or field.source_turn_index
            observed = observed.with_override(
                UserOverride(
                    field_name=field.field_name,
                    override_value=field.proposed_value,
                    override_unit=field.unit,
                    turn_index=turn_index,
                )
            )
            applied_fields.append(field.field_name)
    else:
        rejected_fields = [field.field_name for field in selected_fields]

    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    governance = reduce_asserted_to_governance(asserted)

    revision_after = rev_before + 1
    derived = governed.derived
    if request.action == "accept" and applied_fields:
        derived = mark_stale_derived_values(
            derived,
            changed_fields=applied_fields,
            new_revision=revision_after,
            reason="accepted_case_delta_changed_inputs",
        )

    updated = governed.model_copy(
        update={
            "observed": observed,
            "normalized": normalized,
            "asserted": asserted,
            "derived": derived,
            "governance": governance,
            "persistence_marker": GovernedPersistenceMarker(
                postgres_snapshot_revision=revision_after,
                postgres_case_revision=revision_after,
            ),
        }
    )
    decision_event = build_case_delta_decision_event(
        case_id=session_id,
        action=request.action,
        fields=decision_fields,
        source_event_id=proposal_event.event_id,
        persistence_marker=governed.persistence_marker,
    )
    updated = _with_case_event(updated, event=decision_event)

    from app.agent.api.loaders import _persist_live_governed_state # noqa: PLC0415
    await _persist_live_governed_state(
        current_user=current_user,
        session_id=session_id,
        state=updated,
    )

    return CaseDeltaDecisionResponse(
        session_id=session_id,
        action=request.action,
        source_event_id=proposal_event.event_id,
        applied_fields=applied_fields,
        rejected_fields=rejected_fields,
        governance=OverrideGovernanceResult(
            gov_class=updated.governance.gov_class,
            rfq_admissible=updated.governance.rfq_admissible,
            blocking_unknowns=list(updated.asserted.blocking_unknowns),
            conflict_flags=list(updated.asserted.conflict_flags),
            validity_limits=list(updated.governance.validity_limits),
            open_validation_points=list(updated.governance.open_validation_points),
        ),
    )
