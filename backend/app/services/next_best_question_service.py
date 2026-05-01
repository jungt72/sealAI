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
    "speed": ("speed", "speed_rpm", "rpm"),
    "speed_or_stroke": ("speed_or_stroke", "stroke_speed", "speed", "speed_rpm"),
    "stroke": ("stroke", "stroke_length", "hub"),
    "shaft_surface": ("shaft_surface", "surface_finish", "counterface_surface"),
    "shaft_diameter": (
        "shaft_diameter",
        "shaft_diameter_mm",
        "shaft_or_stem_diameter",
    ),
    "housing_bore": ("housing_bore", "housing_bore_mm"),
    "width": ("width", "installation_width", "installation_width_mm"),
    "flange_standard": ("flange_standard", "standard_refs", "standard"),
    "flange_size_or_dimensions": (
        "flange_size_or_dimensions",
        "dn_or_dimensions",
        "dn",
        "pn",
        "nps",
        "class",
    ),
    "inner_outer_diameter": (
        "inner_outer_diameter",
        "inner_diameter",
        "outer_diameter",
        "id_od",
    ),
    "hole_pattern": ("hole_pattern", "bolt_pattern", "bolt_circle"),
    "thickness": ("thickness", "gasket_thickness"),
    "gasket_material": ("gasket_material", "material"),
    "bolt_load_or_torque": ("bolt_load_or_torque", "torque", "bolt_load"),
    "surface_roughness": ("surface_roughness", "surface_finish", "roughness"),
    "hydraulic_fluid": ("hydraulic_fluid", "medium", "medium_name"),
    "groove_dimensions": ("groove_dimensions", "geometry_context", "geometry"),
    "rod_or_piston_diameter": (
        "rod_or_piston_diameter",
        "rod_diameter",
        "piston_diameter",
        "shaft_diameter",
        "shaft_diameter_mm",
    ),
    "pressure_peaks": ("pressure_peaks", "pressure_peak", "peak_pressure"),
    "single_or_double_acting": ("single_or_double_acting", "acting_mode"),
    "wiper_or_guide_required": ("wiper_or_guide_required", "wiper", "guide_ring"),
    "water_content": ("water_content", "water", "condensate"),
    "load_direction": ("load_direction", "radial_load", "side_load"),
    "air_quality": ("air_quality", "compressed_air_quality", "condensate"),
    "lubrication": ("lubrication", "lubrication_condition", "oiled_air"),
    "friction_requirement": ("friction_requirement", "low_friction", "breakaway_force"),
    "pump_or_aggregate_type": (
        "pump_or_aggregate_type",
        "pump_type",
        "asset_type",
        "installation",
    ),
    "single_or_double_seal": ("single_or_double_seal", "seal_arrangement"),
    "flush_or_barrier_fluid": ("flush_or_barrier_fluid", "flush", "barrier_fluid"),
    "solids_or_gas_content": ("solids_or_gas_content", "contamination"),
    "viscosity": ("viscosity", "medium_viscosity"),
    "atex_or_leakage_requirement": (
        "atex_or_leakage_requirement",
        "atex_relevance",
        "leakage_requirement",
        "compliance",
    ),
    "inner_diameter": ("inner_diameter", "id", "inner_diameter_mm"),
    "cross_section": ("cross_section", "cord_diameter", "cross_section_mm"),
    "material": ("material", "candidate_materials", "gasket_material"),
    "hardness": ("hardness", "shore_hardness"),
    "static_or_dynamic": ("static_or_dynamic", "motion_type"),
    "squeeze_or_stretch": ("squeeze_or_stretch", "squeeze", "stretch"),
    "backup_ring_required": ("backup_ring_required", "backup_ring"),
    "shaft_or_stem_diameter": ("shaft_or_stem_diameter", "shaft_diameter", "stem_diameter"),
    "stuffing_box_dimensions": ("stuffing_box_dimensions", "stuffing_box", "packing_space"),
    "lubrication_or_flush": ("lubrication_or_flush", "flush", "lubrication"),
    "damage_pattern": ("damage_pattern", "symptom_class", "leakage_pattern"),
    "photo_or_evidence": ("photo_or_evidence", "photos", "evidence_refs"),
    "safety_context": ("safety_context", "safety_relevance", "atex_relevance", "environmental_risk"),
    "leak_location": ("leak_location", "leakage_location", "leak_path"),
    "failure_timing": ("failure_timing", "operating_duration", "time_to_failure"),
    "pressure_profile": ("pressure_profile", "pressure_peaks", "pulsation", "relief_rate"),
    "temperature_at_seal": ("temperature_at_seal", "seal_temperature", "temperature"),
    "motion_profile": ("motion_profile", "speed_rpm", "stroke", "start_stop_frequency"),
    "geometry_surface_context": (
        "geometry_surface_context",
        "surface_finish",
        "shaft_runout",
        "eccentricity",
        "shaft_hardness",
        "counterface_surface",
    ),
    "installation_context": ("installation_context", "assembly", "mounting", "installation_method"),
    "material_or_compound": ("material_or_compound", "material", "compound", "hardness"),
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
    "sealing_function": ("sealing_function", "seal_function", "primary_function", "function"),
    "leakage_target": (
        "leakage_target",
        "leak_target",
        "leakage_requirement",
        "leakage_rate",
        "leakage_class",
        "atex_or_leakage_requirement",
    ),
    "motion_type": ("motion_type", "movement", "static_or_dynamic"),
    "pressure_profile": (
        "pressure_profile",
        "pressure",
        "pressure_bar",
        "pressure_max_bar",
        "pressure_peak",
        "pressure_peaks",
        "pressure_nominal",
    ),
    "temperature_profile": (
        "temperature_profile",
        "temperature",
        "temperature_c",
        "temperature_min",
        "temperature_max",
    ),
    "lifetime_target": (
        "lifetime_target",
        "target_lifetime",
        "target_lifetime_hours",
        "target_lifetime_cycles",
        "service_life",
    ),
    "geometry_space": (
        "geometry_space",
        "available_space",
        "geometry",
        "geometry_context",
        "groove_dimensions",
        "shaft_diameter",
        "housing_bore",
    ),
    "tolerance_gap": (
        "tolerance_gap",
        "radial_gap_mm",
        "clearance_gap_mm",
        "shaft_runout",
        "runout_um",
        "eccentricity",
        "misalignment",
    ),
    "mounting_path": (
        "mounting_path",
        "installation_context",
        "installation_method",
        "assembly",
        "lead_in_angle_deg",
    ),
    "verification_criteria": (
        "verification_criteria",
        "acceptance_criteria",
        "lab_tests",
        "field_tests",
        "test_plan",
    ),
}

_NEW_DESIGN_FOCUS_ORDER: tuple[str, ...] = (
    "sealing_function",
    "leakage_target",
    "safety_context",
    "medium",
    "motion_type",
    "pressure_profile",
    "temperature_profile",
    "lifetime_target",
    "lubrication",
    "contamination",
    "geometry_space",
    "tolerance_gap",
    "surface_roughness",
    "mounting_path",
    "verification_criteria",
    "seal_type",
)

_TYPE_FOCUS_ORDER: dict[SealType, tuple[str, ...]] = {
    SealType.radial_shaft_seal: (
        "pressure_or_pressure_difference",
        "speed_rpm",
        "shaft_surface",
        "tolerance_gap",
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
        "flange_size_or_dimensions",
        "inner_outer_diameter",
        "hole_pattern",
        "thickness",
        "bolt_load_or_torque",
        "surface_roughness",
        "certification_requirement",
    ),
    SealType.flange_gasket: (
        "flange_standard",
        "pressure",
        "gasket_material",
        "medium",
        "temperature",
        "flange_size_or_dimensions",
        "inner_outer_diameter",
        "hole_pattern",
        "thickness",
        "bolt_load_or_torque",
        "surface_roughness",
        "certification_requirement",
    ),
    SealType.hydraulic_rod_seal: (
        "pressure",
        "hydraulic_fluid",
        "groove_dimensions",
        "rod_or_piston_diameter",
        "pressure_peaks",
        "speed_or_stroke",
        "single_or_double_acting",
        "contamination",
        "wiper_or_guide_required",
        "water_content",
    ),
    SealType.hydraulic_piston_seal: (
        "pressure",
        "hydraulic_fluid",
        "groove_dimensions",
        "rod_or_piston_diameter",
        "pressure_peaks",
        "speed_or_stroke",
        "single_or_double_acting",
        "contamination",
        "wiper_or_guide_required",
        "water_content",
    ),
    SealType.hydraulic_wiper: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "stroke",
        "contamination",
        "water_content",
        "temperature",
        "hydraulic_fluid",
    ),
    SealType.hydraulic_guide_ring: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "load_direction",
        "stroke",
        "hydraulic_fluid",
        "temperature",
        "contamination",
    ),
    SealType.hydraulic_buffer_seal: (
        "pressure",
        "pressure_peaks",
        "hydraulic_fluid",
        "groove_dimensions",
        "rod_or_piston_diameter",
        "speed_or_stroke",
        "temperature",
    ),
    SealType.pneumatic_rod_seal: (
        "pressure",
        "air_quality",
        "lubrication",
        "groove_dimensions",
        "rod_or_piston_diameter",
        "speed_or_stroke",
        "temperature",
        "friction_requirement",
    ),
    SealType.pneumatic_piston_seal: (
        "pressure",
        "air_quality",
        "lubrication",
        "groove_dimensions",
        "rod_or_piston_diameter",
        "speed_or_stroke",
        "temperature",
        "friction_requirement",
    ),
    SealType.mechanical_seal: (
        "medium",
        "pressure",
        "pump_or_aggregate_type",
        "flush_or_barrier_fluid",
        "solids_or_gas_content",
        "speed",
        "single_or_double_seal",
        "shaft_diameter",
        "temperature",
        "viscosity",
        "atex_or_leakage_requirement",
    ),
    SealType.o_ring: (
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "hardness",
        "medium",
        "temperature",
        "pressure",
        "static_or_dynamic",
        "squeeze_or_stretch",
        "backup_ring_required",
        "certification_requirement",
    ),
    SealType.x_ring: (
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "hardness",
        "medium",
        "temperature",
        "pressure",
        "static_or_dynamic",
        "squeeze_or_stretch",
    ),
    SealType.backup_ring: (
        "pressure",
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "medium",
        "temperature",
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
    "sealing_function": (
        "Welche Aufgabe soll die Dichtung vor allem erfuellen: Medium halten, Medien trennen, Schmutz fernhalten, Vakuum halten oder eine definierte Leckage begrenzen?",
        "Die Dichtfunktion steht vor der Bauart, weil sie Leckageziel, Pruefweg und Dichtungsfamilie bestimmt.",
        "text",
    ),
    "leakage_target": (
        "Welche Leckage ist noch akzeptabel, zum Beispiel keine sichtbare Leckage, Tropfgrenze, ml/min, sccm oder eine Emissionsgrenze?",
        "Ohne Leckageziel bleibt jede Neuauslegung nur eine Vororientierung und keine pruefbare Anfragebasis.",
        "text",
    ),
    "motion_type": (
        "Ist die Dichtstelle statisch, rotierend, hubend oder oszillierend?",
        "Die Bewegungsart trennt frueh zwischen Flansch-/O-Ring-, Wellendichtungs-, Hydraulik-/Pneumatik- und Gleitringdichtungspfaden.",
        "text",
    ),
    "pressure_profile": (
        "Welche Druecke wirken an der Dichtstelle: min, normal, maximal, Druckspitzen, Pulsation oder Vakuum?",
        "Das Druckprofil entscheidet ueber Extrusionsrisiko, Stuetzringbedarf und Bauartgrenzen.",
        "engineering_values",
    ),
    "temperature_profile": (
        "Welche Temperaturen treten an der Dichtstelle auf: min, normal, maximal und kurzzeitige Peaks?",
        "Das Temperaturprofil begrenzt Werkstoffe und beeinflusst Alterung, Quellung und Medienzustand.",
        "engineering_values",
    ),
    "lifetime_target": (
        "Welche Lebensdauer soll erreicht werden, zum Beispiel Betriebsstunden, Kalenderzeit oder Zyklenzahl?",
        "Das Lebensdauerziel bestimmt, ob eine grobe Vorauswahl reicht oder ein Pruef- und Validierungsplan noetig wird.",
        "text",
    ),
    "geometry_space": (
        "Welche reale Geometrie oder welcher Bauraum ist bekannt, zum Beispiel Welle, Bohrung, Nut, Einbaubreite, Flansch oder Zeichnung?",
        "Erst der reale Einbauraum macht Profil, Nut, Gegenflaeche und Herstelleranfrage pruefbar.",
        "engineering_values",
    ),
    "tolerance_gap": (
        "Welche Toleranzen, Dichtspalte, Runout- oder Fluchtungswerte sind bekannt?",
        "Spalt, Runout und Exzentrizitaet koennen wichtiger sein als der reine Werkstoffname.",
        "engineering_values",
    ),
    "mounting_path": (
        "Wie wird die Dichtung montiert: ueber Kanten, Gewinde, Fasen, Montagehuelse oder mit Montagehilfe?",
        "Der Montagepfad entscheidet, ob eine theoretisch passende Dichtung beim Einbau beschaedigt werden kann.",
        "text",
    ),
    "verification_criteria": (
        "Woran soll die Loesung spaeter gemessen werden: Lecktest, Drucktest, Lebensdauerlauf, Feldtest oder Herstellerfreigabe?",
        "Eine Neuauslegung ist erst belastbar, wenn Pruefweg und Akzeptanzkriterium klar sind.",
        "text",
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
    "flange_size_or_dimensions": (
        "Welche Flanschgroesse oder Abmessung ist bekannt, zum Beispiel DN/PN, NPS/Class oder Zeichnungsmass?",
        "Flachdichtungen brauchen eine eindeutige Anschluss- oder Zeichnungsgeometrie, bevor die Anfrage eng genug wird.",
        "text",
    ),
    "inner_outer_diameter": (
        "Sind Innen- und Aussendurchmesser der Dichtung bekannt?",
        "Innen- und Aussendurchmesser machen eine Flach- oder O-Ring-Anfrage deutlich pruefbarer.",
        "engineering_value",
    ),
    "hole_pattern": (
        "Gibt es ein Lochbild oder einen Teilkreis fuer die Dichtung?",
        "Das Lochbild verhindert, dass eine Flanschdichtung nur ueber Material und Medium beschrieben wird.",
        "text",
    ),
    "gasket_material": (
        "Welches Dichtungsmaterial ist vorgesehen oder aktuell verbaut?",
        "Das Material muss gegen Medium, Temperatur, Druck und Nachweise getrennt geprueft werden.",
        "text",
    ),
    "thickness": (
        "Welche Dichtungsdicke ist vorgesehen oder aktuell verbaut?",
        "Die Dicke beeinflusst Verpressung, Einbaulage und Austauschbarkeit.",
        "engineering_value",
    ),
    "bolt_load_or_torque": (
        "Sind Schraubenkraft, Drehmoment oder Montagevorgaben bekannt?",
        "Die Montagebelastung ist bei Flanschdichtungen ein wichtiger Pruefpunkt.",
        "text",
    ),
    "surface_roughness": (
        "Welche Oberflaeche oder Rauheit haben die Dichtflaechen?",
        "Die Dichtflaechen bestimmen mit, ob eine Flachdichtung technisch sinnvoll geprueft werden kann.",
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
    "rod_or_piston_diameter": (
        "Welcher Stangen- oder Kolbendurchmesser ist bekannt?",
        "Bei Hydraulik- und Pneumatikdichtungen ist der Durchmesser ein Grundanker fuer Profil und Nutraum.",
        "engineering_value",
    ),
    "pressure_peaks": (
        "Gibt es Druckspitzen, und wie hoch sind sie ungefaehr?",
        "Druckspitzen koennen Extrusions- und Ausfallrisiken deutlich verschieben.",
        "engineering_value",
    ),
    "speed_or_stroke": (
        "Welche Hubgeschwindigkeit, Hublänge oder Bewegung ist bekannt?",
        "Dynamische Hydraulik- und Pneumatikdichtungen brauchen den Bewegungsfall, nicht nur den Druck.",
        "text",
    ),
    "single_or_double_acting": (
        "Ist der Zylinder einfachwirkend oder doppeltwirkend?",
        "Die Wirkweise beeinflusst Druckrichtung, Dichtungsanordnung und Zusatzteile.",
        "text",
    ),
    "wiper_or_guide_required": (
        "Sind Abstreifer, Fuehrungsringe oder Stuetzringe Teil des Problems?",
        "Bei Zylindern haengt die Dichtfunktion oft mit Abstreifung, Fuehrung und Extrusionsschutz zusammen.",
        "text",
    ),
    "water_content": (
        "Gibt es Wasser, Kondensat oder starke Verschmutzung im System?",
        "Wasser und Schmutz verschieben Verschleiss- und Werkstoffrisiken deutlich.",
        "text",
    ),
    "stroke": (
        "Welcher Hub oder Bewegungsweg ist bekannt?",
        "Der Hub hilft, Abstreifer, Fuehrung und dynamische Beanspruchung einzuordnen.",
        "text",
    ),
    "load_direction": (
        "Welche Querlast oder Fuehrungsbelastung liegt an?",
        "Fuehrungsringe werden vor allem ueber Last, Spiel und Bewegung beurteilt.",
        "text",
    ),
    "air_quality": (
        "Wie ist die Druckluft beschaffen, zum Beispiel trocken, geoelt oder mit Kondensat?",
        "Bei Pneumatikdichtungen beeinflusst Luftqualitaet Reibung, Verschleiss und Werkstoffrichtung.",
        "text",
    ),
    "lubrication": (
        "Ist die Pneumatik geschmiert oder trockenlaufend?",
        "Schmierung entscheidet bei Pneumatik stark ueber Reibung und Verschleiss.",
        "text",
    ),
    "friction_requirement": (
        "Gibt es Anforderungen an geringe Reibung oder Losbrechkraft?",
        "Pneumatikdichtungen werden oft nicht nur auf Dichtheit, sondern auch auf Reibverhalten geprueft.",
        "text",
    ),
    "pump_or_aggregate_type": (
        "Um welche Pumpe oder welches Aggregat geht es?",
        "Bei Gleitringdichtungen bestimmt das Aggregat frueh, welche Angaben Hersteller wirklich brauchen.",
        "text",
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
    "viscosity": (
        "Ist die Viskositaet oder der Aggregatzustand des Mediums bekannt?",
        "Viskositaet, Dampfanteil oder Gasanteil veraendern die Bewertung einer Gleitringdichtung deutlich.",
        "text",
    ),
    "atex_or_leakage_requirement": (
        "Gibt es ATEX-, Leckage- oder Sicherheitsanforderungen?",
        "Solche Anforderungen muessen als Pruefpunkte sichtbar sein und gehoeren in die Herstellerklaerung.",
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
    "hardness": (
        "Welche Haerte ist bekannt, zum Beispiel Shore A?",
        "Die Haerte beeinflusst Verpressung, Montage und Dichtverhalten bei Elastomerdichtungen.",
        "engineering_value",
    ),
    "static_or_dynamic": (
        "Ist die Dichtung statisch oder bewegt sich die Gegenflaeche?",
        "Statische und dynamische O-Ring-Faelle brauchen unterschiedliche Nut- und Werkstoffpruefung.",
        "text",
    ),
    "squeeze_or_stretch": (
        "Sind Verpressung oder Dehnung bekannt?",
        "Verpressung und Dehnung entscheiden, ob O-Ring-Geometrie und Nut zusammen plausibel sind.",
        "engineering_value",
    ),
    "backup_ring_required": (
        "Ist ein Stuetzring vorhanden oder wegen Druck/Spalt zu pruefen?",
        "Bei hoeherem Druck kann der Stuetzring ein wichtiger Extrusionsschutz sein.",
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
    "safety_context": (
        "Gibt es Sicherheits-, Umwelt-, Brand-, ATEX- oder Personengefaehrdung im Zusammenhang mit der Leckage?",
        "Sicherheit und Anlagenzustand muessen vor jeder technischen Ursachenlogik geklaert sein.",
        "text",
    ),
    "leak_location": (
        "Wo genau tritt die Leckage auf: an der Welle, am Gehaeuse, an der Dichtlippe oder an einer Leckagebohrung?",
        "Die Leckstelle trennt Dichtungsversagen, Einbauproblem und Nebensysteme.",
        "text",
    ),
    "failure_timing": (
        "Wann tritt die Leckage auf: sofort nach Montage, beim Anfahren, im Dauerlauf, nach Druckspitzen oder erst nach bestimmter Laufzeit?",
        "Der Zeitpunkt hilft, Montage-, Betriebs-, Werkstoff- und Verschleissmechanismen zu trennen.",
        "text",
    ),
    "pressure_profile": (
        "Gab es Druckspitzen, Pulsation, Vakuum, schnelle Entlastung oder wechselnde Druckrichtung?",
        "Das reale Druckprofil ist fuer Extrusion, Umstuelpen und Gasdekompression oft entscheidend.",
        "text",
    ),
    "temperature_at_seal": (
        "Welche Temperatur lag direkt an der Dichtstelle an?",
        "Die Dichtstellentemperatur bestimmt Alterung, Medienzustand und Werkstoffgrenzen.",
        "engineering_value",
    ),
    "motion_profile": (
        "Welche Bewegung lag an: Drehzahl, Hub, Schwenkbewegung, Start-Stopp-Betrieb oder laengere Stillstaende?",
        "Bewegung und Stillstand beeinflussen Reibung, Schmierung, Trockenlauf und Verschleiss.",
        "text",
    ),
    "geometry_surface_context": (
        "Welche Masse und Gegenlaufdaten sind bekannt: Welle, Bohrung, Einbaubreite, Rauheit, Haerte, Rundlauf und Exzentrizitaet?",
        "Geometrie und Oberflaeche entscheiden, ob ein Schadensbild aus Betrieb oder Einbauraum plausibel wird.",
        "text",
    ),
    "installation_context": (
        "Wie wurde montiert: Werkzeug, Schmierung, Einbaurichtung, Kanten, Fasen und Schutz der Dichtlippe?",
        "Montagefehler koennen wie Material- oder Betriebsprobleme aussehen.",
        "text",
    ),
    "material_or_compound": (
        "Welche Werkstoff-, Compound- oder Haerteangabe ist belegt?",
        "Werkstoffnamen ohne Beleg bleiben Kandidaten fuer die Herstellerpruefung.",
        "text",
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
    "shaft_or_stem_diameter": (
        "Welcher Wellen- oder Spindeldurchmesser ist bekannt?",
        "Packungen und Ventilschaftdichtungen brauchen zuerst die Grundgeometrie der Dichtstelle.",
        "engineering_value",
    ),
    "stuffing_box_dimensions": (
        "Welche Stopfbuchs- oder Packungsraumabmessungen sind bekannt?",
        "Der Packungsraum bestimmt, welche Packungsquerschnitte ueberhaupt pruefbar sind.",
        "engineering_value",
    ),
    "lubrication_or_flush": (
        "Gibt es Schmierung, Spuelung oder Sperrmedium an der Packung?",
        "Schmierung und Spuelung beeinflussen Waerme, Verschleiss und Leckageverhalten.",
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
        CaseType.new_rfq,
        CaseType.compatibility_inquiry,
        CaseType.complaint_case,
        CaseType.failure_analysis,
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
            return (
                "safety_context",
                "leak_location",
                "photo_or_evidence",
                "seal_type",
                "failure_timing",
                "damage_pattern",
            )
        return (
            "safety_context",
            "leak_location",
            "photo_or_evidence",
            "failure_timing",
            "damage_pattern",
            "operating_conditions",
            "medium",
            "pressure_profile",
            "temperature_at_seal",
            "motion_profile",
            "geometry_surface_context",
            "installation_context",
            "material_or_compound",
            *type_order,
        )
    if case_type in {CaseType.replacement_reorder, CaseType.unknown_legacy_part}:
        return ("marking", "dimensions", "photo_or_evidence", "application_requirement")
    if case_type is CaseType.emergency_mro:
        if seal_type is SealType.unknown_seal:
            return ("seal_type",)
        if not _field_known("dimensions", known_fields):
            return ("dimensions",)
        return ("medium",)
    if case_type is CaseType.new_rfq:
        if seal_type is SealType.unknown_seal:
            return _NEW_DESIGN_FOCUS_ORDER
        return (*type_order, *_NEW_DESIGN_FOCUS_ORDER)
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
    if seal_type is SealType.unknown_seal and case_type not in {
        *_NO_ENGINEERING_QUESTION_CASE_TYPES,
        CaseType.new_rfq,
    }:
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
    if normalized in {"speed_rpm", "rpm"}:
        return "speed"
    if normalized in {"dn_or_dimensions", "dn", "pn", "nps", "class"}:
        return "flange_size_or_dimensions"
    if normalized in {"inner_diameter", "id", "inner_diameter_mm"}:
        return "inner_diameter"
    if normalized in {"outer_diameter", "id_od"}:
        return "inner_outer_diameter"
    if normalized in {"geometry", "geometry_context"}:
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
