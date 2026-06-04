from __future__ import annotations

from typing import Callable, Iterable, Literal

from app.agent.graph import GraphState
from app.agent.runtime.clarification_priority import prioritized_open_point_labels
from app.agent.runtime.outward_names import normalize_outward_response_class
from app.agent.state.models import ConversationStrategyContract, TurnContextContract

# ── Fast-confirm helpers ────────────────────────────────────────────────────
# Defined here (not imported from output_contract_node) to avoid circular
# imports — output_contract_node imports build_governed_turn_context from here.

_FAST_CONFIRM_CORE_FIELDS: tuple[str, ...] = (
    "medium",
    "temperature_c",
    "pressure_bar",
    "shaft_diameter_mm",
    "speed_rpm",
    "sealing_type",
)

_FAST_CONFIRM_OPTIONAL_FIELDS: frozenset[str] = frozenset({
    "installation",
    "geometry_context",
    "duty_profile",
    "counterface_surface",
    "contamination",
    "tolerances",
    "industry",
    "compliance",
    "motion_type",
    "pressure_direction",
    "medium_qualifiers",
})

# Human-readable assumption labels added to confirmed_facts_summary
# so the LLM render knows what was assumed.
_FAST_CONFIRM_ASSUMPTION_LABELS: dict[str, str] = {
    "installation":        "Einbausituation: Pumpen-Einbau (angenommen)",
    "duty_profile":        "Betriebsprofil: Dauerbetrieb (angenommen)",
    "motion_type":         "Bewegungsart: rotierend (angenommen)",
    "counterface_surface": "Gegenlaufpartner: geschliffene Welle Ra ≤ 0.8 µm (angenommen)",
    "contamination":       "Feststoffeintrag: kein besonderer (angenommen)",
    "geometry_context":    "Einbaugeometrie: Standard (angenommen)",
}


def _fast_confirm_applicable(state: GraphState, blocking: list[str]) -> bool:
    """True when 4+ core params are asserted and all blocking fields are optional."""
    if not blocking or state.asserted.conflict_flags:
        return False
    if not all(f in _FAST_CONFIRM_OPTIONAL_FIELDS for f in blocking):
        return False
    count = sum(
        1 for f in _FAST_CONFIRM_CORE_FIELDS
        if state.asserted.assertions.get(f) is not None
        and state.asserted.assertions[f].asserted_value is not None
    )
    return count >= 4

_MAX_TURN_CONTEXT_ITEMS = 3       # open points per turn
_MAX_CONFIRMED_FACTS_LIMIT = 8    # all technical params should surface
_CONFIRMED_FACT_KEYS: tuple[str, ...] = (
    "medium",
    "installation",
    "geometry_context",
    "clearance_gap_mm",
    "counterface_surface",
    "counterface_material",
    "shaft_diameter_mm",
    "speed_rpm",
    "pressure_bar",
    "temperature_c",
)
_FIELD_LABELS: dict[str, str] = {
    "medium": "Medium",
    "installation": "Einbausituation",
    "geometry_context": "Geometrie",
    "clearance_gap_mm": "Spalt",
    "counterface_surface": "Oberflaeche",
    "counterface_material": "Gegenlaufpartner",
    "shaft_diameter_mm": "Wellendurchmesser",
    "speed_rpm": "Drehzahl",
    "pressure_bar": "Betriebsdruck",
    "temperature_c": "Betriebstemperatur",
}

_MOTION_HINT_LABELS: dict[str, str] = {
    "rotary": "Bewegungsart: rotierend",
    "linear": "Bewegungsart: linear",
    "static": "Bewegungsart: statisch",
}

_APPLICATION_HINT_LABELS: dict[str, str] = {
    "shaft_sealing": "Anwendung: Wellenabdichtung",
    "linear_sealing": "Anwendung: lineare Abdichtung",
    "static_sealing": "Anwendung: statische Abdichtung",
    "housing_sealing": "Anwendung: Gehaeuseabdichtung",
    "external_sealing": "Anforderung: nach aussen abdichten",
    "marine_propulsion": "Anwendung: Schiffsschraube / Wellenabdichtung",
}


def _compact_unique_strings(items: Iterable[str | None], *, limit: int = _MAX_TURN_CONTEXT_ITEMS) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def build_turn_context_contract(
    *,
    strategy: ConversationStrategyContract | None,
    confirmed_facts_summary: list[str] | None = None,
    open_points_summary: list[str] | None = None,
) -> TurnContextContract | None:
    """Build one small shared communication context object.

    Returns None only when there is neither a strategy hint nor compact
    contextual summaries to expose.
    """
    confirmed = _compact_unique_strings(confirmed_facts_summary or [], limit=_MAX_CONFIRMED_FACTS_LIMIT)
    open_points = _compact_unique_strings(open_points_summary or [], limit=_MAX_TURN_CONTEXT_ITEMS)

    if strategy is None and not confirmed and not open_points:
        return None

    if strategy is None:
        return TurnContextContract(
            primary_question_reason="",
            confirmed_facts_summary=confirmed,
            open_points_summary=open_points,
        )

    return TurnContextContract(
        conversation_phase=strategy.conversation_phase,
        turn_goal=strategy.turn_goal,
        user_signal_mirror=strategy.user_signal_mirror,
        primary_question=strategy.primary_question,
        primary_question_reason=strategy.primary_question_reason,
        supporting_reason=strategy.supporting_reason,
        response_mode=strategy.response_mode,
        confirmed_facts_summary=confirmed,
        open_points_summary=open_points,
    )


def _open_points_clarification(state: GraphState) -> list[str]:
    result = prioritized_open_point_labels(state, state.asserted.blocking_unknowns)
    result.extend(
        f"Konflikt bei {_FIELD_LABELS.get(field_name, field_name)}"
        for field_name in state.asserted.conflict_flags
    )
    return result


_OPEN_POINTS_SELECTORS: dict[str, Callable[[GraphState], list[str]]] = {
    "structured_clarification": _open_points_clarification,
    "inquiry_ready": lambda state: list(
        state.dispatch_contract.unresolved_points or state.export_profile.unresolved_points
    ),
}


def build_governed_turn_context(
    *,
    state: GraphState,
    strategy: ConversationStrategyContract,
    response_class: Literal[
        "structured_clarification",
        "governed_state_update",
        "technical_preselection",
        "candidate_shortlist",
        "inquiry_ready",
    ] | str = "structured_clarification",
) -> TurnContextContract:
    """Build a compact governed turn-context from existing deterministic state."""
    response_class = normalize_outward_response_class(response_class)
    current_turn_index = state.analysis_cycle
    confirmed_facts_current_turn: list[str] = []
    confirmed_facts_stable: list[str] = []
    for field_name in _CONFIRMED_FACT_KEYS:
        claim = state.asserted.assertions.get(field_name)
        if claim is None or claim.asserted_value is None:
            continue
        label = _FIELD_LABELS.get(field_name, field_name)
        # Determine whether the value is assumed/estimated or confirmed
        lifecycle_status = state.normalized.parameter_status.get(field_name)
        is_assumed = (
            lifecycle_status == "assumed"
            or claim.confidence in ("estimated", "inferred", "requires_confirmation")
        )
        raw_val = claim.asserted_value
        # Normalize integer-like floats (6000.0 → 6000) so the LLM prompt
        # doesn't contain "6000.0" which would propagate into chat output.
        display_val = int(raw_val) if isinstance(raw_val, float) and raw_val == int(raw_val) else raw_val
        if is_assumed:
            fact = f"{label}: {display_val} (angenommen)"
        else:
            fact = f"{label}: {display_val}"
        normalized = state.normalized.parameters.get(field_name)
        if normalized is not None and normalized.source_turn == current_turn_index:
            confirmed_facts_current_turn.append(fact)
        else:
            confirmed_facts_stable.append(fact)

    motion_label = getattr(state.motion_hint, "label", None)
    if isinstance(state.motion_hint, dict):
        motion_label = state.motion_hint.get("label")
    application_label = getattr(state.application_hint, "label", None)
    if isinstance(state.application_hint, dict):
        application_label = state.application_hint.get("label")

    if motion_label in _MOTION_HINT_LABELS:
        target = confirmed_facts_current_turn if getattr(state.motion_hint, "source_turn_index", None) == current_turn_index else confirmed_facts_stable
        target.append(_MOTION_HINT_LABELS[str(motion_label)])
    if application_label in _APPLICATION_HINT_LABELS:
        target = confirmed_facts_current_turn if getattr(state.application_hint, "source_turn_index", None) == current_turn_index else confirmed_facts_stable
        target.append(_APPLICATION_HINT_LABELS[str(application_label)])
    if state.governance.requirement_class is not None and state.governance.requirement_class.class_id:
        confirmed_facts_stable.append(f"Anforderungsklasse: {state.governance.requirement_class.class_id}")

    open_points = _OPEN_POINTS_SELECTORS.get(
        response_class,
        lambda s: prioritized_open_point_labels(s, s.governance.open_validation_points),
    )(state)

    # ── Fast-confirm: suppress open_points, add assumption labels ──────────
    # When 4+ core params are present and ALL blocking fields are optional,
    # the system confirms params + states assumptions instead of asking.
    # Clearing open_points prevents the LLM render from asking about them.
    blocking = list(state.asserted.blocking_unknowns)
    if _fast_confirm_applicable(state, blocking):
        open_points = []
        for field in blocking:
            label = _FAST_CONFIRM_ASSUMPTION_LABELS.get(field)
            if label:
                confirmed_facts_stable.append(label)

    return build_turn_context_contract(
        strategy=strategy,
        confirmed_facts_summary=confirmed_facts_current_turn + confirmed_facts_stable,
        open_points_summary=open_points,
    ) or TurnContextContract()
