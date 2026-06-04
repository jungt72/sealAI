"""RFQ readiness + manufacturer-friendly One-Pager (Blueprint §20, §22, §32.14-16).

Additive layer on top of the existing RWDR/RFQ seams. It does NOT replace the
3 existing RWDR statuses (``rwdr_mvp_brief.RWDR_STATUS_*``) — it adds the V1.6
readiness band and a deterministic one-pager. Hard safety rule (§22): the
one-pager states no final suitability/release/compliance — the manufacturer
evaluates. Output is guarded by the Patch-2 No-Go / final-release guard.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Mapping, Sequence

from app.agent.templates.no_go_guard import assert_no_no_go
from app.agent.templates.registry import render_template

# --- Readiness band (§20.1) — additive; OUT_OF_SCOPE mirrors the RWDR status --
RFQ_READINESS_DRAFT = "DRAFT"
RFQ_READINESS_MINIMAL_RFQ = "MINIMAL_RFQ"
RFQ_READINESS_WITH_OPEN_POINTS = "RFQ_WITH_OPEN_POINTS"
RFQ_READINESS_MANUFACTURER_REVIEW_READY = "MANUFACTURER_REVIEW_READY"
RFQ_READINESS_OUT_OF_SCOPE = "OUT_OF_SCOPE"

RFQ_READINESS_BANDS = (
    RFQ_READINESS_DRAFT,
    RFQ_READINESS_MINIMAL_RFQ,
    RFQ_READINESS_WITH_OPEN_POINTS,
    RFQ_READINESS_MANUFACTURER_REVIEW_READY,
    RFQ_READINESS_OUT_OF_SCOPE,
)

# Minimum viable RFQ core (§20.2). Each group is satisfied by ANY alternative.
MINIMUM_RFQ_CORE: dict[str, tuple[str, ...]] = {
    "seal_type_or_photo": (
        "sealing_function",
        "seal_type",
        "sealing_type",
        "old_part_photo_available",
    ),
    "dimensions_or_photo": (
        "shaft_diameter_d1_mm",
        "housing_bore_D_mm",
        "seal_width_b_mm",
        "old_part_photo_available",
        "old_part_cross_section_or_drawing_available",
    ),
    "application": ("application", "installation_situation"),
    "medium_or_leakage": (
        "inside_medium",
        "medium",
        "leakage_description",
        "failure_symptom",
    ),
    "request_goal": ("request_goal", "rfq_goal"),
}

_MINIMUM_CORE_LABELS: dict[str, str] = {
    "seal_type_or_photo": "Dichtungstyp oder Foto",
    "dimensions_or_photo": "Maße (d1/D/b) oder Altteilfoto",
    "application": "Anwendung/Maschine",
    "medium_or_leakage": "Medium oder Leckagebeschreibung",
    "request_goal": "Anfrageziel",
}

# Open-point priority tiers (§20). Mirrors rwdr_mvp_brief critical vocabulary.
_CRITICAL_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_diameter_d1_mm",
        "housing_bore_D_mm",
        "seal_width_b_mm",
        "sealing_function",
        "inside_medium",
        "max_speed_rpm",
        "pressure_differential",
        "temperature_min_c",
        "temperature_max_c",
        "application",
        "shaft_condition_known",
        "shaft_condition",
    }
)
_OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {
        "quantity",
        "target_delivery_date",
        "desired_service_life_or_maintenance_interval",
    }
)

_SAFETY_BOUNDARY = (
    "Technische Vorqualifizierung und RFQ-Strukturierung. Keine finale "
    "Bewertung, Eignung oder Freigabe durch sealingAI — finale Bewertung/"
    "Freigabe erfolgt durch Hersteller oder verantwortliche Fachstelle."
)

RFQ_ONE_PAGER_TEMPLATE_ID = "rfq.rfq_one_pager.v1"
_RFQ_ONE_PAGER_TEMPLATE_PATH = "rfq/rfq_one_pager.j2"

# Affirmative suitability/release wording that must never appear (§22).
_RFQ_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "ist geeignet",
    "garantiert dicht",
    "freigegeben",
    "final geeignet",
    "beste Lösung ist",
)


@dataclass
class RfqReadiness:
    status: str
    can_generate_brief: bool
    minimum_needed: list[str] = dataclass_field(default_factory=list)
    open_points_critical: list[str] = dataclass_field(default_factory=list)
    open_points_helpful: list[str] = dataclass_field(default_factory=list)
    open_points_optional: list[str] = dataclass_field(default_factory=list)
    reason: str = ""


def prioritize_open_points(missing_fields: Sequence[str]) -> dict[str, list[str]]:
    """Split missing fields into critical / helpful / optional (§20)."""
    critical: list[str] = []
    helpful: list[str] = []
    optional: list[str] = []
    for raw in missing_fields:
        field = str(raw or "").strip()
        if not field:
            continue
        if field in _CRITICAL_FIELDS:
            critical.append(field)
        elif field in _OPTIONAL_FIELDS:
            optional.append(field)
        else:
            helpful.append(field)
    return {"critical": critical, "helpful": helpful, "optional": optional}


def _core_gaps(present_fields: set[str]) -> list[str]:
    gaps: list[str] = []
    for group, alternatives in MINIMUM_RFQ_CORE.items():
        if not any(alt in present_fields for alt in alternatives):
            gaps.append(_MINIMUM_CORE_LABELS[group])
    return gaps


def evaluate_rfq_readiness(
    present_fields: Sequence[str],
    *,
    missing_fields: Sequence[str] = (),
    out_of_scope: bool = False,
) -> RfqReadiness:
    """Determine the V1.6 readiness band from present + missing fields (§20)."""
    present = {str(f).strip() for f in present_fields if str(f).strip()}
    tiers = prioritize_open_points(missing_fields)

    if out_of_scope:
        return RfqReadiness(
            status=RFQ_READINESS_OUT_OF_SCOPE,
            can_generate_brief=False,
            reason="Fall ist nicht Teil des RWDR-MVP-Scopes.",
        )

    core_gaps = _core_gaps(present)
    if core_gaps:
        # §32.15: insufficient minimum core → DRAFT, name what is missing.
        return RfqReadiness(
            status=RFQ_READINESS_DRAFT,
            can_generate_brief=False,
            minimum_needed=core_gaps,
            open_points_critical=tiers["critical"],
            open_points_helpful=tiers["helpful"],
            open_points_optional=tiers["optional"],
            reason="Mindestkern für eine erste Herstelleranfrage fehlt.",
        )

    # Core present → RFQ can be generated, open points are surfaced not hidden.
    if tiers["critical"]:
        status = RFQ_READINESS_WITH_OPEN_POINTS
    elif tiers["helpful"]:
        status = RFQ_READINESS_MINIMAL_RFQ
    else:
        status = RFQ_READINESS_MANUFACTURER_REVIEW_READY

    return RfqReadiness(
        status=status,
        can_generate_brief=True,
        open_points_critical=tiers["critical"],
        open_points_helpful=tiers["helpful"],
        open_points_optional=tiers["optional"],
        reason="Mindestkern vorhanden; offene Punkte sind markiert.",
    )


def _one_pager_context(
    *,
    request_goal: str,
    confirmed_facts: Sequence[str],
    open_points_critical: Sequence[str],
    open_points_helpful: Sequence[str],
    open_points_optional: Sequence[str],
    review_flags: Sequence[str],
    computed_values: Sequence[str],
    attachments: Sequence[str],
    manufacturer_questions: Sequence[str],
) -> dict[str, Any]:
    return {
        "request_goal": request_goal.strip()
        or "Herstellerbewertbare RWDR-Anfrage vorbereiten.",
        "confirmed_facts": [str(f) for f in confirmed_facts],
        "open_points_critical": [str(f) for f in open_points_critical],
        "open_points_helpful": [str(f) for f in open_points_helpful],
        "open_points_optional": [str(f) for f in open_points_optional],
        "review_flags": [str(f) for f in review_flags],
        "computed_values": [str(f) for f in computed_values],
        "attachments": [str(f) for f in attachments],
        "manufacturer_questions": [str(f) for f in manufacturer_questions],
        "safety_boundary": _SAFETY_BOUNDARY,
    }


def build_rfq_one_pager(
    *,
    request_goal: str = "",
    confirmed_facts: Sequence[str] = (),
    open_points_critical: Sequence[str] = (),
    open_points_helpful: Sequence[str] = (),
    open_points_optional: Sequence[str] = (),
    review_flags: Sequence[str] = (),
    computed_values: Sequence[str] = (),
    attachments: Sequence[str] = (),
    manufacturer_questions: Sequence[str] = (),
    enforce_guard: bool = True,
) -> str:
    """Render a manufacturer-friendly RFQ one-pager (§20.5, §32.16).

    Short and structured — not a long AI report. Guarded against final
    suitability/release wording (§22).
    """
    context = _one_pager_context(
        request_goal=request_goal,
        confirmed_facts=confirmed_facts,
        open_points_critical=open_points_critical,
        open_points_helpful=open_points_helpful,
        open_points_optional=open_points_optional,
        review_flags=review_flags,
        computed_values=computed_values,
        attachments=attachments,
        manufacturer_questions=manufacturer_questions,
    )
    markdown = render_template(_RFQ_ONE_PAGER_TEMPLATE_PATH, context).strip()
    if enforce_guard:
        # No final suitability/release/compliance claim may appear (§22).
        assert_no_no_go(markdown, _RFQ_FORBIDDEN_PHRASES, include_final_release=True)
    return markdown


def _field_name(field: Mapping[str, Any]) -> str:
    return str(
        field.get("field")
        or field.get("canonical_field")
        or field.get("field_name")
        or ""
    ).strip()


def _fact_text(field: Mapping[str, Any]) -> str:
    name = _field_name(field)
    value = field.get("value")
    unit = field.get("unit")
    rendered = f"{value} {unit}".strip() if unit else str(value)
    return f"{name}: {rendered}".strip(": ").strip()


def attach_rfq_one_pager(brief: Mapping[str, Any]) -> dict[str, Any]:
    """Augment an existing RWDR brief dict with V1.6 readiness + one-pager.

    Pure and additive: reads the brief produced by
    ``rwdr_mvp_brief.build_rwdr_brief_from_confirmed_fields`` and returns a new
    dict with ``rfq_readiness``, ``rfq_one_pager`` and ``rfq_snapshot``. The
    existing brief keys (incl. its 3-value ``status``) are preserved untouched.
    """
    augmented = dict(brief)
    canonical = dict(brief.get("canonical_case") or {})
    confirmed = [
        dict(f)
        for f in (brief.get("confirmed_case_fields") or [])
        if isinstance(f, Mapping)
    ]

    present_fields = [name for f in confirmed if (name := _field_name(f))]
    missing_fields = [
        *(str(x) for x in (canonical.get("missing_critical_fields") or [])),
        *(str(x) for x in (canonical.get("missing_helpful_fields") or [])),
    ]
    out_of_scope = str(brief.get("status") or "") == RFQ_READINESS_OUT_OF_SCOPE

    readiness = evaluate_rfq_readiness(
        present_fields, missing_fields=missing_fields, out_of_scope=out_of_scope
    )

    confirmed_facts = [_fact_text(f) for f in confirmed if _field_name(f)]
    computed_values = [str(v) for v in (brief.get("computed_values") or [])]
    review_flags = [str(v) for v in (brief.get("engineering_review_flags") or [])]
    manufacturer_questions = [
        str(v) for v in (brief.get("manufacturer_questions") or [])
    ]

    one_pager = build_rfq_one_pager(
        request_goal="Herstellerbewertbare RWDR-Anfrage vorbereiten.",
        confirmed_facts=confirmed_facts,
        open_points_critical=readiness.open_points_critical,
        open_points_helpful=readiness.open_points_helpful,
        open_points_optional=readiness.open_points_optional,
        review_flags=review_flags,
        computed_values=computed_values,
        manufacturer_questions=manufacturer_questions,
    )

    snapshot = build_rfq_snapshot(
        case_id=str(brief.get("case_id") or ""),
        case_revision=int(brief.get("case_revision") or 0),
        readiness=readiness,
        confirmed_facts=confirmed_facts,
        review_flags=review_flags,
        computed_values=computed_values,
    )

    augmented["rfq_readiness"] = {
        "status": readiness.status,
        "can_generate_brief": readiness.can_generate_brief,
        "minimum_needed": readiness.minimum_needed,
        "open_points_critical": readiness.open_points_critical,
        "open_points_helpful": readiness.open_points_helpful,
        "open_points_optional": readiness.open_points_optional,
        "reason": readiness.reason,
    }
    augmented["rfq_one_pager"] = one_pager
    augmented["rfq_snapshot"] = snapshot
    return augmented


def build_rfq_snapshot(
    *,
    case_id: str,
    case_revision: int,
    readiness: RfqReadiness,
    confirmed_facts: Sequence[str] = (),
    review_flags: Sequence[str] = (),
    computed_values: Sequence[str] = (),
) -> dict[str, Any]:
    """Deterministic, immutable RFQ snapshot bound to a case_revision (§20.7).

    The same case_revision + content yields an identical snapshot (stable
    snapshot_id). A later case change produces a new snapshot, never a silent
    mutation of the old one.
    """
    payload: dict[str, Any] = {
        "case_id": case_id,
        "case_revision": int(case_revision),
        "readiness": readiness.status,
        "can_generate_brief": readiness.can_generate_brief,
        "confirmed_facts": [str(f) for f in confirmed_facts],
        "open_points_critical": list(readiness.open_points_critical),
        "open_points_helpful": list(readiness.open_points_helpful),
        "open_points_optional": list(readiness.open_points_optional),
        "review_flags": [str(f) for f in review_flags],
        "computed_values": [str(f) for f in computed_values],
        "no_final_technical_release": True,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    snapshot_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {"snapshot_id": snapshot_id, **payload}
