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


def confirm_recommendation_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Ask the user whether a concrete recommendation should be generated.
    """
    parameters = state.parameters.as_dict()
    param_lines = [
        f"{PARAMETER_LABELS.get(key, key.replace('_', ' ').capitalize())}: {value}"
        for key, value in parameters.items()
        if value not in (None, "", [])
    ]
    coverage = max(0.0, min(1.0, getattr(state, "coverage_score", 0.0)))
    gaps = ", ".join(state.coverage_gaps or [])

    details = ", ".join(param_lines) if param_lines else "bisher noch keine technischen Angaben"
    gaps_text = f" Fehlende Werte: {gaps}." if gaps else ""
    percentage = f"{coverage * 100:.0f}%"

    question = (
        f"Ich habe aktuell {details} (Coverage: {percentage}){gaps_text}. "
        "Möchtest du nun eine konkrete Empfehlung für Material, Profil und Sicherheitsbox erhalten, "
        "oder sollen wir zuerst weitere offene Punkte klären?"
    )

    return {
        "final_text": question,
        "phase": "confirm",
        "last_node": "confirm_recommendation_node",
    }
