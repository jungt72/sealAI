"""V9.2 turn envelope and answer-context assembly."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.agent.runtime.output_guard import FAST_PATH_GUARD_FALLBACK
from app.agent.state.models import GovernedSessionState
from app.agent.v92.adversarial_review import (
    review_answer_draft,
    review_answer_draft_with_llm_fallback,
)
from app.agent.v92.contracts import (
    AdversarialReviewVerdict,
    FinalAnswerContext,
    FinalGuardResult,
    NonTechnicalAnswerContext,
    StateMutationPolicy,
    StreamingPolicy,
    TurnEnvelope,
    TurnRoute,
)
from app.agent.v92.dashboard_contract import (
    build_v92_dashboard_contract,
    extract_case_revision,
)
from app.agent.v92.final_guard import guarded_fallback_answer, validate_final_output
from app.agent.v92.revision_composer import revise_answer_once
from app.agent.v92.turn_boundary import resolve_turn_boundary
from app.observability.langsmith import traceable
from app.observability.sealai_quality import emit_quality_trace, stable_trace_hash


_TECHNICAL_ROUTES: frozenset[str] = frozenset(
    {
        "engineering_case_update",
        "engineering_recommendation",
        "leakage_failure_analysis",
        "standards_or_compliance",
        "rfq_readiness",
        "expert_review_action",
    }
)
_DEFAULT_FORBIDDEN_CLAIMS = [
    "final_engineering_release",
    "final_material_suitability",
    "compound_claim_from_material_family",
    "product_claim_without_product_evidence",
    "norm_conformity_without_licensed_rule_or_expert_review",
    "calculation_as_release_claim",
]


def _dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def _dump_list(values: Any) -> list[dict[str, Any]]:
    return [_dump(value) for value in list(values or []) if _dump(value)]


def _trace_id(session_id: str, user_message: str, route: str) -> str:
    digest = sha256(f"{session_id}|{route}|{user_message}".encode("utf-8")).hexdigest()
    return f"trace_{digest[:24]}"


def _adversarial_review_source(
    verdict: AdversarialReviewVerdict | None,
    *,
    llm_reviewer_enabled: bool | None = None,
) -> str:
    if verdict is None:
        return "not_required"
    if bool(verdict.prompt_trace):
        return "llm"
    return "deterministic_fallback" if llm_reviewer_enabled else "deterministic"


def _emit_v92_output_quality_trace(
    *,
    envelope: TurnEnvelope,
    final_guard: FinalGuardResult,
    adversarial_review: AdversarialReviewVerdict | None,
    revision_applied: bool,
    guarded_fallback_used: bool,
    initial_guard: FinalGuardResult | None,
    component: str,
    llm_reviewer_enabled: bool | None = None,
) -> None:
    emit_quality_trace(
        component=component,
        tags=("v92-output-contract", "final-guard"),
        session_id=envelope.session_id,
        case_id=envelope.case_id,
        turn_id_hash=stable_trace_hash(envelope.turn_id),
        trace_id_hash=stable_trace_hash(envelope.trace_id),
        route=envelope.route,
        intent=envelope.intent,
        is_technical=envelope.is_technical,
        streaming_policy=envelope.streaming_policy,
        requires_engine=envelope.requires_engine,
        requires_evidence=envelope.requires_evidence,
        requires_adversarial_review=envelope.requires_adversarial_review,
        adversarial_review_source=_adversarial_review_source(
            adversarial_review,
            llm_reviewer_enabled=llm_reviewer_enabled,
        ),
        adversarial_review_decision=getattr(adversarial_review, "decision", None),
        adversarial_review_severity=getattr(adversarial_review, "severity", None),
        unsupported_claims_count=len(
            getattr(adversarial_review, "unsupported_claims", []) or []
        ),
        forbidden_claims_count=len(
            getattr(adversarial_review, "forbidden_claims", []) or []
        ),
        required_revision_count=len(
            getattr(adversarial_review, "required_revision_instructions", []) or []
        ),
        revision_applied=revision_applied,
        guarded_fallback_used=guarded_fallback_used,
        initial_final_guard_decision=getattr(initial_guard, "decision", None),
        initial_final_guard_severity=getattr(initial_guard, "severity", None),
        final_guard_decision=final_guard.decision,
        final_guard_severity=final_guard.severity,
        final_stream_allowed=final_guard.final_stream_allowed,
        human_review_required=final_guard.human_review_required,
        final_guard_blocked_reasons_count=len(final_guard.blocked_reasons),
        final_guard_required_revisions_count=len(final_guard.required_revisions),
        llm_reviewer_enabled=llm_reviewer_enabled,
        llm_reviewer_succeeded=(
            _adversarial_review_source(
                adversarial_review,
                llm_reviewer_enabled=llm_reviewer_enabled,
            )
            == "llm"
            if llm_reviewer_enabled is not None
            else None
        ),
    )


def infer_turn_route(
    *,
    route_hint: str | None = None,
    policy_path: str | None = None,
    response_class: str | None = None,
    answer_mode: str | None = None,
    user_message: str = "",
) -> TurnRoute:
    value = (
        route_hint or answer_mode or policy_path or response_class or ""
    ).casefold()
    message = user_message.casefold()
    if "unsafe" in value or "blocked" in value or "guard" in value:
        return "unsafe_or_blocked"
    if "rfq" in value or "inquiry_ready" in value:
        return "rfq_readiness"
    if "active_case_process" in value:
        return "knowledge_case_side_question"
    if "side" in value or "knowledge" in value:
        return (
            "knowledge_case_side_question" if "side" in value else "knowledge_general"
        )
    if "smalltalk" in value or "fast" in value or "conversation" in value:
        return "smalltalk"
    if "review" in value:
        return "expert_review_action"
    if any(
        token in message
        for token in ("leckage", "schaden", "ausfall", "root cause", "ursache")
    ):
        return "leakage_failure_analysis"
    if any(
        token in message
        for token in ("norm", "standard", "konform", "atex", "fda", "reach")
    ):
        return "standards_or_compliance"
    if any(
        token in message
        for token in (
            "bewerte",
            "beurteile",
            "einschaetz",
            "einschätz",
            "screening",
            "eignung",
        )
    ):
        return "engineering_recommendation"
    if response_class in {"technical_preselection", "candidate_shortlist"}:
        return "engineering_recommendation"
    if response_class in {"structured_clarification", "governed_state_update"}:
        return "engineering_case_update"
    return "engineering_case_update"


def _route_mutation_policy(route: TurnRoute) -> StateMutationPolicy:
    if route in {
        "smalltalk",
        "abusive_or_shit_chat",
        "knowledge_general",
        "knowledge_case_side_question",
        "unsafe_or_blocked",
    }:
        return "none"
    if route == "expert_review_action":
        return "review_action"
    return "case_revision_allowed"


def _route_streaming_policy(route: TurnRoute) -> StreamingPolicy:
    if route == "unsafe_or_blocked":
        return "blocked"
    if route in _TECHNICAL_ROUTES:
        return "status_only_until_guarded_final"
    return "direct_stream_allowed"


def build_turn_envelope(
    *,
    session_id: str,
    user_message: str,
    route: TurnRoute,
    state: GovernedSessionState | None = None,
    case_id: str | None = None,
    intent: str | None = None,
    turn_id: str | None = None,
) -> TurnEnvelope:
    revision = extract_case_revision(state)
    is_technical = route in _TECHNICAL_ROUTES
    return TurnEnvelope(
        turn_id=turn_id or f"turn_{uuid4().hex}",
        session_id=session_id,
        case_id=case_id or session_id or None,
        case_revision_before=revision,
        case_revision_after=revision,
        user_message=user_message,
        route=route,
        intent=intent or route,
        is_technical=is_technical,
        state_mutation_policy=_route_mutation_policy(route),
        requires_engine=is_technical,
        requires_evidence=is_technical or route == "knowledge_case_side_question",
        requires_adversarial_review=route
        in {
            "engineering_recommendation",
            "leakage_failure_analysis",
            "standards_or_compliance",
            "rfq_readiness",
            "expert_review_action",
        },
        requires_final_guard=True,
        streaming_policy=_route_streaming_policy(route),
        created_at=datetime.now(UTC).isoformat(),
        trace_id=_trace_id(session_id, user_message, route),
    )


def build_nontechnical_answer_context(
    *,
    envelope: TurnEnvelope,
    dashboard_projection: dict[str, Any],
) -> NonTechnicalAnswerContext:
    scope = "knowledge"
    if envelope.route == "smalltalk":
        scope = "smalltalk"
    elif envelope.route == "unsafe_or_blocked":
        scope = "safety"
    return NonTechnicalAnswerContext(
        turn_id=envelope.turn_id,
        route=envelope.route,
        intent=envelope.intent,
        user_message=envelope.user_message,
        answer_scope=scope,  # type: ignore[arg-type]
        state_mutation_policy=envelope.state_mutation_policy,
        forbidden_claims=_DEFAULT_FORBIDDEN_CLAIMS,
        dashboard_projection=dashboard_projection,
    )


def _case_state_summary(state: GovernedSessionState | None) -> dict[str, Any]:
    if state is None:
        return {"state_present": False}
    return {
        "state_present": True,
        "user_turn_index": int(getattr(state, "user_turn_index", 0) or 0),
        "assertion_count": len(
            getattr(getattr(state, "asserted", None), "assertions", {}) or {}
        ),
        "normalized_parameter_count": len(
            getattr(getattr(state, "normalized", None), "parameters", {}) or {}
        ),
        "pending_question": _dump(getattr(state, "pending_question", None)) or None,
        "persistence_marker": _dump(getattr(state, "persistence_marker", None)) or None,
    }


def _required_warnings(state: GovernedSessionState | None) -> list[str]:
    warnings = [
        "Keine finale technische Freigabe ohne passenden Expert-Review-Scope.",
        "Berechnete Werte sind Screening-/Pruefwerte, keine Freigabeclaims.",
    ]
    if state is None:
        warnings.append(
            "Kein vollstaendig persistierter CaseState fuer diese Antwort sichtbar."
        )
        return warnings
    stale_ids = list(
        getattr(getattr(state, "calculation", None), "stale_result_ids", []) or []
    )
    if stale_ids:
        warnings.append(
            "Stale Berechnungen muessen vor technischen Zusagen erneuert werden."
        )
    if getattr(getattr(state, "standards", None), "blocking_gaps", None):
        warnings.append(
            "Norm-/Compliance-Aussagen bleiben ohne lizenzierten Nachweis oder Review begrenzt."
        )
    if getattr(
        getattr(state, "document_evidence", None), "prompt_injection_findings", None
    ):
        warnings.append(
            "Upload-Inhalte wurden als untrusted evidence behandelt, nicht als Instruktion."
        )
    return warnings


def _allowed_claim_level(state: GovernedSessionState | None) -> str:
    approved = getattr(
        getattr(state, "review_state", None), "approved_claim_level", None
    )
    if approved:
        return str(approved)
    if state is None:
        return "L0_raw"
    if getattr(getattr(state, "evidence_graph", None), "nodes", None):
        return "L4_source_backed_screening"
    if getattr(getattr(state, "calculation", None), "results", None):
        return "L3_deterministic_calculation"
    return "L2_screening"


def build_final_answer_context(
    *,
    envelope: TurnEnvelope,
    state: GovernedSessionState | None,
    dashboard_projection: dict[str, Any],
) -> FinalAnswerContext:
    engineering = getattr(state, "engineering", None) if state is not None else None
    challenge = getattr(state, "challenge", None) if state is not None else None
    calculation = getattr(state, "calculation", None) if state is not None else None
    evidence = getattr(state, "evidence_graph", None) if state is not None else None
    standards = getattr(state, "standards", None) if state is not None else None
    compound = getattr(state, "compound_state", None) if state is not None else None
    review = getattr(state, "review_state", None) if state is not None else None
    completeness = getattr(engineering, "completeness_matrix", None)
    stale_items = list(dashboard_projection.get("stale_items") or [])
    review_required = bool(
        state is None
        or stale_items
        or list(getattr(review, "required_review_types", []) or [])
        or str(getattr(review, "status", "not_started") or "")
        in {"pending", "changes_required", "blocked"}
    )
    human_review_reasons: list[str] = []
    if state is None:
        human_review_reasons.append("case_state_missing")
    if stale_items:
        human_review_reasons.append("stale_calculation_or_screening_present")
    human_review_reasons.extend(
        [str(item) for item in list(getattr(review, "required_review_types", []) or [])]
    )

    return FinalAnswerContext(
        turn_id=envelope.turn_id,
        case_id=envelope.case_id,
        case_revision=extract_case_revision(state),
        route=envelope.route,
        intent=envelope.intent,
        is_technical=envelope.is_technical,
        user_message=envelope.user_message,
        case_state_summary=_case_state_summary(state),
        seal_system_summary=_dump(getattr(state, "seal_system", None)) or None,
        engineering_outputs=_dump_list(getattr(engineering, "decisions", []) or []),
        calculation_results=_dump_list(getattr(calculation, "results", []) or []),
        evidence_summary={
            "status": str(getattr(evidence, "status", "pending") or "pending"),
            "node_count": len(list(getattr(evidence, "nodes", []) or [])),
            "unresolved_gaps": list(getattr(evidence, "unresolved_gaps", []) or []),
        },
        standards_summary={
            "status": str(getattr(standards, "status", "pending") or "pending"),
            "blocking_gaps": list(getattr(standards, "blocking_gaps", []) or []),
            "claim_boundary": str(getattr(standards, "claim_boundary", "") or ""),
        },
        risk_findings=_dump_list(getattr(engineering, "risk_findings", []) or [])
        + _dump_list(getattr(challenge, "findings", []) or []),
        completeness=_dump(completeness) or None,
        material_candidates=_dump_list(
            getattr(compound, "material_family_candidates", []) or []
        ),
        compound_candidates=_dump_list(
            getattr(compound, "compound_candidates", []) or []
        ),
        product_candidates=_dump_list(
            getattr(compound, "product_candidates", []) or []
        ),
        allowed_claim_level=_allowed_claim_level(state),
        forbidden_claims=list(
            dict.fromkeys(
                [
                    *_DEFAULT_FORBIDDEN_CLAIMS,
                    *list(
                        getattr(getattr(state, "dossier", None), "forbidden_claims", [])
                        or []
                    ),
                ]
            )
        ),
        required_warnings=_required_warnings(state),
        stale_items=stale_items,
        review_required=review_required,
        human_review_reasons=list(dict.fromkeys(human_review_reasons)),
        dashboard_projection=dashboard_projection,
        prompt_trace=None,
        guard_trace=None,
    )


def apply_v92_contracts_to_payload(
    payload: dict[str, Any],
    *,
    session_id: str,
    user_message: str,
    state: GovernedSessionState | None = None,
    route_hint: str | None = None,
    intent: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    updated = dict(payload)
    response_class = str(
        updated.get("response_class") or updated.get("responseClass") or ""
    )
    run_meta = dict(updated.get("run_meta") or {})
    answer_trace = (
        run_meta.get("answer_trace")
        if isinstance(run_meta.get("answer_trace"), dict)
        else {}
    )
    composer_meta = (
        run_meta.get("governed_answer_composer")
        if isinstance(run_meta.get("governed_answer_composer"), dict)
        else {}
    )
    prompt_trace = (
        composer_meta.get("prompt_trace")
        if isinstance(composer_meta, dict)
        and isinstance(composer_meta.get("prompt_trace"), dict)
        else None
    )
    answer_mode = str(answer_trace.get("answer_mode") or "")
    policy_path = str(updated.get("policy_path") or "")
    inferred_route = infer_turn_route(
        route_hint=route_hint,
        policy_path=policy_path,
        response_class=response_class,
        answer_mode=answer_mode,
        user_message=user_message,
    )
    boundary = resolve_turn_boundary(
        user_message=user_message,
        session_id=session_id,
        state=state,
        payload=updated,
        route_hint=route_hint or inferred_route,
        policy_path=policy_path,
        response_class=response_class,
        answer_mode=answer_mode,
    )
    route = boundary.route
    envelope = build_turn_envelope(
        session_id=session_id,
        user_message=user_message,
        route=route,
        state=state,
        case_id=case_id or session_id,
        intent=intent or boundary.intent,
    )
    dashboard = build_v92_dashboard_contract(
        state,
        turn_id=envelope.turn_id,
        route=route,
        case_id=envelope.case_id,
    )
    dashboard_payload = dashboard.model_dump(mode="json")
    visible_answer = str(
        updated.get("answer_markdown")
        or updated.get("assistant_message")
        or updated.get("reply")
        or ""
    ).strip()

    adversarial_review: AdversarialReviewVerdict | None = None
    final_guard: FinalGuardResult
    final_context: FinalAnswerContext | None = None
    nontechnical_context: NonTechnicalAnswerContext | None = None
    revision_applied = False
    guarded_fallback_used = False
    initial_guard: FinalGuardResult | None = None

    if envelope.is_technical:
        final_context = build_final_answer_context(
            envelope=envelope,
            state=state,
            dashboard_projection=dashboard_payload,
        )
        final_context.prompt_trace = prompt_trace
        if envelope.requires_adversarial_review:
            adversarial_review = review_answer_draft(visible_answer, final_context)
            if adversarial_review.decision == "revise":
                revision_applied = True
                visible_answer = revise_answer_once(
                    visible_answer,
                    context=final_context,
                    verdict=adversarial_review,
                )
        final_guard = validate_final_output(
            visible_answer,
            context=final_context,
            adversarial_review=adversarial_review,
        )
        initial_guard = final_guard
        if (
            final_guard.decision in {"block", "human_review"}
            or not final_guard.final_stream_allowed
        ):
            guarded_fallback_used = True
            visible_answer = guarded_fallback_answer(
                context=final_context,
                guard_result=final_guard,
            )
            final_guard = validate_final_output(visible_answer, context=final_context)
        final_context.guard_trace = final_guard.model_dump(mode="json")
        final_context.adversarial_review = (
            adversarial_review.model_dump(mode="json") if adversarial_review else None
        )
        updated["final_answer_context"] = final_context.model_dump(mode="json")
        if adversarial_review is not None:
            dashboard.challenge_card = {
                "decision": adversarial_review.decision,
                "severity": adversarial_review.severity,
                "summary": adversarial_review.user_visible_challenge_summary,
                "unsupported_claims": list(adversarial_review.unsupported_claims),
                "forbidden_claims": list(adversarial_review.forbidden_claims),
            }
            dashboard_payload = dashboard.model_dump(mode="json")
    else:
        nontechnical_context = build_nontechnical_answer_context(
            envelope=envelope,
            dashboard_projection=dashboard_payload,
        )
        final_guard = validate_final_output(
            visible_answer, context=nontechnical_context
        )
        initial_guard = final_guard
        # F2: a non-technical block must ENFORCE, not just record telemetry —
        # substitute the same safe fallback the technical branch (:471) and L1 use,
        # then re-validate. Without this, a detected knowledge-turn leak (e.g. an
        # L2-only "sind geeignet") still left in visible_answer below.
        if (
            final_guard.decision in {"block", "human_review"}
            or not final_guard.final_stream_allowed
        ):
            guarded_fallback_used = True
            visible_answer = FAST_PATH_GUARD_FALLBACK
            final_guard = validate_final_output(
                visible_answer, context=nontechnical_context
            )
        nontechnical_context.guard_trace = final_guard.model_dump(mode="json")
        updated["nontechnical_answer_context"] = nontechnical_context.model_dump(
            mode="json"
        )

    updated["answer_markdown"] = visible_answer
    updated["assistant_message"] = visible_answer
    if str(updated.get("reply") or "").strip():
        updated["reply"] = visible_answer

    updated["turn_envelope"] = envelope.model_dump(mode="json")
    updated["turn_boundary_decision"] = boundary.model_dump(mode="json")
    updated["final_guard_result"] = final_guard.model_dump(mode="json")
    updated["v92_dashboard"] = dashboard_payload
    ui = dict(updated.get("ui") or {})
    ui.setdefault("v92_contract", dashboard_payload)
    updated["ui"] = ui
    run_meta["v92"] = {
        "turn_id": envelope.turn_id,
        "trace_id": envelope.trace_id,
        "route": envelope.route,
        "streaming_policy": envelope.streaming_policy,
        "final_guard_decision": final_guard.decision,
        "final_guard_severity": final_guard.severity,
        "final_stream_allowed": final_guard.final_stream_allowed,
        "human_review_required": final_guard.human_review_required,
        "initial_final_guard_decision": getattr(initial_guard, "decision", None),
        "guarded_fallback_used": guarded_fallback_used,
        "adversarial_review_source": _adversarial_review_source(adversarial_review),
        "adversarial_review_decision": getattr(adversarial_review, "decision", None),
        "adversarial_review_severity": getattr(adversarial_review, "severity", None),
        "revision_applied": revision_applied,
        "dashboard_contract_version": dashboard.schema_version,
        "turn_boundary_decision": boundary.model_dump(mode="json"),
    }
    updated["run_meta"] = run_meta
    _emit_v92_output_quality_trace(
        envelope=envelope,
        final_guard=final_guard,
        adversarial_review=adversarial_review,
        revision_applied=revision_applied,
        guarded_fallback_used=guarded_fallback_used,
        initial_guard=initial_guard,
        component="v92_output_contract",
    )
    return updated


@traceable(name="sealai.v92_adversarial_review", run_type="chain")
async def apply_async_adversarial_review_to_payload(
    payload: dict[str, Any],
    *,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Optionally run the LLM adversarial reviewer over an existing V9.2 payload.

    This preserves the existing TurnEnvelope and FinalAnswerContext; it only
    strengthens the review/guard stage. The default is off unless explicitly
    enabled via ``SEALAI_ENABLE_LLM_ADVERSARIAL_REVIEW=1``.
    """

    use_llm = (
        str(os.getenv("SEALAI_ENABLE_LLM_ADVERSARIAL_REVIEW", "")).strip().lower()
        in {"1", "true", "yes", "on"}
        if enabled is None
        else enabled
    )
    if not use_llm:
        return payload
    if not isinstance(payload.get("final_answer_context"), dict):
        return payload
    envelope = payload.get("turn_envelope")
    if not isinstance(envelope, dict) or not bool(
        envelope.get("requires_adversarial_review")
    ):
        return payload

    updated = dict(payload)
    final_context = FinalAnswerContext.model_validate(updated["final_answer_context"])
    visible_answer = str(
        updated.get("answer_markdown")
        or updated.get("assistant_message")
        or updated.get("reply")
        or ""
    ).strip()
    verdict = await review_answer_draft_with_llm_fallback(visible_answer, final_context)
    revision_applied = False
    if verdict.decision == "revise":
        revision_applied = True
        visible_answer = revise_answer_once(
            visible_answer,
            context=final_context,
            verdict=verdict,
        )
    guard = validate_final_output(
        visible_answer,
        context=final_context,
        adversarial_review=verdict,
    )
    initial_guard = guard
    guarded_fallback_used = False
    if guard.decision in {"block", "human_review"} or not guard.final_stream_allowed:
        guarded_fallback_used = True
        visible_answer = guarded_fallback_answer(
            context=final_context, guard_result=guard
        )
        guard = validate_final_output(visible_answer, context=final_context)

    final_context.adversarial_review = verdict.model_dump(mode="json")
    final_context.guard_trace = guard.model_dump(mode="json")
    updated["answer_markdown"] = visible_answer
    updated["assistant_message"] = visible_answer
    if str(updated.get("reply") or "").strip():
        updated["reply"] = visible_answer
    updated["final_answer_context"] = final_context.model_dump(mode="json")
    updated["final_guard_result"] = guard.model_dump(mode="json")
    dashboard = dict(updated.get("v92_dashboard") or {})
    dashboard["challenge_card"] = {
        "decision": verdict.decision,
        "severity": verdict.severity,
        "summary": verdict.user_visible_challenge_summary,
        "unsupported_claims": list(verdict.unsupported_claims),
        "forbidden_claims": list(verdict.forbidden_claims),
    }
    updated["v92_dashboard"] = dashboard
    ui = dict(updated.get("ui") or {})
    ui["v92_contract"] = dashboard
    updated["ui"] = ui
    run_meta = dict(updated.get("run_meta") or {})
    v92_meta = dict(run_meta.get("v92") or {})
    review_source = _adversarial_review_source(verdict, llm_reviewer_enabled=use_llm)
    v92_meta["adversarial_review_source"] = review_source
    v92_meta["adversarial_review_decision"] = verdict.decision
    v92_meta["adversarial_review_severity"] = verdict.severity
    v92_meta["revision_applied"] = revision_applied
    v92_meta["guarded_fallback_used"] = guarded_fallback_used
    v92_meta["initial_final_guard_decision"] = initial_guard.decision
    v92_meta["final_guard_decision"] = guard.decision
    v92_meta["final_guard_severity"] = guard.severity
    v92_meta["final_stream_allowed"] = guard.final_stream_allowed
    v92_meta["human_review_required"] = guard.human_review_required
    v92_meta["llm_reviewer_enabled"] = use_llm
    v92_meta["llm_reviewer_succeeded"] = review_source == "llm"
    run_meta["v92"] = v92_meta
    updated["run_meta"] = run_meta
    try:
        envelope_model = TurnEnvelope.model_validate(envelope)
    except Exception:  # noqa: BLE001
        envelope_model = TurnEnvelope(
            turn_id=str(envelope.get("turn_id") or final_context.turn_id),
            session_id=str(
                envelope.get("session_id") or final_context.case_id or "unknown"
            ),
            case_id=final_context.case_id,
            case_revision_before=None,
            case_revision_after=final_context.case_revision,
            user_message=final_context.user_message,
            route=final_context.route,
            intent=final_context.intent,
            is_technical=final_context.is_technical,
            state_mutation_policy=str(  # type: ignore[arg-type]
                envelope.get("state_mutation_policy") or "case_revision_allowed"
            ),
            requires_engine=bool(envelope.get("requires_engine", True)),
            requires_evidence=bool(envelope.get("requires_evidence", True)),
            requires_adversarial_review=bool(
                envelope.get("requires_adversarial_review", True)
            ),
            requires_final_guard=bool(envelope.get("requires_final_guard", True)),
            streaming_policy=str(  # type: ignore[arg-type]
                envelope.get("streaming_policy") or "status_only_until_guarded_final"
            ),
            created_at=str(envelope.get("created_at") or datetime.now(UTC).isoformat()),
            trace_id=str(envelope.get("trace_id") or final_context.turn_id),
        )
    _emit_v92_output_quality_trace(
        envelope=envelope_model,
        final_guard=guard,
        adversarial_review=verdict,
        revision_applied=revision_applied,
        guarded_fallback_used=guarded_fallback_used,
        initial_guard=initial_guard,
        component="v92_adversarial_review",
        llm_reviewer_enabled=use_llm,
    )
    return updated
