# Fallkatalog-Methode — Fachwissen durch Grenzfall-Challenge aufbauen (RWDR/DIN 3760)

**Status:** Instrument + erster Katalog · `reviewed_internal` · **Datum:** 2026-06-27
**Zweck:** systematisch + überprüfbar Dichtungs-Fachwissen aufbauen. Jeder Fall klopft GEZIELT eine Regel/
Entscheidungsgrenze ab; die echte Engine-Ausgabe steht dabei, sodass GPT 5.5 (und später ein Dichtungstechniker)
pro Fall **eine konkrete Prüffrage** beantwortet → das Feedback fließt zurück in genau diese Regel.

---

## TEIL 1 — Die Methode (wiederverwendbar, das ist der Kern)
Die Schleife, die du in Zukunft immer wieder fährst:
1. **Grenzfall entwerfen** — gezielt EINE Regel/Grenze pro Fall (Schwellenwert, Medienklasse, Achsen-Entscheidung).
2. **Engine fahren** → echte Ausgabe (Level L0–L2 · Envelope · Werkstoff-Kandidaten · Defer/Eskalation).
3. **Prüffrage stellen** — pro Fall eine konkrete Domänenfrage an den Experten.
4. **Antwort → Regel-ID** — die Antwort bestätigt/korrigiert eine Regel (W-NBR, G-SPEED, OD-ELASTOMER …); Reifegrad
   der Regel steigt (`reviewed_internal` → `expert_signed`).
5. **Validierten Fall fixieren** — als rote Schranke in `tests/test_produktspec_real_cases.py` (Regression).
6. **Reifegrad-Effekt:** sind die Kern-Regeln einer Familie `expert_signed`, darf die Familie **L3** (konkret) statt nur L2.

**Fall-Vorlage** (1 Fall = 1 Regel-Sonde):
```
[ID] Szenario (1 Satz, Praxissprache)
Inputs: medium_class · T_cont/peak · p · v · Verschmutzung · Welle(Härte/Drall) · Gehäuse · Anwendungsmodus
Engine: Level · Envelope-Band · Werkstoff-Kandidaten · Defer/Eskalation
Hypothese (was ein Techniker erwartet): …
❓ Prüffrage: <die EINE Domänenfrage, die der Fall stellt>   → betrifft Regel: <ID>
```

## TEIL 2 — Challenge-Prompt für GPT 5.5
> *„Du bist erfahrener Dichtungstechniker (RWDR/DIN 3760). Unten ein Katalog von Grenzfällen mit der echten
> Ausgabe einer Regel-Engine (Antwortstufen L0=Eskalation, L1=Kandidatenraum/Defer, L2=Screening-Kandidat). Für
> JEDEN Fall: (a) ist die Hypothese fachlich richtig? (b) beantworte die Prüffrage konkret mit Wert/Regelkorrektur;
> (c) wenn die Engine-Ausgabe fachlich falsch oder gefährlich ist, sag welche Regel wie zu ändern ist; (d) markiere,
> was du ohne Originalnorm/Prüfstand NICHT sicher beurteilen kannst. Keine Höflichkeiten, nur Substanz.“*

---

## TEIL 3 — Erster Katalog (24 Grenzfälle, echte Engine-Ausgabe)
> Alle mit Standard-Setup (Welle 40, 3 m/s, sauber, belüftet, Härte 58 HRC), sofern nicht anders genannt.

### A — Werkstoff × Medium × Temperatur  (Regeln W-NBR/HNBR/FKM/EPDM/PTFE, N-*)
| ID | Medium/T | Engine | Hypothese | ❓ Prüffrage (Regel) |
|---|---|---|---|---|
| A1 | Mineralöl 80°C | L2 · NBR/HNBR | NBR (HNBR ok) | Ist HNBR hier sinnvoll im Set, oder verwirrend? (W-NBR/W-HNBR) |
| A2 | Mineralöl 110°C | L1 · HNBR/FKM | NBR-Grenze überschritten → HNBR/FKM | Ist 100°C die richtige NBR-Obergrenze, oder 120 (Kurzzeit)? (W-NBR) |
| A3 | Mineralöl 160°C | L1 · FKM | FKM | Korrekt? FKM-Bereich bis 200? (W-FKM) |
| A4 | Mineralöl 220°C | L1 · PTFE | über FKM → PTFE/Spezial | Soll das als PTFE-**Eskalation** (kein DIN-A/AS) laufen? (ESC-CHEM) |
| A5 | Wasser 40°C | L2 · EPDM | EPDM | Korrekt? (W-EPDM) |
| A6 | **Dampf 130°C** | **L1 · LEER** (FKM raus, EPDM ≤120) | EPDM-Sondergrade/PTFE? | **Soll Dampf>120°C eskalieren statt leer deferieren? Welcher Werkstoff?** (W-EPDM/ESC-CHEM) |
| A7 | Bremsfl. (Glykol) 60°C | L2 · EPDM | EPDM; NBR/FKM raus | Korrekt? Genügt „glykol_bremsfluessigkeit" als Klasse? (W-EPDM/N-NBR-BRAKE) |
| A8 | Diesel 60°C | L2 · NBR/HNBR | NBR/FKM/HNBR-Set | Fehlt FKM im Set (bei 60°C nur NBR/HNBR)? Soll FKM optional rein? (W-FKM) |
| A9 | **HFC 50°C** | **L1 · LEER** (Notiz „NBR Low-Temp") | NBR (low-temp) | **Soll HFC ≤50°C NBR-Kandidat sein? (Regel notiert, fügt aber nicht hinzu)** (W-NBR-HYDRAULIC) |
| A10 | HFD 60°C | L1 · LEER (NBR/HNBR raus) | kein NBR → Defer/Spezial | Korrekt ausgeschlossen? Welcher Werkstoff bei HFD? (W-NBR-HYDRAULIC) |
| A11 | Silikonöl 80°C | L2 · EPDM | EPDM (kein KW) | Korrekt, dass „Öl" hier NICHT EPDM ausschließt? (N-EPDM-HC) |
| A12 | „Synthetiköl" Freitext 120°C | L1 · LEER | Kandidatenraum, Additivprüfung | Richtig, dass unklare Synthetik kein Werkstoff ergibt? (Freitext-Guard) |

### B — Druck/Geschwindigkeit-Envelope  (G-*, Envelope-Bänder)
| ID | p/v/T | Engine | Hypothese | ❓ Prüffrage |
|---|---|---|---|---|
| B1 | 0 bar · 8 m/s · 80°C | L2 · green_base | sauberer Standardfall | Grenzen green_base (v≤8, T≤80) konservativ richtig? |
| B2 | 0 bar · 12 m/s · 100°C | L2 · green_extended | gerade noch Screening mit Prüfpunkt | Ist v≤12/T≤100 als green_extended-Obergrenze ok? (G-SPEED-NBR) |
| B3 | 0 bar · 12,5 m/s | L1 · orange | knapp drüber → Defer | Ist 12 die richtige NBR-Grenze, oder material-/schmierungsabhängig? |
| B4 | **0,5 bar (Sicherung ok)** | **L1 · orange** | Grenze | **Ist die rote Druckgrenze >0,5 oder ≥0,5 bar?** (G-STD-PRESSURE) |
| B5 | 0,6 bar | L1 · red | Druckdichtung/Spezial | Korrekt → red? (G-STD-PRESSURE) |
| B6 | 0,3 bar · 11 m/s · 110°C | L1 · orange | mehrfach-grenzwertig → Defer | Richtig defert? Fehlt eine echte p-v-Kurve? (G-PV) |

### C — Form/OD-Achse  (LIP-*, OD-*)
| ID | Gehäuse | Engine | Hypothese | ❓ Prüffrage |
|---|---|---|---|---|
| C3 | Alu-Gehäuse | L2 · OD=elastomer | Elastomer-OD (Wärmedehnung) | Korrekt, dass Alu → Elastomer-OD? (OD-ELASTOMER) |
| C4 | präzise Stahlbohrung | L2 · OD=metal | Metall-OD möglich | Korrekt? Wann ZWINGEND Metall-OD? (OD-METAL) |

### D — Welle/Einbau  (S-*, N-SHAFT-LEAD-PUMPING)
| ID | Fall | Engine | Hypothese | ❓ Prüffrage |
|---|---|---|---|---|
| D2 | staubig + Härte 55 HRC (A2b) | **L1 · orange** | Standard-AS-Fall → L2? | **Soll Schmutz + AS + Härte≥55 grün/L2 sein (offene Über-Blockierung)?** (Envelope/S-HRC) |
| D3 | Wellendrall | L1 (shaft gate) | Leckage unabhängig vom Typ | Korrekt, dass Drall alles blockt? (N-SHAFT-LEAD-PUMPING) |

### F — Kritikalität / Freitext
| ID | Fall | Engine | ❓ Prüffrage |
|---|---|---|---|
| F3 | „aggressive Chemie" (Freitext) | L1 · kein Elastomer-Kandidat | Richtig, dass unklassifizierte Chemie kein Material ergibt? (N-AGGRESSIVE-UNCLASSIFIED) |

## TEIL 4 — Auffällige Engine-Verhalten (bitte ZUERST challengen)
1. **A6 Dampf 130 °C → leeres Werkstoff-Set + stilles Defer.** FKM ausgeschlossen (Dampf), EPDM nur ≤120 → bei 130
   bleibt nichts. Soll das eine **PTFE/Sondergrad-Eskalation** mit Hinweis sein statt einem leeren Defer?
2. **A9 HFC 50 °C → leeres Set, obwohl die Regel „NBR low-temp" notiert.** Die Regel KOMMENTIERT, fügt NBR aber nicht
   als Kandidat hinzu → wahrscheinlich ein Implementierungs-Loch: soll HFC ≤ ~50 °C NBR-Kandidat (mit Prüfvermerk) sein?
3. **B4 0,5 bar exakt → orange/L1 (nicht red).** Boundary: ist die rote Grenze `>0,5` (aktuell) oder `≥0,5`?
4. **D2/A2b staubig + Härte → L1.** Die dokumentierte Über-Blockierung — soll der Standard-AS-Fall L2 sein?

> Diese vier sind die wertvollsten Challenge-Punkte: jede Antwort schließt direkt ein konkretes Regel-/Code-Loch.
