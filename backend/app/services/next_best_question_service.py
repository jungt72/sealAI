from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.api.v1.schemas.case_workspace import (
    CompletenessScoreProjection,
    CurrentStateAnalysisProjection,
    NeedsAnalysisProjection,
    NextBestQuestionProjection,
)
from app.domain.case_type import CaseType
from app.domain.seal_type import SealType


@dataclass(frozen=True, slots=True)
class NeedsCurrentStateQuestionProjection:
    needs_analysis: NeedsAnalysisProjection
    current_state_analysis: CurrentStateAnalysisProjection
    next_best_questions: list[NextBestQuestionProjection]
    completeness_score: CompletenessScoreProjection

    @property
    def event_names(self) -> tuple[str, ...]:
        events = [
            "NeedsAnalysisDerived",
            "CurrentStateAnalysisDerived",
            "CompletenessScoreComputed",
        ]
        if self.current_state_analysis.missing_fields:
            events.append("MissingInformationIdentified")
        if self.next_best_questions:
            events.append("NextBestQuestionGenerated")
        return tuple(events)


_NO_ENGINEERING_QUESTION_CASE_TYPES = {
    CaseType.no_case,
    CaseType.general_knowledge,
}

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "seal_type": ("seal_type", "sealing_type", "requested_seal_type"),
    "medium": ("medium", "medium_name", "media", "hydraulic_fluid", "oil_type"),
    "temperature": ("temperature", "temperature_c", "temperature_max"),
    "pressure": (
        "pressure",
        "pressure_bar",
        "pressure_nominal",
        "pressure_or_pressure_difference",
    ),
    "pressure_or_pressure_difference": (
        "pressure_or_pressure_difference",
        "pressure_difference",
        "pressure_bar",
        "pressure",
        "pressure_nominal",
    ),
    "speed": ("speed", "speed_rpm", "rpm", "speed_or_stroke"),
    "shaft_surface": ("shaft_surface", "surface_finish", "counterface_surface"),
    "shaft_diameter": (
        "shaft_diameter",
        "shaft_diameter_mm",
        "shaft_or_stem_diameter",
    ),
    "housing_bore": ("housing_bore", "housing_bore_mm"),
    "width": ("width", "installation_width", "installation_width_mm"),
    "flange_standard": ("flange_standard", "standard_refs", "standard"),
    "gasket_material": ("gasket_material", "material"),
    "bolt_load_or_torque": ("bolt_load_or_torque", "torque", "bolt_load"),
    "hydraulic_fluid": ("hydraulic_fluid", "medium", "medium_name"),
    "groove_dimensions": ("groove_dimensions", "geometry_context", "geometry"),
    "single_or_double_seal": ("single_or_double_seal", "seal_arrangement"),
    "flush_or_barrier_fluid": ("flush_or_barrier_fluid", "flush", "barrier_fluid"),
    "solids_or_gas_content": ("solids_or_gas_content", "contamination"),
    "inner_diameter": ("inner_diameter", "id", "inner_diameter_mm"),
    "cross_section": ("cross_section", "cord_diameter", "cross_section_mm"),
    "material": ("material", "candidate_materials", "gasket_material"),
    "damage_pattern": ("damage_pattern", "symptom_class", "leakage_pattern"),
    "photo_or_evidence": ("photo_or_evidence", "photos", "evidence_refs"),
    "marking": ("marking", "part_number", "old_part_number"),
    "dimensions": ("dimensions", "geometry", "shaft_diameter", "inner_diameter"),
    "oil_analysis_values": (
        "oil_analysis_values",
        "water_value",
        "sodium_value",
        "potassium_value",
    ),
    "oil_type": ("oil_type", "lubricant_type", "oil_grade"),
    "certification_requirement": (
        "certification_requirement",
        "compliance",
        "industry",
    ),
    "application_requirement": (
        "application_requirement",
        "application_context",
        "application_domain",
    ),
}

_TYPE_FOCUS_ORDER: dict[SealType, tuple[str, ...]] = {
    SealType.radial_shaft_seal: (
        "pressure_or_pressure_difference",
        "speed_rpm",
        "shaft_surface",
        "shaft_diameter",
        "housing_bore",
        "width",
        "medium",
        "temperature",
    ),
    SealType.flat_gasket: (
        "flange_standard",
        "pressure",
        "gasket_material",
        "medium",
        "temperature",
        "bolt_load_or_torque",
    ),
    SealType.flange_gasket: (
        "flange_standard",
        "pressure",
        "gasket_material",
        "medium",
        "temperature",
        "bolt_load_or_torque",
    ),
    SealType.hydraulic_rod_seal: (
        "pressure",
        "hydraulic_fluid",
        "groove_dimensions",
        "pressure_peaks",
        "speed_or_stroke",
        "contamination",
    ),
    SealType.hydraulic_piston_seal: (
        "pressure",
        "hydraulic_fluid",
        "groove_dimensions",
        "pressure_peaks",
        "speed_or_stroke",
        "contamination",
    ),
    SealType.mechanical_seal: (
        "medium",
        "pressure",
        "flush_or_barrier_fluid",
        "solids_or_gas_content",
        "speed",
        "single_or_double_seal",
    ),
    SealType.o_ring: (
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "medium",
        "temperature",
        "pressure",
    ),
    SealType.gland_packing: (
        "shaft_or_stem_diameter",
        "stuffing_box_dimensions",
        "medium",
        "temperature",
        "pressure",
        "speed",
        "lubrication_or_flush",
    ),
}

_QUESTION_LIBRARY: dict[str, tuple[str, str, str]] = {
    "seal_type": (
        "Um welchen Dichtungstyp geht es, zum Beispiel O-Ring, Wellendichtring, Flachdichtung, Hydraulikdichtung oder Gleitringdichtung?",
        "Der Dichtungstyp grenzt Pflichtangaben, Risiken und den Herstellerpruefpfad zuerst ein.",
        "seal_type",
    ),
    "pressure_or_pressure_difference": (
        "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        "Druck oder Druckdifferenz entscheidet bei rotierenden Wellendichtungen frueh ueber Bauartgrenzen.",
        "engineering_value",
    ),
    "pressure": (
        "Welcher Betriebsdruck liegt direkt an der Dichtstelle an?",
        "Der Druck ist ein kritischer Auslegungs- und Pruefparameter fuer die Herstellerklaerung.",
        "engineering_value",
    ),
    "speed_rpm": (
        "Welche Drehzahl liegt an der Welle an?",
        "Bei radialen Wellendichtungen bestimmt die Drehzahl Geschwindigkeit, Waermeeintrag und Verschleissrisiko.",
        "engineering_value",
    ),
    "speed": (
        "Welche Drehzahl oder Geschwindigkeit liegt an der Dichtstelle an?",
        "Geschwindigkeit beeinflusst Reibung, Waerme und Dichtprinzipauswahl.",
        "engineering_value",
    ),
    "shaft_surface": (
        "Welche Gegenlaufflaeche ist bekannt, zum Beispiel Rauheit, Haerte oder Huelse?",
        "Die Gegenlaufflaeche ist bei Wellendichtungen zentral fuer Dichtverhalten und Verschleiss.",
        "text",
    ),
    "shaft_diameter": (
        "Welcher Wellendurchmesser oder Einbaudurchmesser ist bekannt?",
        "Die Geometrie macht den Fall herstellerpruefbar und verhindert eine zu breite Vorauswahl.",
        "engineering_value",
    ),
    "housing_bore": (
        "Welche Gehaeusebohrung ist bekannt?",
        "Die Bohrung gehoert zur Grundgeometrie fuer eine pruefbare Dichtungsanfrage.",
        "engineering_value",
    ),
    "width": (
        "Welche Einbaubreite steht zur Verfuegung?",
        "Die Breite entscheidet, welche Bauformen realistisch in den Einbauraum passen.",
        "engineering_value",
    ),
    "flange_standard": (
        "Welche Flansch- oder Normgeometrie liegt vor, zum Beispiel EN, ASME, DN/PN oder Zeichnung?",
        "Bei Flachdichtungen bestimmt der Flanschstandard die Geometrie und die pruefbaren Randbedingungen.",
        "text",
    ),
    "gasket_material": (
        "Welches Dichtungsmaterial ist vorgesehen oder aktuell verbaut?",
        "Das Material muss gegen Medium, Temperatur, Druck und Nachweise getrennt geprueft werden.",
        "text",
    ),
    "bolt_load_or_torque": (
        "Sind Schraubenkraft, Drehmoment oder Montagevorgaben bekannt?",
        "Die Montagebelastung ist bei Flanschdichtungen ein wichtiger Pruefpunkt.",
        "text",
    ),
    "hydraulic_fluid": (
        "Welches Hydraulikmedium ist im Einsatz?",
        "Das Fluid bestimmt Werkstofffenster, Quellung und Verschleissrisiken.",
        "text",
    ),
    "groove_dimensions": (
        "Welche Nut- oder Einbauraumabmessungen sind bekannt?",
        "Nutgeometrie und Einbauraum sind fuer Hydraulik- und O-Ring-Faelle kritische Pruefdaten.",
        "text",
    ),
    "pressure_peaks": (
        "Gibt es Druckspitzen, und wie hoch sind sie ungefaehr?",
        "Druckspitzen koennen Extrusions- und Ausfallrisiken deutlich verschieben.",
        "engineering_value",
    ),
    "flush_or_barrier_fluid": (
        "Ist eine Spuelung, Sperrfluessigkeit oder Barriere vorgesehen?",
        "Bei Gleitringdichtungen beeinflusst die Versorgung das Dichtprinzip und die Pruefbarkeit.",
        "text",
    ),
    "solids_or_gas_content": (
        "Enthaelt das Medium Feststoffe, Gasanteile oder neigt es zur Kristallisation?",
        "Feststoffe und Gasanteile sind bei Gleitringdichtungen fruehe Risikoanker.",
        "text",
    ),
    "single_or_double_seal": (
        "Ist eine einfache oder doppelte Gleitringdichtung vorgesehen?",
        "Die Anordnung veraendert Sperr-/Spuelbedarf, Risiko und Herstellerpruefung.",
        "text",
    ),
    "inner_diameter": (
        "Welcher Innendurchmesser des O-Rings ist bekannt?",
        "Der Innendurchmesser ist eine Grundangabe fuer die O-Ring-Geometrie.",
        "engineering_value",
    ),
    "cross_section": (
        "Welche Schnurstaerke beziehungsweise welcher Querschnitt ist bekannt?",
        "Der Querschnitt bestimmt Verpressung, Nutraum und Dichtfunktion.",
        "engineering_value",
    ),
    "material": (
        "Welcher Werkstoff oder welche Compound-Angabe ist bekannt?",
        "Werkstoffnamen allein sind keine Freigabe, aber sie sind ein wichtiger Herstellerpruefpunkt.",
        "text",
    ),
    "medium": (
        "Welches Medium liegt direkt an der Dichtstelle an?",
        "Das Medium bestimmt Werkstofffenster und Kompatibilitaetsfragen.",
        "text",
    ),
    "temperature": (
        "In welchem Temperaturbereich arbeitet die Dichtstelle?",
        "Temperatur begrenzt Werkstoffe und beeinflusst Medienzustand und Alterung.",
        "engineering_value",
    ),
    "technical_profile_readiness": (
        "Welche technischen Muss-Anforderungen sind fuer die Herstellersuche bereits bekannt?",
        "Hersteller-Fit braucht zuerst ein pruefbares technisches Profil, keinen Partnernamen.",
        "text",
    ),
    "certification_requirement": (
        "Welche Nachweise oder Normanforderungen sind erforderlich, zum Beispiel FDA, ATEX oder Trinkwasser?",
        "Nachweisanforderungen beeinflussen den Hersteller-Fit, duerfen aber nicht geraten werden.",
        "text",
    ),
    "application_requirement": (
        "Welche Anwendung oder Branche soll der Hersteller technisch abdecken?",
        "Anwendungsanforderungen helfen, den Fit im SeaLAI-Partnernetzwerk fachlich einzugrenzen.",
        "text",
    ),
    "oil_analysis_values": (
        "Welche exakten Messwerte mit Einheiten liegen im Oelbericht vor, zum Beispiel Wasser, Natrium oder Kalium?",
        "Kompatibilitaetsfragen brauchen konkrete Werte, Einheiten und Messkontext; daraus folgt keine finale Freigabe.",
        "engineering_values",
    ),
    "oil_type": (
        "Um welches Oel beziehungsweise welchen Schmierstoff handelt es sich?",
        "Oeltyp und Additivsystem sind notwendig, um Berichtswerte technisch einzuordnen.",
        "text",
    ),
    "damage_pattern": (
        "Welches Schadensbild ist sichtbar, zum Beispiel Leckage, Risse, Quellung, Verschleiss oder Extrusion?",
        "Das Schadensbild strukturiert die Fehleraufnahme, ohne eine finale Ursache zu behaupten.",
        "text",
    ),
    "photo_or_evidence": (
        "Gibt es Fotos, Zeichnungen oder Befunde zur Dichtung und Einbausituation?",
        "Evidence hilft, die Ausfall- oder Ersatzteilaufnahme nachvollziehbar zu machen.",
        "evidence",
    ),
    "operating_conditions": (
        "Welche Betriebsbedingungen galten beim Ausfall, vor allem Medium, Druck, Temperatur und Laufzeit?",
        "Betriebsdaten trennen Beobachtung von Ursache und halten die Analyse herstellerpruefbar.",
        "text",
    ),
    "marking": (
        "Welche Markierung, Teilenummer oder alte Bezeichnung ist auf dem Teil erkennbar?",
        "Kennzeichnungen sind Kandidaten fuer die Identifikation, aber noch kein Identitaetsnachweis.",
        "text",
    ),
    "dimensions": (
        "Welche Abmessungen oder Fotos des Altteils liegen vor?",
        "Abmessungen und Fotos machen einen Ersatzfall pruefbar, ohne die Identitaet vorwegzunehmen.",
        "text",
    ),
}


def derive_needs_current_state_and_questions(
    state: Mapping[str, Any],
) -> NeedsCurrentStateQuestionProjection:
    case_type = _coerce_case_type(state.get("case_type"))
    seal_type = _coerce_seal_type(
        _mapping_value(state.get("seal_application_profile"), "seal_type")
    )
    known_fields = _known_fields(state)
    missing_fields = _missing_fields(state, case_type, seal_type, known_fields)
    uncertain_fields = _uncertain_fields(state, seal_type)
    conflicting_fields = _conflicting_fields(state)
    evidence_backed_fields = _evidence_backed_fields(state)
    completeness_score = _completeness_score(
        missing_fields=missing_fields,
        known_fields=known_fields,
        uncertain_fields=uncertain_fields,
        conflicting_fields=conflicting_fields,
        case_type=case_type,
    )
    current_state = CurrentStateAnalysisProjection(
        known_fields=sorted(known_fields),
        missing_fields=missing_fields,
        uncertain_fields=uncertain_fields,
        conflicting_fields=conflicting_fields,
        evidence_backed_fields=evidence_backed_fields,
        seal_type_status=_seal_type_status(state, seal_type),
        readiness_hint=_readiness_hint(state),
        confidence=round(completeness_score.score, 2),
    )
    needs = _needs_analysis(state, case_type, completeness_score.score)
    questions = _next_questions(
        case_type=case_type,
        seal_type=seal_type,
        known_fields=known_fields,
        missing_fields=missing_fields,
        state=state,
    )
    return NeedsCurrentStateQuestionProjection(
        needs_analysis=needs,
        current_state_analysis=current_state,
        next_best_questions=questions,
        completeness_score=completeness_score,
    )


def _needs_analysis(
    state: Mapping[str, Any],
    case_type: CaseType,
    completeness_score: float,
) -> NeedsAnalysisProjection:
    primary_need = {
        CaseType.no_case: "no_engineering_case",
        CaseType.general_knowledge: "general_technical_orientation",
        CaseType.new_rfq: "prepare_manufacturer_review_ready_rfq_basis",
        CaseType.manufacturer_matching: "prepare_technical_profile_for_partner_network_fit",
        CaseType.compatibility_inquiry: "qualify_compatibility_question",
        CaseType.complaint_case: "structure_complaint_intake",
        CaseType.failure_analysis: "structure_failure_intake",
        CaseType.replacement_reorder: "qualify_replacement_or_reorder_case",
        CaseType.unknown_legacy_part: "identify_legacy_part_candidates",
        CaseType.emergency_mro: "triage_urgent_mro_need",
    }.get(case_type, "clarify_sealing_case_need")
    secondary = {
        CaseType.manufacturer_matching: ["technical_fit_readiness", "open_requirements"],
        CaseType.compatibility_inquiry: ["values_units_evidence", "manufacturer_review_need"],
        CaseType.complaint_case: ["damage_evidence", "operating_context"],
        CaseType.failure_analysis: ["damage_evidence", "operating_context"],
        CaseType.replacement_reorder: ["marking_dimensions_photo", "application_context"],
        CaseType.unknown_legacy_part: ["marking_dimensions_photo", "identity_uncertainty"],
        CaseType.new_rfq: ["rfq_readiness", "open_points"],
    }.get(case_type, [])
    urgency = "emergency" if case_type is CaseType.emergency_mro else "normal"
    profile = _mapping(state.get("profile"))
    user_side = _first_present(profile, "user_side", "persona", "user_persona")
    context_side = _first_present(profile, "context_side", "buyer_or_manufacturer_context")
    confidence = 0.25 if case_type in {CaseType.unknown, CaseType.no_case} else 0.55
    if completeness_score >= 0.6:
        confidence += 0.2
    return NeedsAnalysisProjection(
        primary_need=primary_need,
        secondary_needs=secondary,
        urgency=urgency,
        user_side=user_side,
        context_side=context_side,
        confidence=round(min(confidence, 0.9), 2),
        notes=_compact(
            [
                "read-only projection; no case state mutation",
                "manufacturer review remains required for technical release",
            ]
        ),
    )


def _next_questions(
    *,
    case_type: CaseType,
    seal_type: SealType,
    known_fields: set[str],
    missing_fields: list[str],
    state: Mapping[str, Any],
) -> list[NextBestQuestionProjection]:
    if case_type in _NO_ENGINEERING_QUESTION_CASE_TYPES:
        return []

    focus_order = _scenario_focus_order(case_type, seal_type, known_fields, state)
    if not focus_order:
        focus_order = tuple(missing_fields)
    if seal_type is SealType.unknown_seal and case_type not in {
        CaseType.compatibility_inquiry,
        CaseType.replacement_reorder,
        CaseType.unknown_legacy_part,
    }:
        focus_order = ("seal_type", *focus_order)

    max_questions = 1 if case_type is CaseType.emergency_mro else 3
    questions: list[NextBestQuestionProjection] = []
    seen_focus: set[str] = set()
    for focus in focus_order:
        canonical = _canonical_focus(focus)
        if canonical in seen_focus or _field_known(canonical, known_fields):
            continue
        question = _question_for_focus(
            canonical,
            case_type=case_type,
            seal_type=seal_type,
            priority=len(questions) + 1,
        )
        if question is None:
            continue
        questions.append(question)
        seen_focus.add(canonical)
        if len(questions) >= max_questions:
            break
    return questions


def _scenario_focus_order(
    case_type: CaseType,
    seal_type: SealType,
    known_fields: set[str],
    state: Mapping[str, Any],
) -> tuple[str, ...]:
    type_order = _TYPE_FOCUS_ORDER.get(seal_type, ())
    if case_type is CaseType.manufacturer_matching:
        if seal_type is SealType.unknown_seal:
            return ("seal_type", "technical_profile_readiness")
        return (
            "technical_profile_readiness",
            "material",
            "medium",
            "certification_requirement",
            "application_requirement",
            *type_order,
        )
    if case_type is CaseType.compatibility_inquiry:
        if _looks_like_oil_report(state):
            return ("oil_analysis_values", "oil_type", "temperature", "material")
        return ("medium", "temperature", "material", "evidence_refs", *type_order)
    if case_type in {CaseType.complaint_case, CaseType.failure_analysis}:
        if seal_type is SealType.unknown_seal:
            return ("seal_type", "damage_pattern", "photo_or_evidence")
        return ("damage_pattern", "photo_or_evidence", "operating_conditions", *type_order)
    if case_type in {CaseType.replacement_reorder, CaseType.unknown_legacy_part}:
        return ("marking", "dimensions", "photo_or_evidence", "application_requirement")
    if case_type is CaseType.emergency_mro:
        if seal_type is SealType.unknown_seal:
            return ("seal_type",)
        if not _field_known("dimensions", known_fields):
            return ("dimensions",)
        return ("medium",)
    return type_order


def _question_for_focus(
    focus: str,
    *,
    case_type: CaseType,
    seal_type: SealType,
    priority: int,
) -> NextBestQuestionProjection | None:
    meta = _QUESTION_LIBRARY.get(focus)
    if meta is None:
        return None
    policy = (
        "emergency_mro_exactly_one_question"
        if case_type is CaseType.emergency_mro
        else "ask_1_to_3_targeted_questions"
    )
    return NextBestQuestionProjection(
        question=meta[0],
        reason=meta[1],
        focus_key=focus,
        priority=priority,
        expected_answer_type=meta[2],
        applies_to_case_type=case_type,
        applies_to_seal_type=seal_type,
        max_questions_policy=policy,
    )


def _known_fields(state: Mapping[str, Any]) -> set[str]:
    known: set[str] = set()
    for container_key in ("profile", "parameters"):
        for key, value in _mapping(state.get(container_key)).items():
            if value not in (None, "", [], {}):
                known.add(_canonical_focus(str(key)))
    profile = _mapping(state.get("seal_application_profile"))
    if _coerce_seal_type(profile.get("seal_type")) is not SealType.unknown_seal:
        known.add("seal_type")
    return known


def _missing_fields(
    state: Mapping[str, Any],
    case_type: CaseType,
    seal_type: SealType,
    known_fields: set[str],
) -> list[str]:
    candidates: list[str] = []
    candidates.extend(
        _string_list(_mapping(state.get("readiness")).get("missing_required_fields"))
    )
    candidates.extend(
        _string_list(
            _mapping(state.get("governance_status")).get("unknowns_release_blocking")
        )
    )
    candidates.extend(_string_list(_mapping(state.get("rfq_status")).get("open_points")))
    candidates.extend(
        _string_list(
            _mapping(state.get("seal_application_profile")).get(
                "type_specific_missing_hints"
            )
        )
    )
    candidates.extend(_scenario_focus_order(case_type, seal_type, known_fields, state))
    if seal_type is SealType.unknown_seal and case_type not in _NO_ENGINEERING_QUESTION_CASE_TYPES:
        candidates.insert(0, "seal_type")

    missing: list[str] = []
    for item in candidates:
        focus = _canonical_focus(item)
        if not focus or _field_known(focus, known_fields):
            continue
        if focus not in missing:
            missing.append(focus)
    return missing


def _uncertain_fields(state: Mapping[str, Any], seal_type: SealType) -> list[str]:
    uncertain: list[str] = []
    seal_profile = _mapping(state.get("seal_application_profile"))
    if seal_type is SealType.unknown_seal or bool(seal_profile.get("ambiguous")):
        uncertain.append("seal_type")
    confidence = _safe_float(seal_profile.get("seal_type_confidence"))
    if confidence is not None and confidence < 0.55 and "seal_type" not in uncertain:
        uncertain.append("seal_type")
    for item in _string_list(_mapping(state.get("governance_status")).get("assumptions_active")):
        focus = _canonical_focus(item)
        if focus not in uncertain:
            uncertain.append(focus)
    return uncertain


def _conflicting_fields(state: Mapping[str, Any]) -> list[str]:
    conflicts = _mapping(state.get("conflicts"))
    fields: list[str] = []
    for item in _string_list(conflicts.get("items")):
        focus = _canonical_focus(item)
        if focus and focus not in fields:
            fields.append(focus)
    if int(conflicts.get("open") or 0) > 0 and not fields:
        fields.append("open_conflict")
    return fields


def _evidence_backed_fields(state: Mapping[str, Any]) -> list[str]:
    evidence = _mapping(state.get("evidence_summary"))
    fields: list[str] = []
    for key in ("source_backed_findings", "deterministic_findings"):
        for item in _string_list(evidence.get(key)):
            focus = _canonical_focus(item)
            if focus and focus not in fields:
                fields.append(focus)
    return fields


def _completeness_score(
    *,
    missing_fields: list[str],
    known_fields: set[str],
    uncertain_fields: list[str],
    conflicting_fields: list[str],
    case_type: CaseType,
) -> CompletenessScoreProjection:
    if case_type in _NO_ENGINEERING_QUESTION_CASE_TYPES:
        return CompletenessScoreProjection(
            score=0.0,
            missing_critical_count=0,
            known_critical_count=0,
            uncertainty_count=0,
            conflict_count=0,
            notes=["no technical case completeness computed for this route"],
        )
    critical = set(missing_fields) | {
        item for item in known_fields if item in _all_critical_focus_keys()
    }
    known_critical = len([item for item in critical if _field_known(item, known_fields)])
    missing_critical = len([item for item in critical if not _field_known(item, known_fields)])
    denominator = known_critical + missing_critical + len(uncertain_fields) * 0.5 + len(conflicting_fields)
    score = 0.0 if denominator <= 0 else known_critical / denominator
    return CompletenessScoreProjection(
        score=round(max(0.0, min(1.0, score)), 2),
        missing_critical_count=missing_critical,
        known_critical_count=known_critical,
        uncertainty_count=len(uncertain_fields),
        conflict_count=len(conflicting_fields),
        notes=_compact(
            [
                "score is read-only projection metadata",
                "missing, uncertain and conflicting critical fields reduce the score",
            ]
        ),
    )


def _all_critical_focus_keys() -> set[str]:
    keys = set(_QUESTION_LIBRARY)
    for values in _TYPE_FOCUS_ORDER.values():
        keys.update(_canonical_focus(item) for item in values)
    return keys


def _seal_type_status(state: Mapping[str, Any], seal_type: SealType) -> str:
    profile = _mapping(state.get("seal_application_profile"))
    if seal_type is SealType.unknown_seal:
        return "unknown"
    if bool(profile.get("ambiguous")):
        return "ambiguous"
    confidence = _safe_float(profile.get("seal_type_confidence"))
    if confidence is not None and confidence < 0.55:
        return "uncertain"
    return "known_not_confirmed"


def _readiness_hint(state: Mapping[str, Any]) -> str:
    readiness = _mapping(state.get("readiness"))
    for key in ("readiness_label", "status", "release_status"):
        value = readiness.get(key)
        if value not in (None, "", [], {}):
            return str(value)
    governance = _mapping(state.get("governance_status"))
    return str(governance.get("release_status") or "precheck")


def _looks_like_oil_report(state: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(value)
        for container_key in ("profile", "parameters")
        for value in _mapping(state.get(container_key)).values()
        if value not in (None, "", [], {})
    ).casefold()
    return any(token in text for token in ("oel", "öl", "oil", "natrium", "sodium", "kalium", "potassium", "water", "wasser"))


def _field_known(focus: str, known_fields: set[str]) -> bool:
    canonical = _canonical_focus(focus)
    aliases = {_canonical_focus(item) for item in _FIELD_ALIASES.get(canonical, ())}
    aliases.add(canonical)
    return bool(aliases & known_fields)


def _canonical_focus(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.casefold().replace("-", "_").replace(" ", "_")
    if normalized in {"hydraulic_fluid", "hydraulic_oil"}:
        return "hydraulic_fluid"
    if normalized in {"oil_type", "lubricant_type", "oil_grade"}:
        return "oil_type"
    if normalized in {
        "oil_analysis_values",
        "water_value",
        "sodium_value",
        "potassium_value",
    }:
        return "oil_analysis_values"
    if normalized in {"pressure_or_pressure_difference", "pressure_difference"}:
        return "pressure_or_pressure_difference"
    if normalized in {"speed_rpm", "rpm", "speed_or_stroke"}:
        return "speed"
    if normalized in {"dn_or_dimensions", "geometry", "geometry_context"}:
        return "dimensions"
    for canonical, aliases in _FIELD_ALIASES.items():
        alias_set = {canonical, *aliases}
        if normalized in {item.casefold() for item in alias_set}:
            return canonical
    return normalized


def _coerce_case_type(value: Any) -> CaseType:
    if isinstance(value, CaseType):
        return value
    try:
        return CaseType(str(value or ""))
    except ValueError:
        return CaseType.unknown


def _coerce_seal_type(value: Any) -> SealType:
    if isinstance(value, SealType):
        return value
    try:
        return SealType(str(value or ""))
    except ValueError:
        return SealType.unknown_seal


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _string_list(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        candidates = []
        for key in ("field", "field_name", "focus_key", "key", "name"):
            if value.get(key):
                candidates.append(str(value[key]))
        return candidates or [str(value)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items: list[str] = []
        for item in value:
            items.extend(_string_list(item))
        return items
    return [str(value)]


def _first_present(mapping: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return str(value)
    return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact(items: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
