# backend/app/langgraph_v2/nodes/nodes_supervisor.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.langgraph_v2.state import (
    Budget,
    CandidateItem,
    DecisionEntry,
    FactItem,
    QuestionItem,
    SealAIState,
    Source,
    WorkingMemory,
)
from app.langgraph_v2.utils.messages import latest_user_text

logger = logging.getLogger(__name__)

YES_KEYWORDS: List[str] = [
    "ja",
    "gerne",
    "bitte empfehle",
    "mach eine empfehlung",
    "go",
    "ok, mach weiter",
    "ja bitte",
    "leg los",
]
NO_KEYWORDS: List[str] = [
    "nein",
    "erst später",
    "nicht jetzt",
    "später",
    "noch nicht",
    "noch nicht bereit",
]

_REQUIRED_PARAMS_FOR_READY: List[str] = [
    "medium",
    "pressure_bar",
    "temperature_C",
    "shaft_diameter",
    "speed_rpm",
]

_READY_THRESHOLD = 0.8

ACTION_ASK_USER = "ASK_USER"
ACTION_RUN_PANEL_CALC = "RUN_PANEL_CALC"
ACTION_RUN_PANEL_MATERIAL = "RUN_PANEL_MATERIAL"
ACTION_RUN_PANEL_NORMS_RAG = "RUN_PANEL_NORMS_RAG"
ACTION_RUN_KNOWLEDGE = "RUN_KNOWLEDGE"
ACTION_RUN_COMPARISON = "RUN_COMPARISON"
ACTION_RUN_TROUBLESHOOTING = "RUN_TROUBLESHOOTING"
ACTION_CONFIRM_RECOMMENDATION = "RUN_CONFIRM"
ACTION_REQUIRE_CONFIRM = "REQUIRE_CONFIRM"
ACTION_FINALIZE = "FINALIZE"

MAX_SUPERVISOR_ROUNDS = 3

_ACTION_COSTS: Dict[str, int] = {
    ACTION_ASK_USER: 1,
    ACTION_RUN_PANEL_CALC: 1,
    ACTION_RUN_PANEL_MATERIAL: 2,
    ACTION_RUN_PANEL_NORMS_RAG: 3,
    ACTION_RUN_KNOWLEDGE: 1,
    ACTION_RUN_COMPARISON: 1,
    ACTION_RUN_TROUBLESHOOTING: 2,
    ACTION_CONFIRM_RECOMMENDATION: 1,
    ACTION_REQUIRE_CONFIRM: 0,
    ACTION_FINALIZE: 0,
}

_PARAM_LABELS: Dict[str, str] = {
    "medium": "Medium",
    "pressure_bar": "Druck (bar)",
    "temperature_C": "Temperatur (°C)",
    "shaft_diameter": "Wellen-Ø (mm)",
    "speed_rpm": "Drehzahl (rpm)",
}
_RFQ_PART_RE = re.compile(r"\b(rfq|export|part[\s-]?number|part[\s-]?no|teilenummer|pn)\b", re.IGNORECASE)


def _compute_coverage(required: List[str], missing: List[str]) -> float:
    if not required:
        return 1.0
    score = (len(required) - len(missing)) / len(required)
    return max(0.0, min(1.0, score))


def _infer_missing_params(state: SealAIState, required: List[str]) -> List[str]:
    params = state.parameters
    missing: List[str] = []
    for key in required:
        value = getattr(params, key, None)
        if value is None or value == "":
            missing.append(key)
    return missing


def _intent_goal_value(state: SealAIState) -> str:
    intent = getattr(state, "intent", None)
    if isinstance(intent, dict):
        return str(intent.get("goal") or "").strip().lower()
    return str(getattr(intent, "goal", "") or "").strip().lower()


def _is_info_query(state: SealAIState, user_text: str) -> bool:
    goal = _intent_goal_value(state)
    if goal in {"explanation_or_comparison", "generic_qa", "knowledge_only"}:
        return True
    text = (user_text or "").strip().lower()
    if not text:
        return False
    markers = ("information", "informationen", "erkläre", "erklaere", "was ist", "vergleich", "stichpunkt")
    return any(marker in text for marker in markers)


def _guardrail_escalation_level(state: SealAIState) -> str:
    level = str(getattr(state, "guardrail_escalation_level", "none") or "none").strip().lower()
    if level in {"none", "ask_user", "human_required", "refuse"}:
        return level
    _, _, status = str(getattr(state, "guardrail_escalation_reason", "") or "").partition(":")
    status = status.strip().lower()
    if status in {"ask_user", "human_required", "refuse"}:
        return status
    return "none"


def _assumption_hash_unconfirmed(state: SealAIState) -> bool:
    current = getattr(state, "assumption_lock_hash", None)
    confirmed = getattr(state, "assumption_lock_hash_confirmed", None)
    return bool(current) and str(current) != str(confirmed or "")


def _rfq_or_part_number_requested(user_text: str) -> bool:
    return bool(_RFQ_PART_RE.search(user_text or ""))


def _conversation_track(state: SealAIState, *, is_info_query: bool, user_text: str) -> str:
    if bool(getattr(state, "failure_mode_active", False)):
        return "diagnostic"
    goal = _intent_goal_value(state)
    if goal == "troubleshooting_leakage":
        return "diagnostic"
    if is_info_query or _is_knowledge_intent(state):
        return "knowledge"
    return "design"


def _is_high_design_escalation(state: SealAIState, *, conversation_track: str) -> bool:
    if str(conversation_track or "").strip().lower() != "design":
        return False
    level = _guardrail_escalation_level(state)
    if level in {"human_required", "refuse"}:
        return True
    flags = dict(getattr(state, "flags", {}) or {})
    risk_level = str(flags.get("risk_level") or "").strip().lower()
    if risk_level in {"high", "critical"}:
        return True
    heatmap = dict(getattr(state, "risk_heatmap", {}) or {})
    return any(str(v or "").strip().lower() in {"high", "critical"} for v in heatmap.values())


def _cap_questions(questions: List[str], *, max_questions: int) -> List[str]:
    out: List[str] = []
    for item in list(questions or []):
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= max_questions:
            break
    return out


def _build_supervisor_hard_stop_patch(state: SealAIState, user_text: str) -> Dict[str, Any] | None:
    escalation_level = _guardrail_escalation_level(state)
    failure_missing = bool(getattr(state, "failure_mode_active", False)) and bool(getattr(state, "failure_evidence_missing", False))
    hash_unconfirmed = _assumption_hash_unconfirmed(state)
    rfq_not_ready = (not bool(getattr(state, "rfq_ready", False))) and _rfq_or_part_number_requested(user_text)

    if not any([escalation_level in {"ask_user", "human_required", "refuse"}, failure_missing, hash_unconfirmed, rfq_not_ready]):
        return None

    request = state.ask_missing_request
    escalation_reason = str(getattr(state, "guardrail_escalation_reason", "") or "")
    track = _conversation_track(state, is_info_query=_is_info_query(state, user_text), user_text=user_text)
    guardrail_questions = list(getattr(state, "guardrail_questions", []) or [])

    if failure_missing:
        diag_questions = _cap_questions(
            [
                "Upload photo of failed seal + damage area.",
                "Describe damage: cuts / blisters / flat set / nibbling / spiral twist.",
                "How long until failure + cycles + depressurization events?",
            ],
            max_questions=2,
        )
        request = request or AskMissingRequest(
            missing_fields=["failure_photo_or_damage_evidence"],
            question="Kurzdiagnose zuerst: Bitte zuerst Schadensnachweise (Foto/Schadensbild/Zyklen) liefern.",
            reason="failure_evidence_required",
            questions=diag_questions,
        )
        escalation_reason = "failure_evidence_required"
    elif escalation_level == "refuse":
        request = request or AskMissingRequest(
            missing_fields=["human_review", "compliance_signoff"],
            question=(
                "Ich kann keine Compliance-/Sign-off- oder sicherheitskritische Endfreigabe erteilen. "
                "Bitte Human-Engineer-Review durchführen und belastbare Nachweise bereitstellen."
            ),
            reason=escalation_reason or "compliance_signoff:refuse",
            questions=[
                "Provide normative scope and required compliance basis for manual sign-off.",
                "Provide safety-critical constraints and acceptance criteria.",
                "Escalate to a responsible human sealing engineer.",
            ],
        )
        escalation_reason = escalation_reason or "compliance_signoff:refuse"
    elif escalation_level == "human_required":
        questions = _cap_questions(
            guardrail_questions or ["Bitte risikorelevante Randbedingungen und fehlende Belastungsdaten liefern."],
            max_questions=3,
        )
        request = request or AskMissingRequest(
            missing_fields=["human_review", "guardrail"],
            question="Senior Review erforderlich: Human engineer required. Bitte die sicherheitskritischen Luecken klaeren.",
            reason=escalation_reason or "guardrail:human_required",
            questions=questions,
        )
        escalation_reason = escalation_reason or "guardrail:human_required"
    elif hash_unconfirmed:
        request = request or AskMissingRequest(
            missing_fields=["assumption_lock_confirmation"],
            question="Assumption lock ist nicht bestaetigt oder hat sich geaendert. Bitte Annahmen erneut bestaetigen.",
            reason="assumption_lock_required",
            questions=["Bitte bestaetige die offenen Annahmen explizit (z. B. `confirm #1,#2`)."],
        )
    elif rfq_not_ready:
        request = request or AskMissingRequest(
            missing_fields=["rfq_gate"],
            question="RFQ/Part-number Freigabe ist noch blockiert, weil rfq_ready=False.",
            reason="rfq_gate_not_ready",
            questions=["Bitte erst Assumption Lock und Guardrail-Freigaben abschliessen."],
        )
    else:
        questions = _cap_questions(guardrail_questions, max_questions=2)
        request = request or AskMissingRequest(
            missing_fields=["guardrail"],
            question="Kurzcheck vor dem naechsten Schritt: Bitte offene Guardrail-Rueckfragen beantworten.",
            reason=escalation_reason or "guardrail:ask_user",
            questions=questions,
        )

    return {
        "ask_missing_request": request,
        "ask_missing_scope": "technical",
        "awaiting_user_input": True,
        "guardrail_escalation_reason": escalation_reason or getattr(state, "guardrail_escalation_reason", None),
        "guardrail_escalation_level": escalation_level if escalation_level in {"ask_user", "human_required", "refuse"} else getattr(state, "guardrail_escalation_level", "none"),
        "rfq_ready": False,
        "conversation_track": track,
        "next_action": ACTION_ASK_USER,
        "last_node": "supervisor_policy_node",
        "phase": PHASE.VALIDATION,
    }


def supervisor_logic_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("supervisor_logic_node", state)
    _maybe_set_recommendation_go(state)
    wm = state.working_memory or WorkingMemory()

    missing = _infer_missing_params(state, _REQUIRED_PARAMS_FOR_READY)
    coverage_score = _compute_coverage(_REQUIRED_PARAMS_FOR_READY, missing)
    recommendation_ready = coverage_score >= _READY_THRESHOLD
    return {
        "working_memory": wm,
        # WICHTIG: Phase auf einen gültigen PhaseLiteral-Wert setzen
        "phase": PHASE.INTENT,
        "last_node": "supervisor_logic_node",
        # Deterministic readiness/coverage for supervisor gating.
        "missing_params": missing,
        "coverage_gaps": missing,
        "coverage_score": coverage_score,
        "recommendation_ready": recommendation_ready,
    }


def _coerce_questions(items: List[QuestionItem | Dict[str, Any]] | None) -> List[QuestionItem]:
    questions: List[QuestionItem] = []
    for item in items or []:
        if isinstance(item, QuestionItem):
            questions.append(item)
            continue
        if isinstance(item, dict):
            try:
                questions.append(QuestionItem.model_validate(item))
            except ValidationError as exc:
                logger.warning("skip_invalid_open_question", extra={"error": str(exc), "item_keys": list(item.keys())})
    return questions


def _derive_open_questions(state: SealAIState) -> List[QuestionItem]:
    seen: set[str] = set()
    questions: List[QuestionItem] = []
    for key in (state.missing_params or []):
        if not key or key in seen:
            continue
        seen.add(key)
        label = _PARAM_LABELS.get(key, key.replace("_", " "))
        questions.append(
            QuestionItem(
                id=key,
                question=f"Bitte ergänze: {label}.",
                reason="Benötigt für die Auslegung.",
                priority="high",
                status="open",
                source="missing_params",
            )
        )
    for key in (state.discovery_missing or []):
        if not key or key in seen:
            continue
        seen.add(key)
        label = _PARAM_LABELS.get(key, key.replace("_", " "))
        questions.append(
            QuestionItem(
                id=key,
                question=f"Kannst du Details zu {label} ergänzen?",
                reason="Fehlt in der Discovery.",
                priority="medium",
                status="open",
                source="discovery_missing",
            )
        )
    return questions


def _open_questions_summary(questions: List[QuestionItem]) -> str:
    total = len(questions)
    high = sum(1 for q in questions if q.priority == "high" and q.status == "open")
    answered = sum(1 for q in questions if q.status == "answered")
    return f"open={total} high={high} answered={answered}"


def _detect_candidate_contradictions(candidates: List[CandidateItem]) -> List[str]:
    conflicts: List[str] = []
    by_kind: Dict[str, Dict[str, int]] = {}
    for candidate in candidates:
        if candidate.confidence < 0.6:
            continue
        by_kind.setdefault(candidate.kind, {})
        by_kind[candidate.kind][candidate.value] = by_kind[candidate.kind].get(candidate.value, 0) + 1
    for kind, values in by_kind.items():
        if len(values) > 1:
            conflicts.append(f"{kind} has {len(values)} competing values")
    return conflicts


def _coerce_candidates(items: List[CandidateItem | Dict[str, Any]] | None) -> List[CandidateItem]:
    candidates: List[CandidateItem] = []
    for item in items or []:
        if isinstance(item, CandidateItem):
            candidates.append(item)
            continue
        if isinstance(item, dict):
            try:
                candidates.append(CandidateItem.model_validate(item))
            except ValidationError as exc:
                logger.warning(
                    "skip_invalid_candidate",
                    extra={"error": str(exc), "item_keys": list(item.keys())},
                )
    return candidates


def supervisor_policy_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("supervisor_policy_node", state)
    user_text = latest_user_text(state.get("messages")) or ""
    hard_stop_patch = _build_supervisor_hard_stop_patch(state, user_text)
    if hard_stop_patch is not None:
        return hard_stop_patch
    _maybe_set_recommendation_go(state)
    is_info_query = _is_info_query(state, user_text)
    track = _conversation_track(state, is_info_query=is_info_query, user_text=user_text)
    if is_info_query:
        missing: List[str] = []
        coverage_score = 1.0
        recommendation_ready = True
    else:
        missing = _infer_missing_params(state, _REQUIRED_PARAMS_FOR_READY)
        coverage_score = _compute_coverage(_REQUIRED_PARAMS_FOR_READY, missing)
        recommendation_ready = coverage_score >= _READY_THRESHOLD
    questions = _coerce_questions(state.open_questions)
    derived = False
    if not questions:
        questions = _derive_open_questions(state)
        derived = True

    budget = state.budget if isinstance(state.budget, Budget) else Budget.model_validate(state.budget or {})
    round_index = int(state.round_index or 0)
    confidence = float(state.confidence or 0.0)
    awaiting = bool(getattr(state, "awaiting_user_input", False))

    candidates = _coerce_candidates(state.candidates)
    contradictions = _detect_candidate_contradictions(candidates)

    high_open = [q for q in questions if q.priority == "high" and q.status == "open"]

    reason = "default_finalize"
    action = ACTION_FINALIZE
    goal = _intent_goal_value(state) or "design_recommendation"

    needs_sources = _needs_sources(state)
    is_knowledge = _is_knowledge_intent(state)
    is_norms = _is_norms_knowledge(state)


    # --- text heuristics used across branches (material questions vs calc questions)
    _t = (user_text or "").lower()
    _is_material_q = any(k in _t for k in (
        "ptfe","fkm","nbr","epdm","kyrolon","medienbeständ","medienbestaend","temperatur",
        "einsatzgrenz","einsatzgrenze","chemisch","beständig","bestaendig","dichtung","werkstoff","material"
    ))
    _looks_like_calc = any(k in _t for k in (
        "rechn","berechn","umfang","drehzahl","rpm","geschwindigkeit","sicherheitsfaktor","druck","bar"
    ))
    if goal in ("smalltalk", "out_of_scope"):
        reason = "non_technical_goal"
        action = ACTION_FINALIZE
    elif goal == "troubleshooting_leakage":
        reason = "troubleshooting_flow"
        action = ACTION_RUN_TROUBLESHOOTING
    elif goal == "design_recommendation" and is_knowledge:
        missing_calc = state.calc_results is None or not bool(getattr(state, "calc_results_ok", False))
        material_choice = state.material_choice or {}
        missing_material = not bool(material_choice.get("material"))
        if missing_calc:
            reason = "missing_calc_facts"

            action = ACTION_RUN_PANEL_CALC
        # If the user asks material limits (e.g. PTFE), do NOT route to calc.
        _t = (user_text or "").lower()
        _is_material_q = any(k in _t for k in (
            "ptfe","fkm","nbr","epdm","kyrolon","medienbeständ","medienbestaend","temperatur",
            "einsatzgrenz","einsatzgrenze","chemisch","beständig","bestaendig","dichtung","werkstoff","material"
        ))
        _looks_like_calc = any(k in _t for k in (
            "rechn","berechn","umfang","drehzahl","rpm","geschwindigkeit","sicherheitsfaktor","druck","bar"
        ))
        if _is_material_q and not _looks_like_calc:
            action = ACTION_RUN_KNOWLEDGE
            reason = "material_question_not_calc"
        elif missing_material:
            reason = "missing_material_decision"
            action = ACTION_RUN_PANEL_MATERIAL
        elif is_norms:
            reason = "rag_norms"
            action = ACTION_RUN_PANEL_NORMS_RAG
        else:
            reason = "knowledge_flow"
            action = ACTION_RUN_KNOWLEDGE
    elif is_knowledge:
        if is_norms:
            reason = "rag_norms"
            action = ACTION_RUN_PANEL_NORMS_RAG
        else:
            reason = "knowledge_flow"
            action = ACTION_RUN_KNOWLEDGE
    elif goal == "explanation_or_comparison":
        comparison_notes = getattr(state.working_memory, "comparison_notes", {}) if state.working_memory else {}
        has_comparison = bool(comparison_notes.get("comparison_text"))
        has_rag = bool(comparison_notes.get("rag_context"))
        material_knowledge_query = (
            (is_knowledge and not is_norms)
            or (
                _is_material_q
                and not _looks_like_calc
            )
            or (
                "vergleiche" in _t
                and any(k in _t for k in ("ptfe", "fkm", "nbr", "epdm", "werkstoff", "material"))
            )
        )
        if material_knowledge_query:
            reason = "knowledge_flow"
            action = ACTION_RUN_KNOWLEDGE
        elif needs_sources and not has_rag:
            reason = "rag_sources_required"
            action = ACTION_RUN_PANEL_NORMS_RAG
        elif not has_comparison:
            reason = "comparison_missing"
            action = ACTION_RUN_COMPARISON
        else:
            reason = "comparison_ready"
            action = ACTION_FINALIZE
    elif needs_sources:
        reason = "rag_sources_required"
        action = ACTION_RUN_PANEL_NORMS_RAG
    elif recommendation_ready and not state.recommendation_go:
        reason = "await_recommendation_go"
        action = ACTION_CONFIRM_RECOMMENDATION
    elif budget.remaining <= 0:
        reason = "budget_exhausted"
        action = ACTION_FINALIZE
    elif round_index >= MAX_SUPERVISOR_ROUNDS:
        reason = "max_rounds_reached"
        action = ACTION_FINALIZE
    elif confidence >= 0.8 and not high_open:
        reason = "confidence_high"
        action = ACTION_FINALIZE
    elif high_open and not awaiting:
        reason = "missing_high_priority_inputs"

        # Heuristic: route common material/knowledge questions to knowledge instead of ASK_USER
        try:
            _txt = (user_text or "").strip().lower()
        except Exception:
            _txt = ""
        if _txt:
            _kw = (
                "ptfe", "fkm", "nbr", "epdm", "kyrolon", "werkstoff", "material",
                "medienbeständ", "temperatur", "einsatzgrenz", "chemisch",
                "säure", "saeure", "laugen", "lösung", "loesung", "dichtung"
            )
            if any(k in _txt for k in _kw):
                action = ACTION_RUN_KNOWLEDGE
                reason = "heuristic_material_knowledge"
        if action != ACTION_RUN_KNOWLEDGE:
            action = ACTION_ASK_USER
    else:
        missing_calc = state.calc_results is None or not bool(getattr(state, "calc_results_ok", False))
        material_choice = state.material_choice or {}
        missing_material = not bool(material_choice.get("material"))
        if missing_calc:
            reason = "missing_calc_facts"
            action = ACTION_RUN_PANEL_CALC
            if _is_material_q and not _looks_like_calc:
                reason = "material_question_not_calc"
                action = ACTION_RUN_KNOWLEDGE
        elif missing_material:
            reason = "missing_material_decision"
            action = ACTION_RUN_PANEL_MATERIAL
        elif contradictions or needs_sources:
            reason = "resolve_contradictions" if contradictions else "rag_sources_required"
            action = ACTION_RUN_PANEL_NORMS_RAG
        else:
            reason = "no_action_required"
            action = ACTION_FINALIZE

    requires_confirm = (
        action == ACTION_RUN_PANEL_NORMS_RAG
        and _is_high_design_escalation(state, conversation_track=track)
        and action not in (state.confirmed_actions or [])
        and not state.awaiting_user_confirmation
    )
    if requires_confirm:
        pending_action = action
        action = ACTION_REQUIRE_CONFIRM
    else:
        pending_action = state.pending_action

    if state.awaiting_user_confirmation and pending_action:
        action = ACTION_REQUIRE_CONFIRM

    cost = _ACTION_COSTS.get(action, 0)
    updated_budget = budget.model_copy()
    if cost > 0:
        updated_budget = updated_budget.model_copy(
            update={
                "remaining": max(0, updated_budget.remaining - cost),
                "spent": updated_budget.spent + cost,
            }
        )

    new_round = round_index + 1
    decision_entry = DecisionEntry(
        round=new_round,
        action=action,
        reason=reason,
        cost=cost,
        confidence=confidence,
        open_questions_summary=_open_questions_summary(questions),
    )

    retrieval_meta: Dict[str, Any] | None = None
    if (
        goal == "explanation_or_comparison"
        and action != ACTION_RUN_PANEL_NORMS_RAG
        and not getattr(state, "requires_rag", False)
    ):
        tenant_id = getattr(state, "tenant_id", None) or getattr(state, "user_id", None)
        retrieval_meta = {
            "skipped": True,
            "reason": "requires_rag_false",
            "retrieval_attempted": False,
            "tenant_id": tenant_id,
        }


    # Final guard: material questions should not be forced into calc

    if action == ACTION_RUN_PANEL_CALC:

        _t = (user_text or "").lower()

        _is_material_q = any(k in _t for k in (

            "ptfe","fkm","nbr","epdm","kyrolon","medienbeständ","medienbestaend","temperatur",

            "einsatzgrenz","einsatzgrenze","chemisch","beständig","bestaendig","dichtung","werkstoff","material"

        ))

        _looks_like_calc = any(k in _t for k in (

            "rechn","berechn","umfang","drehzahl","rpm","geschwindigkeit","sicherheitsfaktor","druck","bar"

        ))

        if _is_material_q and not _looks_like_calc:

            action = ACTION_RUN_KNOWLEDGE

            reason = "material_question_not_calc"


    patch: Dict[str, Any] = {
        "next_action": action,
        "next_action_reason": reason,
        "pending_action": pending_action,
        "decision_log": [*(state.decision_log or []), decision_entry],
        "round_index": new_round,
        "budget": updated_budget,
        "phase": PHASE.SUPERVISOR,
        "last_node": "supervisor_policy_node",
        "missing_params": missing,
        "coverage_gaps": missing,
        "coverage_score": coverage_score,
        "recommendation_ready": recommendation_ready,
        "conversation_track": track,
    }
    if is_info_query:
        patch.update(
            {
                "missing_params": [],
                "coverage_gaps": [],
                "awaiting_user_input": False,
            }
        )
    if retrieval_meta:
        patch["retrieval_meta"] = retrieval_meta
    if derived:
        patch["open_questions"] = questions
    return patch


def _is_knowledge_intent(state: SealAIState) -> bool:
    intent = state.intent
    if intent:
        key = str(getattr(intent, "key", "") or "")
        if key in {
            "knowledge_material",
            "knowledge_lifetime",
            "knowledge_norms",
            "generic_sealing_qa",
        }:
            return True
        if getattr(intent, "knowledge_type", None) in {"material", "lifetime", "norms"}:
            return True
    if getattr(state, "knowledge_type", None) in {"material", "lifetime", "norms"}:
        return True
    return False


def _is_norms_knowledge(state: SealAIState) -> bool:
    intent = state.intent
    if intent:
        key = str(getattr(intent, "key", "") or "")
        if key == "knowledge_norms":
            return True
        if getattr(intent, "knowledge_type", None) == "norms":
            return True
    return getattr(state, "knowledge_type", None) == "norms"


def _needs_sources(state: SealAIState) -> bool:
    intent = state.intent
    return bool(
        getattr(state, "needs_sources", False)
        or getattr(state, "needs_sources", False)
        or getattr(state, "requires_rag", False)
        or (bool(getattr(intent, "needs_sources", False)) if intent else False)
        or (bool(getattr(intent, "needs_sources", False)) if intent else False)
    )


def _merge_fact(existing: FactItem | None, update: FactItem) -> FactItem:
    if not existing:
        return update
    merged = existing.model_copy()
    if update.value is not None:
        merged = merged.model_copy(update={"value": update.value})
    merged_refs = list(dict.fromkeys([*existing.evidence_refs, *update.evidence_refs]))
    merged = merged.model_copy(
        update={
            "source": update.source or existing.source,
            "confidence": max(existing.confidence, update.confidence),
            "evidence_refs": merged_refs,
        }
    )
    return merged


def _merge_candidate(existing: CandidateItem | None, update: CandidateItem) -> CandidateItem:
    if not existing:
        return update
    merged_refs = list(dict.fromkeys([*existing.evidence_refs, *update.evidence_refs]))
    return existing.model_copy(
        update={
            "rationale": update.rationale or existing.rationale,
            "confidence": max(existing.confidence, update.confidence),
            "evidence_refs": merged_refs,
        }
    )


def _compute_confidence(
    coverage_score: float,
    evidence_bonus: float,
    contradiction_penalty: float,
) -> float:
    coverage_pct = coverage_score * 100.0 if coverage_score <= 1.0 else coverage_score
    raw = 0.4 * (coverage_pct / 100.0) + 0.3 * evidence_bonus + 0.3 * (1.0 - contradiction_penalty)
    return max(0.0, min(1.0, raw))


def aggregator_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("aggregator_node", state)
    facts: Dict[str, FactItem] = {}
    for key, value in (state.facts or {}).items():
        if isinstance(value, FactItem):
            facts[key] = value
        elif isinstance(value, dict):
            try:
                facts[key] = FactItem.model_validate(value)
            except ValidationError as exc:
                logger.warning(
                    "skip_invalid_fact",
                    extra={"error": str(exc), "fact_key": key, "item_keys": list(value.keys())},
                )

    candidates: Dict[Tuple[str, str], CandidateItem] = {}
    for candidate in _coerce_candidates(state.candidates):
        candidates[(candidate.kind, candidate.value)] = candidate

    calc = state.calc_results
    if calc:
        if calc.safety_factor is not None:
            key = "calc.safety_factor"
            facts[key] = _merge_fact(
                facts.get(key),
                FactItem(value=calc.safety_factor, source="panel_calculator", confidence=0.6),
            )
        if calc.temperature_margin is not None:
            key = "calc.temperature_margin"
            facts[key] = _merge_fact(
                facts.get(key),
                FactItem(value=calc.temperature_margin, source="panel_calculator", confidence=0.5),
            )
        if calc.pressure_margin is not None:
            key = "calc.pressure_margin"
            facts[key] = _merge_fact(
                facts.get(key),
                FactItem(value=calc.pressure_margin, source="panel_calculator", confidence=0.5),
            )

    material_choice = state.material_choice or {}
    material = material_choice.get("material")
    if material:
        key = ("material", str(material))
        candidates[key] = _merge_candidate(
            candidates.get(key),
            CandidateItem(
                kind="material",
                value=str(material),
                rationale=str(material_choice.get("details") or ""),
                confidence=0.6,
            ),
        )

    profile_choice = state.profile_choice or {}
    profile = profile_choice.get("profile")
    if profile:
        key = ("profile", str(profile))
        candidates[key] = _merge_candidate(
            candidates.get(key),
            CandidateItem(
                kind="profile",
                value=str(profile),
                rationale=str(profile_choice.get("rationale") or ""),
                confidence=0.55,
            ),
        )

    sources: List[Source] = []
    for item in (state.sources or []):
        if isinstance(item, Source):
            sources.append(item)
        elif isinstance(item, dict):
            sources.append(Source.model_validate(item))
    source_ids = [s.source for s in sources if s.source]

    questions = _coerce_questions(state.open_questions)
    updated_questions: List[QuestionItem] = []
    for question in questions:
        if question.status != "answered":
            param_value = None
            if question.id:
                param_value = getattr(state.parameters, question.id, None)
            has_fact = bool(question.id and question.id in facts)
            if param_value not in (None, "") or has_fact:
                question = question.model_copy(update={"status": "answered"})
        updated_questions.append(question)

    contradictions = _detect_candidate_contradictions(list(candidates.values()))
    contradiction_penalty = min(1.0, 0.2 * len(contradictions))
    evidence_bonus = min(1.0, 0.1 * len(source_ids) + 0.05 * len([f for f in facts.values() if f.evidence_refs]))
    coverage_score = float(getattr(state, "coverage_score", 0.0) or 0.0)
    confidence = _compute_confidence(coverage_score, evidence_bonus, contradiction_penalty)

    return {
        "facts": facts,
        "candidates": list(candidates.values()),
        "open_questions": updated_questions,
        "confidence": confidence,
        "phase": PHASE.AGGREGATION,
        "last_node": "aggregator_node",
    }


def panel_calculator_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("panel_calculator_node", state)
    from app.langgraph_v2.nodes.nodes_flows import calculator_node

    patch = calculator_node(state, *_args, **_kwargs)
    wm = patch.get("working_memory") or state.working_memory or WorkingMemory()
    panel_payload = {
        "calc_results": (patch.get("calc_results") or state.calc_results).model_dump(exclude_none=True)
        if (patch.get("calc_results") or state.calc_results)
        else {},
    }
    wm = wm.model_copy(update={"panel_calculator": panel_payload})
    patch.update(
        {
            "working_memory": wm,
            "phase": PHASE.PANEL,
            "last_node": "panel_calculator_node",
        }
    )
    return patch


def panel_material_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("panel_material_node", state)
    from app.langgraph_v2.nodes.nodes_flows import material_agent_node

    patch = material_agent_node(state, *_args, **_kwargs)
    wm = patch.get("working_memory") or state.working_memory or WorkingMemory()
    panel_payload = {
        "material_choice": patch.get("material_choice") or state.material_choice,
        "material_candidates": (patch.get("working_memory") or state.working_memory).material_candidates
        if (patch.get("working_memory") or state.working_memory)
        else [],
    }
    wm = wm.model_copy(update={"panel_material": panel_payload})
    patch.update(
        {
            "working_memory": wm,
            "phase": PHASE.PANEL,
            "last_node": "panel_material_node",
        }
    )
    return patch


def panel_norms_rag_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("panel_norms_rag_node", state)
    from app.langgraph_v2.nodes.nodes_flows import rag_support_node

    return rag_support_node(state, *_args, **_kwargs)


def supervisor_route(state: SealAIState) -> str:
    goal = getattr(state.intent, "goal", "smalltalk") if state.intent else "smalltalk"
    ready = bool(getattr(state, "recommendation_ready", False))
    go = bool(getattr(state, "recommendation_go", False))
    if goal == "design_recommendation":
        if not ready:
            return "intermediate"
        if go:
            return "design_flow"
        return "confirm"
    if goal == "explanation_or_comparison":
        return "comparison"
    if goal == "troubleshooting_leakage":
        return "troubleshooting"
    if goal == "out_of_scope":
        return "out_of_scope"
    return "smalltalk"


def _maybe_set_recommendation_go(state: SealAIState) -> None:
    if state.recommendation_go:
        return
    last_message = latest_user_text(state.messages or [])
    if not last_message:
        return
    normalized = last_message.lower()
    if any(keyword in normalized for keyword in YES_KEYWORDS):
        state.recommendation_go = True
        return
    if any(keyword in normalized for keyword in NO_KEYWORDS):
        state.recommendation_go = False


__all__ = [
    "supervisor_logic_node",
    "supervisor_route",
    "supervisor_policy_node",
    "aggregator_node",
    "panel_calculator_node",
    "panel_material_node",
    "panel_norms_rag_node",
    "ACTION_ASK_USER",
    "ACTION_RUN_PANEL_CALC",
    "ACTION_RUN_PANEL_MATERIAL",
    "ACTION_RUN_PANEL_NORMS_RAG",
    "ACTION_RUN_COMPARISON",
    "ACTION_RUN_TROUBLESHOOTING",
    "ACTION_CONFIRM_RECOMMENDATION",
    "ACTION_REQUIRE_CONFIRM",
    "ACTION_FINALIZE",
]
