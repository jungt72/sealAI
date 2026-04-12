"""
output_contract_node — Phase F-C.1, Zone 7

Outward contract assembly.

Responsibility:
    Determine the outward response class deterministically from GovernanceState,
    assemble a clean public payload (output_public), and produce a deterministic
    reply stub (output_reply). Nothing internal leaks past this node.

Architecture invariants enforced here:
    - Invariant 8: output_public NEVER contains raw ObservedState, NormalizedState,
      AssertedState, or GovernanceState objects — only derived, clean values.
    - LLM does NOT call here. All text is template-generated.
    - The response class is derived from GovernanceState — the LLM cannot
      produce a class that the deterministic state has not reached.
    - No class may be skipped (Blaupause: conversational_answer → … → inquiry_ready).

Response class selection (deterministic from GovernanceState.gov_class):

    rfq.rfq_ready is True            → inquiry_ready
        (bounded RFQ handover basis is available)
    matching.status indicates match  → candidate_shortlist
        (bounded manufacturer candidate is available)
    gov_class is None / D           → structured_clarification
        (nothing useful asserted — ask for core parameters)
    gov_class C                     → structured_clarification
        (cycle exhausted or unresolvable conflict)
    gov_class B                     → structured_clarification
        (blocking unknowns — ask for the missing fields)
    gov_class A + compute_results   → technical_preselection
        (full technical specification with calc output)
    gov_class A + no compute        → governed_state_update
        (all core parameters confirmed — state visible, no calc needed)

    Phase G Block 1 may now produce candidate_shortlist.
    inquiry_ready remains reserved for a later phase.

output_public shape (Invariant 8 — no internal artefacts):
    response_class      — one of the 6 outward classes
    gov_class           — "A"|"B"|"C"|"D" (derived summary, not raw object)
    inquiry_admissible  — bool
    parameters          — {field: {value, confidence, source_turn}}
    missing_fields      — list[str] of blocking unknowns
    conflicts           — list[str] of conflict field names
    validity_notes      — list[str] from GovernanceState.validity_limits
    open_points         — list[str] from GovernanceState.open_validation_points
    compute             — list[dict] simplified calc summaries (Phase F: RWDR)
    matching            — bounded matching summary for outward use
    rfq                 — bounded RFQ-handover summary for outward use
    dispatch            — bounded dispatch/transport-prep summary for outward use
    norm                — bounded SealAI norm summary for outward use
    export_profile      — bounded export-profile summary for outward use
    manufacturer_mapping — bounded manufacturer-mapping summary for outward use
    dispatch_contract   — bounded connector-ready contract for outward use
    message             — human-readable stub (template, not LLM)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Literal

from langgraph.types import Command, interrupt

from app.agent.domain.admissibility import check_inquiry_admissibility
from app.agent.graph import GraphState
from app.agent.runtime.clarification_priority import prioritized_open_point_labels, select_clarification_priority
from app.agent.runtime.outward_names import build_admissibility_payload
from app.agent.runtime.reply_composition import compose_clarification_reply, compose_result_reply
from app.agent.runtime.turn_context import build_governed_turn_context
from app.agent.state.models import ConversationStrategyContract

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Knowledge / comparison question detection (zone-stickiness override)
# ---------------------------------------------------------------------------
# In a GOVERNED session, pure knowledge or comparison questions must NOT trigger
# a governed_state_update. Instead they are routed to the light runtime
# (conversation_runtime or exploration_runtime) without any state dump.

_KNOWLEDGE_PATTERNS: tuple[str, ...] = (
    r"was ist\b",
    r"was sind\b",
    r"erkl[äa]r",
    r"erkläre\b",
    r"erklär\b",
    r"wie funktioniert",
    r"was bedeutet",
    r"was bedeutet\b",
    r"was heisst",
    r"was versteht man unter",
    r"kannst du.*erklären",
)

_COMPARISON_PATTERNS: tuple[str, ...] = (
    r"vergleich",
    r"\bunterschied\b",
    r"\bversus\b",
    r"\bvs\.?\b",
    r"besser.*oder",
    r"oder.*besser",
)

# These markers indicate a parameter correction/update — override is suppressed.
_PARAM_UPDATE_MARKERS: tuple[str, ...] = (
    r"\bstatt\b",
    r"\bkorrig",
    r"\bsondern\b",
    r"\bänder",
    r"\bkorrekt(?:ur)?\b",
)


def classify_message_as_knowledge_override(
    message: str,
) -> Literal["conversational_answer", "exploration_answer"] | None:
    """Return an override response class for knowledge/comparison questions in GOVERNED.

    Returns None when the message is a parameter update (correction markers present)
    or when no knowledge/comparison pattern matches.
    """
    lowered = str(message or "").strip().lower()
    if not lowered:
        return None
    # Parameter update markers suppress the override — keep governed flow
    if any(re.search(p, lowered, re.IGNORECASE) for p in _PARAM_UPDATE_MARKERS):
        return None
    # Comparison is checked first — "was ist besser: X oder Y?" should use RAG
    if any(re.search(p, lowered, re.IGNORECASE) for p in _COMPARISON_PATTERNS):
        return "exploration_answer"
    if any(re.search(p, lowered, re.IGNORECASE) for p in _KNOWLEDGE_PATTERNS):
        return "conversational_answer"
    return None


# Outward response classes (Blaupause V1.1)
_STRUCTURED_CLARIFICATION = "structured_clarification"
_GOVERNED_STATE_UPDATE     = "governed_state_update"
_TECHNICAL_PRESELECTION = "technical_preselection"
_CANDIDATE_SHORTLIST = "candidate_shortlist"
_INQUIRY_READY = "inquiry_ready"

# Fields that are treated as optional when 4+ core params are already confirmed.
# When all remaining missing fields are in this set, the system confirms parameters
# and states assumptions instead of asking a question.
_OPTIONAL_CLARIFICATION_FIELDS: frozenset[str] = frozenset({
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

# Default assumptions stated when optional fields are missing and we skip asking.
_ASSUMPTION_DEFAULTS: dict[str, str] = {
    "installation": "Pumpen-Einbau (typische Radialdichtungs-Einbaugeometrie)",
    "geometry_context": "Standard-Einbau ohne besondere Bauraumrestriktionen",
    "duty_profile": "Dauerbetrieb",
    "motion_type": "rotierend",
    "counterface_surface": "geschliffene Welle (Ra ≤ 0.8 µm)",
    "contamination": "kein besonderer Feststoffeintrag",
    "pressure_direction": "Abdichtung nach außen",
}

# Core params counted to decide whether we can skip optional questions.
_CORE_TECH_FIELDS: tuple[str, ...] = (
    "medium",
    "temperature_c",
    "pressure_bar",
    "shaft_diameter_mm",
    "speed_rpm",
    "sealing_type",
)

# Core fields the system always asks for when missing
_CORE_FIELD_LABELS: dict[str, str] = {
    "medium":            "Medium",
    "pressure_bar":      "Betriebsdruck [bar]",
    "temperature_c":     "Betriebstemperatur [°C]",
    "sealing_type":      "Dichtungstyp",
    "shaft_diameter_mm": "Wellendurchmesser [mm]",
    "speed_rpm":         "Drehzahl [rpm]",
    "duty_profile": "Betriebsprofil",
    "installation": "Einbausituation",
    "geometry_context": "Geometrie / Bauform",
    "pressure_direction": "Druckrichtung",
    "contamination": "Schmutz / Partikel",
    "counterface_surface": "Gegenlaufpartner / Oberflaeche",
    "tolerances": "Rundlauf / Toleranzen",
    "industry": "Branche",
    "compliance": "regulatorische Anforderungen",
    "medium_qualifiers": "Mediumdetails",
}

_CLARIFICATION_FIELD_META: dict[str, dict[str, str | int]] = {
    "medium": {
        "label": "Medium (Fluid/Gas)",
        "question": "Um welches Medium geht es genau?",
        "conflict_question": "Welches Medium ist hier der richtige Wert?",
        "reason": "Das Medium entscheidet zuerst ueber Werkstoffwahl und Einsatzrahmen.",
        "priority": 0,
    },
    "pressure_bar": {
        "label": "Betriebsdruck [bar]",
        "question": "Wie hoch ist der Betriebsdruck ungefähr?",
        "conflict_question": "Welcher Betriebsdruck ist hier der richtige Wert?",
        "reason": "Der Druck bestimmt, welche Belastung die Dichtung sicher aufnehmen muss.",
        "priority": 1,
    },
    "temperature_c": {
        "label": "Betriebstemperatur [°C]",
        "question": "In welchem Temperaturbereich arbeiten Sie?",
        "conflict_question": "Welche Betriebstemperatur ist hier der richtige Wert?",
        "reason": "Die Temperatur grenzt Werkstoff und Einsatzfenster ein.",
        "priority": 2,
    },
    "sealing_type": {
        "label": "Dichtungstyp / Dichtprinzip",
        "question": "Um welchen Dichtungstyp oder welches Dichtprinzip geht es?",
        "conflict_question": "Welcher Dichtungstyp ist hier der richtige Wert?",
        "reason": "Ohne Dichtungstyp bleibt der technische Loesungsraum zu breit fuer eine belastbare Vorauswahl.",
        "priority": 3,
    },
    "duty_profile": {
        "label": "Betriebsprofil",
        "question": "Ist der Betrieb kontinuierlich, intermittierend oder nur gelegentlich?",
        "conflict_question": "Welches Betriebsprofil ist hier der richtige Wert?",
        "reason": "Das Betriebsprofil entscheidet mit, wie robust die Vorauswahl ausgelegt werden muss.",
        "priority": 4,
    },
    "installation": {
        "label": "Einbausituation",
        "question": "Wie ist die Einbausituation bei Ihnen genau ausgeführt?",
        "conflict_question": "Welche Einbausituation ist hier der richtige Stand?",
        "reason": "Die Einbausituation bestimmt, wie der Dichtungsfall technisch eingegrenzt werden kann.",
        "priority": 5,
    },
    "geometry_context": {
        "label": "Geometrie / Bauform",
        "question": "Welche Geometrie oder vorhandene Bauform liegt an der Dichtstelle vor?",
        "conflict_question": "Welche Geometrie oder Bauform ist hier der richtige Stand?",
        "reason": "Die Geometrie grenzt den Dichtprinzipraum und den Requirement-Class-Raum deutlich ein.",
        "priority": 6,
    },
    "compliance": {
        "label": "regulatorische Anforderungen",
        "question": "Welche regulatorischen Anforderungen gelten hier, zum Beispiel FDA, ATEX oder eine Normvorgabe?",
        "conflict_question": "Welche regulatorische Anforderung ist hier der richtige Stand?",
        "reason": "Regulatorische Anforderungen duerfen nicht als technischer Fit mitgeraten werden.",
        "priority": 7,
    },
    "pressure_direction": {
        "label": "Druckrichtung",
        "question": "Aus welcher Richtung wirkt der Druck an der Dichtung?",
        "conflict_question": "Welche Druckrichtung ist hier der richtige Stand?",
        "reason": "Die Druckrichtung beeinflusst Dichtprinzip und Belastungsfall.",
        "priority": 8,
    },
    "medium_qualifiers": {
        "label": "Mediumdetails",
        "question": "Welche Mediumdetails sind bekannt, zum Beispiel Konzentration, Chloride oder Feststoffanteile?",
        "conflict_question": "Welche Mediumdetails sind hier der richtige Stand?",
        "reason": "Diese Mediumdetails koennen die Werkstoff- und Korrosionsgrenzen entscheidend veraendern.",
        "priority": 9,
    },
    "contamination": {
        "label": "Schmutz / Partikel",
        "question": "Gibt es Schmutz, Partikel oder abrasive Anteile im Umfeld oder Medium?",
        "conflict_question": "Welche Angabe zu Schmutz oder Partikeln ist hier der richtige Stand?",
        "reason": "Partikel und abrasive Anteile koennen Werkstoff- und Bauartgrenzen frueh verschieben.",
        "priority": 10,
    },
    "counterface_surface": {
        "label": "Gegenlaufpartner / Oberflaeche",
        "question": "Wie sehen Gegenlaufpartner und Oberflaechen an der Dichtstelle aus?",
        "conflict_question": "Welche Angabe zu Gegenlaufpartner oder Oberflaeche ist hier der richtige Stand?",
        "reason": "Oberflaeche und Gegenlaufpartner beeinflussen Dichtverhalten und Verschleiss stark mit.",
        "priority": 11,
    },
    "tolerances": {
        "label": "Rundlauf / Toleranzen",
        "question": "Gibt es Angaben zu Rundlauf, Exzentrizitaet, Spalt oder Toleranzen?",
        "conflict_question": "Welche Toleranzangabe ist hier der richtige Stand?",
        "reason": "Toleranzen und Rundlauf bestimmen, wie belastbar die Dichtstelle technisch einzuordnen ist.",
        "priority": 12,
    },
}


def _preselection_blocker_fields(state: GraphState) -> list[str]:
    return list(
        dict.fromkeys(
            list(getattr(state.governance, "preselection_blockers", []) or [])
            + list(getattr(state.governance, "compliance_blockers", []) or [])
            + list(getattr(state.governance, "type_sensitive_required", []) or [])
        )
    )


def _has_asserted_value(state: GraphState, field_name: str) -> bool:
    claim = state.asserted.assertions.get(field_name)
    return claim is not None and claim.asserted_value is not None


def _has_recommendation_boundary_anchor(state: GraphState) -> bool:
    boundary_fields = (
        "installation",
        "geometry_context",
        "clearance_gap_mm",
        "counterface_surface",
        "counterface_material",
    )
    if any(_has_asserted_value(state, field_name) for field_name in boundary_fields):
        return True

    motion_label = getattr(state.motion_hint, "label", None)
    if isinstance(state.motion_hint, dict):
        motion_label = state.motion_hint.get("label")
    application_label = getattr(state.application_hint, "label", None)
    if isinstance(state.application_hint, dict):
        application_label = state.application_hint.get("label")

    if motion_label == "rotary" or application_label in {"shaft_sealing", "marine_propulsion"}:
        return _has_asserted_value(state, "shaft_diameter_mm") and _has_asserted_value(state, "speed_rpm")
    return False


def _is_recommendation_ready(state: GraphState) -> bool:
    if _blocking_evidence_gaps_for_preselection(state):
        return False

    if _preselection_blocker_fields(state):
        return False

    requirement_class = state.governance.requirement_class
    class_id = str(getattr(requirement_class, "class_id", "") or "").strip()
    if not class_id:
        return False

    open_points = [str(item or "").strip() for item in state.governance.open_validation_points]
    blocking_open_points = [
        item
        for item in open_points
        if item
        and item not in {"pressure_bar", "temperature_c"}
        and not item.startswith("Unresolved conflict:")
    ]
    if blocking_open_points:
        return False

    if state.asserted.conflict_flags or state.asserted.blocking_unknowns:
        return False

    return _has_recommendation_boundary_anchor(state)


def _blocking_evidence_gaps_for_preselection(state: GraphState) -> list[str]:
    """Return evidence gaps that make technical_preselection too strong."""

    blocking: list[str] = []
    for gap in list(getattr(state.evidence, "evidence_gaps", []) or []):
        text = str(gap or "").strip()
        if not text:
            continue
        if text.startswith("missing_source_for_") or text in {"retrieval_failed", "no_evidence_retrieved"}:
            blocking.append(text)
    return list(dict.fromkeys(blocking))


def _shortlist_release_blockers(state: GraphState) -> list[str]:
    blockers: list[str] = []
    if not state.matching.shortlist_ready:
        blockers.append("shortlist_not_released")
    blockers.extend(list(state.matching.release_blockers))
    blockers.extend(_preselection_blocker_fields(state))
    blockers.extend(_blocking_evidence_gaps_for_preselection(state))
    blockers.extend(str(item) for item in list(state.asserted.blocking_unknowns or []) if item)
    blockers.extend(f"conflict:{item}" for item in list(state.asserted.conflict_flags or []) if item)
    return list(dict.fromkeys(blockers))


def _inquiry_release_blockers(state: GraphState) -> list[str]:
    blockers = _shortlist_release_blockers(state)
    if not state.matching.inquiry_ready:
        blockers.append("matching_not_inquiry_ready")
    blockers.extend(str(item) for item in list(state.rfq.blocking_findings or []) if item)
    blockers.extend(f"open_point:{item}" for item in list(state.governance.open_validation_points or []) if item)
    if not state.rfq.rfq_ready or state.rfq.status != "rfq_ready":
        blockers.append("rfq_not_ready")
    return list(dict.fromkeys(blockers))


def _pick_priority_clarification_field(fields: list[str]) -> str | None:
    prioritized = sorted(
        {field for field in fields if isinstance(field, str)},
        key=lambda field: (
            int(_CLARIFICATION_FIELD_META.get(field, {}).get("priority", 999)),
            _CORE_FIELD_LABELS.get(field, field),
        ),
    )
    return prioritized[0] if prioritized else None


def _clarification_field_meta(field_name: str | None) -> dict[str, str | int]:
    if field_name and field_name in _CLARIFICATION_FIELD_META:
        return _CLARIFICATION_FIELD_META[field_name]
    label = _CORE_FIELD_LABELS.get(field_name or "", field_name or "technische Angabe")
    return {
        "label": label,
        "question": f"Welche Angabe koennen Sie zu {label} noch nennen?",
        "conflict_question": f"Welche Angabe ist bei {label} der richtige Wert?",
        "reason": "Diese Angabe brauche ich, damit ich die Anwendung technisch sauber eingrenzen kann.",
        "priority": 999,
    }


def build_clarification_strategy_fields(state: GraphState) -> dict[str, str | None]:
    """Return small deterministic communication hints for clarification turns."""
    conflicts = state.asserted.conflict_flags
    missing = list(
        dict.fromkeys(
            list(state.asserted.blocking_unknowns)
            + _preselection_blocker_fields(state)
        )
    )
    pending_message = str(getattr(state, "pending_message", "") or "").strip().lower()
    is_correction_turn = any(marker in pending_message for marker in ("korrig", "statt", "sondern"))
    motion_label = getattr(state.motion_hint, "label", None)
    motion_turn = getattr(state.motion_hint, "source_turn_index", None)
    medium_param = state.normalized.parameters.get("medium")

    correction_mirror: str | None = None
    if is_correction_turn:
        if motion_label == "linear" and motion_turn == state.analysis_cycle:
            correction_mirror = "Verstanden, damit ist das kein rotativer, sondern ein linearer Dichtkontext."
        elif motion_label == "static" and motion_turn == state.analysis_cycle:
            correction_mirror = "Verstanden, damit liegt hier kein bewegter, sondern ein statischer Dichtkontext vor."
        elif medium_param is not None and medium_param.source_turn == state.analysis_cycle and medium_param.value is not None:
            correction_mirror = f"Verstanden, ich gehe jetzt vom korrigierten Medium {medium_param.value} aus."
        else:
            correction_mirror = "Verstanden, ich richte die technische Einordnung an Ihrer Korrektur neu aus."

    if conflicts:
        primary_conflict = _pick_priority_clarification_field(conflicts)
        meta = _clarification_field_meta(primary_conflict)
        return {
            "focus_key": str(primary_conflict) if primary_conflict else None,
            "user_signal_mirror": correction_mirror,
            "primary_question": str(meta["conflict_question"]),
            "primary_question_reason": str(meta["reason"]),
        }

    if missing:
        priority = select_clarification_priority(state, missing)
        if priority is not None:
            return {
                "focus_key": priority.focus_key,
                "user_signal_mirror": correction_mirror or "Die technische Richtung ist schon enger, jetzt brauche ich noch genau einen belastbaren Hebel.",
                "primary_question": priority.question,
                "primary_question_reason": priority.reason,
            }
        primary_missing = _pick_priority_clarification_field(missing)
        meta = _clarification_field_meta(primary_missing)
        return {
            "focus_key": str(primary_missing) if primary_missing else None,
            "user_signal_mirror": correction_mirror or "Ich habe schon genug Kontext, um den naechsten technischen Hebel gezielt zu setzen.",
            "primary_question": str(meta["question"]),
            "primary_question_reason": str(meta["reason"]),
        }

    return {
        "focus_key": None,
        "user_signal_mirror": None,
        "primary_question": None,
        "primary_question_reason": None,
    }


_GOVERNED_STRATEGY_FACTORIES: dict[str, Callable[[], ConversationStrategyContract]] = {
    _CANDIDATE_SHORTLIST: lambda: ConversationStrategyContract(
        conversation_phase="matching",
        turn_goal="explain_matching_result",
        response_mode="result_summary",
    ),
    _INQUIRY_READY: lambda: ConversationStrategyContract(
        conversation_phase="rfq_handover",
        turn_goal="prepare_handover",
        response_mode="handover_summary",
    ),
}


def build_governed_conversation_strategy_contract(
    state: GraphState,
    response_class: str,
) -> ConversationStrategyContract:
    """Return a small deterministic communication contract for governed replies."""
    if response_class == _STRUCTURED_CLARIFICATION:
        hints = build_clarification_strategy_fields(state)
        return ConversationStrategyContract(
            conversation_phase="narrowing",
            turn_goal="clarify_primary_open_point",
            user_signal_mirror=str(hints["user_signal_mirror"]) if hints.get("user_signal_mirror") else "",
            primary_question=str(hints["primary_question"]) if hints.get("primary_question") else None,
            primary_question_reason=str(hints["primary_question_reason"]) if hints.get("primary_question_reason") else "",
            response_mode="single_question",
        )
    factory = _GOVERNED_STRATEGY_FACTORIES.get(response_class)
    if factory is not None:
        return factory()
    return ConversationStrategyContract(
        conversation_phase="recommendation",
        turn_goal="explain_governed_result",
        response_mode="result_summary",
    )


# ---------------------------------------------------------------------------
# Response class selection
# ---------------------------------------------------------------------------

def _determine_response_class(state: GraphState) -> str:
    """Select the outward response class deterministically from GovernanceState."""
    pending_message = str(getattr(state, "pending_message", "") or "").strip()

    # Knowledge / comparison override: pure questions in a GOVERNED session must
    # not emit a governed_state_update. Correction markers ("statt", "korrigiere")
    # suppress the override so parameter updates go through the governed flow.
    knowledge_override = classify_message_as_knowledge_override(pending_message)
    if knowledge_override is not None:
        return knowledge_override

    gov_class = state.governance.gov_class
    preselection_blockers = _preselection_blocker_fields(state)

    if gov_class is None or gov_class == "D":
        return _STRUCTURED_CLARIFICATION
    if gov_class == "C":
        return _STRUCTURED_CLARIFICATION
    if gov_class == "B":
        # Fast-confirm: 4+ core params present, only optional fields missing
        # → emit governed_state_update (param confirmation) instead of asking
        if _is_fast_confirm_applicable(state):
            return _GOVERNED_STATE_UPDATE
        return _STRUCTURED_CLARIFICATION
    # gov_class == "A"
    if preselection_blockers:
        return _STRUCTURED_CLARIFICATION
    if state.rfq.rfq_ready and state.rfq.status == "rfq_ready" and not _inquiry_release_blockers(state):
        return _INQUIRY_READY
    if state.matching.status == "matched_primary_candidate" and not _shortlist_release_blockers(state):
        return _CANDIDATE_SHORTLIST
    if state.compute_results or _is_recommendation_ready(state):
        if _blocking_evidence_gaps_for_preselection(state):
            return _GOVERNED_STATE_UPDATE
        return _TECHNICAL_PRESELECTION
    return _GOVERNED_STATE_UPDATE


# ---------------------------------------------------------------------------
# Public payload assembly
# ---------------------------------------------------------------------------

def _parameters_public(state: GraphState) -> dict[str, Any]:
    """Derive a clean parameters dict from AssertedState (no internal objects)."""
    out: dict[str, Any] = {}
    for field_name, claim in state.asserted.assertions.items():
        out[field_name] = {
            "value":      claim.asserted_value,
            "confidence": claim.confidence,
        }
    return out


def _compute_public(state: GraphState) -> list[dict[str, Any]]:
    """Produce a trimmed compute summary for each calc result."""
    summaries = []
    for r in state.compute_results:
        calc_type = r.get("calc_type", "unknown")
        if calc_type == "rwdr":
            summaries.append({
                "calc_type":        "rwdr",
                "status":           r.get("status"),
                "v_surface_m_s":    r.get("v_surface_m_s"),
                "pv_value_mpa_m_s": r.get("pv_value_mpa_m_s"),
                "dn_value":         r.get("dn_value"),
                "dn_warning":       r.get("dn_warning"),
                "pv_warning":       r.get("pv_warning"),
                "hrc_warning":      r.get("hrc_warning"),
                "notes":            r.get("notes", []),
            })
        else:
            summaries.append({"calc_type": calc_type, "status": r.get("status")})
    return summaries


def _build_output_public_base(state: GraphState, response_class: str) -> dict[str, Any]:
    """Assemble the public-facing output payload (Invariant 8 compliant).

    The 'message' key is intentionally absent here — it is filled in by
    output_contract_node after awaiting the async _build_reply().
    """
    return {
        "response_class":  response_class,
        "gov_class":       state.governance.gov_class,
        **build_admissibility_payload(state.governance.rfq_admissible),
        "parameters":      _parameters_public(state),
        "missing_fields":  list(
            dict.fromkeys(
                list(state.asserted.blocking_unknowns)
                + _preselection_blocker_fields(state)
            )
        ),
        "conflicts":       list(state.asserted.conflict_flags),
        "validity_notes":  list(state.governance.validity_limits),
        "open_points":     prioritized_open_point_labels(state, state.governance.open_validation_points),
        "evidence": {
            "evidence_present": state.evidence.evidence_present,
            "evidence_count": state.evidence.evidence_count,
            "trusted_sources_present": state.evidence.trusted_sources_present,
            "evidence_supported_topics": list(state.evidence.evidence_supported_topics),
            "source_backed_findings": list(state.evidence.source_backed_findings),
            "deterministic_findings": list(state.evidence.deterministic_findings),
            "assumption_based_findings": list(state.evidence.assumption_based_findings),
            "unresolved_open_points": list(state.evidence.unresolved_open_points),
            "evidence_gaps": list(state.evidence.evidence_gaps),
            "blocking_evidence_gaps": _blocking_evidence_gaps_for_preselection(state),
        },
        "readiness": {
            "shortlist_ready": state.matching.shortlist_ready and not _shortlist_release_blockers(state),
            "inquiry_ready": state.matching.inquiry_ready and state.rfq.rfq_ready and not _inquiry_release_blockers(state),
            "shortlist_blockers": _shortlist_release_blockers(state),
            "inquiry_blockers": _inquiry_release_blockers(state),
        },
        "preselection_blockers": _preselection_blocker_fields(state),
        "missing_but_assumable": list(getattr(state.governance, "missing_but_assumable", []) or []),
        "optional_context": list(getattr(state.governance, "optional_context", []) or []),
        "compliance_blockers": list(getattr(state.governance, "compliance_blockers", []) or []),
        "type_sensitive_required": list(getattr(state.governance, "type_sensitive_required", []) or []),
        "compute":         _compute_public(state),
        "matching":        _matching_public(state),
        "rfq":             _rfq_public(state),
        "dispatch":        _dispatch_public(state),
        "norm":            _norm_public(state),
        "export_profile":  _export_profile_public(state),
        "manufacturer_mapping": _manufacturer_mapping_public(state),
        "dispatch_contract": _dispatch_contract_public(state),
    }


def _matching_public(state: GraphState) -> dict[str, Any]:
    selected = state.matching.selected_manufacturer_ref
    return {
        "status": state.matching.status,
        "matchability_status": state.matching.matchability_status,
        "shortlist_ready": state.matching.shortlist_ready and not _shortlist_release_blockers(state),
        "inquiry_ready": state.matching.inquiry_ready and not _inquiry_release_blockers(state),
        "release_blockers": _shortlist_release_blockers(state),
        "data_source": state.matching.data_source,
        "selected_manufacturer": selected.manufacturer_name if selected is not None else None,
        "manufacturer_count": len(state.matching.manufacturer_refs),
        "manufacturers": [
            ref.manufacturer_name
            for ref in state.matching.manufacturer_refs
            if ref.manufacturer_name
        ],
        "notes": list(state.matching.matching_notes),
    }


def _rfq_public(state: GraphState) -> dict[str, Any]:
    selected = state.rfq.selected_manufacturer_ref
    requirement_class = state.rfq.requirement_class
    return {
        "status": state.rfq.status,
        "rfq_ready": state.rfq.rfq_ready and not _inquiry_release_blockers(state),
        "release_blockers": _inquiry_release_blockers(state),
        **build_admissibility_payload(state.rfq.rfq_admissible),
        "handover_status": state.rfq.handover_status,
        "selected_manufacturer": selected.manufacturer_name if selected is not None else None,
        "recipient_count": len(state.rfq.recipient_refs),
        "qualified_material_count": len(state.rfq.qualified_material_ids),
        "confirmed_parameter_count": len(state.rfq.confirmed_parameters),
        "dimension_count": len(state.rfq.dimensions),
        "requirement_class": requirement_class.class_id if requirement_class is not None else None,
        "notes": list(state.rfq.notes),
    }


def _sanitize_public_notes(notes: list[str]) -> list[str]:
    blocked_fragments = (
        "transport",
        "bridge",
        "handoff",
        "dry-run",
        "internal trigger",
        "sender/connector",
        "connector consumption",
        "envelope",
    )
    public_notes: list[str] = []
    for note in notes:
        text = str(note or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if any(fragment in lowered for fragment in blocked_fragments):
            continue
        if text not in public_notes:
            public_notes.append(text)
    return public_notes


def _dispatch_public(state: GraphState) -> dict[str, Any]:
    selected = state.dispatch.selected_manufacturer_ref
    requirement_class = state.dispatch.requirement_class
    return {
        "dispatch_ready": state.dispatch.dispatch_ready,
        "dispatch_status": state.dispatch.dispatch_status,
        "selected_manufacturer": selected.manufacturer_name if selected is not None else None,
        "recipient_count": len(state.dispatch.recipient_refs),
        "requirement_class": requirement_class.class_id if requirement_class is not None else None,
        "notes": _sanitize_public_notes(list(state.dispatch.dispatch_notes)),
    }


def _norm_public(state: GraphState) -> dict[str, Any]:
    norm = state.sealai_norm
    return {
        "status": norm.status,
        "norm_version": norm.identity.norm_version,
        "sealai_request_id": norm.identity.sealai_request_id,
        "requirement_class": norm.identity.requirement_class_id,
        "seal_family": norm.identity.seal_family,
        "application_summary": norm.application_summary,
        "geometry": dict(norm.geometry),
        "material_family": norm.material.material_family,
        "qualified_materials": list(norm.material.qualified_materials),
        "assumptions": list(norm.assumptions),
        "validity_limits": list(norm.validity_limits),
        "open_validation_points": list(norm.open_validation_points),
        "manufacturer_validation_required": norm.manufacturer_validation_required,
    }


def _export_profile_public(state: GraphState) -> dict[str, Any]:
    export_profile = state.export_profile
    return {
        "status": export_profile.status,
        "export_profile_version": export_profile.export_profile_version,
        "sealai_request_id": export_profile.sealai_request_id,
        "selected_manufacturer": export_profile.selected_manufacturer,
        "recipient_count": len(export_profile.recipient_refs),
        "requirement_class": export_profile.requirement_class_id,
        "application_summary": export_profile.application_summary,
        "dimensions_summary": list(export_profile.dimensions_summary),
        "material_summary": export_profile.material_summary,
        "rfq_ready": export_profile.rfq_ready,
        "dispatch_ready": export_profile.dispatch_ready,
        "unresolved_points": list(export_profile.unresolved_points),
        "notes": _sanitize_public_notes(list(export_profile.export_notes)),
    }


def _manufacturer_mapping_public(state: GraphState) -> dict[str, Any]:
    mapping = state.manufacturer_mapping
    return {
        "status": mapping.status,
        "mapping_version": mapping.mapping_version,
        "selected_manufacturer": mapping.selected_manufacturer,
        "mapped_product_family": mapping.mapped_product_family,
        "mapped_material_family": mapping.mapped_material_family,
        "geometry_export_hint": mapping.geometry_export_hint,
        "unresolved_mapping_points": list(mapping.unresolved_mapping_points),
        "notes": list(mapping.mapping_notes),
    }


def _dispatch_contract_public(state: GraphState) -> dict[str, Any]:
    contract = state.dispatch_contract
    return {
        "status": contract.status,
        "contract_version": contract.contract_version,
        "sealai_request_id": contract.sealai_request_id,
        "selected_manufacturer": contract.selected_manufacturer,
        "recipient_count": len(contract.recipient_refs),
        "requirement_class": contract.requirement_class_id,
        "application_summary": contract.application_summary,
        "material_summary": contract.material_summary,
        "dimensions_summary": list(contract.dimensions_summary),
        "rfq_ready": contract.rfq_ready,
        "dispatch_ready": contract.dispatch_ready,
        "unresolved_points": list(contract.unresolved_points),
        "mapping_summary": contract.mapping_summary,
        "handover_notes": _sanitize_public_notes(list(contract.handover_notes)),
    }


# ---------------------------------------------------------------------------
# Reply text (deterministic template — no LLM)
# ---------------------------------------------------------------------------

_REPLY_BUILDERS: dict[str, Callable[..., str]] = {
    _STRUCTURED_CLARIFICATION: lambda state, strategy: _reply_clarification(state, strategy),
    _INQUIRY_READY:            lambda state, strategy: _reply_rfq_ready(state, strategy),
    _CANDIDATE_SHORTLIST:      lambda state, strategy: _reply_matching(state, strategy),
    _GOVERNED_STATE_UPDATE:    lambda state, strategy: _reply_state_update(state),
    _TECHNICAL_PRESELECTION:   lambda state, strategy: _reply_recommendation(state, strategy),
}


async def _build_reply(state: GraphState, response_class: str) -> str:
    """Generate the deterministic governed reply basis.

    This node owns the structured output contract. The final user-visible
    wording is assembled later through the canonical user-facing reply layer,
    so this node must not introduce an additional LLM speaking authority.
    """
    strategy = build_governed_conversation_strategy_contract(state, response_class)
    builder = _REPLY_BUILDERS.get(response_class)
    if builder is not None:
        return builder(state, strategy)
    return "Bitte geben Sie die technischen Parameter Ihrer Anwendung an."


def _confirmed_core_tech_count(state: GraphState) -> int:
    """Count how many core technical fields have any asserted value (any confidence)."""
    return sum(
        1 for f in _CORE_TECH_FIELDS
        if state.asserted.assertions.get(f) is not None
        and state.asserted.assertions[f].asserted_value is not None
    )


def _is_fast_confirm_applicable(state: GraphState) -> bool:
    """True when 4+ core params are confirmed and ALL missing fields are optional.

    When this is True the system should confirm parameters + state assumptions
    instead of asking a blocking clarification question.
    """
    if state.asserted.conflict_flags:
        return False
    missing = list(
        dict.fromkeys(
            list(state.asserted.blocking_unknowns)
            + _preselection_blocker_fields(state)
        )
    )
    if not missing:
        return False
    if _confirmed_core_tech_count(state) < 4:
        return False
    return all(f in _OPTIONAL_CLARIFICATION_FIELDS for f in missing)


def _reply_params_confirmed_with_assumptions(
    state: GraphState,
    missing_optional: list[str],
) -> str:
    """Return a confirmation message with stated assumptions for optional missing fields.

    Called when 4+ core params are confirmed and all remaining missing fields are
    optional. Instead of asking a question, confirms the captured params and states
    explicit assumptions so the user can correct them if needed.
    """
    # Internal STS enum → human-readable outward display name
    _SEALING_TYPE_DISPLAY: dict[str, str] = {
        "mechanical_seal": "Gleitringdichtung",
        "rwdr": "Radialwellendichtring (RWDR)",
        "o_ring": "O-Ring",
        "gasket": "Flachdichtung",
        "packing": "Stopfbuchse",
        "lip_seal": "Lippendichtung",
    }

    params = state.asserted.assertions
    parts: list[str] = []
    for field_name in ("medium", "sealing_type", "pressure_bar", "temperature_c", "shaft_diameter_mm", "speed_rpm"):
        if field_name in params and params[field_name].asserted_value is not None:
            label = _CORE_FIELD_LABELS.get(field_name, field_name)
            raw_val = params[field_name].asserted_value
            if field_name == "sealing_type":
                val: object = _SEALING_TYPE_DISPLAY.get(str(raw_val), str(raw_val))
            elif isinstance(raw_val, float) and raw_val == int(raw_val):
                val = int(raw_val)
            else:
                val = raw_val
            parts.append(f"{label}: {val}")

    assumed_parts: list[str] = []
    for field in missing_optional:
        if field in _ASSUMPTION_DEFAULTS:
            label = _CORE_FIELD_LABELS.get(field, field)
            assumed_parts.append(f"{label}: {_ASSUMPTION_DEFAULTS[field]}")

    params_text = "; ".join(parts) if parts else "keine"
    if assumed_parts:
        assumptions_text = "; ".join(assumed_parts)
        return (
            f"Betriebsparameter erfasst: {params_text}. "
            f"Ich setze folgende Annahmen: {assumptions_text}. "
            "Bitte korrigieren Sie, falls das nicht zutrifft — sonst fahre ich mit der technischen Analyse fort."
        )
    return (
        f"Betriebsparameter erfasst: {params_text}. "
        "Alle wesentlichen Parameter sind bekannt — ich fahre mit der technischen Analyse fort."
    )


def _reply_clarification(
    state: GraphState,
    strategy: ConversationStrategyContract | None = None,
) -> str:
    missing = list(
        dict.fromkeys(
            list(state.asserted.blocking_unknowns)
            + _preselection_blocker_fields(state)
        )
    )
    conflicts = state.asserted.conflict_flags
    primary_question = (
        str(strategy.primary_question).strip()
        if strategy and isinstance(strategy.primary_question, str) and strategy.primary_question.strip()
        else None
    )
    supporting_reason = (
        str(strategy.primary_question_reason or strategy.supporting_reason).strip()
        if strategy and isinstance((strategy.primary_question_reason or strategy.supporting_reason), str) and str(strategy.primary_question_reason or strategy.supporting_reason).strip()
        else None
    )
    response_mode = (
        str(strategy.response_mode)
        if strategy is not None and getattr(strategy, "response_mode", None)
        else "single_question"
    )
    turn_context = build_governed_turn_context(
        state=state,
        strategy=strategy or build_governed_conversation_strategy_contract(state, _STRUCTURED_CLARIFICATION),
        response_class=_STRUCTURED_CLARIFICATION,
    )

    # ── Fast-confirm path: 4+ core params confirmed, only optional fields missing ──
    # When enough technical context is present, assume the optional fields and
    # confirm instead of asking. Conflicts always bypass this shortcut.
    if not conflicts and missing and _confirmed_core_tech_count(state) >= 4:
        truly_optional = [f for f in missing if f in _OPTIONAL_CLARIFICATION_FIELDS]
        if truly_optional and len(truly_optional) == len(missing):
            return _reply_params_confirmed_with_assumptions(state, truly_optional)

    if conflicts:
        primary_conflict = _pick_priority_clarification_field(conflicts)
        meta = _clarification_field_meta(primary_conflict)
        question = primary_question or str(meta["conflict_question"])
        reason = supporting_reason or str(meta["reason"])
        if primary_conflict and response_mode == "single_question":
            return compose_clarification_reply(
                turn_context.model_copy(
                    update={"primary_question": question, "supporting_reason": reason}
                ),
                fallback_text=f"{question} {reason}",
            )
        fields = ", ".join(conflicts)
        return f"Ich sehe noch offene Widersprueche bei {fields}. Damit ich sauber eingrenzen kann, brauche ich hier eine kurze Klaerung."
    if missing:
        priority = select_clarification_priority(state, missing)
        primary_missing = priority.focus_key if priority is not None else _pick_priority_clarification_field(missing)
        meta = _clarification_field_meta(primary_missing)
        question = primary_question or (priority.question if priority is not None else str(meta["question"]))
        reason = supporting_reason or (priority.reason if priority is not None else str(meta["reason"]))
        if (primary_missing or priority is not None) and response_mode == "single_question":
            return compose_clarification_reply(
                turn_context.model_copy(
                    update={"primary_question": question, "supporting_reason": reason}
                ),
                fallback_text=f"{question} {reason}",
            )
        labels = [_CORE_FIELD_LABELS.get(f, f) for f in missing]
        field_list = ", ".join(labels)
        return (
            f"Ich brauche noch eine kurze Klaerung zu {field_list}, "
            "damit ich die Anwendung technisch sauber eingrenzen kann."
        )
    return (
        "Mit den Betriebsbedingungen kann ich die Anwendung sauber eingrenzen. "
        "Welches Medium, welcher Druck und welche Temperatur liegen an?"
    )


def _reply_state_update(state: GraphState) -> str:
    # Fast-confirm path: enough core params, only optional fields missing
    if _is_fast_confirm_applicable(state):
        missing = list(
            dict.fromkeys(
                list(state.asserted.blocking_unknowns)
                + _preselection_blocker_fields(state)
            )
        )
        optional_missing = [f for f in missing if f in _OPTIONAL_CLARIFICATION_FIELDS]
        return _reply_params_confirmed_with_assumptions(state, optional_missing)

    params = state.asserted.assertions
    missing = list(
        dict.fromkeys(
            list(state.asserted.blocking_unknowns)
            + _preselection_blocker_fields(state)
        )
    )
    parts = []
    for field_name in ("medium", "pressure_bar", "temperature_c", "shaft_diameter_mm", "speed_rpm"):
        if field_name in params:
            label = _CORE_FIELD_LABELS.get(field_name, field_name)
            raw_val = params[field_name].asserted_value
            # Normalize integer-like floats (6000.0 → 6000) for clean display
            if isinstance(raw_val, float) and raw_val == int(raw_val):
                val: object = int(raw_val)
            else:
                val = raw_val
            conf = params[field_name].confidence
            parts.append(f"{label}: {val} ({conf})")
    priority = select_clarification_priority(state, missing) if missing else None
    evidence_gaps = _blocking_evidence_gaps_for_preselection(state)
    if parts:
        params_text = "; ".join(parts)
        if evidence_gaps:
            return (
                f"Betriebsparameter erfasst: {params_text}. "
                "Die technische Basis ist berechnet, aber fuer eine belastbare quellenbasierte Vorauswahl fehlt noch Evidenz."
            )
        if priority is not None:
            return (
                f"Betriebsparameter erfasst: {params_text}. "
                f"Als naechstes brauche ich noch genau einen Kernwert: {priority.question}"
            )
        return (
            f"Betriebsparameter erfasst: {params_text}. "
            "Die technischen Grenzen werden geprüft."
        )
    if priority is not None:
        return f"Betriebsparameter wurden strukturiert erfasst. {priority.question}"
    if evidence_gaps:
        return "Betriebsparameter wurden strukturiert erfasst; fuer die quellenbasierte Einordnung bleibt ein Evidence-Gap offen."
    return "Betriebsparameter wurden strukturiert erfasst."


def _reply_recommendation(
    state: GraphState,
    strategy: ConversationStrategyContract | None = None,
) -> str:
    params = state.asserted.assertions
    gov = state.governance
    parts = []
    for field_name in ("medium", "pressure_bar", "temperature_c"):
        if field_name in params:
            label = _CORE_FIELD_LABELS.get(field_name, field_name)
            parts.append(f"{label}: {params[field_name].asserted_value}")

    header = "Technische Einengung auf Basis bestätigter Parameter"
    if parts:
        header += f" ({'; '.join(parts)})"
    header += "."

    calc_notes: list[str] = []
    for r in state.compute_results:
        calc_notes.extend(r.get("notes", []))

    validity = gov.validity_limits
    open_pts = prioritized_open_point_labels(state, gov.open_validation_points)
    evidence_supported = list(state.evidence.source_backed_findings)
    assumptions = list(state.evidence.assumption_based_findings)

    lines = [header]
    if evidence_supported:
        lines.append("Quellenbasiert gestützt: " + "; ".join(evidence_supported))
    if assumptions:
        lines.append("Annahmebasiert: " + "; ".join(assumptions))
    if calc_notes:
        lines.append("Berechnungshinweise: " + " | ".join(calc_notes))
    if validity:
        lines.append("Gültigkeitsgrenzen: " + "; ".join(validity))
    if open_pts:
        lines.append("Offene Prüfpunkte: " + "; ".join(open_pts))

    fallback = "\n".join(lines)
    turn_context = build_governed_turn_context(
        state=state,
        strategy=strategy or build_governed_conversation_strategy_contract(state, _TECHNICAL_PRESELECTION),
        response_class=_TECHNICAL_PRESELECTION,
    )
    return compose_result_reply(
        turn_context,
        fallback_text=fallback,
        facts_prefix="Bestaetigte Basis",
        open_points_prefix="Offene Pruefpunkte",
    )


def _reply_matching(
    state: GraphState,
    strategy: ConversationStrategyContract | None = None,
) -> str:
    selected = state.matching.selected_manufacturer_ref
    if selected is None:
        return "Es liegt noch kein belastbares Hersteller-Matching vor."

    notes = list(state.matching.matching_notes)
    line = (
        f"Passender Herstellerkandidat: {selected.manufacturer_name}. "
        "Die Auswahl basiert auf Requirement Class, Werkstofffamilie und aktuellem Gültigkeitsrahmen."
    )
    if notes:
        line += " " + notes[-1]
    turn_context = build_governed_turn_context(
        state=state,
        strategy=strategy or build_governed_conversation_strategy_contract(state, _CANDIDATE_SHORTLIST),
        response_class=_CANDIDATE_SHORTLIST,
    )
    return compose_result_reply(
        turn_context,
        fallback_text=line,
        facts_prefix="Technische Basis",
        open_points_prefix="Offene Pruefpunkte",
    )


def _reply_rfq_ready(
    state: GraphState,
    strategy: ConversationStrategyContract | None = None,
) -> str:
    selected = state.rfq.selected_manufacturer_ref
    manufacturer = selected.manufacturer_name if selected is not None else "dem ausgewählten Hersteller"
    req = state.rfq.requirement_class.class_id if state.rfq.requirement_class is not None else "ohne Requirement Class"
    line = (
        f"Die Anfragebasis ist inquiry-ready. "
        f"Requirement Class: {req}. "
        f"Herstellerbezug: {manufacturer}."
    )
    if state.dispatch.dispatch_ready:
        line += " Die spätere Partnerübergabe ist vorbereitet."
    turn_context = build_governed_turn_context(
        state=state,
        strategy=strategy or build_governed_conversation_strategy_contract(state, _INQUIRY_READY),
        response_class=_INQUIRY_READY,
    )
    return compose_result_reply(
        turn_context,
        fallback_text=line,
        facts_prefix="Anfragebasis",
        open_points_prefix="Restpunkte",
    )


# ---------------------------------------------------------------------------
# Inquiry confirmation (H1.2)
# ---------------------------------------------------------------------------

def build_inquiry_summary(state: GraphState) -> dict[str, Any]:
    """Build a compact, outward-safe inquiry summary for the confirmation interrupt.

    Returns only clean, derived values — no internal state artefacts (Invariant 8).
    """
    # Sealing type from normalized parameters
    norm_params = state.normalized.parameters
    sealing_type = None
    for key in ("sealing_type",):
        p = norm_params.get(key)
        if p is not None:
            sealing_type = getattr(p, "value", None) or (p.get("value") if isinstance(p, dict) else None)
            break

    # Material combination from decision.preselection
    preselection = state.decision.preselection or {}
    material_combination = preselection.get("material_combination") or preselection.get("material")

    # Key parameters
    key_parameters: dict[str, Any] = {}
    for field_key, label in (
        ("medium",            "medium"),
        ("temperature_max_c", "temperature_max_c"),
        ("pressure_max_bar",  "pressure_max_bar"),
        ("shaft_diameter_mm", "shaft_diameter_mm"),
    ):
        for alias in (field_key, field_key.replace("_max_c", "_c").replace("_max_bar", "_bar")):
            p = norm_params.get(alias)
            if p is not None:
                val = getattr(p, "value", None) or (p.get("value") if isinstance(p, dict) else None)
                key_parameters[label] = val
                break

    # Top manufacturer (first candidate with fit_score if available)
    top_manufacturer: dict[str, Any] | None = None
    if state.matching.selected_manufacturer_ref is not None:
        ref = state.matching.selected_manufacturer_ref
        top_manufacturer = {
            "name": ref.manufacturer_name,
            "fit_score": preselection.get("fit_score"),
        }
    elif state.matching.manufacturer_refs:
        ref = state.matching.manufacturer_refs[0]
        top_manufacturer = {"name": ref.manufacturer_name, "fit_score": None}

    # Open points
    open_points_count = len(state.governance.open_validation_points)

    return {
        "sealing_type": sealing_type,
        "material_combination": material_combination,
        "key_parameters": key_parameters,
        "top_manufacturer": top_manufacturer,
        "open_points_count": open_points_count,
        "pdf_ready": state.action_readiness.pdf_ready,
    }


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def output_contract_node(state: GraphState) -> GraphState:
    """Zone 7 — Assemble outward contract.

    Determines the response class from GovernanceState, assembles output_public
    (Invariant 8: no internal artefacts), and produces the visible reply.
    The visible reply is finalized by the canonical user-facing reply layer;
    this node only emits the deterministic governed reply basis.

    inquiry_ready path (H1.2):
      1. check_inquiry_admissibility — deterministic, no LLM
      2. Not admissible → downgrade to structured_clarification
      3. Admissible → interrupt() for explicit user confirmation
      4. confirmed=True → keep inquiry_ready, set action_readiness.inquiry_confirmed
      5. confirmed=False → downgrade to governed_state_update
    """
    response_class = _determine_response_class(state)

    # H1.2 — Inquiry admissibility + user confirmation gate
    if response_class == _INQUIRY_READY:
        admissibility = check_inquiry_admissibility(state)
        if not admissibility.admissible:
            # Downgrade: inquiry not ready, ask user for missing/assumed fields
            log.info(
                "[output_contract_node] inquiry not admissible — downgrading to structured_clarification. "
                "blocking_reasons=%s",
                admissibility.blocking_reasons,
            )
            response_class = _STRUCTURED_CLARIFICATION
            # Store blocking_reasons in DecisionState so frontend can surface them
            state = state.model_copy(update={
                "decision": state.decision.model_copy(
                    update={"blocking_reasons": list(admissibility.blocking_reasons)}
                )
            })
        else:
            # Admissible — require explicit user confirmation via interrupt()
            summary = build_inquiry_summary(state)
            try:
                # "state" mirrors the structured_clarification interrupt format
                # so callers can uniformly read state from any interrupt.
                # output_response_class is pre-filled so callers know the
                # tentative class even before confirmation is resolved.
                _pre_state = state.model_copy(
                    update={"output_response_class": _INQUIRY_READY}
                )
                confirmation = interrupt({
                    "type": "inquiry_confirmation",
                    "case_summary": summary,
                    "blocking_reasons": [],
                    "basis_hash": admissibility.basis_hash,
                    "state": _pre_state.model_dump(mode="python"),
                })
            except RuntimeError:
                # interrupt() not available (e.g. tests without checkpointer)
                confirmation = None

            if confirmation is not None:
                confirmed = bool(
                    confirmation.get("confirmed") if isinstance(confirmation, dict) else confirmation
                )
                if confirmed:
                    log.info(
                        "[output_contract_node] inquiry confirmed by user. basis_hash=%s",
                        admissibility.basis_hash,
                    )
                    state = state.model_copy(update={
                        "action_readiness": state.action_readiness.model_copy(
                            update={"inquiry_confirmed": True}
                        )
                    })
                else:
                    log.info("[output_contract_node] inquiry rejected by user — downgrading to governed_state_update")
                    response_class = _GOVERNED_STATE_UPDATE

    output_public = _build_output_public_base(state, response_class)
    reply = await _build_reply(state, response_class)
    output_public["message"] = reply

    log.debug(
        "[output_contract_node] response_class=%s gov_class=%s rfq_admissible=%s",
        response_class,
        state.governance.gov_class,
        state.governance.rfq_admissible,
    )

    result_state = state.model_copy(update={
        "output_response_class": response_class,
        "output_public":         output_public,
        "output_reply":          reply,
    })
    if response_class == _STRUCTURED_CLARIFICATION:
        try:
            resumed_message = interrupt(
                {
                    "kind": "structured_clarification",
                    "message": reply,
                    "response_class": response_class,
                    "output_public": output_public,
                    "state": result_state.model_dump(mode="python"),
                }
            )
        except RuntimeError:
            return result_state
        resumed_text = str(resumed_message or "").strip()
        if resumed_text:
            return Command(
                update={"pending_message": resumed_text},
                goto="intake_observe",
            )
    return result_state
