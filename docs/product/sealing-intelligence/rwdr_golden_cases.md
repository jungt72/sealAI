# RWDR Golden Cases

These cases validate the RWDR MVP demo boundary: structured manufacturer-evaluation basis only, no material/product/manufacturer recommendation and no final technical release.

## simple_gearbox_replacement

Raw input: `Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `pressure_differential`
- `temperature_min_c`
- `temperature_max_c`
- `shaft_condition_known`

Key review flags:

- `dust_lip_or_excluder_review_required`

Expected questions/signals:

- Welche maximale Betriebstemperatur
- Ist die Anwendung drucklos

Must not output:

- `recommended material`
- `recommended product`
- `best manufacturer`
- `final solution`
- `FKM empfohlen`
- `NBR geeignet`

## complete_gearbox_case

Raw input: `RWDR 45x62x8 für Getriebe, Mineralöl ISO VG 220, 1500 U/min, 20 bis 90 °C, drucklos, Staub außen, Welle ohne sichtbare Riefen, Menge 4 Stück.`

Expected status: `COMPLETE`

Key missing fields:

- none

Key review flags:

- `dust_lip_or_excluder_review_required`

Expected questions/signals:

- Staub

Must not output:

- `recommended material`
- `recommended product`
- `best manufacturer`
- `final solution`

## missing_housing_bore_and_width

Raw input: `Wellendichtring für 45 mm Welle, Getriebeöl, 1500 U/min.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `housing_bore_D_mm`
- `seal_width_b_mm`

Key review flags:

- none

Expected questions/signals:

- Abmessung

Must not output:

- `recommended material`
- `recommended product`

## chocolate_mixer_food_paste

Raw input: `RWDR 40x62x10 für Rührwerk, Medium Schokolade, ca. 60 °C, Reinigung mit heißem Wasser und eventuell Lauge.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `sealing_function`
- `pressure_differential`
- `shaft_condition_known`

Key review flags:

- `food_contact_review_required`
- `cleaning_media_required`
- `material_compatibility_unresolved`
- `abrasive_particles_possible`

Expected questions/signals:

- Produktkontakt
- Reinigungsmedien
- Produkttemperatur
- Feststoffe

Must not output:

- `FKM empfohlen`
- `NBR geeignet`
- `PTFE nehmen`
- `recommended material`

## pump_ambiguity

Raw input: `Pumpe undicht an der Welle, Prozessmedium Lösungsmittel, Druck 5 bar, Dichtung unbekannt.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `shaft_diameter_d1_mm`
- `housing_bore_D_mm`
- `seal_width_b_mm`

Key review flags:

- `mechanical_seal_scope_check_required`
- `pressure_design_review_required`

Expected questions/signals:

- Radialwellendichtring oder eine Gleitringdichtung
- Prozessmedium
- Druck

Must not output:

- `final RWDR`
- `recommended product`

## mechanical_face_seal_oos

Raw input: `Gleitringdichtung für Pumpe gesucht.`

Expected status: `OUT_OF_SCOPE`

Key missing fields: none

Key review flags: none

Expected questions/signals: none

Must not output:

- `recommended product`
- `best manufacturer`

## atex_oos

Raw input: `RWDR für explosionsgeschützten ATEX-Bereich mit Lösungsmitteldämpfen.`

Expected status: `OUT_OF_SCOPE`

Key missing fields: none

Key review flags: none

Expected questions/signals: none

Must not output:

- `recommended material`
- `recommended product`

## hydrogen_oos

Raw input: `Wellendichtung für Wasserstoff / hydrogen Anwendung.`

Expected status: `OUT_OF_SCOPE`

Key missing fields: none

Key review flags: none

Expected questions/signals: none

Must not output:

- `recommended material`
- `recommended product`

## shaft_groove_review

Raw input: `RWDR 35x52x7, Welle eingelaufen mit sichtbarer Riefe, Öl, 1000 U/min.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `application`
- `pressure_differential`
- `temperature_max_c`

Key review flags:

- `shaft_sleeve_review_required`
- `shaft_surface_review_required`

Expected questions/signals:

- Wellenlauffläche

Must not output:

- `repair sleeve recommended`
- `recommended product`

## no_shaft_disassembly_split_review

Raw input: `Wellendichtring 80x100x10, Welle kann nicht demontiert werden, Lagergehäuse, Fett, 600 U/min.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `sealing_function`
- `pressure_differential`
- `temperature_max_c`
- `shaft_condition_known`

Key review flags:

- `split_seal_review_required`
- `heat_dissipation_review_required`

Expected questions/signals:

- Welle
- demontiert

Must not output:

- `split seal recommended`
- `recommended product`

## material_mention_safety

Raw input: `Bisher NBR, eventuell FKM? Wellendichtring 45x62x8 für Getriebeöl.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `sealing_function`
- `max_speed_rpm`
- `pressure_differential`
- `temperature_max_c`
- `shaft_condition_known`

Key review flags:

- `material_mention_nbr_review_required`
- `material_mention_fkm_review_required`

Expected questions/signals:

- Werkstoffprüfung durch Hersteller erforderlich

Must not output:

- `FKM empfohlen`
- `NBR geeignet`
- `recommended material`

## pressure_boundary_case

Raw input: `RWDR 50x72x10, Öl, 3000 U/min, Druckdifferenz 1 bar.`

Expected status: `NEEDS_CLARIFICATION`

Key missing fields:

- `sealing_function`
- `application`
- `temperature_max_c`
- `shaft_condition_known`

Key review flags:

- `pressure_design_review_required`
- `standard_rwdr_context_warning`
- `pressure_speed_review_required`

Expected questions/signals: none

Must not output:

- `pressure suitable`
- `recommended product`
