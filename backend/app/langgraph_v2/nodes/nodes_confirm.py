from __future__ import annotations

from typing import Dict

from app.langgraph_v2.state import SealAIState

PARAMETER_LABELS: Dict[str, str] = {
    "medium": "Medium",
    "pressure_bar": "Druck (bar)",
    "p_min": "Min. Druck (bar)",
    "p_max": "Max. Druck (bar)",
    "temperature_C": "Betriebstemperatur (°C)",
    "temperature_min": "Min. Temp (°C)",
    "temperature_max": "Max. Temp (°C)",
    "speed_rpm": "Drehzahl (rpm)",
    "speed_linear": "Geschw. (m/s)",
    "shaft_diameter": "Wellen-Ø (mm)",
    "d_shaft_nominal": "Nenn-Ø Welle (mm)",
    "housing_diameter": "Gehäuse-Ø (mm)",
    "d_bore_nominal": "Bohrungs-Ø (mm)",
    "dynamic_runout": "Wellenschlag (dyn)",
    "mounting_offset": "Montageversatz (mm)",
}

_CORE_FIELDS = ["medium", "temperature_C", "pressure_bar", "speed_rpm", "shaft_diameter"]
_READY_THRESHOLD = 0.8


_QUESTION_BANK: Dict[str, Dict[str, str]] = {
    "medium": {
        "q": "Welches Medium (inkl. Additive/Verunreinigung)?",
        "w": "Warum: steuert Werkstoffverträglichkeit und Schmierung.",
    },
    "temperature_C": {
        "q": "Welcher Temperaturbereich (min/max oder Betrieb)?",
        "w": "Warum: entscheidet über Werkstofffenster, Setzverhalten und Wärmeeintrag.",
    },
    "pressure_bar": {
        "q": "Welcher Druck bzw. Differenzdruck Δp (Druckseite)?",
        "w": "Warum: beeinflusst Leckage, Lippenbelastung und ggf. Stützelemente.",
    },
    "speed_rpm": {
        "q": "Welcher Drehzahlbereich (min/max, Dauer/Spitzen)?",
        "w": "Warum: bestimmt Wärmeeintrag, Verschleiß und Profilwahl.",
    },
    "shaft_diameter": {
        "q": "Welcher Wellen-Ø inkl. Toleranz/Material/Oberfläche?",
        "w": "Warum: Einbaumaß/Pressung, Gegenlauffläche und Standardabmessungen.",
    },
}


def _missing_core_fields(parameters: Dict[str, object], coverage_gaps: list[str]) -> list[str]:
    if coverage_gaps:
        missing = [key for key in _CORE_FIELDS if key in coverage_gaps]
        if missing:
            return missing
    missing: list[str] = []
    for key in _CORE_FIELDS:
        value = parameters.get(key)
        if value in (None, ""):
            missing.append(key)
    return missing


def confirm_recommendation_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Abnahme-Checkpoint: GO/NO-GO basierend auf Coverage + Kernfeldern.
    """
    parameters = state.parameters.as_dict()
    param_lines = [
        f"{PARAMETER_LABELS.get(key, key.replace('_', ' ').capitalize())}: {value}"
        for key, value in parameters.items()
        if value not in (None, "", [])
    ]
    coverage = max(0.0, min(1.0, float(getattr(state, "coverage_score", 0.0) or 0.0)))
    coverage_gaps = list(state.coverage_gaps or [])
    missing_core = _missing_core_fields(parameters, coverage_gaps)

    go = bool(coverage >= _READY_THRESHOLD and not missing_core)

    details = ", ".join(param_lines) if param_lines else "bisher noch keine technischen Angaben"
    percentage = f"{coverage * 100:.0f}%"

    status_text = "GO" if go else "NO-GO"
    reasons: list[str] = []
    if go:
        reasons.append(f"Coverage: {percentage} und alle Kernfelder sind vorhanden.")
        reasons.append("Freigabe ist vorläufig; Validierung im Versuch bleibt erforderlich.")
    else:
        if missing_core:
            missing_labels = ", ".join(PARAMETER_LABELS.get(k, k) for k in missing_core)
            reasons.append(f"Kernfelder fehlen: {missing_labels}.")
        if coverage < _READY_THRESHOLD:
            reasons.append(f"Coverage: {percentage} < {_READY_THRESHOLD:.0%} (vorläufig).")

    checklist = [
        "Medienverträglichkeit und Schmierung (inkl. Additive).",
        "Temperaturfenster/thermische Belastung (Wärmeeintrag, Setzverhalten).",
        "Druck-/Δp-Situation und Lippenbelastung (falls relevant).",
        "Drehzahl/Umfangsgeschwindigkeit (Verschleiß/Wärme).",
        "Gegenlauffläche und Einbausituation (Ø/Toleranz/Oberfläche/Montage).",
        "Standzeit-/Dichtheitsprüfung unter repräsentativen Bedingungen.",
    ]

    questions: list[str] = []
    if not go:
        for key in missing_core[:3]:
            spec = _QUESTION_BANK.get(key) or {}
            q = spec.get("q") or f"Kannst du {key} ergänzen?"
            w = spec.get("w") or "Warum: reduziert die größte Unsicherheit in der Auslegung."
            questions.append(f"- {q} {w}")

    lines: list[str] = []
    lines.append("**Abnahme-Checkpoint (vorläufig)**")
    lines.append(f"- Status: {status_text}")
    lines.append(f"- Aktuelle Datenbasis: {details} (Coverage: {percentage})")
    lines.append("- Begründung:")
    for reason in reasons[:2]:
        lines.append(f"  - {reason}")
    lines.append("- Checkliste (Absicherung):")
    for item in checklist:
        lines.append(f"  - {item}")
    if questions:
        lines.append("- Top-Rückfragen (priorisiert):")
        lines.extend(questions)
    else:
        lines.append("- Hinweis: Bitte im Versuch/Prototyp absichern (Checkliste oben).")

    final_text = "\n".join(lines).strip()

    return {
        "final_text": final_text,
        "recommendation_go": go,
        "phase": "confirm",
        "last_node": "confirm_recommendation_node",
    }
