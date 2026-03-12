"""Bounded RWDR field parser for stage-driven dialog intake.

This module is intentionally narrow: it only maps the currently requested field
to a safely structured patch. It must not grow into generic free-text
extraction or reimplement domain decisions.
"""

from __future__ import annotations

import re

from app.agent.domain.rwdr import RWDRConfidenceField, RWDRSelectorInputPatchDTO

_UNKNOWN_PATTERNS = ("weiß nicht", "weiss nicht", "unknown", "unklar", "keine ahnung")
_NUMBER_WITH_UNIT = re.compile(r"(\d+(?:[.,]\d+)?)")

FIELD_QUESTIONS: dict[RWDRConfidenceField, str] = {
    "motion_type": "Wie bewegt sich die Welle? Antwort moeglich: eine Richtung, Richtungswechsel, Schwenken, linearer Hub.",
    "shaft_diameter_mm": "Wie gross ist der Wellendurchmesser in mm?",
    "max_speed_rpm": "Wie hoch ist die maximale Drehzahl in U/min?",
    "pressure_profile": "Welches Druckprofil liegt an? Antwort moeglich: drucklos, bis 0,5 bar, konstanter Druck ueber 0,5 bar, pulsierend, Vakuum.",
    "inner_lip_medium_scenario": "Was liegt direkt an der inneren Dichtlippe an? Antwort moeglich: Oelbad, Spritzoel, Fett, Wasser, Trockenlauf.",
    "maintenance_mode": "Wird auf neuer oder gebrauchte Welle montiert?",
    "external_contamination_class": "Wie stark ist der Aussenbereich verschmutzt? Antwort moeglich: sauber, Spritzwasser/Staub, Schlamm/Hochdruck/abrasiv.",
    "available_width_mm": "Wie viel axiale Breite steht in mm zur Verfuegung?",
    "installation_over_edges_flag": "Muss die Dichtung ueber Gewinde, Nut oder scharfe Kanten geschoben werden? Antwort: ja oder nein.",
    "vertical_shaft_flag": "Ist die Welle vertikal angeordnet? Antwort: ja oder nein.",
    "medium_level_relative_to_seal": "Liegt das Medium oberhalb, unterhalb oder auf Hoehe der Dichtstelle?",
}


def next_rwdr_question(next_field: RWDRConfidenceField | None) -> str:
    if next_field is None:
        return "RWDR-Daten sind noch unvollstaendig."
    return FIELD_QUESTIONS[next_field]


def parse_rwdr_patch_for_field(
    next_field: RWDRConfidenceField | None,
    message: str,
) -> RWDRSelectorInputPatchDTO | None:
    if next_field is None:
        return None

    normalized = " ".join(message.strip().lower().split())
    if not normalized or any(pattern in normalized for pattern in _UNKNOWN_PATTERNS):
        return None

    if next_field == "motion_type":
        if "linear" in normalized or "hub" in normalized or "rein raus" in normalized:
            return RWDRSelectorInputPatchDTO(motion_type="linear_stroke", confidence={"motion_type": "known"})
        if "richtungswechsel" in normalized or "revers" in normalized or "beide richtungen" in normalized:
            return RWDRSelectorInputPatchDTO(motion_type="reversing_rotation", confidence={"motion_type": "known"})
        if "schwenk" in normalized or "oszill" in normalized:
            return RWDRSelectorInputPatchDTO(motion_type="small_angle_oscillation", confidence={"motion_type": "known"})
        if "eine richtung" in normalized or "nur rechts" in normalized or "nur links" in normalized:
            return RWDRSelectorInputPatchDTO(motion_type="single_direction_rotation", confidence={"motion_type": "known"})
        return None

    if next_field in {"shaft_diameter_mm", "available_width_mm", "max_speed_rpm"}:
        match = _NUMBER_WITH_UNIT.search(normalized)
        if not match:
            return None
        value = float(match.group(1).replace(",", "."))
        if next_field == "shaft_diameter_mm" and ("mm" in normalized or normalized == match.group(1)):
            return RWDRSelectorInputPatchDTO(shaft_diameter_mm=value, confidence={"shaft_diameter_mm": "known"})
        if next_field == "available_width_mm" and ("mm" in normalized or normalized == match.group(1)):
            return RWDRSelectorInputPatchDTO(available_width_mm=value, confidence={"available_width_mm": "known"})
        if next_field == "max_speed_rpm" and (
            "u/min" in normalized or "rpm" in normalized or "min-1" in normalized or normalized == match.group(1)
        ):
            return RWDRSelectorInputPatchDTO(max_speed_rpm=value, confidence={"max_speed_rpm": "known"})
        return None

    if next_field == "pressure_profile":
        if "vakuum" in normalized:
            return RWDRSelectorInputPatchDTO(pressure_profile="vacuum", confidence={"pressure_profile": "known"})
        if "puls" in normalized or "druckschlag" in normalized:
            return RWDRSelectorInputPatchDTO(pressure_profile="pulsating_pressure", confidence={"pressure_profile": "known"})
        if "drucklos" in normalized or "entl" in normalized:
            return RWDRSelectorInputPatchDTO(pressure_profile="pressureless_vented", confidence={"pressure_profile": "known"})
        if "0,5" in normalized or "0.5" in normalized:
            if "bis" in normalized or "leicht" in normalized or "unter" in normalized:
                return RWDRSelectorInputPatchDTO(pressure_profile="light_pressure_upto_0_5_bar", confidence={"pressure_profile": "known"})
            if "ueber" in normalized or "über" in normalized or "konstant" in normalized:
                return RWDRSelectorInputPatchDTO(pressure_profile="constant_pressure_above_0_5_bar", confidence={"pressure_profile": "known"})
        if "konstant" in normalized or "ueberdruck" in normalized or "überdruck" in normalized:
            return RWDRSelectorInputPatchDTO(pressure_profile="constant_pressure_above_0_5_bar", confidence={"pressure_profile": "known"})
        return None

    if next_field == "inner_lip_medium_scenario":
        if "oelbad" in normalized or "ölbad" in normalized or "sumpf" in normalized:
            return RWDRSelectorInputPatchDTO(inner_lip_medium_scenario="oil_bath", confidence={"inner_lip_medium_scenario": "known"})
        if "spritz" in normalized or "oelnebel" in normalized or "ölnebel" in normalized:
            return RWDRSelectorInputPatchDTO(inner_lip_medium_scenario="splash_oil", confidence={"inner_lip_medium_scenario": "known"})
        if "fett" in normalized:
            return RWDRSelectorInputPatchDTO(inner_lip_medium_scenario="grease", confidence={"inner_lip_medium_scenario": "known"})
        if "wasser" in normalized or "waessrig" in normalized or "wässrig" in normalized:
            return RWDRSelectorInputPatchDTO(inner_lip_medium_scenario="water_or_aqueous", confidence={"inner_lip_medium_scenario": "known"})
        if "trocken" in normalized or "luft" in normalized:
            return RWDRSelectorInputPatchDTO(inner_lip_medium_scenario="dry_run_or_air", confidence={"inner_lip_medium_scenario": "known"})
        return None

    if next_field == "maintenance_mode":
        if "gebraucht" in normalized or "gelaufen" in normalized or "altwelle" in normalized:
            return RWDRSelectorInputPatchDTO(maintenance_mode="used_shaft", confidence={"maintenance_mode": "known"})
        if "neu" in normalized or "neuwelle" in normalized:
            return RWDRSelectorInputPatchDTO(maintenance_mode="new_shaft", confidence={"maintenance_mode": "known"})
        return None

    if next_field == "external_contamination_class":
        if "schlamm" in normalized or "hochdruck" in normalized or "abrasiv" in normalized:
            return RWDRSelectorInputPatchDTO(
                external_contamination_class="mud_high_pressure_abrasive",
                confidence={"external_contamination_class": "known"},
            )
        if "spritzwasser" in normalized or "staub" in normalized or "outdoor" in normalized:
            return RWDRSelectorInputPatchDTO(
                external_contamination_class="splash_water_or_outdoor_dust",
                confidence={"external_contamination_class": "known"},
            )
        if "sauber" in normalized or "raumstaub" in normalized or "clean" in normalized:
            return RWDRSelectorInputPatchDTO(
                external_contamination_class="clean_room_dust",
                confidence={"external_contamination_class": "known"},
            )
        return None

    if next_field in {"installation_over_edges_flag", "vertical_shaft_flag"}:
        positive = {"ja", "yes"}
        negative = {"nein", "no"}
        is_true = normalized in positive or " ja" in f" {normalized}" or "vertikal" in normalized
        is_false = normalized in negative or "horizontal" in normalized
        if next_field == "installation_over_edges_flag":
            if "gewinde" in normalized or "nut" in normalized or "kante" in normalized:
                is_true = True
        if is_true and not is_false:
            return RWDRSelectorInputPatchDTO(
                **{next_field: True, "confidence": {next_field: "known"}}  # type: ignore[arg-type]
            )
        if is_false and not is_true:
            return RWDRSelectorInputPatchDTO(
                **{next_field: False, "confidence": {next_field: "known"}}  # type: ignore[arg-type]
            )
        return None

    if next_field == "medium_level_relative_to_seal":
        if "oberhalb" in normalized or "darueber" in normalized or "darüber" in normalized:
            return RWDRSelectorInputPatchDTO(
                medium_level_relative_to_seal="above",
                confidence={"medium_level_relative_to_seal": "known"},
            )
        if "unterhalb" in normalized or "darunter" in normalized:
            return RWDRSelectorInputPatchDTO(
                medium_level_relative_to_seal="below",
                confidence={"medium_level_relative_to_seal": "known"},
            )
        if "gleich" in normalized or "auf hoehe" in normalized or "auf höhe" in normalized or "niveau" in normalized:
            return RWDRSelectorInputPatchDTO(
                medium_level_relative_to_seal="at_level",
                confidence={"medium_level_relative_to_seal": "known"},
            )
        return None

    return None
