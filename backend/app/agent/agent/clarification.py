from __future__ import annotations

from typing import Any, Dict, List, Optional


STRUCTURED_REQUIRED_CORE_PARAMS: tuple[str, ...] = (
    "medium",
    "pressure",
    "temperature",
)
STRUCTURED_SUPPLEMENTARY_PARAMS: tuple[str, ...] = (
    "shaft_diameter",
    "shaft_speed",
)
STRUCTURED_CONTEXT_PARAMS: tuple[str, ...] = (
    "dynamic_type",
)

_CLARIFICATION_FIELD_META: dict[str, dict[str, Any]] = {
    "medium": {
        "label": "Medium",
        "question_label": "Dichtungsmedium",
        "priority_bucket": 0,
        "priority_order": 0,
        "question": "Welches Medium soll abgedichtet werden?",
    },
    "pressure": {
        "label": "Betriebsdruck (bar)",
        "question_label": "Betriebsdruck",
        "priority_bucket": 0,
        "priority_order": 1,
        "question": "Wie hoch ist der Betriebsdruck in bar?",
    },
    "temperature": {
        "label": "Betriebstemperatur (°C)",
        "question_label": "Betriebstemperatur",
        "priority_bucket": 0,
        "priority_order": 2,
        "question": "Wie hoch ist die Betriebstemperatur in °C?",
    },
    "shaft_diameter": {
        "label": "Wellendurchmesser (mm)",
        "question_label": "Wellendurchmesser",
        "priority_bucket": 1,
        "priority_order": 0,
        "question": "Wie groß ist der Wellendurchmesser in mm?",
    },
    "shaft_speed": {
        "label": "Drehzahl (rpm)",
        "question_label": "Drehzahl",
        "priority_bucket": 1,
        "priority_order": 1,
        "question": "Wie hoch ist die Drehzahl in rpm?",
    },
    "dynamic_type": {
        "label": "Bewegungsart",
        "question_label": "Bewegungsart",
        "priority_bucket": 2,
        "priority_order": 0,
        "question": "Handelt es sich um eine rotierende oder lineare Anwendung?",
    },
}

CLARIFICATION_PAUSED_PREFIX = "Weitere Klärung ist derzeit nicht der nächste erforderliche Schritt."
NEXT_QUESTION_PREFIX = "Nächste Klärungsfrage:"


def _build_missing_inputs_text(
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> str:
    wp = working_profile or {}
    as_ = asserted_state or {}
    oc = as_.get("operating_conditions") or {}

    medium_asserted = (as_.get("medium_profile") or {}).get("name")
    medium_wp = wp.get("medium")
    pressure_asserted = oc.get("pressure")
    pressure_wp = wp.get("pressure") or wp.get("pressure_bar")
    temp_asserted = oc.get("temperature")
    temp_wp = wp.get("temperature") or wp.get("temperature_max_c")

    missing: List[str] = []
    pending: List[str] = []

    if not medium_asserted:
        if medium_wp:
            pending.append(f"Medium ({medium_wp} — noch nicht bestätigt)")
        else:
            missing.append("Medium (z. B. Wasser, Öl, Kraftstoff)")

    if not pressure_asserted:
        if pressure_wp is not None:
            pending.append(f"Betriebsdruck ({pressure_wp} bar — noch nicht bestätigt)")
        else:
            missing.append("Betriebsdruck (bar)")

    if not temp_asserted:
        if temp_wp is not None:
            pending.append(f"Betriebstemperatur ({temp_wp} °C — noch nicht bestätigt)")
        else:
            missing.append("Betriebstemperatur (°C)")

    parts: List[str] = []
    if missing:
        missing_list = "\n".join(f"- {item}" for item in missing)
        parts.append(f"Für eine Auslegungsempfehlung benötige ich noch:\n{missing_list}")
    if pending:
        pending_list = "\n".join(f"- {item}" for item in pending)
        parts.append(f"Ausstehende Bestätigung:\n{pending_list}")
    if not parts:
        return "Lassen Sie uns die Betriebsbedingungen gemeinsam eingrenzen — das ist der nächste sinnvolle Schritt."
    parts.append("Lassen Sie uns diese Punkte gemeinsam eingrenzen.")
    return "\n\n".join(parts)


def _missing_core_input_items(asserted_state: Optional[Dict[str, Any]]) -> list[str]:
    asserted = asserted_state or {}
    operating = asserted.get("operating_conditions") or {}
    missing: list[str] = []
    if not (asserted.get("medium_profile") or {}).get("name"):
        missing.append("medium")
    if operating.get("pressure") is None:
        missing.append("pressure")
    if operating.get("temperature") is None:
        missing.append("temperature")
    return missing


def _field_is_known_or_pending(
    field_key: str,
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> bool:
    asserted = asserted_state or {}
    working = working_profile or {}
    operating = asserted.get("operating_conditions") or {}
    machine = asserted.get("machine_profile") or {}

    if field_key == "medium":
        return bool((asserted.get("medium_profile") or {}).get("name") or working.get("medium"))
    if field_key == "pressure":
        return operating.get("pressure") is not None or working.get("pressure") is not None or working.get("pressure_bar") is not None
    if field_key == "temperature":
        return operating.get("temperature") is not None or working.get("temperature") is not None or working.get("temperature_max_c") is not None
    if field_key == "shaft_diameter":
        return machine.get("shaft_diameter_mm") is not None or working.get("shaft_diameter_mm") is not None
    if field_key == "shaft_speed":
        return (
            machine.get("shaft_speed_rpm") is not None
            or working.get("speed") is not None
            or working.get("speed_rpm") is not None
            or working.get("rpm") is not None
        )
    if field_key == "dynamic_type":
        return bool(operating.get("dynamic_type") or working.get("dynamic_type"))
    return False


def prioritize_missing_inputs(
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> list[str]:
    candidates = (
        list(STRUCTURED_REQUIRED_CORE_PARAMS)
        + list(STRUCTURED_SUPPLEMENTARY_PARAMS)
        + list(STRUCTURED_CONTEXT_PARAMS)
    )
    missing = [
        key for key in candidates
        if not _field_is_known_or_pending(key, asserted_state, working_profile)
    ]
    return sorted(
        missing,
        key=lambda key: (
            int(_CLARIFICATION_FIELD_META[key]["priority_bucket"]),
            int(_CLARIFICATION_FIELD_META[key]["priority_order"]),
            key,
        ),
    )


def build_clarification_projection(
    *,
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    evidence_provenance_projection: Optional[Dict[str, Any]] = None,
    conflict_status_projection: Optional[Dict[str, Any]] = None,
    parameter_integrity_projection: Optional[Dict[str, Any]] = None,
    domain_scope_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from app.agent.state.projections_extended import _build_domain_scope_note

    prioritized_missing = prioritize_missing_inputs(asserted_state, working_profile)
    review_status = (review_escalation_projection or {}).get("status")
    evidence_status = str((evidence_provenance_projection or {}).get("status") or "no_evidence")
    provenance_refs = list((evidence_provenance_projection or {}).get("provenance_refs") or [])
    conflict_status = str((conflict_status_projection or {}).get("status") or "no_conflict")
    affected_keys = list((conflict_status_projection or {}).get("affected_keys") or [])
    integrity_status = str((parameter_integrity_projection or {}).get("integrity_status") or "normalized_ok")
    integrity_blocking_keys = list((parameter_integrity_projection or {}).get("blocking_keys") or [])
    domain_scope_status = str((domain_scope_projection or {}).get("status") or "in_domain_scope")

    if domain_scope_status in {"out_of_domain_scope", "escalation_required"}:
        return {
            "missing_items": prioritized_missing,
            "next_question_key": None,
            "next_question_label": None,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": affected_keys,
            "clarification_still_meaningful": False,
            "reason_if_not": _build_domain_scope_note(domain_scope_projection),
        }

    if integrity_status == "unusable_until_clarified":
        next_key = next((key for key in integrity_blocking_keys if key in _CLARIFICATION_FIELD_META), None)
        return {
            "missing_items": prioritized_missing,
            "next_question_key": next_key,
            "next_question_label": str(_CLARIFICATION_FIELD_META[next_key]["question_label"]) if next_key else None,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "clarification_still_meaningful": bool(next_key),
            "reason_if_not": "" if next_key else "Parameterintegrität erfordert manuelle Klärung.",
        }

    if review_status in {"review_pending", "ambiguous_but_reviewable", "escalation_needed"}:
        return {
            "missing_items": prioritized_missing,
            "next_question_key": None,
            "next_question_label": None,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": affected_keys,
            "clarification_still_meaningful": False,
            "reason_if_not": "Review oder Eskalation ist bereits der nächste deterministische Schritt.",
        }
    if review_status in {"withheld_no_evidence", "withheld_demo_data"}:
        return {
            "missing_items": prioritized_missing,
            "next_question_key": None,
            "next_question_label": None,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": affected_keys,
            "clarification_still_meaningful": False,
            "reason_if_not": str((review_escalation_projection or {}).get("reason") or ""),
        }
    if (conflict_status_projection or {}).get("conflict_still_open"):
        next_key = next((key for key in affected_keys if key in _CLARIFICATION_FIELD_META), None)
        return {
            "missing_items": prioritized_missing,
            "next_question_key": next_key,
            "next_question_label": str(_CLARIFICATION_FIELD_META[next_key]["question_label"]) if next_key else None,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": affected_keys,
            "clarification_still_meaningful": bool(next_key),
            "reason_if_not": "" if next_key else "Offener Konflikt erfordert manuelle Klärung.",
        }
    if not prioritized_missing:
        return {
            "missing_items": [],
            "next_question_key": None,
            "next_question_label": None,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": affected_keys,
            "clarification_still_meaningful": False,
            "reason_if_not": "Keine weitere deterministische Rückfrage erforderlich.",
        }

    next_key = prioritized_missing[0]
    return {
        "missing_items": prioritized_missing,
        "next_question_key": next_key,
        "next_question_label": str(_CLARIFICATION_FIELD_META[next_key]["question_label"]),
        "evidence_status": evidence_status,
        "provenance_refs": provenance_refs,
        "conflict_status": conflict_status,
        "integrity_status": integrity_status,
        "affected_keys": affected_keys,
        "clarification_still_meaningful": True,
        "reason_if_not": "",
    }


def build_next_clarification_question(
    clarification_projection: Optional[Dict[str, Any]],
) -> Optional[str]:
    projection = clarification_projection or {}
    if not projection.get("clarification_still_meaningful"):
        return None
    next_key = projection.get("next_question_key")
    if not isinstance(next_key, str) or next_key not in _CLARIFICATION_FIELD_META:
        return None
    if projection.get("integrity_status") == "unusable_until_clarified":
        integrity_questions = {
            "pressure": "Welcher Betriebsdruck ist korrekt und in welcher Einheit?",
            "temperature": "Welche Betriebstemperatur ist korrekt und in welcher Einheit?",
            "medium": "Welches Medium ist fachlich korrekt bestätigt?",
        }
        return integrity_questions.get(next_key) or str(_CLARIFICATION_FIELD_META[next_key]["question"])
    if projection.get("conflict_status") in {"conflicting_values", "unresolved_conflict"}:
        conflict_questions = {
            "medium": "Welches Medium ist korrekt?",
            "pressure": "Welcher Betriebsdruck ist korrekt?",
            "temperature": "Welche Betriebstemperatur ist korrekt?",
            "shaft_diameter": "Welcher Wellendurchmesser ist korrekt?",
            "shaft_speed": "Welche Drehzahl ist korrekt?",
            "dynamic_type": "Welche Bewegungsart ist korrekt?",
        }
        return conflict_questions.get(next_key)
    return str(_CLARIFICATION_FIELD_META[next_key]["question"])


def _build_missing_data_reply(
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
) -> str:
    base_text = _build_missing_inputs_text(asserted_state, working_profile)
    next_question = build_next_clarification_question(clarification_projection)
    if next_question:
        return f"{base_text}\n\n{NEXT_QUESTION_PREFIX} {next_question}"
    if clarification_projection and not clarification_projection.get("clarification_still_meaningful"):
        reason = str(clarification_projection.get("reason_if_not") or "").strip()
        if reason:
            return f"{base_text}\n\n{CLARIFICATION_PAUSED_PREFIX} {reason}"
    return base_text
