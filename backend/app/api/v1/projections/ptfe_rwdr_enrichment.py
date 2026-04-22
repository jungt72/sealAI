# backend/app/api/v1/projections/ptfe_rwdr_enrichment.py
"""PTFE-RWDR deterministic workspace enrichment.

This module adapts backend-owned V3 services into the public workspace
projection. It must not perform state mutation; it only enriches a read model
from already-known case/profile values.
"""

from __future__ import annotations

from typing import Any, Dict

from app.api.v1.schemas.case_workspace import TechnicalDerivationItem
from app.services.advisory_engine import AdvisoryEngine
from app.services.application_pattern_service import ApplicationPatternLibrary
from app.services.calculation_engine import CascadingCalculationEngine
from app.services.medium_intelligence_service import MediumIntelligenceService


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _ls(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _first_present(profile: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = profile.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    return int(number) if number is not None else None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "ja", "y", "j"}


def _infer_ptfe_family(profile: Dict[str, Any]) -> str | None:
    explicit = _first_present(
        profile,
        "sealing_material_family",
        "material_family",
        "compound_family",
        "ptfe_compound_family",
    )
    if explicit:
        return str(explicit)
    text = " ".join(
        str(value)
        for key, value in profile.items()
        if key
        in {
            "material",
            "compound",
            "sealing_type",
            "medium",
            "application_context",
            "installation",
        }
        and value not in (None, "")
    ).casefold()
    if "ptfe" not in text:
        return None
    if "glas" in text or "glass" in text:
        return "ptfe_glass_filled"
    if "carbon" in text or "kohle" in text:
        return "ptfe_carbon_filled"
    if "bronze" in text:
        return "ptfe_bronze_filled"
    if "graphit" in text or "graphite" in text:
        return "ptfe_graphite_filled"
    if "mos2" in text or "moly" in text:
        return "ptfe_mos2_filled"
    if "peek" in text:
        return "ptfe_peek_filled"
    return "ptfe_virgin"


def _is_ptfe_rwdr_profile(
    profile: Dict[str, Any], engineering_path: Any | None
) -> bool:
    path = (
        str(engineering_path or profile.get("engineering_path") or "")
        .strip()
        .casefold()
    )
    if path == "rwdr":
        family = _infer_ptfe_family(profile)
        if family is None:
            text = " ".join(
                str(value) for value in profile.values() if value not in (None, "")
            ).casefold()
            return "ptfe" in text
        return family.startswith("ptfe")
    text = " ".join(
        str(value) for value in profile.values() if value not in (None, "")
    ).casefold()
    return "ptfe" in text and any(
        marker in text for marker in ("rwdr", "wellendich", "simmerring", "welle")
    )


def _build_ptfe_rwdr_case_for_services(profile: Dict[str, Any]) -> Dict[str, Any]:
    case: Dict[str, Any] = {"engineering_path": "rwdr"}
    family = _infer_ptfe_family(profile)
    if family:
        case["sealing_material_family"] = family
    shaft_diameter = _float_or_none(
        _first_present(profile, "shaft_diameter_mm", "shaft_diameter", "diameter")
    )
    speed_rpm = _float_or_none(_first_present(profile, "speed_rpm", "rpm", "speed"))
    pressure_bar = _float_or_none(
        _first_present(profile, "pressure_bar", "pressure_max_bar", "pressure")
    )
    temperature_c = _float_or_none(
        _first_present(profile, "temperature_c", "temperature_max_c", "temperature")
    )
    temperature_nom_c = _float_or_none(
        _first_present(profile, "temperature_nom_c", "temperature_c", "temperature")
    )
    radial_force = _float_or_none(
        _first_present(profile, "radial_force_n_per_mm", "lip_radial_force_n_per_mm")
    )
    contact_width = _float_or_none(
        _first_present(profile, "contact_width_mm", "lip_contact_width_mm")
    )
    extrusion_gap = _float_or_none(
        _first_present(profile, "extrusion_gap_mm", "clearance_gap_mm")
    )
    years = _float_or_none(_first_present(profile, "expected_service_duration_years"))
    life_hours = _float_or_none(_first_present(profile, "life_hours"))
    if years is None and life_hours is not None:
        years = round(life_hours / 8760.0, 4)
    if shaft_diameter is not None:
        case.setdefault("shaft", {})["diameter_mm"] = shaft_diameter
    if speed_rpm is not None:
        case.setdefault("operating", {}).setdefault("shaft_speed", {})["rpm_nom"] = (
            speed_rpm
        )
    if pressure_bar is not None:
        case.setdefault("operating", {}).setdefault("pressure", {})["max_bar"] = (
            pressure_bar
        )
    if temperature_c is not None:
        case.setdefault("operating", {}).setdefault("temperature", {})["max_c"] = (
            temperature_c
        )
    if temperature_nom_c is not None:
        case.setdefault("operating", {}).setdefault("temperature", {})["nom_c"] = (
            temperature_nom_c
        )
    if radial_force is not None:
        case.setdefault("rwdr", {}).setdefault("lip", {})["radial_force_n_per_mm"] = (
            radial_force
        )
    if contact_width is not None:
        case.setdefault("rwdr", {}).setdefault("lip", {})["contact_width_mm"] = (
            contact_width
        )
    if extrusion_gap is not None:
        case.setdefault("rwdr", {})["extrusion_gap_mm"] = extrusion_gap
    if years is not None:
        case["expected_service_duration_years"] = years
    friction = _float_or_none(_first_present(profile, "friction_coefficient"))
    if friction is not None:
        case.setdefault("compound", {})["friction_coefficient"] = friction
    return case


def _ptfe_required_missing(profile: Dict[str, Any]) -> list[str]:
    required = {
        "medium": ("medium",),
        "shaft_diameter_mm": ("shaft_diameter_mm", "shaft_diameter", "diameter"),
        "speed_rpm": ("speed_rpm", "rpm", "speed"),
        "temperature_c": ("temperature_c", "temperature_max_c", "temperature"),
        "pressure_bar": ("pressure_bar", "pressure_max_bar", "pressure"),
        "quantity_requested": ("quantity_requested", "quantity_pieces", "pieces"),
        "shaft_surface_finish_ra_um": (
            "shaft_surface_finish_ra_um",
            "surface_finish_ra_um",
            "shaft_ra_um",
        ),
        "shaft_hardness_hrc": ("shaft_hardness_hrc", "shaft_hardness", "hardness_hrc"),
        "machining_method": ("machining_method",),
    }
    missing: list[str] = []
    for canonical, aliases in required.items():
        if _first_present(profile, *aliases) is None:
            missing.append(canonical)
    return missing


def _ptfe_pattern_notes(profile: Dict[str, Any]) -> list[str]:
    text = " ".join(
        str(
            _first_present(
                profile, "application_context", "installation", "medium", "sealing_type"
            )
            or ""
        ).split()
    )
    if not text:
        return []
    candidates = ApplicationPatternLibrary().match(text, limit=3)
    if not candidates:
        return []
    return [
        f"Application pattern candidate: {candidate.pattern.canonical_name} (confidence {candidate.confidence:.2f}); user confirmation required."
        for candidate in candidates
    ]


def _ptfe_medium_context(
    profile: Dict[str, Any], existing: Dict[str, Any]
) -> Dict[str, Any]:
    if existing.get("status") not in (None, "", "unavailable"):
        return existing
    medium = _first_present(profile, "medium")
    if medium is None:
        return existing
    result = MediumIntelligenceService().get_medium_intelligence(
        str(medium),
        temperature_c=_float_or_none(
            _first_present(profile, "temperature_c", "temperature")
        ),
        application_context=str(
            _first_present(profile, "application_context", "installation") or ""
        )
        or None,
    )
    return {
        "medium_label": str(medium),
        "status": "recognized"
        if result.matched_registry_entry is not None
        else "unavailable",
        "scope": "ptfe_rwdr_preselection_context",
        "summary": result.medium_summary,
        "properties": [
            f"{key}: {prop.value}"
            for key, prop in result.llm_synthesized_properties.items()
        ],
        "challenges": list(result.risk_notes),
        "followup_points": ["Finale Werkstoffauswahl bleibt Herstellerpruefung."],
        "confidence": result.confidence_level,
        "source_type": result.provenance_tier.value,
        "not_for_release_decisions": True,
        "disclaimer": "Mediumdaten sind Vorqualifizierungs-Kontext, keine finale Werkstofffreigabe.",
    }


def _ptfe_advisory_notes(profile: Dict[str, Any], missing: list[str]) -> list[str]:
    quantity = _int_or_none(
        _first_present(profile, "quantity_requested", "quantity_pieces", "pieces")
    )
    context: Dict[str, Any] = {
        "missing_critical_fields": missing[:4],
        "quantity_requested": quantity,
        "quantity_capability_available": False if quantity is not None else True,
        "food_contact_required": _boolish(
            _first_present(profile, "food_contact_required")
        ),
        "atex_required": _boolish(_first_present(profile, "atex_required")),
        "dry_run_possible": _boolish(
            _first_present(profile, "dry_run_possible", "dry_run_risk")
        ),
        "dry_run_allowed": not _boolish(_first_present(profile, "dry_run_not_allowed")),
        "shaft_diameter_mm": _first_present(profile, "shaft_diameter_mm"),
        "housing_bore_diameter_mm": _first_present(profile, "housing_bore_diameter_mm"),
    }
    ra = _float_or_none(
        _first_present(
            profile, "shaft_surface_finish_ra_um", "surface_finish_ra_um", "shaft_ra_um"
        )
    )
    hardness = _float_or_none(
        _first_present(profile, "shaft_hardness_hrc", "shaft_hardness", "hardness_hrc")
    )
    machining = str(_first_present(profile, "machining_method") or "").casefold()
    warnings: list[str] = []
    if ra is not None and (ra < 0.1 or ra > 0.8):
        warnings.append("PTFE-RWDR shaft Ra outside 0.1-0.8 um guardrail.")
    if hardness is not None and hardness < 45:
        warnings.append("PTFE-RWDR shaft hardness below 45 HRC guardrail.")
    if "hard" in machining and "turn" in machining:
        warnings.append("Hard-turned shaft is a PTFE-RWDR lead-pumping risk.")
    if warnings:
        context["installation_warnings"] = warnings
        context["geometry_consistency_issue"] = True
    advisories = AdvisoryEngine().evaluate_advisories(context)
    return [
        f"Advisory {advisory.category.value}/{advisory.severity.value}: {advisory.title} - {advisory.recommended_action}"
        for advisory in advisories
    ]


def _build_ptfe_rwdr_derivation(
    profile: Dict[str, Any],
) -> TechnicalDerivationItem | None:
    case = _build_ptfe_rwdr_case_for_services(profile)
    state, records = CascadingCalculationEngine().execute_cascade(case)
    derived = _d(state.get("derived"))
    diameter = _float_or_none(
        _first_present(profile, "shaft_diameter_mm", "shaft_diameter", "diameter")
    )
    rpm = _float_or_none(_first_present(profile, "speed_rpm", "rpm", "speed"))
    notes = [f"{record.calc_id}@{record.version}" for record in records]
    missing = _ptfe_required_missing(profile)
    notes.extend(_ptfe_pattern_notes(profile))
    notes.extend(_ptfe_advisory_notes(profile, missing))
    if not derived and not notes:
        return None
    status = "ok" if records else "insufficient_data"
    return TechnicalDerivationItem(
        calc_type="rwdr",
        status=status,
        v_surface_m_s=derived.get("surface_speed_ms"),
        pv_value_mpa_m_s=derived.get("pv_loading"),
        dn_value=(diameter * rpm if diameter is not None and rpm is not None else None),
        notes=notes,
    )


def _enrich_ptfe_rwdr_workspace_inputs(
    *,
    routing_profile: Dict[str, Any],
    engineering_path: Any | None,
    system: Dict[str, Any],
    matching_state: Dict[str, Any],
    medium_context: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if not _is_ptfe_rwdr_profile(routing_profile, engineering_path):
        return system, matching_state, medium_context
    system = dict(system)
    matching_state = dict(matching_state)
    medium_context = _ptfe_medium_context(routing_profile, dict(medium_context))
    existing_derivations = [
        item
        for item in _ls(system.get("technical_derivations"))
        if isinstance(item, dict)
    ]
    if not existing_derivations:
        derivation = _build_ptfe_rwdr_derivation(routing_profile)
        if derivation is not None:
            system["technical_derivations"] = [derivation.model_dump()]
    if not matching_state.get("match_candidates"):
        quantity = _int_or_none(
            _first_present(
                routing_profile, "quantity_requested", "quantity_pieces", "pieces"
            )
        )
        missing = _ptfe_required_missing(routing_profile)
        blockers = []
        if missing:
            blockers.append("ptfe_rwdr_required_inputs_missing")
        blockers.append("manufacturer_capability_data_required")
        matching_state.update(
            {
                "status": "ptfe_rwdr_problem_signature_ready"
                if not missing
                else "ptfe_rwdr_intake_incomplete",
                "matchability_status": "requires_manufacturer_capability_data",
                "shortlist_ready": False,
                "inquiry_ready": False,
                "release_blockers": blockers,
                "blocking_reasons": blockers,
                "match_candidates": [],
                "data_source": "ptfe_rwdr_deterministic_projection",
            }
        )
        if quantity is not None and quantity <= 10:
            matching_state["blocking_reasons"] = list(
                dict.fromkeys(
                    blockers + ["small_quantity_requires_accepts_single_pieces_claim"]
                )
            )
    return system, matching_state, medium_context
