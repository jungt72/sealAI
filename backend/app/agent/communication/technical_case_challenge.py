from __future__ import annotations

import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


ANSWER_MODE_TECHNICAL_CASE_CHALLENGE = "technical_case_challenge"


class RWDRChallengeSignals(BaseModel):
    d1_mm: float | None = None
    D_mm: float | None = None
    b_mm: float | None = None
    medium: str | None = None
    pressure_bar: float | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    speed_rpm: float | None = None
    circumferential_speed_mps: float | None = None
    application: str | None = None
    counterface_surface: str | None = None
    eccentricity: str | None = None
    material_mentions: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    missing_critical_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class TechnicalCaseChallengePlan(BaseModel):
    case_type: str = "technical_case"
    detected_domain: str = "unknown"
    confirmed_or_extracted_facts: dict[str, Any] = Field(default_factory=dict)
    computed_signals: list[str] = Field(default_factory=list)
    critical_points: list[str] = Field(default_factory=list)
    cautious_hypotheses: list[str] = Field(default_factory=list)
    counter_indicators: list[str] = Field(default_factory=list)
    missing_blockers: list[str] = Field(default_factory=list)
    next_best_question: str | None = None
    forbidden_claims: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Das ist eine technische Strukturierung für die weitere Bewertung, "
        "keine finale Freigabe und keine Materialentscheidung."
    )
    rwdr_signals: RWDRChallengeSignals | None = None

    model_config = ConfigDict(extra="forbid")


_CHALLENGE_MARKERS = (
    "challenge",
    "analysiere",
    "analyse",
    "prüfe kritisch",
    "pruefe kritisch",
    "kritische punkte",
    "keine stumpfe parameterabfrage",
    "gegenindikatoren",
    "prüfhypothesen",
    "pruefhypothesen",
    "fehlende blocker",
    "nächste beste rückfrage",
    "naechste beste rueckfrage",
    "stress-test",
)

_CASE_MARKERS = (
    "dichtungsfall",
    "dichtungsparameter",
    "rwdr",
    "radialwellendichtring",
    "wellendichtring",
    "medium",
    "druck",
    "temperatur",
    "drehzahl",
    "wellendurchmesser",
    "d1",
)

_KNOWLEDGE_ONLY_RE = re.compile(
    r"^\s*(?:was\s+ist|was\s+sind|erklär|erklaer|unterschied|vergleich|ptfe|fkm|nbr|epdm|hnbr|ffkm)"
    r".{0,120}(?:ptfe|fkm|nbr|epdm|hnbr|ffkm)?\s*\??\s*$",
    re.IGNORECASE | re.UNICODE,
)


def is_technical_case_challenge_request(message: str | None) -> bool:
    text = _clean_text(message)
    if not text:
        return False
    has_challenge_marker = any(marker in text for marker in _CHALLENGE_MARKERS)
    has_case_marker = any(marker in text for marker in _CASE_MARKERS)
    has_numeric_case_data = bool(re.search(r"\b\d+(?:[,.]\d+)?\s*(?:bar|rpm|°c|grad|mm)\b", text))
    if has_challenge_marker and (has_case_marker or has_numeric_case_data):
        return True
    if has_challenge_marker:
        return False
    if _KNOWLEDGE_ONLY_RE.match(str(message or "")) and not has_numeric_case_data:
        return False
    return has_case_marker and has_numeric_case_data and any(marker in text for marker in ("analys", "bewert", "prüf", "pruef"))


def build_technical_case_challenge_plan(
    *,
    latest_user_message: str | None,
    state_snapshot: dict[str, Any] | None = None,
    missing_fields: list[str] | None = None,
    force: bool = False,
) -> TechnicalCaseChallengePlan | None:
    if not force and not is_technical_case_challenge_request(latest_user_message):
        return None

    text = str(latest_user_message or "")
    snapshot_facts = _facts_from_snapshot(state_snapshot or {})
    extracted = _facts_from_text(text)
    facts = {**extracted, **{key: value for key, value in snapshot_facts.items() if value not in (None, "", [], {})}}
    domain = "rwdr" if _looks_like_rwdr(text, facts) else "technical_sealing_case"
    if domain != "rwdr":
        return TechnicalCaseChallengePlan(
            detected_domain=domain,
            confirmed_or_extracted_facts=facts,
            critical_points=[
                "Der Fall enthält konkrete Betriebsdaten und sollte als technischer Bewertungsfall strukturiert werden.",
                "Ohne Dichtprinzip, Mediumspezifikation und Lastkollektiv bleibt die Bewertung offen.",
            ],
            missing_blockers=_unique(missing_fields or []),
            next_best_question="Welches Dichtprinzip und welche reale Dichtstelle sollen bewertet werden?",
            forbidden_claims=_forbidden_claims(),
        )

    signals = _rwdr_signals_from_facts(facts, missing_fields or [])
    critical_points = _rwdr_critical_points(signals)
    hypotheses = _rwdr_hypotheses(signals)
    counter_indicators = _rwdr_counter_indicators(signals)
    missing_blockers = _rwdr_missing_blockers(signals)
    next_question = _rwdr_next_best_question(signals)

    return TechnicalCaseChallengePlan(
        case_type="rwdr_technical_case",
        detected_domain="rwdr",
        confirmed_or_extracted_facts={key: value for key, value in facts.items() if value not in (None, "", [], {})},
        computed_signals=_rwdr_computed_signals(signals),
        critical_points=critical_points,
        cautious_hypotheses=hypotheses,
        counter_indicators=counter_indicators,
        missing_blockers=missing_blockers,
        next_best_question=next_question,
        forbidden_claims=_forbidden_claims(),
        rwdr_signals=signals,
    )


def render_technical_case_challenge_plan(plan: TechnicalCaseChallengePlan) -> str:
    lines: list[str] = [
        "### Kurzurteil",
        _short_judgement(plan),
        "",
        "### Kritische Punkte",
        *_bullet_lines(plan.critical_points),
        "",
        "### Abgeleitete Signale",
        *_bullet_lines(plan.computed_signals or ["Keine belastbare Berechnung aus den vorliegenden Angaben ableitbar."]),
        "",
        "### Vorsichtige Prüfhypothesen",
        *_bullet_lines(plan.cautious_hypotheses),
        "",
        "### Gegenindikatoren / Risiken",
        *_bullet_lines(plan.counter_indicators),
        "",
        "### Fehlende Blocker",
        *_bullet_lines(plan.missing_blockers),
        "",
        "### Nächste beste Rückfrage",
        plan.next_best_question or "Welche einzelne Angabe blockiert die Bewertung aus deiner Sicht am stärksten?",
        "",
        "### Grenze der Aussage",
        plan.disclaimer,
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def _clean_text(message: str | None) -> str:
    return " ".join(str(message or "").casefold().split())


def _looks_like_rwdr(text: str, facts: dict[str, Any]) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in ("rwdr", "wellendichtring", "radialwellendichtring")) or any(
        facts.get(key) is not None for key in ("d1_mm", "D_mm", "b_mm", "speed_rpm", "counterface_surface")
    )


def _facts_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    asserted = dict(snapshot.get("asserted", {}) or {}).get("assertions", {}) or {}
    for key, claim in dict(asserted).items():
        if not isinstance(claim, dict):
            continue
        value = claim.get("asserted_value")
        if value in (None, "", [], {}):
            continue
        mapped = _map_field_name(str(key))
        if mapped:
            facts[mapped] = value
    normalized = dict(snapshot.get("normalized", {}) or {}).get("parameters", {}) or {}
    for key, parameter in dict(normalized).items():
        if not isinstance(parameter, dict):
            continue
        value = parameter.get("value")
        if value in (None, "", [], {}):
            continue
        mapped = _map_field_name(str(key))
        if mapped:
            facts[mapped] = value
    return facts


def _map_field_name(field: str) -> str | None:
    normalized = field.casefold()
    mapping = {
        "shaft_diameter_mm": "d1_mm",
        "d1": "d1_mm",
        "outer_diameter_mm": "D_mm",
        "housing_bore_diameter_mm": "D_mm",
        "width_mm": "b_mm",
        "b": "b_mm",
        "medium": "medium",
        "pressure_bar": "pressure_bar",
        "temperature_min_c": "temperature_min_c",
        "temperature_max_c": "temperature_max_c",
        "temperature_c": "temperature_max_c",
        "speed_rpm": "speed_rpm",
        "rpm": "speed_rpm",
        "application": "application",
        "asset": "application",
        "counterface_surface": "counterface_surface",
        "surface_roughness": "counterface_surface",
        "eccentricity": "eccentricity",
        "runout": "eccentricity",
    }
    return mapping.get(normalized)


def _facts_from_text(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    facts["d1_mm"] = _number_after(text, (r"\bd1\s*=\s*", r"wellendurchmesser\s*[:=]?\s*"))
    facts["D_mm"] = _number_after(text, (r"\bD\s*=\s*", r"\bau[ßs]endurchmesser\s*[:=]?\s*"))
    facts["b_mm"] = _number_after(text, (r"\bb\s*=\s*", r"\bbreite\s*[:=]?\s*"))
    facts["pressure_bar"] = _number_before_unit(text, "bar")
    facts["speed_rpm"] = _number_before_unit(text, "rpm")
    temp_min, temp_max = _temperature_range(text)
    facts["temperature_min_c"] = temp_min
    facts["temperature_max_c"] = temp_max
    facts["medium"] = _extract_labeled_text(text, ("medium",))
    facts["application"] = _extract_labeled_text(text, ("anlage / einbauort", "einbauort", "anwendung", "arbeitslage"))
    facts["counterface_surface"] = _extract_labeled_text(text, ("gegenlauffläche", "gegenlaufflaeche"))
    facts["eccentricity"] = _extract_labeled_text(text, ("außermittigkeit", "aussermittigkeit", "rundlauf"))
    if re.search(r"\bkeine\s+drehzahl\b", text, re.IGNORECASE | re.UNICODE):
        facts["speed_rpm"] = None
        facts["speed_explicitly_absent"] = True
    if re.search(r"\bkeine\s+au[ßs]ermittigkeit\b", text, re.IGNORECASE | re.UNICODE):
        facts["eccentricity"] = "keine"
    material_mentions = [term for term in ("NBR", "FKM", "PTFE", "EPDM", "HNBR", "FFKM") if re.search(rf"\b{term}\b", text, re.IGNORECASE)]
    if material_mentions:
        facts["material_mentions"] = material_mentions
    return {key: value for key, value in facts.items() if value not in ("", [], {})}


def _number_after(text: str, prefixes: tuple[str, ...]) -> float | None:
    for prefix in prefixes:
        match = re.search(prefix + r"(-?\d+(?:[,.]\d+)?)\s*(?:mm)?\b", text, re.IGNORECASE | re.UNICODE)
        if match:
            return _to_float(match.group(1))
    return None


def _number_before_unit(text: str, unit: str) -> float | None:
    match = re.search(rf"(-?\d+(?:[,.]\d+)?)\s*{re.escape(unit)}\b", text, re.IGNORECASE | re.UNICODE)
    return _to_float(match.group(1)) if match else None


def _temperature_range(text: str) -> tuple[float | None, float | None]:
    range_match = re.search(
        r"(-?\d+(?:[,.]\d+)?)\s*(?:bis|-)\s*\+?(-?\d+(?:[,.]\d+)?)\s*(?:°\s*c|°c|grad|c)\b",
        text,
        re.IGNORECASE | re.UNICODE,
    )
    if range_match:
        return _to_float(range_match.group(1)), _to_float(range_match.group(2))
    single = re.search(r"temperatur\s*[:=]?\s*(-?\d+(?:[,.]\d+)?)\s*(?:°\s*c|°c|grad|c)\b", text, re.IGNORECASE | re.UNICODE)
    if single:
        value = _to_float(single.group(1))
        return None, value
    return None, None


def _extract_labeled_text(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*[:=]\s*([^;\n.,]+(?:[,.]\d+)?)",
            text,
            re.IGNORECASE | re.UNICODE,
        )
        if match:
            return match.group(1).strip()
    return None


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "."))
    except ValueError:
        return None


def _rwdr_signals_from_facts(facts: dict[str, Any], missing_fields: list[str]) -> RWDRChallengeSignals:
    d1 = _maybe_float(facts.get("d1_mm"))
    rpm = _maybe_float(facts.get("speed_rpm"))
    v = round(math.pi * d1 * rpm / 60000, 2) if d1 is not None and rpm is not None else None
    signals = RWDRChallengeSignals(
        d1_mm=d1,
        D_mm=_maybe_float(facts.get("D_mm")),
        b_mm=_maybe_float(facts.get("b_mm")),
        medium=_maybe_str(facts.get("medium")),
        pressure_bar=_maybe_float(facts.get("pressure_bar")),
        temperature_min_c=_maybe_float(facts.get("temperature_min_c")),
        temperature_max_c=_maybe_float(facts.get("temperature_max_c")),
        speed_rpm=rpm,
        circumferential_speed_mps=v,
        application=_maybe_str(facts.get("application")),
        counterface_surface=_maybe_str(facts.get("counterface_surface")),
        eccentricity=_maybe_str(facts.get("eccentricity")),
        material_mentions=[str(item).upper() for item in list(facts.get("material_mentions") or [])],
        missing_critical_fields=_unique([_human_missing_field(item) for item in missing_fields]),
    )
    signals.review_flags = _rwdr_review_flags(signals, bool(facts.get("speed_explicitly_absent")))
    return signals


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return _to_float(str(value)) if value not in (None, "") else None


def _maybe_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _rwdr_review_flags(signals: RWDRChallengeSignals, speed_explicitly_absent: bool) -> list[str]:
    flags: list[str] = []
    medium = str(signals.medium or "").casefold()
    application = str(signals.application or "").casefold()
    if signals.d1_mm is not None and signals.d1_mm <= 10:
        flags.append("Sehr kleiner Wellendurchmesser: Fertigung, Montage, Rundlauf und Dichtlippentragbild sind kritisch zu prüfen.")
    if "druckluft" in medium:
        flags.append("Druckluft als Medium: Schmierung, Leckagepfad und Druck direkt an der Dichtlippe sind kritisch.")
    if "salzwasser" in medium or ("salz" in medium and "wasser" in medium):
        flags.append("Salzwasser: Korrosion, Feder-/Metallwerkstoff, Werkstoffverträglichkeit und Schmierung sind Review-Themen.")
    if signals.pressure_bar is not None and signals.pressure_bar >= 1:
        flags.append("Druckbelastung am RWDR muss gegen Bauform, Stützung und Druckdifferenz geprüft werden.")
    if speed_explicitly_absent or signals.speed_rpm is None:
        flags.append("Keine Drehzahl: klären, ob wirklich eine rotierende RWDR-Anwendung vorliegt.")
    if signals.circumferential_speed_mps is not None:
        flags.append("Umfangsgeschwindigkeit beeinflusst Wärme, Rundlauf, Oberfläche und Schmierfilm.")
    if "boot" in application:
        flags.append("Einbauort Boot: Wasser, Schmutz, Korrosion und Wechselbetrieb sind plausible Belastungen.")
    if signals.counterface_surface:
        flags.append("Gegenlaufflächenangabe muss mit Parameter und Einheit geklärt werden.")
    if signals.material_mentions:
        flags.append(f"{', '.join(signals.material_mentions)} ist Nutzerangabe oder Wunschmaterial, keine Empfehlung.")
    return _unique(flags)


def _rwdr_critical_points(signals: RWDRChallengeSignals) -> list[str]:
    return signals.review_flags[:6] or [
        "Der Fall ist als RWDR-Review zu strukturieren, bevor eine Herstellerbewertung sinnvoll ist."
    ]


def _rwdr_hypotheses(signals: RWDRChallengeSignals) -> list[str]:
    hypotheses: list[str] = []
    medium = str(signals.medium or "").casefold()
    if "druckluft" in medium:
        hypotheses.append("Es könnte eher ein pneumatischer oder statischer Dichtfall als eine klassische rotierende RWDR-Aufgabe sein.")
    if "salzwasser" in medium or ("salz" in medium and "wasser" in medium):
        hypotheses.append("Korrosion und mangelhafte Schmierung können den RWDR-Lastfall dominieren.")
    if signals.pressure_bar is not None and signals.pressure_bar >= 1:
        hypotheses.append("Der Druck kann eine druckbezogene RWDR-Bauformprüfung oder ein anderes Dichtkonzept erforderlich machen.")
    if signals.circumferential_speed_mps is not None and signals.circumferential_speed_mps >= 5:
        hypotheses.append("Die Geschwindigkeit ist relevant für Reibwärme, Oberfläche, Rundlauf und Schmierfilm.")
    if signals.material_mentions:
        hypotheses.append(f"{', '.join(signals.material_mentions)} bleibt ein Review-Thema aus der Nutzervorgabe, keine Materialentscheidung.")
    return _unique(hypotheses)


def _rwdr_counter_indicators(signals: RWDRChallengeSignals) -> list[str]:
    risks: list[str] = []
    if signals.speed_rpm is None:
        risks.append("Ohne Drehzahl oder Bewegungsart ist RWDR als Dichtprinzip nicht belastbar eingeordnet.")
    if signals.pressure_bar is not None and signals.pressure_bar >= 1:
        risks.append("Druckangabe ist nur verwertbar, wenn sie als Druckdifferenz direkt über der Dichtung verstanden wird.")
    if signals.counterface_surface:
        risks.append("Gegenlauffläche 0,2 ist ohne Parameter und Einheit kein belastbarer Oberflächenwert.")
    if signals.d1_mm is not None and signals.d1_mm <= 10:
        risks.append("Bei sehr kleiner Welle können Montage- und Toleranzeffekte den Fall stärker prägen als die Werkstofffrage.")
    return _unique(risks)


def _rwdr_missing_blockers(signals: RWDRChallengeSignals) -> list[str]:
    blockers = list(signals.missing_critical_fields)
    if signals.speed_rpm is None:
        blockers.append("Bewegungsart/Drehzahl der Welle")
    if not signals.medium:
        blockers.append("Medium an der Dichtlippe")
    if signals.pressure_bar is None:
        blockers.append("Druckdifferenz direkt über der Dichtung")
    if not signals.counterface_surface:
        blockers.append("Gegenlauffläche mit Parameter und Einheit")
    return _unique(blockers)[:6]


def _rwdr_next_best_question(signals: RWDRChallengeSignals) -> str:
    medium = str(signals.medium or "").casefold()
    if "druckluft" in medium and (signals.speed_rpm is None or (signals.d1_mm is not None and signals.d1_mm <= 10)):
        return (
            "Ist das tatsächlich eine rotierende Welle mit Radialwellendichtring oder eher eine pneumatische/"
            "statische Abdichtung beziehungsweise Führungs-/Kolbendichtung?"
        )
    if ("salzwasser" in medium or ("salz" in medium and "wasser" in medium)) and signals.pressure_bar is not None:
        pressure = _format_number(signals.pressure_bar)
        surface = signals.counterface_surface or "0,2"
        return (
            f"Sind die {pressure} bar als dauerhafte Druckdifferenz direkt über der Dichtung zu verstehen, "
            f"und welche Gegenlaufflächenangabe ist mit {surface} gemeint - Ra in µm?"
        )
    return "Welche Angabe blockiert die Herstellerbewertung aktuell am stärksten: Druckdifferenz, Drehzahl/Bewegung oder Gegenlauffläche?"


def _rwdr_computed_signals(signals: RWDRChallengeSignals) -> list[str]:
    values: list[str] = []
    if signals.d1_mm is not None and signals.D_mm is not None and signals.b_mm is not None:
        values.append(f"RWDR-Geometrie erkannt: d1={_format_number(signals.d1_mm)} mm, D={_format_number(signals.D_mm)} mm, b={_format_number(signals.b_mm)} mm.")
    if signals.pressure_bar is not None:
        values.append(f"Druck-Review: {_format_number(signals.pressure_bar)} bar direkt an der Dichtung nur verwertbar, wenn Referenz und Druckdifferenz klar sind.")
    if signals.circumferential_speed_mps is not None:
        values.append(
            "Umfangsgeschwindigkeit: "
            f"v = pi x d1 x rpm / 60000 = ca. {_format_number(signals.circumferential_speed_mps)} m/s."
        )
    elif signals.d1_mm is not None and signals.speed_rpm is None:
        values.append("Umfangsgeschwindigkeit ist nicht berechenbar, weil keine Drehzahl vorliegt.")
    if signals.temperature_min_c is not None or signals.temperature_max_c is not None:
        temp = (
            f"{_format_number(signals.temperature_min_c)} bis {_format_number(signals.temperature_max_c)} °C"
            if signals.temperature_min_c is not None and signals.temperature_max_c is not None
            else f"bis {_format_number(signals.temperature_max_c)} °C"
        )
        values.append(f"Temperaturfenster als Arbeitsstand: {temp}.")
    return values


def _short_judgement(plan: TechnicalCaseChallengePlan) -> str:
    if plan.detected_domain == "rwdr":
        return (
            "Das ist ein RWDR-Review-Fall mit mehreren offenen Bewertungsachsen. "
            "Die Angaben reichen für eine strukturierte Herstellerbewertungsvorbereitung, aber nicht für eine Freigabe."
        )
    return "Das ist ein technischer Dichtungsfall für eine strukturierte Vorprüfung, nicht für eine finale Entscheidung."


def _bullet_lines(items: list[str]) -> list[str]:
    clean = _unique(items)
    return [f"- {item}" for item in clean] if clean else ["- Kein belastbarer Punkt aus den vorliegenden Angaben ableitbar."]


def _human_missing_field(field: str) -> str:
    mapping = {
        "pressure_bar": "Druckdifferenz direkt über der Dichtung",
        "temperature_c": "Temperaturbereich",
        "speed_rpm": "Drehzahl/Bewegungsart",
        "shaft_diameter_mm": "Wellendurchmesser d1",
        "medium": "Medium an der Dichtlippe",
        "counterface_surface": "Gegenlauffläche mit Parameter und Einheit",
    }
    return mapping.get(str(field), str(field))


def _forbidden_claims() -> list[str]:
    return [
        "final_engineering_release",
        "material_release",
        "product_recommendation",
        "manufacturer_recommendation",
        "final_suitability_claim",
    ]


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in items if str(item or "").strip()))


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")
