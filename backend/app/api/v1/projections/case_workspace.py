# backend/app/api/v1/projections/case_workspace.py
"""Workspace projection helpers for transitional v1 and canonical agent reads.

project_case_workspace maps the 4-pillar workspace state shape to
CaseWorkspaceProjection.

The additional synthesis helpers convert canonical SSoT AgentState into that
same 4-pillar shape so both `/api/v1/state/*` and `/api/agent/*` can expose the
same workspace contract without inventing a parallel projection path.
"""

from __future__ import annotations

import math
from typing import Any, Dict

from app.api.v1.projections.ptfe_rwdr_enrichment import (
    _enrich_ptfe_rwdr_workspace_inputs,
)
from app.api.v1.projections.workspace_routing import (
    _derive_engineering_path,
    _derive_request_type,
)

from app.agent.runtime.clarification_priority import (
    select_next_focus_from_known_context,
)
from app.agent.state.models import GovernedSessionState
from app.agent.domain.checks_registry import build_registered_check_results
from app.agent.domain.delta_conflicts import build_governed_conflict_summary
from app.agent.domain.dependency_graph import derived_values_for_projection
from app.agent.domain.medium_registry import classify_medium_value
from app.agent.domain.risk_readiness import evaluate_readiness, evaluate_risks
from app.domain.case_type import assign_case_type_from_legacy_routing
from app.domain.seal_type import (
    normalize_seal_type,
    type_specific_missing_hints_for_type,
)
from app.domain.source_validation import source_validation_metadata
from app.services.decision_understanding_service import (
    build_decision_understanding_projection,
)
from app.services.next_best_question_service import (
    derive_needs_current_state_and_questions,
)
from app.api.v1.schemas.case_workspace import (
    ArtifactStatus,
    CaseSummary,
    CaseWorkspaceProjection,
    ClaimItem,
    ClaimsSummary,
    CockpitProperty,
    CockpitReadinessSummary,
    CockpitRoutingMetadata,
    CompletenessStatus,
    RiskEvaluationResult,
    CockpitSection,
    CockpitSectionCompletion,
    CommunicationContext,
    ConflictSummary,
    CycleInfo,
    DeepDiveCard,
    DeepDiveTabProjection,
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
    SealApplicationProfileView,
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


def _bounded_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(score) or math.isinf(score):
        return 0.0
    return max(0.0, min(1.0, score))


def _build_completeness_status(
    *,
    payload: Dict[str, Any],
    score: Any,
    missing_fields: list[str],
) -> CompletenessStatus:
    payload_score = _bounded_score(payload.get("coverage_score"))
    projected_score = _bounded_score(score)
    coverage_score = payload_score if payload_score > 0 else projected_score
    missing_critical = _compact_unique_strings(
        [
            str(item)
            for item in (
                _ls(payload.get("missing_critical_parameters")) or missing_fields
            )
            if item
        ],
        limit=12,
    )
    coverage_gaps = _compact_unique_strings(
        [
            str(item)
            for item in (_ls(payload.get("coverage_gaps")) or missing_critical)
            if item
        ],
        limit=12,
    )
    depth = str(
        payload.get("completeness_depth")
        or ("prequalification" if coverage_score > 0 else "precheck")
    )
    return CompletenessStatus(
        coverage_score=round(coverage_score, 2),
        coverage_gaps=coverage_gaps,
        completeness_depth=depth,
        missing_critical_parameters=missing_critical,
        discovery_missing=[
            str(item) for item in _ls(payload.get("discovery_missing")) if item
        ],
        analysis_complete=bool(payload.get("analysis_complete", False)),
        recommendation_ready=bool(payload.get("recommendation_ready", False)),
    )


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

_SEAL_TYPE_TEXT_KEYS: tuple[str, ...] = (
    "sealing_type",
    "seal_type",
    "seal_family",
    "application_context",
    "application_category",
    "installation",
    "geometry_context",
    "asset_type",
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

_COCKPIT_SECTION_CONFIG: tuple[dict[str, Any], ...] = (
    {
        "section_id": "application_function",
        "title": "1. Anlage & Funktion",
        "fields": (
            {
                "key": "asset_type",
                "label": "Anlage / Baugruppe",
                "unit": None,
                "aliases": ("installation", "application_context"),
            },
            {
                "key": "asset_function",
                "label": "Funktion",
                "unit": None,
                "aliases": ("primary_function",),
            },
            {
                "key": "seal_location",
                "label": "Dichtstelle",
                "unit": None,
                "aliases": ("geometry_context",),
            },
            {
                "key": "motion_type",
                "label": "Bewegungsart",
                "unit": None,
                "aliases": ("movement_type",),
            },
            {
                "key": "primary_function",
                "label": "Dichtfunktion",
                "unit": None,
                "aliases": ("pressure_direction",),
            },
            {
                "key": "consequence_of_failure",
                "label": "Ausfallfolge",
                "unit": None,
                "aliases": ("allowable_leakage",),
            },
        ),
    },
    {
        "section_id": "medium_environment",
        "title": "2. Medium & Umgebung",
        "fields": (
            {
                "key": "medium_name",
                "label": "Medium",
                "unit": None,
                "aliases": ("medium",),
            },
            {
                "key": "medium_category",
                "label": "Medienkategorie",
                "unit": None,
                "aliases": ("medium_family",),
            },
            {
                "key": "temperature_max",
                "label": "Temperatur max.",
                "unit": "degC",
                "aliases": ("temperature_c",),
            },
            {
                "key": "particles_present",
                "label": "Partikel",
                "unit": None,
                "aliases": ("solids_percent", "contamination"),
            },
            {
                "key": "cleaning_media",
                "label": "Reinigung / CIP",
                "unit": None,
                "aliases": ("cleaning_cycles",),
            },
            {
                "key": "food_contact",
                "label": "Food/Pharma/ATEX",
                "unit": None,
                "aliases": ("compliance", "industry"),
            },
            {
                "key": "benetzung",
                "label": "Benetzung",
                "unit": None,
                "aliases": ("dry_run_possible", "duty_profile"),
            },
        ),
    },
    {
        "section_id": "operating_geometry",
        "title": "3. Betriebsdaten & Geometrie",
        "fields": (
            {
                "key": "shaft_diameter",
                "label": "Wellendurchmesser",
                "unit": "mm",
                "aliases": ("shaft_diameter_mm",),
            },
            {
                "key": "housing_bore",
                "label": "Gehäusebohrung",
                "unit": "mm",
                "aliases": ("housing_bore_mm",),
            },
            {
                "key": "installation_width",
                "label": "Einbaubreite",
                "unit": "mm",
                "aliases": ("installation_width_mm",),
            },
            {"key": "speed_rpm", "label": "Drehzahl", "unit": "rpm", "aliases": ()},
            {
                "key": "pressure_nominal",
                "label": "Betriebsdruck",
                "unit": "bar",
                "aliases": ("pressure_bar",),
            },
            {
                "key": "surface_finish",
                "label": "Oberfläche",
                "unit": None,
                "aliases": ("counterface_surface",),
            },
            {
                "key": "shaft_material",
                "label": "Wellenwerkstoff",
                "unit": None,
                "aliases": (),
            },
            {
                "key": "shaft_runout",
                "label": "Rundlauf",
                "unit": "mm",
                "aliases": ("runout_mm",),
            },
        ),
    },
    {
        "section_id": "risk_readiness",
        "title": "4. Risiken & Anfrage-Reife",
        "fields": (
            {
                "key": "top_risks",
                "label": "Top-Risiken",
                "unit": None,
                "aliases": ("contamination", "medium_qualifiers"),
            },
            {
                "key": "readiness_level",
                "label": "Readiness Level",
                "unit": None,
                "aliases": (),
            },
            {
                "key": "blocking_unknowns",
                "label": "Blockierende Unbekannte",
                "unit": None,
                "aliases": (),
            },
            {
                "key": "recommended_next_question",
                "label": "Nächste Frage",
                "unit": None,
                "aliases": (),
            },
            {
                "key": "rfq_possible",
                "label": "RFQ möglich",
                "unit": None,
                "aliases": (),
            },
            {
                "key": "compliance",
                "label": "Norm/Hygiene/ATEX",
                "unit": None,
                "aliases": ("industry",),
            },
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


def _provenance_validation_status(value: Any) -> str | None:
    if isinstance(value, dict):
        text = str(value.get("validation_status") or "").strip()
        return text or None
    return None


def _provenance_source_type(value: Any) -> str | None:
    if isinstance(value, dict):
        text = str(value.get("source_type") or "").strip()
        return text or None
    return None


def _first_mapping_value(
    mapping: Dict[str, Any], key: str, aliases: tuple[str, ...]
) -> Any:
    for candidate in (key, *aliases):
        if candidate in mapping and mapping.get(candidate) not in (None, "", []):
            return mapping.get(candidate)
    return None


def _required_key_for_field(
    key: str, aliases: tuple[str, ...], mandatory_keys: set[str]
) -> str | None:
    for candidate in (key, *aliases):
        if candidate in mandatory_keys:
            return candidate
    return None


def _cockpit_field_value(
    profile: Dict[str, Any], key: str, aliases: tuple[str, ...] = ()
) -> Any:
    for candidate in (key, *aliases):
        if candidate in profile and profile.get(candidate) not in (None, "", []):
            return profile.get(candidate)
    if key == "readiness_level":
        return profile.get("readiness_level") or profile.get("readiness")
    if key == "blocking_unknowns":
        return profile.get("blocking_unknowns") or profile.get(
            "missing_required_fields"
        )
    if key == "recommended_next_question":
        return profile.get("recommended_next_question") or profile.get(
            "pending_best_next_question"
        )
    if key == "rfq_possible":
        return profile.get("rfq_possible")
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
            aliases = tuple(str(alias) for alias in field.get("aliases", ()))
            value = _cockpit_field_value(profile, key, aliases)
            provenance_value = _first_mapping_value(provenance_map, key, aliases)
            confidence_value = _first_mapping_value(confidence_map, key, aliases)
            origin = _provenance_origin(provenance_value)
            confidence = (
                str(confidence_value).strip()
                if confidence_value not in (None, "")
                else _provenance_confidence(provenance_value)
            )
            required_key = _required_key_for_field(key, aliases, mandatory_keys)
            is_mandatory = required_key is not None
            is_confirmed = confidence == "confirmed"
            if value in (None, "", []):
                value = None
                if required_key is not None:
                    missing_mandatory_keys.append(required_key)
                origin = origin or "missing"
            status_for_source_validation = (
                "missing"
                if value is None
                else (
                    confidence
                    or _provenance_validation_status(provenance_value)
                    or "unknown"
                )
            )
            source_validation = source_validation_metadata(
                status=status_for_source_validation,
                provenance=provenance_value,
                origin=origin,
                source_type=_provenance_source_type(provenance_value),
                validation_status=_provenance_validation_status(provenance_value),
            )
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
                    source_type=source_validation.source_type,
                    validation_status=source_validation.validation_status,
                    is_confirmed=is_confirmed,
                    is_mandatory=is_mandatory,
                )
            )

        percent = (
            int(round((mandatory_present / mandatory_total) * 100))
            if mandatory_total
            else 100
        )
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
    initial_sections, missing_mandatory_keys = _build_cockpit_sections(
        profile=profile,
        engineering_path=engineering_path,
        reasoning=reasoning,
    )
    del initial_sections
    blockers = [
        str(item)
        for item in dict.fromkeys(
            list(rfq_status.blockers) + list(governance_status.gate_failures)
        )
        if item
    ]
    risk_evaluations_raw = evaluate_risks(
        profile,
        engineering_path=str(engineering_path or "") or None,
        missing_required_fields=[],
        checks=checks,
    )
    readiness_eval = evaluate_readiness(
        profile,
        request_type=str(request_type or "") or None,
        engineering_path=str(engineering_path or "") or None,
        missing_mandatory_keys=missing_mandatory_keys,
        blockers=blockers,
        risk_results=risk_evaluations_raw,
    )
    cockpit_profile = dict(profile)
    cockpit_profile.update(readiness_eval.to_profile_patch())
    top_risks = [
        item.risk_name for item in risk_evaluations_raw if item.score in {2, 3, 4, 9}
    ][:3]
    if top_risks:
        cockpit_profile["top_risks"] = top_risks
    sections, missing_mandatory_keys = _build_cockpit_sections(
        profile=cockpit_profile,
        engineering_path=engineering_path,
        reasoning=reasoning,
    )
    coverage_score = _bounded_score(completeness_payload.get("coverage_score"))
    is_rfq_ready = bool(rfq_status.rfq_ready or readiness_eval.rfq_possible)
    status = (
        "rfq_ready"
        if is_rfq_ready
        else ("preliminary" if missing_mandatory_keys else "review_needed")
    )
    risk_evaluations = [
        RiskEvaluationResult.model_validate(item.to_dict())
        for item in risk_evaluations_raw
    ]
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
        risk_evaluations=risk_evaluations,
        missing_mandatory_keys=missing_mandatory_keys,
        blockers=blockers,
        readiness=CockpitReadinessSummary(
            status=status,
            is_rfq_ready=is_rfq_ready,
            release_status=governance_status.release_status,
            coverage_score=coverage_score,
            readiness_level=readiness_eval.readiness_level,
            readiness_label=readiness_eval.readiness_label,
            missing_required_fields=readiness_eval.missing_required_fields,
            blocking_unknowns=readiness_eval.blocking_unknowns,
            recommended_next_question=readiness_eval.recommended_next_question,
            rfq_possible=readiness_eval.rfq_possible,
            risk_score_max=readiness_eval.risk_score_max,
            risk_label_max=readiness_eval.risk_label_max,
            ruleset_version=readiness_eval.ruleset_version,
        ),
    )


def _stringify_value(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (list, tuple, set)):
        rendered = ", ".join(str(item) for item in value if item not in (None, ""))
        return rendered or None
    if isinstance(value, bool):
        return "ja" if value else "nein"
    return str(value)


def _deep_value(profile: Dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _cockpit_field_value(profile, key)
        rendered = _stringify_value(value)
        if rendered:
            return rendered
    return None


def _compact_items(items: list[str | None], *, limit: int = 6) -> list[str]:
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


def _section_values(cockpit_view: EngineeringCockpitView, section_id: str) -> list[str]:
    for section in cockpit_view.sections:
        if section.section_id != section_id:
            continue
        values: list[str] = []
        for prop in section.properties:
            rendered = _stringify_value(prop.value)
            if rendered:
                unit = f" {prop.unit}" if prop.unit else ""
                values.append(f"{prop.label}: {rendered}{unit}")
        return values
    return []


def _build_deep_dive_tabs(
    *,
    profile: Dict[str, Any],
    cockpit_view: EngineeringCockpitView,
    medium_context: MediumContextSummary,
    partner_matching: PartnerMatchingSummary,
    communication_context: CommunicationContext,
    technical_derivations: list[TechnicalDerivationItem],
) -> list[DeepDiveTabProjection]:
    medium_label = (
        medium_context.medium_label
        or _deep_value(profile, "medium_name", "medium")
        or "Medium noch offen"
    )
    seal_type = _deep_value(profile, "sealing_type", "seal_type") or (
        "PTFE-RWDR"
        if str(cockpit_view.engineering_path or "") == "rwdr"
        else "Dichtungstyp noch offen"
    )
    application = (
        _deep_value(profile, "asset_type", "installation", "application_context")
        or "Anlage noch offen"
    )
    motion = (
        _deep_value(profile, "motion_type", "movement_type") or "Bewegung noch offen"
    )
    geometry = (
        _deep_value(
            profile,
            "geometry",
            "geometry_context",
            "shaft_diameter",
            "shaft_diameter_mm",
        )
        or "Geometrie noch offen"
    )
    material_items = _compact_items(
        [item.material for item in partner_matching.material_fit_items if item.material]
    )
    if not material_items:
        material_items = _compact_items(
            [
                _deep_value(profile, "material"),
                _deep_value(profile, "shaft_material"),
                "Werkstoffrichtung noch nicht belastbar eingegrenzt",
            ]
        )
    risk_items = _compact_items(
        [
            risk.explanation_short or risk.risk_name
            for risk in cockpit_view.risk_evaluations
            if risk.score in {2, 3, 4, 9}
        ],
        limit=4,
    )
    missing = _compact_items(
        list(cockpit_view.readiness.missing_required_fields)
        + list(cockpit_view.readiness.blocking_unknowns)
        + list(cockpit_view.missing_mandatory_keys),
        limit=6,
    )
    next_action = (
        cockpit_view.readiness.recommended_next_question
        or communication_context.primary_question
        or "Naechste fehlende Pflichtangabe in der Analyse klaeren."
    )
    calc_items = []
    for item in technical_derivations:
        if item.v_surface_m_s is not None:
            calc_items.append(f"Umfangsgeschwindigkeit: {item.v_surface_m_s} m/s")
        if item.pv_value_mpa_m_s is not None:
            calc_items.append(f"p·v: {item.pv_value_mpa_m_s} MPa·m/s")
        calc_items.extend(item.notes[:2])

    return [
        DeepDiveTabProjection(
            tab_id="analysis",
            label="Analyse",
            detected=_compact_items([application, motion, medium_label, seal_type]),
            relevance="Fuehrt die fallbezogene technische Einordnung zusammen und zeigt, ob daraus bereits eine Herstelleranfrage vorbereitet werden kann.",
            opportunities=_compact_items(
                [
                    "Strukturierte Anfragebasis",
                    "sichtbare offene Punkte",
                    "governed Projection statt Chat-Schaetzung",
                ]
            ),
            risks=risk_items,
            derived_direction=f"Aktueller Pfad: {_stringify_value(cockpit_view.engineering_path) or 'noch offen'}; Readiness Level {cockpit_view.readiness.readiness_level}.",
            missing=missing,
            next_action=next_action,
            cards=[
                DeepDiveCard(
                    title="Was wurde erkannt?",
                    body=" | ".join(
                        _section_values(cockpit_view, "application_function")[:4]
                    )
                    or "Noch keine belastbare Anlagenprojektion.",
                ),
                DeepDiveCard(
                    title="Rueckfuehrung", body=next_action or "Zurueck zur Analyse."
                ),
            ],
        ),
        DeepDiveTabProjection(
            tab_id="medium",
            label="Medium",
            status=medium_context.status,
            detected=_compact_items([medium_label, medium_context.summary]),
            relevance="Das Medium bestimmt Werkstofffenster, Schmierung, Korrosions-/Quellrisiken und offene Herstellerpruefpunkte.",
            opportunities=_compact_items(
                list(medium_context.properties) + ["fruehe Werkstoff-Eingrenzung"]
            ),
            risks=_compact_items(list(medium_context.challenges) + risk_items, limit=5),
            derived_direction=medium_context.summary
            or f"{medium_label} ist als Medium im Fallkontext erfasst, aber noch nicht final validiert.",
            missing=_compact_items(
                list(medium_context.followup_points) + missing, limit=6
            ),
            next_action=(
                medium_context.followup_points[0]
                if medium_context.followup_points
                else next_action
            ),
            cards=[
                DeepDiveCard(
                    title="Medium-Kontext",
                    body=medium_context.summary
                    or "Noch keine vertiefte Medium-Projektion verfuegbar.",
                    items=list(medium_context.properties),
                ),
                DeepDiveCard(
                    title="Grenzen",
                    body=medium_context.disclaimer
                    or "Medium-Hinweise bleiben orientierend bis zur Hersteller-/Datenpruefung.",
                    items=list(medium_context.challenges),
                ),
            ],
        ),
        DeepDiveTabProjection(
            tab_id="material",
            label="Werkstoff",
            detected=material_items,
            relevance="Werkstofffragen muessen gegen Medium, Temperatur, Dynamik, Gegenlaufflaeche und Validierungsbedarf gespiegelt werden.",
            opportunities=_compact_items(
                [
                    "Kandidaten koennen transparent vorqualifiziert werden",
                    "Herstellerfreigabe bleibt finale Instanz",
                ]
                + material_items[:2]
            ),
            risks=_compact_items(
                risk_items + list(partner_matching.not_ready_reasons), limit=5
            ),
            derived_direction=(
                "; ".join(material_items[:3])
                if material_items
                else "Noch keine belastbare Werkstoffrichtung."
            ),
            missing=(
                _compact_items(
                    [
                        _deep_value(profile, "shaft_material"),
                        _deep_value(profile, "surface_finish"),
                    ],
                    limit=2,
                )
                if False
                else _compact_items(
                    [
                        m
                        for m in missing
                        if m
                        in {
                            "surface_finish",
                            "shaft_material",
                            "medium_name",
                            "temperature_max",
                        }
                    ]
                    or missing[:3]
                )
            ),
            next_action=next_action,
            cards=[
                DeepDiveCard(
                    title="Werkstoffbasis",
                    body="Fallbezogene Werkstoffrichtung aus Matching-/Risikoprojektion.",
                    items=material_items,
                ),
                DeepDiveCard(
                    title="Validierung",
                    body="Keine finale Werkstofffreigabe ohne Herstellerpruefung und vollstaendige Betriebsdaten.",
                    items=list(partner_matching.open_manufacturer_questions[:4]),
                ),
            ],
        ),
        DeepDiveTabProjection(
            tab_id="seal_type",
            label="Dichtungstyp",
            detected=_compact_items([seal_type, geometry, motion]),
            relevance="Der Dichtungstyp grenzt Loesungsraum, Geometrie, Berechnungen und Hersteller-Capabilities ein.",
            opportunities=_compact_items(
                [
                    "Pfadlogik kann gezielt Pflichtfelder priorisieren",
                    "Shallow Paths bleiben bewusst vorlaeufig",
                ]
            ),
            risks=_compact_items(
                [item for item in risk_items if item]
                + [
                    "Dichtungstyp darf ohne Geometrie und Betriebsdaten nicht final behauptet werden"
                ],
                limit=5,
            ),
            derived_direction=f"Aktuelle Dichtungstyp-Richtung: {seal_type}.",
            missing=_compact_items(
                [
                    m
                    for m in missing
                    if m
                    in {
                        "seal_location",
                        "geometry",
                        "shaft_diameter",
                        "speed_rpm",
                        "pressure_nominal",
                    }
                ]
                or missing[:3]
            ),
            next_action=next_action,
            cards=[
                DeepDiveCard(
                    title="Typ-Richtung",
                    body=f"{seal_type} im Kontext {motion}, {geometry}.",
                    items=calc_items[:4],
                ),
                DeepDiveCard(
                    title="Rueckfuehrung", body=next_action or "Zurueck zur Analyse."
                ),
            ],
        ),
    ]


def _build_confirmed_facts_summary(working_profile_pillar: Dict[str, Any]) -> list[str]:
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    facts: list[str] = []
    for key in (
        "movement_type",
        "application_context",
        "medium",
        "pressure_bar",
        "temperature_c",
    ):
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


def _build_parameters_snapshot(
    working_profile_pillar: Dict[str, Any],
) -> Dict[str, Any]:
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


def _list_of_strings(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _build_seal_application_profile(
    *,
    profile: Dict[str, Any],
    system: Dict[str, Any],
    engineering_path: WorkspaceEngineeringPath | None,
) -> SealApplicationProfileView:
    text_parts = []
    for key in _SEAL_TYPE_TEXT_KEYS:
        rendered = _stringify_value(profile.get(key))
        if rendered:
            text_parts.append(rendered)
    seal_type_text = " ".join(text_parts) or None
    result = normalize_seal_type(
        seal_type_text,
        context={
            "profile": profile,
            "engineering_path": engineering_path,
            "routing": _d(system.get("routing")),
        },
    )
    return SealApplicationProfileView(
        seal_family=result.seal_family,
        seal_type=result.seal_type,
        seal_type_confidence=result.confidence,
        confidence_band=result.confidence_band,
        matched_alias=result.matched_alias,
        ambiguous=result.ambiguous,
        candidate_types=list(result.candidate_types),
        application_domain=_deep_value(
            profile,
            "application_domain",
            "application_context",
            "application_category",
            "industry",
        ),
        motion_type=_deep_value(profile, "motion_type", "movement_type"),
        standard_refs=_list_of_strings(
            profile.get("standard_refs")
            or profile.get("norm_references")
            or profile.get("standard")
        ),
        type_specific_missing_hints=list(
            type_specific_missing_hints_for_type(result.seal_type)
        ),
        notes=list(result.notes),
        source=result.source,
    )


def _parameter_confidence_from_meta(parameter_meta: Dict[str, Any]) -> Dict[str, str]:
    confidence_map: Dict[str, str] = {}
    for key, value in parameter_meta.items():
        if not isinstance(value, dict):
            continue
        confidence = str(value.get("confidence") or "").strip()
        if confidence:
            confidence_map[str(key)] = confidence
    return confidence_map


def _technical_derivation_from_live_calc_tile(
    tile: Dict[str, Any],
) -> TechnicalDerivationItem | None:
    if not tile:
        return None
    if not any(
        tile.get(key) is not None
        for key in (
            "v_surface_m_s",
            "pv_value_mpa_m_s",
            "dn_value",
            "temperature_headroom_c",
            "pressure_window",
        )
    ):
        return None
    return TechnicalDerivationItem(
        calc_type="rwdr",
        status=str(tile.get("status") or "insufficient_data"),
        v_surface_m_s=tile.get("v_surface_m_s"),
        pv_value_mpa_m_s=tile.get("pv_value_mpa_m_s"),
        dn_value=tile.get("dn_value"),
        temperature_headroom_c=tile.get("temperature_headroom_c"),
        pressure_window=tile.get("pressure_window"),
        notes=[str(item) for item in _ls(tile.get("notes")) if item],
    )


def _float_from_profile(profile: Dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = profile.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", ".").strip())
        except (TypeError, ValueError):
            continue
    return None


def _technical_derivation_from_current_profile(
    profile: Dict[str, Any],
) -> TechnicalDerivationItem | None:
    shaft_diameter_mm = _float_from_profile(
        profile, "shaft_diameter_mm", "shaft_diameter", "diameter"
    )
    speed_rpm = _float_from_profile(profile, "speed_rpm", "rpm", "speed")
    temperature_c = _float_from_profile(
        profile, "temperature_c", "temperature_max_c", "temperature"
    )
    material_family = (
        str(
            profile.get("sealing_material_family")
            or profile.get("material_family")
            or profile.get("compound_family")
            or profile.get("ptfe_compound_family")
            or profile.get("material")
            or ""
        )
        .strip()
        .casefold()
    )
    temperature_headroom_c: float | None = None
    if temperature_c is not None and material_family:
        limit = 260.0 if material_family.startswith("ptfe") else 180.0
        temperature_headroom_c = round(limit - temperature_c, 2)

    has_dynamic_inputs = shaft_diameter_mm is not None and speed_rpm is not None
    if not has_dynamic_inputs and temperature_headroom_c is None:
        return None

    v_surface_m_s = (
        math.pi * shaft_diameter_mm / 1000.0 * speed_rpm / 60.0
        if has_dynamic_inputs
        and shaft_diameter_mm is not None
        and speed_rpm is not None
        else None
    )
    pressure_bar = _float_from_profile(
        profile, "pressure_bar", "pressure_nominal", "pressure_max_bar", "pressure"
    )
    sealing_type = _deep_value(profile, "sealing_type", "seal_type")
    pv_value_mpa_m_s = (
        pressure_bar * 0.1 * v_surface_m_s
        if pressure_bar is not None and v_surface_m_s is not None
        else None
    )
    pressure_window = (
        (
            f"{pressure_bar:g} bar · RWDR-Druckfenster herstellerseitig prüfen"
            if "rwdr" in str(sealing_type).casefold()
            or "radial" in str(sealing_type).casefold()
            else f"{pressure_bar:g} bar · Dichtungsbauart herstellerseitig prüfen"
        )
        if pressure_bar is not None and sealing_type
        else None
    )
    dn_value = (
        shaft_diameter_mm * speed_rpm
        if shaft_diameter_mm is not None and speed_rpm is not None
        else None
    )

    return TechnicalDerivationItem(
        calc_type="rwdr",
        status="ok",
        v_surface_m_s=round(v_surface_m_s, 2) if v_surface_m_s is not None else None,
        pv_value_mpa_m_s=(
            round(pv_value_mpa_m_s, 2) if pv_value_mpa_m_s is not None else None
        ),
        dn_value=round(dn_value, 2) if dn_value is not None else None,
        temperature_headroom_c=temperature_headroom_c,
        pressure_window=pressure_window,
        notes=[
            "Deterministisch aus aktuellen Workspace-Parametern berechnet; keine Herstellerfreigabe."
        ],
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

    live_calc_tile = _d(working_profile_pillar.get("live_calc_tile")) or _d(
        system.get("live_calc_tile")
    )
    profile = _d(working_profile_pillar.get("engineering_profile")) or _d(
        working_profile_pillar.get("extracted_params")
    )
    live_calc_derivation = _technical_derivation_from_live_calc_tile(
        live_calc_tile
    ) or _technical_derivation_from_current_profile(profile)
    if live_calc_derivation is not None and not any(
        item.calc_type == "rwdr" for item in items
    ):
        items.insert(0, live_calc_derivation)
    return items


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
        evidence_supported_topics=[
            str(item)
            for item in _ls(evidence_state.get("evidence_supported_topics"))
            if item
        ],
        source_backed_findings=[
            str(item)
            for item in _ls(evidence_state.get("source_backed_findings"))
            if item
        ],
        deterministic_findings=[
            str(item)
            for item in _ls(evidence_state.get("deterministic_findings"))
            if item
        ],
        assumption_based_findings=[
            str(item)
            for item in _ls(evidence_state.get("assumption_based_findings"))
            if item
        ],
        unresolved_open_points=[
            str(item)
            for item in _ls(evidence_state.get("unresolved_open_points"))
            if item
        ],
        evidence_gaps=[
            str(item) for item in _ls(evidence_state.get("evidence_gaps")) if item
        ],
    )


def _build_claims_summary(evidence_summary: EvidenceSummary) -> ClaimsSummary:
    items: list[ClaimItem] = []
    for finding in evidence_summary.deterministic_findings:
        items.append(
            ClaimItem(
                value=finding,
                claim_type="deterministic_fact",
                claim_origin="deterministic",
            )
        )
    for finding in evidence_summary.source_backed_findings:
        items.append(
            ClaimItem(
                value=finding,
                claim_type="source_backed_finding",
                claim_origin="evidence",
            )
        )
    for finding in evidence_summary.assumption_based_findings:
        items.append(
            ClaimItem(
                value=finding,
                claim_type="assumption_based_finding",
                claim_origin="assumption",
            )
        )
    for finding in evidence_summary.unresolved_open_points:
        items.append(
            ClaimItem(
                value=finding, claim_type="unresolved_open_point", claim_origin="open"
            )
        )
    for finding in evidence_summary.evidence_gaps:
        items.append(
            ClaimItem(
                value=finding, claim_type="evidence_gap", claim_origin="evidence_gap"
            )
        )

    by_type: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    for item in items:
        by_type[item.claim_type] = by_type.get(item.claim_type, 0) + 1
        by_origin[item.claim_origin] = by_origin.get(item.claim_origin, 0) + 1

    return ClaimsSummary(
        total=len(items), by_type=by_type, by_origin=by_origin, items=items
    )


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
    return any(
        marker in text
        for marker in ("rotierend", "welle", "wellen", "rwdr", "wellendichtring")
    )


def _filter_stale_focus_points(
    items: list[str], *, profile: Dict[str, Any]
) -> list[str]:
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
    missing = [
        str(item)
        for item in _ls(completeness.get("missing_critical_parameters"))
        if item
    ]
    unknowns = [
        str(item)
        for item in list(
            dict.fromkeys(
                list(governance_metadata.get("unknowns_release_blocking") or [])
                + list(
                    governance_metadata.get("unknowns_manufacturer_validation") or []
                )
            )
        )
        if item
    ]

    confirmed_facts_summary = _build_confirmed_facts_summary(working_profile_pillar)
    known_fields = {
        str(key) for key, value in profile.items() if value not in (None, "")
    }
    focus_priority = None
    if any(
        profile.get(key) not in (None, "")
        for key in (
            "movement_type",
            "application_context",
            "installation",
            "geometry_context",
            "speed_rpm",
            "shaft_diameter_mm",
        )
    ):
        focus_priority = select_next_focus_from_known_context(
            known_fields=known_fields,
            medium_status=(
                "recognized" if profile.get("medium") not in (None, "") else "unknown"
            ),
            current_text=" ".join(str(item) for item in confirmed_facts_summary),
            application_anchor_present=bool(
                profile.get("application_context")
                or profile.get("movement_type")
                or profile.get("installation")
            ),
            rotary_context_detected=bool(
                profile.get("movement_type") == "rotary"
                or {"speed_rpm", "shaft_diameter_mm"} & known_fields
            ),
        )

    if missing or unknowns:
        prioritized_open_points = (
            [focus_priority.open_point_label] if focus_priority is not None else []
        )
        open_points_summary = _compact_unique_strings(
            _filter_stale_focus_points(
                prioritized_open_points + missing + unknowns, profile=profile
            )
        )
        return CommunicationContext(
            conversation_phase="clarification",
            turn_goal="clarify_primary_open_point",
            primary_question=(
                focus_priority.question
                if focus_priority is not None
                else _question_from_open_point(
                    open_points_summary[0] if open_points_summary else None
                )
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
                [
                    str(item)
                    for item in list(rfq_status.open_points) + list(rfq_status.blockers)
                    if item
                ]
            ),
        )

    if matching_ready or material_fit_items:
        return CommunicationContext(
            conversation_phase="matching",
            turn_goal="explain_matching_result",
            response_mode="result_summary",
            confirmed_facts_summary=confirmed_facts_summary,
            open_points_summary=_compact_unique_strings(
                not_ready_reasons or list(rfq_status.open_points)
            ),
        )

    mapped_phase = (
        "exploration" if phase in {"intake", "conversation"} else "recommendation"
    )
    return CommunicationContext(
        conversation_phase=mapped_phase,
        turn_goal="explain_governed_result",
        response_mode="guided_explanation",
        confirmed_facts_summary=confirmed_facts_summary,
        open_points_summary=_compact_unique_strings(
            [str(item) for item in list(rfq_status.open_points) if item]
        ),
    )


def _serialize_ssot_messages(messages: list) -> list:
    """Serialize LangChain message objects into JSON-safe dicts."""
    result = []
    for msg in messages or []:
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
    if (
        state.matching.status == "matched_primary_candidate"
        or state.governance.gov_class == "A"
    ):
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
    for derived_item in derived_values_for_projection(state.derived):
        value_id = str(
            derived_item.get("id") or derived_item.get("calculation_id") or "unknown"
        )
        item: dict[str, Any] = {
            "calc_type": value_id,
            "status": str(derived_item.get("status") or "unknown"),
            "value": derived_item.get("value"),
            "derived_value_id": value_id,
            "derived_from_fields": list(derived_item.get("derived_from_fields") or []),
            "derived_from_revision": int(
                derived_item.get("derived_from_revision") or 0
            ),
            "calculation_id": str(derived_item.get("calculation_id") or value_id),
            "ruleset_version": derived_item.get("ruleset_version"),
            "stale_reason": derived_item.get("stale_reason"),
            "notes": [],
        }
        if value_id == "rwdr_circumferential_speed":
            item["v_surface_m_s"] = derived_item.get("value")
        elif value_id == "rwdr_pv_precheck":
            item["pv_value_mpa_m_s"] = derived_item.get("value")
        elif value_id == "rwdr_dn_value":
            item["dn_value"] = derived_item.get("value")
        technical_derivations.append(item)

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
                "temperature_headroom_c": result.get("temperature_headroom_c"),
                "pressure_window": result.get("pressure_window"),
                "notes": [
                    str(item) for item in list(result.get("notes") or []) if item
                ],
            }
        )
    if technical_derivations:
        working_profile["live_calc_tile"] = {
            "status": technical_derivations[0].get("status"),
            "v_surface_m_s": technical_derivations[0].get("v_surface_m_s"),
            "pv_value_mpa_m_s": technical_derivations[0].get("pv_value_mpa_m_s"),
            "dn_value": technical_derivations[0].get("dn_value"),
            "temperature_headroom_c": technical_derivations[0].get(
                "temperature_headroom_c"
            ),
            "pressure_window": technical_derivations[0].get("pressure_window"),
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
                "grade_name": (
                    capability.grade_names[0] if capability.grade_names else None
                ),
                "material_family": (
                    capability.material_families[0]
                    if capability.material_families
                    else None
                ),
                "fit_reasons": list(capability.capability_hints),
                "viability_status": (
                    "viable"
                    if capability.qualified_for_rfq
                    else "manufacturer_validation_required"
                ),
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
    user_turn_count = sum(
        1
        for item in state.conversation_messages
        if getattr(item, "role", None) == "user"
    )
    phase = (
        "rfq_handover"
        if state.rfq.rfq_ready
        else (
            "matching"
            if state.matching.status == "matched_primary_candidate"
            else (
                "recommendation"
                if state.governance.gov_class in {"A", "B"}
                else "clarification"
            )
        )
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
            sum(
                1
                for field_name in tracked_basis_fields
                if field_name in state.asserted.assertions
            )
            / len(tracked_basis_fields),
            2,
        ),
    )
    analysis_complete = state.governance.gov_class == "A" and not missing_critical
    completeness = {
        "coverage_score": coverage_score,
        "coverage_gaps": missing_critical,
        "completeness_depth": (
            "governed" if state.governance.gov_class in {"A", "B"} else "precheck"
        ),
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
            "derived_artifacts_stale": bool(state.derived.stale_derived_value_ids),
            "stale_reason": ", ".join(state.derived.stale_derived_value_ids) or None,
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
                "operating_context_redacted": dict(
                    state.rfq.confirmed_parameters or {}
                ),
                "manufacturer_questions_mandatory": [],
                "conflicts_visible_count": len(state.rfq.blocking_findings)
                + int(build_governed_conflict_summary(state).get("open") or 0),
                "buyer_assumptions_acknowledged": [],
            },
            "rfq_admissibility": {
                "release_status": release_status,
                "status": state.rfq.status
                or ("rfq_ready" if state.rfq.rfq_ready else release_status),
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
                "unknowns_manufacturer_validation": list(
                    state.governance.open_validation_points
                ),
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
            "conflict_summary": build_governed_conflict_summary(state),
        },
    }


def _build_rfq_draft_for_ssot(
    governance: Dict[str, Any],
    rfq_state: Dict[str, Any],
    handover: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the minimal rfq_draft shape expected by workspace projection."""
    release_status = (
        governance.get("release_status") or rfq_state.get("status") or "inadmissible"
    )
    rfq_object = _d(rfq_state.get("rfq_object"))
    payload = rfq_object or _d(handover.get("handover_payload"))
    if not payload:
        return {}
    return {
        "has_draft": True,
        "rfq_id": str(
            payload.get("object_version")
            or payload.get("object_type")
            or "rfq_payload_basis_v1"
        ),
        "rfq_basis_status": release_status,
        "operating_context_redacted": dict(payload.get("confirmed_parameters") or {}),
        "manufacturer_questions_mandatory": [],
        "conflicts_visible_count": len(
            list(rfq_state.get("blockers") or rfq_state.get("blocking_reasons") or [])
        ),
        "buyer_assumptions_acknowledged": list(
            governance.get("assumptions_active") or []
        ),
    }


def synthesize_workspace_state_from_ssot(
    state: Dict[str, Any], *, chat_id: str
) -> Dict[str, Any]:
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
    medium_capture: Dict[str, Any] = dict(
        state.get("medium_capture") or case_state.get("medium_capture") or {}
    )
    medium_classification: Dict[str, Any] = dict(
        state.get("medium_classification")
        or case_state.get("medium_classification")
        or {}
    )
    medium_context: Dict[str, Any] = dict(case_state.get("medium_context") or {})
    evidence_state: Dict[str, Any] = dict(case_state.get("evidence_state") or {})
    governance_state: Dict[str, Any] = dict(case_state.get("governance_state") or {})
    matching_state: Dict[str, Any] = dict(case_state.get("matching_state") or {})
    rfq_state: Dict[str, Any] = dict(case_state.get("rfq_state") or {})
    manufacturer_state: Dict[str, Any] = dict(
        case_state.get("manufacturer_state") or {}
    )
    result_contract: Dict[str, Any] = dict(case_state.get("result_contract") or {})
    sealing_requirement_spec: Dict[str, Any] = dict(
        case_state.get("sealing_requirement_spec") or {}
    )
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
    selected_partner_id = recipient_selection.get(
        "selected_partner_id"
    ) or selection.get("selected_partner_id")
    rfq_confirmed = bool(
        rfq_state.get("rfq_confirmed", handover.get("rfq_confirmed", False))
    )
    rfq_handover_initiated = bool(
        rfq_state.get(
            "rfq_handover_initiated", handover.get("handover_completed", False)
        )
    )
    rfq_object = _d(rfq_state.get("rfq_object"))
    rfq_html_report = handover.get("rfq_html_report")
    rfq_html_report_present = bool(
        rfq_state.get(
            "rfq_html_report_present", bool(rfq_html_report) or bool(rfq_object)
        )
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
                "status": rfq_state.get("status")
                or ("ready" if release_status == "rfq_ready" else "inadmissible"),
                "blockers": list(
                    rfq_state.get("blockers") or rfq_state.get("blocking_reasons") or []
                ),
                "open_points": list(rfq_state.get("open_points") or []),
            },
            "answer_contract": {
                "release_status": release_status or "inadmissible",
                "required_disclaimers": required_disclaimers,
                "recommendation_identity": result_contract.get(
                    "recommendation_identity"
                ),
                "requirement_class": requirement_class or None,
                "requirement_class_hint": result_contract.get("requirement_class_hint"),
            },
            "governance_metadata": {
                "release_status": release_status or "inadmissible",
                "unknowns_release_blocking": governance.get("unknowns_release_blocking")
                or [],
                "unknowns_manufacturer_validation": governance.get(
                    "unknowns_manufacturer_validation"
                )
                or [],
                "assumptions_active": governance.get("assumptions_active") or [],
                "scope_of_validity": governance_state.get("scope_of_validity")
                or governance.get("scope_of_validity")
                or [],
                "required_disclaimers": required_disclaimers,
                "review_required": bool(
                    governance_state.get(
                        "review_required", review.get("review_required", False)
                    )
                ),
                "review_state": governance_state.get("review_state")
                or review.get("review_state"),
                "contract_obsolete": bool(
                    result_contract.get(
                        "contract_obsolete", cycle.get("contract_obsolete", False)
                    )
                ),
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


def project_case_workspace_from_ssot(
    state: Dict[str, Any], *, chat_id: str
) -> CaseWorkspaceProjection:
    """Project canonical SSoT AgentState into the public workspace contract."""
    return project_case_workspace(
        synthesize_workspace_state_from_ssot(state, chat_id=chat_id)
    )


def project_case_workspace_from_governed_state(
    state: GovernedSessionState,
    *,
    chat_id: str,
) -> CaseWorkspaceProjection:
    """Project live governed state into the public workspace contract."""
    return project_case_workspace(
        synthesize_workspace_state_from_governed(state, chat_id=chat_id)
    )


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

    routing_profile_for_enrichment = _d(
        working_profile_pillar.get("engineering_profile")
    ) or _d(working_profile_pillar.get("extracted_params"))
    engineering_path_for_enrichment = _derive_engineering_path(
        profile=routing_profile_for_enrichment,
        system=system,
        reasoning=reasoning,
    )
    system, matching_state, medium_context = _enrich_ptfe_rwdr_workspace_inputs(
        routing_profile=routing_profile_for_enrichment,
        engineering_path=engineering_path_for_enrichment,
        system=system,
        matching_state=matching_state,
        medium_context=medium_context,
    )

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
        required_disclaimers=list(answer_contract.get("required_disclaimers") or []),
    )

    # ── RFQStatus ──────────────────────────────────────────────────────────────
    rfq_ready = bool(
        rfq_admissibility.get("status") == "rfq_ready" or release_status == "rfq_ready"
    )
    handover_ready = bool(
        rfq_state.get(
            "handover_ready",
            rfq_confirmed and rfq_html_report_present and bool(selected_partner_id),
        )
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
        operating_context_redacted=dict(
            rfq_draft.get("operating_context_redacted") or {}
        ),
        manufacturer_questions_mandatory=list(
            rfq_draft.get("manufacturer_questions_mandatory") or []
        ),
        conflicts_visible_count=int(rfq_draft.get("conflicts_visible_count") or 0),
        buyer_assumptions_acknowledged=list(
            rfq_draft.get("buyer_assumptions_acknowledged") or []
        ),
    )

    # ── ArtifactStatus ─────────────────────────────────────────────────────────
    artifact_status = ArtifactStatus(
        has_rfq_draft=bool(rfq_draft.get("has_draft", False)),
    )

    # ── CycleInfo ──────────────────────────────────────────────────────────────
    cycle_info = CycleInfo(
        state_revision=state_revision,
        derived_artifacts_stale=bool(reasoning.get("derived_artifacts_stale", False)),
        stale_reason=reasoning.get("stale_reason"),
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
    if (
        not matching_ready
        and not not_ready_reasons
        and matchability_status
        and matchability_status != "ready_for_matching"
    ):
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
                "specificity": (
                    "compound_specific"
                    if candidate.get("grade_name")
                    else "family_only"
                ),
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
    case_type_assignment = assign_case_type_from_legacy_routing(
        request_type=request_type,
        engineering_path=engineering_path,
        routing=_d(system.get("routing")),
    )
    case_type = case_type_assignment.case_type
    routing_metadata = _d(system.get("routing"))
    routing_metadata.setdefault("case_type", case_type.value)
    routing_metadata.setdefault("case_type_event", case_type_assignment.event_name)
    system = dict(system)
    system["routing"] = routing_metadata
    seal_application_profile = _build_seal_application_profile(
        profile=routing_profile,
        system=system,
        engineering_path=engineering_path,
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
        raw_mentions=[
            str(item) for item in _ls(medium_capture.get("raw_mentions")) if item
        ],
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
        properties=[
            str(item) for item in _ls(medium_context.get("properties")) if item
        ],
        challenges=[
            str(item) for item in _ls(medium_context.get("challenges")) if item
        ],
        followup_points=[
            str(item) for item in _ls(medium_context.get("followup_points")) if item
        ],
        confidence=medium_context.get("confidence"),
        source_type=medium_context.get("source_type"),
        validation_status=medium_context.get("validation_status"),
        not_for_release_decisions=bool(
            medium_context.get("not_for_release_decisions", True)
        ),
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
    conflicts = ConflictSummary.model_validate(_d(system.get("conflict_summary")))
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

    deep_dive_tabs = _build_deep_dive_tabs(
        profile=routing_profile,
        cockpit_view=cockpit_view,
        medium_context=medium_context_summary,
        partner_matching=partner_matching,
        communication_context=communication_context,
        technical_derivations=technical_derivations,
    )
    decision_understanding_state = {
        "case_type": case_type.value,
        "profile": routing_profile,
        "parameters": parameters,
        "readiness": cockpit_view.readiness.model_dump(),
        "risks": [item.model_dump() for item in cockpit_view.risk_evaluations],
        "communication_context": communication_context.model_dump(),
        "medium_context": medium_context_summary.model_dump(),
        "partner_matching": partner_matching.model_dump(),
        "governance_status": governance_status.model_dump(),
        "rfq_status": rfq_status.model_dump(),
        "evidence_summary": evidence_summary.model_dump(),
        "seal_application_profile": seal_application_profile.model_dump(),
        "conflicts": conflicts.model_dump(),
    }
    nbq_projection = derive_needs_current_state_and_questions(
        decision_understanding_state
    )
    decision_understanding = build_decision_understanding_projection(
        decision_understanding_state
    ).model_copy(
        update={
            "needs_analysis": nbq_projection.needs_analysis,
            "current_state_analysis": nbq_projection.current_state_analysis,
            "next_best_questions": nbq_projection.next_best_questions,
            "completeness_score": nbq_projection.completeness_score,
        }
    )
    completeness_status = _build_completeness_status(
        payload=completeness_payload,
        score=nbq_projection.completeness_score.score,
        missing_fields=nbq_projection.current_state_analysis.missing_fields,
    )
    cockpit_view = cockpit_view.model_copy(
        update={
            "readiness": cockpit_view.readiness.model_copy(
                update={"coverage_score": completeness_status.coverage_score}
            )
        }
    )

    return CaseWorkspaceProjection(
        case_type=case_type,
        request_type=request_type,
        engineering_path=engineering_path,
        seal_application_profile=seal_application_profile,
        cockpit_view=cockpit_view,
        deep_dive_tabs=deep_dive_tabs,
        decision_understanding=decision_understanding,
        needs_analysis=nbq_projection.needs_analysis,
        current_state_analysis=nbq_projection.current_state_analysis,
        next_best_questions=nbq_projection.next_best_questions,
        completeness_score=nbq_projection.completeness_score,
        case_summary=case_summary,
        completeness=completeness_status,
        governance_status=governance_status,
        claims_summary=claims_summary,
        evidence_summary=evidence_summary,
        conflicts=conflicts,
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
