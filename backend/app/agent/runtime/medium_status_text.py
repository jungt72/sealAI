from __future__ import annotations

from app.agent.state.models import GovernedSessionState


def _text(value: str | None) -> str:
    return str(value or "").strip()


def _state_has_medium_value(state: GovernedSessionState) -> bool:
    asserted = state.asserted.assertions.get("medium")
    if asserted is not None and getattr(asserted, "asserted_value", None) not in (None, ""):
        return True
    normalized = state.normalized.parameters.get("medium")
    return normalized is not None and getattr(normalized, "value", None) not in (None, "")


def medium_status_open_point(state: GovernedSessionState) -> str:
    classification = state.medium_classification
    if isinstance(classification, dict):
        classification = type("ClassificationProxy", (), classification)()
    capture = state.medium_capture
    if isinstance(capture, dict):
        capture = type("CaptureProxy", (), capture)()
    status = _text(classification.status) or "unavailable"
    if status == "unavailable" and _state_has_medium_value(state):
        status = "recognized"
    family = _text(getattr(classification, "family", None))
    canonical = _text(getattr(classification, "canonical_label", None))
    raw = _text(getattr(capture, "primary_raw_text", None))
    followup = _text(getattr(classification, "followup_question", None))

    if status == "recognized":
        if followup:
            if canonical == "Dampf":
                return "Dampfphase sowie Druck- und Temperaturbereich präzisieren"
            if family == "oelhaltig":
                return "Mediumtyp bzw. Auspraegung des oelhaltigen Mediums präzisieren"
            return f"Mediumdetails zu {canonical or 'dem erkannten Medium'} präzisieren"
        if family == "waessrig_salzhaltig":
            return "Salzgehalt bzw. Konzentration des Mediums präzisieren"
        return "Mediumdetails präzisieren"

    if status == "family_only":
        if "reinig" in raw.casefold():
            return "Reinigungsloesung genauer einordnen (Stoff und Konzentration)"
        if family == "chemisch_aggressiv":
            return "Chemisch aggressives Medium genauer einordnen (Stoff und Konzentration)"
        if family == "loesemittelhaltig":
            return "Loesungsmitteltyp genauer angeben"
        return f"Medium innerhalb der Familie {family.replace('_', ' ')} präzisieren"

    if status == "mentioned_unclassified":
        if raw:
            return f"Genanntes Medium fachlich einordnen: {raw}"
        return "Genanntes Medium fachlich genauer einordnen"

    return "Medium angeben"


def medium_status_primary_question(state: GovernedSessionState) -> tuple[str, str] | None:
    classification = state.medium_classification
    if isinstance(classification, dict):
        classification = type("ClassificationProxy", (), classification)()
    capture = state.medium_capture
    if isinstance(capture, dict):
        capture = type("CaptureProxy", (), capture)()
    status = _text(classification.status) or "unavailable"
    if status == "unavailable" and _state_has_medium_value(state):
        status = "recognized"
    family = _text(getattr(classification, "family", None))
    canonical = _text(getattr(classification, "canonical_label", None))
    raw = _text(getattr(capture, "primary_raw_text", None))
    followup = _text(getattr(classification, "followup_question", None))

    if status == "recognized":
        if followup:
            return (
                followup,
                "Das Medium ist bereits erkannt, ich muss jetzt die prozessrelevanten Detailangaben dazu präzisieren.",
            )
        if family == "waessrig_salzhaltig":
            return (
                f"Wie hoch ist der Salzgehalt bzw. die Konzentration bei {canonical or 'dem Medium'}?",
                "Das Medium ist erkannt; fuer die technische Einengung brauche ich noch die prozessrelevante Auspraegung.",
            )
        return None

    if status == "family_only":
        if "reinig" in raw.casefold():
            return (
                "Welche genaue Reinigungsloesung liegt an und in welcher Konzentration?",
                "Ich erkenne bereits einen Medienkontext, fuer die technische Einengung brauche ich jetzt den genauen Stoff und die Konzentration.",
            )
        if family == "chemisch_aggressiv":
            return (
                "Welcher genaue Stoff liegt an und in welcher Konzentration?",
                "Ich erkenne bereits einen chemisch relevanten Medienkontext, brauche aber die genaue stoffliche Einordnung.",
            )
        if family == "loesemittelhaltig":
            return (
                "Welcher genaue Loesungsmitteltyp liegt an?",
                "Ich erkenne bereits einen loesemittelhaltigen Medienkontext, brauche aber den genauen Stoff.",
            )
        return (
            f"Welches Medium liegt innerhalb der Familie {family.replace('_', ' ')} genau an?",
            "Ein Medienkontext ist bereits erkannt, fuer die technische Einengung fehlt noch die genaue stoffliche Angabe.",
        )

    if status == "mentioned_unclassified":
        return (
            f"Wie ist {raw} fachlich genau einzuordnen?" if raw else "Wie ist das genannte Medium fachlich genau einzuordnen?",
            "Ich habe eine Medium-Nennung erfasst, kann sie aber noch nicht belastbar technisch einordnen.",
        )

    return None


def render_open_point_label(state: GovernedSessionState | None, field_name: str) -> str:
    if field_name == "medium" and state is not None:
        return medium_status_open_point(state)
    if field_name == "sealing_type":
        return "Dichtungstyp / Dichtprinzip"
    if field_name == "application_context":
        return "Anwendungs- und Bewegungsart präzisieren"
    if field_name == "duty_profile":
        return "Betriebsprofil"
    if field_name == "pressure_direction":
        return "Druckrichtung / Wirkprinzip"
    if field_name == "contamination":
        return "Schmutz, Partikel oder abrasive Anteile"
    if field_name == "tolerances":
        return "Rundlauf, Exzentrizitaet oder Toleranzen"
    if field_name == "industry":
        return "Branche / Einsatzumfeld"
    if field_name == "compliance":
        return "Regulatorische Anforderungen"
    if field_name == "medium_qualifiers":
        return "Mediumdetails wie Konzentration, Chloride oder Feststoffe"
    if field_name == "speed_rpm":
        return "Drehzahl der rotierenden Welle"
    if field_name == "shaft_diameter_mm":
        return "Wellendurchmesser"
    if field_name == "installation":
        return "Einbausituation"
    if field_name == "geometry_context":
        return "Geometrie / Bauform an der Dichtstelle"
    if field_name == "clearance_gap_mm":
        return "Spalt- und Toleranzbereich"
    if field_name == "counterface_surface":
        return "Gegenlaufpartner und Oberflaechen"
    if field_name == "counterface_material":
        return "Werkstoff des Gegenlaufpartners"
    if field_name == "pressure_bar":
        return "Betriebsdruck"
    if field_name == "temperature_c":
        return "Betriebstemperatur"
    return str(field_name or "").strip() or "technische Angabe"
