# Dichtungsregeln + Algorithmus v2 — RWDR / DIN 3760 (Constraint-/Defer-System, `reviewed_internal`)

**Status:** Draft **v2**, `reviewed_internal` — NICHT `expert_signed`, NICHT produktiv. · **Datum:** 2026-06-27
**v1→v2:** nach harter Fachreview (GPT 5.5, Dichtungstechniker-Lens) vom „Entscheidungsbaum" zum
**Constraint-/Defer-System** umgebaut. Leitsatz: **nicht „wir wissen den Dichtring", sondern „wir wissen,
wann wir ihn NICHT sicher wissen".** 0,5 bar / 12 m/s bleiben als konservative Screening-Gates, aber
Druck × Geschwindigkeit × Temperatur × Schmierung × Wellenzustand × Medium/Additive werden **gekoppelt**
bewertet — Default bei Unsicherheit = Defer / Kandidatenraum.

> **Disziplin:** Werte sind Referenzwerte aus Fachreview + Herstellerleitfäden (Quellen unten), je
> Hersteller/Charge variabel. Jede Regel: Quelle + Konfidenz. Nichts empfiehlt live KONKRET bis
> `expert_signed`. Die Form-OD-Korrektur (§B-Bauform) wurde unabhängig verifiziert (Pumps&Systems/SKF).

## Was sich ggü. v1 geändert hat (Review akzeptiert)
1. **Druck/Geschwindigkeit gekoppelt** (p-v), nicht isoliert; ohne validierte p-v-Kurve ab p>0,2 bar ODER
   v>10 m/s → caution/Defer. 2. **Temperatur disqualifiziert WERKSTOFF, nicht FAMILIE.** 3. **Medium →
   Medienklasse + oil_type + chemische Cluster + Additive**; unbekannt/Gemisch → Kandidatenraum, nie ein
   Werkstoff. 4. **HNBR + FFKM** ergänzt; FKM/EPDM mit harten Ausschlüssen. 5. **Form-B-Flip:** rau/geteilt/
   Leichtmetall/Wärmedehnung → **Elastomer-OD** (NICHT Metallmantel). 6. **Welle/Härte/Rauheit/Drall/Rundlauf
   werden ab Schwellen zu Gates.** 7. **Hydrodynamik/Drehrichtung** ergänzt. 8. **Leckage/Wechsel →
   Failure-Mode-first** (nicht Werkstofftausch). 9. **Druckdifferenz → axiale Sicherung** (Schulter/Sicherungsring).

---

## TEIL A — ALGORITHMUS (Constraint/Defer)
**A.0 Eingaben** (3 Tiers, §B): jede mit Confidence. **A.1 Einheiten** normalisieren (bar; v=π·d·n/60000;
°C); mehrdeutig → Defer. **A.2 Criticality** → high-risk (ATEX/Food/Pharma/Druckgerät/H₂/Säure/Lauge/
unbekanntes Gemisch …) → kein Spec. **A.3 Completeness-Gate** je Tier. **A.4 Scope-Gates (p-v-T gekoppelt)**.
**A.5 Werkstoff** = `resolve_material(...)` (volle Signatur unten). **A.6 Bauform/OD**. **A.7 Welle/Einbau-
Gates**. **A.8 Hydrodynamik/Drehrichtung**. **A.9 Maße** (Welle observed; OD/Breite nie fabriziert). **A.10
Reifegrad-Gating** (reviewed_internal → freigegeben=False).

```
# Werkstoff ist die gefährlichste Stelle — NIE nur (medium, temp):
werkstoff = resolve_material(medium_class, exact_medium_or_tradename, T_continuous, T_peak,
                             additives_known, water_content, oil_type, chemical_cluster,
                             lubrication_state, confidence)
if medium is mixture/unknown/additized AND no compatibility_evidence:
    werkstoff = candidate_set_only ; freigegeben = False

# Anwendungstyp steuert die Antwortform:
if application_type in {leakage, replacement} AND shaft_condition_unknown:
    # KEINE „besserer Werkstoff"-Empfehlung vor Fehlerursachen-Check
    return failure_mode_investigation(shaft_lead, runout, mounting, install_direction, bearing_play, dry_start)

# p-v-T gekoppelt (nicht isolierte Gates):
if no_validated_pv_curve AND (druck_bar > 0.2 OR v > 10): result = caution/defer
if druck_bar > 0.5: standard A/AS elastomer ausserhalb Screening-Scope → Druckdichtung/Haltegeometrie
if pressure_differential AND axial_retention_unknown: no_pressure_candidate (Schulter/Sicherungsring NS-seitig)
```
**Invarianten:** grounded-only · neutral · no-fabrication · **default-to-defer-on-coupling-uncertainty** ·
disqualify-precedence · no-ranking · Leckagefall ⇒ Fehlerursache vor Produktwechsel · keine verbotenen Wörter.

---

## TEIL B — REGELWERK RWDR / DIN 3760

### required_inputs (3 Tiers)
- **Tier-1 (jede Screening-Aussage):** medium_class, T_continuous, T_peak, pressure_normal, pressure_peak/pulse,
  shaft_diameter, speed (rpm|m/s), lubrication_state, contamination_external, application_type(new/replace/leakage).
- **Tier-2 (Bauform/OD):** housing_bore_d, housing_material, bore_tolerance, bore_roughness, split_housing, thermal_context.
- **Tier-3 (Vertrauensstufe):** shaft_roughness, shaft_hardness, shaft_lead/drallfrei, runout, misalignment,
  shaft_condition(groove/corrosion), install_direction.
> Fehlt Tier-1 → nur „Teil-Screening, Kandidatenraum offen".

### Tabelle A — Scope-Gates (Druck/Geschw/Temp GEKOPPELT)
| ID | Bedingung | Konsequenz | Quelle | Konf. |
|---|---|---|---|---|
| G-PV-UNVALIDATED | keine p-v-Kurve UND (p>0,2 bar ODER v>10 m/s) | nur caution/Defer | SKF: p-v gekoppelt (10 psi@5 m/s) | hoch |
| G-STD-PRESSURE | p>0,5 bar | Standard A/AS-Elastomer **außerhalb Screening-Scope** → Druckdichtung/Haltegeometrie | ~7 psi≈0,48 bar; A+P „<0,5 bar" | hoch |
| G-PRESS-RETAIN | Druckdifferenz UND axiale Sicherung unbekannt | kein Druckkandidat (Schulter/Sicherungsring NS-seitig) | SKF | hoch |
| G-SPEED-NBR | Werkstoff=NBR UND v>10–12 m/s | kein Standard-NBR-A/AS | A+P/Parker NBR ≤10–12 | hoch |
| G-SPEED-UNK | v>10 m/s UND Werkstoff unbekannt | kein finaler Werkstoff; Material/Design-Review | — | mittel |
| G-TEMP-MAT | Temperatur disqualifiziert **Werkstoff**, nicht Familie | (→ Tabelle C) | A+P: Einzelwerte sind Maxima | hoch |

### Medien-Klassen-Taxonomie (Pflicht vor jeder Materialaussage)
`oil_type`: mineral_low_additive · mineral_high_additive · synthetic_PAO · ester · bio · hypoid · ATF ·
hydraulic_HL/HLP · hydraulic_HFA/HFB/HFC/HFD · fuel_diesel · fuel_gasoline · aromatic_fuel · unknown_oil.
`chemical_cluster`: hot_water · steam · glycol · water_glycol · glycol_brake_fluid · solvent_polar ·
solvent_nonpolar · ketone · amine · acid · alkali · food_contact · unknown_mixture.
> **unknown_oil / unknown_mixture / additiviert ohne Beleg → nur Kandidatenraum, freigegeben=False.**

### Tabelle C — Werkstoff (mit harten Ausschlüssen)
| ID | Eignung | Ausschluss (wichtig!) | Konf. |
|---|---|---|---|
| W-NBR | Mineralöl/Fett/HLP/aliphat. KW, -30…80(100)°C; 100–120 nur caution | Glykol-Bremsfl., HFD, Heißdampf, polar, Ozon/UV, aromat./chlor. | hoch |
| W-HNBR | NBR-Medien + höhere Temp/Ozon/Abrieb, -30…150°C | (wie NBR, enger) | mittel (A+P/Freudenberg) |
| W-FKM | Öle/Kraftstoffe/synth./Mineralöle, -20/-25…200°C | **Heißwasser/Dampf, Amine, Laugen, polare Solventien, Glykol-Bremsfl.** | hoch |
| W-EPDM | Wasser/Dampf/Glykol-Bremsfl./polar, ≤120°C | **JEDER Kohlenwasserstoff: Öl/Fett/Kraftstoff** | hoch |
| W-PTFE | Spezialkandidat: Trockenlauf/Hochtemp/Chemie/Highspeed — Herstellerreview | nicht generisches DIN-A/AS | mittel |
| W-FFKM | nur als High-Cost-High-Chemie-Kandidat | **nie Default** | mittel |

### Tabelle D — Negatives Wissen („Nie"-Regeln, schützen am meisten)
| ID | Bedingung | Aktion |
|---|---|---|
| N-EPDM-HC | Mineralöl/Fett/Kraftstoff | EPDM ausschließen |
| N-FKM-STEAM | Heißwasser/Dampf | generisches FKM ausschließen (außer Sondergrade verifiziert) |
| N-FKM-AMINE | Amin/Lauge/Ammoniak | generisches FKM ausschließen |
| N-NBR-BRAKE | Glykol-Bremsflüssigkeit | NBR ausschließen |
| N-NBR-OZON | Außen/Ozon/UV exponiert | NBR caution/ausschließen (je Kritikalität) |
| N-ELAST-DRY | Trockenlauf / Schmierung beim Anlauf unbekannt | kein Standard-Elastomer-Lippenkandidat |
| N-DIR-LIP | bidirektional / Drehrichtung unbekannt | gerichtete Pumplippe ausschließen |
| N-PRESS-RETAIN | Druckdifferenz, axiale Sicherung unbekannt | kein Druckkandidat |
| N-LEAK-UNK | Wechsel/Leckage, Wellenzustand unbekannt | KEINE „besserer Werkstoff"-Empfehlung vor Fehlerursachen-Check |

### Tabelle B-OD — Bauform / Außendurchmesser (KORRIGIERT)
| ID | Bedingung | Konsequenz | Quelle | Konf. |
|---|---|---|---|---|
| F-A | sauber, Öl/Fett, low pressure, geeignete Bohrung | Form A (1 Lippe) | DIN 3760 | hoch |
| F-AS | externer Staub/Spritz/Schmutz | Form AS (Staublippe) — **Fettfilm zwischen den Lippen nötig** | DIN 3760 | hoch |
| **F-OD-ELASTOMER** | **rau/verschlissen/geteilt/Leichtmetall/Wärmedehnung/Druck/dünnflüssig** | **Elastomer-ummantelter OD** | Pumps&Systems, Anyseals (verifiziert) | hoch |
| F-OD-METAL | präzise/starre Stahlbohrung, exakter Sitz nötig, Bohrung geeignet | Metall-OD möglich | Pumps&Systems | hoch |
| F-OD-UNKNOWN | Gehäusematerial/Toleranz/Rauheit unbekannt | **A/B/C NICHT entscheiden** → nach Bohrung fragen | — | hoch |
| F-PRESSURE | Druck vorhanden | Druck-RWDR/Stützring/Haltegeometrie | SKF | hoch |
| F-PTFE | Trockenlauf/Hochtemp/Chemie/Highspeed | PTFE-Lippe (Spezial, kein generisches A/AS) | A+P | mittel |

### Tabelle E — Welle/Einbau als GATES (nicht nur Prüfpunkte)
| ID | Bedingung | Aktion | Quelle |
|---|---|---|---|
| S-RA | Wellen-Ra außerhalb 0,2–0,8 µm / Rz 1–5 / drallbehaftet | kein sicherer Kandidat; Oberfläche prüfen | A+P/SKF |
| S-HRC-SPEED | v>4 m/s UND Härte unbekannt | kein sicherer Kandidat; Härte verifizieren | A+P (≥45, bei Schmutz/>4 m/s ≥55 HRC) |
| S-HRC-DIRT | Verschmutzung UND Härte <55 HRC | caution/high-risk Verschleiß; kein finaler Kandidat | A+P |
| S-RUNOUT | hohe v UND Rundlauf/Fluchtung unbekannt | kein konkreter Kandidat; Rundlauf/Lagerabstand erfragen | SKF |
| S-LEAD | Drall/Helix vorhanden ODER unbekannt bei Leckagefall | Troubleshooting-Priorität; kein Produkttausch als Primärantwort | A+P |

### Tabelle F — Hydrodynamik / Drehrichtung
| ID | Bedingung | Aktion |
|---|---|---|
| H-DIR | gerichtete Rückförderhilfen UND Drehrichtung unbekannt | kein Kandidat / Drehrichtung erfragen |
| H-REV | Reversier-/Bidirektionalbetrieb | unidirektionale Pumplippe ausschließen (außer verifiziert) |
| H-LEAK | Leckage UND möglicher Wellendrall | Drall/Rundlauf/Montage vor Werkstofftausch |

**Lippen:** A/B=1 (+optional Wiper), AS/BS=2. **Maße:** Welle=observed; OD/Breite nie abgeleitet → „gegen DIN/Datenblatt".

### eval_traps (erweitert)
| Trap | Erwartung |
|---|---|
| 0,4 bar + 11 m/s + NBR + 110 °C | kein „passt" → p-v-/Temp-Defer |
| 0,6 bar + 1 m/s | Standard-A/AS außer Scope, aber Druckdichtung möglich |
| 15 m/s + FKM + gute Schmierung | nicht pauschal RWDR disqualifizieren → Spezialprüfung |
| Wasser + 90 °C + Mineralölspuren | EPDM nicht eindeutig → Medienklärung |
| Heißwasser/Dampf + FKM | FKM ausschließen/Defer |
| Glykol-Bremsfl. + NBR/FKM | ausschließen/Defer; EPDM nur bei passender Spez. |
| Synthetiköl unbekannt + 120 °C | kein NBR; FKM/HNBR nur Kandidatenraum + Additivprüfung |
| Leckage nach Wechsel, gleiche Maße | erst Welle/Drall/Montage/Rundlauf; KEINE Werkstoffempfehlung |
| verschmutzt + v>4 m/s + Härte unbekannt | keine Kandidaten-Sicherheit; Härte prüfen |
| raue Leichtmetallbohrung | NICHT Form B → Elastomer-OD-Konflikt/Defer |

---

## TEIL C — Was OHNE Original-DIN / Herstellerfreigabe NICHT festnagelbar ist
Exakte DIN-3760-Maßreihen + Typdetails · exakte p-v-Kurven je Bauform/Werkstoff/Lippe · ob ein konkreter RWDR
bei 0,6 bar / 12,5 m/s noch funktioniert (design-/temp-/schmierungs-/lebensdauerabhängig) · Materialbeständigkeit
bei realen additivierten/synthetischen/Misch-Medien · Lebensdauerprognosen · FDA/EU1935/ATEX/Druckgeräte ·
ob vorhandene Welle/Gehäuse ohne Nacharbeit nutzbar sind. → Bei all dem: Kandidatenraum + Defer, nie konkret.

## TEIL D — Offene Fragen für Runde 3
1. p-v(-T)-Kurve: ein generischer konservativer Schwellensatz, oder pro Werkstoff/Bauform? 2. Medienklassen-
Mapping: wie führt der User es ein (Freitext→Klasse-Klassifikator mit Confidence?) ohne Fehlklassifikation?
3. HNBR/FFKM-Eignungsgrenzen. 4. Leckage-Modus als eigener Pfad — reicht die Failure-Mode-Checkliste? 5. Welche
Tier-1-Inputs sind im Chat realistisch erhebbar, ohne den User zu überfordern? 6. Reicht „candidate_set_only"
als UX, oder braucht es eine Vertrauens-Ampel?

**Quellen (Fachreview + Verifikation):** Betriebsgrenzen/p-v + Welle — SKF, Angst+Pfister (A+P), ESP; Werkstoffe/
Ausschlüsse — Freudenberg/Dichtomatik, Parker, idealbell/dxtseals; Form-OD (verifiziert) — Pumps&Systems
(Metal-OD vs Rubber-OD, Alu/Wärmedehnung, Splitring), Anyseals; Bauformen — DIN 3760 / Eclipse/Gallagher.
