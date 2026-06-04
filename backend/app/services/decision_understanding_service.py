from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.api.v1.schemas.case_workspace import DecisionUnderstandingProjection

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "asset_type": (
        "asset_type",
        "equipment_type",
        "installation",
        "application_context",
    ),
    "asset_function": ("asset_function", "primary_function", "function"),
    "seal_location": ("seal_location", "sealing_position", "geometry_context"),
    "motion_type": ("motion_type", "movement_type"),
    "medium_name": ("medium_name", "medium", "media"),
    "temperature_max": ("temperature_max", "temperature_max_c", "temperature_c"),
    "pressure_nominal": ("pressure_nominal", "pressure_bar", "operating_pressure_bar"),
    "speed_rpm": ("speed_rpm", "rotation_speed_rpm"),
    "shaft_diameter": ("shaft_diameter", "shaft_diameter_mm"),
    "surface_finish": ("surface_finish", "counterface_surface", "shaft_surface_finish"),
    "shaft_material": ("shaft_material",),
    "candidate_materials": ("candidate_materials", "material_candidates", "materials"),
    "material_question": ("material_question", "material_comparison"),
    "requested_seal_type": ("requested_seal_type", "sealing_type", "seal_type"),
    "food_contact": ("food_contact", "food", "fda_relevance"),
    "atex_relevance": ("atex_relevance", "atex"),
}

_PRIORITY_MISSING_FIELDS: tuple[tuple[str, str], ...] = (
    ("asset_type", "In welcher Anlage oder Baugruppe sitzt die Dichtung?"),
    (
        "motion_type",
        "Sitzt die Dichtung an einer rotierenden Welle, an einer statischen Verbindung oder an einer linearen Bewegung?",
    ),
    ("seal_location", "An welcher Dichtstelle sitzt die Dichtung genau?"),
    ("medium_name", "Welches Medium soll an der Dichtstelle abgedichtet werden?"),
    ("temperature_max", "Welche maximale Temperatur liegt an der Dichtstelle an?"),
    ("pressure_nominal", "Liegt an der Dichtstelle Druck oder Vakuum an?"),
    ("speed_rpm", "Welche Drehzahl oder Geschwindigkeit liegt an der Welle an?"),
    ("shaft_diameter", "Welchen Wellendurchmesser oder Einbauraum kennen Sie?"),
    ("surface_finish", "Welche Gegenlaufflaeche oder Oberflaechenangabe ist bekannt?"),
)


def _walk_mappings(value: Any) -> list[Mapping[str, Any]]:
    mappings: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        mappings.append(value)
        for nested in value.values():
            mappings.extend(_walk_mappings(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            mappings.extend(_walk_mappings(item))
    return mappings


def _unwrap(value: Any) -> Any:
    if isinstance(value, Mapping):
        for key in ("canonical_value", "value", "asserted_value", "raw_value"):
            nested = value.get(key)
            if nested not in (None, "", []):
                return _unwrap(nested)
    return value


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return [value]


def _compact(items: Sequence[Any], *, limit: int = 8) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(_unwrap(item) if isinstance(item, Mapping) else item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _number(value: Any) -> float | None:
    value = _unwrap(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", ".").strip()
        token = normalized.split()[0] if normalized.split() else ""
        try:
            return float(token)
        except ValueError:
            return None
    return None


def _field(state: Mapping[str, Any], canonical_key: str) -> Any:
    aliases = _FIELD_ALIASES.get(canonical_key, (canonical_key,))
    for mapping in _walk_mappings(state):
        for alias in aliases:
            if alias in mapping and mapping[alias] not in (None, "", []):
                return _unwrap(mapping[alias])
    return None


def _text_contains(value: Any, *needles: str) -> bool:
    text = str(value or "").casefold()
    return any(needle.casefold() in text for needle in needles)


def _label(field_name: str, value: Any) -> str | None:
    if value in (None, "", []):
        return None
    labels = {
        "asset_type": "Anlage/Baugruppe",
        "motion_type": "Bewegung",
        "seal_location": "Dichtstelle",
        "medium_name": "Medium",
        "temperature_max": "Temperatur max.",
        "pressure_nominal": "Druck",
        "speed_rpm": "Drehzahl",
        "shaft_diameter": "Wellendurchmesser",
        "requested_seal_type": "Dichtungstyp-Richtung",
    }
    rendered = str(value)
    if field_name == "temperature_max" and _number(value) is not None:
        rendered = f"{_number(value):g} degC"
    elif field_name == "pressure_nominal" and _number(value) is not None:
        rendered = f"{_number(value):g} bar"
    elif field_name == "shaft_diameter" and _number(value) is not None:
        rendered = f"{_number(value):g} mm"
    elif field_name == "speed_rpm" and _number(value) is not None:
        rendered = f"{_number(value):g} rpm"
    return f"{labels.get(field_name, field_name)}: {rendered}"


def _derive_case_summary(fields: Mapping[str, Any]) -> str:
    parts = [
        str(fields.get("asset_type") or "Dichtungssituation"),
        str(fields.get("medium_name") or "Medium offen"),
    ]
    temp = _number(fields.get("temperature_max"))
    pressure = _number(fields.get("pressure_nominal"))
    if temp is not None:
        parts.append(f"{temp:g} degC")
    if pressure is not None:
        parts.append(f"{pressure:g} bar")
    motion = fields.get("motion_type")
    if motion:
        parts.append(str(motion))
    return ", ".join(parts) + "."


def _derive_technical_meaning(fields: Mapping[str, Any]) -> list[str]:
    asset = fields.get("asset_type")
    medium = fields.get("medium_name")
    temp = _number(fields.get("temperature_max"))
    pressure = _number(fields.get("pressure_nominal"))
    motion = fields.get("motion_type")
    material_question = fields.get("material_question")
    requested_seal_type = fields.get("requested_seal_type")
    notes: list[str] = []

    if _text_contains(medium, "salzwasser", "seawater", "sole", "chlorid"):
        notes.append(
            "Salzhaltige Medien sind fuer Dichtungen vor allem wegen Korrosion, Ablagerungen, Partikeln und wechselnder Benetzung relevant."
        )
    if _text_contains(medium, "ethanol", "alkohol"):
        notes.append(
            "Ethanol kann je nach Temperatur, Druck und Anlagenkontext Dampf-, Entzuendungs- und ATEX-Relevanz erzeugen."
        )
    if _text_contains(asset, "pump", "pumpe"):
        notes.append(
            "Pumpenanwendungen duerfen nicht vorschnell wie einfache druckarme RWDR-Faelle behandelt werden; Dichtstellendruck, Pumpentyp und Welle sind entscheidend."
        )
    if _text_contains(asset, "agitator", "ruehrwerk", "ruehrwerk"):
        notes.append(
            "Ruehrwerke brauchen besondere Aufmerksamkeit fuer Dichtstelle, Exzentrizitaet, Behaelterdruck, Reinigung und Wellenbewegung."
        )
    if _text_contains(asset, "gearbox", "getriebe"):
        notes.append(
            "Bei Getriebeausgaengen geht es meist um Oelrueckhaltung und Kontaminationsschutz; Welle, Drehzahl, Einbau und Oberflaeche bestimmen die Richtung."
        )
    if pressure is not None and pressure >= 5:
        notes.append(
            "Der angegebene Druck ist fuer viele Standard-RWDR-Kontexte ein frueher Pruefpunkt und muss an der Dichtstelle bestaetigt werden."
        )
    if temp is not None and temp >= 120:
        notes.append(
            "Die Temperatur liegt in einem Bereich, in dem Werkstofffenster und Medienzustand fallbezogen geprueft werden muessen."
        )
    if _text_contains(material_question, "ptfe", "fkm") or (
        _text_contains(requested_seal_type, "ptfe")
        and _text_contains(str(fields), "fkm")
    ):
        notes.append(
            "Ein PTFE/FKM-Vergleich ist ohne Medium, Temperatur, Bewegung, Druck und Gegenlaufflaeche keine belastbare Auswahlentscheidung."
        )
    if motion:
        notes.append(
            "Die Bewegungsart ist ein zentraler Diagnoseanker fuer Dichtungstyp, Geometrie und berechenbare Werte."
        )
    return _compact(notes, limit=6)


def _derive_plausible_directions(fields: Mapping[str, Any]) -> list[str]:
    asset = fields.get("asset_type")
    medium = fields.get("medium_name")
    pressure = _number(fields.get("pressure_nominal"))
    temp = _number(fields.get("temperature_max"))
    motion = fields.get("motion_type")
    requested = fields.get("requested_seal_type")
    directions: list[str] = []
    if _text_contains(asset, "pump", "pumpe") and (
        (pressure or 0) >= 5 or _text_contains(medium, "ethanol") or (temp or 0) >= 120
    ):
        directions.append(
            "Gleitringdichtung als technische Richtung pruefen; Standard-RWDR nicht vorschnell vorgeben."
        )
    if _text_contains(motion, "rotary", "rotierend") and not directions:
        directions.append(
            "Rotierende Wellenabdichtung strukturiert vorqualifizieren; RWDR/PTFE-RWDR nur bei passendem Druck-, Medien- und Geometriefenster."
        )
    if _text_contains(requested, "ptfe", "rwdr"):
        directions.append(
            "PTFE-RWDR als Kandidatenrichtung mit Herstellerpruefung und Gegenlaufflaechencheck fuehren."
        )
    if not directions:
        directions.append(
            "Technische Richtung erst nach Anlagenkontext, Bewegung, Medium und Betriebsdaten belastbar eingrenzen."
        )
    return _compact(directions, limit=4)


def _derive_missing(fields: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    explicit = []
    for key in (
        "missing_required_fields",
        "blocking_unknowns",
        "open_points",
        "coverage_gaps",
    ):
        for mapping in _walk_mappings(state):
            explicit.extend(_as_list(mapping.get(key)))
    explicit = _compact(explicit, limit=8)
    if explicit:
        return explicit
    missing = [
        key
        for key, _question in _PRIORITY_MISSING_FIELDS
        if fields.get(key) in (None, "", [])
    ]
    return missing[:6]


def _derive_risks(fields: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    risks: list[Any] = []
    for key in ("top_risks", "key_risks", "risks", "risk_evaluations"):
        for mapping in _walk_mappings(state):
            value = mapping.get(key)
            if key == "risk_evaluations" and isinstance(value, Sequence):
                for item in value:
                    if isinstance(item, Mapping):
                        score = item.get("score")
                        if score in {2, 3, 4, 9}:
                            risks.append(
                                item.get("explanation_short") or item.get("risk_name")
                            )
            else:
                risks.extend(_as_list(value))
    medium = fields.get("medium_name")
    temp = _number(fields.get("temperature_max"))
    pressure = _number(fields.get("pressure_nominal"))
    if _text_contains(medium, "salzwasser", "chlorid"):
        risks.extend(["corrosion_risk", "abrasion_or_deposit_risk"])
    if _text_contains(medium, "ethanol"):
        risks.extend(["atex_or_vapor_context_to_check", "chemical_compatibility_risk"])
    if temp is not None and temp >= 120:
        risks.append("temperature_risk")
    if pressure is not None and pressure >= 5:
        risks.append("pressure_risk")
    if not risks:
        risks.append("unknowns_risk")
    return _compact(risks, limit=6)


def _derive_next_question(
    fields: Mapping[str, Any], state: Mapping[str, Any], missing: Sequence[str]
) -> str | None:
    for key in (
        "recommended_next_question",
        "next_best_question",
        "pending_best_next_question",
        "primary_question",
    ):
        for mapping in _walk_mappings(state):
            value = mapping.get(key)
            if value not in (None, "", []):
                return str(_unwrap(value))
    missing_set = {str(item) for item in missing}
    for field_name, question in _PRIORITY_MISSING_FIELDS:
        if field_name in missing_set or fields.get(field_name) in (None, "", []):
            return question
    return None


def _derive_review_needs(
    fields: Mapping[str, Any], state: Mapping[str, Any], missing: Sequence[str]
) -> list[str]:
    needs: list[Any] = []
    for key in (
        "manufacturer_review_needs",
        "manufacturer_questions",
        "open_manufacturer_questions",
        "manufacturer_questions_mandatory",
    ):
        for mapping in _walk_mappings(state):
            needs.extend(_as_list(mapping.get(key)))
    if not needs:
        field_to_need = {
            "asset_type": "Anlage/Baugruppe und Funktion",
            "motion_type": "Bewegungsart und Dichtstelle",
            "medium_name": "Medium und Zustand an der Dichtstelle",
            "temperature_max": "maximale Temperatur",
            "pressure_nominal": "Druck direkt an der Dichtstelle",
            "speed_rpm": "Drehzahl/Geschwindigkeit",
            "shaft_diameter": "Wellen- und Einbauraumgeometrie",
            "surface_finish": "Gegenlaufflaeche und Werkstoff",
        }
        needs.extend(field_to_need.get(str(item), str(item)) for item in missing)
    if fields.get("atex_relevance") or _text_contains(
        fields.get("medium_name"), "ethanol"
    ):
        needs.append(
            "ATEX-/Dampf-/Entzuendungskontext durch Hersteller oder Fachstelle pruefen"
        )
    return _compact(needs, limit=8)


def _derive_confidence_notes(
    fields: Mapping[str, Any], state: Mapping[str, Any], missing: Sequence[str]
) -> list[str]:
    notes: list[str] = []
    for key in ("assumptions_active", "confidence_notes", "evidence_gaps"):
        for mapping in _walk_mappings(state):
            notes.extend(str(item) for item in _as_list(mapping.get(key)) if item)
    if missing:
        notes.append(
            "Offene oder unbestaetigte Angaben begrenzen die technische Aussagekraft."
        )
    if fields.get("medium_name"):
        notes.append(
            "Medium-Hinweise sind Diagnose- und RFQ-Vorbereitung, keine Materialfreigabe."
        )
    notes.append("Herstellerfreigabe bleibt die finale technische Instanz.")
    return _compact(notes, limit=6)


def build_decision_understanding_projection(
    state: Mapping[str, Any]
) -> DecisionUnderstandingProjection:
    fields = {key: _field(state, key) for key in _FIELD_ALIASES}
    understood = _compact(
        [
            _label("asset_type", fields.get("asset_type")),
            _label("motion_type", fields.get("motion_type")),
            _label("seal_location", fields.get("seal_location")),
            _label("medium_name", fields.get("medium_name")),
            _label("temperature_max", fields.get("temperature_max")),
            _label("pressure_nominal", fields.get("pressure_nominal")),
            _label("speed_rpm", fields.get("speed_rpm")),
            _label("shaft_diameter", fields.get("shaft_diameter")),
            _label("requested_seal_type", fields.get("requested_seal_type")),
        ],
        limit=9,
    )
    missing = _derive_missing(fields, state)
    return DecisionUnderstandingProjection(
        case_summary=_derive_case_summary(fields),
        understood_now=understood,
        technical_meaning=_derive_technical_meaning(fields),
        plausible_directions=_derive_plausible_directions(fields),
        not_yet_decidable=missing,
        key_risks=_derive_risks(fields, state),
        confidence_notes=_derive_confidence_notes(fields, state, missing),
        next_best_question=_derive_next_question(fields, state, missing),
        manufacturer_review_needs=_derive_review_needs(fields, state, missing),
    )


def build_decision_understanding_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    return build_decision_understanding_projection(state).model_dump()
