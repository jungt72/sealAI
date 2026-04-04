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
    - No class may be skipped (Blaupause: conversational_answer → … → rfq_ready).

Response class selection (deterministic from GovernanceState.gov_class):

    rfq.rfq_ready is True            → rfq_ready
        (bounded RFQ handover basis is available)
    matching.status indicates match  → manufacturer_match_result
        (bounded manufacturer candidate is available)
    gov_class is None / D           → structured_clarification
        (nothing useful asserted — ask for core parameters)
    gov_class C                     → structured_clarification
        (cycle exhausted or unresolvable conflict)
    gov_class B                     → structured_clarification
        (blocking unknowns — ask for the missing fields)
    gov_class A + compute_results   → governed_recommendation
        (full technical specification with calc output)
    gov_class A + no compute        → governed_state_update
        (all core parameters confirmed — state visible, no calc needed)

    Phase G Block 1 may now produce manufacturer_match_result.
    rfq_ready remains reserved for a later phase.

output_public shape (Invariant 8 — no internal artefacts):
    response_class      — one of the 6 outward classes
    gov_class           — "A"|"B"|"C"|"D" (derived summary, not raw object)
    rfq_admissible      — bool
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
import os
from typing import Any

from app.agent.graph import GraphState
from app.agent.runtime.clarification_priority import prioritized_open_point_labels, select_clarification_priority
from app.agent.runtime.reply_composition import compose_clarification_reply, compose_result_reply
from app.agent.runtime.turn_context import build_governed_turn_context
from app.agent.state.models import ConversationStrategyContract

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversational humanizer — wraps deterministic template text with one LLM
# call that adds natural engineer tone while preserving all factual content.
# Disable via SEALAI_HUMANIZE_REPLY=false for testing/debugging.
# ---------------------------------------------------------------------------

_HUMANIZE_SYSTEM_PROMPT = """Du bist SealAI — ein erfahrener Dichtungsingenieur mit 20+ Jahren Praxis.
Du führst ein Beratungsgespräch. Du denkst und antwortest wie ein Mensch, nicht wie ein Formular.

DEINE AUFGABE:
Du bekommst eine strukturierte Systemnachricht (was technisch zu sagen ist)
und formulierst daraus eine natürliche, menschliche Antwort.

KOMMUNIKATIONSREGELN:
1. Gehe ZUERST auf das ein, was der Kunde gerade gesagt hat — zeige dass du es gehört hast
2. Wenn neue Werte genannt wurden: bestätige sie kurz und positiv
3. Füge wenn sinnvoll eine kurze fachliche Einschätzung ein (1 Satz)
4. Stelle genau EINE Folgefrage — die wichtigste offene
5. Erkläre in einem Halbsatz WARUM du diese Information brauchst
6. NIEMALS nach bereits bekannten Parametern fragen
7. Kein Formularjargon. Kein "Ich habe folgende Parameter erfasst:". Natürlich sprechen wie ein Kollege.
8. Maximale Länge: 4 Sätze

TON: Kollegial, kompetent, direkt. Deutsche Sprache."""


async def _humanize_reply(
    *,
    mechanical_reply: str,
    state: GraphState,
    response_class: str,
) -> str:
    """Transform a deterministic template reply into natural conversational text.

    The mechanical_reply is used as structured input (what to say), not as
    visible output. The LLM reformulates it in engineer voice.
    On any failure, falls back to mechanical_reply (fail-open).
    """
    try:
        from langchain_openai import ChatOpenAI  # local import — not available in all envs

        # Build conversation history (last 10 turns, exclude current)
        messages = list(state.conversation_messages or [])
        history_lines: list[str] = []
        for msg in messages[:-1]:
            role = "SealAI" if msg.role == "assistant" else "Kunde"
            history_lines.append(f"{role}: {msg.content.strip()}")
        history_text = "\n".join(history_lines) if history_lines else "Erstes Gespräch."

        # Current user message
        current_msg = ""
        if messages and messages[-1].role == "user":
            current_msg = messages[-1].content.strip()

        # Known parameters — must not be asked again
        assertions = state.asserted.assertions if state.asserted else {}
        _param_labels = {
            "medium": "Medium",
            "temperature_c": "Temperatur",
            "pressure_bar": "Druck",
            "shaft_diameter_mm": "Wellen-Ø",
            "speed_rpm": "Drehzahl",
            "motion_type": "Bewegungsart",
            "installation": "Einbau",
        }
        known = [
            f"{lbl}: {assertions[k].asserted_value}"
            for k, lbl in _param_labels.items()
            if k in assertions
        ]
        known_text = ", ".join(known) if known else "Noch keine Parameter."

        user_prompt = (
            f"BISHERIGER GESPRÄCHSVERLAUF:\n{history_text}\n\n"
            f"LETZTE NACHRICHT DES KUNDEN:\n{current_msg}\n\n"
            f"BEREITS BEKANNTE PARAMETER (NICHT ERNEUT FRAGEN):\n{known_text}\n\n"
            f"STRUKTURIERTE VORGABE (was inhaltlich gesagt werden soll):\n{mechanical_reply}\n\n"
            "Formuliere jetzt eine natürliche Antwort basierend auf der strukturierten Vorgabe.\n"
            "Antworte NUR mit dem Text der Antwort — kein Präfix, keine Erklärung."
        )

        model_id = os.getenv("SEALAI_REPLY_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=model_id, temperature=0.4, max_tokens=300)
        response = await llm.ainvoke([
            {"role": "system", "content": _HUMANIZE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        humanized = str(response.content).strip()
        if len(humanized) < 10:
            return mechanical_reply
        return humanized
    except Exception as exc:
        log.warning("[output_contract_node] _humanize_reply failed (%s) — using mechanical reply", exc)
        return mechanical_reply

# Outward response classes (Blaupause V1.1)
_STRUCTURED_CLARIFICATION = "structured_clarification"
_GOVERNED_STATE_UPDATE     = "governed_state_update"
_GOVERNED_RECOMMENDATION   = "governed_recommendation"
_MANUFACTURER_MATCH_RESULT = "manufacturer_match_result"
_RFQ_READY                 = "rfq_ready"

# Core fields the system always asks for when missing
_CORE_FIELD_LABELS: dict[str, str] = {
    "medium":        "Medium (Fluid/Gas)",
    "pressure_bar":  "Betriebsdruck [bar]",
    "temperature_c": "Betriebstemperatur [°C]",
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
}


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
    missing = state.asserted.blocking_unknowns
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
    if response_class == _MANUFACTURER_MATCH_RESULT:
        return ConversationStrategyContract(
            conversation_phase="matching",
            turn_goal="explain_matching_result",
            response_mode="result_summary",
        )
    if response_class == _RFQ_READY:
        return ConversationStrategyContract(
            conversation_phase="rfq_handover",
            turn_goal="prepare_handover",
            response_mode="handover_summary",
        )
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
    if state.rfq.rfq_ready and state.rfq.status == "rfq_ready":
        return _RFQ_READY
    if state.matching.status == "matched_primary_candidate":
        return _MANUFACTURER_MATCH_RESULT

    gov_class = state.governance.gov_class

    if gov_class is None or gov_class == "D":
        return _STRUCTURED_CLARIFICATION
    if gov_class == "C":
        return _STRUCTURED_CLARIFICATION
    if gov_class == "B":
        return _STRUCTURED_CLARIFICATION
    # gov_class == "A"
    if state.compute_results or _is_recommendation_ready(state):
        return _GOVERNED_RECOMMENDATION
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
        "rfq_admissible":  state.governance.rfq_admissible,
        "parameters":      _parameters_public(state),
        "missing_fields":  list(state.asserted.blocking_unknowns),
        "conflicts":       list(state.asserted.conflict_flags),
        "validity_notes":  list(state.governance.validity_limits),
        "open_points":     prioritized_open_point_labels(state, state.governance.open_validation_points),
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
        "rfq_ready": state.rfq.rfq_ready,
        "rfq_admissible": state.rfq.rfq_admissible,
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

async def _build_reply(state: GraphState, response_class: str) -> str:
    """Generate deterministic template reply text, then humanize via LLM.

    Step 1 (deterministic): build a structured mechanical reply from state.
    Step 2 (LLM, optional): pass it through _humanize_reply() for natural tone.
    Step 2 can be disabled via SEALAI_HUMANIZE_REPLY=false.
    """
    strategy = build_governed_conversation_strategy_contract(state, response_class)
    if response_class == _STRUCTURED_CLARIFICATION:
        mechanical = _reply_clarification(state, strategy)
    elif response_class == _RFQ_READY:
        mechanical = _reply_rfq_ready(state, strategy)
    elif response_class == _MANUFACTURER_MATCH_RESULT:
        mechanical = _reply_matching(state, strategy)
    elif response_class == _GOVERNED_STATE_UPDATE:
        mechanical = _reply_state_update(state)
    elif response_class == _GOVERNED_RECOMMENDATION:
        mechanical = _reply_recommendation(state, strategy)
    else:
        mechanical = "Bitte geben Sie die technischen Parameter Ihrer Anwendung an."

    if os.getenv("SEALAI_HUMANIZE_REPLY", "true").lower() == "true":
        return await _humanize_reply(
            mechanical_reply=mechanical,
            state=state,
            response_class=response_class,
        )
    return mechanical


def _reply_clarification(
    state: GraphState,
    strategy: ConversationStrategyContract | None = None,
) -> str:
    missing = state.asserted.blocking_unknowns
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
    params = state.asserted.assertions
    parts = []
    for field_name in ("medium", "pressure_bar", "temperature_c"):
        if field_name in params:
            label = _CORE_FIELD_LABELS.get(field_name, field_name)
            val = params[field_name].asserted_value
            conf = params[field_name].confidence
            parts.append(f"{label}: {val} ({conf})")
    if parts:
        params_text = "; ".join(parts)
        return (
            f"Betriebsparameter erfasst: {params_text}. "
            "Die technischen Grenzen werden geprüft."
        )
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

    lines = [header]
    if calc_notes:
        lines.append("Berechnungshinweise: " + " | ".join(calc_notes))
    if validity:
        lines.append("Gültigkeitsgrenzen: " + "; ".join(validity))
    if open_pts:
        lines.append("Offene Prüfpunkte: " + "; ".join(open_pts))

    fallback = "\n".join(lines)
    turn_context = build_governed_turn_context(
        state=state,
        strategy=strategy or build_governed_conversation_strategy_contract(state, _GOVERNED_RECOMMENDATION),
        response_class=_GOVERNED_RECOMMENDATION,
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
        strategy=strategy or build_governed_conversation_strategy_contract(state, _MANUFACTURER_MATCH_RESULT),
        response_class=_MANUFACTURER_MATCH_RESULT,
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
        f"Die Anfragebasis ist RFQ-ready. "
        f"Requirement Class: {req}. "
        f"Herstellerbezug: {manufacturer}."
    )
    if state.dispatch.dispatch_ready:
        line += " Die spätere Partnerübergabe ist vorbereitet."
    turn_context = build_governed_turn_context(
        state=state,
        strategy=strategy or build_governed_conversation_strategy_contract(state, _RFQ_READY),
        response_class=_RFQ_READY,
    )
    return compose_result_reply(
        turn_context,
        fallback_text=line,
        facts_prefix="Anfragebasis",
        open_points_prefix="Restpunkte",
    )


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def output_contract_node(state: GraphState) -> GraphState:
    """Zone 7 — Assemble outward contract.

    Determines the response class from GovernanceState, assembles output_public
    (Invariant 8: no internal artefacts), and produces the visible reply.
    One optional LLM call (_humanize_reply) adds conversational tone;
    all factual content is determined deterministically before that call.
    """
    response_class = _determine_response_class(state)
    output_public = _build_output_public_base(state, response_class)
    reply = await _build_reply(state, response_class)
    output_public["message"] = reply

    log.debug(
        "[output_contract_node] response_class=%s gov_class=%s rfq_admissible=%s humanize=%s",
        response_class,
        state.governance.gov_class,
        state.governance.rfq_admissible,
        os.getenv("SEALAI_HUMANIZE_REPLY", "true"),
    )

    return state.model_copy(update={
        "output_response_class": response_class,
        "output_public":         output_public,
        "output_reply":          reply,
    })
