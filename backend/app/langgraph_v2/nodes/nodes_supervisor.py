# backend/app/langgraph_v2/nodes/nodes_supervisor.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

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
    _maybe_set_recommendation_go(state)
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
    goal = getattr(state.intent, "goal", "design_recommendation") if state.intent else "design_recommendation"

    if goal in ("smalltalk", "out_of_scope"):
        reason = "non_technical_goal"
        action = ACTION_FINALIZE
    elif goal == "troubleshooting_leakage":
        reason = "troubleshooting_flow"
        action = ACTION_RUN_TROUBLESHOOTING
    elif goal == "explanation_or_comparison":
        comparison_notes = getattr(state.working_memory, "comparison_notes", {}) if state.working_memory else {}
        has_comparison = bool(comparison_notes.get("comparison_text"))
        has_rag = bool(comparison_notes.get("rag_context"))
        if not has_comparison:
            reason = "comparison_missing"
            action = ACTION_RUN_COMPARISON
        elif bool(getattr(state, "requires_rag", False)) and not has_rag:
            reason = "comparison_needs_rag"
            action = ACTION_RUN_PANEL_NORMS_RAG
        else:
            reason = "comparison_ready"
            action = ACTION_FINALIZE
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
        action = ACTION_ASK_USER
    else:
        missing_calc = state.calc_results is None or not bool(getattr(state, "calc_results_ok", False))
        material_choice = state.material_choice or {}
        missing_material = not bool(material_choice.get("material"))
        intent_needs_sources = bool(getattr(state.intent, "needs_sources", False)) if state.intent else False
        intent_need_sources = bool(getattr(state.intent, "need_sources", False)) if state.intent else False
        needs_rag = bool(
            getattr(state, "requires_rag", False)
            or intent_needs_sources
            or intent_need_sources
            or getattr(state, "need_sources", False)
        )

        if missing_calc:
            reason = "missing_calc_facts"
            action = ACTION_RUN_PANEL_CALC
        elif missing_material:
            reason = "missing_material_decision"
            action = ACTION_RUN_PANEL_MATERIAL
        elif contradictions or needs_rag:
            reason = "resolve_contradictions" if contradictions else "needs_rag"
            action = ACTION_RUN_PANEL_NORMS_RAG
        else:
            reason = "no_action_required"
            action = ACTION_FINALIZE

    requires_confirm = (
        action == ACTION_RUN_PANEL_NORMS_RAG
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
        retrieval_meta = {
            "skipped": True,
            "reason": "requires_rag_false",
            "tenant_id": state.tenant_id or state.user_id,
        }

    patch: Dict[str, Any] = {
        "next_action": action,
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
    }
    if retrieval_meta:
        patch["retrieval_meta"] = retrieval_meta
    if derived:
        patch["open_questions"] = questions
    return patch


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
