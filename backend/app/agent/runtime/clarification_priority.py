from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.agent.domain.medium_registry import is_medium_placeholder_value
from app.agent.runtime.medium_status_text import (
    medium_status_primary_question,
    render_open_point_label,
)
from app.agent.state.models import GovernedSessionState


@dataclass(frozen=True)
class ClarificationPriority:
    focus_key: str
    question: str
    reason: str
    open_point_label: str


_ROTARY_CONTEXT_RE = re.compile(
    r"\b(rotierend\w*|rotary|radialwellendichtring|rwdr|welle|shaft)\b",
    re.IGNORECASE,
)
_LINEAR_CONTEXT_RE = re.compile(
    r"\b(lineare?\s+beweg\w*|linear\w*|hubbeweg\w*|hubstange|kolbenstange)\b",
    re.IGNORECASE,
)
_APPLICATION_CONTEXT_RE = re.compile(
    r"\b(einbau\w*|anwendung\w*|welle|shaft|pumpe\w*|ventil\w*|flansch\w*|gehaeuse|gehäuse|statisch\w*|rotierend\w*|linear\w*|hubstange|kolbenstange|zylinder)\b",
    re.IGNORECASE,
)
_GEOMETRY_CONTEXT_RE = re.compile(
    r"\b(geometr\w*|bauform\w*|nut\w*|bohrung\w*|flansch\w*|gehaeuse|gehäuse|dichtsitz\w*|einbauraum\w*)\b",
    re.IGNORECASE,
)
_CLEARANCE_CONTEXT_RE = re.compile(
    r"\b(spalt\w*|spiel\w*|toleranz\w*|clearance|extrusion\w*)\b",
    re.IGNORECASE,
)
_SURFACE_CONTEXT_RE = re.compile(
    r"\b(oberflaech\w*|oberfläch\w*|rauheit\w*|gegenlauf\w*|laufpartner\w*|huelse|hülse)\b",
    re.IGNORECASE,
)
_COUNTERFACE_MATERIAL_RE = re.compile(
    r"\b(gegenlaufpartner\w*|gegenlaufwerkstoff\w*|gegenlaufmaterial\w*|wellenwerkstoff\w*|buchse\w*)\b",
    re.IGNORECASE,
)

_QUESTION_META: dict[str, tuple[str, str]] = {
    "application_context": (
        "Wie ist die Einbausituation bei Ihnen ausgeführt?",
        "Mit dem Medium allein ist die Anwendung noch nicht ausreichend eingegrenzt; zuerst brauche ich den Anwendungs- und Bewegungsanker.",
    ),
    "speed_rpm": (
        "Welche Drehzahl liegt ungefähr an?",
        "Bei einer rotierenden Welle ist die Drehzahl einer der wichtigsten Kernparameter fuer die technische Einengung.",
    ),
    "sealing_type": (
        "Um welchen Dichtungstyp oder welches Dichtprinzip geht es?",
        "Ohne Dichtungstyp bleibt der technische Loesungsraum zu breit fuer eine belastbare Vorauswahl.",
    ),
    "duty_profile": (
        "Ist der Betrieb kontinuierlich, intermittierend oder nur gelegentlich?",
        "Das Betriebsprofil entscheidet mit, wie robust die Vorauswahl ausgelegt werden muss.",
    ),
    "pressure_direction": (
        "Aus welcher Richtung wirkt der Druck an der Dichtung?",
        "Die Druckrichtung beeinflusst Dichtprinzip und Belastungsfall.",
    ),
    "contamination": (
        "Gibt es Schmutz, Partikel oder abrasive Anteile im Umfeld oder Medium?",
        "Partikel und abrasive Anteile koennen Werkstoff- und Bauartgrenzen frueh verschieben.",
    ),
    "contamination_condition": (
        "Gibt es Staub, Schmutz oder abrasive Partikel an der Dichtstelle?",
        "Verschmutzung und Abrasion sind bei RWDR wichtige Pruefgroessen fuer Dichtlippe und Gegenlaufflaeche.",
    ),
    "tolerances": (
        "Gibt es Angaben zu Rundlauf, Exzentrizitaet, Spalt oder Toleranzen?",
        "Toleranzen und Rundlauf bestimmen, wie belastbar die Dichtstelle technisch einzuordnen ist.",
    ),
    "industry": (
        "In welcher Branche oder in welchem regulierten Umfeld wird die Dichtung eingesetzt?",
        "Der Branchenkontext kann zusaetzliche technische und regulatorische Pruefpunkte ausloesen.",
    ),
    "compliance": (
        "Welche regulatorischen Anforderungen gelten hier, zum Beispiel FDA, ATEX oder eine Normvorgabe?",
        "Regulatorische Anforderungen duerfen nicht als technischer Fit mitgeraten werden.",
    ),
    "medium_qualifiers": (
        "Welche Mediumdetails sind bekannt, zum Beispiel Konzentration, Chloride oder Feststoffanteile?",
        "Diese Mediumdetails koennen die Werkstoff- und Korrosionsgrenzen entscheidend veraendern.",
    ),
    "concentration": (
        "Welche genaue Konzentration oder Zusammensetzung liegt an der Dichtung an?",
        "Das ist wichtig, weil die Werkstoffvertraeglichkeit stark von Medium, Konzentration und Temperatur abhaengt.",
    ),
    "ph": (
        "Welcher pH-Wert oder pH-Bereich liegt am Medium an?",
        "Der pH-Kontext kann den Werkstoff-Precheck bei Saeuren, Laugen und Reinigungsmedien deutlich verschieben.",
    ),
    "material": (
        "Welcher Werkstoff oder welche Werkstofffamilie ist vorhanden oder geplant?",
        "Ohne Werkstoffangabe kann der Material/Medium-Precheck keine belastbare Pruefhypothese bilden.",
    ),
    "compliance_evidence": (
        "Welcher konkrete Nachweis liegt fuer die regulatorische Anforderung vor, zum Beispiel Datenblatt, Zertifikat oder Herstellerbestaetigung?",
        "Regulatorische Anforderungen duerfen nicht aus einer Material-/Medium-Orientierung abgeleitet werden.",
    ),
    "shaft_diameter_mm": (
        "Wie groß ist der Wellendurchmesser ungefähr?",
        "Bei einer rotierenden Welle brauche ich den Wellendurchmesser, um die technische Richtung sauber einzugrenzen.",
    ),
    "installation": (
        "Wie ist die Einbausituation bei Ihnen genau ausgeführt?",
        "Die Einbausituation bestimmt, wie ich den bereits erkannten Anwendungsfall technisch einordne.",
    ),
    "geometry_context": (
        "Welche Geometrie oder vorhandene Bauform liegt an der Dichtstelle vor?",
        "Die Geometrie grenzt den Dichtprinzipraum und den Requirement-Class-Raum deutlich ein.",
    ),
    "clearance_gap_mm": (
        "Mit welchem Spalt- oder Toleranzbereich muessen wir an der Dichtstelle rechnen?",
        "Spalt und Toleranzen entscheiden frueh, ob der technische Loesungsraum tragfaehig bleibt.",
    ),
    "counterface_surface": (
        "Wie sehen Gegenlaufpartner und Oberflaechen an der Dichtstelle aus?",
        "Oberflaeche und Gegenlaufpartner beeinflussen Dichtverhalten und Verschleiss stark mit.",
    ),
    "counterface_surface_condition": (
        "Wie ist die Gegenlaufflaeche der Welle ausgefuehrt bzw. in welchem Zustand ist sie?",
        "Das ist bei einem RWDR wichtig, weil die Dichtlippe direkt auf dieser Flaeche laeuft.",
    ),
    "shaft_roughness_ra_um": (
        "Welche Rauheit Ra hat die Gegenlaufflaeche der Welle?",
        "Die Rauheit ist bei RWDR ein zentraler Vorcheck-Wert fuer Reibung, Schmierfilm und Verschleiss.",
    ),
    "shaft_hardness_hrc": (
        "Welche Haerte hat die Gegenlaufflaeche, idealerweise in HRC?",
        "Die Haerte begrenzt bei RWDR die Belastbarkeit der Laufflaeche gegen Einlaufen und Verschleiss.",
    ),
    "runout_mm": (
        "Welcher Rundlauf oder Wellenschlag liegt an der Welle an?",
        "Rundlauf/Wellenschlag bestimmt, wie stark die RWDR-Dichtlippe dynamisch ausgelenkt wird.",
    ),
    "eccentricity_mm": (
        "Welche Exzentrizitaet liegt an der Welle an?",
        "Exzentrizitaet ist bei RWDR eine relevante dynamische Belastungsgroesse.",
    ),
    "axial_movement_mm": (
        "Welche axiale Bewegung oder welcher axiale Versatz der Welle ist zu erwarten?",
        "Axiale Bewegung kann die Lage der Dichtlippe und die Beanspruchung der Laufflaeche veraendern.",
    ),
    "lubrication_condition": (
        "Wie ist die Schmierung an der Dichtlippe: geschmiert, zeitweise trocken oder Mangelschmierung?",
        "Der Schmierzustand entscheidet bei RWDR wesentlich ueber Waerme, Reibung und Verschleiss.",
    ),
    "installation_space_summary": (
        "Welcher Einbauraum oder welche vorhandene Nut-/Gehaeusesituation liegt vor?",
        "Der Einbauraum begrenzt bei RWDR Bauform, Montage und Nebenfunktionen.",
    ),
    "counterface_material": (
        "Aus welchem Werkstoff besteht der Gegenlaufpartner an der Dichtstelle?",
        "Der Werkstoff des Gegenlaufpartners bestimmt zusammen mit Oberflaeche und Medium die tribologische Grenze.",
    ),
    "pressure_bar": (
        "Wie hoch ist der Betriebsdruck ungefähr?",
        "Der Druck bestimmt, welche Belastung die Dichtung sicher aufnehmen muss.",
    ),
    "pressure_at_seal_bar": (
        "Welcher Druck liegt direkt an der Dichtung an?",
        "Für die technische Einordnung zählt der tatsächlich an der Dichtstelle anliegende Druck, nicht automatisch der Systemdruck.",
    ),
    "pressure_delta_bar": (
        "Welcher Differenzdruck liegt über der Dichtung an?",
        "Der Differenzdruck beschreibt die wirksame Druckbelastung über der Dichtung.",
    ),
    "temperature_c": (
        "In welchem Temperaturbereich arbeiten Sie?",
        "Die Temperatur grenzt Werkstoff und Einsatzfenster ein.",
    ),
}


def _text(value: str | None) -> str:
    return str(value or "").strip()


def _nested_text(container: object, key: str) -> str:
    if isinstance(container, dict):
        return _text(container.get(key))
    return _text(getattr(container, key, None))


def _has_value(state: GovernedSessionState, field_name: str) -> bool:
    asserted = state.asserted.assertions.get(field_name)
    if asserted is not None and asserted.asserted_value is not None:
        if field_name == "medium" and is_medium_placeholder_value(
            str(asserted.asserted_value)
        ):
            return False
        return True
    normalized = state.normalized.parameters.get(field_name)
    if normalized is None or normalized.value is None:
        return False
    if field_name == "medium" and is_medium_placeholder_value(str(normalized.value)):
        return False
    return True


def _observed_unasserted_value(
    state: GovernedSessionState, field_name: str
) -> object | None:
    asserted = state.asserted.assertions.get(field_name)
    if asserted is not None and asserted.asserted_value is not None:
        return None
    normalized = state.normalized.parameters.get(field_name)
    if normalized is None or normalized.value is None:
        return None
    return normalized.value


def _display_value(value: object) -> object:
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value


def _pressure_interpretation(state: GovernedSessionState) -> str:
    normalized = state.normalized.parameters.get("pressure_bar")
    if normalized is None:
        return ""
    engineering_value = getattr(normalized, "engineering_value", None)
    return str(getattr(engineering_value, "interpretation", "") or "").strip()


def _pressure_value(state: GovernedSessionState, field_name: str) -> object | None:
    asserted = state.asserted.assertions.get(field_name)
    if asserted is not None and asserted.asserted_value is not None:
        return asserted.asserted_value
    normalized = state.normalized.parameters.get(field_name)
    if normalized is not None and normalized.value is not None:
        return normalized.value
    return None


def _state_value(state: GovernedSessionState, field_name: str) -> object | None:
    asserted = state.asserted.assertions.get(field_name)
    if asserted is not None and asserted.asserted_value is not None:
        return asserted.asserted_value
    normalized = state.normalized.parameters.get(field_name)
    if normalized is not None and normalized.value is not None:
        return normalized.value
    return None


def _has_design_pressure_value(state: GovernedSessionState) -> bool:
    return _has_value(state, "pressure_at_seal_bar") or _has_value(
        state, "pressure_delta_bar"
    )


def _pressure_role_priority(
    state: GovernedSessionState,
) -> ClarificationPriority | None:
    if _has_design_pressure_value(state):
        return None

    ambiguous = _pressure_value(state, "ambiguous_pressure_bar")
    if ambiguous is None:
        ambiguous = _observed_unasserted_value(state, "pressure_bar")
    if ambiguous is not None:
        display = _display_value(ambiguous)
        return ClarificationPriority(
            focus_key="pressure_bar",
            question=(
                f"Sind die {display} bar der Systemdruck, der Druck direkt an der Dichtung "
                "oder der Druckunterschied beziehungsweise Differenzdruck ueber der Dichtung?"
            ),
            reason=(
                "Das ist wichtig, weil RWDR, Gleitringdichtung oder andere Dichtprinzipien "
                "je nach tatsaechlich anliegendem Dichtungsdruck unterschiedlich bewertet werden."
            ),
            open_point_label=f"Druckrolle klaeren ({display} bar erkannt)",
        )

    system_pressure = _pressure_value(state, "pressure_system_bar")
    if system_pressure is not None:
        display = _display_value(system_pressure)
        return ClarificationPriority(
            focus_key="pressure_at_seal_bar",
            question=(
                f"Liegt der Systemdruck von {display} bar auch direkt an der Dichtung an, "
                "oder ist der Dichtungsdruck durch Einbausituation oder Entlastung niedriger?"
            ),
            reason=(
                "Der Systemdruck ist bekannt, aber fuer die Auslegung zaehlt die Druckbelastung "
                "direkt an der Dichtstelle."
            ),
            open_point_label="Druck an der Dichtstelle klaeren",
        )
    return None


def _observed_confirmation_priority(
    state: GovernedSessionState,
    field_name: str,
) -> ClarificationPriority | None:
    if field_name not in {"pressure_bar"}:
        return None
    pressure_role = _pressure_role_priority(state)
    if pressure_role is not None:
        return pressure_role
    value = _observed_unasserted_value(state, field_name)
    if value is None:
        return None
    display = _display_value(value)
    if field_name == "pressure_bar":
        interpretation = _pressure_interpretation(state)
        if interpretation in {"gauge", "absolute", "differential"}:
            return None
        return ClarificationPriority(
            focus_key=field_name,
            question=(
                f"Ich habe {display} bar erkannt; meinst du damit den Druck direkt an der Dichtung, "
                "den Systemdruck oder den Druckunterschied ueber der Dichtung?"
            ),
            reason=(
                "Der Druckwert ist da, aber der Bezug fehlt, damit fuer die Anfrage klar ist, "
                "welcher Druck wirklich an der Dichtung ankommt."
            ),
            open_point_label=f"Druckbezug klaeren ({display} bar erkannt)",
        )
    return None


def _medium_status(state: GovernedSessionState) -> str:
    status = _nested_text(state.medium_classification, "status")
    if status and status != "unavailable":
        return status
    if _has_value(state, "medium"):
        return "recognized"
    return "unavailable"


def _motion_hint_label(state: GovernedSessionState) -> str:
    return _nested_text(state.motion_hint, "label")


def _application_hint_label(state: GovernedSessionState) -> str:
    return _nested_text(state.application_hint, "label")


def _current_turn_text(state: GovernedSessionState) -> str:
    if hasattr(state, "pending_message"):
        text = _text(getattr(state, "pending_message", None))
        if text:
            return text
    return ""


def _rotary_context_detected(state: GovernedSessionState) -> bool:
    if _motion_hint_label(state) in {"linear", "static"}:
        return False
    if _application_hint_label(state) in {
        "linear_sealing",
        "static_sealing",
        "housing_sealing",
    }:
        return False
    if _has_value(state, "speed_rpm") or _has_value(state, "shaft_diameter_mm"):
        return True
    if _motion_hint_label(state) == "rotary":
        return True
    if _application_hint_label(state) in {"shaft_sealing", "marine_propulsion"}:
        return True
    current_text = _current_turn_text(state)
    if _LINEAR_CONTEXT_RE.search(current_text):
        return False
    return bool(_ROTARY_CONTEXT_RE.search(current_text))


def _rwdr_context_detected(state: GovernedSessionState) -> bool:
    sealing_type = str(_state_value(state, "sealing_type") or "").casefold()
    if (
        "rwdr" in sealing_type
        or "radialwellendichtring" in sealing_type
        or "wellendichtring" in sealing_type
    ):
        return True
    return bool(
        re.search(
            r"\b(?:rwdr|radialwellendichtring|wellendichtring|simmerring|simmering)\b",
            _current_turn_text(state),
            re.IGNORECASE,
        )
    )


def _application_anchor_present(state: GovernedSessionState) -> bool:
    if _has_value(state, "installation"):
        return True
    if _has_value(state, "sealing_type"):
        return True
    if _application_hint_label(state) or _motion_hint_label(state):
        return True
    return any(
        _text(summary)
        for summary in (
            getattr(state.sealai_norm, "application_summary", None),
            getattr(state.export_profile, "application_summary", None),
            getattr(state.dispatch_contract, "application_summary", None),
        )
    )


def _geometry_context_present(*, known_fields: set[str], current_text: str) -> bool:
    return "geometry_context" in known_fields or bool(
        _GEOMETRY_CONTEXT_RE.search(current_text)
    )


def _clearance_context_present(*, known_fields: set[str], current_text: str) -> bool:
    return "clearance_gap_mm" in known_fields or bool(
        _CLEARANCE_CONTEXT_RE.search(current_text)
    )


def _surface_context_present(*, known_fields: set[str], current_text: str) -> bool:
    return "counterface_surface" in known_fields or bool(
        _SURFACE_CONTEXT_RE.search(current_text)
    )


def _counterface_material_present(*, known_fields: set[str], current_text: str) -> bool:
    return "counterface_material" in known_fields or bool(
        _COUNTERFACE_MATERIAL_RE.search(current_text)
    )


def _priority_from_field(field_name: str) -> ClarificationPriority | None:
    meta = _QUESTION_META.get(field_name)
    if meta is None:
        return None
    return ClarificationPriority(
        focus_key=field_name,
        question=meta[0],
        reason=meta[1],
        open_point_label=render_open_point_label(None, field_name),
    )


def select_next_focus_from_known_context(
    *,
    known_fields: Iterable[str],
    medium_status: str = "unknown",
    current_text: str = "",
    application_anchor_present: bool = False,
    rotary_context_detected: bool = False,
    rwdr_context_detected: bool = False,
) -> ClarificationPriority | None:
    known = {str(field) for field in known_fields if isinstance(field, str) and field}
    current = _text(current_text)

    if "medium" not in known:
        return ClarificationPriority(
            focus_key="medium",
            question="Welches Medium soll abgedichtet werden?",
            reason="Das Medium entscheidet zuerst ueber Werkstoffwahl und Einsatzrahmen.",
            open_point_label=render_open_point_label(None, "medium"),
        )

    if not application_anchor_present and _APPLICATION_CONTEXT_RE.search(current):
        application_anchor_present = True
    linear_context_detected = bool(_LINEAR_CONTEXT_RE.search(current))
    if linear_context_detected:
        rotary_context_detected = False
    if (
        not linear_context_detected
        and not rotary_context_detected
        and _ROTARY_CONTEXT_RE.search(current)
    ):
        rotary_context_detected = True
    if rwdr_context_detected:
        rotary_context_detected = True
    geometry_context_present = _geometry_context_present(
        known_fields=known,
        current_text=current,
    )
    clearance_context_present = _clearance_context_present(
        known_fields=known,
        current_text=current,
    )
    surface_context_present = _surface_context_present(
        known_fields=known,
        current_text=current,
    )
    counterface_material_present = _counterface_material_present(
        known_fields=known,
        current_text=current,
    )
    pressure_present = bool(
        known & {"pressure_bar", "pressure_at_seal_bar", "pressure_delta_bar"}
    )

    if medium_status == "recognized":
        if not application_anchor_present:
            priority = _priority_from_field("application_context")
            if priority is not None:
                return priority
        if rotary_context_detected:
            for field_name in (
                "speed_rpm",
                "shaft_diameter_mm",
                "pressure_bar",
                "temperature_c",
            ):
                if field_name == "pressure_bar" and pressure_present:
                    continue
                if field_name not in known:
                    priority = _priority_from_field(field_name)
                    if priority is not None:
                        return priority
            if rwdr_context_detected:
                for field_name in (
                    "counterface_surface_condition",
                    "shaft_roughness_ra_um",
                    "shaft_hardness_hrc",
                    "runout_mm",
                    "eccentricity_mm",
                    "lubrication_condition",
                    "contamination_condition",
                    "installation_space_summary",
                ):
                    if field_name not in known:
                        priority = _priority_from_field(field_name)
                        if priority is not None:
                            return priority
            for field_name in ("installation", "geometry_context"):
                if field_name not in known:
                    priority = _priority_from_field(field_name)
                    if priority is not None:
                        return priority
            if "speed_rpm" in known and not surface_context_present:
                priority = _priority_from_field("counterface_surface")
                if priority is not None:
                    return priority
            if surface_context_present and not counterface_material_present:
                priority = _priority_from_field("counterface_material")
                if priority is not None:
                    return priority
        elif not geometry_context_present:
            priority = _priority_from_field("geometry_context")
            if priority is not None:
                return priority
        if (
            geometry_context_present
            and not clearance_context_present
            and ("pressure_bar" in known or "temperature_c" in known)
        ):
            priority = _priority_from_field("clearance_gap_mm")
            if priority is not None:
                return priority

    for field_name in ("pressure_bar", "temperature_c"):
        if field_name not in known:
            priority = _priority_from_field(field_name)
            if priority is not None:
                return priority
    return None


def select_clarification_priority(
    state: GovernedSessionState,
    fields: Iterable[str],
) -> ClarificationPriority | None:
    field_list = [str(field) for field in fields if isinstance(field, str) and field]
    field_set = set(field_list)
    structured_focus_fields = {
        "medium",
        "pressure_bar",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "temperature_c",
        "sealing_type",
        "duty_profile",
        "pressure_direction",
        "contamination",
        "contamination_condition",
        "tolerances",
        "industry",
        "compliance",
        "compliance_evidence",
        "medium_qualifiers",
        "concentration",
        "ph",
        "material",
        "application_context",
        "installation",
        "geometry_context",
        "clearance_gap_mm",
        "counterface_surface",
        "counterface_surface_condition",
        "shaft_roughness_ra_um",
        "shaft_hardness_hrc",
        "runout_mm",
        "eccentricity_mm",
        "axial_movement_mm",
        "lubrication_condition",
        "installation_space_summary",
        "counterface_material",
        "speed_rpm",
        "shaft_diameter_mm",
    }

    if "medium" in field_set:
        medium_prompt = medium_status_primary_question(state)
        if medium_prompt is not None:
            return ClarificationPriority(
                focus_key="medium",
                question=medium_prompt[0],
                reason=medium_prompt[1],
                open_point_label=render_open_point_label(state, "medium"),
            )
        if _has_value(state, "medium"):
            field_set.discard("medium")
            field_list = [
                field_name for field_name in field_list if field_name != "medium"
            ]
            if not field_set:
                return None
        else:
            return ClarificationPriority(
                focus_key="medium",
                question="Welches Medium soll abgedichtet werden?",
                reason="Das Medium entscheidet zuerst ueber Werkstoffwahl und Einsatzrahmen.",
                open_point_label=render_open_point_label(state, "medium"),
            )

    for field_name in ("concentration", "ph", "material", "compliance_evidence"):
        if field_name in field_set:
            if _has_value(state, field_name):
                continue
            priority = _priority_from_field(field_name)
            if priority is not None:
                return priority

    has_explicit_medium_context = (
        _nested_text(state.medium_classification, "status") == "recognized"
    )

    for field_name in (
        "pressure_bar",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "temperature_c",
        "speed_rpm",
        "shaft_diameter_mm",
    ):
        if field_name in field_set:
            if field_name in {
                "pressure_bar",
                "pressure_at_seal_bar",
                "pressure_delta_bar",
            }:
                pressure_role = _pressure_role_priority(state)
                if pressure_role is not None:
                    return pressure_role
                if _has_design_pressure_value(state):
                    continue
            confirmation_priority = _observed_confirmation_priority(state, field_name)
            if confirmation_priority is not None:
                return confirmation_priority
            if _has_value(state, field_name):
                continue
            if field_name in {"pressure_bar", "temperature_c"}:
                if has_explicit_medium_context:
                    continue
                priority = _priority_from_field(field_name)
                if priority is not None:
                    return priority
            priority = _priority_from_field(field_name)
            if priority is not None:
                return priority

    for field_name in ("sealing_type", "compliance"):
        if field_name in field_set:
            if _has_value(state, field_name):
                continue
            priority = _priority_from_field(field_name)
            if priority is not None:
                return priority

    if not field_set & structured_focus_fields:
        return None

    known_fields = {
        field_name
        for field_name in (
            "medium",
            "speed_rpm",
            "shaft_diameter_mm",
            "installation",
            "geometry_context",
            "clearance_gap_mm",
            "counterface_surface",
            "counterface_surface_condition",
            "shaft_roughness_ra_um",
            "shaft_hardness_hrc",
            "runout_mm",
            "eccentricity_mm",
            "axial_movement_mm",
            "lubrication_condition",
            "contamination_condition",
            "installation_space_summary",
            "counterface_material",
            "pressure_bar",
            "pressure_at_seal_bar",
            "pressure_delta_bar",
            "temperature_c",
            "sealing_type",
            "duty_profile",
            "pressure_direction",
            "contamination",
            "tolerances",
            "industry",
            "compliance",
            "compliance_evidence",
            "medium_qualifiers",
            "concentration",
            "ph",
            "material",
        )
        if _has_value(state, field_name)
    }
    priority = select_next_focus_from_known_context(
        known_fields=known_fields,
        medium_status=_medium_status(state),
        current_text=_current_turn_text(state),
        application_anchor_present=_application_anchor_present(state),
        rotary_context_detected=_rotary_context_detected(state),
        rwdr_context_detected=_rwdr_context_detected(state),
    )
    contextual_override_fields = {
        "application_context",
        "installation",
        "geometry_context",
        "clearance_gap_mm",
        "counterface_surface",
        "counterface_surface_condition",
        "shaft_roughness_ra_um",
        "shaft_hardness_hrc",
        "runout_mm",
        "eccentricity_mm",
        "axial_movement_mm",
        "lubrication_condition",
        "contamination_condition",
        "installation_space_summary",
        "counterface_material",
        "speed_rpm",
        "shaft_diameter_mm",
    }
    if priority is not None and (
        priority.focus_key in field_set
        or (len(field_set) > 1 and priority.focus_key in contextual_override_fields)
    ):
        return priority

    for field_name in (
        "duty_profile",
        "installation",
        "geometry_context",
        "pressure_direction",
        "medium_qualifiers",
        "contamination",
        "contamination_condition",
        "counterface_surface",
        "counterface_surface_condition",
        "shaft_roughness_ra_um",
        "shaft_hardness_hrc",
        "runout_mm",
        "eccentricity_mm",
        "axial_movement_mm",
        "lubrication_condition",
        "installation_space_summary",
        "tolerances",
        "industry",
        "compliance_evidence",
        "concentration",
        "ph",
        "material",
        "speed_rpm",
        "shaft_diameter_mm",
    ):
        if field_name in field_set:
            priority = _priority_from_field(field_name)
            if priority is not None:
                return priority

    for field_name in ("pressure_bar", "temperature_c"):
        if field_name in field_set:
            priority = _priority_from_field(field_name)
            if priority is not None:
                return priority
    return None


def prioritized_open_point_labels(
    state: GovernedSessionState,
    fields: Iterable[str],
) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    priority = select_clarification_priority(state, fields)
    if priority is not None and priority.open_point_label not in seen:
        labels.append(priority.open_point_label)
        seen.add(priority.open_point_label)

    for field_name in fields:
        if (
            field_name == "medium"
            and field_name in state.asserted.assertions
            and _has_value(state, "medium")
            and medium_status_primary_question(state) is None
        ):
            continue
        if field_name in {
            "speed_rpm",
            "shaft_diameter_mm",
        } and not _rotary_context_detected(state):
            continue
        if isinstance(field_name, str) and field_name.startswith(
            "Unresolved conflict:"
        ):
            label = field_name
        else:
            label = render_open_point_label(state, str(field_name))
        text = _text(label)
        if not text or text in seen:
            continue
        labels.append(text)
        seen.add(text)

    return labels
