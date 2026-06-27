# Dichtungsregeln + Algorithmus — RWDR / DIN 3760 (Draft-Regelwerk zur Fach- & adversarialen Review)

**Status:** Entwurf, **`reviewed_internal` — NICHT `expert_signed`, NICHT produktiv.** · **Datum:** 2026-06-27
**Zweck:** das konkrete Auswahl-Regelwerk + den Algorithmus für GPT-5.5 **und** einen Dichtungstechniker
challengebar machen. Gehört zum Konzept v2 (`KONZEPT_Produktempfehlung_Bauform_DIN.md`).

> **Disziplin-Hinweis (wichtig):** Ich bin kein Dichtungstechniker. Die Werte unten sind **typische
> Referenzwerte aus Herstellerleitfäden/DIN-Sekundärquellen** (s. Quellen), die je Hersteller/Werkstoffcharge
> variieren. Jede Regel trägt **Quelle + Konfidenz + Validierungsstatus**. NICHTS davon darf live KONKRET
> empfehlen, bis ein Dichtungstechniker es signiert (`expert_signed`). Bis dahin: nur Kandidat + Defer.

---

## TEIL A — DER ALGORITHMUS

### A.0 Eingaben (Case-State) + Input-Confidence
Pflicht-/Optionalfelder; jede Userangabe trägt eine Confidence (`vom_typenschild | gemessen | aus_altdichtung
| geschätzt | unbekannt`). Schwache Confidence senkt die Konkretheit + erzwingt Defer.
`medium, temperatur_c, druck_bar, drehzahl_rpm|geschwindigkeit_ms, welle_d_mm, verschmutzung, gehaeuse,
welle_haerte_hrc?, welle_rauheit_ra?, rohtext`.

### A.1 Einheiten-Normalisierung (deterministisch, vor allen Regeln)
- Druck → bar (MPa ×10; psi ×0,06895).
- Geschwindigkeit → m/s. Falls nur `drehzahl_rpm` + `welle_d_mm`: **v = π · d · n / 60000** (d in mm, n in rpm).
- Temperatur → °C.
- **Schranke:** mehrdeutige/fehlende Einheit → nicht raten → `offene_punkte` + Defer.

### A.2 Criticality-Classifier → ggf. Abbruch
Scan `medium + rohtext + gehaeuse` auf Eskalationsbegriffe (ATEX/Ex, Lebensmittel/Pharma/FDA/EU 1935,
Druckgerät, H₂, sCO₂, sicherheitskritisch, Kerntechnik, aggressive Chemie). Treffer → `high-risk` →
**KEIN Spec**, Eskalation zur Fachprüfung. `medium` leer → mind. `caution` (Werkstoff nicht ableitbar).

### A.3 Completeness-Gate (gegen falsche Komposition aus wahren Teilregeln)
`required_inputs` der Familie prüfen. Fehlt ein kritischer Input → die davon abhängige Aussage wird **nicht**
getroffen (Teil-Screening + benannte Lücke), nie geraten.

### A.4 Eignungsgrenzen (Disqualify) — schlägt alles
Feuert eine GRENZE-Regel → die Standard-Bauform/Familie ist disqualifiziert → Defer „andere Familie mit
Hersteller prüfen". Keine Bauform-Ausgabe für die disqualifizierte Familie.

### A.5 Bauform-Kandidaten — Constraint-Resolution, KEIN Ranking
FORM-Regeln sammeln. Genau 1 eindeutiger Kandidat → Bauform. Mehrere → **Varianten + expliziter Konflikt +
offene Entscheidung** (kein „bestes" Produkt). 0 → Defer.

### A.6 Werkstoff — Medium × Temperatur, mit Negativ-Ausschlüssen
Nur wenn Medium UND Temperatur vorliegen. WERKSTOFF-Regeln sammeln, NEGATIV-Ausschlüsse abziehen. 1 → Werkstoff;
mehrere → Varianten + Konflikt; 0 → Defer.

### A.7 Lippen — aus der Bauform (A=1, AS/BS=2 …).

### A.8 Maße — KEINE Fabrikation
Welle = `observed` (User). Dichtungs-Außen-Ø/Breite werden **nie** abgeleitet (DIN-Copyright + Pseudo-Präzision)
→ `offene_punkte`: „gegen DIN 3760 + Herstellerdatenblatt verifizieren".

### A.9 Prüfpunkte (Welle/Einbau) — als offene Verifikation, nicht als Empfehlung
Surface/Härte-Anforderungen (s. Tabelle F) werden als **Prüfpunkte** ausgegeben („Welle sollte Ra 0,2–0,6 µm
+ ≥ 45 HRC erfüllen — bitte prüfen"), nicht als Selektionsregel.

### A.10 Reifegrad-Gating
Ist die genutzte Bauform-/Werkstoffregel < `expert_signed` → `freigegeben = False` + Defer „reviewed_internal,
Fachprüfung ausstehend". (Im Prototyp IMMER, da Seed = reviewed_internal.)

### Pseudocode
```
normalize_units(fall)
krit = classify_criticality(fall)
if krit in {high-risk, out-of-scope}: return escalation_spec(krit)
fehlend = required_inputs - present(fall)
if any GRENZE.fires(fall): bauform = None; defer += "Standard-RWDR disqualifiziert → andere Familie"
else:
    formen = {r.bauform for r in FORM if r.fires(fall)}
    bauform = single(formen) or (varianten+konflikt if len>1 else None)
werkstoff = resolve_material(fall) if medium and temperatur else defer("Medium/Temp fehlt")
masse = [observed(welle_d)]; offene += "OD/Breite gegen DIN/Datenblatt"
pruefpunkte = shaft_requirements()           # Tabelle F
freigegeben = False  if used_rule.reifegrad < expert_signed
return KandidatenSpec(...)                    # mit Provenance je Feld
```
### Invarianten (testbar)
grounded-only (jede Aussage hat `rule_id`) · neutral (kein Capability-Input) · no-fabrication (keine Norm-Maße)
· defer-on-incompleteness · disqualify-precedence · no-ranking · keine verbotenen Wörter.

---

## TEIL B — DAS REGELWERK: FAMILIE RWDR / DIN 3760

**required_inputs:** `medium, temperatur_c, druck_bar, welle_d_mm`. (Ohne diese: kein konkreter Spec.)

### Tabelle A — Eignungsgrenzen (GRENZE / Disqualify)
| ID | Bedingung | Konsequenz | Quelle | Konfidenz |
|---|---|---|---|---|
| G-DRUCK | `druck_bar > 0,5` | Standard-RWDR disqualifiziert (Druck) | ~7 psi ≈ 0,48 bar (ESP/Parker) | **hoch** (mehrere Quellen) |
| G-SPEED | `geschwindigkeit_ms > 12` | Standard-RWDR (NBR) disqualifiziert (Geschw.) | 10–15 m/s NBR continuous | **mittel** (Schwelle 12 gewählt; validieren) |
| G-TEMP-HI | `temperatur_c > 120` | Standard-NBR-RWDR ungeeignet → Werkstoff/Familie prüfen | Std-RWDR -40…120 °C | **mittel** |
| G-TEMP-LO | `temperatur_c < -40` | Standard-RWDR ungeeignet (Kälte) | Std-RWDR ab -40 °C | **mittel** |
| G-PV*    | `druck_bar · geschwindigkeit_ms > PV_grenz` | Druck×Geschw-Kopplung überschritten | „höhere Geschw. → kleinerer zul. Druck" | **niedrig** (PV_grenz domänen-zu-validieren) |

> *G-PV ist bewusst als offene Frage markiert — der genaue PV-Grenzwert + die Kopplung gehören in die Fachreview.

### Tabelle B — Bauform (FORM)
| ID | Bedingung | Konsequenz | Quelle | Konfidenz |
|---|---|---|---|---|
| F-A  | `verschmutzung == false` (sauber) | Form A (Elastomer-Mantel, 1 Lippe) | DIN 3760 Form A | **hoch** |
| F-AS | `verschmutzung == true` | Form AS (Zusatz-Staublippe) | Staublippe schützt Hauptlippe vor Schmutz | **hoch** |
| F-B  | `gehaeuse contains "metall"/"rau"` | Form B (Metall-Außenmantel) | Metallmantel für Bohrung/Retention | **mittel** (Bedingung zu grob — validieren) |
| F-PTFE | `temperatur_c > 200` OR `trockenlauf` OR `medium aggressiv` | PTFE-Lippe (Metallgehäuse) | PTFE: Hochtemp/Trockenlauf/Chemie/Highspeed | **mittel** |

### Tabelle C — Werkstoff (WERKSTOFF), Medium × Temperatur
| ID | Bedingung | Konsequenz | Quelle | Konfidenz |
|---|---|---|---|---|
| W-NBR | `medium contains "öl"` AND `-30 ≤ T ≤ 100` | NBR | NBR -30…100 °C, exzellent Mineralöl | **hoch** |
| W-FKM | (`medium contains "öl"` OR aggressiv/Kraftstoff) AND `100 < T ≤ 200` | FKM | FKM -20…200 °C, Kraftstoffe/Chemie | **hoch** |
| W-EPDM | `medium contains "wasser"/"glykol"/"bremsflüssigkeit"` AND `T ≤ 120` | EPDM | EPDM Wasser/Dampf/Glykol, **nicht** Öl | **hoch** |
| W-PTFE | `T > 200` OR Trockenlauf OR stark aggressiv | PTFE | PTFE Extrembereich | **mittel** |

### Tabelle D — Negatives Wissen (NEGATIV / Ausschluss)
| ID | Bedingung | Ausschluss | Quelle | Konfidenz |
|---|---|---|---|---|
| N-EPDM-OEL | `medium contains "mineralöl"/"öl"` | EPDM ausschließen | EPDM petroleum-inkompatibel | **hoch** (klassisch) |
| N-NBR-OZON | `ozon/witterung im rohtext` | NBR abwerten/ausschließen | NBR ozon-anfällig | **mittel** |
| N-NBR-POLAR | `medium contains "keton"/"ester"` | NBR ausschließen | NBR gegen polare Solventien schwach | **mittel** |

### Tabelle E — Lippen
| Bauform | Lippen |
|---|---|
| A, B | 1 (Hauptlippe; optional dünne Wiper-Lippe) |
| AS, BS | 2 (Haupt- + Staublippe) |

### Tabelle F — Prüfpunkte Welle/Einbau (PRUEFPUNKT, keine Selektion)
| ID | Anforderung | Quelle | Konfidenz |
|---|---|---|---|
| P-RA | Wellen-Rauheit **Ra 0,2–0,6 µm** (druckbelastet 0,2–0,4) | DIN 3760/3761 | **hoch** |
| P-HRC | Wellen-Härte **≥ 45 HRC** (höherer Druck 60–65) | Herstellerleitfäden | **hoch** |
| P-BORE | Bohrungs-Rauheit Ra 1,6–4 µm | Herstellerleitfäden | **mittel** |
| P-DRALL | Welle drallfrei geschliffen (Einstich/Drallfreiheit) | Leckage-Hauptursache: Oberfläche | **hoch** (qualitativ) |

### eval_traps (Familien-Tests)
- 5 bar → KEIN Standard-RWDR-Kandidat (G-DRUCK).
- 15 m/s → disqualifiziert (G-SPEED).
- Mineralöl + Wasser → **nicht** EPDM (N-EPDM-OEL).
- 220 °C → nicht NBR/FKM-Elastomer → PTFE-Pfad/Defer.
- verschmutzt + raue Metallbohrung → AS **und** B → Varianten + Konflikt (kein Ranking).
- Medium leer → kein Werkstoff (Defer).

---

## TEIL C — QUELLEN & KONFIDENZ-LEGENDE
**Konfidenz:** hoch = mehrere konsistente Quellen / klassisches Lehrbuchwissen · mittel = plausibel, Schwelle/
Bedingung gewählt → validieren · niedrig = bewusst offen, gehört in die Fachreview.
Alle Werte sind **Referenzwerte** (herstellerabhängig) — DIN-Normtext/-Tabellen sind NICHT reproduziert.

## TEIL D — BEKANNTE LÜCKEN / BITTE BESONDERS CHALLENGEN
1. **Schwellen exakt:** 0,5 bar / 12 m/s / 100↔120 °C — Grenzen sind gewählt; sind sie konservativ genug? Herstellerabhängig?
2. **PV-Kopplung (G-PV):** Druck×Geschwindigkeit ist real gekoppelt — der Algorithmus behandelt sie noch separat. Richtiger Grenzwert/Kurve?
3. **Form-B-Bedingung** (`gehaeuse contains metall`) ist zu grob — wann WIRKLICH Metallmantel?
4. **Werkstoff-Entscheidungsbaum:** Emulsionen, Additive (EP/AW), HNBR/ACM/MVQ/PTFE-Sondergrade fehlen; Medium-Detail (Konzentration/pH) ignoriert.
5. **Drehrichtung/Hydrodynamik:** hydrodynamische Rückförderrillen (drehrichtungsabhängig) fehlen.
6. **Dynamik fehlt:** Lebensdauer, Temperaturspitzen, Druckimpulse, Stillstand/Trockenlaufanlauf, Wellenschlag/Exzentrizität, Montagebedingungen.
7. **Prüfpunkte vs. Disqualify:** sollten Welle-Härte/Rauheit bei klarer Unterschreitung disqualifizieren statt nur warnen?
8. **Negatives Wissen unvollständig:** welche weiteren „nie"-Regeln sind sicherheitskritisch?
9. **Einheiten-Randfälle:** °F, kPa, U/min vs. rad/s — vollständig abgedeckt?

Sources: NBR/FKM/EPDM-Auswahl + Temp/Medien — idealbelltechnology, dxtseals, waynerubber; Betriebsgrenzen/Welle —
ESP International (Shaft Seal Handbook + Speed Guide), CV Technik, AHP Seals; Bauform/Lippen — Eclipse/Gallagher Seals.
