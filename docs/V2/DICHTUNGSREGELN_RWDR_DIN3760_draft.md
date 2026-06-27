# Dichtungsregeln + Algorithmus v3 — RWDR / DIN 3760 (Achsenmodell + Antwortstufen, `reviewed_internal`)

**Status:** Draft **v3.2**, `reviewed_internal_plus` — NICHT `expert_signed`. · **Datum:** 2026-06-27
**v3.1→v3.2 (Fachreview-Patches, im Code + als Tests umgesetzt):** A6 Dampf>120°C → Spezialeskalation (nicht leer);
A9 HFC≤50°C → NBR-Kandidat, aber `validation_required` (max L1); A10 HFD → fire-resistant Eskalation; B4 ≥0,5 bar →
red; D2 Schmutz+Härte≥55+v≤4 → L2 mit AS (Härte unbekannt bleibt L1); A8 Diesel → FKM-Alternative; A5 Wasser →
lubricity-caution; A1 Werkstoff primary/alternative getrennt; strukturell: **nie 'bare empty'** → typisiertes
`MaterialResult` (candidate_set/empty_excluded/empty_unknown/special_escalation + primary/alt/escalation/excluded).
**v3→v3.1 (Mini-Patch vor Code):** löst den echten Grenzwert-Widerspruch `v>10=orange` vs. Trap „9–11 m/s=L2".
Speed-Bänder neu (green_base v≤8 / green_extended 8<v≤12 mit Prüfpunkt / orange v>12) + harte Code-Guards
(Freitext→candidate_set_only, `derive_DIN` nur bei reviewten Achsen, Prototyp max L2). Danach: Code.
**v2→v3 (Konvergenz-Runde, GPT-5.5):** 5 strukturelle Korrekturen, KEIN Rewrite. (1) **Bauform-Achsenmodell**
statt Formtabelle (DIN-Bezeichnung erst am Ende, wenn die Achskombination reviewed ist). (2) **Freitext-
Medien-Pipeline** mit Confidence + SDS/TDS-Defer. (3) **Antwortstufen L0–L4** gegen Überblockierung (False-
Negatives). (4) **Leckage ≠ vorbeugender Ersatz** (Anwendungsmodi). (5) **FFKM/PTFE = Spezialeskalation**,
keine normale Materialentscheidung. Leitsatz bleibt: *wir wissen, wann wir es NICHT sicher wissen* — aber
**nicht zu defensiv:** der Prototyp soll sicher deferieren UND saubere Standardfälle als L2 durchlassen.

> **Disziplin:** Werte = Referenzwerte aus Fachreview + Herstellerquellen (SKF, Angst+Pfister, Freudenberg/
> Dichtomatik, Parker; Form-OD verifiziert: Pumps&Systems). Je Hersteller/Charge variabel. Nichts empfiehlt
> KONKRET live bis `expert_signed`. Der Prototyp darf max. **L1/L2**.

---

## TEIL A — ALGORITHMUS

### A.1 Antwortstufen (Response-Level) — gegen Überblockierung
```
L0 no_spec / escalation        (high-risk, out-of-scope)
L1 candidate_space_only        (Achsen offen/Konflikt → Kandidatenraum + Frageliste)
L2 low_risk_screening_candidate(grüne Envelope, Achsen eindeutig, reviewed_internal → MAX im Prototyp)
L3 expert_signed_candidate     (erst nach Fachsignatur)
L4 manufacturer_verified
```
Das Ziel ist NICHT „alles deferieren", sondern die richtige Stufe wählen. Saubere Standardfälle → L2.

### A.2 Bauform als ACHSENMODELL (nicht als Formtabelle)
Der Algorithmus entscheidet einzelne **Achsen**, NICHT direkt eine DIN-Form. Die DIN-Bezeichnung (A/AS/B/BS…)
wird **erst ganz am Ende** erzeugt — und nur, wenn die Achskombination `reviewed/expert_signed` ist. So kann
nie „AS" + „Metall-OD" widersprüchlich nebeneinander entstehen.
```
selection_axes:
  lip_configuration:    main_lip | main+dust_lip | directional_pumping_lip | ptfe_lip_special
  od_configuration:     elastomer_covered_od | metal_od | reinforced_metal_od | special_od
  pressure_configuration: pressureless_low | pressure_profile | retaining_geometry_required | outside_scope
  material_candidate_set: {…}        # nie ein Werkstoff bei Unsicherheit
  shaft_surface_confidence: ok | open_verification | gate_blocked
  application_mode: new | preventive_replacement | replacement_unknown | leakage_failure | premature_failure
final_design_code = derive_DIN(axes)   # NUR wenn alle Achsen reviewed
```

### A.3 p-v-T als ENVELOPE-BÄNDER (v3.1 — Widerspruch v>10 vs. 9–11 m/s aufgelöst)
```
green_base:     p≈0/belüftet · v ≤ 8 m/s · T_cont ≤ 80°C · Medium exakt bekannt · gute Schmierung ·
                keine Leckage/Schmutz                                            → L2 möglich
green_extended: p≈0/belüftet · 8 < v ≤ 12 m/s · T_cont ≤ 100°C · Medium exakt bekannt · gute Schmierung ·
                keine Leckage/Schmutz · Welle/Härte/Rauheit = open_verification  → L2 möglich + Prüfpunkt „v/Welle verifizieren"
yellow:         0,05 < p ≤ 0,2 bar  OR  T nahe Materialgrenze  OR  v 10–12 m/s mit Unsicherheiten → L1 Kandidatenraum
orange:         p > 0,2 bar  OR  v > 12 m/s  OR  Schmierung unbekannt  OR  Medium nicht exakt bekannt
                OR Temp/Material-Kopplung unsicher                               → keine konkrete Bauform, Frageliste
red:            p > 0,5 bar  OR  Druckpulse  OR  axiale Sicherung unbekannt bei Druckdiff.  OR  Vakuum → Spezial/Druckdichtung/Herstellerprüfung
```
> Damit bleibt der saubere Standardfall (belüftet, sauberes Mineralöl, 90 °C, 9–11 m/s) **L2-fähig mit Prüfpunkt**,
> ohne den 12-m/s-Bereich blind freizugeben.

### A.4 Freitext-Medien-Pipeline (größter LLM-Risikokanal)
```
1 extract exact phrase / trade_name
2 classify medium_class WITH confidence
3 detect_dangerous_ambiguity → ambiguous_medium_term_detected
4 if confidence < threshold OR ambiguous: ask exact medium / SDS / TDS  (kein Materialentscheid)
5 only then: material_candidate_set  (NIE ein Einzelwerkstoff aus reinem Freitext)
```
Gefährliche Mehrdeutigkeit (Beispiele): „Öl"→mineral/PAO/Ester/Bio/Hypoid/additiviert? · „Hydrauliköl"→HLP/
HFA/HFB/HFC/HFD/Phosphatester? · „Glykol"→Kühlmittel/Wasser-Glykol/Bremsflüssigkeit/HFC? · „synthetisch"→PAO/
Ester/PAG/Silikon? · „Wasser"→kalt/heiß/Dampf/Reiniger/Emulsion? · „Kraftstoff"→Diesel/Benzin/E10-E85/Bio/aromatenreich?

### A.5 Anwendungsmodus steuert die Antwortform (Leckage ≠ Ersatz)
```
leakage_failure | premature_failure → failure_mode_first MANDATORY
   (Welle/Drall/Rundlauf/Montage/Einbaurichtung/Lagerluft/Trockenanlauf/Entlüfter VOR Werkstofftausch)
preventive_replacement_same_type_no_failure → begrenztes Replacement-Screening erlaubt
   (Welle/Rauheit/Härte als open_verification, nicht als harte Sperre)
replacement_unknown_reason → erst fragen: ausgefallen/undicht ODER vorbeugend?
```

### A.6 Werkstoff = volle Signatur (gefährlichste Stelle)
```
werkstoff = resolve_material(medium_class, exact_name, T_cont, T_peak, additives_known, water_content,
                             oil_type, chemical_cluster, lubrication_state, confidence)
if mixture/unknown/additized AND no compatibility_evidence: material = candidate_set_only ; level ≤ L1
```
**Invarianten:** grounded-only · neutral · no-fabrication (auch keine DIN-Form ohne reviewte Achsen) ·
default-to-candidate-set-on-uncertainty · disqualify-precedence · no-ranking · Leckage⇒Ursache-vor-Produkt ·
keine verbotenen Wörter.

---

## TEIL B — REGELWERK

### required_inputs (Tier-1/2/3 wie v2) — aber Partial-Input ⇒ L1 statt Blockade
Tier-1: medium_class, T_cont, T_peak, p_normal, p_peak/pulse, shaft_d, speed, lubrication_state,
contamination, application_mode. Tier-2 (OD): bore_d, housing_material, bore_tol, bore_roughness,
split_housing, thermal_context. Tier-3 (Confidence): shaft_roughness, hardness, lead/drallfrei, runout,
misalignment, shaft_condition, install_direction.

### Tabelle A — Druck als DRUCKDIFFERENZ + Profil
| ID | Bedingung | Aktion | Konf. |
|---|---|---|---|
| G-BREATHER | Anwendung normal belüftet UND Entlüfter-Zustand unbekannt | Entlüfter prüfen VOR Druckannahme (klassischer Leckage-Treiber) | hoch |
| G-PRESS-DIR | Druckdifferenz UND Dichtungsorientierung unbekannt | kein Druckkandidat | hoch |
| G-PRESS-RETAIN | Druckdifferenz UND axiale Sicherung unbekannt | kein Druckkandidat (Schulter/Sicherungsring NS-seitig) | hoch |
| G-VACUUM | Vakuum/Unterdruck | kein generischer RWDR → Herstellerreview | mittel |
| (p-v-T) | siehe Envelope-Bänder A.3 | grün→L2 / gelb→L1 / orange→Defer / rot→Spezial | hoch |

### Werkstoff — Medienklasse-basiert (Tabelle C), FFKM ESKALIERT (nicht hier)
| ID | Eignung | Ausschluss/Caution | Konf. |
|---|---|---|---|
| W-NBR | Mineralöl/Fett/aliphat. KW; Hydraulik **H/HL/HLP**; Wasser ≤80°C; -30…80(100)°C | 100–120 nur caution; **HFC nur Low-Temp/spezifisch**; **HFD/Phosphatester ausschließen**; Glykol-Bremsfl., Heißdampf, polar, Ozon/UV | hoch |
| W-HNBR | wo NBR-Medien plausibel UND höhere Temp/Ozon/Alterung/Abrieb nötig (-30…150°C) | **nicht** automatisch für polar/Bremsfl./Dampf/HFD/unbekannte Synthetik | mittel |
| W-FKM | Öle/Kraftstoffe/synth./Mineralöle, -20…200°C | **Heißwasser/Dampf, Amine, Laugen, polare Solventien, Glykol-Bremsfl.** | hoch |
| W-EPDM | Wasser/Dampf/Glykol-Bremsfl./polar; ggf. **Silikonöl/-fett**; ≤120°C | **medium_class ∈ {Mineralöl, KW-Fett, Kraftstoff, PAO, aromat. KW}** (NICHT keyword „Öl") | hoch |
| W-PTFE | Spezialkandidat (Trockenlauf/Hochtemp/Chemie/Highspeed) — profil-/herstellerabhängig | kein generisches DIN-A/AS | mittel |
| ESC-CHEM | **FFKM/PTFE/Sonderdesign** | nur via SPECIAL-CHEMISTRY-ESCALATION (s. u.), **nie Default**, nur wenn Herstellerprodukt existiert | mittel |

### Hydraulikfluid-Feinregel (W-NBR-HYDRAULIC)
`H/HL/HLP → NBR` · `HFA/HFB → NBR caution` · `HFC → NBR nur Low-Temp/spezifische Validierung, sonst Defer` ·
`HFD/Phosphatester → NBR ausschließen/Defer`.

### Tabelle D — Negatives Wissen („Nie"-Regeln)
| ID | Bedingung | Aktion |
|---|---|---|
| N-EPDM-HC | medium_class ∈ {Mineralöl, KW-Fett, Kraftstoff, PAO, aromat. KW} | EPDM ausschließen |
| EPDM-AMB-OIL | Text enthält „Öl", `oil_type` unbekannt | NICHT entscheiden → oil_type erfragen |
| N-FKM-STEAM / N-FKM-AMINE | Heißwasser/Dampf / Amin/Lauge/Ammoniak | generisches FKM ausschließen (außer Sondergrade verifiziert) |
| N-NBR-BRAKE / N-NBR-OZON | Glykol-Bremsfl. / Außen-Ozon-UV exponiert | NBR ausschließen / caution |
| **N-AGGRESSIVE-UNCLASSIFIED** | „aggressiv/Chemie/Reiniger/Säure/Lauge/Lösemittel" **ohne** exakten Stoff/Konzentration | **kein Elastomer-Kandidat** → exaktes Medium/SDS/Herstellerreview |
| N-ELAST-DRY / N-DIR-LIP | Trockenlauf/Anlauf-Schmierung unbekannt / bidirektional/Drehrichtung unbekannt | kein Standard-Elastomer-Lippenkandidat / gerichtete Pumplippe ausschließen |
| N-PRESS-RETAIN / N-VACUUM | Druckdiff. ohne axiale Sicherung / Vakuum | kein Druckkandidat / Herstellerreview |
| **N-SHAFT-LEAD-PUMPING** | Wellendrall/Helix fördert Medium nach außen | **Leckagerisiko unabhängig vom Dichtungstyp** → kein Kandidat bis Welle/Drall verifiziert |
| N-LEAK-UNK | Leckage/Frühausfall, Wellenzustand unbekannt | KEINE „besserer Werkstoff"-Empfehlung vor Fehlerursachen-Check |

### SPECIAL-CHEMISTRY-ESCALATION (ersetzt FFKM-Zeile)
```
if severe_chemistry OR T extreme OR elastomers_unresolved:
  candidate_space = special rotary seal / PTFE / FFKM  (NUR wenn Herstellerprodukt existiert)
  no DIN A/AS candidate ; manufacturer_review_required = true ; level ≤ L1
```

### OD/Bauform-Achsen (korrigiert + verifiziert)
| Achse-Regel | Bedingung | Wert |
|---|---|---|
| OD-ELASTOMER | rau/verschlissen/geteilt/Leichtmetall/Wärmedehnung/Druck/dünnflüssig | elastomer_covered_od (verifiziert: Pumps&Systems/Anyseals) |
| OD-METAL | präzise/starre Stahlbohrung, exakter Sitz, Bohrung geeignet | metal_od |
| OD-UNKNOWN | Gehäusematerial/Toleranz/Rauheit unbekannt | **nicht entscheiden** → erfragen |
| LIP-AS | externer Staub/Spritz/Schmutz | main+dust_lip (**Fettfilm zwischen Lippen nötig**) |
| LIP-A | sauber | main_lip |

### Wellen-Gates — ABGESTUFT (nicht absolut)
| ID | Bedingung | Aktion |
|---|---|---|
| S-HRC-OPEN | v>4 m/s UND Härte unbekannt, sonst Low-Risk | **confidence downgrade + open_verification** (kein harter Block) |
| S-HRC-GATE | Leckage ODER Verschmutzung ODER v>10 m/s ODER Druck UND Härte/Wellenzustand unbekannt | **harter Gate** — kein sicherer Kandidat bis verifiziert |
| S-RA / S-LEAD / S-RUNOUT | Ra außerhalb 0,2–0,8 µm / Drall / Rundlauf-unbekannt bei hoher v | open_verification (Low-Risk) bzw. Gate (Leckage/Highspeed) |

### eval_traps (v3 — inkl. False-Negative-Kontrolle)
| Trap | Erwartung |
|---|---|
| belüftetes Getriebe, 9–11 m/s, sauberes Mineralöl, 90°C | **L2-Kandidat, NICHT vorschnell Defer** (gelb→grenzwertig, nicht orange) |
| 0,4 bar + 11 m/s + NBR + 110°C | orange Defer (p-v-T) |
| 0,6 bar + 1 m/s | rot → Druckdichtung |
| „Hydrauliköl" ohne Typ | Pipeline: ambiguous → HLP/HFC/HFD erfragen, kein Werkstoff |
| Silikonöl | EPDM **nicht** über „Öl"-Keyword ausschließen |
| „aggressive Chemie" ohne Stoff | N-AGGRESSIVE-UNCLASSIFIED → kein Elastomer-Kandidat |
| Vorbeugender Ersatz, gleicher Typ, kein Ausfall | begrenztes Screening (L2), Welle als open_verification |
| Leckage nach Wechsel | failure_mode_first, kein Werkstofftausch |
| schwere Chemie/Extrem | ESC-CHEM, kein DIN-A/AS, FFKM nie als simple Zeile |
| AS gewählt + Metall-OD | **Achsenmodell verhindert Widerspruch** (getrennte Achsen, DIN erst am Ende) |

---

## TEIL C — Ohne Original-DIN/Herstellerfreigabe NICHT festnagelbar
Exakte DIN-Maßreihen/Typdetails · exakte p-v-Kurven · ob ein konkreter RWDR bei 0,6 bar/12,5 m/s noch
funktioniert · Beständigkeit bei additivierten/synthetischen/Misch-Medien · Lebensdauer · FDA/EU1935/ATEX/
Druckgeräte · ob Welle/Gehäuse ohne Nacharbeit nutzbar. → Bei all dem: Kandidatenraum + Defer.

## TEIL C2 — Findings aus echten Fallbeispielen (Eval gegen die v3.1-Engine, für die Fachsignatur)
17 realistische Fälle (Getriebe/E-Motor/Pumpe/Spindel/Leckage/Lebensmittel/Dampf/Freitext) gegen die Engine:
**16/17 verhalten sich sicher + erwartungsgemäß** — saubere, vollständig bekannte Standardfälle → L2; riskante
(Hochdrehzahl, Druck, Dampf) → L1; Leckage → Failure-Mode; Lebensmittel/ATEX → L0; Freitext/unvollständig → kein
Einzelwerkstoff. Die harten Guards (kein finaler DIN-Code, kein Einzelwerkstoff, nie freigegeben, max L2) halten
auf ALLEN Fällen. Als Regressionsschranken fixiert (`tests/test_produktspec_real_cases.py`).
**Finding A2b — GELÖST (PATCH-4, Fachreview):** „Verschmutzung + Lippe=AS + Härte≥55 HRC + v≤4 + sonst grün" gilt
jetzt als **L2-Screening** (AS ist die Schmutzlösung, Härte adressiert den Verschleiß); Schmutz mit **unbekannter**
Härte bleibt konservativ **L1** (Härte erst verifizieren). Im Code + als Schranke (`test_produktspec_patches.py`).

## TEIL D-Guards — ROTE SCHRANKEN, die der Code TYPMODELL-hart erzwingen MUSS
```
G1 max_level = L2 ; review_state = reviewed_internal ; no final approval ; no manufacturer claim
G2 free-text guard:  if material.source == "llm_inferred_from_free_text":
                        material.kind = candidate_set_only ; material.single_material = null ; level <= L1
                     # L2 erst, wenn medium_class aus exakter Bezeichnung / TDS / SDS / reviewter Fachkarte
G3 derive_DIN guard: final_design_code = null  (IMMER im Prototyp)
                     erzeuge nur DIN_candidate_label = "DIN-3760-orientierter Kandidatenraum"
                     ein echtes A/AS/B/BS NUR wenn alle Achsen review_state>=reviewed_internal
                        UND keine Achse in {unknown, conflict, gate_blocked}  (→ erst expert_signed)
```

## TEIL D — Konvergenz & nächster Schritt
**Reviewer-Urteil Runde 3 + finale Bestätigung: Konvergenz erreicht, „Go" nach diesem v3.1-Patch.** Der Schritt ist —
das ist **NICHT „Produktivlogik bauen", sondern ein Regel-Engine-Prototyp mit ROTEN Schranken**, der beweist:
er deferiert sicher, begründet sauber (Provenance je Achse/Feld), erzeugt **keine** Form-/Materialkombination
ohne reviewte Achsen, blockt aber saubere Standardfälle NICHT (L2). Erst danach: Fachsignatur (→ L3) +
Lizenz/Recht + UI-Sprache → produktiv. Offene Detailpunkte (p-v-Envelope-Bänder exakt, Medienklassen-Mapping,
HNBR/HFC-Grenzen) gehen mit in die Fachsignatur, nicht in den Prototyp.
