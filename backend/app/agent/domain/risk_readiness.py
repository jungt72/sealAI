"""Deterministic v0.4 risk and RFQ-readiness evaluation.

The LLM may explain risks in natural language, but the numeric risk score and
readiness level are backend-owned, rule-based projection facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

RULESET_VERSION = "v0.4-mvp-2026-04-25"

RISK_LABELS: dict[int, str] = {
    0: "low",
    1: "watch",
    2: "moderate",
    3: "high",
    4: "critical",
    9: "unknown",
}

READINESS_LABELS: dict[int, str] = {
    0: "no_technical_case_detected",
    1: "application_roughly_recognized",
    2: "sealing_situation_partly_understood",
    3: "technical_direction_plausible",
    4: "rfq_preparable_with_open_points",
    5: "manufacturer_ready_inquiry",
}

_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "asset_type": ("asset_type", "installation", "application_context"),
    "seal_location": ("seal_location", "geometry_context"),
    "motion_type": ("motion_type", "movement_type"),
    "medium_name": ("medium_name", "medium"),
    "temperature_min": ("temperature_min", "temperature_min_c"),
    "temperature_max": ("temperature_max", "temperature_max_c", "temperature_c"),
    "pressure_nominal": ("pressure_nominal", "pressure_bar", "pressure"),
    "speed_rpm": ("speed_rpm", "rpm"),
    "shaft_diameter": ("shaft_diameter", "shaft_diameter_mm"),
    "geometry": ("geometry", "geometry_context", "housing_bore", "housing_bore_mm", "installation_width", "installation_width_mm"),
    "food_contact": ("food_contact", "compliance", "industry"),
    "atex": ("atex", "compliance", "industry"),
    "contamination": ("contamination", "medium_qualifiers"),
    "surface_finish": ("surface_finish", "counterface_surface"),
    "runout": ("shaft_runout", "runout_mm"),
    "sealing_type": ("sealing_type", "seal_type"),
}

CRITICAL_FIELDS: tuple[str, ...] = (
    "asset_type",
    "seal_location",
    "motion_type",
    "medium_name",
    "temperature_max",
    "pressure_nominal",
    "speed_rpm",
    "shaft_diameter",
    "geometry",
    "food_contact",
    "atex",
)


def _value(profile: dict[str, Any], key: str) -> Any:
    for candidate in _ALIAS_MAP.get(key, (key,)):
        if candidate not in profile:
            continue
        value = profile.get(candidate)
        if value not in (None, "", []):
            return value
    return None


def _has(profile: dict[str, Any], key: str) -> bool:
    return _value(profile, key) not in (None, "", [])


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value or "").strip().casefold()


def _contains(value: Any, needles: Iterable[str]) -> bool:
    text = _text(value)
    return any(needle.casefold() in text for needle in needles)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _add_unique(items: list[str], values: Iterable[str]) -> list[str]:
    for item in values:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


@dataclass(frozen=True)
class RiskEvaluationResult:
    risk_name: str
    score: int
    drivers: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    explanation_short: str = ""
    confidence: str = "medium"
    ruleset_version: str = RULESET_VERSION

    @property
    def label(self) -> str:
        return RISK_LABELS.get(self.score, "unknown")

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_name": self.risk_name,
            "score": self.score,
            "label": self.label,
            "drivers": list(self.drivers),
            "missing_inputs": list(self.missing_inputs),
            "rule_ids": list(self.rule_ids),
            "explanation_short": self.explanation_short,
            "confidence": self.confidence,
            "ruleset_version": self.ruleset_version,
        }


@dataclass(frozen=True)
class ReadinessEvaluationResult:
    readiness_level: int
    readiness_label: str
    missing_required_fields: list[str]
    blocking_unknowns: list[str]
    recommended_next_question: str | None
    rfq_possible: bool
    risk_score_max: int
    risk_label_max: str
    ruleset_version: str = RULESET_VERSION

    def to_profile_patch(self) -> dict[str, Any]:
        return {
            "readiness_level": self.readiness_level,
            "readiness_label": self.readiness_label,
            "missing_required_fields": list(self.missing_required_fields),
            "blocking_unknowns": list(self.blocking_unknowns),
            "recommended_next_question": self.recommended_next_question,
            "rfq_possible": self.rfq_possible,
            "risk_score_max": self.risk_score_max,
            "risk_label_max": self.risk_label_max,
        }


def missing_critical_fields(profile: dict[str, Any], *, engineering_path: str | None = None) -> list[str]:
    missing = [field for field in CRITICAL_FIELDS if not _has(profile, field)]
    path = str(engineering_path or "")
    if path in {"static", "hyd_pneu"}:
        missing = [field for field in missing if field not in {"speed_rpm", "shaft_diameter"}]
    if path == "ms_pump":
        missing = [field for field in missing if field != "geometry"]
    return missing


def evaluate_risks(
    profile: dict[str, Any],
    *,
    engineering_path: str | None = None,
    missing_required_fields: list[str] | None = None,
    checks: list[Any] | None = None,
) -> list[RiskEvaluationResult]:
    missing_required_fields = list(missing_required_fields or [])
    checks = checks or []
    results: list[RiskEvaluationResult] = []

    critical_missing = missing_critical_fields(profile, engineering_path=engineering_path)
    unknowns_missing = list(dict.fromkeys(missing_required_fields + critical_missing))
    results.append(
        RiskEvaluationResult(
            risk_name="unknowns_risk",
            score=9 if unknowns_missing else 0,
            drivers=["critical_inputs_missing"] if unknowns_missing else ["critical_inputs_available"],
            missing_inputs=unknowns_missing,
            rule_ids=["risk.unknowns.missing_critical.v0"],
            explanation_short=(
                "Kritische Eingangsdaten fehlen; technische Bewertung bleibt begrenzt."
                if unknowns_missing
                else "Keine kritischen Pflichtdaten als fehlend markiert."
            ),
            confidence="high",
        )
    )

    medium = _value(profile, "medium_name")
    qualifiers = _value(profile, "contamination")
    temp = _float(_value(profile, "temperature_max"))
    pressure = _float(_value(profile, "pressure_nominal"))
    speed = _float(_value(profile, "speed_rpm"))

    corrosive = _contains(medium, ("salz", "salt", "seawater", "meerwasser", "chlorid", "chloride", "saeure", "acid")) or _contains(qualifiers, ("chlorid", "chloride", "salinity"))
    if medium is None:
        results.append(RiskEvaluationResult("corrosion_risk", 9, missing_inputs=["medium_name"], rule_ids=["risk.corrosion.medium_missing.v0"], explanation_short="Korrosionsrisiko ohne Medium nicht bewertbar.", confidence="high"))
    elif corrosive:
        score = 3 if (temp is not None and temp >= 60) else 2
        results.append(RiskEvaluationResult("corrosion_risk", score, drivers=["corrosive_or_saline_medium"] + (["temperature_elevated"] if score >= 3 else []), rule_ids=["risk.corrosion.saline_or_acidic.v0"], explanation_short="Mediumhinweise deuten auf Korrosions-/Werkstoffrisiko.", confidence="medium"))
    else:
        results.append(RiskEvaluationResult("corrosion_risk", 0, drivers=["no_corrosive_hint"], rule_ids=["risk.corrosion.no_hint.v0"], explanation_short="Kein eindeutiger Korrosionshinweis aus den bekannten Angaben.", confidence="low"))

    abrasive = _contains(qualifiers, ("abras", "partikel", "particle", "sand", "feststoff", "solids", "schmutz"))
    results.append(
        RiskEvaluationResult(
            "abrasion_risk",
            3 if abrasive else 0,
            drivers=["abrasive_contamination"] if abrasive else ["no_abrasive_hint"],
            rule_ids=["risk.abrasion.contamination.v0"],
            explanation_short=("Partikel/Feststoffe koennen Dichtkante oder Gleitflaechen belasten." if abrasive else "Kein Abrasionshinweis aus den bekannten Angaben."),
            confidence="medium" if abrasive else "low",
        )
    )

    if temp is None:
        results.append(RiskEvaluationResult("temperature_risk", 9, missing_inputs=["temperature_max"], rule_ids=["risk.temperature.missing.v0"], explanation_short="Temperatur fehlt; Werkstofffenster nicht belastbar pruefbar.", confidence="high"))
    else:
        if temp >= 200:
            score = 4
        elif temp >= 140:
            score = 3
        elif temp >= 90:
            score = 2
        else:
            score = 0
        results.append(RiskEvaluationResult("temperature_risk", score, drivers=[f"temperature_max={temp:g}C"], rule_ids=["risk.temperature.thresholds.v0"], explanation_short="Temperatur wird gegen MVP-Schwellen bewertet.", confidence="medium"))

    if pressure is None:
        results.append(RiskEvaluationResult("pressure_risk", 9, missing_inputs=["pressure_nominal"], rule_ids=["risk.pressure.missing.v0"], explanation_short="Druck fehlt; Auspress-/Bauartgrenzen nicht bewertbar.", confidence="high"))
    else:
        if pressure >= 25:
            score = 3
        elif pressure >= 10:
            score = 2
        elif pressure > 1 and str(engineering_path or "") == "rwdr":
            score = 2
        else:
            score = 0
        results.append(RiskEvaluationResult("pressure_risk", score, drivers=[f"pressure_nominal={pressure:g}bar"], rule_ids=["risk.pressure.thresholds.v0"], explanation_short="Druck wird gegen MVP-Schwellen bewertet.", confidence="medium"))

    pv_scores: list[int] = []
    pv_missing: list[str] = []
    for check in checks:
        calc_id = str(getattr(check, "calc_id", "") or "")
        if calc_id not in {"rwdr_pv_precheck", "rwdr_dn_value", "rwdr_circumferential_speed"}:
            continue
        missing_inputs = list(getattr(check, "missing_inputs", []) or [])
        if missing_inputs:
            pv_missing.extend(str(item) for item in missing_inputs)
            continue
        value = _float(getattr(check, "value", None))
        if value is None:
            continue
        if calc_id == "rwdr_pv_precheck":
            pv_scores.append(3 if value >= 1.0 else 2 if value >= 0.5 else 0)
        elif calc_id == "rwdr_dn_value":
            pv_scores.append(3 if value >= 200000 else 2 if value >= 100000 else 0)
        elif calc_id == "rwdr_circumferential_speed":
            pv_scores.append(3 if value >= 12 else 2 if value >= 8 else 0)
    if pv_scores:
        results.append(RiskEvaluationResult("speed_pv_risk", max(pv_scores), drivers=["registered_check_results"], rule_ids=["risk.speed_pv.registered_checks.v0"], explanation_short="Drehzahl/PV wird aus registrierten Berechnungen bewertet.", confidence="medium"))
    elif speed is None and str(engineering_path or "") in {"rwdr", "ms_pump", "unclear_rotary"}:
        results.append(RiskEvaluationResult("speed_pv_risk", 9, missing_inputs=list(dict.fromkeys(pv_missing or ["speed_rpm"])), rule_ids=["risk.speed_pv.missing.v0"], explanation_short="Drehzahl/PV nicht bewertbar, weil Eingaben fehlen.", confidence="high"))

    compliance = _value(profile, "food_contact")
    regulated = _contains(compliance, ("food", "lebensmittel", "pharma", "hygiene"))
    if regulated and not _contains(compliance, ("confirmed", "yes", "true", "food_contact")):
        results.append(RiskEvaluationResult("hygiene_risk", 2, drivers=["regulated_context_unclear"], rule_ids=["risk.hygiene.regulated_context.v0"], explanation_short="Hygiene-/Lebensmittelkontext braucht explizite Klaerung.", confidence="medium"))

    surface_missing = not _has(profile, "surface_finish")
    runout_missing = not _has(profile, "runout")
    if str(engineering_path or "") == "rwdr" and (surface_missing or runout_missing):
        missing = []
        if surface_missing:
            missing.append("surface_finish")
        if runout_missing:
            missing.append("shaft_runout")
        results.append(RiskEvaluationResult("surface_risk", 9, missing_inputs=missing, rule_ids=["risk.surface.rwdr_missing.v0"], explanation_short="RWDR-Funktion haengt stark von Gegenlaufflaeche und Rundlauf ab.", confidence="high"))

    return sorted(results, key=lambda item: (item.score != 9, item.score), reverse=True)


def evaluate_readiness(
    profile: dict[str, Any],
    *,
    request_type: str | None = None,
    engineering_path: str | None = None,
    missing_mandatory_keys: list[str] | None = None,
    blockers: list[str] | None = None,
    risk_results: list[RiskEvaluationResult] | None = None,
) -> ReadinessEvaluationResult:
    missing_mandatory_keys = list(missing_mandatory_keys or [])
    blockers = list(blockers or [])
    risk_results = list(risk_results or [])

    has_asset_or_problem = _has(profile, "asset_type") or bool(request_type)
    has_motion_or_location = _has(profile, "motion_type") or _has(profile, "seal_location")
    has_medium_or_problem = _has(profile, "medium_name") or _has(profile, "contamination")
    has_operating = _has(profile, "temperature_max") or _has(profile, "pressure_nominal") or _has(profile, "speed_rpm")
    has_direction = bool(engineering_path) or _has(profile, "sealing_type")
    has_temp = _has(profile, "temperature_max")
    has_pressure = _has(profile, "pressure_nominal")
    has_speed_or_static = _has(profile, "speed_rpm") or _contains(_value(profile, "motion_type"), ("static", "linear", "statisch", "linear"))
    has_geometry_partial = _has(profile, "shaft_diameter") or _has(profile, "geometry")

    if not (has_asset_or_problem or has_medium_or_problem or has_motion_or_location):
        level = 0
    elif has_asset_or_problem and not (has_motion_or_location and has_medium_or_problem):
        level = 1
    elif has_asset_or_problem and has_motion_or_location and has_medium_or_problem:
        level = 2
        if has_operating and has_direction:
            level = 3
            if has_temp and has_pressure and has_speed_or_static and has_geometry_partial:
                level = 4
    else:
        level = 1

    risk_score_max = 0
    for result in risk_results:
        if result.score == 9:
            continue
        risk_score_max = max(risk_score_max, result.score)

    blocking_unknowns = list(dict.fromkeys(blockers))
    critical_missing = missing_critical_fields(profile, engineering_path=engineering_path)
    missing_required = list(dict.fromkeys(critical_missing))
    has_unknown_risk = any(result.score == 9 and result.missing_inputs for result in risk_results)
    has_critical_risk = any(result.score >= 4 for result in risk_results if result.score != 9)

    if level >= 4 and not critical_missing and not blocking_unknowns and not has_unknown_risk and not has_critical_risk:
        level = 5

    if has_critical_risk and level > 4:
        level = 4

    next_question = _next_question(missing_required or blocking_unknowns)
    return ReadinessEvaluationResult(
        readiness_level=level,
        readiness_label=READINESS_LABELS[level],
        missing_required_fields=missing_required,
        blocking_unknowns=blocking_unknowns,
        recommended_next_question=next_question,
        rfq_possible=level >= 5,
        risk_score_max=risk_score_max if not has_unknown_risk else 9,
        risk_label_max=RISK_LABELS[9 if has_unknown_risk else risk_score_max],
    )


def _next_question(missing_fields: list[str]) -> str | None:
    if not missing_fields:
        return None
    field = missing_fields[0]
    questions = {
        "asset_type": "In welcher Anlage oder Baugruppe sitzt die Dichtung?",
        "seal_location": "Wo genau sitzt die Dichtstelle?",
        "motion_type": "Ist die Dichtstelle rotierend, statisch oder linear bewegt?",
        "medium_name": "Welches Medium beruehrt die Dichtung?",
        "temperature_max": "Welche maximale Betriebstemperatur tritt an der Dichtstelle auf?",
        "pressure_nominal": "Welcher Betriebsdruck liegt an der Dichtung an?",
        "speed_rpm": "Welche Drehzahl liegt an der Welle an?",
        "shaft_diameter": "Welchen Wellendurchmesser hat die Dichtstelle?",
        "geometry": "Welche Einbaugeometrie oder Abmessungen sind bekannt?",
        "food_contact": "Gibt es Lebensmittel-, Pharma- oder Hygieneanforderungen?",
        "atex": "Gibt es ATEX- oder Explosionsschutzanforderungen?",
    }
    return questions.get(field, f"Koennen Sie den fehlenden Punkt '{field}' ergaenzen?")
