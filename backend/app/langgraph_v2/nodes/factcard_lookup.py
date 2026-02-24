"""node_factcard_lookup — deterministic KB lookup before supervisor.

Runs after frontdoor_discovery_node for queries routed to the supervisor.

Responsibilities:
- Extract relevant context from the user message and state
- Query FactCardStore for matching cards (deterministic triggers)
- Run GateChecker to detect hard-block conditions
- If a high-confidence deterministic answer exists: set response in
  working_memory and route to response_node (skip LLM)
- Otherwise: populate kb_factcard_result and route to node_compound_filter
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.langgraph_v2.state import SealAIState, WorkingMemory

log = logging.getLogger("app.langgraph_v2.nodes.factcard_lookup")

# Minimum number of matching factcards to count as a deterministic hit
_MIN_CARDS_FOR_DETERMINISTIC = 1


def node_factcard_lookup(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """KB FactCard lookup node.

    Returns a partial state dict with:
    - ``kb_factcard_result``: lookup metadata and matched cards
    - ``working_memory``: updated if deterministic answer available
    - ``last_node``
    """
    try:
        from app.services.knowledge.factcard_store import FactCardStore
        from app.services.knowledge.gate_checker import GateChecker
    except Exception as exc:
        log.warning("factcard_lookup.import_failed", extra={"error": str(exc)})
        return {
            "kb_factcard_result": {"error": str(exc), "deterministic": False},
            "last_node": "node_factcard_lookup",
        }

    # ------------------------------------------------------------------
    # Build query context from state
    # ------------------------------------------------------------------
    messages = state.messages or []
    last_user_message = ""
    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            last_user_message = str(getattr(msg, "content", ""))
            break

    query_lower = last_user_message.lower()

    parameters = state.parameters
    medium = getattr(parameters, "medium", None) if parameters else None
    temp_max = getattr(parameters, "temperature_max", None) if parameters else None
    temp_min = getattr(parameters, "temperature_min", None) if parameters else None
    pressure = getattr(parameters, "pressure_bar", None) if parameters else None

    # Detect food-grade requirement from query
    food_grade_required: Optional[bool] = None
    if any(kw in query_lower for kw in ["lebensmittel", "food grade", "food-grade", "fda", "pharma"]):
        food_grade_required = True

    gate_context: Dict[str, Any] = {}
    if temp_max is not None:
        gate_context["temperature_max_c"] = float(temp_max)
    if temp_min is not None:
        gate_context["temperature_min_c"] = float(temp_min)
    if food_grade_required is not None:
        gate_context["food_grade_required"] = food_grade_required

    # Intent goal from state
    intent = state.intent
    intent_goal = getattr(intent, "goal", "design_recommendation") if intent else "design_recommendation"

    # ------------------------------------------------------------------
    # Run FactCard lookup
    # ------------------------------------------------------------------
    store = FactCardStore.get_instance()
    matched_cards = store.match_query_to_cards(
        query_lower=query_lower,
        medium=medium,
        food_grade=food_grade_required,
    )

    # ------------------------------------------------------------------
    # Run Gate checks
    # ------------------------------------------------------------------
    gate_checker = GateChecker.get_instance()
    triggered_gates = gate_checker.check_all(gate_context)
    hard_blocks = [g for g in triggered_gates if g.is_hard_block()]
    warnings = [g for g in triggered_gates if g.is_warning()]

    log.info(
        "factcard_lookup.done",
        extra={
            "matched_cards": len(matched_cards),
            "hard_blocks": len(hard_blocks),
            "warnings": len(warnings),
            "run_id": state.run_id,
        },
    )

    # ------------------------------------------------------------------
    # Decide: deterministic answer or route to compound_filter
    # ------------------------------------------------------------------
    deterministic = False
    deterministic_reply: Optional[str] = None

    # Hard-block gates override everything — generate a blocking message
    if hard_blocks:
        block_messages = [g.message for g in hard_blocks]
        deterministic_reply = (
            "**Sicherheitshinweis:** Die angegebenen Betriebsbedingungen lösen "
            "kritische Ausschlusskriterien aus:\n\n"
            + "\n".join(f"- {m}" for m in block_messages)
        )
        deterministic = True

    # Food-gate with allowed compounds → deterministic recommendation
    elif food_grade_required is True and not hard_blocks:
        allowed = gate_checker.get_allowed_compounds(gate_context)
        if allowed:
            cards = [store.get_by_compound_id(c) for c in allowed if store.get_by_compound_id(c)]
            if cards:
                summaries = "\n".join(
                    f"- **{c.get('title')}**: {c.get('answer_template', '')}"
                    for c in cards
                )
                deterministic_reply = (
                    "Für Lebensmittel- und Pharmaanwendungen (FDA/food-grade) kommen "
                    "folgende PTFE-Werkstoffe in Frage:\n\n" + summaries
                )
                deterministic = True

    # Single unambiguous card match → deterministic answer
    elif len(matched_cards) == _MIN_CARDS_FOR_DETERMINISTIC and not hard_blocks:
        card = matched_cards[0]
        answer_tpl = card.get("answer_template")
        if answer_tpl:
            warning_text = ""
            if warnings:
                warning_text = "\n\n**Hinweise:** " + " | ".join(w.message for w in warnings)
            deterministic_reply = answer_tpl + warning_text
            deterministic = True

    # ------------------------------------------------------------------
    # Build result dict
    # ------------------------------------------------------------------
    kb_factcard_result: Dict[str, Any] = {
        "deterministic": deterministic,
        "matched_cards": [c.get("id") for c in matched_cards],
        "hard_blocks": [g.to_dict() for g in hard_blocks],
        "warnings": [g.to_dict() for g in warnings],
        "cards_loaded": store.is_loaded,
    }

    updates: Dict[str, Any] = {
        "kb_factcard_result": kb_factcard_result,
        "last_node": "node_factcard_lookup",
    }

    if deterministic and deterministic_reply:
        wm: WorkingMemory = state.working_memory or WorkingMemory()
        wm = wm.model_copy(update={"frontdoor_reply": deterministic_reply, "response_kind": "kb_factcard"})
        updates["working_memory"] = wm

    return updates


__all__ = ["node_factcard_lookup"]
