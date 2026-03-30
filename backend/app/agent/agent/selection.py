import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional
from app.agent.domain.material import MaterialPhysicalProfile, MaterialValidator, normalize_fact_card_evidence
from app.agent.domain.parameters import PhysicalParameter
from app.agent.agent.boundaries import build_boundary_block
from app.agent.domain.normalization import extract_parameters as norm_extract
from app.agent.domain.rwdr_calc import calculate_rwdr, RwdrCalcInput


_MATERIAL_PATTERN = re.compile(r"\b(PTFE|NBR|FKM|EPDM|SILIKON)\b", re.I)
_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)

# ---------------------------------------------------------------------------
# Canonical required parameters for governed RWDR structured output.
#
# STRUCTURED_REQUIRED_CORE_PARAMS — absolute minimum; all three must be present
#   in asserted_state before a governed recommendation can proceed.
#   interaction_policy._missing_critical_params() mirrors these names exactly.
#
# STRUCTURED_SUPPLEMENTARY_PARAMS — extend the analysis when confirmed;
#   their absence does not block governance but limits calc depth (Dn, v_s, pv).
# ---------------------------------------------------------------------------
STRUCTURED_REQUIRED_CORE_PARAMS: tuple[str, ...] = (
    "medium",       # Dichtungsmedium — asserted.medium_profile.name
    "pressure",     # Betriebsdruck [bar] — asserted.operating_conditions.pressure
    "temperature",  # Betriebstemperatur [°C] — asserted.operating_conditions.temperature
)
STRUCTURED_SUPPLEMENTARY_PARAMS: tuple[str, ...] = (
    "shaft_diameter",  # Wellendurchmesser [mm] — for v_s / Dn / pv calc (DIN 3760)
    "shaft_speed",     # Wellendrehzahl [rpm] — for v_s / Dn calc
)
STRUCTURED_CONTEXT_PARAMS: tuple[str, ...] = (
    "dynamic_type",    # Bewegungsart — rotary/linear context
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

SAFEGUARDED_WITHHELD_REPLY = "Eine Auslegungsempfehlung kann auf Basis der vorliegenden Angaben derzeit nicht ausgegeben werden."
NO_CANDIDATES_REPLY = "Für diese Anfrage konnten keine technisch geeigneten Referenzdaten gefunden werden."
NO_VIABLE_CANDIDATES_REPLY = "Die vorliegenden Referenzkandidaten erfüllen die technischen Anforderungen nicht vollständig. Eine gebundene Auslegung ist derzeit nicht möglich."


def _build_missing_inputs_text(
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a helpful German text listing missing and pending critical parameters.

    Phase 0D.5: Three-tier parameter status — honest about what is confirmed vs pending.

    - asserted_state values: confirmed / binding (not listed as missing or pending)
    - working_profile-only values: pending confirmation (listed separately, not as confirmed)
    - Neither source: missing (listed as required)

    This prevents the false impression that a heuristically-extracted value (working_profile)
    has the same status as a formally-confirmed value (asserted_state).
    """
    wp = working_profile or {}
    as_ = asserted_state or {}
    oc = as_.get("operating_conditions") or {}

    # Evaluate each parameter: asserted → confirmed; wp-only → pending; neither → missing
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
        items = "\n".join(f"- {m}" for m in missing)
        parts.append(f"Das hilft schon deutlich. Der nächste wichtige Punkt:\n{items}")
    if pending:
        items = "\n".join(f"- {p}" for p in pending)
        parts.append(f"Ausstehende Bestätigung (erfasst, aber noch nicht freigegeben):\n{items}")
    if not parts:
        return "Lassen Sie uns die Betriebsbedingungen gemeinsam eingrenzen — das ist der nächste sinnvolle Schritt."
    return "\n\n".join(parts)
NEUTRAL_SCOPE_REPLY = (
    "Technischer Auslegungsbereich vorbereitet. Die Freigabe bleibt an die vollständige "
    "technische Überprüfung und dokumentierte Offene Punkte gebunden."
)
MANUFACTURER_VALIDATION_REPLY = (
    "Technischer Eignungsraum vorbereitet. Hersteller-Validierung ist erforderlich; "
    "keine Material- oder Compound-Freigabe wird ausgegeben."
)
PRECHECK_ONLY_REPLY = (
    "Technischer Vorprüfstand erreicht. Weitere fachliche Klärung ist erforderlich."
)
AMBIGUOUS_CANDIDATE_REPLY = (
    "Es liegen mehrere technisch tragfähige Kandidaten vor. "
    "Eine eindeutige Auslegungsempfehlung kann derzeit nicht ausgegeben werden."
)
# Phase 1B PATCH 3 — per-readiness-status reply constants
REVIEW_PENDING_REPLY = (
    "Technische Vorbeurteilung liegt vor. "
    "Freigabe ist zurückgestellt — ein manueller Experten-Review ist erforderlich."
)
ESCALATION_NEEDED_REPLY = (
    "Der Fall erfordert eine fachliche Eskalation. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
EVIDENCE_MISSING_REPLY = (
    "Die technischen Betriebsparameter sind erfasst. "
    "Qualifizierte technische Referenzdaten für diese Anfrage sind derzeit nicht verfügbar — "
    "eine Auslegungsempfehlung ohne qualifizierte Referenzbasis ist nicht möglich."
)
DEMO_DATA_QUARANTINE_REPLY = (
    "Die Anfrage enthält synthetische Referenzdaten. "
    "Eine Auslegungsempfehlung ist zurückgestellt, bis echte qualifizierte Referenzdaten vorliegen."
)
INVARIANT_BLOCKED_REPLY = (
    "Die interne Zustandsprüfung hat einen Konsistenzfehler festgestellt. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
CLARIFICATION_PAUSED_PREFIX = "Weitere Klärung ist derzeit nicht der nächste erforderliche Schritt."
NEXT_QUESTION_PREFIX = "Nächste Klärungsfrage:"
CORRECTION_APPLIED_PREFIX = "Aktualisierte Angabe übernommen:"
INTEGRITY_WARNING_PREFIX = "Parameter verwendbar mit Warnhinweis:"
INTEGRITY_UNUSABLE_REPLY = (
    "Parameterangaben liegen vor, sind aber fachlich noch nicht sauber verwendbar. "
    "Eine Auslegungsempfehlung kann derzeit nicht ausgegeben werden."
)


def _resolve_runtime_dispatch_source(canonical_case_state: Dict[str, Any]) -> Dict[str, Any]:
    canonical_state = dict(canonical_case_state or {})
    dispatch_intent = dict(canonical_state.get("dispatch_intent") or {})
    if dispatch_intent:
        return dispatch_intent
    rfq_state = dict(canonical_state.get("rfq_state") or {})
    return dict(rfq_state.get("rfq_dispatch") or {})
DOMAIN_WARNING_PREFIX = "Fachlicher Grenzfall im aktuellen Anwendungsbereich:"
OUT_OF_DOMAIN_REPLY = (
    "Der Fall liegt außerhalb des fachlich abgedeckten Anwendungsbereichs. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
THRESHOLD_ESCALATION_REPLY = (
    "Technische Grenzwerte erfordern eine fachliche Eskalation. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)
UNRESOLVED_CONFLICT_REPLY = (
    "Widersprüchliche Parameterangaben liegen vor. "
    "Eine Auslegungsempfehlung kann aus dem aktuellen Zustand nicht ausgegeben werden."
)


def _pick_material_family(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("material_family", "material", "family"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    match = _MATERIAL_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    return None


def _pick_filler_hint(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("filler_hint", "filler", "fill"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    match = _FILLER_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _pick_grade_name(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("grade_name", "grade", "compound_code", "compound"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    match = _GRADE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _pick_manufacturer(metadata: Dict[str, Any]) -> Optional[str]:
    for key in ("manufacturer_name", "manufacturer", "brand"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _candidate_kind(
    family: str,
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> str:
    if manufacturer_name and grade_name:
        return "manufacturer_grade"
    if grade_name:
        return "grade"
    if filler_hint:
        return "filled_family"
    return "family"


def _candidate_id(
    family: str,
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> str:
    parts = [
        family.lower(),
        (filler_hint or "").lower(),
        (grade_name or "").lower(),
        (manufacturer_name or "").lower(),
    ]
    return "::".join(part for part in parts if part)


def has_confirmed_core_params(asserted_state: Optional[Dict[str, Any]]) -> bool:
    """True if ALL three STRUCTURED_REQUIRED_CORE_PARAMS are present in asserted_state.

    Phase 1A PATCH 4 — confirmed layer:
    asserted_state is the only source of truth for confirmed parameters.
    working_profile values are pending, not confirmed, and must never enter here.
    """
    as_ = asserted_state or {}
    oc = as_.get("operating_conditions") or {}
    return bool(
        (as_.get("medium_profile") or {}).get("name")
        and oc.get("pressure") is not None
        and oc.get("temperature") is not None
    )


def is_sufficient_for_structured(asserted_state: Optional[Dict[str, Any]]) -> bool:
    """True when asserted_state has enough confirmed params to enter the governed structured path.

    Phase 1A PATCH 4 — sufficient layer:
    "Sufficient" means the minimum required inputs are confirmed so that
    governance evaluation and candidate classification can proceed meaningfully.
    This is a pre-condition check — passing it does NOT imply output will be released.
    """
    return has_confirmed_core_params(asserted_state)


def is_releasable(
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
) -> bool:
    """True when BOTH sufficient params are confirmed AND governance projection allows release.

    Phase 1A PATCH 4 — releasable layer:
    Releasable = sufficient_for_structured AND _governance_projection_blocks_output() == False.
    These two gates are intentionally separate:
    - sufficient_for_structured: data completeness (inputs)
    - governance projection: policy completeness (rules, review, scope)
    """
    if not is_sufficient_for_structured(asserted_state):
        return False
    return not _governance_projection_blocks_output(governance_state or {})


# ---------------------------------------------------------------------------
# Phase 1B PATCH 1 — Central Governed Output Readiness
# ---------------------------------------------------------------------------

OutputReadinessStatus = Literal[
    "releasable",
    "insufficient_inputs",
    "governance_blocked",
    "review_pending",
    "evidence_missing",
    "demo_data_quarantine",
    "conflict_unresolved",
    "integrity_unusable",
    "domain_scope_blocked",
]

EvidenceProvenanceStatus = Literal[
    "no_evidence",
    "thin_evidence",
    "grounded_evidence",
]

ReviewEscalationStatus = Literal[
    "releasable",
    "review_pending",
    "escalation_needed",
    "ambiguous_but_reviewable",
    "withheld_no_evidence",
    "withheld_demo_data",
    "withheld_missing_core_inputs",
]


@dataclass(frozen=True)
class OutputReadinessDecision:
    """Central governed-output readiness verdict.

    Phase 1B PATCH 1: single place that combines all blocking conditions.
    Consumers should check .releasable first; branch on .status for the specific reason.
    blocking_reason is a deterministic one-liner — never LLM-generated.
    """

    releasable: bool
    status: OutputReadinessStatus
    blocking_reason: str


def evaluate_output_readiness(
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    *,
    review_state: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    demo_data_present: bool = False,
    conflict_status_projection: Optional[Dict[str, Any]] = None,
    parameter_integrity_projection: Optional[Dict[str, Any]] = None,
    domain_scope_projection: Optional[Dict[str, Any]] = None,
) -> OutputReadinessDecision:
    """Return the central governed-output readiness verdict.

    Phase 1B PATCH 1: replaces ad-hoc flag checks scattered across build_final_reply()
    and boundary injection.

    Priority order (first match wins):
    1. insufficient core params  → insufficient_inputs
    2. demo data in scope        → demo_data_quarantine
    3. evidence not available    → evidence_missing
    4. HITL review pending       → review_pending
    5. governance projection blocks → governance_blocked
    6. else                      → releasable
    """
    if not is_sufficient_for_structured(asserted_state):
        return OutputReadinessDecision(
            releasable=False,
            status="insufficient_inputs",
            blocking_reason=(
                "Required core params (medium, pressure, temperature) "
                "not yet confirmed in asserted_state."
            ),
        )

    if demo_data_present:
        return OutputReadinessDecision(
            releasable=False,
            status="demo_data_quarantine",
            blocking_reason=(
                "Demo data is in scope — governed output quarantined "
                "until real evidence is available."
            ),
        )

    if not evidence_available:
        return OutputReadinessDecision(
            releasable=False,
            status="evidence_missing",
            blocking_reason=(
                "Evidence basis not available — governed output cannot be "
                "released without qualified evidence."
            ),
        )

    if parameter_integrity_projection and not parameter_integrity_projection.get("usable_for_structured_step", True):
        return OutputReadinessDecision(
            releasable=False,
            status="integrity_unusable",
            blocking_reason=(
                "Parameter integrity is not sufficient for structured use — "
                "unit, normalization, or plausibility clarification is required."
            ),
        )

    if domain_scope_projection and not domain_scope_projection.get("usable_for_governed_step", True):
        return OutputReadinessDecision(
            releasable=False,
            status="domain_scope_blocked",
            blocking_reason=(
                "Domain thresholds or scope gates block governed output — "
                "the current case is outside the deterministic recommendation scope."
            ),
        )

    if (conflict_status_projection or {}).get("conflict_still_open"):
        return OutputReadinessDecision(
            releasable=False,
            status="conflict_unresolved",
            blocking_reason=(
                "Parameter conflict remains open — governed output cannot be "
                "released until the conflicting value is clarified."
            ),
        )

    review = review_state or {}
    if review.get("review_required"):
        reason = review.get("review_reason") or "not specified"
        return OutputReadinessDecision(
            releasable=False,
            status="review_pending",
            blocking_reason=f"HITL review pending — {reason}",
        )

    if _governance_projection_blocks_output(governance_state or {}):
        return OutputReadinessDecision(
            releasable=False,
            status="governance_blocked",
            blocking_reason=(
                "Governance projection blocks output (release_status, "
                "gate_failures, or blocking unknowns)."
            ),
        )

    return OutputReadinessDecision(
        releasable=True,
        status="releasable",
        blocking_reason="",
    )


def _governance_projection_blocks_output(governance_state: Dict[str, Any]) -> bool:
    """Projection-only gate: mirrors governance and never creates its own release truth."""

    if governance_state.get("release_status") != "rfq_ready":
        return True
    if governance_state.get("rfq_admissibility") != "ready":
        return True
    if governance_state.get("specificity_level") != "compound_required":
        return True
    if governance_state.get("unknowns_release_blocking"):
        return True
    if governance_state.get("gate_failures"):
        return True
    return any(str(conflict.get("severity") or "").upper() in {"CRITICAL", "BLOCKING_UNKNOWN"} for conflict in governance_state.get("conflicts", []))


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
    """Return missing structured inputs in stable deterministic priority order."""
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
    """Return the deterministic clarification projection for incomplete cases."""
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
    """Build one deterministic next question for the top-priority missing input."""
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


def project_review_escalation_state(
    *,
    selection_status: str,
    readiness_status: str,
    blocking_reason: str,
    viable_candidate_ids: List[str],
    asserted_state: Optional[Dict[str, Any]],
    review_state: Optional[Dict[str, Any]],
    evidence_available: bool,
    demo_data_present: bool,
    evidence_provenance_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a deterministic next-step projection for withheld/review/escalation cases."""
    missing_items = _missing_core_input_items(asserted_state)
    ambiguous_candidate_ids = list(viable_candidate_ids) if selection_status == "multiple_viable_candidates" else []
    evidence_status = str((evidence_provenance_projection or {}).get("status") or "no_evidence")
    provenance_refs = list((evidence_provenance_projection or {}).get("provenance_refs") or [])
    conflict_status = str((conflict_status_projection or {}).get("status") or "no_conflict")
    affected_keys = list((conflict_status_projection or {}).get("affected_keys") or [])
    integrity_status = str((parameter_integrity_projection or {}).get("integrity_status") or "normalized_ok")
    integrity_blocking_keys = list((parameter_integrity_projection or {}).get("blocking_keys") or [])
    domain_scope_status = str((domain_scope_projection or {}).get("status") or "in_domain_scope")

    if missing_items:
        return {
            "status": "withheld_missing_core_inputs",
            "reason": blocking_reason or "Required core params are not yet confirmed.",
            "missing_items": missing_items,
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": False,
            "handover_possible": False,
            "human_validation_ready": False,
        }

    if demo_data_present:
        return {
            "status": "withheld_demo_data",
            "reason": blocking_reason or "Demo data is quarantined from governed output.",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": False,
        }

    if not evidence_available:
        return {
            "status": "withheld_no_evidence",
            "reason": blocking_reason or "Qualified evidence is missing.",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": False,
            "handover_possible": False,
            "human_validation_ready": False,
        }

    if domain_scope_status in {"out_of_domain_scope", "escalation_required"}:
        return {
            "status": "escalation_needed",
            "reason": _build_domain_scope_note(domain_scope_projection),
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": bool(provenance_refs),
        }

    if selection_status == "multiple_viable_candidates":
        return {
            "status": "ambiguous_but_reviewable",
            "reason": blocking_reason or "Multiple viable candidates remain after deterministic checks.",
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        }

    review = review_state or {}
    if review.get("review_required"):
        return {
            "status": "review_pending",
            "reason": str(review.get("review_reason") or blocking_reason or "Human review pending."),
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        }

    if readiness_status == "releasable":
        return {
            "status": "releasable",
            "reason": "",
            "missing_items": [],
            "ambiguous_candidate_ids": [],
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": True,
            "human_validation_ready": True,
        }

    if integrity_status == "unusable_until_clarified":
        return {
            "status": "escalation_needed",
            "reason": blocking_reason or "Parameterintegrität erfordert weitere Klärung oder Review.",
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": bool(provenance_refs),
        }

    if (conflict_status_projection or {}).get("conflict_still_open"):
        return {
            "status": "escalation_needed",
            "reason": blocking_reason or "Offener Parameterkonflikt erfordert Klärung oder Review.",
            "missing_items": [],
            "ambiguous_candidate_ids": ambiguous_candidate_ids,
            "evidence_status": evidence_status,
            "provenance_refs": provenance_refs,
            "conflict_status": conflict_status,
            "integrity_status": integrity_status,
            "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
            "review_meaningful": True,
            "handover_possible": False,
            "human_validation_ready": bool(provenance_refs),
        }

    reviewable_escalation = selection_status in {
        "blocked_no_candidates",
        "blocked_no_viable_candidates",
    } or readiness_status in {"candidate_ambiguity", "no_governed_candidate", "governance_blocked"}
    return {
        "status": "escalation_needed",
        "reason": blocking_reason or "Deterministic engineering escalation is required.",
        "missing_items": [],
        "ambiguous_candidate_ids": ambiguous_candidate_ids,
        "evidence_status": evidence_status,
        "provenance_refs": provenance_refs,
        "conflict_status": conflict_status,
        "integrity_status": integrity_status,
        "affected_keys": sorted(set(affected_keys) | set(integrity_blocking_keys)),
        "review_meaningful": reviewable_escalation,
        "handover_possible": reviewable_escalation,
        "human_validation_ready": reviewable_escalation,
    }


# ---------------------------------------------------------------------------
# Phase 1B PATCH 2 — Case Closure / Readiness Projection
# ---------------------------------------------------------------------------

CaseReadinessStatus = Literal[
    "incomplete",           # core params missing — cannot proceed to governance
    "sufficient_but_blocked",  # params confirmed, governance or evidence blocks
    "releasable",           # params + governance green, no review pending
    "handover_ready",       # releasable + no HITL review required
]


def project_case_readiness(
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    *,
    review_state: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    demo_data_present: bool = False,
) -> CaseReadinessStatus:
    """Return a deterministic case-closure status label.

    Phase 1B PATCH 2: makes the four distinct readiness levels testable independently.

    Levels (in ascending order of completeness):
    - incomplete:             core input params missing
    - sufficient_but_blocked: inputs confirmed, but governance/evidence/review blocks
    - releasable:             inputs + governance green, but review still pending
    - handover_ready:         fully releasable AND no pending HITL review

    Note: "releasable" here means the governed output CAN be released (governance green,
    evidence available, no demo data). The distinction from "handover_ready" is that
    an approved review state might still be pending for commercial handover.
    """
    if not is_sufficient_for_structured(asserted_state):
        return "incomplete"

    decision = evaluate_output_readiness(
        asserted_state,
        governance_state,
        review_state=review_state,
        evidence_available=evidence_available,
        demo_data_present=demo_data_present,
    )

    if not decision.releasable:
        # Params are sufficient but something else blocks
        if decision.status == "review_pending":
            # review_pending is a sub-case of sufficient_but_blocked, EXCEPT
            # when the review state is "approved" — then handover becomes possible.
            review = review_state or {}
            if review.get("review_state") == "approved":
                return "handover_ready"
            return "sufficient_but_blocked"
        return "sufficient_but_blocked"

    # Governance is green and no blockers — check review for handover distinction
    review = review_state or {}
    review_required = review.get("review_required", False)
    review_resolved = review.get("review_state") in ("approved", "none")
    if review_required and not review_resolved:
        return "releasable"

    return "handover_ready"


def _build_recommendation_artifact(
    selection_status: str,
    winner_candidate_id: Optional[str],
    candidate_projection: Optional[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    viable_candidate_ids: List[str],
    blocked_candidates: List[Dict[str, str]],
    evidence_basis: List[str],
    evidence_status: str,
    provenance_refs: List[str],
    conflict_status: str,
    integrity_status: str,
    domain_scope_status: str,
    threshold_status: str,
    release_status: str,
    rfq_admissibility: str,
    specificity_level: str,
    output_blocked: bool,
    readiness_status: str,
    blocking_reason: str,
    rationale_summary: str,
    trace_refs: List[str],
) -> Dict[str, Any]:
    return {
        "selection_status": selection_status,
        "winner_candidate_id": winner_candidate_id,
        "candidate_projection": candidate_projection,
        "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
        "viable_candidate_ids": viable_candidate_ids,
        "blocked_candidates": blocked_candidates,
        "evidence_basis": evidence_basis,
        "evidence_status": evidence_status,
        "provenance_refs": provenance_refs,
        "rationale_basis": [
            selection_status,
            readiness_status,
            evidence_status,
            conflict_status,
            integrity_status,
            domain_scope_status,
            threshold_status,
            "non_binding_projection",
        ],
        "conflict_status": conflict_status,
        "integrity_status": integrity_status,
        "domain_scope_status": domain_scope_status,
        "threshold_status": threshold_status,
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
        "binding_level": "non_binding",
        "readiness_status": readiness_status,
        "blocking_reason": blocking_reason,
        "rationale_summary": rationale_summary,
        "trace_provenance_refs": trace_refs,
    }


def _artifact_is_aligned(selection_state: Dict[str, Any], artifact: Dict[str, Any]) -> bool:
    if not artifact:
        return False
    return (
        artifact.get("selection_status") == selection_state.get("selection_status")
        and artifact.get("winner_candidate_id") == selection_state.get("winner_candidate_id")
        and artifact.get("viable_candidate_ids") == selection_state.get("viable_candidate_ids")
        and artifact.get("blocked_candidates") == selection_state.get("blocked_candidates")
        and artifact.get("release_status") == selection_state.get("release_status")
        and artifact.get("rfq_admissibility") == selection_state.get("rfq_admissibility")
        and artifact.get("specificity_level") == selection_state.get("specificity_level")
        and artifact.get("output_blocked") == selection_state.get("output_blocked")
        and artifact.get("binding_level") in {None, "non_binding"}
    )


def _find_candidate(
    candidates: List[Dict[str, Any]],
    candidate_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not candidate_id:
        return None
    for candidate in candidates:
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def _build_candidate_projection(
    candidates: List[Dict[str, Any]],
    winner_candidate_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    winner = _find_candidate(candidates, winner_candidate_id)
    if not winner:
        return None
    return {
        "candidate_id": winner["candidate_id"],
        "candidate_kind": winner.get("candidate_kind"),
        "material_family": winner.get("material_family"),
        "grade_name": winner.get("grade_name"),
        "manufacturer_name": winner.get("manufacturer_name"),
        "evidence_refs": list(winner.get("evidence_refs") or []),
    }


def _collect_provenance_refs(
    relevant_fact_cards: List[Dict[str, Any]],
    evidence_basis: List[str],
) -> List[str]:
    """Return deterministic provenance refs for the evidence actually carrying the state."""
    refs: List[str] = []
    evidence_basis_set = {str(ref) for ref in evidence_basis}
    for card in relevant_fact_cards:
        evidence_id = card.get("evidence_id") or card.get("id")
        if str(evidence_id) not in evidence_basis_set:
            continue
        provenance_ref = card.get("source_ref") or evidence_id
        if not provenance_ref:
            continue
        provenance_ref = str(provenance_ref)
        if provenance_ref not in refs:
            refs.append(provenance_ref)
    return refs


def project_evidence_provenance_state(
    relevant_fact_cards: List[Dict[str, Any]],
    evidence_basis: List[str],
) -> Dict[str, Any]:
    """Classify the current evidence footing from actual provenance references only."""
    provenance_refs = _collect_provenance_refs(relevant_fact_cards, evidence_basis)
    if not provenance_refs:
        status: EvidenceProvenanceStatus = "no_evidence"
    elif len(provenance_refs) == 1:
        status = "thin_evidence"
    else:
        status = "grounded_evidence"
    return {
        "status": status,
        "provenance_refs": provenance_refs,
        "evidence_basis": list(evidence_basis),
    }


def _build_evidence_binding_note(
    evidence_provenance_projection: Optional[Dict[str, Any]],
) -> str:
    projection = evidence_provenance_projection or {}
    status = str(projection.get("status") or "no_evidence")
    refs = list(projection.get("provenance_refs") or [])
    ref_text = ", ".join(refs) if refs else "keine"
    if status == "grounded_evidence":
        return "Die technischen Angaben sind durch qualifizierte Referenzdaten gestützt."
    if status == "thin_evidence":
        return "Die technische Referenzbasis ist eingeschränkt; eine ergänzende Herstellerprüfung ist ratsam."
    return "Qualifizierte technische Referenzdaten sind für diese Anfrage nicht verfügbar."


def _extract_observed_field_values(
    observed_state: Optional[Dict[str, Any]],
) -> Dict[str, List[Any]]:
    observed_values: Dict[str, List[Any]] = {}
    for entry in (observed_state or {}).get("observed_inputs", []):
        raw_text = str(entry.get("raw_text") or "")
        if not raw_text:
            continue
        extracted = norm_extract(raw_text)
        field_map = {
            "medium": extracted.get("medium_normalized"),
            "pressure": extracted.get("pressure_bar"),
            "temperature": extracted.get("temperature_c"),
        }
        for field_name, value in field_map.items():
            if value in (None, ""):
                continue
            observed_values.setdefault(field_name, [])
            if value not in observed_values[field_name]:
                observed_values[field_name].append(value)
    return observed_values


def _resolve_current_field_value(
    field_name: str,
    asserted_state: Optional[Dict[str, Any]],
    normalized_state: Optional[Dict[str, Any]],
) -> Any:
    asserted = asserted_state or {}
    normalized_parameters = (normalized_state or {}).get("normalized_parameters") or {}
    operating = asserted.get("operating_conditions") or {}
    if field_name == "medium":
        return (asserted.get("medium_profile") or {}).get("name") or normalized_parameters.get("medium_normalized")
    if field_name == "pressure":
        return operating.get("pressure") if operating.get("pressure") is not None else normalized_parameters.get("pressure_bar")
    if field_name == "temperature":
        return operating.get("temperature") if operating.get("temperature") is not None else normalized_parameters.get("temperature_c")
    return None


def project_conflict_status(
    *,
    observed_state: Optional[Dict[str, Any]],
    normalized_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Project whether the current parameter state is conflict-free, corrected, or still open."""
    observed_values = _extract_observed_field_values(observed_state)
    governance_conflicts = list((governance_state or {}).get("conflicts") or [])
    normalized_identities = (normalized_state or {}).get("identity_records") or {}

    conflicting_fields = sorted(
        field_name for field_name, values in observed_values.items()
        if len(values) > 1
    )
    open_conflict_fields = {
        str(conflict.get("field"))
        for conflict in governance_conflicts
        if conflict.get("field") in {"medium", "pressure", "temperature"}
    }
    for field_name, identity in normalized_identities.items():
        if field_name not in {"medium", "pressure", "temperature"}:
            continue
        if identity.get("identity_class") == "identity_unresolved" and "conflict" in str(identity.get("mapping_reason") or ""):
            open_conflict_fields.add(field_name)

    corrected_fields: List[str] = []
    unresolved_fields = set(open_conflict_fields)
    previous_parts: List[str] = []
    current_parts: List[str] = []

    for field_name in conflicting_fields:
        values = list(observed_values.get(field_name) or [])
        current_value = _resolve_current_field_value(field_name, asserted_state, normalized_state)
        previous_value = values[0]
        if len(values) > 1 and current_value not in (None, "") and current_value == values[-1] and field_name not in unresolved_fields:
            corrected_fields.append(field_name)
            previous_parts.append(f"{field_name}={previous_value}")
            current_parts.append(f"{field_name}={current_value}")
        else:
            unresolved_fields.add(field_name)
            previous_parts.append(f"{field_name}={values[0]}")
            current_parts.append(f"{field_name}={values[-1]}")

    affected_keys = sorted(set(corrected_fields) | set(unresolved_fields))
    if unresolved_fields:
        status = "unresolved_conflict" if open_conflict_fields else "conflicting_values"
    elif corrected_fields:
        status = "corrected_value"
    else:
        status = "no_conflict"

    return {
        "status": status,
        "affected_keys": affected_keys,
        "previous_value_summary": ", ".join(previous_parts),
        "current_value_summary": ", ".join(current_parts),
        "correction_applied": bool(corrected_fields) and not bool(unresolved_fields),
        "conflict_still_open": bool(unresolved_fields),
    }


def build_correction_projection(
    conflict_status_projection: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    projection = conflict_status_projection or {}
    if projection.get("status") == "no_conflict":
        return None
    return {
        "affected_keys": list(projection.get("affected_keys") or []),
        "previous_value_summary": str(projection.get("previous_value_summary") or ""),
        "current_value_summary": str(projection.get("current_value_summary") or ""),
        "correction_applied": bool(projection.get("correction_applied")),
        "conflict_still_open": bool(projection.get("conflict_still_open")),
    }


def _identity_or_normalized_value(
    field_name: str,
    normalized_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Any:
    identity_records = (normalized_state or {}).get("identity_records") or {}
    identity = identity_records.get(field_name) or {}
    if identity.get("normalized_value") not in (None, ""):
        return identity.get("normalized_value")
    return _resolve_current_field_value(field_name, asserted_state, normalized_state)


def _field_integrity_status(
    field_name: str,
    normalized_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Optional[str]:
    identity_records = (normalized_state or {}).get("identity_records") or {}
    identity = identity_records.get(field_name) or {}
    current_value = _identity_or_normalized_value(field_name, normalized_state, asserted_state)
    if current_value in (None, ""):
        return None

    raw_value = str(identity.get("raw_value") or "").strip().lower()
    normalization_certainty = str(identity.get("normalization_certainty") or "")
    mapping_reason = str(identity.get("mapping_reason") or "")
    identity_class = str(identity.get("identity_class") or "")

    if identity_class == "identity_unresolved":
        return "unusable_until_clarified"

    if field_name == "temperature":
        try:
            numeric_value = float(current_value)
        except Exception:
            return "unusable_until_clarified"
        if numeric_value < -273.15:
            return "implausible_value"
        if raw_value.endswith("grad") or (raw_value and re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", raw_value)):
            return "unit_ambiguous"
        if "umgerechnet von" in mapping_reason.lower():
            return "usable_with_warning"
        return "normalized_ok"

    if field_name == "pressure":
        try:
            numeric_value = float(current_value)
        except Exception:
            return "unusable_until_clarified"
        if numeric_value < 0:
            return "implausible_value"
        if raw_value and re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", raw_value):
            return "unit_ambiguous"
        if "umgerechnet von" in mapping_reason.lower():
            return "usable_with_warning"
        return "normalized_ok"

    if field_name == "medium":
        if identity_class == "identity_probable" or normalization_certainty == "inferred":
            return "usable_with_warning"
        if identity_class == "identity_unresolved":
            return "unusable_until_clarified"
        return "normalized_ok"

    return "normalized_ok"


def project_unit_normalization_status(
    *,
    normalized_state: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    statuses: Dict[str, str] = {}
    for field_name in STRUCTURED_REQUIRED_CORE_PARAMS:
        status = _field_integrity_status(field_name, normalized_state, asserted_state)
        if status:
            statuses[field_name] = status

    warning_keys = sorted(
        key for key, status in statuses.items()
        if status == "usable_with_warning"
    )
    blocking_keys = sorted(
        key for key, status in statuses.items()
        if status in {"unit_ambiguous", "implausible_value", "unusable_until_clarified"}
    )
    return {
        "statuses": statuses,
        "affected_keys": sorted(statuses.keys()),
        "warning_keys": warning_keys,
        "blocking_keys": blocking_keys,
    }


def build_parameter_integrity_projection(
    unit_normalization_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    projection = unit_normalization_projection or {}
    warning_keys = list(projection.get("warning_keys") or [])
    blocking_keys = list(projection.get("blocking_keys") or [])
    affected_keys = list(projection.get("affected_keys") or [])
    if blocking_keys:
        integrity_status = "unusable_until_clarified"
    elif warning_keys:
        integrity_status = "usable_with_warning"
    else:
        integrity_status = "normalized_ok"
    return {
        "affected_keys": affected_keys,
        "integrity_status": integrity_status,
        "warning_keys": warning_keys,
        "blocking_keys": blocking_keys,
        "usable_for_structured_step": not bool(blocking_keys),
    }


def _build_rwdr_threshold_payload(
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]],
) -> Optional[RwdrCalcInput]:
    asserted = asserted_state or {}
    working = working_profile or {}
    operating = asserted.get("operating_conditions") or {}
    machine = asserted.get("machine_profile") or {}

    shaft_diameter = (
        machine.get("shaft_diameter_mm")
        or working.get("shaft_diameter_mm")
        or working.get("shaft_diameter")
        or working.get("diameter")
    )
    rpm = working.get("speed_rpm") or working.get("rpm") or working.get("speed")
    if shaft_diameter is None or rpm is None:
        return None

    return RwdrCalcInput(
        shaft_diameter_mm=float(shaft_diameter),
        rpm=float(rpm),
        pressure_bar=operating.get("pressure"),
        temperature_max_c=operating.get("temperature"),
        temperature_min_c=working.get("temperature_min_c"),
        surface_hardness_hrc=working.get("surface_hardness_hrc") or working.get("hrc"),
        runout_mm=working.get("runout_mm") or working.get("runout"),
        clearance_gap_mm=working.get("clearance_gap_mm") or working.get("clearance_gap"),
        elastomer_material=(
            machine.get("material")
            or working.get("material")
            or working.get("elastomer_material")
        ),
        medium=(asserted.get("medium_profile") or {}).get("name") or working.get("medium"),
        lubrication_mode=working.get("lubrication_mode") or working.get("lubrication"),
    )


def project_threshold_status(
    *,
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Project triggered deterministic RWDR/domain thresholds from existing calc inputs."""
    rwdr_input = _build_rwdr_threshold_payload(asserted_state, working_profile)
    if rwdr_input is None:
        return {
            "triggered_thresholds": [],
            "warning_thresholds": [],
            "blocking_thresholds": [],
            "threshold_status": "threshold_free",
            "usable_for_governed_step": True,
        }

    result = calculate_rwdr(rwdr_input)
    warning_thresholds: List[str] = []
    blocking_thresholds: List[str] = []

    if result.dn_warning:
        warning_thresholds.append("dn_warning")
    if result.hrc_warning:
        warning_thresholds.append("hrc_warning")
    if result.runout_warning:
        warning_thresholds.append("runout_warning")
    if result.pv_warning:
        warning_thresholds.append("pv_warning")
    if result.dry_running_risk:
        warning_thresholds.append("dry_running_risk")
    if result.geometry_warning:
        warning_thresholds.append("geometry_warning")

    if result.material_limit_exceeded:
        blocking_thresholds.append("material_limit_exceeded")
    if result.extrusion_risk:
        blocking_thresholds.append("extrusion_risk")
    if result.shrinkage_risk:
        blocking_thresholds.append("shrinkage_risk")
    if result.status == "critical":
        blocking_thresholds.append("rwdr_critical_status")

    warning_thresholds = list(dict.fromkeys(warning_thresholds))
    blocking_thresholds = list(dict.fromkeys(blocking_thresholds))
    triggered_thresholds = warning_thresholds + [t for t in blocking_thresholds if t not in warning_thresholds]

    if blocking_thresholds:
        threshold_status = "blocking_thresholds"
    elif warning_thresholds:
        threshold_status = "warning_thresholds"
    else:
        threshold_status = "threshold_free"

    return {
        "triggered_thresholds": triggered_thresholds,
        "warning_thresholds": warning_thresholds,
        "blocking_thresholds": blocking_thresholds,
        "threshold_status": threshold_status,
        "usable_for_governed_step": not bool(blocking_thresholds),
    }


def project_domain_scope_status(
    threshold_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Project whether the current case remains inside deterministic domain scope."""
    projection = threshold_projection or {}
    warning_thresholds = list(projection.get("warning_thresholds") or [])
    blocking_thresholds = list(projection.get("blocking_thresholds") or [])
    threshold_status = str(projection.get("threshold_status") or "threshold_free")

    if (
        "material_limit_exceeded" in blocking_thresholds
        and "extrusion_risk" not in blocking_thresholds
        and "shrinkage_risk" not in blocking_thresholds
    ):
        status = "out_of_domain_scope"
    elif blocking_thresholds:
        status = "escalation_required"
    elif warning_thresholds:
        status = "in_domain_with_warning"
    else:
        status = "in_domain_scope"

    return {
        "status": status,
        "triggered_thresholds": list(projection.get("triggered_thresholds") or []),
        "warning_thresholds": warning_thresholds,
        "blocking_thresholds": blocking_thresholds,
        "threshold_status": threshold_status,
        "usable_for_governed_step": not bool(blocking_thresholds),
    }


def _build_conflict_correction_note(
    conflict_status_projection: Optional[Dict[str, Any]],
) -> str:
    projection = conflict_status_projection or {}
    status = str(projection.get("status") or "no_conflict")
    previous_summary = str(projection.get("previous_value_summary") or "").strip()
    current_summary = str(projection.get("current_value_summary") or "").strip()
    if status == "corrected_value":
        return f"{CORRECTION_APPLIED_PREFIX} {previous_summary} -> {current_summary}."
    if status in {"conflicting_values", "unresolved_conflict"}:
        detail = current_summary or previous_summary
        if detail:
            return f"{UNRESOLVED_CONFLICT_REPLY} Offener Konflikt: {detail}."
        return UNRESOLVED_CONFLICT_REPLY
    return ""


def _build_integrity_note(
    parameter_integrity_projection: Optional[Dict[str, Any]],
    unit_normalization_projection: Optional[Dict[str, Any]],
) -> str:
    integrity = parameter_integrity_projection or {}
    unit_projection = unit_normalization_projection or {}
    integrity_status = str(integrity.get("integrity_status") or "normalized_ok")
    blocking_keys = list(integrity.get("blocking_keys") or [])
    warning_keys = list(integrity.get("warning_keys") or [])
    statuses = dict(unit_projection.get("statuses") or {})
    if integrity_status == "unusable_until_clarified":
        param_count = len(blocking_keys) if blocking_keys else 1
        subject = "Ein Betriebsparameter bedarf" if param_count == 1 else f"{param_count} Betriebsparameter bedürfen"
        return f"{INTEGRITY_UNUSABLE_REPLY} {subject} fachlicher Klärung."
    if integrity_status == "usable_with_warning":
        param_count = len(warning_keys) if warning_keys else 1
        subject = "Ein Betriebsparameter ist" if param_count == 1 else f"{param_count} Betriebsparameter sind"
        return f"{INTEGRITY_WARNING_PREFIX} {subject} mit Vorbehalt verwendbar."
    return ""


def _build_domain_scope_note(
    domain_scope_projection: Optional[Dict[str, Any]],
) -> str:
    projection = domain_scope_projection or {}
    status = str(projection.get("status") or "in_domain_scope")
    warnings = list(projection.get("warning_thresholds") or [])
    blocking = list(projection.get("blocking_thresholds") or [])
    if status == "in_domain_with_warning":
        return f"{DOMAIN_WARNING_PREFIX} Die Betriebsbedingungen liegen an den Grenzen des fachlich abgedeckten Bereichs."
    if status == "out_of_domain_scope":
        return f"{OUT_OF_DOMAIN_REPLY} Die angegebenen Betriebsbedingungen überschreiten den fachlich abgedeckten Bereich."
    if status == "escalation_required":
        return f"{THRESHOLD_ESCALATION_REPLY} Die angegebenen Betriebsbedingungen erfordern eine fachliche Einzelfallprüfung."
    return ""


def project_user_facing_output_status(
    *,
    selection_status: str,
    recommendation_artifact: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project the single user-visible structured result class from existing internal projections."""
    artifact = recommendation_artifact or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    domain_scope = domain_scope_projection or {}
    invariant_projection = projection_invariant_projection or {}

    review_status = str(review_projection.get("status") or "")
    domain_status = str(domain_scope.get("status") or "in_domain_scope")
    readiness_status = str(artifact.get("readiness_status") or "")
    release_status = str(artifact.get("release_status") or "")
    rfq_admissibility = str(artifact.get("rfq_admissibility") or "")

    if not invariant_projection.get("invariant_ok", True):
        status = "withheld_escalation"
    elif selection_status == "blocked_missing_required_inputs":
        status = "clarification_needed"
    elif release_status in {"precheck_only", "manufacturer_validation_required"} or rfq_admissibility == "provisional":
        status = "withheld_review"
    elif review_status == "withheld_no_evidence" or readiness_status == "evidence_missing":
        status = "withheld_no_evidence"
    elif domain_status == "out_of_domain_scope":
        status = "withheld_domain_block"
    elif review_status in {"review_pending", "ambiguous_but_reviewable"} or readiness_status == "review_pending":
        status = "withheld_review"
    elif review_status == "escalation_needed" or readiness_status in {
        "conflict_unresolved",
        "integrity_unusable",
        "domain_scope_blocked",
        "candidate_ambiguity",
        "no_governed_candidate",
        "governance_blocked",
    }:
        status = "withheld_escalation"
    elif artifact.get("candidate_projection"):
        status = "governed_non_binding_result"
    elif clarification.get("clarification_still_meaningful"):
        status = "clarification_needed"
    else:
        status = "withheld_escalation"

    return {"status": status}


def build_output_contract_projection(
    *,
    user_facing_output_projection: Optional[Dict[str, Any]],
    recommendation_artifact: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    threshold_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a compact user-facing output contract from existing deterministic projections."""
    output_status = str((user_facing_output_projection or {}).get("status") or "withheld_escalation")
    artifact = recommendation_artifact or {}
    clarification = clarification_projection or {}
    review_projection = review_escalation_projection or {}
    conflict_projection = conflict_status_projection or {}
    integrity_projection = parameter_integrity_projection or {}
    domain_scope = domain_scope_projection or {}
    threshold = threshold_projection or {}
    invariant_projection = projection_invariant_projection or {}
    invariant_violations = list(invariant_projection.get("invariant_violations") or [])

    visible_warning_flags: List[str] = []
    if artifact.get("evidence_status") == "thin_evidence":
        visible_warning_flags.append("thin_evidence")
    if conflict_projection.get("correction_applied"):
        visible_warning_flags.append("corrected_value")
    if integrity_projection.get("integrity_status") == "usable_with_warning":
        visible_warning_flags.append("integrity_warning")
    if domain_scope.get("status") == "in_domain_with_warning":
        visible_warning_flags.append("domain_warning")
    if threshold.get("threshold_status") == "warning_thresholds":
        visible_warning_flags.append("threshold_warning")

    if invariant_violations:
        allowed_surface_claims = ["withheld", "state_invariant_violation"]
        next_user_action = (
            "human_review"
            if review_projection.get("review_meaningful")
            else "engineering_escalation"
        )
        suppress_recommendation_details = True
    elif output_status == "governed_non_binding_result":
        allowed_surface_claims = ["non_binding_result", "warnings", "next_step_none"]
        next_user_action = "confirmed_result_review"
        suppress_recommendation_details = False
    elif output_status == "clarification_needed":
        allowed_surface_claims = ["missing_inputs", "single_next_question"]
        next_user_action = (
            "answer_next_question"
            if clarification.get("clarification_still_meaningful")
            else "pause_for_review_or_escalation"
        )
        suppress_recommendation_details = True
    elif output_status == "withheld_review":
        allowed_surface_claims = ["withheld", "review_required"]
        next_user_action = "human_review"
        suppress_recommendation_details = True
    elif output_status == "withheld_no_evidence":
        allowed_surface_claims = ["withheld", "evidence_missing"]
        next_user_action = "obtain_qualified_evidence"
        suppress_recommendation_details = True
    elif output_status == "withheld_domain_block":
        allowed_surface_claims = ["withheld", "domain_block"]
        next_user_action = "engineering_escalation"
        suppress_recommendation_details = True
    else:
        allowed_surface_claims = ["withheld", "escalation_required"]
        next_user_action = (
            "human_review"
            if review_projection.get("review_meaningful")
            else "engineering_escalation"
        )
        suppress_recommendation_details = True

    if conflict_projection.get("conflict_still_open"):
        visible_warning_flags.append("conflict_open")
    if integrity_projection.get("integrity_status") == "unusable_until_clarified":
        visible_warning_flags.append("integrity_blocked")
    if domain_scope.get("status") in {"out_of_domain_scope", "escalation_required"}:
        visible_warning_flags.append("domain_blocked")
    if invariant_violations:
        visible_warning_flags.append("invariant_violation")

    return {
        "output_status": output_status,
        "allowed_surface_claims": visible_warning_flags and list(dict.fromkeys(allowed_surface_claims)) or allowed_surface_claims,
        "next_user_action": next_user_action,
        "visible_warning_flags": list(dict.fromkeys(visible_warning_flags)),
        "suppress_recommendation_details": suppress_recommendation_details,
    }


def project_projection_invariants(
    *,
    recommendation_artifact: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    evidence_provenance_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a small deterministic list of cross-projection invariant violations."""
    artifact = recommendation_artifact or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    evidence_projection = evidence_provenance_projection or {}
    conflict_projection = conflict_status_projection or {}
    integrity_projection = parameter_integrity_projection or {}
    domain_scope = domain_scope_projection or {}
    output_contract = output_contract_projection or {}

    output_status = str(output_contract.get("output_status") or "withheld_escalation")
    suppress_details = bool(output_contract.get("suppress_recommendation_details"))
    candidate_projection = artifact.get("candidate_projection")
    readiness_status = str(artifact.get("readiness_status") or "")
    review_status = str(review_projection.get("status") or "")
    evidence_status = str(evidence_projection.get("status") or "no_evidence")
    clarification_meaningful = bool(clarification.get("clarification_still_meaningful"))
    conflict_open = bool(conflict_projection.get("conflict_still_open"))
    integrity_blocked = str(integrity_projection.get("integrity_status") or "") == "unusable_until_clarified"
    domain_blocked = str(domain_scope.get("status") or "") in {"out_of_domain_scope", "escalation_required"}
    blocked_by_review = review_status in {
        "review_pending",
        "ambiguous_but_reviewable",
        "withheld_no_evidence",
        "withheld_demo_data",
        "escalation_needed",
    }
    blocked_clarification_step = review_status in {
        "review_pending",
        "ambiguous_but_reviewable",
        "withheld_no_evidence",
        "withheld_demo_data",
    }

    violations: List[str] = []

    if output_status == "governed_non_binding_result" and suppress_details:
        violations.append("governed_result_cannot_suppress_recommendation_details")
    if output_status == "governed_non_binding_result" and not candidate_projection:
        violations.append("governed_result_requires_candidate_projection")
    if output_status == "governed_non_binding_result" and (
        conflict_open
        or integrity_blocked
        or domain_blocked
        or evidence_status == "no_evidence"
        or blocked_by_review
    ):
        violations.append("governed_result_conflicts_with_blocking_projection")
    if output_status == "clarification_needed" and (
        blocked_clarification_step
        or domain_blocked
        or evidence_status == "no_evidence"
    ):
        violations.append("clarification_output_conflicts_with_blocking_projection")
    if conflict_open and (output_status == "governed_non_binding_result" or candidate_projection):
        violations.append("unresolved_conflict_cannot_surface_governed_recommendation")
    if readiness_status == "releasable" and (
        review_status != "releasable"
        or evidence_status == "no_evidence"
        or conflict_open
        or integrity_blocked
        or domain_blocked
    ):
        violations.append("releasable_readiness_conflicts_with_blocking_projection")

    return {
        "invariant_ok": not violations,
        "invariant_violations": list(dict.fromkeys(violations)),
    }


def _apply_invariant_safeguards(
    *,
    recommendation_artifact: Dict[str, Any],
    user_facing_output_projection: Dict[str, Any],
    output_contract_projection: Dict[str, Any],
    projection_invariant_projection: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], bool]:
    """Downgrade outward-facing projections when cross-projection invariants are violated."""
    if projection_invariant_projection.get("invariant_ok", True):
        return (
            recommendation_artifact,
            user_facing_output_projection,
            output_contract_projection,
            bool(recommendation_artifact.get("output_blocked")),
        )

    safe_artifact = dict(recommendation_artifact)
    safe_artifact["candidate_projection"] = None
    safe_artifact["output_blocked"] = True
    safe_artifact["readiness_status"] = "invariant_blocked"
    safe_artifact["blocking_reason"] = (
        "Projection invariants violated — governed output downgraded to a safe withheld state."
    )
    safe_artifact["rationale_summary"] = INVARIANT_BLOCKED_REPLY

    safe_user_facing = {"status": "withheld_escalation"}
    safe_output_contract = dict(output_contract_projection)
    safe_output_contract["output_status"] = "withheld_escalation"
    safe_output_contract["allowed_surface_claims"] = ["withheld", "state_invariant_violation"]
    safe_output_contract["suppress_recommendation_details"] = True
    safe_output_contract["visible_warning_flags"] = list(dict.fromkeys(
        list(safe_output_contract.get("visible_warning_flags") or []) + ["invariant_violation"]
    ))

    return safe_artifact, safe_user_facing, safe_output_contract, True


def build_state_trace_audit_projection(
    *,
    selection_status: str,
    recommendation_artifact: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a compact deterministic reason trace for the final structured state."""
    artifact = recommendation_artifact or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    conflict_projection = conflict_status_projection or {}
    integrity_projection = parameter_integrity_projection or {}
    domain_scope = domain_scope_projection or {}
    output_contract = output_contract_projection or {}
    invariant_projection = projection_invariant_projection or {}

    output_status = str(output_contract.get("output_status") or "withheld_escalation")
    review_status = str(review_projection.get("status") or "")
    readiness_status = str(artifact.get("readiness_status") or "")
    release_status = str(artifact.get("release_status") or "")
    rfq_admissibility = str(artifact.get("rfq_admissibility") or "")
    candidate_projection = artifact.get("candidate_projection")
    conflict_open = bool(conflict_projection.get("conflict_still_open"))
    integrity_status = str(integrity_projection.get("integrity_status") or "normalized_ok")
    domain_status = str(domain_scope.get("status") or "in_domain_scope")
    invariant_violations = list(invariant_projection.get("invariant_violations") or [])
    missing_items = list(clarification.get("missing_items") or [])

    blocking_reasons: List[str] = []
    contributing_reasons: List[str] = []
    trace_flags = list(output_contract.get("visible_warning_flags") or [])

    if invariant_violations:
        blocking_reasons.append("invariant_blocked")
        contributing_reasons.extend(invariant_violations)
        primary_reason = "invariant_blocked"
    elif output_status == "governed_non_binding_result" and candidate_projection:
        primary_reason = "governed_releasable_result"
        if artifact.get("evidence_status") == "thin_evidence":
            contributing_reasons.append("evidence_thin")
    elif output_status == "clarification_needed":
        primary_reason = "clarification_missing_inputs"
        if missing_items:
            contributing_reasons.append("missing_inputs")
    elif output_status == "withheld_review":
        if review_status == "review_pending":
            primary_reason = "review_pending"
            blocking_reasons.append("review_pending")
        elif review_status == "ambiguous_but_reviewable" or selection_status == "multiple_viable_candidates":
            primary_reason = "review_candidate_ambiguity"
            blocking_reasons.append("candidate_ambiguity")
        elif release_status in {"precheck_only", "manufacturer_validation_required"} or rfq_admissibility == "provisional":
            primary_reason = "review_governance_withheld"
            blocking_reasons.append("governance_withheld")
        else:
            primary_reason = "review_required"
            blocking_reasons.append("review_required")
    elif output_status == "withheld_no_evidence":
        primary_reason = "withheld_no_evidence"
        blocking_reasons.append("no_evidence")
    elif output_status == "withheld_domain_block":
        primary_reason = "domain_scope_blocked"
        blocking_reasons.append("domain_blocked")
    elif conflict_open or readiness_status == "conflict_unresolved":
        primary_reason = "escalation_conflict_open"
        blocking_reasons.append("conflict_open")
    elif integrity_status == "unusable_until_clarified" or readiness_status == "integrity_unusable":
        primary_reason = "escalation_integrity_blocked"
        blocking_reasons.append("integrity_blocked")
    elif domain_status == "escalation_required" or readiness_status == "domain_scope_blocked":
        primary_reason = "escalation_domain_threshold"
        blocking_reasons.append("domain_threshold_blocked")
    elif selection_status == "blocked_no_candidates":
        primary_reason = "escalation_no_candidates"
        blocking_reasons.append("no_candidates")
    elif selection_status == "blocked_no_viable_candidates":
        primary_reason = "escalation_no_viable_candidates"
        blocking_reasons.append("no_viable_candidates")
    elif readiness_status == "governance_blocked":
        primary_reason = "escalation_governance_blocked"
        blocking_reasons.append("governance_blocked")
    elif readiness_status == "no_governed_candidate":
        primary_reason = "escalation_no_governed_candidate"
        blocking_reasons.append("no_governed_candidate")
    elif readiness_status == "candidate_ambiguity":
        primary_reason = "review_candidate_ambiguity"
        blocking_reasons.append("candidate_ambiguity")
    else:
        primary_reason = "escalation_required"
        if output_status != "governed_non_binding_result":
            blocking_reasons.append("escalation_required")

    if missing_items and primary_reason != "clarification_missing_inputs":
        contributing_reasons.append("missing_inputs")
    if review_status == "escalation_needed":
        contributing_reasons.append("review_escalation")
    elif review_status == "review_pending":
        contributing_reasons.append("review_pending")
    elif review_status == "ambiguous_but_reviewable":
        contributing_reasons.append("candidate_ambiguity")
    elif review_status == "withheld_no_evidence":
        contributing_reasons.append("no_evidence")
    elif review_status == "withheld_demo_data":
        contributing_reasons.append("demo_data_quarantine")

    if conflict_open:
        contributing_reasons.append("conflict_open")
    if integrity_status == "unusable_until_clarified":
        contributing_reasons.append("integrity_blocked")
    elif integrity_status == "usable_with_warning":
        trace_flags.append("integrity_warning")
    if domain_status == "out_of_domain_scope":
        contributing_reasons.append("domain_blocked")
    elif domain_status == "escalation_required":
        contributing_reasons.append("domain_threshold_blocked")
    elif domain_status == "in_domain_with_warning":
        trace_flags.append("domain_warning")
    if artifact.get("evidence_status") == "no_evidence":
        contributing_reasons.append("no_evidence")
    if release_status in {"precheck_only", "manufacturer_validation_required"} or rfq_admissibility == "provisional":
        contributing_reasons.append("governance_withheld")

    return {
        "primary_status_reason": primary_reason,
        "contributing_reasons": list(dict.fromkeys(contributing_reasons)),
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "trace_flags": list(dict.fromkeys(trace_flags)),
    }


def get_primary_trace_reason(state_trace_audit_projection: Optional[Dict[str, Any]]) -> str:
    projection = state_trace_audit_projection or {}
    return str(projection.get("primary_status_reason") or "")


def is_blocked_by_trace(
    state_trace_audit_projection: Optional[Dict[str, Any]],
    reason_code: Optional[str] = None,
) -> bool:
    projection = state_trace_audit_projection or {}
    blocking_reasons = set(str(item) for item in (projection.get("blocking_reasons") or []))
    if reason_code is None:
        return bool(blocking_reasons)
    return str(reason_code) in blocking_reasons


def build_case_summary_projection(
    *,
    asserted_state: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    state_trace_audit_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a compact deterministic case summary for downstream readers."""
    output_contract = output_contract_projection or {}
    clarification = clarification_projection or {}
    trace_projection = state_trace_audit_projection or {}

    missing_core_fields = _missing_core_input_items(asserted_state)
    confirmed_core_fields = [
        key for key in STRUCTURED_REQUIRED_CORE_PARAMS
        if key not in missing_core_fields
    ]
    current_case_status = str(output_contract.get("output_status") or "withheld_escalation")
    active_blockers = list(trace_projection.get("blocking_reasons") or [])
    next_step = str(output_contract.get("next_user_action") or "")

    if "invariant_blocked" in active_blockers:
        next_step = "engineering_escalation"
    elif current_case_status == "withheld_escalation" and active_blockers and not set(active_blockers).issubset({"review_pending", "candidate_ambiguity", "review_required"}):
        next_step = "engineering_escalation"
    elif current_case_status == "clarification_needed" and not next_step:
        next_step = (
            "answer_next_question"
            if clarification.get("clarification_still_meaningful")
            else "pause_for_review_or_escalation"
        )
    elif current_case_status == "governed_non_binding_result" and not next_step:
        next_step = "confirmed_result_review"
    elif not next_step:
        next_step = "engineering_escalation"

    return {
        "current_case_status": current_case_status,
        "confirmed_core_fields": confirmed_core_fields,
        "missing_core_fields": missing_core_fields,
        "active_blockers": active_blockers,
        "next_step": next_step,
    }


def get_case_status(case_summary_projection: Optional[Dict[str, Any]]) -> str:
    projection = case_summary_projection or {}
    return str(projection.get("current_case_status") or "")


def get_next_case_step(case_summary_projection: Optional[Dict[str, Any]]) -> str:
    projection = case_summary_projection or {}
    return str(projection.get("next_step") or "")


def has_active_blockers(case_summary_projection: Optional[Dict[str, Any]]) -> bool:
    projection = case_summary_projection or {}
    return bool(projection.get("active_blockers") or [])


_ACTIONABILITY_ACTIONS: tuple[str, ...] = (
    "provide_missing_input",
    "await_review",
    "escalate_engineering",
    "consume_governed_result",
    "prepare_handover",
    "obtain_qualified_evidence",
    "no_action_until_clarified",
)


def build_actionability_projection(
    *,
    case_summary_projection: Optional[Dict[str, Any]],
    output_contract_projection: Optional[Dict[str, Any]],
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    projection_invariant_projection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a compact deterministic projection of the currently allowed action space."""
    summary = case_summary_projection or {}
    output_contract = output_contract_projection or {}
    review_projection = review_escalation_projection or {}
    clarification = clarification_projection or {}
    invariant_projection = projection_invariant_projection or {}

    current_case_status = str(summary.get("current_case_status") or "withheld_escalation")
    active_blockers = list(summary.get("active_blockers") or [])
    next_expected_user_action = str(
        summary.get("next_step")
        or output_contract.get("next_user_action")
        or "engineering_escalation"
    )
    review_status = str(review_projection.get("status") or "")
    handover_possible = bool(review_projection.get("handover_possible"))

    if not invariant_projection.get("invariant_ok", True) or "invariant_blocked" in active_blockers:
        actionability_status = "blocked"
        primary_allowed_action = "no_action_until_clarified"
    elif current_case_status == "clarification_needed":
        if clarification.get("clarification_still_meaningful"):
            actionability_status = "input_required"
            primary_allowed_action = "provide_missing_input"
        else:
            actionability_status = "blocked"
            primary_allowed_action = "no_action_until_clarified"
    elif current_case_status == "withheld_no_evidence":
        actionability_status = "evidence_required"
        primary_allowed_action = "obtain_qualified_evidence"
    elif current_case_status == "withheld_review":
        if handover_possible and review_status == "ambiguous_but_reviewable":
            actionability_status = "handoverable_restricted"
            primary_allowed_action = "prepare_handover"
        else:
            actionability_status = "review_pending"
            primary_allowed_action = "await_review"
    elif current_case_status == "governed_non_binding_result":
        actionability_status = "result_available"
        primary_allowed_action = "consume_governed_result"
    else:
        actionability_status = "escalation_required"
        primary_allowed_action = "escalate_engineering"

    blocked_actions = [
        action for action in _ACTIONABILITY_ACTIONS
        if action != primary_allowed_action
    ]
    return {
        "actionability_status": actionability_status,
        "primary_allowed_action": primary_allowed_action,
        "blocked_actions": blocked_actions,
        "next_expected_user_action": next_expected_user_action,
    }


def get_primary_allowed_action(actionability_projection: Optional[Dict[str, Any]]) -> str:
    projection = actionability_projection or {}
    return str(projection.get("primary_allowed_action") or "")


def get_next_expected_user_action(actionability_projection: Optional[Dict[str, Any]]) -> str:
    projection = actionability_projection or {}
    return str(projection.get("next_expected_user_action") or "")


def is_action_blocked(
    actionability_projection: Optional[Dict[str, Any]],
    action_code: str,
) -> bool:
    projection = actionability_projection or {}
    blocked_actions = set(str(item) for item in (projection.get("blocked_actions") or []))
    return str(action_code) in blocked_actions


_STATE_DELTA_FIELD_ORDER: tuple[str, ...] = (
    "invariant_ok",
    "conflict_status",
    "integrity_status",
    "domain_scope_status",
    "threshold_status",
    "output_status",
    "case_status",
    "actionability_status",
    "primary_allowed_action",
    "next_step",
    "next_expected_user_action",
    "active_blockers",
    "blocked_actions",
)


def _compare_transition(previous_value: Any, current_value: Any) -> str:
    previous_code = str(previous_value or "none")
    current_code = str(current_value or "none")
    if previous_code == current_code:
        return "unchanged"
    return f"{previous_code}_to_{current_code}"


def compare_case_status(
    previous_case_summary_projection: Optional[Dict[str, Any]],
    current_case_summary_projection: Optional[Dict[str, Any]],
) -> str:
    return _compare_transition(
        get_case_status(previous_case_summary_projection),
        get_case_status(current_case_summary_projection),
    )


def compare_actionability(
    previous_actionability_projection: Optional[Dict[str, Any]],
    current_actionability_projection: Optional[Dict[str, Any]],
) -> str:
    previous_projection = previous_actionability_projection or {}
    current_projection = current_actionability_projection or {}
    return _compare_transition(
        previous_projection.get("actionability_status"),
        current_projection.get("actionability_status"),
    )


def _threshold_scope_level(
    *,
    threshold_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
) -> str:
    threshold_status = str((threshold_projection or {}).get("threshold_status") or "threshold_free")
    domain_status = str((domain_scope_projection or {}).get("status") or "in_domain_scope")

    if domain_status in {"out_of_domain_scope", "escalation_required"} or threshold_status == "threshold_blocking":
        return "blocked"
    if domain_status == "in_domain_with_warning" or threshold_status == "threshold_warning":
        return "warning"
    return "neutral"


def compare_threshold_scope(
    *,
    previous_threshold_projection: Optional[Dict[str, Any]],
    current_threshold_projection: Optional[Dict[str, Any]],
    previous_domain_scope_projection: Optional[Dict[str, Any]],
    current_domain_scope_projection: Optional[Dict[str, Any]],
) -> str:
    previous_level = _threshold_scope_level(
        threshold_projection=previous_threshold_projection,
        domain_scope_projection=previous_domain_scope_projection,
    )
    current_level = _threshold_scope_level(
        threshold_projection=current_threshold_projection,
        domain_scope_projection=current_domain_scope_projection,
    )
    if previous_level == current_level:
        return "unchanged"
    return f"{previous_level}_to_{current_level}"


def _delta_state_severity(selection_state: Optional[Dict[str, Any]]) -> int:
    state = selection_state or {}
    output_contract = state.get("output_contract_projection") or {}
    case_summary = state.get("case_summary_projection") or {}
    actionability = state.get("actionability_projection") or {}
    invariant_projection = state.get("projection_invariant_projection") or {}
    domain_scope = state.get("domain_scope_projection") or {}
    threshold_projection = state.get("threshold_projection") or {}
    integrity_projection = state.get("parameter_integrity_projection") or {}
    active_blockers = set(str(item) for item in (case_summary.get("active_blockers") or []))
    output_status = str(output_contract.get("output_status") or "")
    actionability_status = str(actionability.get("actionability_status") or "")

    if not invariant_projection.get("invariant_ok", True) or "invariant_blocked" in active_blockers:
        return 6
    if output_status in {"withheld_domain_block", "withheld_escalation", "withheld_no_evidence"} or actionability_status in {"blocked", "escalation_required", "evidence_required"}:
        return 5
    if output_status == "withheld_review" or actionability_status in {"review_pending", "handoverable_restricted"}:
        return 4
    if output_status == "clarification_needed" or actionability_status == "input_required":
        return 3
    if _threshold_scope_level(
        threshold_projection=threshold_projection,
        domain_scope_projection=domain_scope,
    ) == "warning" or str(integrity_projection.get("integrity_status") or "") == "usable_with_warning":
        return 2
    if output_status == "governed_non_binding_result" and actionability_status == "result_available":
        return 0
    return 4


def _classify_delta_direction(
    *,
    previous_selection_state: Optional[Dict[str, Any]],
    current_selection_state: Optional[Dict[str, Any]],
    changed_keys: List[str],
) -> str:
    if not changed_keys:
        return "unchanged"

    previous_score = _delta_state_severity(previous_selection_state)
    current_score = _delta_state_severity(current_selection_state)

    if current_score < previous_score:
        return "improved"
    if current_score > previous_score:
        if current_score >= 5 and previous_score < 5:
            return "more_blocked"
        return "degraded"
    return "changed"


def build_state_delta_projection(
    *,
    previous_selection_state: Optional[Dict[str, Any]],
    current_selection_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare two structured states without introducing any new simulation layer."""
    previous_state = previous_selection_state or {}
    current_state = current_selection_state or {}
    previous_summary = previous_state.get("case_summary_projection") or {}
    current_summary = current_state.get("case_summary_projection") or {}
    previous_actionability = previous_state.get("actionability_projection") or {}
    current_actionability = current_state.get("actionability_projection") or {}
    previous_output_contract = previous_state.get("output_contract_projection") or {}
    current_output_contract = current_state.get("output_contract_projection") or {}
    previous_domain_scope = previous_state.get("domain_scope_projection") or {}
    current_domain_scope = current_state.get("domain_scope_projection") or {}
    previous_threshold = previous_state.get("threshold_projection") or {}
    current_threshold = current_state.get("threshold_projection") or {}
    previous_integrity = previous_state.get("parameter_integrity_projection") or {}
    current_integrity = current_state.get("parameter_integrity_projection") or {}
    previous_conflict = previous_state.get("conflict_status_projection") or {}
    current_conflict = current_state.get("conflict_status_projection") or {}
    previous_invariant = previous_state.get("projection_invariant_projection") or {}
    current_invariant = current_state.get("projection_invariant_projection") or {}

    case_status_delta = compare_case_status(previous_summary, current_summary)
    actionability_delta = compare_actionability(previous_actionability, current_actionability)
    threshold_scope_delta = compare_threshold_scope(
        previous_threshold_projection=previous_threshold,
        current_threshold_projection=current_threshold,
        previous_domain_scope_projection=previous_domain_scope,
        current_domain_scope_projection=current_domain_scope,
    )

    changed_statuses: Dict[str, Dict[str, Any]] = {}

    def record_change(key: str, previous_value: Any, current_value: Any, *, delta: Optional[str] = None) -> None:
        if previous_value == current_value:
            return
        payload: Dict[str, Any] = {
            "from": previous_value,
            "to": current_value,
        }
        if delta and delta != "unchanged":
            payload["delta"] = delta
        changed_statuses[key] = payload

    previous_active_blockers = list(previous_summary.get("active_blockers") or [])
    current_active_blockers = list(current_summary.get("active_blockers") or [])
    previous_blocked_actions = sorted(str(item) for item in (previous_actionability.get("blocked_actions") or []))
    current_blocked_actions = sorted(str(item) for item in (current_actionability.get("blocked_actions") or []))

    record_change(
        "invariant_ok",
        bool(previous_invariant.get("invariant_ok", True)),
        bool(current_invariant.get("invariant_ok", True)),
        delta=_compare_transition(
            bool(previous_invariant.get("invariant_ok", True)),
            bool(current_invariant.get("invariant_ok", True)),
        ),
    )
    record_change(
        "conflict_status",
        str(previous_conflict.get("status") or "no_conflict"),
        str(current_conflict.get("status") or "no_conflict"),
        delta=_compare_transition(
            previous_conflict.get("status") or "no_conflict",
            current_conflict.get("status") or "no_conflict",
        ),
    )
    record_change(
        "integrity_status",
        str(previous_integrity.get("integrity_status") or "normalized_ok"),
        str(current_integrity.get("integrity_status") or "normalized_ok"),
        delta=_compare_transition(
            previous_integrity.get("integrity_status") or "normalized_ok",
            current_integrity.get("integrity_status") or "normalized_ok",
        ),
    )
    record_change(
        "domain_scope_status",
        str(previous_domain_scope.get("status") or "in_domain_scope"),
        str(current_domain_scope.get("status") or "in_domain_scope"),
        delta=threshold_scope_delta,
    )
    record_change(
        "threshold_status",
        str(previous_threshold.get("threshold_status") or "threshold_free"),
        str(current_threshold.get("threshold_status") or "threshold_free"),
        delta=threshold_scope_delta,
    )
    record_change(
        "output_status",
        str(previous_output_contract.get("output_status") or ""),
        str(current_output_contract.get("output_status") or ""),
        delta=_compare_transition(
            previous_output_contract.get("output_status"),
            current_output_contract.get("output_status"),
        ),
    )
    record_change(
        "case_status",
        get_case_status(previous_summary),
        get_case_status(current_summary),
        delta=case_status_delta,
    )
    record_change(
        "actionability_status",
        str(previous_actionability.get("actionability_status") or ""),
        str(current_actionability.get("actionability_status") or ""),
        delta=actionability_delta,
    )
    record_change(
        "primary_allowed_action",
        get_primary_allowed_action(previous_actionability),
        get_primary_allowed_action(current_actionability),
        delta=_compare_transition(
            get_primary_allowed_action(previous_actionability),
            get_primary_allowed_action(current_actionability),
        ),
    )
    record_change(
        "next_step",
        get_next_case_step(previous_summary),
        get_next_case_step(current_summary),
        delta=_compare_transition(
            get_next_case_step(previous_summary),
            get_next_case_step(current_summary),
        ),
    )
    record_change(
        "next_expected_user_action",
        get_next_expected_user_action(previous_actionability),
        get_next_expected_user_action(current_actionability),
        delta=_compare_transition(
            get_next_expected_user_action(previous_actionability),
            get_next_expected_user_action(current_actionability),
        ),
    )
    record_change(
        "active_blockers",
        previous_active_blockers,
        current_active_blockers,
        delta=_compare_transition(
            "|".join(previous_active_blockers),
            "|".join(current_active_blockers),
        ),
    )
    record_change(
        "blocked_actions",
        previous_blocked_actions,
        current_blocked_actions,
        delta=_compare_transition(
            "|".join(previous_blocked_actions),
            "|".join(current_blocked_actions),
        ),
    )

    changed_keys = [
        key for key in _STATE_DELTA_FIELD_ORDER
        if key in changed_statuses
    ]

    if "invariant_ok" in changed_statuses:
        primary_delta_reason = "invariant_status_changed"
    elif "conflict_status" in changed_statuses:
        primary_delta_reason = "conflict_status_changed"
    elif "integrity_status" in changed_statuses:
        primary_delta_reason = "integrity_status_changed"
    elif "domain_scope_status" in changed_statuses or "threshold_status" in changed_statuses:
        primary_delta_reason = "threshold_scope_changed"
    elif "output_status" in changed_statuses:
        primary_delta_reason = "output_status_changed"
    elif "case_status" in changed_statuses:
        primary_delta_reason = "case_status_changed"
    elif "actionability_status" in changed_statuses or "primary_allowed_action" in changed_statuses:
        primary_delta_reason = "actionability_changed"
    elif "next_step" in changed_statuses or "next_expected_user_action" in changed_statuses:
        primary_delta_reason = "next_step_changed"
    elif "active_blockers" in changed_statuses:
        primary_delta_reason = "blocker_set_changed"
    elif "blocked_actions" in changed_statuses:
        primary_delta_reason = "blocked_actions_changed"
    else:
        primary_delta_reason = "no_relevant_change"

    return {
        "changed_keys": changed_keys,
        "changed_statuses": changed_statuses,
        "primary_delta_reason": primary_delta_reason,
        "delta_direction": _classify_delta_direction(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
            changed_keys=changed_keys,
        ),
    }


def build_structured_snapshot(
    selection_state: Optional[Dict[str, Any]],
    *,
    asserted_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a small stable snapshot contract for downstream structured consumers."""
    state = selection_state or {}
    output_contract = state.get("output_contract_projection") or {}
    trace_projection = state.get("state_trace_audit_projection") or build_state_trace_audit_projection(
        selection_status=str(state.get("selection_status") or ""),
        recommendation_artifact=state.get("recommendation_artifact"),
        review_escalation_projection=state.get("review_escalation_projection"),
        clarification_projection=state.get("clarification_projection"),
        conflict_status_projection=state.get("conflict_status_projection"),
        parameter_integrity_projection=state.get("parameter_integrity_projection"),
        domain_scope_projection=state.get("domain_scope_projection"),
        output_contract_projection=output_contract,
        projection_invariant_projection=state.get("projection_invariant_projection"),
    )
    case_summary = state.get("case_summary_projection") or build_case_summary_projection(
        asserted_state=asserted_state,
        output_contract_projection=output_contract,
        clarification_projection=state.get("clarification_projection"),
        state_trace_audit_projection=trace_projection,
    )
    actionability = state.get("actionability_projection") or build_actionability_projection(
        case_summary_projection=case_summary,
        output_contract_projection=output_contract,
        review_escalation_projection=state.get("review_escalation_projection"),
        clarification_projection=state.get("clarification_projection"),
        projection_invariant_projection=state.get("projection_invariant_projection"),
    )

    return {
        "case_status": get_case_status(case_summary),
        "output_status": str(output_contract.get("output_status") or ""),
        "primary_reason": get_primary_trace_reason(trace_projection),
        "next_step": get_next_case_step(case_summary),
        "primary_allowed_action": get_primary_allowed_action(actionability),
        "active_blockers": list(case_summary.get("active_blockers") or []),
    }


def compare_structured_snapshots(
    previous_snapshot: Optional[Dict[str, Any]],
    current_snapshot: Optional[Dict[str, Any]],
    *,
    delta_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a compact comparison contract between two structured snapshots."""
    previous = previous_snapshot or {}
    current = current_snapshot or {}
    delta = delta_projection or {}

    previous_blockers = list(previous.get("active_blockers") or [])
    current_blockers = list(current.get("active_blockers") or [])
    previous_blocker_set = set(str(item) for item in previous_blockers)
    current_blocker_set = set(str(item) for item in current_blockers)

    previous_action = str(previous.get("primary_allowed_action") or "")
    current_action = str(current.get("primary_allowed_action") or "")
    action_changed = previous_action != current_action

    return {
        "from_status": str(previous.get("case_status") or ""),
        "to_status": str(current.get("case_status") or ""),
        "changed_actions": {
            "from_primary_allowed_action": previous_action,
            "to_primary_allowed_action": current_action,
            "action_changed": action_changed,
        },
        "changed_blockers": {
            "added": sorted(current_blocker_set - previous_blocker_set),
            "removed": sorted(previous_blocker_set - current_blocker_set),
        },
        "primary_delta_reason": str(delta.get("primary_delta_reason") or "no_relevant_change"),
        "delta_direction": str(delta.get("delta_direction") or "unchanged"),
    }


_STRUCTURED_API_EXPOSURE_KEYS: tuple[str, ...] = (
    "case_status",
    "output_status",
    "next_step",
    "primary_allowed_action",
    "active_blockers",
)


def _normalize_structured_api_exposure_value(key: str, value: Any) -> Any:
    if key == "active_blockers":
        return [str(item) for item in (value or [])]
    return str(value or "")


def _assert_structured_api_exposure_contract(exposure: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Enforce the tiny public structured_state contract before API exposure."""
    if exposure is None:
        return None

    normalized = {
        key: _normalize_structured_api_exposure_value(key, exposure.get(key))
        for key in _STRUCTURED_API_EXPOSURE_KEYS
    }

    if set(normalized.keys()) != set(_STRUCTURED_API_EXPOSURE_KEYS):
        raise ValueError("structured_state exposure keys drifted from the allowlist")
    if not isinstance(normalized["active_blockers"], list):
        raise ValueError("structured_state.active_blockers must be a list")
    if any(not isinstance(item, str) for item in normalized["active_blockers"]):
        raise ValueError("structured_state.active_blockers must contain only strings")
    for key in _STRUCTURED_API_EXPOSURE_KEYS:
        if key == "active_blockers":
            continue
        if not isinstance(normalized[key], str):
            raise ValueError(f"structured_state.{key} must be a string")

    return normalized


def _minimal_structured_snapshot_contract(selection_state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return only the explicit snapshot contract that is approved for API minimization."""
    state = selection_state or {}
    snapshot = state.get("structured_snapshot_contract")
    if not isinstance(snapshot, dict):
        return None
    return snapshot


def _minimal_structured_snapshot_from_case_state(
    case_state: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    state = case_state or {}
    governance_state = dict(state.get("governance_state") or {})
    rfq_state = dict(state.get("rfq_state") or {})
    qualified_action_gate = dict(state.get("qualified_action_gate") or {})
    release_status = str(governance_state.get("release_status") or "")
    rfq_admissibility = str(
        rfq_state.get("rfq_admissibility")
        or governance_state.get("rfq_admissibility")
        or ""
    )
    review_required = bool(governance_state.get("review_required", False))

    if review_required:
        blockers = list(rfq_state.get("blocking_reasons") or rfq_state.get("blockers") or [])
        if "review_pending" not in blockers:
            blockers = ["review_pending", *blockers]
        return {
            "case_status": "withheld_review",
            "output_status": "withheld_review",
            "primary_reason": "review_pending",
            "next_step": "human_review",
            "primary_allowed_action": "await_review",
            "active_blockers": blockers,
        }

    if rfq_admissibility == "ready" and release_status == "rfq_ready":
        return {
            "case_status": "governed_non_binding_result",
            "output_status": "governed_non_binding_result",
            "primary_reason": "governed_releasable_result",
            "next_step": "confirmed_result_review",
            "primary_allowed_action": (
                "prepare_handover" if bool(qualified_action_gate.get("allowed", False))
                else "consume_governed_result"
            ),
            "active_blockers": list(rfq_state.get("blocking_reasons") or rfq_state.get("blockers") or []),
        }

    return None


def build_structured_api_exposure(
    selection_state: Optional[Dict[str, Any]],
    *,
    case_state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return the minimal stable structured exposure block for API/downstream use."""
    snapshot = _minimal_structured_snapshot_from_case_state(case_state) or _minimal_structured_snapshot_contract(selection_state)
    if not snapshot:
        return None

    return _assert_structured_api_exposure_contract({
        key: list(snapshot.get(key) or []) if key == "active_blockers" else snapshot.get(key)
        for key in _STRUCTURED_API_EXPOSURE_KEYS
    })


def _can_surface_governed_rationale_reply(
    *,
    artifact: Dict[str, Any],
    output_contract: Dict[str, Any],
    case_summary: Dict[str, Any],
    selection_state: Dict[str, Any],
    review_state: Optional[Dict[str, Any]] = None,
) -> bool:
    rationale_summary = artifact.get("rationale_summary")
    if not isinstance(rationale_summary, str) or not rationale_summary.strip():
        return False
    if str(output_contract.get("output_status") or "") != "governed_non_binding_result":
        return False
    if bool(output_contract.get("suppress_recommendation_details")):
        return False
    if str(selection_state.get("release_status") or "") != "rfq_ready":
        return False
    if str(selection_state.get("rfq_admissibility") or "") != "ready":
        return False
    if bool(selection_state.get("output_blocked", True)):
        return False
    if get_case_status(case_summary) != "governed_non_binding_result":
        return False
    if has_active_blockers(case_summary):
        return False
    if bool((review_state or {}).get("review_required")):
        return False
    return True


def _build_recommendation_rationale_summary(
    *,
    review_escalation_projection: Optional[Dict[str, Any]],
    clarification_projection: Optional[Dict[str, Any]],
    evidence_provenance_projection: Optional[Dict[str, Any]],
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    unit_normalization_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    selection_status: str,
    release_status: str,
    rfq_admissibility: str,
    readiness_status: str,
    blocking_reason: str,
    candidate_projection: Optional[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> str:
    evidence_note = _build_evidence_binding_note(evidence_provenance_projection)
    conflict_note = _build_conflict_correction_note(conflict_status_projection)
    integrity_note = _build_integrity_note(parameter_integrity_projection, unit_normalization_projection)
    domain_scope_note = _build_domain_scope_note(domain_scope_projection)
    if candidate_projection:
        candidate_label = (
            candidate_projection.get("grade_name")
            or candidate_projection.get("candidate_id")
            or candidate_projection.get("material_family")
            or "unbekannter_kandidat"
        )
        candidate_id = candidate_projection.get("candidate_id") or candidate_label
        evidence_refs = list(candidate_projection.get("evidence_refs") or [])
        evidence_text = ", ".join(evidence_refs) if evidence_refs else "keine"
        prefix_parts = [note for note in (conflict_note, integrity_note, domain_scope_note) if note]
        prefix = " ".join(prefix_parts)
        return ((f"{prefix} " if prefix else "")) + (
            f"{NEUTRAL_SCOPE_REPLY} "
            f"Technischer Orientierungsrahmen: {candidate_label}. "
            f"{evidence_note} "
            "Kein verbindlicher Freigabeschluss; Herstellervalidierung bleibt erforderlich."
        )

    projection_status = (review_escalation_projection or {}).get("status")
    if release_status == "precheck_only":
        return f"{PRECHECK_ONLY_REPLY} {evidence_note}"
    if release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
        return f"{MANUFACTURER_VALIDATION_REPLY} {evidence_note}"
    if projection_status == "review_pending":
        return f"{REVIEW_PENDING_REPLY} {evidence_note}"
    if projection_status == "ambiguous_but_reviewable":
        return f"{AMBIGUOUS_CANDIDATE_REPLY} {evidence_note}"
    if projection_status == "escalation_needed":
        if conflict_note:
            return f"{conflict_note} {evidence_note}"
        if integrity_note:
            return f"{integrity_note} {evidence_note}"
        if domain_scope_note:
            return f"{domain_scope_note} {evidence_note}"
        return f"{ESCALATION_NEEDED_REPLY} {evidence_note}"
    if readiness_status == "demo_data_quarantine":
        return f"{DEMO_DATA_QUARANTINE_REPLY} {evidence_note}"
    if readiness_status == "evidence_missing":
        return f"{EVIDENCE_MISSING_REPLY} {evidence_note}"
    if readiness_status == "review_pending":
        return f"{REVIEW_PENDING_REPLY} {evidence_note}"
    if readiness_status == "integrity_unusable":
        if integrity_note:
            return f"{integrity_note} {evidence_note}"
        return f"{INTEGRITY_UNUSABLE_REPLY} {evidence_note}"
    if readiness_status == "domain_scope_blocked":
        if domain_scope_note:
            return f"{domain_scope_note} {evidence_note}"
        return f"{THRESHOLD_ESCALATION_REPLY} {evidence_note}"
    if readiness_status == "conflict_unresolved":
        if conflict_note:
            return f"{conflict_note} {evidence_note}"
        return f"{UNRESOLVED_CONFLICT_REPLY} {evidence_note}"
    if selection_status == "multiple_viable_candidates":
        return f"{AMBIGUOUS_CANDIDATE_REPLY} {evidence_note}"
    if selection_status == "blocked_no_candidates":
        return f"{NO_CANDIDATES_REPLY} {evidence_note}"
    if selection_status == "blocked_no_viable_candidates":
        return f"{NO_VIABLE_CANDIDATES_REPLY} {evidence_note}"
    if selection_status == "blocked_missing_required_inputs" or readiness_status == "insufficient_inputs":
        base = f"{_build_missing_data_reply(asserted_state, working_profile, clarification_projection)}\n\n{evidence_note}"
        if integrity_note:
            return f"{integrity_note} {base}"
        return base
    if blocking_reason:
        if conflict_note:
            return f"{conflict_note} {evidence_note}"
        if integrity_note:
            return f"{integrity_note} {evidence_note}"
        if domain_scope_note:
            return f"{domain_scope_note} {evidence_note}"
        return f"{SAFEGUARDED_WITHHELD_REPLY} {evidence_note}"
    base_text = f"{_build_missing_inputs_text(asserted_state, working_profile)}\n\n{evidence_note}"
    if conflict_note:
        return f"{conflict_note} {base_text}"
    if integrity_note:
        return f"{integrity_note} {base_text}"
    if domain_scope_note:
        return f"{domain_scope_note} {base_text}"
    return base_text


def _resolve_recommendation_projection(
    *,
    selection_status: str,
    winner_candidate_id: Optional[str],
    candidates: List[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]],
    governance_state: Optional[Dict[str, Any]],
    review_state: Optional[Dict[str, Any]],
    evidence_available: bool,
    demo_data_present: bool,
    conflict_status_projection: Optional[Dict[str, Any]],
    parameter_integrity_projection: Optional[Dict[str, Any]],
    domain_scope_projection: Optional[Dict[str, Any]],
    working_profile: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Dict[str, Any]], str, str]:
    readiness = evaluate_output_readiness(
        asserted_state,
        governance_state,
        review_state=review_state,
        evidence_available=evidence_available,
        demo_data_present=demo_data_present,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
    )

    if not readiness.releasable:
        return None, readiness.status, readiness.blocking_reason

    if selection_status == "multiple_viable_candidates":
        blocking_reason = (
            "Multiple viable candidates remain after deterministic checks; "
            "no single governed candidate projection is available."
        )
        return None, "candidate_ambiguity", blocking_reason

    candidate_projection = _build_candidate_projection(candidates, winner_candidate_id)
    if candidate_projection is None:
        blocking_reason = "No single governed candidate projection is available."
        return None, "no_governed_candidate", blocking_reason

    return candidate_projection, readiness.status, readiness.blocking_reason


def _normalize_temperature(asserted_state: Dict[str, Any]) -> Optional[PhysicalParameter]:
    temperature_value = (asserted_state or {}).get("operating_conditions", {}).get("temperature")
    if temperature_value is None:
        return None
    try:
        return PhysicalParameter(value=float(temperature_value), unit="C")
    except Exception:
        return None


def _normalize_pressure(asserted_state: Dict[str, Any]) -> Optional[PhysicalParameter]:
    pressure_value = (asserted_state or {}).get("operating_conditions", {}).get("pressure")
    if pressure_value is None:
        return None
    try:
        return PhysicalParameter(value=float(pressure_value), unit="bar")
    except Exception:
        return None


def _classify_candidates(
    candidates: List[Dict[str, Any]],
    relevant_fact_cards: List[Dict[str, Any]],
    asserted_state: Dict[str, Any],
) -> tuple[List[str], List[Dict[str, str]]]:
    temperature = _normalize_temperature(asserted_state)
    pressure = _normalize_pressure(asserted_state)

    cards_by_evidence_id = {
        (card.get("evidence_id") or card.get("id")): {
            "card": card,
            "normalized_evidence": card.get("normalized_evidence") or normalize_fact_card_evidence(card),
        }
        for card in relevant_fact_cards
        if (card.get("evidence_id") or card.get("id"))
    }
    viable_candidate_ids: List[str] = []
    blocked_candidates: List[Dict[str, str]] = []

    for candidate in candidates:
        supporting_profiles: List[MaterialPhysicalProfile] = []
        for evidence_ref in candidate.get("evidence_refs", []):
            entry = cards_by_evidence_id.get(evidence_ref)
            if not entry:
                continue
            card = dict(entry["card"])
            card["normalized_evidence"] = entry["normalized_evidence"]
            profile = MaterialPhysicalProfile.from_fact_card(card)
            if profile and profile.material_id.upper() == candidate.get("material_family", "").upper():
                supporting_profiles.append(profile)

        if not supporting_profiles:
            candidate["viability_status"] = "blocked_missing_required_inputs"
            candidate["block_reason"] = "blocked_missing_required_inputs"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_missing_required_inputs",
                }
            )
            continue

        requires_temperature = True
        requires_pressure = any(getattr(profile, "pressure_max", None) is not None for profile in supporting_profiles)

        if requires_temperature and temperature is None:
            candidate["viability_status"] = "blocked_missing_required_inputs"
            candidate["block_reason"] = "blocked_missing_required_inputs"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_missing_required_inputs",
                }
            )
            continue

        if requires_pressure and pressure is None:
            candidate["viability_status"] = "blocked_missing_required_inputs"
            candidate["block_reason"] = "blocked_missing_required_inputs"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_missing_required_inputs",
                }
            )
            continue

        has_temperature_conflict = any(
            not MaterialValidator(profile).validate_temperature(temperature)
            for profile in supporting_profiles
        )
        if has_temperature_conflict:
            candidate["viability_status"] = "blocked_temperature_conflict"
            candidate["block_reason"] = "blocked_temperature_conflict"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_temperature_conflict",
                }
            )
            continue

        has_pressure_conflict = any(
            getattr(profile, "pressure_max", None) is not None
            and not MaterialValidator(profile).validate_pressure(pressure)
            for profile in supporting_profiles
        )
        if has_pressure_conflict:
            candidate["viability_status"] = "blocked_pressure_conflict"
            candidate["block_reason"] = "blocked_pressure_conflict"
            blocked_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "block_reason": "blocked_pressure_conflict",
                }
            )
            continue

        candidate["viability_status"] = "viable"
        candidate["block_reason"] = None
        viable_candidate_ids.append(candidate["candidate_id"])

    return viable_candidate_ids, blocked_candidates


def build_selection_state(
    relevant_fact_cards: List[Dict[str, Any]],
    cycle_state: Dict[str, Any],
    governance_state: Optional[Dict[str, Any]] = None,
    asserted_state: Optional[Dict[str, Any]] = None,
    *,
    review_state: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    demo_data_present: bool = False,
    working_profile: Optional[Dict[str, Any]] = None,
    observed_state: Optional[Dict[str, Any]] = None,
    normalized_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidates_by_id: Dict[str, Dict[str, Any]] = {}
    evidence_basis: List[str] = []
    governance_state = governance_state or {}
    asserted_state = asserted_state or {}

    for card in relevant_fact_cards:
        normalized_evidence = card.get("normalized_evidence") or normalize_fact_card_evidence(card)
        family = normalized_evidence.get("material_family")
        if not family:
            continue

        filler_hint = normalized_evidence.get("filler_hint")
        grade_name = normalized_evidence.get("grade_name")
        manufacturer_name = normalized_evidence.get("manufacturer_name")
        kind = normalized_evidence.get("candidate_kind") or _candidate_kind(family, filler_hint, grade_name, manufacturer_name)
        candidate_id = _candidate_id(family, filler_hint, grade_name, manufacturer_name)
        evidence_id = card.get("evidence_id") or card.get("id")
        if not evidence_id:
            continue

        existing = candidates_by_id.get(candidate_id)
        if not existing:
            existing = {
                "candidate_id": candidate_id,
                "candidate_kind": kind,
                "material_family": family,
                "filler_hint": filler_hint,
                "grade_name": grade_name,
                "manufacturer_name": manufacturer_name,
                "viability_status": "blocked_missing_required_inputs",
                "block_reason": None,
                "evidence_refs": [],
                "_best_rank": card.get("retrieval_rank", 9999),
            }
            candidates_by_id[candidate_id] = existing

        if evidence_id not in existing["evidence_refs"]:
            existing["evidence_refs"].append(evidence_id)
        existing["_best_rank"] = min(existing["_best_rank"], card.get("retrieval_rank", 9999))
        if evidence_id not in evidence_basis:
            evidence_basis.append(evidence_id)

    ordered_candidates = sorted(candidates_by_id.values(), key=lambda candidate: candidate["candidate_id"])
    for candidate in ordered_candidates:
        candidate.pop("_best_rank", None)

    viable_candidate_ids, blocked_candidates = _classify_candidates(
        ordered_candidates,
        relevant_fact_cards,
        asserted_state,
    )
    winner_candidate_id = viable_candidate_ids[0] if len(viable_candidate_ids) == 1 else None
    if not ordered_candidates:
        selection_status = "blocked_no_candidates"
    elif winner_candidate_id:
        selection_status = "winner_selected"
    elif viable_candidate_ids:
        selection_status = "multiple_viable_candidates"
    elif any(block["block_reason"] == "blocked_missing_required_inputs" for block in blocked_candidates):
        selection_status = "blocked_missing_required_inputs"
    else:
        selection_status = "blocked_no_viable_candidates"
    governance_release_status = governance_state.get("release_status", "inadmissible")
    governance_rfq_admissibility = governance_state.get("rfq_admissibility", "inadmissible")
    specificity_level = governance_state.get("specificity_level", "family_only")
    evidence_provenance_projection = project_evidence_provenance_state(
        relevant_fact_cards,
        evidence_basis,
    )
    conflict_status_projection = project_conflict_status(
        observed_state=observed_state,
        normalized_state=normalized_state,
        governance_state=governance_state,
        asserted_state=asserted_state,
    )
    unit_normalization_projection = project_unit_normalization_status(
        normalized_state=normalized_state,
        asserted_state=asserted_state,
    )
    parameter_integrity_projection = build_parameter_integrity_projection(
        unit_normalization_projection
    )
    threshold_projection = project_threshold_status(
        asserted_state=asserted_state,
        working_profile=working_profile,
    )
    domain_scope_projection = project_domain_scope_status(threshold_projection)
    correction_projection = build_correction_projection(conflict_status_projection)
    effective_evidence_available = bool(
        evidence_available and evidence_provenance_projection.get("status") != "no_evidence"
    )
    candidate_projection, readiness_status, blocking_reason = _resolve_recommendation_projection(
        selection_status=selection_status,
        winner_candidate_id=winner_candidate_id,
        candidates=ordered_candidates,
        asserted_state=asserted_state,
        governance_state=governance_state,
        review_state=review_state,
        evidence_available=effective_evidence_available,
        demo_data_present=demo_data_present,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        working_profile=working_profile,
    )
    review_escalation_projection = project_review_escalation_state(
        selection_status=selection_status,
        readiness_status=readiness_status,
        blocking_reason=blocking_reason,
        viable_candidate_ids=viable_candidate_ids,
        asserted_state=asserted_state,
        review_state=review_state,
        evidence_available=effective_evidence_available,
        demo_data_present=demo_data_present,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
    )
    clarification_projection = build_clarification_projection(
        asserted_state=asserted_state,
        working_profile=working_profile,
        review_escalation_projection=review_escalation_projection,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
    )
    rationale_summary = _build_recommendation_rationale_summary(
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        unit_normalization_projection=unit_normalization_projection,
        domain_scope_projection=domain_scope_projection,
        selection_status=selection_status,
        release_status=governance_release_status,
        rfq_admissibility=governance_rfq_admissibility,
        readiness_status=readiness_status,
        blocking_reason=blocking_reason,
        candidate_projection=candidate_projection,
        asserted_state=asserted_state,
        working_profile=working_profile,
    )
    output_blocked = candidate_projection is None
    trace_refs = list(evidence_basis)
    cycle_id = cycle_state.get("analysis_cycle_id")
    if cycle_id:
        trace_refs.append(cycle_id)

    recommendation_artifact = _build_recommendation_artifact(
        selection_status=selection_status,
        winner_candidate_id=winner_candidate_id,
        candidate_projection=candidate_projection,
        candidates=ordered_candidates,
        viable_candidate_ids=viable_candidate_ids,
        blocked_candidates=blocked_candidates,
        evidence_basis=evidence_basis,
        evidence_status=str(evidence_provenance_projection.get("status") or "no_evidence"),
        provenance_refs=list(evidence_provenance_projection.get("provenance_refs") or []),
        conflict_status=str(conflict_status_projection.get("status") or "no_conflict"),
        integrity_status=str(parameter_integrity_projection.get("integrity_status") or "normalized_ok"),
        domain_scope_status=str(domain_scope_projection.get("status") or "in_domain_scope"),
        threshold_status=str(threshold_projection.get("threshold_status") or "threshold_free"),
        release_status=governance_release_status,
        rfq_admissibility=governance_rfq_admissibility,
        specificity_level=specificity_level,
        output_blocked=output_blocked,
        readiness_status=readiness_status,
        blocking_reason=blocking_reason,
        rationale_summary=rationale_summary,
        trace_refs=trace_refs,
    )
    user_facing_output_projection = project_user_facing_output_status(
        selection_status=selection_status,
        recommendation_artifact=recommendation_artifact,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        domain_scope_projection=domain_scope_projection,
    )
    output_contract_projection = build_output_contract_projection(
        user_facing_output_projection=user_facing_output_projection,
        recommendation_artifact=recommendation_artifact,
        clarification_projection=clarification_projection,
        review_escalation_projection=review_escalation_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        threshold_projection=threshold_projection,
    )
    projection_invariant_projection = project_projection_invariants(
        recommendation_artifact=recommendation_artifact,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        evidence_provenance_projection=evidence_provenance_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract_projection,
    )
    if not projection_invariant_projection.get("invariant_ok", True):
        recommendation_artifact, user_facing_output_projection, output_contract_projection, output_blocked = _apply_invariant_safeguards(
            recommendation_artifact=recommendation_artifact,
            user_facing_output_projection=user_facing_output_projection,
            output_contract_projection=output_contract_projection,
            projection_invariant_projection=projection_invariant_projection,
        )
    state_trace_audit_projection = build_state_trace_audit_projection(
        selection_status=selection_status,
        recommendation_artifact=recommendation_artifact,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        conflict_status_projection=conflict_status_projection,
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract_projection,
        projection_invariant_projection=projection_invariant_projection,
    )
    case_summary_projection = build_case_summary_projection(
        asserted_state=asserted_state,
        output_contract_projection=output_contract_projection,
        clarification_projection=clarification_projection,
        state_trace_audit_projection=state_trace_audit_projection,
    )
    actionability_projection = build_actionability_projection(
        case_summary_projection=case_summary_projection,
        output_contract_projection=output_contract_projection,
        review_escalation_projection=review_escalation_projection,
        clarification_projection=clarification_projection,
        projection_invariant_projection=projection_invariant_projection,
    )
    structured_snapshot_contract = build_structured_snapshot(
        {
            "selection_status": selection_status,
            "recommendation_artifact": recommendation_artifact,
            "review_escalation_projection": review_escalation_projection,
            "clarification_projection": clarification_projection,
            "conflict_status_projection": conflict_status_projection,
            "parameter_integrity_projection": parameter_integrity_projection,
            "domain_scope_projection": domain_scope_projection,
            "output_contract_projection": output_contract_projection,
            "projection_invariant_projection": projection_invariant_projection,
            "state_trace_audit_projection": state_trace_audit_projection,
            "case_summary_projection": case_summary_projection,
            "actionability_projection": actionability_projection,
        },
        asserted_state=asserted_state,
    )

    return {
        "selection_status": selection_status,
        "candidates": ordered_candidates,
        "viable_candidate_ids": viable_candidate_ids,
        "blocked_candidates": blocked_candidates,
        "winner_candidate_id": winner_candidate_id,
        "recommendation_artifact": recommendation_artifact,
        "evidence_provenance_projection": evidence_provenance_projection,
        "conflict_status_projection": conflict_status_projection,
        "unit_normalization_projection": unit_normalization_projection,
        "parameter_integrity_projection": parameter_integrity_projection,
        "threshold_projection": threshold_projection,
        "domain_scope_projection": domain_scope_projection,
        "correction_projection": correction_projection,
        "review_escalation_projection": review_escalation_projection,
        "clarification_projection": clarification_projection,
        "user_facing_output_projection": user_facing_output_projection,
        "output_contract_projection": output_contract_projection,
        "projection_invariant_projection": projection_invariant_projection,
        "state_trace_audit_projection": state_trace_audit_projection,
        "case_summary_projection": case_summary_projection,
        "actionability_projection": actionability_projection,
        "structured_snapshot_contract": structured_snapshot_contract,
        "release_status": governance_release_status,
        "rfq_admissibility": governance_rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
    }


def build_final_reply(
    selection_state: Dict[str, Any],
    *,
    coverage_status: Optional[str] = None,
    known_unknowns: Optional[List[str]] = None,
    demo_data_present: bool = False,
    review_required: bool = False,
    review_reason: str = "",
    asserted_state: Optional[Dict[str, Any]] = None,
    working_profile: Optional[Dict[str, Any]] = None,
    evidence_available: bool = True,
    review_state: Optional[Dict[str, Any]] = None,
    case_state: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the governed structured-path reply and append a deterministic boundary block.

    Phase 1B PATCH 3: core_reply selection is now driven by evaluate_output_readiness(),
    making each reply class explicitly tied to the corresponding readiness status gate.
    The boundary block is ALWAYS appended — never produced by the LLM.

    Reply class hierarchy (first match wins):
    1. Artifact misaligned           → SAFEGUARDED_WITHHELD_REPLY
    2. demo_data_quarantine          → DEMO_DATA_QUARANTINE_REPLY
    3. evidence_missing              → EVIDENCE_MISSING_REPLY
    4. review_pending                → REVIEW_PENDING_REPLY
    5. governance_blocked            → release-status-specific reply
    6. insufficient_inputs           → selection-status-specific reply
    7. releasable                    → NEUTRAL_SCOPE_REPLY
    """
    artifact = selection_state.get("recommendation_artifact") or {}
    review_projection = selection_state.get("review_escalation_projection") or {}
    clarification_projection = selection_state.get("clarification_projection") or {}
    correction_projection = selection_state.get("correction_projection") or {}
    parameter_integrity_projection = selection_state.get("parameter_integrity_projection") or {}
    unit_normalization_projection = selection_state.get("unit_normalization_projection") or {}
    domain_scope_projection = selection_state.get("domain_scope_projection") or {}
    output_contract = selection_state.get("output_contract_projection") or {}
    state_trace_audit = selection_state.get("state_trace_audit_projection") or build_state_trace_audit_projection(
        selection_status=str(selection_state.get("selection_status") or ""),
        recommendation_artifact=artifact,
        review_escalation_projection=review_projection,
        clarification_projection=clarification_projection,
        conflict_status_projection=selection_state.get("conflict_status_projection"),
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract,
        projection_invariant_projection=selection_state.get("projection_invariant_projection"),
    )
    case_summary = selection_state.get("case_summary_projection") or build_case_summary_projection(
        asserted_state=asserted_state,
        output_contract_projection=output_contract,
        clarification_projection=clarification_projection,
        state_trace_audit_projection=state_trace_audit,
    )
    actionability = selection_state.get("actionability_projection")
    canonical_case_state = dict(case_state or {})
    canonical_dispatch_source = _resolve_runtime_dispatch_source(canonical_case_state)
    canonical_result_contract = dict(canonical_case_state.get("result_contract") or {})
    canonical_requirement_class = dict(canonical_case_state.get("requirement_class") or {})
    canonical_rfq_state = dict(canonical_case_state.get("rfq_state") or {})
    canonical_rfq_dispatch = dict(canonical_rfq_state.get("rfq_dispatch") or {})
    canonical_matching_state = dict(canonical_case_state.get("matching_state") or {})
    canonical_matching_outcome = dict(
        canonical_matching_state.get("matching_outcome")
        or canonical_case_state.get("matching_outcome")
        or {}
    )
    canonical_recipient_selection = dict(
        canonical_case_state.get("recipient_selection")
        or canonical_rfq_state.get("recipient_selection")
        or {}
    )
    invariant_projection = selection_state.get("projection_invariant_projection") or project_projection_invariants(
        recommendation_artifact=artifact,
        review_escalation_projection=review_projection,
        clarification_projection=clarification_projection,
        evidence_provenance_projection=selection_state.get("evidence_provenance_projection"),
        conflict_status_projection=selection_state.get("conflict_status_projection"),
        parameter_integrity_projection=parameter_integrity_projection,
        domain_scope_projection=domain_scope_projection,
        output_contract_projection=output_contract,
    )
    if not _artifact_is_aligned(selection_state, artifact):
        core_reply = SAFEGUARDED_WITHHELD_REPLY
    elif get_primary_trace_reason(state_trace_audit) == "invariant_blocked" or not invariant_projection.get("invariant_ok", True):
        core_reply = INVARIANT_BLOCKED_REPLY
    elif _can_surface_governed_rationale_reply(
        artifact=artifact,
        output_contract=output_contract,
        case_summary=case_summary,
        selection_state=selection_state,
        review_state=review_state,
    ):
        core_reply = str(artifact["rationale_summary"]).strip()
    else:
        release_status = (
            canonical_result_contract.get("release_status")
            or selection_state.get("release_status")
        )
        rfq_admissibility = (
            canonical_rfq_state.get("rfq_admissibility")
            or canonical_result_contract.get("rfq_admissibility")
            or selection_state.get("rfq_admissibility")
        )
        output_blocked = bool(selection_state.get("output_blocked", True))
        specificity_level = (
            canonical_requirement_class.get("specificity_level")
            or canonical_result_contract.get("specificity_level")
            or selection_state.get("specificity_level", "family_only")
        )
        output_status = str(output_contract.get("output_status") or "")
        canonical_dispatch_ready = bool(canonical_dispatch_source.get("dispatch_ready", False))

        # ---- Phase 1B PATCH 3: readiness-driven routing ----
        #
        # Priority order:
        # 1. Governance-specific release states (set by governance firewall, not input gate)
        # 2. Demo data quarantine / evidence missing (evidence-layer blockers)
        # 3. Review pending (HITL layer blocker)
        # 4. Selection-specific blocked states (no candidates, no viable, missing inputs)
        # 5. Releasable → NEUTRAL_SCOPE_REPLY
        # 6. Fallback → SAFEGUARDED_WITHHELD_REPLY
        #
        # Governance-specific states are checked BEFORE evaluate_output_readiness()
        # because they represent authoritative governance decisions that supersede
        # input-completeness checks (governance may fire even without full params).

        if release_status == "precheck_only":
            core_reply = PRECHECK_ONLY_REPLY
        elif release_status == "manufacturer_validation_required" or rfq_admissibility == "provisional":
            core_reply = MANUFACTURER_VALIDATION_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "no_action_until_clarified":
            core_reply = INVARIANT_BLOCKED_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "provide_missing_input":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif actionability and get_primary_allowed_action(actionability) == "obtain_qualified_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "await_review":
            core_reply = REVIEW_PENDING_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "prepare_handover":
            if "candidate_ambiguity" in list(case_summary.get("active_blockers") or []):
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif actionability and get_primary_allowed_action(actionability) == "consume_governed_result" and _can_surface_governed_rationale_reply(
            artifact=artifact,
            output_contract=output_contract,
            case_summary=case_summary,
            selection_state=selection_state,
            review_state=review_state,
        ):
            core_reply = str(artifact["rationale_summary"]).strip()
        elif actionability and get_primary_allowed_action(actionability) == "escalate_engineering":
            if correction_projection.get("conflict_still_open") or (selection_state.get("conflict_status_projection") or {}).get("conflict_still_open"):
                core_reply = _build_conflict_correction_note(
                    selection_state.get("conflict_status_projection")
                ) or ESCALATION_NEEDED_REPLY
            elif parameter_integrity_projection.get("integrity_status") == "unusable_until_clarified":
                core_reply = _build_integrity_note(
                    parameter_integrity_projection,
                    unit_normalization_projection,
                ) or ESCALATION_NEEDED_REPLY
            elif domain_scope_projection.get("status") in {"out_of_domain_scope", "escalation_required"}:
                core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
            else:
                core_reply = ESCALATION_NEEDED_REPLY
        elif get_case_status(case_summary) == "clarification_needed":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif get_case_status(case_summary) == "withheld_no_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif get_case_status(case_summary) == "withheld_review":
            if "candidate_ambiguity" in list(case_summary.get("active_blockers") or []):
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif get_case_status(case_summary) == "withheld_domain_block":
            core_reply = _build_domain_scope_note(domain_scope_projection) or OUT_OF_DOMAIN_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "withheld_no_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif get_primary_trace_reason(state_trace_audit) in {"review_pending", "review_candidate_ambiguity", "review_governance_withheld", "review_required"}:
            if get_primary_trace_reason(state_trace_audit) == "review_candidate_ambiguity":
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "clarification_missing_inputs":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif get_primary_trace_reason(state_trace_audit) == "domain_scope_blocked":
            core_reply = _build_domain_scope_note(domain_scope_projection) or OUT_OF_DOMAIN_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "escalation_conflict_open":
            core_reply = _build_conflict_correction_note(
                selection_state.get("conflict_status_projection")
            ) or ESCALATION_NEEDED_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "escalation_integrity_blocked":
            core_reply = _build_integrity_note(
                parameter_integrity_projection,
                unit_normalization_projection,
            ) or ESCALATION_NEEDED_REPLY
        elif get_primary_trace_reason(state_trace_audit) == "escalation_domain_threshold":
            core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
        elif output_status == "clarification_needed":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        elif output_status == "withheld_no_evidence":
            core_reply = EVIDENCE_MISSING_REPLY
        elif output_status == "withheld_review":
            if review_projection.get("status") == "ambiguous_but_reviewable" or selection_state.get("selection_status") == "multiple_viable_candidates":
                core_reply = AMBIGUOUS_CANDIDATE_REPLY
            else:
                core_reply = REVIEW_PENDING_REPLY
        elif output_status == "withheld_domain_block":
            core_reply = _build_domain_scope_note(domain_scope_projection) or OUT_OF_DOMAIN_REPLY
        elif output_status == "withheld_escalation":
            if correction_projection.get("conflict_still_open"):
                core_reply = _build_conflict_correction_note(
                    selection_state.get("conflict_status_projection")
                ) or ESCALATION_NEEDED_REPLY
            elif parameter_integrity_projection.get("integrity_status") == "unusable_until_clarified":
                core_reply = _build_integrity_note(
                    parameter_integrity_projection,
                    unit_normalization_projection,
                ) or ESCALATION_NEEDED_REPLY
            elif domain_scope_projection.get("status") in {"out_of_domain_scope", "escalation_required"}:
                core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
            else:
                core_reply = ESCALATION_NEEDED_REPLY
        elif demo_data_present:
            core_reply = DEMO_DATA_QUARANTINE_REPLY
        elif not evidence_available:
            core_reply = EVIDENCE_MISSING_REPLY
        elif (review_state or {}).get("review_required"):
            # Only fire REVIEW_PENDING_REPLY when a full review_state dict is provided.
            # The legacy `review_required` flat param only annotates the boundary block.
            core_reply = REVIEW_PENDING_REPLY
        elif (
            not output_blocked
            and (
                (
                    release_status == "rfq_ready"
                    and rfq_admissibility == "ready"
                    and specificity_level == "compound_required"
                )
                or (
                    canonical_dispatch_ready
                    and specificity_level == "compound_required"
                )
            )
        ):
            core_reply = NEUTRAL_SCOPE_REPLY
        elif selection_state.get("selection_status") == "blocked_no_candidates":
            core_reply = NO_CANDIDATES_REPLY
        elif selection_state.get("selection_status") == "blocked_no_viable_candidates":
            core_reply = NO_VIABLE_CANDIDATES_REPLY
        elif review_projection.get("status") == "escalation_needed":
            if correction_projection.get("conflict_still_open"):
                core_reply = _build_conflict_correction_note(
                    selection_state.get("conflict_status_projection")
                ) or ESCALATION_NEEDED_REPLY
            elif parameter_integrity_projection.get("integrity_status") == "unusable_until_clarified":
                core_reply = _build_integrity_note(
                    parameter_integrity_projection,
                    unit_normalization_projection,
                ) or ESCALATION_NEEDED_REPLY
            elif domain_scope_projection.get("status") in {"out_of_domain_scope", "escalation_required"}:
                core_reply = _build_domain_scope_note(domain_scope_projection) or ESCALATION_NEEDED_REPLY
            else:
                core_reply = ESCALATION_NEEDED_REPLY
        elif selection_state.get("selection_status") == "multiple_viable_candidates":
            core_reply = AMBIGUOUS_CANDIDATE_REPLY
        elif selection_state.get("selection_status") == "blocked_missing_required_inputs":
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)
        else:
            core_reply = _build_missing_data_reply(asserted_state, working_profile, clarification_projection)

    boundary = build_boundary_block(
        "structured",
        coverage_status=coverage_status,
        known_unknowns=known_unknowns,
        demo_data_present=demo_data_present,
        review_required=review_required,
        review_reason=review_reason,
        evidence_available=evidence_available,
    )
    return f"{core_reply}\n\n{boundary}"
