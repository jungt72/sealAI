# sealingAI — Coverage / Bias-Map (Prio 1)

_Blind-Flecken-Karte über Eval-Anker + Fachkarten-Wissen (MedGenAI-Gedanke: kontrollierte Gegenbeispiele statt nur Wissen). Keyword-Klassifikation, approximativ — zeigt Schieflage, keine Wahrheit._


## A) Eval-Anker — 96 Fälle

**Nach Dimension (seed-file):**
- `seed_set_v0`: 25
- `retrieval_recall_v0`: 18
- `injection_v0`: 7
- `multiturn_v0`: 7
- `beratungs_ux_v0`: 5
- `calibration_v0`: 5
- `edge_v0`: 5
- `loesungserarbeitung_v0`: 5
- `archetype_v0`: 4
- `decode_v0`: 4
- `diagnose_v0`: 4
- `gegencheck_v0`: 4
- `alternativen_v0`: 3

**Nach Fallklasse:**
- ?: 18
- INJECTION: 7
- BERATUNGS_UX: 5
- CALIBRATION: 5
- EDGE: 5
- LOESUNGSERARBEITUNG: 5
- ARCHETYPE: 4
- DECODE: 4
- DIAGNOSE: 4
- GEGENCHECK: 4
- TRAP: 4
- ALTERNATIVEN: 3
- COMBO: 3
- UNCERT: 3
- UNDER: 3
- DEFAULT: 3
- CONFLICT: 2
- LIMIT: 2
- SAFETY: 2
- CALC: 2
- re-ask: Medium: 1
- re-ask: Geometrie + Drehzahl: 1
- re-ask: Medium + Temperatur über 3 Turns: 1
- Binder: Wellendurchmesser + Drehzahl → Kern: 1
- nur Drehzahl erinnert → kein Zahlenwert: 1
- b): der Lag-Turn darf nicht selbst rechnen — 'v = …' in Symbolform ohne Größenwort: 1
- M8 user-form: Eingaben via Parameter-Formular statt Chat → der Kern rechnet, das Zitat weist die Eingabe ehrlich als formular-eingegeben aus — neuer Origin-Pfad, Analog zu CALC-SYMBOL-LAG-01: 1
- APP: 1

**Achsen-Abdeckung (Fälle je Achse):**
- Achse 1 (Faktische Korrektheit): 41
- Achse 2 (Fallen-Vermeidung): 41
- Achse 3 (Ehrliche Unsicherheit): 10
- Achse 4 (Begründungstiefe): 27
- Achse 5 (Proaktivität): 22
- Achse 6 (Grounding/Provenienz): 6
- Achse 7 (Grenze gehalten): 16

**Schranken-Abdeckung (gate-relevante Fälle):**
- `confident_wrong`: 18
- `walked_into_trap`: 12
- `injection_override`: 7
- `invented_precision`: 6
- `memory_fabrication`: 6
- `edge_overreach`: 5
- `parametric_computation`: 4

**Eval — Werkstoff-Erwähnungen:**
- FKM: 29
- SiC: 24
- EPDM: 18
- NBR: 15
- PTFE: 6
- HNBR: 6
- FFKM: 6
- VMQ/Silikon: 4
- FEPM/Aflas: 1
- **⚠ 0 Treffer:** FVMQ, ACM, CR/Neopren, PU/AU/TPU, POM, PEEK

**Eval — Dichtungstyp-Erwähnungen:**
- RWDR: 20
- O-Ring: 8
- Hydraulik: 6
- Gleitring: 4
- **⚠ 0 Treffer:** Flachdichtung, Membran, Formdichtung

**Eval — Medien-Erwähnungen:**
- Mineralöl/Schmierstoff: 10
- Wasser: 8
- Lebensmittel/Trinkwasser: 6
- Hochdruckgas/RGD: 6
- Dampf/Heißwasser/SIP: 6
- Ozon/Witterung: 2
- Glykol/Kühlmittel: 2
- Säure/Lauge: 2
- Bremsflüssigkeit: 1
- **⚠ 0 Treffer:** Kraftstoff, Kältemittel

## B) Fachkarten — 47 Karten (9 reviewed + 38 provisional), 550 Claims

**kind-Verteilung (Claims):**
- `family_tendency`: 192
- `system_dependent`: 140
- `example_value`: 68
- `definition`: 64
- `safety_caution`: 24
- `qualification_required`: 24
- `regulatory_status`: 20
- `safety_nogo`: 18

**Fachkarten — Werkstoff-Abdeckung (Karten):**
- FKM: 30
- NBR: 27
- PTFE: 20
- EPDM: 19
- HNBR: 17
- VMQ/Silikon: 14
- FFKM: 8
- FEPM/Aflas: 6
- PU/AU/TPU: 6
- ACM: 4
- SiC: 4
- POM: 4
- CR/Neopren: 2
- FVMQ: 2
- PEEK: 2

**Fachkarten — Dichtungstyp-Abdeckung (Karten):**
- O-Ring: 28
- RWDR: 18
- Hydraulik: 9
- Flachdichtung: 8
- Gleitring: 6
- Formdichtung: 4
- Membran: 3

**Fachkarten — Medien-Abdeckung (Karten):**
- Wasser: 22
- Säure/Lauge: 17
- Dampf/Heißwasser/SIP: 14
- Mineralöl/Schmierstoff: 14
- Kraftstoff: 14
- Glykol/Kühlmittel: 11
- Hochdruckgas/RGD: 8
- Bremsflüssigkeit: 5
- Ozon/Witterung: 4
- Lebensmittel/Trinkwasser: 3
- Kältemittel: 3

## C) Kreuzbefund — Wissen vorhanden, aber im Eval 0 Fälle (gefährlichster blinder Fleck)

- **Werkstoff:** Wissen-aber-0-Eval → FVMQ, ACM, CR/Neopren, PU/AU/TPU, POM, PEEK
  - nur 1 Eval-Fall (dünn): FEPM/Aflas
- **Dichtungstyp:** Wissen-aber-0-Eval → Flachdichtung, Membran, Formdichtung
- **Medium:** Wissen-aber-0-Eval → Kraftstoff, Kältemittel
  - nur 1 Eval-Fall (dünn): Bremsflüssigkeit
