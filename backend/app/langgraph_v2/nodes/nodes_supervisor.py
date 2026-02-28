# backend/app/langgraph_v2/nodes/nodes_supervisor.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple, Literal

from pydantic import ValidationError
from langgraph.types import Command, Send

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.langgraph_v2.state import (
    Budget,
    CandidateItem,
    DecisionEntry,
    FactItem,
    Intent,
    QuestionItem,
    SealAIState,
    Source,
    WorkingMemory,
)
from app.langgraph_v2.nodes.nodes_frontdoor import detect_material_or_trade_query
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

_MATERIAL_DOC_TOKENS: tuple[str, ...] = (
    "datenblatt",
    "datasheet",
    "data sheet",
    "technical sheet",
    "werkstoff",
    "material",
    "nbr",
    "fkm",
    "epdm",
    "hnbr",
    "ptfe",
    "vmq",
    "ffkm",
)
_MATERIAL_CODE_PATTERN = re.compile(r"\b[a-z]{2,6}[-_/]?\d{2,4}\b", re.IGNORECASE)
_EXPLICIT_KNOWLEDGE_LOOKUP_TOKENS: tuple[str, ...] = (
    "search_technical_docs",
    "get_available_filters",
    "qdrant",
    "knowledge-base",
    "knowledge base",
    "trade_name",
)

SUPERVISOR_SYSTEM_INSTRUCTION_QDRANT = (
    "You HAVE access to technical data sheets via the `search_technical_docs` tool in Qdrant. "
    "This tool performs semantic search on PDF documents. "
    "Use `get_available_filters` to discover dynamic metadata filters before applying targeted filter constraints. "
    "For material-data, norm, or datasheet questions, call `search_technical_docs` before answering. "
    "Never claim you cannot access Qdrant."
)


def _with_supervisor_qdrant_instruction(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    next_plan = dict(plan or {})
    raw = next_plan.get("system_instructions")
    instructions: List[str] = []
    if isinstance(raw, list):
        instructions = [str(item).strip() for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        instructions = [raw.strip()]
    if SUPERVISOR_SYSTEM_INSTRUCTION_QDRANT not in instructions:
        instructions.append(SUPERVISOR_SYSTEM_INSTRUCTION_QDRANT)
    next_plan["system_instructions"] = instructions
    return next_plan


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
        "plan": _with_supervisor_qdrant_instruction(state.plan),
        "phase": PHASE.INTENT,
        "last_node": "supervisor_logic_node",
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


def supervisor_policy_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Command:
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

    goal = getattr(state.intent, "goal", "design_recommendation") if state.intent else "design_recommendation"
    user_text = latest_user_text(state.messages or []) or ""
    flags = dict(state.flags or {})
    frontdoor_intent_category = str(flags.get("frontdoor_intent_category") or "").upper()

    intent_needs_sources = bool(getattr(state.intent, "needs_sources", False) or getattr(state.intent, "need_sources", False)) if state.intent else False
    material_trade_query = detect_material_or_trade_query(user_text)
    explicit_knowledge_lookup = _is_explicit_knowledge_lookup(user_text)
    doc_like_query = _looks_like_material_doc_query(user_text)
    has_material_report = _has_material_report(state)

    requires_rag = bool(
        state.requires_rag
        or state.need_sources
        or intent_needs_sources
        or frontdoor_intent_category == "MATERIAL_RESEARCH"
        or material_trade_query
        or explicit_knowledge_lookup
        or doc_like_query
    )
    needs_pricing = bool(flags.get("needs_pricing") or frontdoor_intent_category == "COMMERCIAL")
    is_safety_critical = bool(flags.get("is_safety_critical"))
    is_engineering = bool(
        frontdoor_intent_category == "ENGINEERING_CALCULATION"
        or goal == "design_recommendation"
    )
    rag_turn_count = int(getattr(state, "rag_turn_count", 0) or 0)

    forced_intent = state.intent
    if requires_rag:
        # Stop RAG after 3 attempts to prevent infinite recursion
        if rag_turn_count >= 3:
            logger.warning("supervisor_policy_node.rag_turn_limit_reached", rag_turn_count=rag_turn_count)
            requires_rag = False
            flags["rag_limit_reached"] = True
        
    if requires_rag:
        if forced_intent is None:
            forced_intent = Intent(
                goal="explanation_or_comparison",
                confidence=0.8,
                high_impact_gaps=[],
                needs_sources=True,
                need_sources=True,
            )
        else:
            forced_goal = forced_intent.goal
            if material_trade_query and forced_goal in {"smalltalk", "out_of_scope"}:
                forced_goal = "explanation_or_comparison"
            forced_intent = forced_intent.model_copy(
                update={
                    "goal": forced_goal,
                    "needs_sources": True,
                    "need_sources": True,
                }
            )

    update: Dict[str, Any] = {
        "plan": _with_supervisor_qdrant_instruction(state.plan),
        "phase": PHASE.SUPERVISOR,
        "last_node": "supervisor_policy_node",
        "missing_params": missing,
        "coverage_gaps": missing,
        "coverage_score": coverage_score,
        "recommendation_ready": recommendation_ready,
        "requires_rag": requires_rag,
        "need_sources": requires_rag,
    }
    if forced_intent is not None:
        update["intent"] = forced_intent
    if derived:
        update["open_questions"] = questions

    actions: List[Send] = []
    seen_nodes: set[str] = set()

    def _append_action(node: str, payload_state: SealAIState) -> None:
        if node in seen_nodes:
            return
        actions.append(Send(node, payload_state))
        seen_nodes.add(node)

    if is_safety_critical:
        _append_action("safety_agent", state.model_copy(update=update))

    if requires_rag and not has_material_report:
        material_update = dict(update)
        if forced_intent is not None:
            material_update["intent"] = forced_intent
        _append_action("material_agent", state.model_copy(update=material_update))

    if needs_pricing:
        _append_action("pricing_agent", state.model_copy(update=update))

    if is_engineering and (state.calc_results is None or not bool(state.calc_results_ok)):
        _append_action("calculator_agent", state.model_copy(update=update))

    if actions:
        update["next_action"] = "MAP_REDUCE_PARALLEL"
        return Command(update=update, goto=actions)

    if goal == "troubleshooting_leakage":
        update["next_action"] = ACTION_RUN_TROUBLESHOOTING
        return Command(update=update, goto="troubleshooting_wizard_node")

    if goal == "explanation_or_comparison":
        update["next_action"] = ACTION_RUN_COMPARISON
        return Command(update=update, goto="material_comparison_node")

    if any(q.priority == "high" and q.status == "open" for q in questions):
        update["next_action"] = ACTION_ASK_USER
    else:
        update["next_action"] = ACTION_FINALIZE
    return Command(update=update, goto="final_answer_node")


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
    patch.update({"working_memory": wm})
    return patch


def panel_material_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("panel_material_node", state)
    from app.langgraph_v2.nodes.nodes_flows import material_agent_node

    patch = material_agent_node(state, *_args, **_kwargs)
    wm = patch.get("working_memory") or state.working_memory or WorkingMemory()
    panel_payload = dict(wm.panel_material or {})
    panel_payload.update(
        {
            "material_choice": patch.get("material_choice") or state.material_choice,
            "material_candidates": list(wm.material_candidates or []),
        }
    )
    wm = wm.model_copy(update={"panel_material": panel_payload})
    patch.update({"working_memory": wm})
    return patch


def panel_norms_rag_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("panel_norms_rag_node", state)
    from app.langgraph_v2.nodes.nodes_flows import rag_support_node

    return rag_support_node(state, *_args, **_kwargs)


def calculator_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return panel_calculator_node(state, *_args, **_kwargs)


def safety_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("safety_agent_node", state)
    wm = state.working_memory or WorkingMemory()
    design_notes = dict(wm.design_notes or {})
    design_notes.update(
        {
            "safety_review_required": True,
            "safety_reason": "High-risk operating conditions detected in frontdoor classification.",
        }
    )
    wm = wm.model_copy(update={"design_notes": design_notes})
    critical = dict(state.critical or {})
    critical.update({"status": "requires_safety_review", "target": "safety_agent", "severity": 4})
    safety_review = {
        "severity": 4,
        "code": "SAFETY_CRITICAL_H2_APPLICATION",
        "reason": "Safety-critical operating conditions require human validation.",
    }
    return {
        "working_memory": wm,
        "critical": critical,
        "safety_review": safety_review,
    }


def pricing_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("pricing_agent_node", state)
    wm = state.working_memory or WorkingMemory()
    design_notes = dict(wm.design_notes or {})
    pricing_payload = {
        "needs_pricing": True,
        "quantity": design_notes.get("requested_quantity"),
        "sku": design_notes.get("requested_sku"),
    }
    comparison_notes = dict(wm.comparison_notes or {})
    comparison_notes.update({"pricing_request": pricing_payload})
    wm = wm.model_copy(update={"comparison_notes": comparison_notes})
    return {
        "working_memory": wm,
    }


def supervisor_route(state: SealAIState) -> str:
    # Legacy routing function - now deprecated/unused by main policy
    # but kept for interface compatibility if imported elsewhere
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


def _looks_like_material_doc_query(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    if any(token in normalized for token in _MATERIAL_DOC_TOKENS):
        return True
    return bool(_MATERIAL_CODE_PATTERN.search(normalized))


def _is_explicit_knowledge_lookup(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in _EXPLICIT_KNOWLEDGE_LOOKUP_TOKENS)


def _has_material_report(state: SealAIState) -> bool:
    panel_material = getattr(state.working_memory, "panel_material", {}) if state.working_memory else {}
    if isinstance(panel_material, dict):
        docs = panel_material.get("technical_docs")
        if isinstance(docs, list) and docs:
            return True
        rag_context = panel_material.get("rag_context") or panel_material.get("reducer_context")
        if isinstance(rag_context, str) and rag_context.strip():
            return True
    retrieval_meta = state.retrieval_meta or {}
    reducer_meta = retrieval_meta.get("reducer") if isinstance(retrieval_meta, dict) else None
    if isinstance(reducer_meta, dict) and int(reducer_meta.get("count") or 0) > 0:
        return True
    return False


__all__ = [
    "supervisor_logic_node",
    "supervisor_route",
    "supervisor_policy_node",
    "aggregator_node",
    "panel_calculator_node",
    "panel_material_node",
    "panel_norms_rag_node",
    "calculator_agent_node",
    "safety_agent_node",
    "pricing_agent_node",
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
