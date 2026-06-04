"""Backend-owned deterministic check registry.

This module registers calculation/check metadata separately from risk scoring
and norm activation.  It currently exposes only deterministic RWDR results that
already exist in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.agent.domain.compatibility_precheck import (
    build_material_medium_compatibility_precheck,
    compatibility_check_status,
)
from app.agent.domain.risk_claims import risk_claim_payload
from app.domain.seal_packs import pack_for_engineering_path


@dataclass(frozen=True)
class EngineeringCheckDefinition:
    calc_id: str
    label: str
    formula_version: str
    required_inputs: tuple[str, ...]
    valid_paths: tuple[str, ...]
    output_key: str
    unit: str | None = None
    fallback_behavior: str = "insufficient_data_when_required_inputs_missing"
    guardrails: tuple[str, ...] = ()
    source_calc_type: str = "rwdr"
    severity: str = "screening"
    requirement_tier: str = "required_for_rwdr_precheck"


REGISTERED_CHECKS: tuple[EngineeringCheckDefinition, ...] = (
    EngineeringCheckDefinition(
        calc_id="rwdr_circumferential_speed",
        label="Umlaufgeschwindigkeit",
        formula_version="rwdr_calc_v1",
        required_inputs=("shaft_diameter_mm", "speed_rpm"),
        valid_paths=("rwdr",),
        output_key="v_surface_m_s",
        unit="m/s",
        guardrails=("diameter and speed must be present and non-negative",),
    ),
    EngineeringCheckDefinition(
        calc_id="rwdr_pv_precheck",
        label="PV-Wert",
        formula_version="rwdr_calc_v1",
        required_inputs=("shaft_diameter_mm", "speed_rpm", "pressure_at_seal_bar"),
        valid_paths=("rwdr",),
        output_key="pv_value_mpa_m_s",
        unit="MPa*m/s",
        guardrails=(
            "uses pressure_at_seal_bar or pressure_delta_bar; system pressure is not accepted as seal pressure",
            "not a final effective contact-pressure PV model",
        ),
    ),
    EngineeringCheckDefinition(
        calc_id="rwdr_dn_value",
        label="DN-Wert",
        formula_version="rwdr_calc_v1",
        required_inputs=("shaft_diameter_mm", "speed_rpm"),
        valid_paths=("rwdr",),
        output_key="dn_value",
        unit="mm*min^-1",
        guardrails=("diameter and speed must be present and non-negative",),
    ),
    EngineeringCheckDefinition(
        calc_id="rwdr_temperature_headroom",
        label="Temperatur-Reserve",
        formula_version="rwdr_calc_v1",
        required_inputs=("temperature_c", "sealing_material_family"),
        valid_paths=("rwdr",),
        output_key="temperature_headroom_c",
        unit="°C",
        guardrails=(
            "uses deterministic material-family temperature precheck",
            "material family must be manufacturer-checked before release",
        ),
    ),
    EngineeringCheckDefinition(
        calc_id="rwdr_pressure_window",
        label="Druck-Einordnung",
        formula_version="rwdr_calc_v1",
        required_inputs=("pressure_at_seal_bar", "sealing_type"),
        valid_paths=("rwdr",),
        output_key="pressure_window",
        guardrails=(
            "precheck only; uses pressure_at_seal_bar or pressure_delta_bar, never pressure_system_bar",
            "does not constitute pressure rating or release",
        ),
    ),
)

_INPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "shaft_diameter_mm": ("shaft_diameter_mm", "shaft_diameter", "diameter"),
    "speed_rpm": ("speed_rpm", "rpm", "speed"),
    "pressure_bar": ("pressure_bar", "pressure_max_bar", "pressure"),
    "pressure_at_seal_bar": ("pressure_at_seal_bar", "pressure_delta_bar"),
    "temperature_c": ("temperature_c", "temperature_max_c", "temperature"),
    "counterface_surface_condition": (
        "counterface_surface_condition",
        "counterface_surface",
        "surface_finish",
        "shaft_surface",
    ),
    "shaft_roughness_ra_um": (
        "shaft_roughness_ra_um",
        "surface_roughness_ra_um",
        "surface_roughness",
        "roughness",
    ),
    "shaft_hardness_hrc": (
        "shaft_hardness_hrc",
        "surface_hardness_hrc",
        "shaft_hardness",
        "hardness",
    ),
    "runout_mm": ("runout_mm", "shaft_runout", "runout", "dynamic_runout_mm"),
    "eccentricity_mm": ("eccentricity_mm", "eccentricity"),
    "lubrication_condition": (
        "lubrication_condition",
        "lubrication",
        "lubrication_context",
        "duty_profile",
    ),
    "contamination_condition": ("contamination_condition", "contamination"),
    "sealing_material_family": (
        "sealing_material_family",
        "material_family",
        "compound_family",
        "ptfe_compound_family",
        "material",
    ),
}

_UNKNOWN_TEXT_VALUES = {
    "unknown",
    "unbekannt",
    "unklar",
    "nicht bekannt",
    "not known",
    "n/a",
}
_ROUGHNESS_RA_ORIENTATION_MAX_UM = 0.8
_HARDNESS_ORIENTATION_MIN_HRC = 55.0
_RUNOUT_ORIENTATION_MAX_MM = 0.2
_COMPATIBILITY_VALID_PATHS = (
    "rwdr",
    "static",
    "hyd_pneu",
    "ms_pump",
    "labyrinth",
    "unclear_rotary",
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _has_profile_value(profile: dict[str, Any], key: str) -> bool:
    return _is_known_value(_profile_value(profile, key))


def _profile_value(profile: dict[str, Any], key: str) -> Any:
    for alias in _INPUT_ALIASES.get(key, (key,)):
        value = profile.get(alias)
        if value not in (None, "", [], {}):
            return value
    return None


def _profile_present_field(profile: dict[str, Any], key: str) -> str | None:
    for alias in _INPUT_ALIASES.get(key, (key,)):
        value = profile.get(alias)
        if _is_known_value(value):
            return alias
    return None


def _is_known_value(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str) and value.strip().casefold() in _UNKNOWN_TEXT_VALUES:
        return False
    return True


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text.split()[0])
    except (ValueError, IndexError):
        return None


def _evidence_fields(profile: dict[str, Any], required_inputs: tuple[str, ...]) -> list[str]:
    fields: list[str] = []
    for key in required_inputs:
        if _profile_value(profile, key) not in (None, "", [], {}):
            fields.append(key)
    return fields


def _check_result(
    *,
    calc_id: str,
    label: str,
    required_fields: tuple[str, ...],
    subject_field: str,
    status: str,
    claim_type: str,
    severity: str,
    evidence_fields: list[str] | None = None,
    missing_fields: list[str] | None = None,
    value: Any = None,
    blocking_reason: str | None = None,
    human_readable_reason: str,
    allowed_user_wording: str,
    forbidden_user_wording: list[str] | None = None,
    requirement_tier: str = "recommended_for_professional_review",
    unit: str | None = None,
) -> dict[str, Any]:
    claim_payload = risk_claim_payload(
        claim_id=f"check_registry.{calc_id}",
        claim_type=claim_type,
        subject_field=subject_field,
        severity=severity,
        evidence_fields=evidence_fields or [],
        missing_fields=missing_fields or [],
        blocked_reason=blocking_reason,
        allowed_user_wording=allowed_user_wording,
        forbidden_user_wording=forbidden_user_wording
        or [
            "RWDR ist geeignet.",
            "RWDR ist ungeeignet.",
            "Berechnung ist eine Freigabe.",
        ],
        source="check_registry",
    )
    return {
        "calc_id": calc_id,
        "check_id": calc_id,
        **claim_payload,
        "label": label,
        "formula_version": "rwdr_professional_precheck_v1",
        "required_inputs": list(required_fields),
        "required_fields": list(required_fields),
        "missing_inputs": list(missing_fields or []),
        "missing_fields": list(missing_fields or []),
        "valid_paths": ["rwdr"],
        "output_key": subject_field,
        "unit": unit,
        "status": status,
        "value": value if status in {"passed", "failed"} else None,
        "fallback_behavior": "professional_precheck_only_no_release_claim",
        "guardrails": [
            "screening/precheck only",
            "no manufacturer approval, no lifetime claim, no suitability release",
        ],
        "blocking_reason": blocking_reason,
        "derived_from": ["rwdr_professional_precheck_v1", subject_field],
        "human_readable_reason": human_readable_reason,
        "raw_status": status,
        "notes": [],
        "requirement_tier": requirement_tier,
    }


def _text_value(profile: dict[str, Any], field_name: str) -> str:
    value = _profile_value(profile, field_name)
    return str(value or "").strip().casefold()


def _build_rwdr_professional_check_results(
    profile: dict[str, Any],
    engineering_path: str | None,
) -> list[dict[str, Any]]:
    if pack_for_engineering_path(engineering_path) is None:
        return []

    results: list[dict[str, Any]] = []

    has_seal_pressure = _has_profile_value(profile, "pressure_at_seal_bar")
    has_system_pressure = _has_profile_value(profile, "pressure_system_bar")
    has_ambiguous_pressure = _has_profile_value(profile, "ambiguous_pressure_bar")
    if has_seal_pressure:
        pressure_field = _profile_present_field(profile, "pressure_at_seal_bar") or "pressure_at_seal_bar"
        results.append(
            _check_result(
                calc_id="rwdr_pressure_role_check",
                label="RWDR-Druckrolle",
                required_fields=("pressure_at_seal_bar",),
                subject_field="pressure_at_seal_bar",
                status="passed",
                claim_type="context_advisory",
                severity="screening",
                evidence_fields=[pressure_field],
                human_readable_reason="Dichtstellendruck oder Differenzdruck ist fuer den RWDR-Vorcheck vorhanden.",
                allowed_user_wording="Dichtstellendruck oder Differenzdruck ist als Eingabe fuer den RWDR-Vorcheck vorhanden.",
                requirement_tier="required_for_rwdr_precheck",
                unit="bar",
            )
        )
    elif has_ambiguous_pressure:
        results.append(
            _check_result(
                calc_id="rwdr_pressure_role_check",
                label="RWDR-Druckrolle",
                required_fields=("pressure_at_seal_bar",),
                subject_field="ambiguous_pressure_bar",
                status="blocked",
                claim_type="ambiguity_risk",
                severity="blocking",
                evidence_fields=["ambiguous_pressure_bar"],
                missing_fields=["pressure_at_seal_bar"],
                blocking_reason="pressure_role_ambiguous",
                human_readable_reason="Ein Druckwert ist vorhanden, aber seine Rolle ist unklar.",
                allowed_user_wording="Ein Druckwert ist vorhanden, die Rolle ist aber offen: Systemdruck, Dichtstellendruck oder Differenzdruck.",
                forbidden_user_wording=["Der Dichtungsdruck ist kritisch."],
                requirement_tier="required_for_rwdr_precheck",
                unit="bar",
            )
        )
    else:
        evidence = ["pressure_system_bar"] if has_system_pressure else []
        results.append(
            _check_result(
                calc_id="rwdr_pressure_role_check",
                label="RWDR-Druckrolle",
                required_fields=("pressure_at_seal_bar",),
                subject_field="pressure_at_seal_bar",
                status="blocked" if has_system_pressure else "pending",
                claim_type="missing_input_risk",
                severity="blocking" if has_system_pressure else "medium",
                evidence_fields=evidence,
                missing_fields=["pressure_at_seal_bar"],
                blocking_reason=(
                    "seal_pressure_missing_system_pressure_only"
                    if has_system_pressure
                    else "seal_pressure_missing"
                ),
                human_readable_reason="Der fuer RWDR auslegungsrelevante Dichtstellendruck oder Differenzdruck fehlt.",
                allowed_user_wording="Der Systemdruck ist bekannt. Offen ist noch, welcher Druck direkt an der Dichtstelle anliegt."
                if has_system_pressure
                else "Der Druck direkt an der Dichtstelle oder der Differenzdruck ist fuer den RWDR-Vorcheck noch offen.",
                forbidden_user_wording=["Der Dichtungsdruck ist kritisch."],
                requirement_tier="required_for_rwdr_precheck",
                unit="bar",
            )
        )

    surface_text = _text_value(profile, "counterface_surface_condition")
    if not surface_text or surface_text in _UNKNOWN_TEXT_VALUES:
        results.append(
            _check_result(
                calc_id="rwdr_surface_condition_check",
                label="Gegenlaufflaechenzustand",
                required_fields=("counterface_surface_condition",),
                subject_field="counterface_surface_condition",
                status="pending",
                claim_type="missing_input_risk",
                severity="medium",
                missing_fields=["counterface_surface_condition"],
                blocking_reason="counterface_surface_condition_missing",
                human_readable_reason="Der Zustand der Gegenlaufflaeche ist noch nicht bekannt.",
                allowed_user_wording="Die Gegenlaufflaeche der Welle ist noch offen; bei RWDR laeuft die Dichtlippe direkt darauf.",
            )
        )
    else:
        damaged = any(token in surface_text for token in ("damaged", "besch", "rief", "worn", "eingelaufen", "verschliss", "corrod", "korro"))
        results.append(
            _check_result(
                calc_id="rwdr_surface_condition_check",
                label="Gegenlaufflaechenzustand",
                required_fields=("counterface_surface_condition",),
                subject_field="counterface_surface_condition",
                status="failed" if damaged else "passed",
                claim_type="context_advisory",
                severity="high" if damaged else "screening",
                evidence_fields=["counterface_surface_condition"],
                value=_profile_value(profile, "counterface_surface_condition"),
                human_readable_reason="Der angegebene Gegenlaufflaechenzustand ist ein RWDR-Pruefpunkt.",
                allowed_user_wording="Der Gegenlaufflaechenzustand ist explizit angegeben und bleibt ein nicht finaler RWDR-Pruefpunkt.",
                forbidden_user_wording=["Die Gegenlaufflaeche ist ungeeignet."],
            )
        )

    roughness_value = _as_number(_profile_value(profile, "shaft_roughness_ra_um"))
    if roughness_value is None:
        has_roughness_text = _profile_value(profile, "shaft_roughness_ra_um") not in (None, "", [], {})
        results.append(
            _check_result(
                calc_id="rwdr_roughness_check",
                label="Rauheit Ra Gegenlaufflaeche",
                required_fields=("shaft_roughness_ra_um",),
                subject_field="shaft_roughness_ra_um",
                status="blocked" if has_roughness_text else "pending",
                claim_type="ambiguity_risk" if has_roughness_text else "missing_input_risk",
                severity="medium",
                evidence_fields=["shaft_roughness_ra_um"] if has_roughness_text else [],
                missing_fields=["shaft_roughness_ra_um"],
                blocking_reason="shaft_roughness_missing_or_ambiguous",
                human_readable_reason="Rauheit Ra der Gegenlaufflaeche fehlt oder ist nicht numerisch auswertbar.",
                allowed_user_wording="Die Rauheit Ra der Gegenlaufflaeche ist fuer den RWDR-Vorcheck noch offen.",
            )
        )
    else:
        high = roughness_value > _ROUGHNESS_RA_ORIENTATION_MAX_UM
        results.append(
            _check_result(
                calc_id="rwdr_roughness_check",
                label="Rauheit Ra Gegenlaufflaeche",
                required_fields=("shaft_roughness_ra_um",),
                subject_field="shaft_roughness_ra_um",
                status="failed" if high else "passed",
                claim_type="measured_risk" if high else "context_advisory",
                severity="high" if high else "screening",
                evidence_fields=["shaft_roughness_ra_um"],
                value=roughness_value,
                human_readable_reason="Rauheit Ra ist als numerischer RWDR-Orientierungswert vorhanden.",
                allowed_user_wording="Die angegebene Rauheit wird nur als RWDR-Vorcheck bewertet; daraus entsteht keine finale Entscheidung.",
                forbidden_user_wording=["Die Laufflaeche ist freigegeben."],
                unit="µm",
            )
        )

    hardness_value = _as_number(_profile_value(profile, "shaft_hardness_hrc"))
    if hardness_value is None:
        has_hardness_text = _profile_value(profile, "shaft_hardness_hrc") not in (None, "", [], {})
        results.append(
            _check_result(
                calc_id="rwdr_hardness_check",
                label="Haerte Gegenlaufflaeche",
                required_fields=("shaft_hardness_hrc",),
                subject_field="shaft_hardness_hrc",
                status="blocked" if has_hardness_text else "pending",
                claim_type="ambiguity_risk" if has_hardness_text else "missing_input_risk",
                severity="medium",
                evidence_fields=["shaft_hardness_hrc"] if has_hardness_text else [],
                missing_fields=["shaft_hardness_hrc"],
                blocking_reason="shaft_hardness_missing_or_ambiguous",
                human_readable_reason="Haerte der Gegenlaufflaeche fehlt oder ist nicht numerisch auswertbar.",
                allowed_user_wording="Die Haerte der Gegenlaufflaeche ist fuer den RWDR-Vorcheck noch offen.",
            )
        )
    else:
        low = hardness_value < _HARDNESS_ORIENTATION_MIN_HRC
        results.append(
            _check_result(
                calc_id="rwdr_hardness_check",
                label="Haerte Gegenlaufflaeche",
                required_fields=("shaft_hardness_hrc",),
                subject_field="shaft_hardness_hrc",
                status="failed" if low else "passed",
                claim_type="measured_risk" if low else "context_advisory",
                severity="high" if low else "screening",
                evidence_fields=["shaft_hardness_hrc"],
                value=hardness_value,
                human_readable_reason="Haerte ist als numerischer RWDR-Orientierungswert vorhanden.",
                allowed_user_wording="Die angegebene Haerte wird nur als RWDR-Vorcheck bewertet; daraus entsteht keine finale Entscheidung.",
                forbidden_user_wording=["Die Gegenlaufflaeche ist freigegeben."],
                unit="HRC",
            )
        )

    runout_field = "runout_mm" if _has_profile_value(profile, "runout_mm") else "eccentricity_mm"
    runout_value = _as_number(_profile_value(profile, runout_field))
    if runout_value is None:
        results.append(
            _check_result(
                calc_id="rwdr_runout_eccentricity_check",
                label="Rundlauf / Exzentrizitaet",
                required_fields=("runout_mm", "eccentricity_mm"),
                subject_field="runout_mm",
                status="pending",
                claim_type="missing_input_risk",
                severity="medium",
                missing_fields=["runout_mm", "eccentricity_mm"],
                blocking_reason="runout_eccentricity_missing",
                human_readable_reason="Rundlauf oder Exzentrizitaet ist fuer den RWDR-Vorcheck noch offen.",
                allowed_user_wording="Rundlauf/Wellenschlag ist noch nicht angegeben und sollte fuer RWDR geprueft werden.",
                forbidden_user_wording=["Der Wellenschlag ist hoch."],
                unit="mm",
            )
        )
    else:
        high = runout_value > _RUNOUT_ORIENTATION_MAX_MM
        results.append(
            _check_result(
                calc_id="rwdr_runout_eccentricity_check",
                label="Rundlauf / Exzentrizitaet",
                required_fields=(runout_field,),
                subject_field=runout_field,
                status="failed" if high else "passed",
                claim_type="measured_risk" if high else "context_advisory",
                severity="high" if high else "screening",
                evidence_fields=[runout_field],
                value=runout_value,
                human_readable_reason="Rundlauf oder Exzentrizitaet ist als numerischer RWDR-Orientierungswert vorhanden.",
                allowed_user_wording="Der gemessene Rundlauf/Wellenschlag liegt als Wert vor und wird nur als RWDR-Vorcheck bewertet.",
                forbidden_user_wording=["RWDR versagt wegen Wellenschlag."],
                unit="mm",
            )
        )

    lubrication_text = _text_value(profile, "lubrication_condition")
    if not lubrication_text or lubrication_text in _UNKNOWN_TEXT_VALUES:
        results.append(
            _check_result(
                calc_id="rwdr_lubrication_check",
                label="Schmierung an der Dichtlippe",
                required_fields=("lubrication_condition",),
                subject_field="lubrication_condition",
                status="pending",
                claim_type="missing_input_risk",
                severity="medium",
                missing_fields=["lubrication_condition"],
                blocking_reason="lubrication_condition_missing",
                human_readable_reason="Schmierzustand an der Dichtlippe ist noch nicht bekannt.",
                allowed_user_wording="Die Schmierung an der Dichtlippe ist fuer den RWDR-Vorcheck noch offen.",
            )
        )
    else:
        risky_lubrication = any(token in lubrication_text for token in ("dry", "trocken", "mangel", "insufficient", "poor"))
        results.append(
            _check_result(
                calc_id="rwdr_lubrication_check",
                label="Schmierung an der Dichtlippe",
                required_fields=("lubrication_condition",),
                subject_field="lubrication_condition",
                status="failed" if risky_lubrication else "passed",
                claim_type="context_advisory",
                severity="high" if risky_lubrication else "screening",
                evidence_fields=["lubrication_condition"],
                value=_profile_value(profile, "lubrication_condition"),
                human_readable_reason="Schmierzustand an der Dichtlippe ist explizit angegeben.",
                allowed_user_wording="Der angegebene Schmierzustand ist ein RWDR-Pruefpunkt; daraus entsteht keine finale Versagens- oder Eignungsaussage.",
                forbidden_user_wording=["Die Dichtung versagt wegen Schmierung."],
            )
        )

    contamination_text = _text_value(profile, "contamination_condition")
    if not contamination_text or contamination_text in _UNKNOWN_TEXT_VALUES:
        results.append(
            _check_result(
                calc_id="rwdr_contamination_check",
                label="Verschmutzung / Abrasion",
                required_fields=("contamination_condition",),
                subject_field="contamination_condition",
                status="pending",
                claim_type="missing_input_risk",
                severity="medium",
                missing_fields=["contamination_condition"],
                blocking_reason="contamination_condition_missing",
                human_readable_reason="Verschmutzungs- oder Abrasionskontext ist noch nicht bekannt.",
                allowed_user_wording="Verschmutzung, Staub oder abrasive Partikel sind fuer den RWDR-Vorcheck noch offen.",
            )
        )
    else:
        abrasive = any(token in contamination_text for token in ("abras", "staub", "dust", "sand", "partikel", "solid", "schmutz"))
        results.append(
            _check_result(
                calc_id="rwdr_contamination_check",
                label="Verschmutzung / Abrasion",
                required_fields=("contamination_condition",),
                subject_field="contamination_condition",
                status="failed" if abrasive else "passed",
                claim_type="context_advisory",
                severity="high" if abrasive else "screening",
                evidence_fields=["contamination_condition"],
                value=_profile_value(profile, "contamination_condition"),
                human_readable_reason="Verschmutzungs- oder Abrasionskontext ist explizit angegeben.",
                allowed_user_wording="Der angegebene Verschmutzungskontext ist ein RWDR-Pruefpunkt; daraus entsteht keine finale Eignungsaussage.",
                forbidden_user_wording=["RWDR ist wegen Verschmutzung ungeeignet."],
            )
        )

    return results


def _compatibility_claim_type(status: str) -> str:
    if status == "missing_input":
        return "missing_input_risk"
    if status == "ambiguous_input":
        return "ambiguity_risk"
    if status in {"blocked_claim", "insufficient_evidence"}:
        return "blocked_claim"
    return "context_advisory"


def _build_material_medium_compatibility_check_result(
    profile: dict[str, Any],
    engineering_path: str | None,
) -> dict[str, Any] | None:
    if engineering_path is None and not any(
        _profile_value(profile, key) not in (None, "", [], {})
        for key in (
            "medium",
            "medium_name",
            "material",
            "material_family",
            "sealing_material_family",
            "compliance",
            "industry",
            "certification_requirement",
        )
    ):
        return None

    precheck = build_material_medium_compatibility_precheck(profile)
    compatibility_status = precheck.status
    status = compatibility_check_status(precheck)
    required_fields = ["medium", "material", "temperature_c"]
    for field_name in precheck.missing_fields:
        if field_name and field_name not in required_fields:
            required_fields.append(field_name)
    claim_payload = risk_claim_payload(
        claim_id="check_registry.material_medium_compatibility_precheck",
        claim_type=_compatibility_claim_type(compatibility_status),
        subject_field="material_medium_compatibility",
        severity=precheck.severity,
        evidence_fields=precheck.evidence_fields,
        missing_fields=precheck.missing_fields,
        blocked_reason=(
            f"compatibility_{compatibility_status}"
            if status == "blocked"
            else None
        ),
        allowed_user_wording=precheck.allowed_user_wording,
        forbidden_user_wording=precheck.forbidden_user_wording,
        source="check_registry",
    )
    return {
        "calc_id": precheck.check_id,
        "check_id": precheck.check_id,
        **claim_payload,
        "label": "Material/Medium-Vertraeglichkeits-Precheck",
        "formula_version": "material_medium_compatibility_precheck_v1",
        "required_inputs": required_fields,
        "required_fields": required_fields,
        "missing_inputs": list(precheck.missing_fields),
        "missing_fields": list(precheck.missing_fields),
        "valid_paths": list(_COMPATIBILITY_VALID_PATHS),
        "output_key": "material_medium_compatibility",
        "unit": None,
        "status": status,
        "value": compatibility_status if status == "passed" else None,
        "fallback_behavior": "compatibility_precheck_only_no_approval_claim",
        "guardrails": [
            "deterministic precheck/orientation only",
            "no final material approval, manufacturer release, or compliance approval",
            "missing or ambiguous medium/material/temperature blocks compatibility claims",
        ],
        "blocking_reason": claim_payload["blocked_reason"],
        "derived_from": [
            "material_medium_compatibility_precheck_v1",
            "medium",
            "material",
            "temperature_c",
        ],
        "human_readable_reason": precheck.human_readable_reason,
        "raw_status": compatibility_status,
        "notes": [],
        "requirement_tier": "recommended_for_professional_review",
        "compatibility_status": compatibility_status,
        "compatibility_claim_type": precheck.compatibility_claim_type,
        "evidence_status": precheck.evidence_status,
        "evidence_refs": [ref.to_dict() for ref in precheck.evidence_refs],
        "evidence_summary": precheck.evidence_summary,
        "evidence_limitations": list(precheck.evidence_limitations),
        "medium_field": precheck.medium_field,
        "material_field": precheck.material_field,
        "temperature_field": precheck.temperature_field,
        "concentration_field": precheck.concentration_field,
        "ph_field": precheck.ph_field,
        "ambiguous_fields": list(precheck.ambiguous_fields),
        "final_approval_claim_allowed": False,
    }


def _canonical_status(
    *,
    raw_status: str,
    value: Any,
    missing_inputs: list[str],
) -> str:
    if missing_inputs:
        return "blocked"
    if value is None:
        return "pending"
    if raw_status.casefold() in {"failed", "failure", "error", "warning"}:
        return "failed"
    if raw_status.casefold() in {"not_applicable", "not-applicable", "skipped"}:
        return "not_applicable"
    return "passed"


def _blocking_reason(missing_inputs: list[str]) -> str | None:
    if not missing_inputs:
        return None
    return "missing_required_fields:" + ",".join(missing_inputs)


def _human_reason(
    definition: EngineeringCheckDefinition,
    *,
    status: str,
    missing_inputs: list[str],
) -> str:
    if status == "blocked":
        return (
            f"{definition.label} ist blockiert, weil fachlich benoetigte Eingaben fehlen: "
            + ", ".join(missing_inputs)
        )
    if status == "pending":
        return f"{definition.label} wartet auf eine berechnete Ableitung aus dem Backend."
    if status == "failed":
        return f"{definition.label} hat einen auffaelligen Vorcheck-Status."
    if status == "not_applicable":
        return f"{definition.label} ist fuer diesen Engineering-Pfad nicht anwendbar."
    return f"{definition.label} ist aus den erforderlichen Backend-Eingaben ableitbar."


def _derivations_by_type(
    technical_derivations: Iterable[Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in technical_derivations:
        payload = _as_dict(item)
        calc_type = str(payload.get("calc_type") or "").strip()
        if calc_type and calc_type not in result:
            result[calc_type] = payload
    return result


def build_registered_check_results(
    *,
    profile: dict[str, Any],
    engineering_path: str | None,
    technical_derivations: Iterable[Any],
) -> list[dict[str, Any]]:
    """Project active registered checks with current result or missing-input fallback."""
    derivations = _derivations_by_type(technical_derivations)
    results: list[dict[str, Any]] = []

    for definition in REGISTERED_CHECKS:
        derivation = derivations.get(definition.source_calc_type)
        if engineering_path is not None:
            if engineering_path not in definition.valid_paths:
                continue
        elif derivation is None:
            continue

        missing_inputs = [
            input_key
            for input_key in definition.required_inputs
            if not _has_profile_value(profile, input_key)
        ]
        value = (
            derivation.get(definition.output_key) if derivation is not None else None
        )
        raw_status = str((derivation or {}).get("status") or "pending")
        status = _canonical_status(
            raw_status=raw_status,
            value=value,
            missing_inputs=missing_inputs,
        )
        evidence_fields = _evidence_fields(profile, definition.required_inputs)
        claim_type = (
            "missing_input_risk"
            if missing_inputs
            else ("measured_risk" if status == "failed" else "context_advisory")
        )
        claim_payload = risk_claim_payload(
            claim_id=f"check_registry.{definition.calc_id}",
            claim_type=claim_type,
            subject_field=definition.output_key,
            severity="blocking" if status == "blocked" else definition.severity,
            evidence_fields=evidence_fields,
            missing_fields=missing_inputs,
            blocked_reason=_blocking_reason(missing_inputs),
            allowed_user_wording=_human_reason(
                definition,
                status=status,
                missing_inputs=missing_inputs,
            ),
            forbidden_user_wording=[
                "Check ist bestanden, obwohl Eingaben fehlen.",
                "Berechnung ist eine Freigabe.",
            ],
            source="check_registry",
        )

        results.append(
            {
                "calc_id": definition.calc_id,
                "check_id": definition.calc_id,
                **claim_payload,
                "label": definition.label,
                "formula_version": definition.formula_version,
                "required_inputs": list(definition.required_inputs),
                "required_fields": list(definition.required_inputs),
                "missing_inputs": missing_inputs,
                "missing_fields": missing_inputs,
                "valid_paths": list(definition.valid_paths),
                "output_key": definition.output_key,
                "unit": definition.unit,
                "status": status,
                "value": value if value is not None and not missing_inputs else None,
                "fallback_behavior": definition.fallback_behavior,
                "guardrails": list(definition.guardrails),
                "blocking_reason": claim_payload["blocked_reason"],
                "derived_from": [
                    definition.source_calc_type,
                    definition.output_key,
                ],
                "human_readable_reason": _human_reason(
                    definition,
                    status=status,
                    missing_inputs=missing_inputs,
                ),
                "raw_status": raw_status,
                "notes": [
                    str(item)
                    for item in list((derivation or {}).get("notes") or [])
                    if item
                ],
                "requirement_tier": definition.requirement_tier,
            }
        )

    compatibility_check = _build_material_medium_compatibility_check_result(
        profile,
        engineering_path,
    )
    if compatibility_check is not None:
        results.append(compatibility_check)

    results.extend(_build_rwdr_professional_check_results(profile, engineering_path))

    return results


def build_check_metrics(checks: Iterable[Any]) -> dict[str, Any]:
    """Summarize backend-owned check availability from projected registry results."""

    items = [_as_dict(check) for check in checks]
    items = [item for item in items if item]
    counts = {
        "check_total": len(items),
        "check_available_count": 0,
        "check_blocked_count": 0,
        "check_pending_count": 0,
        "check_failed_count": 0,
        "check_passed_count": 0,
    }
    for item in items:
        status = str(item.get("status") or "unknown")
        if status in {"passed", "failed"}:
            counts["check_available_count"] += 1
        if status == "blocked":
            counts["check_blocked_count"] += 1
        elif status == "pending":
            counts["check_pending_count"] += 1
        elif status == "failed":
            counts["check_failed_count"] += 1
        elif status == "passed":
            counts["check_passed_count"] += 1
    return {
        **counts,
        "checks": items,
        "source": "backend_check_registry",
    }
