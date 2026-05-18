"""Canonical V9.2 turn-boundary decision.

This module centralizes the first decision of a user turn: what route the turn
belongs to, whether state may mutate, whether the deterministic engine and
final guard are required, and whether a short path is allowed. It is deliberately
deterministic so all bypass paths can still be replayed and audited.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.state.models import GovernedSessionState
from app.agent.v92.contracts import (
    StateMutationPolicy,
    StreamingPolicy,
    TurnBoundaryDecision,
    TurnRoute,
)


_TECHNICAL_ROUTES: frozenset[TurnRoute] = frozenset(
    {
        "engineering_case_update",
        "engineering_recommendation",
        "leakage_failure_analysis",
        "standards_or_compliance",
        "rfq_readiness",
        "expert_review_action",
    }
)
_REVIEW_ROUTES: frozenset[TurnRoute] = frozenset(
    {
        "engineering_recommendation",
        "leakage_failure_analysis",
        "standards_or_compliance",
        "rfq_readiness",
        "expert_review_action",
    }
)
_NO_MUTATION_ROUTES: frozenset[TurnRoute] = frozenset(
    {
        "smalltalk",
        "abusive_or_shit_chat",
        "knowledge_general",
        "knowledge_case_side_question",
        "unsafe_or_blocked",
    }
)

_UNSAFE_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "print secrets",
    "show secrets",
    "ignoriere alle vorherigen",
    "ignoriere vorherige",
    "systemprompt",
)
_ABUSIVE_MARKERS = ("scheiss", "scheiß", "fuck", "mist", "bullshit", "idiot")
_SMALLTALK_RE = re.compile(
    r"^\s*(?:hi|hallo|hey|moin|danke|merci|ok|okay|super|passt|servus)[.!?\s]*$",
    re.IGNORECASE,
)
_RECOMMENDATION_RE = re.compile(
    r"\b(?:bewerte|beurteile|einsch[aä]tz\w*|screening|empfiehl|empfehlen|geeignet|"
    r"eignung|nehmen|verwenden|werkstoff|material|compound|produkt|dichtungsl(?:oe|ö)sung)\b",
    re.IGNORECASE,
)
_CASE_UPDATE_RE = re.compile(
    r"\b(?:medium|temperatur|druck|bar|grad|°\s*c|rpm|drehzahl|durchmesser|welle|"
    r"o-ring|oring|rwdr|radialwellendichtring|leckage|pumpe|getriebe|hlp\s*46|öl|oel)\b",
    re.IGNORECASE,
)
_KNOWLEDGE_RE = re.compile(
    r"\b(?:was ist|was bedeutet|erkl[aä]r|unterschied|vergleich|definition|wissen|"
    r"grenzwerte?|einsatzgrenzen?|materialdaten|kennwerte|limits?)\b",
    re.IGNORECASE,
)
_LEAKAGE_RE = re.compile(
    r"\b(?:leckage|leckt|schaden|ausfall|ausgefall\w*|root cause|ursache|abrieb|quellung|riss)\b",
    re.IGNORECASE,
)
_STANDARDS_RE = re.compile(
    r"\b(?:norm|standard|konform|compliance|zertifi|atex|fda|reach|ehedg|iso|din)\b",
    re.IGNORECASE,
)
_RFQ_RE = re.compile(r"\b(?:rfq|anfrage|angebot|dossier|hersteller|freigabeumfang)\b", re.IGNORECASE)
_REVIEW_RE = re.compile(
    r"\b(?:review|prüf\w*|pruef\w*|experte|expert|freigeben|ablehnen|approve|reject)\b",
    re.IGNORECASE,
)


def _as_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def _answer_trace_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    meta = dict((payload or {}).get("run_meta") or {})
    trace = meta.get("answer_trace")
    return dict(trace) if isinstance(trace, dict) else {}


def _has_case_state(state: GovernedSessionState | None) -> bool:
    if state is None:
        return False
    return bool(
        getattr(getattr(state, "asserted", None), "assertions", None)
        or getattr(getattr(state, "normalized", None), "parameters", None)
        or getattr(getattr(state, "seal_system", None), "status", "pending") != "pending"
    )


def _mutation_policy(route: TurnRoute) -> StateMutationPolicy:
    if route in _NO_MUTATION_ROUTES:
        return "none"
    if route == "expert_review_action":
        return "review_action"
    return "case_revision_allowed"


def _streaming_policy(route: TurnRoute) -> StreamingPolicy:
    if route == "unsafe_or_blocked":
        return "blocked"
    if route in _TECHNICAL_ROUTES:
        return "status_only_until_guarded_final"
    return "direct_stream_allowed"


def _route_from_hint(
    *,
    route_hint: str | None,
    policy_path: str | None,
    response_class: str | None,
    answer_mode: str | None,
) -> tuple[TurnRoute | None, str]:
    explicit_hint = _as_value(route_hint).casefold()
    if explicit_hint in {
        "smalltalk",
        "abusive_or_shit_chat",
        "knowledge_general",
        "knowledge_case_side_question",
        "engineering_case_update",
        "engineering_recommendation",
        "leakage_failure_analysis",
        "standards_or_compliance",
        "rfq_readiness",
        "expert_review_action",
        "unsafe_or_blocked",
    }:
        return explicit_hint, "hint_explicit_route"  # type: ignore[return-value]
    value = " ".join(
        item
        for item in (
            _as_value(route_hint),
            _as_value(policy_path),
            _as_value(response_class),
            _as_value(answer_mode),
        )
        if item
    ).casefold()
    if not value:
        return None, "no_hint"
    if "unsafe" in value or "blocked" in value or "guard" in value:
        return "unsafe_or_blocked", "hint_unsafe"
    if "rfq" in value or "inquiry_ready" in value:
        return "rfq_readiness", "hint_rfq"
    if "active_case_process" in value:
        return "knowledge_case_side_question", "hint_active_case_process"
    if "active_case_side" in value or "side" in value:
        return "knowledge_case_side_question", "hint_active_case_side"
    if "knowledge" in value or "exploration" in value:
        return "knowledge_general", "hint_knowledge"
    if "smalltalk" in value or "conversation" in value or "fast" in value:
        return "smalltalk", "hint_conversation"
    if "review" in value:
        return "expert_review_action", "hint_review"
    if response_class in {"technical_preselection", "candidate_shortlist"}:
        return "engineering_recommendation", "hint_response_class"
    if response_class in {"structured_clarification", "governed_state_update"}:
        return "engineering_case_update", "hint_response_class"
    return None, "hint_unmapped"


class TurnBoundaryOrchestrator:
    version = "turn_boundary_orchestrator_v9_2.1"

    def resolve(
        self,
        *,
        user_message: str,
        session_id: str,
        state: GovernedSessionState | None = None,
        payload: dict[str, Any] | None = None,
        route_hint: str | None = None,
        policy_path: str | None = None,
        response_class: str | None = None,
        answer_mode: str | None = None,
        runtime_mode: str | None = None,
        pre_gate_classification: str | None = None,
    ) -> TurnBoundaryDecision:
        text = str(user_message or "")
        lowered = text.casefold()
        answer_trace = _answer_trace_from_payload(payload)
        trace_answer_mode = str(answer_trace.get("answer_mode") or "")
        pre_gate_value = _as_value(pre_gate_classification).upper()
        route, reason = _route_from_hint(
            route_hint=route_hint,
            policy_path=policy_path,
            response_class=response_class,
            answer_mode=answer_mode or trace_answer_mode,
        )

        if pre_gate_value == "BLOCKED":
            route, reason = "unsafe_or_blocked", "pre_gate_blocked"
        elif any(marker in lowered for marker in _UNSAFE_MARKERS):
            route, reason = "unsafe_or_blocked", "unsafe_marker"
        elif route is None and _LEAKAGE_RE.search(text):
            route, reason = "leakage_failure_analysis", "message_leakage"
        elif route is None and _STANDARDS_RE.search(text):
            route, reason = "standards_or_compliance", "message_standards"
        elif route is None and _RFQ_RE.search(text):
            route, reason = "rfq_readiness", "message_rfq"
        elif route is None and _REVIEW_RE.search(text):
            route, reason = "expert_review_action", "message_review"
        elif route is None and _RECOMMENDATION_RE.search(text):
            route, reason = "engineering_recommendation", "message_recommendation"
        elif route is None and _KNOWLEDGE_RE.search(text) and _CASE_UPDATE_RE.search(text):
            route, reason = "engineering_case_update", "message_knowledge_with_case_markers"
        elif route is None and _KNOWLEDGE_RE.search(text):
            route = "knowledge_case_side_question" if _has_case_state(state) else "knowledge_general"
            reason = "message_knowledge_with_case" if _has_case_state(state) else "message_knowledge"
        elif route is None and pre_gate_value in {"KNOWLEDGE_QUERY", "DEEP_DIVE"}:
            route = "knowledge_case_side_question" if _has_case_state(state) else "knowledge_general"
            reason = "pre_gate_knowledge_with_case" if _has_case_state(state) else "pre_gate_knowledge"
        elif route is None and _SMALLTALK_RE.search(text):
            route, reason = "smalltalk", "message_smalltalk"
        elif route is None and any(marker in lowered for marker in _ABUSIVE_MARKERS):
            route, reason = "abusive_or_shit_chat", "message_abusive"
        elif route is None and _CASE_UPDATE_RE.search(text):
            route, reason = "engineering_case_update", "message_case_update"
        elif route is None:
            route = "knowledge_case_side_question" if _has_case_state(state) else "smalltalk"
            reason = "fallback_case_side" if _has_case_state(state) else "fallback_smalltalk"

        if (
            route in {"engineering_case_update", "knowledge_case_side_question", "knowledge_general"}
            and _RECOMMENDATION_RE.search(text)
            and _CASE_UPDATE_RE.search(text)
        ):
            route, reason = "engineering_recommendation", "message_case_specific_recommendation"

        mutation_policy = _mutation_policy(route)
        is_technical = route in _TECHNICAL_ROUTES
        unsafe = route == "unsafe_or_blocked"
        graph_required = route in {
            "engineering_case_update",
            "engineering_recommendation",
            "leakage_failure_analysis",
            "standards_or_compliance",
        }
        short_path_allowed = not graph_required
        return TurnBoundaryDecision(
            route=route,
            intent=route,
            reason=reason,
            source=self.version,
            confidence=0.95 if reason.startswith(("hint_", "unsafe_")) else 0.8,
            state_mutation_policy=mutation_policy,
            requires_engine=is_technical,
            requires_evidence=is_technical or route == "knowledge_case_side_question",
            requires_adversarial_review=route in _REVIEW_ROUTES,
            requires_final_guard=True,
            streaming_policy=_streaming_policy(route),
            graph_required=graph_required,
            short_path_allowed=short_path_allowed,
            unsafe_instruction_blocked=unsafe,
            case_state_may_mutate=mutation_policy in {"case_revision_allowed", "review_action"},
            trace={
                "session_id": session_id,
                "runtime_mode": _as_value(runtime_mode),
                "pre_gate_classification": _as_value(pre_gate_classification),
                "route_hint": _as_value(route_hint),
                "policy_path": _as_value(policy_path),
                "response_class": _as_value(response_class),
                "answer_mode": _as_value(answer_mode or trace_answer_mode),
                "has_case_state": _has_case_state(state),
            },
        )


def resolve_turn_boundary(**kwargs: Any) -> TurnBoundaryDecision:
    return TurnBoundaryOrchestrator().resolve(**kwargs)


__all__ = ["TurnBoundaryOrchestrator", "resolve_turn_boundary"]
