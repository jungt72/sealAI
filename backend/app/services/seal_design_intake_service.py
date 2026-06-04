from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


SEAL_DESIGN_INTAKE_SCHEMA_VERSION = "seal_design_intake_v0.8.3"


@dataclass(frozen=True, slots=True)
class DesignFieldStatus:
    key: str
    label: str
    status: str
    criticality: str
    value: Any = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "criticality": self.criticality,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DesignScreeningCheck:
    check_id: str
    label: str
    status: str
    value: float | None = None
    unit: str | None = None
    inputs: tuple[str, ...] = ()
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "label": self.label,
            "status": self.status,
            "value": self.value,
            "unit": self.unit,
            "inputs": self.inputs,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class DesignEscalationTrigger:
    trigger_id: str
    label: str
    severity: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "label": self.label,
            "severity": self.severity,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SealDesignIntakeBundle:
    schema_version: str
    status: str
    known_fields: tuple[DesignFieldStatus, ...]
    missing_fields: tuple[DesignFieldStatus, ...]
    screening_checks: tuple[DesignScreeningCheck, ...]
    escalation_triggers: tuple[DesignEscalationTrigger, ...]
    next_required_fields: tuple[str, ...]
    boundary_notice: str
    event_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "known_fields": [field.as_dict() for field in self.known_fields],
            "missing_fields": [field.as_dict() for field in self.missing_fields],
            "screening_checks": [check.as_dict() for check in self.screening_checks],
            "escalation_triggers": [
                trigger.as_dict() for trigger in self.escalation_triggers
            ],
            "next_required_fields": self.next_required_fields,
            "boundary_notice": self.boundary_notice,
            "event_names": self.event_names,
        }


class SealDesignIntakeService:
    """Read-only design-intake screening for new sealing designs.

    This service turns a case payload into a strict gap and screening view. It
    does not confirm fields, select a final material, release a design, or write
    case state. Its job is to keep new-design conversations aligned with the
    minimum engineering dataset from the deep-research design framework.
    """

    def build(self, payload: str | Mapping[str, Any]) -> SealDesignIntakeBundle:
        data = _flatten_payload(payload)
        text = _payload_to_text(payload)
        extracted = _extract_text_hints(text)
        values = {**extracted, **data}

        known = tuple(_known_field_statuses(values))
        missing = tuple(_missing_field_statuses(values))
        screening_checks = tuple(_screening_checks(values))
        escalation_triggers = tuple(_escalation_triggers(values, screening_checks))
        next_required = tuple(field.key for field in missing[:5])
        status = _status_for(known, missing)
        events = ["SealDesignIntakeGenerated"]
        if missing:
            events.append("DesignRequiredFieldGapIdentified")
        if screening_checks:
            events.append("DesignScreeningComputed")
        if escalation_triggers:
            events.append("DesignEscalationTriggerIdentified")

        return SealDesignIntakeBundle(
            schema_version=SEAL_DESIGN_INTAKE_SCHEMA_VERSION,
            status=status,
            known_fields=known,
            missing_fields=missing,
            screening_checks=screening_checks,
            escalation_triggers=escalation_triggers,
            next_required_fields=next_required,
            boundary_notice=(
                "Read-only Vorqualifikation fuer Herstellerpruefung; keine finale "
                "Auslegungsfreigabe, keine Materialfreigabe und kein Design-Freeze."
            ),
            event_names=tuple(events),
        )


def build_seal_design_intake(
    payload: str | Mapping[str, Any],
) -> SealDesignIntakeBundle:
    return SealDesignIntakeService().build(payload)


_REQUIRED_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "sealing_function",
        "Dichtfunktion",
        "critical",
        "Ohne Funktion ist das Leckageziel nicht pruefbar.",
    ),
    (
        "leakage_target",
        "Leckageziel",
        "critical",
        "Ohne Leckageziel bleibt jede Loesung nur grob orientierend.",
    ),
    (
        "safety_context",
        "Sicherheits- und Zulassungskontext",
        "critical",
        "Regulierte oder sicherheitskritische Anwendungen muessen frueh markiert werden.",
    ),
    (
        "medium",
        "Medium",
        "critical",
        "Medium und Zusatzstoffe bestimmen Werkstoff- und Nachweisbedarf.",
    ),
    (
        "motion_type",
        "Bewegungsart",
        "critical",
        "Statisch, hubend, oszillierend oder rotierend trennt die Dichtungsfamilien.",
    ),
    (
        "pressure_profile",
        "Druckprofil",
        "critical",
        "Druck min/nom/max, Spitzen und Richtung bestimmen Extrusions- und Bauartgrenzen.",
    ),
    (
        "temperature_profile",
        "Temperaturprofil",
        "critical",
        "Min/nom/max und Peaks bestimmen Werkstofffenster und Alterung.",
    ),
    (
        "geometry_space",
        "Einbauraum und Grundgeometrie",
        "critical",
        "Ohne reale Geometrie sind Nut, Profil und Herstelleranfrage zu ungenau.",
    ),
    (
        "tolerance_gap",
        "Toleranzen, Spalt und Laufabweichung",
        "critical",
        "Spalt, Runout und Exzentrizitaet entscheiden ueber Extrusion und Dichtkontakt.",
    ),
    (
        "surface_roughness",
        "Oberflaechenwerte",
        "critical",
        "Ra/Rz/Rt, Haerte und Lead beeinflussen Leckage, Reibung und Verschleiss.",
    ),
    (
        "verification_criteria",
        "Pruef- und Abnahmekriterium",
        "critical",
        "Eine Neuauslegung braucht einen messbaren Nachweisweg.",
    ),
    (
        "lifetime_target",
        "Lebensdauerziel",
        "important",
        "Betriebsstunden oder Zyklen bestimmen den Auslegungs- und Testumfang.",
    ),
    (
        "lubrication",
        "Schmierung und Trockenlauf",
        "important",
        "Schmierung beeinflusst Reibung, Waerme und Verschleiss.",
    ),
    (
        "contamination",
        "Partikel, Schmutz und Abrasion",
        "important",
        "Abrasive oder Kristalle verschieben Werkstoff- und Profilrisiken.",
    ),
    (
        "mounting_path",
        "Montagepfad",
        "important",
        "Kanten, Fasen, Werkzeuge und Montagehilfe koennen Dichtungen schon beim Einbau schaedigen.",
    ),
)

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sealing_function": (
        "sealing_function",
        "seal_function",
        "primary_function",
        "function",
        "dichtfunktion",
    ),
    "leakage_target": (
        "leakage_target",
        "leak_target",
        "leakage_requirement",
        "leakage_rate",
        "leakage_class",
        "atex_or_leakage_requirement",
    ),
    "safety_context": (
        "safety_context",
        "safety_relevance",
        "criticality",
        "compliance",
        "atex_relevance",
        "certification_requirement",
    ),
    "medium": ("medium", "medium_name", "primary_medium", "hydraulic_fluid", "media"),
    "motion_type": ("motion_type", "movement", "static_or_dynamic", "speed_or_stroke"),
    "pressure_profile": (
        "pressure_profile",
        "pressure",
        "pressure_bar",
        "pressure_mpa",
        "pressure_max_bar",
        "pressure_nominal",
        "pressure_peak",
        "pressure_peaks",
    ),
    "temperature_profile": (
        "temperature_profile",
        "temperature",
        "temperature_c",
        "temperature_min",
        "temperature_max",
        "temperature_max_c",
        "temperature_min_c",
    ),
    "geometry_space": (
        "geometry_space",
        "geometry",
        "geometry_context",
        "available_space",
        "groove_dimensions",
        "shaft_diameter",
        "shaft_diameter_mm",
        "housing_bore",
        "housing_bore_mm",
    ),
    "tolerance_gap": (
        "tolerance_gap",
        "radial_gap_mm",
        "clearance_gap_mm",
        "gap",
        "shaft_runout",
        "runout_um",
        "eccentricity",
        "misalignment",
    ),
    "surface_roughness": (
        "surface_roughness",
        "surface_finish",
        "surface_roughness_ra_um",
        "surface_roughness_rz_um",
        "counterface_surface",
        "shaft_surface",
    ),
    "verification_criteria": (
        "verification_criteria",
        "acceptance_criteria",
        "lab_tests",
        "field_tests",
        "test_plan",
        "proof_required",
    ),
    "lifetime_target": (
        "lifetime_target",
        "target_lifetime",
        "target_lifetime_hours",
        "target_lifetime_cycles",
        "service_life",
    ),
    "lubrication": (
        "lubrication",
        "lubrication_condition",
        "dry_run",
        "wetting_condition",
    ),
    "contamination": (
        "contamination",
        "particles",
        "particles_present",
        "abrasive_content",
        "solids_or_gas_content",
    ),
    "mounting_path": (
        "mounting_path",
        "installation_context",
        "installation_method",
        "assembly",
        "lead_in_angle_deg",
        "mounting_tool",
    ),
}

_NUMERIC_ALIASES: dict[str, tuple[str, ...]] = {
    "pressure_max_bar": ("pressure_max_bar", "pressure_peak", "pressure_bar"),
    "pressure_mpa": ("pressure_mpa",),
    "radial_gap_mm": ("radial_gap_mm", "clearance_gap_mm"),
    "decompression_rate_bar_per_s": ("decompression_rate_bar_per_s", "relief_rate"),
    "temperature_max_c": ("temperature_max_c", "temperature_max", "temperature_c"),
    "cross_section_mm": ("cross_section_mm", "cross_section", "cord_diameter"),
    "groove_depth_mm": ("groove_depth_mm", "groove_depth"),
    "groove_width_mm": ("groove_width_mm", "groove_width"),
    "seal_inner_diameter_mm": (
        "seal_inner_diameter_mm",
        "inner_diameter",
        "inner_diameter_mm",
    ),
    "shaft_diameter_mm": ("shaft_diameter_mm", "shaft_diameter"),
}


def _status_for(
    known: tuple[DesignFieldStatus, ...],
    missing: tuple[DesignFieldStatus, ...],
) -> str:
    if not known:
        return "no_design_dataset"
    if any(field.criticality == "critical" for field in missing):
        return "minimal_dataset_missing"
    if missing:
        return "preselection_ready_with_open_points"
    return "design_review_ready_not_released"


def _known_field_statuses(values: Mapping[str, Any]) -> list[DesignFieldStatus]:
    result: list[DesignFieldStatus] = []
    for key, label, criticality, reason in _REQUIRED_FIELDS:
        value = _lookup(values, key)
        if value in (None, "", [], {}):
            continue
        result.append(
            DesignFieldStatus(
                key=key,
                label=label,
                status="provided_not_released",
                criticality=criticality,
                value=value,
                reason=reason,
            )
        )
    return result


def _missing_field_statuses(values: Mapping[str, Any]) -> list[DesignFieldStatus]:
    result: list[DesignFieldStatus] = []
    for key, label, criticality, reason in _REQUIRED_FIELDS:
        if _lookup(values, key) not in (None, "", [], {}):
            continue
        result.append(
            DesignFieldStatus(
                key=key,
                label=label,
                status="not_specified",
                criticality=criticality,
                reason=reason,
            )
        )
    return result


def _screening_checks(values: Mapping[str, Any]) -> list[DesignScreeningCheck]:
    checks: list[DesignScreeningCheck] = []
    cross_section = _num(values, "cross_section_mm")
    groove_depth = _num(values, "groove_depth_mm")
    groove_width = _num(values, "groove_width_mm")
    seal_id = _num(values, "seal_inner_diameter_mm")
    shaft_diameter = _num(values, "shaft_diameter_mm")

    if cross_section is not None and groove_depth is not None and cross_section > 0:
        squeeze = ((cross_section - groove_depth) / cross_section) * 100.0
        checks.append(
            DesignScreeningCheck(
                check_id="oring.squeeze_pct",
                label="Verpressung",
                status=_band(squeeze, low=8.0, high=30.0),
                value=round(squeeze, 2),
                unit="%",
                inputs=("cross_section_mm", "groove_depth_mm"),
                message="Vorpruefung; reale Grenzwerte haengen von Dichtungsart und Herstellerdaten ab.",
            )
        )

    if (
        cross_section is not None
        and groove_depth is not None
        and groove_width is not None
        and groove_depth > 0
        and groove_width > 0
    ):
        area_seal = math.pi / 4.0 * cross_section**2
        area_groove = groove_depth * groove_width
        groove_fill = area_seal / area_groove * 100.0
        checks.append(
            DesignScreeningCheck(
                check_id="oring.groove_fill_pct",
                label="Nutfuellung",
                status="warning" if groove_fill > 85.0 else "screening_ok",
                value=round(groove_fill, 2),
                unit="%",
                inputs=("cross_section_mm", "groove_depth_mm", "groove_width_mm"),
                message="Richtwert: moeglichst nicht ueber 85 % im Einbauzustand.",
            )
        )

    if seal_id is not None and shaft_diameter is not None and seal_id > 0:
        stretch = ((shaft_diameter - seal_id) / seal_id) * 100.0
        checks.append(
            DesignScreeningCheck(
                check_id="oring.stretch_pct",
                label="Umfangsdehnung",
                status="warning" if stretch > 6.0 else "screening_ok",
                value=round(stretch, 2),
                unit="%",
                inputs=("seal_inner_diameter_mm", "shaft_diameter_mm"),
                message="Richtwert: Montage-Dehnung moeglichst nicht ueber 6 %.",
            )
        )
    return checks


def _escalation_triggers(
    values: Mapping[str, Any],
    checks: Sequence[DesignScreeningCheck],
) -> list[DesignEscalationTrigger]:
    triggers: list[DesignEscalationTrigger] = []
    pressure_bar = _pressure_bar(values)
    radial_gap = _num(values, "radial_gap_mm")
    decompression_rate = _num(values, "decompression_rate_bar_per_s")
    temperature_max = _num(values, "temperature_max_c")
    medium = str(_lookup(values, "medium") or "").casefold()
    seal_text = str(_lookup(values, "geometry_space") or "").casefold()
    leakage_target = _lookup(values, "leakage_target")

    if pressure_bar is not None and pressure_bar >= 100 and radial_gap is None:
        triggers.append(
            DesignEscalationTrigger(
                trigger_id="high_pressure_gap_unknown",
                label="Hochdruck mit unbekanntem Dichtspalt",
                severity="high",
                reason="Bei hohem Druck muss Spalt/Toleranz fuer Extrusion und Stuetzringbedarf geklaert werden.",
            )
        )
    if (
        pressure_bar is not None
        and radial_gap is not None
        and pressure_bar >= 100
        and radial_gap >= 0.3
    ):
        triggers.append(
            DesignEscalationTrigger(
                trigger_id="high_pressure_large_gap",
                label="Hochdruck und grosser Spalt",
                severity="critical",
                reason="Profil, Haerte, Stuetzring und ggf. FEA/Worst-Case-Toleranzstack sind zu pruefen.",
            )
        )
    if _looks_like_gas(medium) and (
        decompression_rate is not None or (pressure_bar or 0) >= 30
    ):
        triggers.append(
            DesignEscalationTrigger(
                trigger_id="gas_decompression_review",
                label="Gasdienst / schnelle Dekompression pruefen",
                severity="high",
                reason="Gas, Druck und Entlastungsrate koennen ED-/RGD-Werkstoffe und kontrollierte Entspannung erfordern.",
            )
        )
    groove_fill = next(
        (check.value for check in checks if check.check_id == "oring.groove_fill_pct"),
        None,
    )
    if (
        groove_fill is not None
        and groove_fill > 85.0
        and (temperature_max or 0.0) >= 100.0
    ):
        triggers.append(
            DesignEscalationTrigger(
                trigger_id="hot_high_groove_fill",
                label="Hohe Temperatur und hohe Nutfuellung",
                severity="high",
                reason="Thermische Ausdehnung, Quellung und Toleranzstack koennen die Nut ueberfuellen.",
            )
        )
    if leakage_target and any(
        token in seal_text
        for token in ("flansch", "flange", "flat gasket", "flachdichtung")
    ):
        triggers.append(
            DesignEscalationTrigger(
                trigger_id="flange_norm_calculation_required",
                label="Flanschdichtung mit Leckageziel",
                severity="high",
                reason="EN-13555-Kennwerte und EN-1591-1-Rechnung muessen als Nachweisweg beruecksichtigt werden.",
            )
        )
    return triggers


def _flatten_payload(payload: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, str):
        return {}
    result: dict[str, Any] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if item not in (None, "", [], {}):
                    result[str(key)] = item
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for item in value:
                visit(item)

    visit(payload)
    return result


def _payload_to_text(payload: str | Mapping[str, Any]) -> str:
    if isinstance(payload, str):
        return payload
    parts: list[str] = []
    for key in ("text", "message", "description", "request", "user_message"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _extract_text_hints(text: str) -> dict[str, Any]:
    normalized = str(text or "")
    result: dict[str, Any] = {}
    if re.search(
        r"\b(sichtleckage|leckrate|leckageziel|leckklasse|tropfgrenze|sccm|ml/min)\b",
        normalized,
        re.IGNORECASE,
    ):
        result["leakage_target"] = _clip_sentence(
            normalized,
            ("leckage", "leckrate", "leckageziel", "leckklasse", "sccm", "ml/min"),
        )
    if re.search(
        r"\b(statisch|rotierend|hubend|oszillierend|schwenkend)\b",
        normalized,
        re.IGNORECASE,
    ):
        result["motion_type"] = _clip_sentence(
            normalized,
            ("statisch", "rotierend", "hubend", "oszillierend", "schwenkend"),
        )
    if re.search(
        r"\b(medium|hlp|wasser|oel|öl|ethanol|salzwasser|luft|gas|wasserstoff)\b",
        normalized,
        re.IGNORECASE,
    ):
        result["medium"] = _clip_sentence(
            normalized,
            (
                "medium",
                "hlp",
                "wasser",
                "oel",
                "öl",
                "ethanol",
                "salzwasser",
                "luft",
                "gas",
                "wasserstoff",
            ),
        )
    if re.search(
        r"\b(fda|atex|trinkwasser|pharma|gmp|food|lebensmittel|sauerstoff|wasserstoff)\b",
        normalized,
        re.IGNORECASE,
    ):
        result["safety_context"] = _clip_sentence(
            normalized,
            (
                "fda",
                "atex",
                "trinkwasser",
                "pharma",
                "gmp",
                "food",
                "lebensmittel",
                "sauerstoff",
                "wasserstoff",
            ),
        )
    return result


def _lookup(values: Mapping[str, Any], canonical_key: str) -> Any:
    for alias in (canonical_key, *_FIELD_ALIASES.get(canonical_key, ())):
        value = values.get(alias)
        if value not in (None, "", [], {}):
            return value
    return None


def _num(values: Mapping[str, Any], canonical_key: str) -> float | None:
    aliases = (
        canonical_key,
        *_NUMERIC_ALIASES.get(canonical_key, ()),
        *_FIELD_ALIASES.get(canonical_key, ()),
    )
    for alias in aliases:
        value = values.get(alias)
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return None


def _pressure_bar(values: Mapping[str, Any]) -> float | None:
    pressure_bar = _num(values, "pressure_max_bar")
    if pressure_bar is not None:
        return pressure_bar
    pressure_mpa = _num(values, "pressure_mpa")
    if pressure_mpa is not None:
        return pressure_mpa * 10.0
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, "", [], {}):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _band(value: float, *, low: float, high: float) -> str:
    if value < low:
        return "low_review"
    if value > high:
        return "warning"
    return "screening_ok"


def _looks_like_gas(text: str) -> bool:
    return any(
        token in text
        for token in (
            "gas",
            "luft",
            "wasserstoff",
            "n2",
            "stickstoff",
            "sauerstoff",
            "co2",
        )
    )


def _clip_sentence(text: str, markers: Sequence[str]) -> str:
    compact = " ".join(str(text or "").split())
    lowered = compact.casefold()
    for marker in markers:
        index = lowered.find(marker.casefold())
        if index >= 0:
            return compact[max(0, index - 24) : index + 96].strip(" .,:;")
    return compact[:120].strip(" .,:;")
