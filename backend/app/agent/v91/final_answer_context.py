from __future__ import annotations

from typing import Any

from app.agent.v91.contracts import (
    AnswerDepth,
    CaseBinding,
    CommunicationPlan,
    DomainRelevance,
    FinalAnswerContext,
    KnowledgePolicy,
    KnowledgeRagPolicy,
    LLMFreedomDecision,
    LLMFreedomLevel,
    RedFlag,
    RedFlagType,
    ResponseMove,
    ResponseAction,
    ResponsePolicy,
    SemanticBoundaryDecision,
    SemanticIntent,
)


def build_v91_final_answer_context(
    *,
    state: Any,
    governed_context: Any,
) -> FinalAnswerContext:
    """Build the V9.1 read-only answer context for the final composer/guards."""

    response_class = str(getattr(governed_context, "response_class", "") or "")
    question_plan = getattr(governed_context, "v91_question_plan", None)
    evidence_ref_ids = _collect_evidence_ref_ids(state, governed_context)
    risk_claims = _collect_risk_claims(state)
    red_flags = _red_flags_for_final_context(state=state, response_class=response_class)
    freedom = LLMFreedomDecision(
        level=LLMFreedomLevel.RESTRICTED_CASE_CLAIMS,
        red_flags=red_flags,
        allowed_actions=[
            "summarize_governed_facts",
            "explain_uncertainty",
            "ask_planned_question",
            "reference_evidence_only_when_present",
        ],
        forbidden_actions=[
            "final_engineering_release",
            "final_material_recommendation",
            "manufacturer_approval_claim",
            "unplanned_multi_question_intake",
            "invented_evidence_claim",
        ],
        reason="final governed answer may explain, but not release or decide",
    )
    response_policy = ResponsePolicy(
        action=(
            ResponseAction.WAIT_FOR_USER
            if getattr(question_plan, "ask_now", False)
            else ResponseAction.ANSWER_ONLY
        ),
        answer_depth=AnswerDepth.NORMAL,
        graph_allowed=False,
        answer_first=True,
        max_primary_questions=1,
        must_explain_uncertainty=True,
        must_resume_primary_task=False,
        reason="final answer layer after governed graph execution",
    )
    knowledge_policy = KnowledgePolicy(
        rag_policy=(
            KnowledgeRagPolicy.OPTIONAL
            if evidence_ref_ids
            else KnowledgeRagPolicy.NOT_NEEDED
        ),
        can_use_general_model_knowledge=True,
        requires_evidence_for_case_claims=True,
        fallback_allowed=False,
        source_scope="case_orientation",
        reason="final answer may use governed facts and documented evidence refs only",
    )
    communication_plan = _build_communication_plan(
        response_class=response_class,
        question_plan=question_plan,
        response_policy=response_policy,
        freedom=freedom,
        evidence_ref_ids=evidence_ref_ids,
        state=state,
    )
    return FinalAnswerContext(
        semantic_boundary=SemanticBoundaryDecision(
            intent=_intent_from_response_class(response_class),
            domain_relevance=DomainRelevance.CONCRETE_SEALING_CASE,
            case_binding=CaseBinding.ACTIVE_CASE_CONTEXT,
            active_case_exists=True,
            should_mutate_case=False,
            graph_candidate=False,
            confidence=0.82,
            reason=f"governed_final_answer:{response_class or 'unknown'}",
        ),
        freedom_decision=freedom,
        response_policy=response_policy,
        knowledge_policy=knowledge_policy,
        question_plan=question_plan,
        communication_plan=communication_plan,
        allowed_claim_levels=[
            "general_orientation",
            "confirmed_case_fact_summary",
            "open_point_summary",
            "unreleased_hypothesis",
            "planned_next_question",
        ],
        evidence_ref_ids=evidence_ref_ids,
        risk_claims=risk_claims,
    )


def _build_communication_plan(
    *,
    response_class: str,
    question_plan: Any | None,
    response_policy: ResponsePolicy,
    freedom: LLMFreedomDecision,
    evidence_ref_ids: list[str],
    state: Any,
) -> CommunicationPlan:
    asks_question = bool(getattr(question_plan, "ask_now", False))
    is_boundary = bool(
        response_class in {"inquiry_ready", "rfq_preview", "rfq_readiness"}
        or any(
            getattr(flag.type, "value", flag.type)
            in {
                RedFlagType.RFQ_EXPORT_OR_DISPATCH.value,
                RedFlagType.COMPLIANCE_OR_CERTIFICATION.value,
                RedFlagType.SAFETY_CRITICAL.value,
            }
            for flag in freedom.red_flags
        )
    )
    tab_updates = _pending_tab_updates(state)
    response_moves: list[ResponseMove] = [ResponseMove.ACKNOWLEDGE]
    if response_policy.answer_first:
        response_moves.append(ResponseMove.ANSWER)
    if is_boundary:
        response_moves.append(ResponseMove.BOUNDARY)
        if any(
            getattr(flag.type, "value", flag.type)
            == RedFlagType.COMPLIANCE_OR_CERTIFICATION.value
            for flag in freedom.red_flags
        ):
            response_moves.append(ResponseMove.ESCALATE)
    if asks_question:
        response_moves.extend([ResponseMove.JUSTIFY_QUESTION, ResponseMove.CLARIFY])
    elif not is_boundary:
        response_moves.append(ResponseMove.EXPLAIN)
    if tab_updates:
        response_moves.append(ResponseMove.MENTION_TAB_UPDATE)
    if evidence_ref_ids:
        response_moves.append(ResponseMove.DISCLOSE_SOURCE)

    return CommunicationPlan(
        goal=(
            "answer_and_clarify"
            if asks_question and response_policy.answer_first
            else "clarify_only"
            if asks_question
            else "boundary"
            if is_boundary
            else "answer"
        ),
        response_mode=(
            "clarification"
            if asks_question
            else "boundary_refusal"
            if is_boundary
            else "guided_explanation"
        ),
        response_moves=_dedupe_response_moves(response_moves),
        response_depth=_communication_response_depth(response_policy.answer_depth),
        answer_depth=response_policy.answer_depth,
        answer_first=response_policy.answer_first,
        ask_user_question=asks_question,
        max_new_questions=1 if asks_question else 0,
        question_justification_required=asks_question,
        include_boundary_notice=True,
        include_tab_update_notice=bool(tab_updates),
        tab_update_visibility="concise" if tab_updates else "silent",
        source_disclosure_mode="on_claims" if evidence_ref_ids else "none",
        user_question_must_be_answered=response_policy.answer_first,
        primary_question=getattr(question_plan, "primary_question", None),
        primary_question_reason=getattr(question_plan, "reason", None),
        must_mention=["current_boundary"] if is_boundary else [],
        may_mention=list(tab_updates[:2]),
        must_not_mention=[
            "final_engineering_release",
            "external_utility_answer",
            "unplanned_question_chain",
        ],
        forbidden_claims=freedom.forbidden_actions,
        allowed_claim_level="planned_next_question"
        if asks_question
        else "confirmed_case_fact_summary",
    )


def _communication_response_depth(answer_depth: AnswerDepth | str) -> str:
    value = _enum_value(answer_depth)
    if value == AnswerDepth.SHORT.value:
        return "short"
    if value == AnswerDepth.DEEP.value:
        return "deep"
    return "standard"


def _dedupe_response_moves(moves: list[ResponseMove]) -> list[ResponseMove]:
    seen: set[str] = set()
    result: list[ResponseMove] = []
    for move in moves:
        value = _enum_value(move)
        if value in seen:
            continue
        seen.add(value)
        result.append(move)
    return result


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _pending_tab_updates(state: Any) -> list[str]:
    dialogue_debt = getattr(state, "v91_dialogue_debt", None)
    return [
        str(item)
        for item in list(getattr(dialogue_debt, "pending_tab_updates", []) or [])
        if str(item or "").strip()
    ]


def _intent_from_response_class(response_class: str) -> SemanticIntent:
    if response_class in {"inquiry_ready", "rfq_preview", "rfq_readiness"}:
        return SemanticIntent.RFQ_OR_EXPORT
    if response_class == "structured_clarification":
        return SemanticIntent.CASE_INTAKE
    if response_class in {"candidate_shortlist", "technical_preselection"}:
        return SemanticIntent.CONCRETE_SUITABILITY
    return SemanticIntent.CASE_INTAKE


def _red_flags_for_final_context(*, state: Any, response_class: str) -> list[RedFlag]:
    flags = [
        RedFlag(
            type=RedFlagType.CASE_STATE_MUTATION,
            severity="medium",
            reason="final answer verbalizes governed case state",
        )
    ]
    if response_class in {"candidate_shortlist", "technical_preselection"}:
        flags.append(
            RedFlag(
                type=RedFlagType.FINAL_SUITABILITY,
                severity="high",
                reason="candidate wording must stay hypothesis-only",
            )
        )
    if response_class in {"inquiry_ready", "rfq_preview", "rfq_readiness"}:
        flags.append(
            RedFlag(
                type=RedFlagType.RFQ_EXPORT_OR_DISPATCH,
                severity="high",
                reason="RFQ/export wording requires consent boundary",
            )
        )
    governance = getattr(state, "governance", None)
    blockers = list(getattr(governance, "compliance_blockers", []) or [])
    if blockers:
        flags.append(
            RedFlag(
                type=RedFlagType.COMPLIANCE_OR_CERTIFICATION,
                severity="blocking",
                reason="compliance blockers remain open",
            )
        )
    return flags


def _collect_evidence_ref_ids(state: Any, governed_context: Any) -> list[str]:
    refs: list[str] = []
    assertions = getattr(getattr(state, "asserted", None), "assertions", {}) or {}
    for claim in dict(assertions).values():
        refs.extend(str(ref) for ref in list(getattr(claim, "evidence_refs", []) or []))

    challenge = getattr(state, "challenge", None)
    for finding in list(getattr(challenge, "findings", []) or []):
        refs.extend(
            str(ref)
            for ref in list(getattr(finding, "evidence_ref_ids", []) or [])
            if str(ref or "").strip()
        )

    for item in list(getattr(state, "rag_evidence", []) or []):
        if not isinstance(item, dict):
            continue
        metadata = (
            item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        )
        for key in ("evidence_ref_id", "chunk_id", "document_id", "source_id", "id"):
            value = item.get(key) or metadata.get(key)
            if value:
                refs.append(str(value))

    for claim in list(getattr(governed_context, "allowed_claims", []) or []):
        if str(claim).startswith("evidence_ref:"):
            refs.append(str(claim).split(":", 1)[1])

    return list(dict.fromkeys(ref for ref in refs if str(ref or "").strip()))


def _collect_risk_claims(state: Any) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for owner in ("engineering", "challenge"):
        source = getattr(state, owner, None)
        for item in list(getattr(source, "risk_findings", []) or []) + list(
            getattr(source, "findings", []) or []
        ):
            if hasattr(item, "model_dump"):
                payload = item.model_dump(mode="json")
            elif isinstance(item, dict):
                payload = dict(item)
            else:
                continue
            if payload.get("claim_type") or payload.get("claim_id"):
                claims.append(payload)
    return claims
