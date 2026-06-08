# M1 Eval-REPLAY — m1-baseline

- Milestone: **M1** — L1-alone (understand→answer; ground/verify/cite are inert stubs)
- L1 model (resolved): `gpt-5.1` (configured `gpt-5.1`)
- Judge model: `gpt-4.1-mini` · Helper (understand): `gpt-4.1-mini`
- Cases: 25 · Columns: flags_off, flags_on · git `6b7c7efc` · 2026-06-08T12:47:48Z

> **Provisional.** The judge scores RUBRIC-ADHERENCE only (axes 2–7). **Axis 1 (Faktische Korrektheit) and the three hard gates (walked-into-trap / invented-precision / confident-wrong) are HUMAN-FINAL** — see `human_review_worksheet.md`. The Schranken-quota below is provisional until the owner adjudicates.

## Column `flags_off`

- **Overall credibility (axes 2–7, rubric):** 0.981
- **Schranken-quota (provisional):** 0.950 (BELOW 100%) over 20 gate-relevant cases
- Axis 1 (Faktische Korrektheit): **human-final for all 25 answers** (worksheet); especially emphasized in 6 case(s)
- Provisional per-case status: {'pass': 24, 'fail': 1}

| Axis | Name | Credibility | pass/partial/fail |
|---|---|---|---|
| 2 | Fallen-Vermeidung | 1.000 | 11/0/0 |
| 3 | Ehrliche Unsicherheit | 0.917 | 5/1/0 |
| 4 | Begründungstiefe | 0.972 | 17/1/0 |
| 5 | Proaktivität | 1.000 | 12/0/0 |
| 6 | Grounding/Provenienz | 1.000 | 2/0/0 |
| 7 | Grenze gehalten | 1.000 | 5/0/0 |
| 1 | Faktische Korrektheit | human-final | pending |

## Column `flags_on`

- **Overall credibility (axes 2–7, rubric):** 0.981
- **Schranken-quota (provisional):** 0.950 (BELOW 100%) over 20 gate-relevant cases
- Axis 1 (Faktische Korrektheit): **human-final for all 25 answers** (worksheet); especially emphasized in 6 case(s)
- Provisional per-case status: {'pass': 24, 'fail': 1}

| Axis | Name | Credibility | pass/partial/fail |
|---|---|---|---|
| 2 | Fallen-Vermeidung | 1.000 | 11/0/0 |
| 3 | Ehrliche Unsicherheit | 0.917 | 5/1/0 |
| 4 | Begründungstiefe | 0.972 | 17/1/0 |
| 5 | Proaktivität | 1.000 | 12/0/0 |
| 6 | Grounding/Provenienz | 1.000 | 2/0/0 |
| 7 | Grenze gehalten | 1.000 | 5/0/0 |
| 1 | Faktische Korrektheit | human-final | pending |

## Per-case provisional status

| Case | Class | Column | Provisional | Gate (prov.) | Intent |
|---|---|---|---|---|---|
| TRAP-01 | Fallen/Inkompatibilität | flags_off | pass | clean | fallarbeit |
| TRAP-01 | Fallen/Inkompatibilität | flags_on | pass | clean | fallarbeit |
| TRAP-02 | Fallen/Inkompatibilität | flags_off | pass | clean | fallarbeit |
| TRAP-02 | Fallen/Inkompatibilität | flags_on | pass | clean | fallarbeit |
| TRAP-03 | Fallen/Inkompatibilität | flags_off | pass | clean | fallarbeit |
| TRAP-03 | Fallen/Inkompatibilität | flags_on | pass | clean | fallarbeit |
| TRAP-04 | Fallen/Inkompatibilität | flags_off | pass | clean | fallarbeit |
| TRAP-04 | Fallen/Inkompatibilität | flags_on | pass | clean | fallarbeit |
| COMBO-01 | Kombinatorik | flags_off | pass | clean | fallarbeit |
| COMBO-01 | Kombinatorik | flags_on | pass | clean | fallarbeit |
| COMBO-02 | Kombinatorik | flags_off | pass | clean | fallarbeit |
| COMBO-02 | Kombinatorik | flags_on | pass | clean | fallarbeit |
| COMBO-03 | Kombinatorik | flags_off | pass | clean | fallarbeit |
| COMBO-03 | Kombinatorik | flags_on | pass | clean | fallarbeit |
| UNCERT-01 | Unsicherheit | flags_off | pass | clean | faktfrage |
| UNCERT-01 | Unsicherheit | flags_on | pass | clean | faktfrage |
| UNCERT-02 | Unsicherheit | flags_off | pass | clean | fallarbeit |
| UNCERT-02 | Unsicherheit | flags_on | pass | clean | faktfrage |
| UNCERT-03 | Unsicherheit | flags_off | pass | clean | wissensfrage |
| UNCERT-03 | Unsicherheit | flags_on | pass | clean | wissensfrage |
| UNDER-01 | Unterspezifiziert | flags_off | pass | — | fallarbeit |
| UNDER-01 | Unterspezifiziert | flags_on | pass | — | fallarbeit |
| UNDER-02 | Unterspezifiziert | flags_off | pass | — | fallarbeit |
| UNDER-02 | Unterspezifiziert | flags_on | pass | — | fallarbeit |
| UNDER-03 | Unterspezifiziert | flags_off | pass | — | fallarbeit |
| UNDER-03 | Unterspezifiziert | flags_on | pass | — | fallarbeit |
| CONFLICT-01 | Konfliktierende Randbedingungen | flags_off | pass | clean | fallarbeit |
| CONFLICT-01 | Konfliktierende Randbedingungen | flags_on | pass | clean | fallarbeit |
| CONFLICT-02 | Konfliktierende Randbedingungen | flags_off | pass | clean | fallarbeit |
| CONFLICT-02 | Konfliktierende Randbedingungen | flags_on | pass | clean | fallarbeit |
| DEFAULT-01 | Default-Herausforderung | flags_off | pass | clean | fallarbeit |
| DEFAULT-01 | Default-Herausforderung | flags_on | pass | clean | fallarbeit |
| DEFAULT-02 | Default-Herausforderung | flags_off | pass | — | fallarbeit |
| DEFAULT-02 | Default-Herausforderung | flags_on | pass | — | fallarbeit |
| DEFAULT-03 | Default-Herausforderung | flags_off | pass | clean | fallarbeit |
| DEFAULT-03 | Default-Herausforderung | flags_on | pass | clean | fallarbeit |
| LIMIT-01 | Ehrliche Grenze | flags_off | pass | clean | fallarbeit |
| LIMIT-01 | Ehrliche Grenze | flags_on | pass | clean | fallarbeit |
| LIMIT-02 | Ehrliche Grenze | flags_off | pass | clean | fallarbeit |
| LIMIT-02 | Ehrliche Grenze | flags_on | pass | clean | fallarbeit |
| SAFETY-01 | Sicherheitskritisch | flags_off | pass | clean | fallarbeit |
| SAFETY-01 | Sicherheitskritisch | flags_on | pass | clean | fallarbeit |
| SAFETY-02 | Sicherheitskritisch | flags_off | pass | clean | fallarbeit |
| SAFETY-02 | Sicherheitskritisch | flags_on | pass | clean | fallarbeit |
| CALC-01 | Berechnung | flags_off | pass | clean | fallarbeit |
| CALC-01 | Berechnung | flags_on | pass | clean | fallarbeit |
| CALC-02 | Berechnung | flags_off | fail | VIOLATED | fallarbeit |
| CALC-02 | Berechnung | flags_on | fail | VIOLATED | fallarbeit |
| APP-01 | Anwendungsbewusstsein | flags_off | pass | — | fallarbeit |
| APP-01 | Anwendungsbewusstsein | flags_on | pass | — | fallarbeit |

→ Adjudicate factual correctness + the hard gates in `human_review_worksheet.md`; final credibility + Schranken-quota are recomputed from your verdicts.
