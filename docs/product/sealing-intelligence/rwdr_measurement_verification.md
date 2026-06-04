# RWDR Measurement Verification

`MeasurementVerificationIntelligence` erzeugt Mess- und Prüfangaben für fehlende oder unsichere Felder.

Methoden:

- `shaft_diameter_d1_mm`: outside micrometer / Bügelmessschraube, `field_measurable`
- `housing_bore_D_mm`: 3-point bore gauge / Innenmessgerät, `workshop_measurable`
- `seal_width_b_mm`: caliper / Messschieber / Zeichnung, `field_measurable`
- `dynamic_runout_DRO`: dial indicator / Messuhr, `workshop_measurable`
- `static_eccentricity_STBM`: dial indicator / CMM, `workshop_measurable`
- `shaft_surface_ra` / `shaft_surface_rz`: stylus profilometer, `workshop_measurable`
- `surface_lead_directionality`: profilometer / optical inspection, `laboratory_or_manufacturer_test`
- `shaft_hardness_hrc`: Rockwell C / Vickers, `workshop_measurable`
- `material`: FTIR-ATR / DSC/TGA, `laboratory_or_manufacturer_test`
- `radial_force`: manufacturer/lab test, `laboratory_or_manufacturer_test`
- `leakage_friction_temperature`: test bench, `laboratory_or_manufacturer_test`
- `PTFE_mounting`: installation cone / bullet / sleeve check, `workshop_measurable`

Brief-Section: `Empfohlene Mess- und Prüfangaben für Herstellerbewertung`.
