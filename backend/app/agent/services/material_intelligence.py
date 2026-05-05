from __future__ import annotations

from typing import Any

from app.agent.domain.medium_registry import classify_medium_value


_SAFETY = {
    "mutates_case_state": False,
    "creates_engineering_truth": False,
    "final_approval_claim_allowed": False,
    "dispatch_allowed": False,
    "external_contact_allowed": False,
    "export_allowed": False,
}

_MATERIALS: dict[str, dict[str, object]] = {
    "nbr": {
        "label": "NBR",
        "family": "Elastomer",
        "strengths": [
            "Mineraloele und viele Hydraulikoele im ueblichen Vorqualifikationsfenster",
            "wirtschaftliche Standardfamilie fuer viele Oel- und Fettkontakte",
            "gute Basis fuer erste Vergleichsfragen bei Hydraulik und Getriebeoel",
        ],
        "limits": [
            "Wasser, Dampf, Ozon und Witterung koennen das Prueffenster stark einengen",
            "hoehere Temperaturen und aggressive Chemie brauchen zusaetzliche Angaben",
        ],
        "medium_families": {"oel", "hydraulikoel"},
    },
    "hnbr": {
        "label": "HNBR",
        "family": "Elastomer",
        "strengths": [
            "haeufig als robusteres NBR-nahes Prueffenster bei Oel, Temperatur und Verschleissfragen",
            "interessant, wenn Standard-NBR thermisch oder mechanisch knapp wird",
        ],
        "limits": [
            "genaue Mischung, Temperatur und Medium muessen vom Lieferanten eingegrenzt werden",
            "nicht automatisch Ersatz fuer NBR in jeder Dichtstelle",
        ],
        "medium_families": {"oel", "hydraulikoel"},
    },
    "fkm": {
        "label": "FKM",
        "family": "Fluorelastomer",
        "strengths": [
            "haeufiges Prueffenster fuer Oele, Kraftstoffe und hoehere Temperaturen",
            "relevant, wenn Temperatur und Medienbelastung ueber Standard-Elastomere hinausgehen",
        ],
        "limits": [
            "Dampf, Heisswasser, Amine, Ketone und manche Bremsfluide muessen separat abgegrenzt werden",
            "PFAS- und Lieferantennachweise koennen fuer Dokumentation und Verfuegbarkeit wichtig werden",
        ],
        "medium_families": {"oel", "kraftstoff", "chemikalien"},
    },
    "epdm": {
        "label": "EPDM",
        "family": "Elastomer",
        "strengths": [
            "haeufiges Prueffenster fuer Wasser, Dampf, Glykol und Aussenbewitterung",
            "interessant bei wasserbasierten Medien, wenn Oelkontakt ausgeschlossen ist",
        ],
        "limits": [
            "Mineraloele, Kraftstoffe und viele Schmierstoffe sind fruehe Ausschlussfragen",
            "Salze, Additive, Temperatur und Reinigungszyklen bleiben entscheidend",
        ],
        "medium_families": {"wasser", "waessrig_salzhaltig", "dampf", "glykol"},
    },
    "ptfe": {
        "label": "PTFE",
        "family": "Fluorpolymer",
        "strengths": [
            "breites chemisches Prueffenster und niedrige Reibung als Designrichtung",
            "bei aggressiven Medien oder dynamischen Sonderfaellen oft als zu pruefende Familie relevant",
        ],
        "limits": [
            "Kriechen, Fuellung, Vorspannung, Gegenlaufflaeche und Trockenlauf muessen konstruktiv betrachtet werden",
            "PFAS- und Dokumentationsfragen sollten frueh mitgefuehrt werden",
        ],
        "medium_families": {"chemikalien", "waessrig_salzhaltig", "wasser", "dampf", "loesungsmittel"},
    },
    "ffkm": {
        "label": "FFKM",
        "family": "Perfluorelastomer",
        "strengths": [
            "Sonderprueffenster fuer sehr anspruchsvolle Chemie- und Temperaturprofile",
            "relevant, wenn Standard-Elastomere aus Dokumentations- oder Mediengruenden ausscheiden koennten",
        ],
        "limits": [
            "Kosten, Lieferzeit, Mischung und Datenblattlage sind fruehe Beschaffungsthemen",
            "PFAS- und Freigabedokumente muessen projektbezogen geklaert werden",
        ],
        "medium_families": {"chemikalien", "loesungsmittel", "dampf"},
    },
    "vmq": {
        "label": "Silikon / VMQ",
        "family": "Elastomer",
        "strengths": [
            "breites Temperaturfenster in vielen statischen oder hygienischen Kontexten",
            "interessant, wenn Tieftemperatur oder weiche Dichtwirkung im Vordergrund steht",
        ],
        "limits": [
            "Abrieb, Reissfestigkeit und dynamische Kantenbelastung sind kritisch zu pruefen",
            "Oel- und Medienkontakt duerfen nicht pauschal uebertragen werden",
        ],
        "medium_families": {"wasser", "luft"},
    },
    "pu": {
        "label": "PU",
        "family": "Polyurethan",
        "strengths": [
            "mechanisch interessantes Prueffenster bei Hydraulik, Abrieb und Spaltextrusion",
            "relevant bei linearen Dichtstellen mit hoher mechanischer Belastung",
        ],
        "limits": [
            "Heisswasser, Hydrolyse, Temperatur und Medienadditive muessen genau eingegrenzt werden",
            "bei rotierenden Dichtstellen nicht ohne Bauformkontext uebernehmen",
        ],
        "medium_families": {"hydraulikoel", "oel"},
    },
}

_ALIASES = {
    "nbr": "nbr",
    "nitril": "nbr",
    "nitrilkautschuk": "nbr",
    "hnbr": "hnbr",
    "fkm": "fkm",
    "viton": "fkm",
    "epdm": "epdm",
    "ptfe": "ptfe",
    "teflon": "ptfe",
    "ffkm": "ffkm",
    "kalrez": "ffkm",
    "vmq": "vmq",
    "silikon": "vmq",
    "silicone": "vmq",
    "pu": "pu",
    "pur": "pu",
    "polyurethan": "pu",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", ".").strip()
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _profile_value(profile: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = profile.get(key)
        if value not in (None, "", []):
            return value
    return None


def _material_key(value: Any) -> str | None:
    lowered = _text(value).casefold()
    if not lowered:
        return None
    for alias, key in _ALIASES.items():
        if alias in lowered:
            return key
    return None


def _medium_family(profile: dict[str, Any], medium_classification: dict[str, Any]) -> tuple[str, str | None]:
    label = _text(
        medium_classification.get("canonical_label")
        or _profile_value(profile, "medium", "medium_name", "media")
    )
    family = _text(medium_classification.get("family"))
    if label and (not family or family == "unknown"):
        classified = classify_medium_value(label)
        family = classified.family
        label = classified.canonical_label or label
    if "hydraulik" in label.casefold():
        family = "hydraulikoel"
    if "oel" in label.casefold() or "öl" in label.casefold():
        family = "oel" if family in ("", "unknown") else family
    return family or "unknown", label or None


def _known_operating_window(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature_c": _number(_profile_value(profile, "temperature_c", "temperature", "temperature_max_c")),
        "pressure_bar": _number(_profile_value(profile, "pressure_bar", "pressure", "operating_pressure_bar")),
        "speed_rpm": _number(_profile_value(profile, "speed_rpm", "rpm", "speed")),
        "shaft_diameter_mm": _number(_profile_value(profile, "shaft_diameter_mm", "shaft_diameter", "diameter_mm")),
        "seal_type": _text(_profile_value(profile, "seal_type", "sealing_type", "dichtungstyp")),
        "motion_type": _text(_profile_value(profile, "motion_type", "motion", "movement")),
    }


def _status_for_material(
    *,
    material_key: str,
    family: str,
    temperature_c: float | None,
    pressure_bar: float | None,
    seal_type: str,
) -> str:
    material = _MATERIALS[material_key]
    supported = set(material.get("medium_families") or set())
    if family == "unknown":
        return "needs_more_data"
    if family not in supported:
        if material_key == "fkm" and family == "waessrig_salzhaltig":
            return "not_prioritized_from_known_context"
        if material_key == "nbr" and family in {"wasser", "waessrig_salzhaltig", "dampf"}:
            return "excluded_by_known_constraint"
        if material_key == "epdm" and family in {"oel", "hydraulikoel", "kraftstoff"}:
            return "excluded_by_known_constraint"
        return "not_prioritized_from_known_context"
    if material_key in {"ptfe", "ffkm"}:
        return "requires_supplier_review"
    if temperature_c is None or pressure_bar is None or not seal_type:
        return "needs_more_data"
    return "candidate_to_check"


def _missing_for_material(profile: dict[str, Any], medium_label: str | None) -> list[str]:
    window = _known_operating_window(profile)
    missing: list[str] = []
    if not medium_label:
        missing.append("Medium")
    if window["temperature_c"] is None:
        missing.append("Temperatur")
    if window["pressure_bar"] is None:
        missing.append("Druck oder Druckdifferenz")
    if not window["seal_type"]:
        missing.append("Dichtprinzip oder Dichtungstyp")
    if not window["motion_type"]:
        missing.append("Bewegungsart")
    if window["motion_type"].casefold() == "rotierend" and window["speed_rpm"] is None:
        missing.append("Drehzahl")
    return missing


def _status_note(status: str) -> str:
    return {
        "candidate_to_check": "Kandidat im Prueffenster",
        "needs_more_data": "Daten fehlen",
        "requires_supplier_review": "Herstellerdaten pruefen",
        "not_prioritized_from_known_context": "aktuell nicht priorisiert",
        "excluded_by_known_constraint": "bekannte Angabe spricht dagegen",
    }.get(status, "orientierend")


def _candidate(
    material_key: str,
    *,
    status: str,
    missing: list[str],
    family: str,
) -> dict[str, Any]:
    material = _MATERIALS[material_key]
    relevant_missing = missing[:]
    if status == "candidate_to_check":
        relevant_missing = [
            item
            for item in missing
            if item in {"Dichtprinzip oder Dichtungstyp", "Druck oder Druckdifferenz", "Temperatur"}
        ]
    why = list(material.get("strengths") or [])[:3]
    if family == "waessrig_salzhaltig" and material_key in {"epdm", "ptfe"}:
        why.insert(0, "Salzhaltiges Wasser verlangt fruehe Trennung zwischen Dichtwerkstoff und metallischen Kontaktteilen.")
    if family in {"oel", "hydraulikoel"} and material_key in {"nbr", "hnbr", "fkm", "pu"}:
        why.insert(0, "Oelkontakt grenzt das elastomere Prueffenster deutlich gegen wassernahe Familien ab.")
    return {
        "material_key": material_key,
        "label": str(material["label"]),
        "family": str(material["family"]),
        "status": status,
        "status_label": _status_note(status),
        "confidence": "medium" if status in {"candidate_to_check", "needs_more_data"} else "low",
        "why_considered": why[:4],
        "limits": list(material.get("limits") or [])[:4],
        "blocking_unknowns": relevant_missing[:5],
        "required_checks": [
            "Mediumdatenblatt und Konzentration",
            "Temperaturfenster im Dauer- und Spitzenbetrieb",
            "Druck direkt an der Dichtstelle",
            "Dichtprinzip, Bauform und Kontaktpartner",
        ],
        "evidence_ref_ids": [f"material-{material_key}"],
    }


def _candidate_order(family: str, known_key: str | None) -> list[str]:
    if family == "waessrig_salzhaltig":
        order = ["epdm", "ptfe", "ffkm", "fkm", "nbr", "hnbr"]
    elif family in {"oel", "hydraulikoel"}:
        order = ["nbr", "hnbr", "fkm", "pu", "ptfe", "epdm"]
    elif family == "dampf":
        order = ["epdm", "ptfe", "ffkm", "fkm", "nbr"]
    elif family in {"chemikalien", "chemisch_aggressiv", "loesungsmittel"}:
        order = ["ptfe", "ffkm", "fkm", "epdm", "nbr"]
    elif family == "wasser":
        order = ["epdm", "ptfe", "vmq", "nbr", "fkm"]
    else:
        order = ["nbr", "fkm", "epdm", "ptfe", "hnbr", "ffkm", "pu", "vmq"]
    if known_key and known_key not in order:
        order.insert(0, known_key)
    elif known_key:
        order.remove(known_key)
        order.insert(0, known_key)
    return order


def _alternatives(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [item for item in candidates if item["status"] in {"candidate_to_check", "needs_more_data", "requires_supplier_review"}]
    alternatives: list[dict[str, Any]] = []
    for left, right in zip(ranked, ranked[1:]):
        alternatives.append(
            {
                "from_material": left["label"],
                "to_material": right["label"],
                "comparison": (
                    f"{left['label']} und {right['label']} liegen in unterschiedlichen Prueffenstern. "
                    "Die Entscheidung haengt an Mediumdetails, Temperatur, Druck, Bauform und Nachweisen."
                ),
                "tradeoffs": [
                    f"{left['label']}: {left['status_label']}",
                    f"{right['label']}: {right['status_label']}",
                ],
                "missing_for_decision": list(dict.fromkeys(left["blocking_unknowns"] + right["blocking_unknowns"]))[:5],
            }
        )
        if len(alternatives) >= 3:
            break
    return alternatives


def build_material_intelligence_projection(
    *,
    profile: dict[str, Any],
    medium_classification: dict[str, Any] | None = None,
    seal_application_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only material capability projection from governed state.

    This function never mutates case state and never produces a release claim.
    It only describes candidate material families and open validation inputs.
    """

    medium_family, medium_label = _medium_family(profile, medium_classification or {})
    window = _known_operating_window(profile)
    known_material = _text(_profile_value(profile, "material", "material_family", "werkstoff")) or None
    known_key = _material_key(known_material)
    if not window["seal_type"] and seal_application_profile:
        window["seal_type"] = _text(
            seal_application_profile.get("seal_type")
            or seal_application_profile.get("seal_family")
        )
    missing = _missing_for_material(profile, medium_label)

    candidates: list[dict[str, Any]] = []
    for material_key in _candidate_order(medium_family, known_key):
        if material_key not in _MATERIALS:
            continue
        status = _status_for_material(
            material_key=material_key,
            family=medium_family,
            temperature_c=window["temperature_c"],
            pressure_bar=window["pressure_bar"],
            seal_type=window["seal_type"],
        )
        candidates.append(
            _candidate(
                material_key,
                status=status,
                missing=missing,
                family=medium_family,
            )
        )
        if len(candidates) >= 6:
            break

    evidence = [
        {
            "id": f"material-{key}",
            "source_type": "deterministic",
            "validation_status": "system_derived",
            "title": f"SeaLAI Werkstoffrahmen: {value['label']}",
            "excerpt": "; ".join(list(value.get("strengths") or [])[:2]),
            "confidence": "medium",
        }
        for key, value in _MATERIALS.items()
        if any(item["material_key"] == key for item in candidates)
    ]

    rfq_notes = [
        "Werkstofffamilie, Mischung/Compound und Nachweise gehoeren spaeter in die Anfragebasis.",
        "Der Hersteller muss Mediumdetails, Temperatur, Druck und Bauform gegen eigene Daten pruefen.",
    ]
    if medium_family == "waessrig_salzhaltig":
        rfq_notes.insert(0, "Bei Salzwasser muessen neben dem Dichtwerkstoff auch Welle, Gehaeuse, Feder und Stuetzteile betrachtet werden.")
    if any(item["material_key"] in {"fkm", "ptfe", "ffkm"} for item in candidates):
        rfq_notes.append("Bei fluorierten Werkstoffen koennen PFAS-, Liefer- und Dokumentationsfragen relevant werden.")

    return {
        "capability_id": "material_seal_type_context",
        "status": "available" if candidates else "insufficient_context",
        "input_summary": {
            "medium": medium_label,
            "medium_family": medium_family,
            "known_material": known_material,
            "temperature_c": window["temperature_c"],
            "pressure_bar": window["pressure_bar"],
            "seal_type": window["seal_type"] or None,
            "motion_type": window["motion_type"] or None,
        },
        "candidate_materials": candidates,
        "alternatives": _alternatives(candidates),
        "missing_field_hints": missing,
        "rfq_relevance_notes": rfq_notes,
        "evidence": evidence,
        "safety": dict(_SAFETY),
        "not_for_release_decisions": True,
        "disclaimer": "Werkstofffenster nur zur Orientierung; keine Materialfreigabe und keine Auslegung.",
    }
