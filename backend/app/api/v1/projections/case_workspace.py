# backend/app/api/v1/projections/case_workspace.py
"""Workspace projection helpers for transitional v1 and canonical agent reads.

project_case_workspace maps the 4-pillar workspace state shape to
CaseWorkspaceProjection.

The additional synthesis helpers convert canonical SSoT AgentState into that
same 4-pillar shape so both `/api/v1/state/*` and `/api/agent/*` can expose the
same workspace contract without inventing a parallel projection path.
"""
from __future__ import annotations

from typing import Any, Dict

from app.agent.runtime.clarification_priority import select_next_focus_from_known_context
from app.agent.state.models import GovernedSessionState
from app.agent.domain.checks_registry import build_registered_check_results
from app.agent.domain.medium_registry import classify_medium_value
from app.api.v1.schemas.case_workspace import (
    ArtifactStatus,
    CaseSummary,
    CaseWorkspaceProjection,
    ClaimItem,
    ClaimsSummary,
    CockpitProperty,
    CockpitReadinessSummary,
    CockpitRoutingMetadata,
    CockpitSection,
    CockpitSectionCompletion,
    CommunicationContext,
    CycleInfo,
    EngineeringCockpitView,
    EngineeringCheckResult,
    EngineeringPath as WorkspaceEngineeringPath,
    EvidenceSummary,
    GovernanceStatus,
    MediumCaptureSummary,
    MediumClassificationSummary,
    MediumContextSummary,
    PartnerMatchingSummary,
    RequestType as WorkspaceRequestType,
    RFQPackageSummary,
    RFQStatus,
    TechnicalDerivationItem,
)


def _d(value: Any) -> Dict[str, Any]:
    """Safely coerce to dict."""
    return dict(value) if isinstance(value, dict) else {}


def _ls(value: Any) -> list:
    """Safely coerce to list."""
    return list(value) if isinstance(value, list) else []


def _compact_unique_strings(items: list[str], *, limit: int = 3) -> list[str]:
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


_FIELD_LABELS: dict[str, str] = {
    "medium": "Medium",
    "pressure_bar": "Betriebsdruck",
    "temperature_c": "Betriebstemperatur",
    "movement_type": "Bewegungsart",
    "application_context": "Anwendung",
}

_CANONICAL_PARAMETER_KEYS: tuple[str, ...] = (
    "medium",
    "temperature_c",
    "pressure_bar",
    "sealing_type",
    "pressure_direction",
    "duty_profile",
    "shaft_diameter_mm",
    "speed_rpm",
    "installation",
    "geometry_context",
    "contamination",
    "counterface_surface",
    "tolerances",
    "industry",
    "compliance",
    "medium_qualifiers",
)

_MOVEMENT_LABELS: dict[str, str] = {
    "rotary": "rotierend",
    "linear": "linear",
    "static": "statisch",
}

_APPLICATION_LABELS: dict[str, str] = {
    "shaft_sealing": "Wellenabdichtung",
    "linear_sealing": "lineare Abdichtung",
    "static_sealing": "statische Abdichtung",
    "housing_sealing": "Gehaeuseabdichtung",
    "external_sealing": "nach aussen abdichten",
    "marine_propulsion": "Schiffsschraube / Wellenabdichtung",
}

_REQUEST_TYPE_VALUES: frozenset[str] = frozenset(
    {
        "new_design",
        "retrofit",
        "rca_failure_analysis",
        "validation_check",
        "spare_part_identification",
        "quick_engineering_check",
    }
)

_ENGINEERING_PATH_VALUES: frozenset[str] = frozenset(
    {
        "ms_pump",
        "rwdr",
        "static",
        "labyrinth",
        "hyd_pneu",
        "unclear_rotary",
    }
)

_COCKPIT_SECTION_CONFIG: tuple[dict[str, Any], ...] = (
    {
        "section_id": "core_intake",
        "title": "A. Grunddaten",
        "fields": (
            {"key": "medium", "label": "Medium / Fluid", "unit": None},
            {"key": "temperature_c", "label": "Temperatur", "unit": "degC"},
            {"key": "pressure_bar", "label": "Druck", "unit": "bar"},
            {"key": "shaft_diameter_mm", "label": "Referenz-Ø", "unit": "mm"},
            {"key": "speed_rpm", "label": "Drehzahl", "unit": "rpm"},
            {"key": "motion_type", "label": "Bewegungsart", "unit": None},
            {"key": "installation", "label": "Equipment-Typ", "unit": None},
            {"key": "pressure_direction", "label": "Druckrichtung", "unit": None},
        ),
    },
    {
        "section_id": "failure_drivers",
        "title": "B. Technische Risikofaktoren",
        "fields": (
            {"key": "viscosity", "label": "Viskosität", "unit": "cSt"},
            {"key": "solids_percent", "label": "Feststoffe", "unit": "%"},
            {"key": "ph", "label": "pH-Wert", "unit": None},
            {"key": "dry_run_possible", "label": "Trockenlauf mögl.", "unit": None},
            {"key": "cleaning_cycles", "label": "Reinigungszyklen", "unit": None},
        ),
    },
    {
        "section_id": "geometry_fit",
        "title": "C. Geometrie & Einbauraum",
        "fields": (
            {"key": "geometry_context", "label": "Bauraum", "unit": None},
            {"key": "shaft_material", "label": "Wellenwerkstoff", "unit": None},
            {"key": "shaft_hardness", "label": "Wellenhärte", "unit": "HRC"},
            {"key": "runout_mm", "label": "Rundlauf", "unit": "mm"},
            {"key": "vibration_rms", "label": "Vibration RMS", "unit": "mm/s"},
        ),
    },
    {
        "section_id": "rfq_liability",
        "title": "D. Anfrage- & Freigabereife",
        "fields": (
            {"key": "allowable_leakage", "label": "Zul. Leckage", "unit": None},
            {"key": "life_hours", "label": "Lebensdauer", "unit": "h"},
            {"key": "compliance", "label": "Konformität", "unit": None},
        ),
    },
)

_DEFAULT_COCKPIT_RULES: dict[str, tuple[str, ...]] = {
    "mandatory": ("medium", "temperature_c", "pressure_bar"),
    "hidden": (),
}

_COCKPIT_PATH_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "ms_pump": {
        "mandatory": (
            "medium",
            "temperature_c",
            "pressure_bar",
            "shaft_diameter_mm",
            "speed_rpm",
            "motion_type",
            "installation",
            "viscosity",
            "solids_percent",
            "runout_mm",
        ),
        "hidden": (),
    },
    "rwdr": {
        "mandatory": (
            "medium",
            "temperature_c",
            "shaft_diameter_mm",
            "speed_rpm",
            "shaft_material",
            "shaft_hardness",
        ),
        "hidden": ("pressure_max_bar",),
    },
    "static": {
        "mandatory": ("medium", "temperature_c", "pressure_bar", "geometry_context"),
        "hidden": ("speed_rpm", "shaft_diameter_mm", "runout_mm"),
    },
    "labyrinth": {
        "mandatory": ("shaft_diameter_mm", "speed_rpm", "medium"),
        "hidden": ("pressure_bar",),
    },
    "hyd_pneu": {
        "mandatory": ("medium", "temperature_c", "pressure_bar", "geometry_context"),
        "hidden": (),
    },
    "unclear_rotary": {
        "mandatory": ("medium", "motion_type"),
        "hidden": (),
    },
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _has_marker(texts: list[str], markers: tuple[str, ...]) -> bool:
    return any(marker in text for text in texts for marker in markers)


def _coerce_request_type(value: Any) -> WorkspaceRequestType | None:
    text = _normalize_text(value)
    if text in _REQUEST_TYPE_VALUES:
        return text  # type: ignore[return-value]
    return None


def _coerce_engineering_path(value: Any) -> WorkspaceEngineeringPath | None:
    text = _normalize_text(value)
    if text in _ENGINEERING_PATH_VALUES:
        return text  # type: ignore[return-value]
    return None


def _derive_request_type(
    *,
    profile: Dict[str, Any],
    system: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> WorkspaceRequestType | None:
    explicit_request_type = (
        _coerce_request_type(system.get("request_type"))
        or _coerce_request_type(_d(system.get("routing")).get("request_type"))
        or _coerce_request_type(reasoning.get("request_type"))
    )
    if explicit_request_type is not None:
        return explicit_request_type

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "geometry_locked",
            "old_part_known",
            "old_part_dimensions",
            "allowed_changes",
            "available_radial_space_mm",
            "available_axial_space_mm",
            "cavity_standard_known",
        )
    ):
        return "retrofit"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "symptom_class",
            "failure_timing",
            "damage_pattern",
            "leakage_pattern",
            "runtime_to_failure",
            "runtime_to_failure_hours",
            "operating_phase_of_failure",
            "inspection_findings",
        )
    ):
        return "rca_failure_analysis"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "validation_target",
            "validation_basis",
            "existing_design_reference",
        )
    ):
        return "validation_check"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "part_number",
            "old_part_number",
            "manufacturer_part_number",
            "spare_part_reference",
        )
    ):
        return "spare_part_identification"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in ("requested_check", "calc_id", "target_formula")
    ):
        return "quick_engineering_check"

    return None


def _derive_engineering_path(
    *,
    profile: Dict[str, Any],
    system: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> WorkspaceEngineeringPath | None:
    explicit_path = (
        _coerce_engineering_path(system.get("engineering_path"))
        or _coerce_engineering_path(_d(system.get("routing")).get("path"))
        or _coerce_engineering_path(reasoning.get("engineering_path"))
    )
    if explicit_path is not None:
        return explicit_path

    motion_type = _normalize_text(profile.get("movement_type") or profile.get("motion_type"))
    texts = [
        _normalize_text(profile.get("installation")),
        _normalize_text(profile.get("application_context")),
        _normalize_text(profile.get("application_category")),
        _normalize_text(profile.get("geometry_context")),
        _normalize_text(profile.get("sealing_type")),
        _normalize_text(_d(system.get("answer_contract")).get("requirement_class_hint")),
        _normalize_text(_d(_d(system.get("answer_contract")).get("requirement_class")).get("seal_type")),
    ]
    texts = [text for text in texts if text]

    if _has_marker(texts, ("labyrinth",)):
        return "labyrinth"

    if motion_type == "static" or _has_marker(texts, ("static_sealing", "housing_sealing", "flachdichtung", "static seal")):
        return "static"

    if _has_marker(texts, ("hydraul", "pneumat", "zylinder", "cylinder", "rod", "kolbenstange")):
        return "hyd_pneu"

    if motion_type == "rotary":
        if _has_marker(texts, ("pump", "kreiselpumpe", "mechanical_seal", "mechanical seal", "gleitring")):
            return "ms_pump"
        if _has_marker(texts, ("rwdr", "wellendichtring", "radial shaft", "radialwellendichtring", "simmerring", "gearbox", "lip seal")):
            return "rwdr"
        return "unclear_rotary"

    return None


def _parameter_provenance_map(reasoning: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key in ("extracted_parameter_provenance", "parameter_provenance"):
        payload = _d(reasoning.get(key))
        if payload:
            merged.update(payload)
    return merged


def _parameter_confidence_map(reasoning: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key in ("parameter_confidence",):
        payload = _d(reasoning.get(key))
        if payload:
            merged.update(payload)
    return merged


def _provenance_origin(value: Any) -> str | None:
    if isinstance(value, str):
        text = str(value).strip()
        return text or None
    if isinstance(value, dict):
        for key in ("origin", "source", "source_kind", "provenance"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return None


def _provenance_confidence(value: Any) -> str | None:
    if isinstance(value, dict):
        text = str(value.get("confidence") or "").strip()
        return text or None
    return None


def _cockpit_field_value(profile: Dict[str, Any], key: str) -> Any:
    if key in profile:
        return profile.get(key)
    if key == "motion_type":
        return profile.get("movement_type")
    return None


def _build_cockpit_sections(
    *,
    profile: Dict[str, Any],
    engineering_path: WorkspaceEngineeringPath | None,
    reasoning: Dict[str, Any],
) -> tuple[list[CockpitSection], list[str]]:
    rules = _COCKPIT_PATH_RULES.get(
        str(engineering_path or ""),
        _DEFAULT_COCKPIT_RULES,
    )
    mandatory_keys = set(rules["mandatory"])
    hidden_keys = set(rules["hidden"])
    provenance_map = _parameter_provenance_map(reasoning)
    confidence_map = _parameter_confidence_map(reasoning)
    missing_mandatory_keys: list[str] = []
    sections: list[CockpitSection] = []

    for section_config in _COCKPIT_SECTION_CONFIG:
        properties: list[CockpitProperty] = []
        mandatory_total = 0
        mandatory_present = 0
        for field in section_config["fields"]:
            key = str(field["key"])
            if key in hidden_keys:
                continue
            value = _cockpit_field_value(profile, key)
            origin = _provenance_origin(provenance_map.get(key))
            confidence = (
                str(confidence_map.get(key)).strip()
                if confidence_map.get(key) not in (None, "")
                else _provenance_confidence(provenance_map.get(key))
            )
            is_mandatory = key in mandatory_keys
            is_confirmed = confidence == "confirmed"
            if value in (None, "", []):
                value = None
                if is_mandatory:
                    missing_mandatory_keys.append(key)
                origin = origin or "missing"
            if is_mandatory:
                mandatory_total += 1
                if value is not None:
                    mandatory_present += 1
            properties.append(
                CockpitProperty(
                    key=key,
                    label=str(field["label"]),
                    value=value,
                    unit=field.get("unit"),
                    origin=origin,
                    confidence=confidence,
                    is_confirmed=is_confirmed,
                    is_mandatory=is_mandatory,
                )
            )

        percent = int(round((mandatory_present / mandatory_total) * 100)) if mandatory_total else 100
        sections.append(
            CockpitSection(
                section_id=str(section_config["section_id"]),
                title=str(section_config["title"]),
                completion=CockpitSectionCompletion(
                    mandatory_present=mandatory_present,
                    mandatory_total=mandatory_total,
                    percent=percent,
                ),
                properties=properties,
            )
        )

    return sections, missing_mandatory_keys


def _build_cockpit_view(
    *,
    profile: Dict[str, Any],
    request_type: WorkspaceRequestType | None,
    engineering_path: WorkspaceEngineeringPath | None,
    reasoning: Dict[str, Any],
    system: Dict[str, Any],
    rfq_status: RFQStatus,
    governance_status: GovernanceStatus,
    completeness_payload: Dict[str, Any],
    checks: list[EngineeringCheckResult],
) -> EngineeringCockpitView:
    sections, missing_mandatory_keys = _build_cockpit_sections(
        profile=profile,
        engineering_path=engineering_path,
        reasoning=reasoning,
    )
    blockers = [
        str(item)
        for item in dict.fromkeys(
            list(rfq_status.blockers)
            + list(governance_status.gate_failures)
        )
        if item
    ]
    coverage_score = float(completeness_payload.get("coverage_score") or 0.0)
    is_rfq_ready = bool(
        rfq_status.rfq_ready
        or (
            not missing_mandatory_keys
            and coverage_score > 0.6
        )
    )
    status = "rfq_ready" if is_rfq_ready else ("preliminary" if missing_mandatory_keys else "review_needed")
    return EngineeringCockpitView(
        request_type=request_type,
        engineering_path=engineering_path,
        routing_metadata=CockpitRoutingMetadata(
            phase=str(reasoning.get("phase") or "") or None,
            last_node=str(reasoning.get("last_node") or "") or None,
            routing=_d(system.get("routing")),
        ),
        sections=sections,
        checks=checks,
        missing_mandatory_keys=missing_mandatory_keys,
        blockers=blockers,
        readiness=CockpitReadinessSummary(
            status=status,
            is_rfq_ready=is_rfq_ready,
            release_status=governance_status.release_status,
            coverage_score=coverage_score,
        ),
    )


def _build_confirmed_facts_summary(working_profile_pillar: Dict[str, Any]) -> list[str]:
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    facts: list[str] = []
    for key in ("movement_type", "application_context", "medium", "pressure_bar", "temperature_c"):
        value = profile.get(key)
        if value in (None, ""):
            continue
        rendered_value = value
        if key == "movement_type":
            rendered_value = _MOVEMENT_LABELS.get(str(value), value)
        elif key == "application_context":
            rendered_value = _APPLICATION_LABELS.get(str(value), value)
        facts.append(f"{_FIELD_LABELS.get(key, key)}: {rendered_value}")
    return _compact_unique_strings(facts)


def _build_parameters_snapshot(working_profile_pillar: Dict[str, Any]) -> Dict[str, Any]:
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    snapshot: Dict[str, Any] = {}
    for key in _CANONICAL_PARAMETER_KEYS:
        value = profile.get(key)
        if value in (None, ""):
            continue
        snapshot[key] = value
    movement_type = profile.get("movement_type")
    if movement_type not in (None, ""):
        snapshot["motion_type"] = movement_type
    return snapshot


def _parameter_confidence_from_meta(parameter_meta: Dict[str, Any]) -> Dict[str, str]:
    confidence_map: Dict[str, str] = {}
    for key, value in parameter_meta.items():
        if not isinstance(value, dict):
            continue
        confidence = str(value.get("confidence") or "").strip()
        if confidence:
            confidence_map[str(key)] = confidence
    return confidence_map


def _technical_derivation_from_live_calc_tile(tile: Dict[str, Any]) -> TechnicalDerivationItem | None:
    if not tile:
        return None
    if not any(tile.get(key) is not None for key in ("v_surface_m_s", "pv_value_mpa_m_s", "dn_value")):
        return None
    return TechnicalDerivationItem(
        calc_type="rwdr",
        status=str(tile.get("status") or "insufficient_data"),
        v_surface_m_s=tile.get("v_surface_m_s"),
        pv_value_mpa_m_s=tile.get("pv_value_mpa_m_s"),
        dn_value=tile.get("dn_value"),
        notes=[str(item) for item in _ls(tile.get("notes")) if item],
    )


def _build_technical_derivations(
    *,
    working_profile_pillar: Dict[str, Any],
    system: Dict[str, Any],
) -> list[TechnicalDerivationItem]:
    items: list[TechnicalDerivationItem] = []
    for item in _ls(system.get("technical_derivations")):
        if not isinstance(item, dict):
            continue
        try:
            items.append(TechnicalDerivationItem.model_validate(item))
        except Exception:
            continue
    if items:
        return items

    live_calc_tile = _d(working_profile_pillar.get("live_calc_tile")) or _d(system.get("live_calc_tile"))
    live_calc_derivation = _technical_derivation_from_live_calc_tile(live_calc_tile)
    return [live_calc_derivation] if live_calc_derivation is not None else []


def _build_engineering_checks(
    *,
    profile: Dict[str, Any],
    engineering_path: WorkspaceEngineeringPath | None,
    technical_derivations: list[TechnicalDerivationItem],
) -> list[EngineeringCheckResult]:
    checks: list[EngineeringCheckResult] = []
    for item in build_registered_check_results(
        profile=profile,
        engineering_path=engineering_path,
        technical_derivations=technical_derivations,
    ):
        try:
            checks.append(EngineeringCheckResult.model_validate(item))
        except Exception:
            continue
    return checks


def _build_evidence_summary(evidence_state: Dict[str, Any]) -> EvidenceSummary:
    return EvidenceSummary(
        evidence_present=bool(evidence_state.get("evidence_present")),
        evidence_count=int(evidence_state.get("evidence_count") or 0),
        trusted_sources_present=bool(evidence_state.get("trusted_sources_present")),
        evidence_supported_topics=[str(item) for item in _ls(evidence_state.get("evidence_supported_topics")) if item],
        source_backed_findings=[str(item) for item in _ls(evidence_state.get("source_backed_findings")) if item],
        deterministic_findings=[str(item) for item in _ls(evidence_state.get("deterministic_findings")) if item],
        assumption_based_findings=[str(item) for item in _ls(evidence_state.get("assumption_based_findings")) if item],
        unresolved_open_points=[str(item) for item in _ls(evidence_state.get("unresolved_open_points")) if item],
        evidence_gaps=[str(item) for item in _ls(evidence_state.get("evidence_gaps")) if item],
    )


def _build_claims_summary(evidence_summary: EvidenceSummary) -> ClaimsSummary:
    items: list[ClaimItem] = []
    for finding in evidence_summary.deterministic_findings:
        items.append(ClaimItem(value=finding, claim_type="deterministic_fact", claim_origin="deterministic"))
    for finding in evidence_summary.source_backed_findings:
        items.append(ClaimItem(value=finding, claim_type="source_backed_finding", claim_origin="evidence"))
    for finding in evidence_summary.assumption_based_findings:
        items.append(ClaimItem(value=finding, claim_type="assumption_based_finding", claim_origin="assumption"))
    for finding in evidence_summary.unresolved_open_points:
        items.append(ClaimItem(value=finding, claim_type="unresolved_open_point", claim_origin="open"))
    for finding in evidence_summary.evidence_gaps:
        items.append(ClaimItem(value=finding, claim_type="evidence_gap", claim_origin="evidence_gap"))

    by_type: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    for item in items:
        by_type[item.claim_type] = by_type.get(item.claim_type, 0) + 1
        by_origin[item.claim_origin] = by_origin.get(item.claim_origin, 0) + 1

    return ClaimsSummary(total=len(items), by_type=by_type, by_origin=by_origin, items=items)


def _question_from_open_point(open_point: str | None) -> str | None:
    text = str(open_point or "").strip()
    if not text:
        return None
    return f"Koennen Sie {text} noch einordnen?"


def _is_stale_medium_open_point(label: str, *, medium_present: bool) -> bool:
    text = str(label or "").strip().casefold()
    if not medium_present or not text:
        return False
    return text == "medium" or text.startswith("medium ")


def _is_stale_rotary_open_point(label: str, *, movement_type: str | None) -> bool:
    text = str(label or "").strip().casefold()
    if str(movement_type or "").strip().casefold() != "linear":
        return False
    return any(marker in text for marker in ("rotierend", "welle", "wellen", "rwdr", "wellendichtring"))


def _filter_stale_focus_points(items: list[str], *, profile: Dict[str, Any]) -> list[str]:
    medium_present = profile.get("medium") not in (None, "")
    movement_type = str(profile.get("movement_type") or "").strip()
    result: list[str] = []
    for item in items:
        if _is_stale_medium_open_point(item, medium_present=medium_present):
            continue
        if _is_stale_rotary_open_point(item, movement_type=movement_type):
            continue
        result.append(item)
    return result


def _build_communication_context(
    *,
    phase: str | None,
    completeness: Dict[str, Any],
    governance_metadata: Dict[str, Any],
    matching_ready: bool,
    material_fit_items: list[dict[str, Any]],
    not_ready_reasons: list[str],
    rfq_ready: bool,
    rfq_status: RFQStatus,
    working_profile_pillar: Dict[str, Any],
) -> CommunicationContext:
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    missing = [str(item) for item in _ls(completeness.get("missing_critical_parameters")) if item]
    unknowns = [
        str(item)
        for item in list(
            dict.fromkeys(
                list(governance_metadata.get("unknowns_release_blocking") or [])
                + list(governance_metadata.get("unknowns_manufacturer_validation") or [])
            )
        )
        if item
    ]

    confirmed_facts_summary = _build_confirmed_facts_summary(working_profile_pillar)
    known_fields = {str(key) for key, value in profile.items() if value not in (None, "")}
    focus_priority = None
    if any(
        profile.get(key) not in (None, "")
        for key in ("movement_type", "application_context", "installation", "geometry_context", "speed_rpm", "shaft_diameter_mm")
    ):
        focus_priority = select_next_focus_from_known_context(
            known_fields=known_fields,
            medium_status="recognized" if profile.get("medium") not in (None, "") else "unknown",
            current_text=" ".join(str(item) for item in confirmed_facts_summary),
            application_anchor_present=bool(profile.get("application_context") or profile.get("movement_type") or profile.get("installation")),
            rotary_context_detected=bool(
                profile.get("movement_type") == "rotary"
                or {"speed_rpm", "shaft_diameter_mm"} & known_fields
            ),
        )

    if missing or unknowns:
        prioritized_open_points = [focus_priority.open_point_label] if focus_priority is not None else []
        open_points_summary = _compact_unique_strings(
            _filter_stale_focus_points(prioritized_open_points + missing + unknowns, profile=profile)
        )
        return CommunicationContext(
            conversation_phase="clarification",
            turn_goal="clarify_primary_open_point",
            primary_question=(
                focus_priority.question
                if focus_priority is not None
                else _question_from_open_point(open_points_summary[0] if open_points_summary else None)
            ),
            supporting_reason=(
                focus_priority.reason
                if focus_priority is not None
                else "Dann kann ich die technische Einengung sauber weiterfuehren."
            ),
            response_mode="single_question",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=open_points_summary,
        )

    if rfq_ready or rfq_status.handover_ready or rfq_status.handover_initiated:
        return CommunicationContext(
            conversation_phase="rfq_handover",
            turn_goal="prepare_handover",
            response_mode="handover_summary",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=_compact_unique_strings(
                [str(item) for item in list(rfq_status.open_points) + list(rfq_status.blockers) if item]
            ),
        )

    if matching_ready or material_fit_items:
        return CommunicationContext(
            conversation_phase="matching",
            turn_goal="explain_matching_result",
            response_mode="result_summary",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=_compact_unique_strings(not_ready_reasons or list(rfq_status.open_points)),
        )

    mapped_phase = "exploration" if phase in {"intake", "conversation"} else "recommendation"
    return CommunicationContext(
        conversation_phase=mapped_phase,
        turn_goal="explain_governed_result",
        response_mode="guided_explanation",
        confirmed_facts_summary=confirmed_facts_summary,
        open_points_summary=_compact_unique_strings([str(item) for item in list(rfq_status.open_points) if item]),
    )


def _serialize_ssot_messages(messages: list) -> list:
    """Serialize LangChain message objects into JSON-safe dicts."""
    result = []
    for msg in (messages or []):
        msg_type = getattr(msg, "type", None)
        if msg_type is None:
            msg_type = type(msg).__name__.lower().replace("message", "")
        entry: Dict[str, Any] = {
            "type": str(msg_type),
            "content": getattr(msg, "content", "") or "",
        }
        msg_id = getattr(msg, "id", None)
        if msg_id:
            entry["id"] = msg_id
        result.append(entry)
    return result


def _serialize_governed_messages(messages: list) -> list:
    result = []
    for index, msg in enumerate(messages or []):
        if not isinstance(msg, dict):
            payload = msg.model_dump() if hasattr(msg, "model_dump") else {}
        else:
            payload = dict(msg)
        role = str(payload.get("role") or "").strip()
        content = str(payload.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        result.append(
            {
                "type": "human" if role == "user" else "ai",
                "content": content,
                "id": payload.get("created_at") or f"governed-{index}",
            }
        )
    return result


def _governed_release_status(state: GovernedSessionState) -> str:
    if state.rfq.rfq_ready:
        return "rfq_ready"
    if state.matching.status == "matched_primary_candidate" or state.governance.gov_class == "A":
        if getattr(state.governance, "preselection_blockers", None):
            return "precheck_only"
        return "manufacturer_validation_required"
    if state.governance.gov_class == "B":
        return "precheck_only"
    return "inadmissible"


def _governed_working_profile(state: GovernedSessionState) -> Dict[str, Any]:
    profile: Dict[str, Any] = {}
    for field_name, claim in state.asserted.assertions.items():
        if claim.asserted_value is None:
            continue
        profile[field_name] = claim.asserted_value
    motion_label = getattr(state.motion_hint, "label", None)
    if motion_label in {"rotary", "linear", "static"}:
        profile["movement_type"] = motion_label
    application_label = getattr(state.application_hint, "label", None)
    if application_label:
        profile["application_context"] = application_label
    return profile


def synthesize_workspace_state_from_governed(
    state: GovernedSessionState,
    *,
    chat_id: str,
) -> Dict[str, Any]:
    working_profile = _governed_working_profile(state)
    technical_derivations: list[dict[str, Any]] = []
    for result in list(getattr(state, "compute_results", []) or []):
        if not isinstance(result, dict):
            continue
        technical_derivations.append(
            {
                "calc_type": str(result.get("calc_type") or "unknown"),
                "status": str(result.get("status") or "insufficient_data"),
                "v_surface_m_s": result.get("v_surface_m_s"),
                "pv_value_mpa_m_s": result.get("pv_value_mpa_m_s"),
                "dn_value": result.get("dn_value"),
                "notes": [str(item) for item in list(result.get("notes") or []) if item],
            }
        )
    if technical_derivations:
        working_profile["live_calc_tile"] = {
            "status": technical_derivations[0].get("status"),
            "v_surface_m_s": technical_derivations[0].get("v_surface_m_s"),
            "pv_value_mpa_m_s": technical_derivations[0].get("pv_value_mpa_m_s"),
            "dn_value": technical_derivations[0].get("dn_value"),
            "notes": technical_derivations[0].get("notes") or [],
        }
    release_status = _governed_release_status(state)
    matching_state = {
        "status": state.matching.status,
        "matchability_status": state.matching.matchability_status,
        "shortlist_ready": state.matching.shortlist_ready,
        "inquiry_ready": state.matching.inquiry_ready,
        "release_blockers": list(state.matching.release_blockers),
        "selected_partner_id": (
            state.matching.selected_manufacturer_ref.manufacturer_name
            if state.matching.selected_manufacturer_ref is not None
            else None
        ),
        "match_candidates": [
            {
                "candidate_id": capability.manufacturer_name,
                "grade_name": (capability.grade_names[0] if capability.grade_names else None),
                "material_family": (
                    capability.material_families[0] if capability.material_families else None
                ),
                "fit_reasons": list(capability.capability_hints),
                "viability_status": "viable" if capability.qualified_for_rfq else "manufacturer_validation_required",
            }
            for capability in state.matching.manufacturer_capabilities
        ],
        "blocking_reasons": list(
            dict.fromkeys(
                list(state.matching.release_blockers)
                + list(state.matching.matching_notes)
            )
        ),
        "data_source": state.matching.data_source,
    }
    rfq_state = {
        "status": state.rfq.status,
        "rfq_admissibility": "ready" if state.rfq.rfq_admissible else "inadmissible",
        "handover_ready": state.rfq.rfq_ready,
        "handover_status": state.rfq.handover_status,
        "rfq_ready": state.rfq.rfq_ready,
        "open_points": list(state.rfq.soft_findings),
        "blockers": list(state.rfq.blocking_findings),
        "rfq_object": dict(state.rfq.rfq_object or {}),
        "rfq_html_report_present": bool(state.rfq.handover_summary),
        "selected_partner_id": (
            state.rfq.selected_manufacturer_ref.manufacturer_name
            if state.rfq.selected_manufacturer_ref is not None
            else None
        ),
    }
    messages = _serialize_governed_messages(state.conversation_messages)
    user_turn_count = sum(1 for item in state.conversation_messages if getattr(item, "role", None) == "user")
    phase = (
        "rfq_handover"
        if state.rfq.rfq_ready
        else "matching"
        if state.matching.status == "matched_primary_candidate"
        else "recommendation"
        if state.governance.gov_class in {"A", "B"}
        else "clarification"
    )
    missing_critical = list(
        dict.fromkeys(
            list(state.asserted.blocking_unknowns)
            + list(getattr(state.governance, "preselection_blockers", []) or [])
        )
    )
    tracked_basis_fields = (
        "medium",
        "pressure_bar",
        "temperature_c",
        "sealing_type",
        "duty_profile",
        "installation",
        "shaft_diameter_mm",
        "speed_rpm",
    )
    coverage_score = min(
        1.0,
        round(
            sum(1 for field_name in tracked_basis_fields if field_name in state.asserted.assertions)
            / len(tracked_basis_fields),
            2,
        ),
    )
    analysis_complete = state.governance.gov_class == "A" and not missing_critical
    completeness = {
        "coverage_score": coverage_score,
        "coverage_gaps": missing_critical,
        "completeness_depth": "governed" if state.governance.gov_class in {"A", "B"} else "precheck",
        "missing_critical_parameters": missing_critical,
        "analysis_complete": analysis_complete,
        "recommendation_ready": analysis_complete,
    }
    return {
        "conversation": {
            "thread_id": chat_id,
            "messages": messages,
            "turn_count": user_turn_count,
            "max_turns": 12,
        },
        "working_profile": {
            "engineering_profile": working_profile,
            "extracted_params": working_profile,
            "completeness": completeness,
        },
        "reasoning": {
            "phase": phase,
            "last_node": "governed_live_state",
            "selected_partner_id": matching_state.get("selected_partner_id"),
            "state_revision": state.analysis_cycle,
            "parameter_confidence": {
                field_name: claim.confidence
                for field_name, claim in state.asserted.assertions.items()
                if getattr(claim, "confidence", None) is not None
            },
        },
        "system": {
            "governed_output_text": "",
            "governed_output_ready": state.governance.gov_class == "A",
            "rfq_confirmed": state.rfq.rfq_ready,
            "rfq_html_report": None,
            "rfq_html_report_present": False,
            "rfq_handover_initiated": bool(state.rfq.handover_status),
            "rfq_draft": {
                "has_draft": bool(state.rfq.rfq_object),
                "rfq_id": str(state.rfq.rfq_object.get("object_version") or "") or None,
                "rfq_basis_status": state.rfq.status or release_status,
                "operating_context_redacted": dict(state.rfq.confirmed_parameters or {}),
                "manufacturer_questions_mandatory": [],
                "conflicts_visible_count": len(state.rfq.blocking_findings),
                "buyer_assumptions_acknowledged": [],
            },
            "rfq_admissibility": {
                "release_status": release_status,
                "status": state.rfq.status or ("rfq_ready" if state.rfq.rfq_ready else release_status),
                "blockers": list(state.rfq.blocking_findings),
                "open_points": list(state.rfq.soft_findings),
            },
            "answer_contract": {
                "release_status": release_status,
                "required_disclaimers": list(state.governance.validity_limits),
                "recommendation_identity": None,
                "requirement_class": (
                    state.governance.requirement_class.model_dump()
                    if state.governance.requirement_class is not None
                    else None
                ),
                "requirement_class_hint": (
                    state.governance.requirement_class.class_id
                    if state.governance.requirement_class is not None
                    else None
                ),
            },
            "governance_metadata": {
                "release_status": release_status,
                "unknowns_release_blocking": missing_critical,
                "unknowns_manufacturer_validation": list(state.governance.open_validation_points),
                "assumptions_active": [],
                "scope_of_validity": list(state.governance.validity_limits),
                "required_disclaimers": list(state.governance.validity_limits),
                "review_required": False,
                "review_state": state.rfq.critical_review_status,
                "contract_obsolete": False,
            },
            "medium_capture": state.medium_capture.model_dump(),
            "medium_classification": state.medium_classification.model_dump(),
            "medium_context": state.medium_context.model_dump(),
            "evidence_state": state.evidence.model_dump(),
            "technical_derivations": technical_derivations,
            "matching_state": matching_state,
            "rfq_state": rfq_state,
            "rfq_object": dict(state.rfq.rfq_object or {}),
            "manufacturer_state": {"data_source": "candidate_derived"},
        },
    }


def _build_rfq_draft_for_ssot(
    governance: Dict[str, Any],
    rfq_state: Dict[str, Any],
    handover: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the minimal rfq_draft shape expected by workspace projection."""
    release_status = governance.get("release_status") or rfq_state.get("status") or "inadmissible"
    rfq_object = _d(rfq_state.get("rfq_object"))
    payload = rfq_object or _d(handover.get("handover_payload"))
    if not payload:
        return {}
    return {
        "has_draft": True,
        "rfq_id": str(payload.get("object_version") or payload.get("object_type") or "rfq_payload_basis_v1"),
        "rfq_basis_status": release_status,
        "operating_context_redacted": dict(payload.get("confirmed_parameters") or {}),
        "manufacturer_questions_mandatory": [],
        "conflicts_visible_count": len(list(rfq_state.get("blockers") or rfq_state.get("blocking_reasons") or [])),
        "buyer_assumptions_acknowledged": list(governance.get("assumptions_active") or []),
    }


def synthesize_workspace_state_from_ssot(state: Dict[str, Any], *, chat_id: str) -> Dict[str, Any]:
    """Build the transitional 4-pillar workspace state from canonical SSoT state."""
    working_profile: Dict[str, Any] = dict(state.get("working_profile") or {})
    sealing_state: Dict[str, Any] = dict(state.get("sealing_state") or {})
    case_state: Dict[str, Any] = dict(state.get("case_state") or {})
    governance: Dict[str, Any] = dict(sealing_state.get("governance") or {})
    cycle: Dict[str, Any] = dict(sealing_state.get("cycle") or {})
    handover: Dict[str, Any] = dict(sealing_state.get("handover") or {})
    review: Dict[str, Any] = dict(sealing_state.get("review") or {})
    selection: Dict[str, Any] = dict(sealing_state.get("selection") or {})
    parameter_meta: Dict[str, Any] = dict(case_state.get("parameter_meta") or {})
    medium_capture: Dict[str, Any] = dict(state.get("medium_capture") or case_state.get("medium_capture") or {})
    medium_classification: Dict[str, Any] = dict(state.get("medium_classification") or case_state.get("medium_classification") or {})
    medium_context: Dict[str, Any] = dict(case_state.get("medium_context") or {})
    evidence_state: Dict[str, Any] = dict(case_state.get("evidence_state") or {})
    governance_state: Dict[str, Any] = dict(case_state.get("governance_state") or {})
    matching_state: Dict[str, Any] = dict(case_state.get("matching_state") or {})
    rfq_state: Dict[str, Any] = dict(case_state.get("rfq_state") or {})
    manufacturer_state: Dict[str, Any] = dict(case_state.get("manufacturer_state") or {})
    result_contract: Dict[str, Any] = dict(case_state.get("result_contract") or {})
    sealing_requirement_spec: Dict[str, Any] = dict(case_state.get("sealing_requirement_spec") or {})
    requirement_class: Dict[str, Any] = dict(
        case_state.get("requirement_class")
        or result_contract.get("requirement_class")
        or {}
    )
    recipient_selection: Dict[str, Any] = dict(
        case_state.get("recipient_selection")
        or rfq_state.get("recipient_selection")
        or {}
    )
    case_meta: Dict[str, Any] = dict(case_state.get("case_meta") or {})

    messages = _serialize_ssot_messages(state.get("messages") or [])
    release_status = governance.get("release_status")
    rfq_admissibility = governance.get("rfq_admissibility")
    phase = case_meta.get("phase") or cycle.get("phase")
    selected_partner_id = (
        recipient_selection.get("selected_partner_id")
        or selection.get("selected_partner_id")
    )
    rfq_confirmed = bool(rfq_state.get("rfq_confirmed", handover.get("rfq_confirmed", False)))
    rfq_handover_initiated = bool(
        rfq_state.get("rfq_handover_initiated", handover.get("handover_completed", False))
    )
    rfq_object = _d(rfq_state.get("rfq_object"))
    rfq_html_report = handover.get("rfq_html_report")
    rfq_html_report_present = bool(
        rfq_state.get("rfq_html_report_present", bool(rfq_html_report) or bool(rfq_object))
    )
    required_disclaimers = list(
        governance_state.get("required_disclaimers")
        or governance.get("scope_of_validity")
        or []
    )

    _ = parameter_meta
    _ = sealing_requirement_spec

    return {
        "conversation": {
            "thread_id": chat_id,
            "messages": messages,
        },
        "working_profile": {
            "engineering_profile": working_profile,
            "extracted_params": working_profile,
        },
        "reasoning": {
            "phase": phase,
            "last_node": "facade_hydration",
            "selected_partner_id": selected_partner_id,
            "state_revision": cycle.get("state_revision", 0),
            "parameter_provenance": parameter_meta,
            "parameter_confidence": _parameter_confidence_from_meta(parameter_meta),
        },
        "system": {
            "governed_output_text": governance.get("governed_output_text") or "",
            "governed_output_ready": release_status in ("approved", "rfq_ready"),
            "rfq_confirmed": rfq_confirmed,
            "rfq_html_report": rfq_html_report,
            "rfq_html_report_present": rfq_html_report_present,
            "rfq_handover_initiated": rfq_handover_initiated,
            "rfq_draft": _build_rfq_draft_for_ssot(governance, rfq_state, handover),
            "rfq_admissibility": {
                "release_status": release_status or "inadmissible",
                "status": rfq_state.get("status") or ("ready" if release_status == "rfq_ready" else "inadmissible"),
                "blockers": list(rfq_state.get("blockers") or rfq_state.get("blocking_reasons") or []),
                "open_points": list(rfq_state.get("open_points") or []),
            },
            "answer_contract": {
                "release_status": release_status or "inadmissible",
                "required_disclaimers": required_disclaimers,
                "recommendation_identity": result_contract.get("recommendation_identity"),
                "requirement_class": requirement_class or None,
                "requirement_class_hint": result_contract.get("requirement_class_hint"),
            },
            "governance_metadata": {
                "release_status": release_status or "inadmissible",
                "unknowns_release_blocking": governance.get("unknowns_release_blocking") or [],
                "unknowns_manufacturer_validation": governance.get("unknowns_manufacturer_validation") or [],
                "assumptions_active": governance.get("assumptions_active") or [],
                "scope_of_validity": governance_state.get("scope_of_validity") or governance.get("scope_of_validity") or [],
                "required_disclaimers": required_disclaimers,
                "review_required": bool(governance_state.get("review_required", review.get("review_required", False))),
                "review_state": governance_state.get("review_state") or review.get("review_state"),
                "contract_obsolete": bool(result_contract.get("contract_obsolete", cycle.get("contract_obsolete", False))),
            },
            "medium_capture": medium_capture,
            "medium_classification": medium_classification,
            "medium_context": medium_context,
            "evidence_state": evidence_state,
            "matching_state": matching_state,
            "rfq_state": rfq_state,
            "rfq_object": rfq_object,
            "manufacturer_state": manufacturer_state,
        },
    }


def project_case_workspace_from_ssot(state: Dict[str, Any], *, chat_id: str) -> CaseWorkspaceProjection:
    """Project canonical SSoT AgentState into the public workspace contract."""
    return project_case_workspace(synthesize_workspace_state_from_ssot(state, chat_id=chat_id))


def project_case_workspace_from_governed_state(
    state: GovernedSessionState,
    *,
    chat_id: str,
) -> CaseWorkspaceProjection:
    """Project live governed state into the public workspace contract."""
    return project_case_workspace(synthesize_workspace_state_from_governed(state, chat_id=chat_id))


def project_case_workspace(state_values: Dict[str, Any]) -> CaseWorkspaceProjection:
    """Project a 4-pillar state dict into a CaseWorkspaceProjection.

    Understands both the legacy LangGraph pillar format and the synthesised
    SSoT format produced by _synthesize_state_response_from_ssot().
    """
    conversation = _d(state_values.get("conversation"))
    working_profile_pillar = _d(state_values.get("working_profile"))
    reasoning = _d(state_values.get("reasoning"))
    system = _d(state_values.get("system"))

    governance_metadata = _d(system.get("governance_metadata"))
    medium_capture = _d(system.get("medium_capture"))
    medium_classification = _d(system.get("medium_classification"))
    medium_context = _d(system.get("medium_context"))
    evidence_state = _d(system.get("evidence_state"))
    rfq_admissibility = _d(system.get("rfq_admissibility"))
    answer_contract = _d(system.get("answer_contract"))
    rfq_draft = _d(system.get("rfq_draft"))

    release_status: str = (
        governance_metadata.get("release_status")
        or answer_contract.get("release_status")
        or rfq_admissibility.get("release_status")
        or "inadmissible"
    )

    rfq_confirmed = bool(system.get("rfq_confirmed", False))
    rfq_html_report = system.get("rfq_html_report")
    rfq_html_report_present = bool(
        system.get("rfq_html_report_present", bool(rfq_html_report))
    )
    rfq_handover_initiated = bool(system.get("rfq_handover_initiated", False))
    rfq_state = _d(system.get("rfq_state"))
    matching_state = _d(system.get("matching_state"))
    manufacturer_state = _d(system.get("manufacturer_state"))
    state_revision = int(reasoning.get("state_revision") or 0)
    selected_partner_id = reasoning.get("selected_partner_id") or None

    # ── CaseSummary ────────────────────────────────────────────────────────────
    case_summary = CaseSummary(
        thread_id=conversation.get("thread_id"),
        user_id=conversation.get("user_id"),
        phase=reasoning.get("phase"),
        turn_count=int(conversation.get("turn_count") or 0),
        max_turns=int(conversation.get("max_turns") or 12),
    )

    # ── GovernanceStatus ───────────────────────────────────────────────────────
    governance_status = GovernanceStatus(
        release_status=release_status,
        unknowns_release_blocking=list(
            governance_metadata.get("unknowns_release_blocking") or []
        ),
        unknowns_manufacturer_validation=list(
            list(governance_metadata.get("unknowns_manufacturer_validation") or [])
            + list(evidence_state.get("unresolved_open_points") or [])
        ),
        assumptions_active=list(
            list(governance_metadata.get("assumptions_active") or [])
            + list(evidence_state.get("assumption_based_findings") or [])
        ),
        required_disclaimers=list(
            answer_contract.get("required_disclaimers") or []
        ),
    )

    # ── RFQStatus ──────────────────────────────────────────────────────────────
    rfq_ready = bool(rfq_admissibility.get("status") == "rfq_ready" or release_status == "rfq_ready")
    handover_ready = bool(
        rfq_state.get("handover_ready", rfq_confirmed and rfq_html_report_present and bool(selected_partner_id))
    )
    rfq_status = RFQStatus(
        admissibility_status=rfq_admissibility.get("status") or release_status,
        release_status=release_status,
        rfq_confirmed=rfq_confirmed,
        rfq_ready=rfq_ready,
        handover_ready=handover_ready,
        handover_initiated=rfq_handover_initiated,
        blockers=list(rfq_admissibility.get("blockers") or []),
        open_points=list(rfq_admissibility.get("open_points") or []),
        has_html_report=rfq_html_report_present,
    )

    # ── RFQPackageSummary ──────────────────────────────────────────────────────
    rfq_package = RFQPackageSummary(
        has_draft=bool(rfq_draft.get("has_draft", False)),
        rfq_id=rfq_draft.get("rfq_id"),
        rfq_basis_status=rfq_draft.get("rfq_basis_status") or release_status,
        operating_context_redacted=dict(rfq_draft.get("operating_context_redacted") or {}),
        manufacturer_questions_mandatory=list(rfq_draft.get("manufacturer_questions_mandatory") or []),
        conflicts_visible_count=int(rfq_draft.get("conflicts_visible_count") or 0),
        buyer_assumptions_acknowledged=list(rfq_draft.get("buyer_assumptions_acknowledged") or []),
    )

    # ── ArtifactStatus ─────────────────────────────────────────────────────────
    artifact_status = ArtifactStatus(
        has_rfq_draft=bool(rfq_draft.get("has_draft", False)),
    )

    # ── CycleInfo ──────────────────────────────────────────────────────────────
    cycle_info = CycleInfo(
        state_revision=state_revision,
        derived_artifacts_stale=bool(reasoning.get("derived_artifacts_stale", False)),
    )

    # ── PartnerMatchingSummary ─────────────────────────────────────────────────
    shortlist_ready = bool(matching_state.get("shortlist_ready", False))
    inquiry_ready = bool(matching_state.get("inquiry_ready", False) and rfq_ready)
    matching_ready = shortlist_ready
    not_ready_reasons = [
        str(item)
        for item in list(
            dict.fromkeys(
                _ls(matching_state.get("release_blockers"))
                + _ls(matching_state.get("blocking_reasons"))
            )
        )
        if item
    ]
    matchability_status = str(matching_state.get("matchability_status") or "").strip()
    if not matching_ready and not not_ready_reasons and matchability_status and matchability_status != "ready_for_matching":
        not_ready_reasons = [matchability_status]
    material_fit_items = []
    for candidate in _ls(matching_state.get("match_candidates")):
        if not isinstance(candidate, dict):
            continue
        fit_reasons = [str(item) for item in _ls(candidate.get("fit_reasons")) if item]
        block_reason = str(candidate.get("block_reason") or "").strip()
        fit_basis = "; ".join(fit_reasons) or block_reason or "governed_capability_fit"
        material_fit_items.append(
            {
                "material": str(
                    candidate.get("grade_name")
                    or candidate.get("material_family")
                    or candidate.get("candidate_id")
                    or ""
                ),
                "cluster": str(candidate.get("viability_status") or "viable"),
                "specificity": "compound_specific" if candidate.get("grade_name") else "family_only",
                "requires_validation": bool(
                    str(candidate.get("viability_status") or "viable") != "viable"
                    or release_status == "manufacturer_validation_required"
                ),
                "fit_basis": fit_basis,
                "grounded_facts": [],
            }
        )
    open_manufacturer_questions = [
        str(item)
        for item in list(
            dict.fromkeys(
                list(rfq_draft.get("manufacturer_questions_mandatory") or [])
                + list(rfq_state.get("open_points") or [])
            )
        )
        if item
    ]
    partner_matching = PartnerMatchingSummary(
        matching_ready=matching_ready,
        shortlist_ready=shortlist_ready,
        inquiry_ready=inquiry_ready,
        not_ready_reasons=not_ready_reasons,
        blocking_reasons=not_ready_reasons,
        material_fit_items=material_fit_items,
        open_manufacturer_questions=open_manufacturer_questions,
        selected_partner_id=selected_partner_id,
        data_source=str(
            matching_state.get("data_source")
            or manufacturer_state.get("data_source")
            or "candidate_derived"
        ),
    )
    communication_context = _build_communication_context(
        phase=reasoning.get("phase"),
        completeness=working_profile_pillar.get("completeness") or {},
        governance_metadata=governance_metadata,
        matching_ready=matching_ready,
        material_fit_items=material_fit_items,
        not_ready_reasons=not_ready_reasons,
        rfq_ready=rfq_ready,
        rfq_status=rfq_status,
        working_profile_pillar=working_profile_pillar,
    )
    parameters = _build_parameters_snapshot(working_profile_pillar)
    routing_profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    request_type = _derive_request_type(
        profile=routing_profile,
        system=system,
        reasoning=reasoning,
    )
    engineering_path = _derive_engineering_path(
        profile=routing_profile,
        system=system,
        reasoning=reasoning,
    )
    primary_raw_text = medium_capture.get("primary_raw_text")
    if not medium_classification and primary_raw_text:
        derived_medium = classify_medium_value(str(primary_raw_text))
        medium_classification = {
            "canonical_label": derived_medium.canonical_label,
            "family": derived_medium.family,
            "confidence": derived_medium.confidence,
            "status": derived_medium.status,
            "normalization_source": derived_medium.normalization_source,
            "mapping_confidence": derived_medium.mapping_confidence,
            "matched_alias": derived_medium.matched_alias,
            "source_registry_key": derived_medium.registry_key,
            "followup_question": derived_medium.followup_question,
        }
    medium_capture_summary = MediumCaptureSummary(
        raw_mentions=[str(item) for item in _ls(medium_capture.get("raw_mentions")) if item],
        primary_raw_text=primary_raw_text,
        source_turn_ref=medium_capture.get("source_turn_ref"),
        source_turn_index=medium_capture.get("source_turn_index"),
    )
    medium_classification_summary = MediumClassificationSummary(
        canonical_label=medium_classification.get("canonical_label"),
        family=str(medium_classification.get("family") or "unknown"),
        confidence=str(medium_classification.get("confidence") or "low"),
        status=str(medium_classification.get("status") or "unavailable"),
        normalization_source=medium_classification.get("normalization_source"),
        mapping_confidence=medium_classification.get("mapping_confidence"),
        matched_alias=medium_classification.get("matched_alias"),
        source_registry_key=medium_classification.get("source_registry_key"),
        followup_question=medium_classification.get("followup_question"),
    )
    medium_context_summary = MediumContextSummary(
        medium_label=medium_context.get("medium_label"),
        status=str(medium_context.get("status") or "unavailable"),
        scope=str(medium_context.get("scope") or "orientierend"),
        summary=medium_context.get("summary"),
        properties=[str(item) for item in _ls(medium_context.get("properties")) if item],
        challenges=[str(item) for item in _ls(medium_context.get("challenges")) if item],
        followup_points=[str(item) for item in _ls(medium_context.get("followup_points")) if item],
        confidence=medium_context.get("confidence"),
        source_type=medium_context.get("source_type"),
        not_for_release_decisions=bool(medium_context.get("not_for_release_decisions", True)),
        disclaimer=medium_context.get("disclaimer"),
    )
    technical_derivations = _build_technical_derivations(
        working_profile_pillar=working_profile_pillar,
        system=system,
    )
    checks = _build_engineering_checks(
        profile=routing_profile,
        engineering_path=engineering_path,
        technical_derivations=technical_derivations,
    )
    evidence_summary = _build_evidence_summary(evidence_state)
    claims_summary = _build_claims_summary(evidence_summary)
    completeness_payload = _d(working_profile_pillar.get("completeness"))
    cockpit_view = _build_cockpit_view(
        profile=routing_profile,
        request_type=request_type,
        engineering_path=engineering_path,
        reasoning=reasoning,
        system=system,
        rfq_status=rfq_status,
        governance_status=governance_status,
        completeness_payload=completeness_payload,
        checks=checks,
    )

    return CaseWorkspaceProjection(
        request_type=request_type,
        engineering_path=engineering_path,
        cockpit_view=cockpit_view,
        case_summary=case_summary,
        governance_status=governance_status,
        claims_summary=claims_summary,
        evidence_summary=evidence_summary,
        rfq_status=rfq_status,
        rfq_package=rfq_package,
        artifact_status=artifact_status,
        cycle_info=cycle_info,
        partner_matching=partner_matching,
        communication_context=communication_context,
        parameters=parameters,
        medium_capture=medium_capture_summary,
        medium_classification=medium_classification_summary,
        medium_context=medium_context_summary,
        technical_derivations=technical_derivations,
    )
