# Technical RWDR RFQ Brief

Case-ID: 55e7cee4-8b76-45f6-bb6b-c3abfeaf1617
Revision: 11
Exportformat: markdown
Status: NEEDS_CLARIFICATION

## Status
- NEEDS_CLARIFICATION

## Anfrageart
- leakage

## Bestätigte Anwendungskategorie
- Getriebe

## Bestätigte Angaben
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: application; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: Getriebe; source_type: user_text; status: confirmed; validation_status: confirmed; value: Getriebe
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: housing_bore_D_mm; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: 45x62x8; source_type: user_text; status: confirmed; unit: mm; validation_status: confirmed; value: 62.0
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: inside_medium; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: Öl; source_type: user_text; status: confirmed; validation_status: confirmed; value: Öl
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: max_speed_rpm; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: 1500 U/min; source_type: user_text; status: confirmed; unit: rpm; validation_status: confirmed; value: 1500.0
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: seal_width_b_mm; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: 45x62x8; source_type: user_text; status: confirmed; unit: mm; validation_status: confirmed; value: 8.0
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: sealing_function; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: undicht; source_type: user_text; status: confirmed; validation_status: confirmed; value: oil_retention
- allowed_in_brief: True; confirmation_status: confirmed; evidence_refs: ; field: shaft_diameter_d1_mm; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: 45x62x8; source_type: user_text; status: confirmed; unit: mm; validation_status: confirmed; value: 45.0

## Nicht bestätigte Angaben
- allowed_in_brief: False; blocked_reason: explicit_user_confirmation_required; confirmation_status: unconfirmed; evidence_refs: ; field: outside_environment_or_contamination; liability_bearing: False; origin: llm_extracted; provenance: missing; source_span: staub; source_type: user_text; status: candidate; validation_status: candidate; value: staubige Umgebung
- allowed_in_brief: False; blocked_reason: explicit_user_confirmation_required; confirmation_status: unconfirmed; evidence_refs: ; field: seal_family; liability_bearing: True; origin: llm_extracted; provenance: missing; source_span: Wellendichtring; source_type: user_text; status: candidate; validation_status: candidate; value: radial_shaft_seal

## Kritisch fehlende Angaben
- pressure_differential
- temperature_min_c
- temperature_max_c
- shaft_condition_known

## Hilfreich fehlende Angaben
- old_part_marking
- old_part_manufacturer
- old_part_photo_available
- old_part_cross_section_or_drawing_available
- existing_design_single_lip
- existing_design_dust_lip
- existing_design_metal_od
- existing_design_rubber_od
- existing_design_cassette
- existing_design_split
- outside_environment_or_contamination
- rotation_direction
- reversing_operation
- transient_temperature_c
- installation_orientation
- installation_situation
- shaft_removal_possible
- regulatory_or_hygienic_requirements
- quantity
- target_delivery_date
- desired_service_life_or_maintenance_interval

## Berechnete Werte
- calculation_type: exact_kinematic; field: circumferential_speed_mps; formula: v = pi * d1_mm * rpm / 60000; input_fields: shaft_diameter_d1_mm, max_speed_rpm; label: Umfangsgeschwindigkeit; not_for_final_technical_release: True; unit: m/s; value: 3.53
- field: speed_class; value: medium
- field: pressure_class; value: unknown
- field: temperature_class; value: unknown
- available_functions: n_max_from_v_allowed, mean_lip_contact_pressure, friction_force, friction_torque, friction_power, heat_flux, contact_temperature_rise, thermal_dimensional_change, metal_OD_press_fit_pressure, PTFE_PV_check, Archard_wear_approximation, wear_limited_life, leakage_upper_bound_reference; classification: requires_manufacturer_data; field: advanced_calculations; hidden: True; not_for_final_technical_release: True

## Engineering Review-Themen
- leakage_failure_intent
- technical_rfq_preparation_intent
- rwdr_generic_term_normalized
- oil_additive_material_review_if_oil_unknown
- pressure_question_required
- shaft_surface_review_required
- dust_lip_or_excluder_review_required
- failure_leakage_review_required
- learning_capture_structure_prepared
- critical_missing_pressure_differential
- critical_missing_temperature_min_c
- critical_missing_temperature_max_c
- critical_missing_shaft_condition_known
- helpful_missing_old_part_marking
- helpful_missing_old_part_manufacturer
- helpful_missing_old_part_photo_available
- helpful_missing_old_part_cross_section_or_drawing_available
- helpful_missing_existing_design_single_lip
- helpful_missing_existing_design_dust_lip
- helpful_missing_existing_design_metal_od
- helpful_missing_existing_design_rubber_od

## Empfohlene Mess- und Prüfangaben für Herstellerbewertung
- classification: workshop_measurable; field: shaft_surface_ra; method: stylus profilometer
- classification: workshop_measurable; field: shaft_surface_rz; method: stylus profilometer
- classification: workshop_measurable; field: shaft_hardness_hrc; method: Rockwell C / Vickers for coating

## Herstellerfragen
- Ist die Anwendung drucklos oder liegt Differenzdruck an?
- Welche minimale Betriebstemperatur tritt an der Dichtstelle auf?
- Welche maximale Betriebstemperatur tritt an der Dichtstelle auf?
- Ist die Wellenlauffläche eingelaufen, beschädigt oder korrodiert?
- Welches Öl oder Fett wird abgedichtet?
- Ist die Umgebung staubig, nass oder verschmutzt?
- Gibt es Staub, Schmutz oder abrasive Partikel auf der Außenseite der Dichtung?
- Welche Leckageanforderung soll der Hersteller bewerten?
- Ist sichtbare Leckage zulässig?

## Dokumentations-/Regulatorikanforderungen
- pressure_question_required
- shaft_surface_review_required
- dust_lip_or_excluder_review_required
- failure_leakage_review_required

## Leckage- und Standzeiterwartungen
- Welche Leckageanforderung soll der Hersteller bewerten?
- Ist sichtbare Leckage zulässig?

## Quellenübersicht
- confirmed_field_count: 7; confirmed_source_spans: field: application; origin: llm_extracted; source_span: Getriebe, field: housing_bore_D_mm; origin: llm_extracted; source_span: 45x62x8, field: inside_medium; origin: llm_extracted; source_span: Öl, field: max_speed_rpm; origin: llm_extracted; source_span: 1500 U/min, field: seal_width_b_mm; origin: llm_extracted; source_span: 45x62x8, field: sealing_function; origin: llm_extracted; source_span: undicht, field: shaft_diameter_d1_mm; origin: llm_extracted; source_span: 45x62x8; open_field_count: 2; quality_metrics: advanced_calculation_hidden_count: 1; brief_completeness_score: 0.64; confirmed_field_count: 8; field_extraction_count: 10; forbidden_language_violation_count: 0; measurement_recommendation_count: 3; missing_critical_field_count: 4; out_of_scope_flag_count: 0; unconfirmed_liability_field_count: 1

## Disclaimer
- Dieser Technical RWDR RFQ Brief strukturiert die Anfrage. Er enthält keine finale technische Eignungsfreigabe, keine Materialfreigabe, keine Produktempfehlung und keine Herstellerfreigabe. Die finale technische Bewertung erfolgt durch Hersteller, Händler oder eine verantwortliche technische Stelle.