# M1 Eval-REPLAY — m1-baseline

- Milestone: **M1** — L1-alone (understand→answer; ground/verify/cite are inert stubs)
- L1 model (resolved): `gpt-5.1` (configured `gpt-5.1`)
- Judge model: `gpt-4.1-mini` · Helper (understand): `gpt-4.1-mini`
- Cases: 25 · Columns: flags_off, flags_on · git `6b7c7efc` · 2026-06-08T12:47:48Z

> **Provisional.** The judge scores RUBRIC-ADHERENCE only (axes 2–7). **Axis 1 (Faktische Korrektheit) and the three hard gates (walked-into-trap / invented-precision / confident-wrong) are HUMAN-FINAL** — see `human_review_worksheet.md`. The Schranken-quota below is provisional until the owner adjudicates.

## Adjudication — first-pass (deep audit deferred)

> **This M1 baseline is PROVISIONAL until the deep audit (M2/L3).** Axis 1 (Faktische Korrektheit) and the three hard gates are HUMAN-FINAL; unadjudicated units keep their provisional figure and are flagged `human-adjudication pending`. Credibility (axes 2–7) is rubric/judge-final and carried unchanged.

- Run label: **first-pass adjudication — deep audit deferred** · verdicts parsed from worksheet: **0** · 2026-06-08T14:01:54Z

### Column `flags_off` — final

- **Final credibility (axes 2–7, carried):** 0.981
- **Final Schranken-quota:** 0.950 (BELOW 100%) over 20 gate cases (adjudicated 0, pending 20)
- Human-final units: **0 adjudicated · 20 pending** (of 20); 5 rubric-final
- Axis 1 disposition: pass 0 · fail 0 · pending 6 · n/a 19
- Final per-case status: {'pass': 24, 'fail': 1}

### Column `flags_on` — final

- **Final credibility (axes 2–7, carried):** 0.981
- **Final Schranken-quota:** 0.950 (BELOW 100%) over 20 gate cases (adjudicated 0, pending 20)
- Human-final units: **0 adjudicated · 20 pending** (of 20); 5 rubric-final
- Axis 1 disposition: pass 0 · fail 0 · pending 6 · n/a 19
- Final per-case status: {'pass': 24, 'fail': 1}

### Divergences — seeds for L3 (M2 target list)

- **CALC-02** (flags_off, flags_on) · _rubric_flag_ — Provisional FAIL; hard gate VIOLATED; axis partials ['3', '4']; judge findings ['must_avoid violated: ignoriert Nutfüllung/Quellung'].
  - → M2: Owner/L3 adjudication: true Schranken-violation (M1 has not cleared the hard gate → L3 must catch it) vs. rubric false-flag (then final quota → 1.0).
- **TRAP-02** (flags_off, flags_on) · _factual_judge_passed_ — Both answers label EPDM a "polarer Kautschuk" — EPDM is non-polar; the swelling-mechanism text is internally inconsistent (calls EPDM polar yet has non-polar oil dissolve it). The conclusion (EPDM swells in mineral oil) is correct, but the stated mechanism is wrong, and the rubric judge passed it (must_catch named, must_contain met).
  - → M2: L3 verifier + Fallen-Katalog must catch confidently-stated mechanism errors; candidate axis-1 issue (human-final, deep audit deferred).

### Per-case final status

| Case | Column | Final | Adjudication | Axis 1 | Gate (final) | (provisional) |
|---|---|---|---|---|---|---|
| TRAP-01 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| TRAP-01 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| TRAP-02 | flags_off | pass | ⏳ pending | pending | clean | pass |
| TRAP-02 | flags_on | pass | ⏳ pending | pending | clean | pass |
| TRAP-03 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| TRAP-03 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| TRAP-04 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| TRAP-04 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| COMBO-01 | flags_off | pass | ⏳ pending | pending | clean | pass |
| COMBO-01 | flags_on | pass | ⏳ pending | pending | clean | pass |
| COMBO-02 | flags_off | pass | ⏳ pending | pending | clean | pass |
| COMBO-02 | flags_on | pass | ⏳ pending | pending | clean | pass |
| COMBO-03 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| COMBO-03 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| UNCERT-01 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| UNCERT-01 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| UNCERT-02 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| UNCERT-02 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| UNCERT-03 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| UNCERT-03 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| UNDER-01 | flags_off | pass | rubric-final | n_a | — | pass |
| UNDER-01 | flags_on | pass | rubric-final | n_a | — | pass |
| UNDER-02 | flags_off | pass | rubric-final | n_a | — | pass |
| UNDER-02 | flags_on | pass | rubric-final | n_a | — | pass |
| UNDER-03 | flags_off | pass | rubric-final | n_a | — | pass |
| UNDER-03 | flags_on | pass | rubric-final | n_a | — | pass |
| CONFLICT-01 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| CONFLICT-01 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| CONFLICT-02 | flags_off | pass | ⏳ pending | pending | clean | pass |
| CONFLICT-02 | flags_on | pass | ⏳ pending | pending | clean | pass |
| DEFAULT-01 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| DEFAULT-01 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| DEFAULT-02 | flags_off | pass | rubric-final | n_a | — | pass |
| DEFAULT-02 | flags_on | pass | rubric-final | n_a | — | pass |
| DEFAULT-03 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| DEFAULT-03 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| LIMIT-01 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| LIMIT-01 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| LIMIT-02 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| LIMIT-02 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| SAFETY-01 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| SAFETY-01 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| SAFETY-02 | flags_off | pass | ⏳ pending | n_a | clean | pass |
| SAFETY-02 | flags_on | pass | ⏳ pending | n_a | clean | pass |
| CALC-01 | flags_off | pass | ⏳ pending | pending | clean | pass |
| CALC-01 | flags_on | pass | ⏳ pending | pending | clean | pass |
| CALC-02 | flags_off | fail | ⏳ pending | pending | VIOLATED | fail |
| CALC-02 | flags_on | fail | ⏳ pending | pending | VIOLATED | fail |
| APP-01 | flags_off | pass | rubric-final | n_a | — | pass |
| APP-01 | flags_on | pass | rubric-final | n_a | — | pass |

## Provisional rubric detail (axes 2–7)

## Column `flags_off`

- **Overall credibility (axes 2–7, rubric):** 0.981
- **Schranken-quota (provisional):** 0.950 (BELOW 100%) over 20 gate-relevant cases
- Axis 1 (Faktische Korrektheit): **human-final for all 25 answers** (worksheet); especially emphasized in 6 case(s)
- Provisional per-case status: {'pass': 24, 'fail': 1}

| Axis | Name | Credibility | pass/partial/fail |
|---|---|---|---|
| 2 | Fallen-Vermeidung | — | 0/0/0 |
| 3 | Ehrliche Unsicherheit | — | 0/0/0 |
| 4 | Begründungstiefe | — | 0/0/0 |
| 5 | Proaktivität | — | 0/0/0 |
| 6 | Grounding/Provenienz | — | 0/0/0 |
| 7 | Grenze gehalten | — | 0/0/0 |
| 1 | Faktische Korrektheit | human-final | pending |

## Column `flags_on`

- **Overall credibility (axes 2–7, rubric):** 0.981
- **Schranken-quota (provisional):** 0.950 (BELOW 100%) over 20 gate-relevant cases
- Axis 1 (Faktische Korrektheit): **human-final for all 25 answers** (worksheet); especially emphasized in 6 case(s)
- Provisional per-case status: {'pass': 24, 'fail': 1}

| Axis | Name | Credibility | pass/partial/fail |
|---|---|---|---|
| 2 | Fallen-Vermeidung | — | 0/0/0 |
| 3 | Ehrliche Unsicherheit | — | 0/0/0 |
| 4 | Begründungstiefe | — | 0/0/0 |
| 5 | Proaktivität | — | 0/0/0 |
| 6 | Grounding/Provenienz | — | 0/0/0 |
| 7 | Grenze gehalten | — | 0/0/0 |
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
