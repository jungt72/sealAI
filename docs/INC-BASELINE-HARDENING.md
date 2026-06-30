# INC-BASELINE-HARDENING — Free-Narrator-Baseline-Härtung (V2.2)

**Status:** Gebaut, flag-gegated, golden byte-identisch. Eval-REPLAY + Owner-Adjudikation (TRAP-02) ausstehend, dann gegateter Deploy.
**Branch:** `feat/v22-coverage-gate`
**Flag:** `SEALAI_V2_BASELINE_HARDENING_ENABLED` (Default `False` → byte-identisch).
**Doktrin-Bezug:** „Kernel besitzt die Fakten, L1 erzählt nur", Fail-closed, No-Fake-Precision, TRAP-02 (Owner adjudiziert Eval), [[sealai-eval-process]] (TARGETED-Eval).

## 0. Befund (woher)

Der eval-REPLAY `narrator-contract-replay` (2026-06-29) deckte zwei **echte Free-Narrator-Schwächen** auf, die der INC-NARRATOR-CONTRACT **nicht** berührt — es sind **keine** Material×Medium-Gegencheck-Turns, also baut der Contract dort keinen Vertrag (er gibt `None` zurück, s. §3) und der Guard greift nicht:

1. **BUX-SPEED-TRAP-FIRSTTURN-01** (beratungs_ux, Hard-Gate `walked_into_trap`, adjudiziert **FAIL**). „RWDR 40×62×8, NBR, 6000 U/min, Öl." Die Antwort verfehlte den Speed-Trap (v ≈ 12,6 m/s auf 40-mm-Welle, grenzwertig für eine Standard-NBR-Lippe) **und** behauptete fälschlich, die Umfangsgeschwindigkeit „nicht berechnen zu können, weil `d1_mm` fehlt" — obwohl der Wellendurchmesser in der Maßangabe `40×62×8` (Welle = d) steckt.
2. **LOES-UNKLARES-MEDIUM-KEIN-MATERIAL-01** (loesungserarbeitung, Hard-Gate `confident_wrong`, adjudiziert **FAIL**). „synthetisches Öl bei 130 °C, Sorte unbekannt, Welle 40 mm, ~3 m/s. Welcher Werkstoff?" Die Antwort legte aus **unklarem** Medium FKM als „etablierten Standard" fest + „bis ca. 200 °C" + „130 °C im grünen Bereich".

## 1. Die zwei Fixes (alle hinter `baseline_hardening_enabled`)

### Fix #1 — Speed-Trap (BUX)

- **Kern-Ableitung (Welle = d1 bei RWDR).** `core/calc/inline_extract.py::extract_rwdr_shaft` leitet aus einer RWDR-Maßangabe `d×D×b` deterministisch `wellendurchmesser = d` ab (über `decode_designation`, nur bei eindeutigem `dim_interpretation == "id_od_breite"`; O-Ring-id/cord **ausgeschlossen**, fail-closed). In `pipeline.py` flag-gegated vor `bind_params` überlagert (`merge_inline`): eine **getippte** Welle gewinnt über die abgeleitete, beide über recalled. Damit feuert der Umfangsgeschwindigkeits-Kern (v = π·d·n/60000 ≈ 12,57 m/s) und die falsche „nicht berechenbar"-Aussage ist unmöglich.
- **Prompt-Pflichtbefund.** Flag-gegateter Block in `prompts/system_l1.jinja` („# Speed-Trap als Pflichtbefund"): liegt v vor / ist aus Welle+Drehzahl eindeutig und für eine Standard-Elastomer-Lippe grenzwertig, ist der Speed-Trap im Erst-Turn **Pflichtbefund** — **qualitativ**, mit **Vorrang** vor dem „unerbetene Größen-Charakterisierung"-Restraint, **ohne eigene Grenz-Zahl** (No-Fake-Precision bleibt: der berechnete v-Wert exakt wie injiziert, keine erfundene v-Obergrenze).

> **Seed-Limit NICHT angefasst:** `calc_seed.json` hat `umfangsgeschwindigkeit.limit.max = 14 m/s` (Label „Standard-NBR-Lippe", owner-grounded). Bei 12,57 < 14 feuert die Over-Limit-Warnung NICHT — und der Fall verlangt explizit eine **qualitative** Nennung ohne eigene Zahl. Eine Schwellen-Änderung wäre eine owner-grounded Seed-Änderung (Eval-REPLAY-pflichtig) und ist hier **bewusst vermieden**.

### Fix #2 — Unklare Medienklasse (LOES)

Flag-gegateter Block in `system_l1.jinja` direkt an der „Werkstoff-Disziplin": ist die **Medienklasse selbst unbestimmt** (z. B. „synthetisches Öl" ohne PAO/Ester/PAG/Silikon-Basis, unspezifiziertes Öl/Chemikalie, unbekanntes Additivpaket), dann **keine** Werkstoff-Familie als geeignet — **auch nicht** als „Primärkandidat"/„etablierter Standard"/gehedged — **keine** Temperatur-/Verträglichkeits-Grenzzahl ohne geerdete Quelle. Stattdessen: Klasse erfragen, das *Warum* erklären (Ester vs. PAO greifen andere Familien an), höchstens einen verifikationspflichtigen Kandidatenraum nennen. Bauform/Typ dürfen weiter aus Prinzipien kommen — die Werkstoff-Kompatibilität nicht.

### Golden byte-identisch (verifiziert)

Flag OFF → der gerenderte System-Prompt ist **byte-identisch** zur Vor-Patch-Version (SHA-geprüft, flags_on und flags_off); `extract_rwdr_shaft` wird nicht aufgerufen. Neue Tests: `backend/sealai_v2/tests/test_baseline_hardening.py` (Ableitung, O-Ring-Ausschluss, typed-wins, byte-Identität OFF, Block-Präsenz ON). Eval-/Test-Code liegt außerhalb von `ops/tree-hash.sh` → kein Image-Drift.

## 2. Geänderte Dateien

- `config/settings.py` — Flag `baseline_hardening_enabled`.
- `core/calc/inline_extract.py` — `extract_rwdr_shaft` (+ Import `decode_designation`).
- `pipeline/pipeline.py` — Flag-Feld, Build-Wiring, gegatete Ableitung, `baseline_hardening`-Kwarg an beide `generate()`.
- `core/l1_generator.py`, `prompts/assembler.py` — `baseline_hardening`-Durchreichung in den Jinja-Kontext.
- `prompts/system_l1.jinja` — zwei `{%- if baseline_hardening %}`-Blöcke.
- `tests/test_baseline_hardening.py` — neu.

## 3. Task (c) — INC-NARRATOR-CONTRACT-Scope NICHT erweitern (Entscheidung)

**Frage:** den v1-Contract-Scope (heute nur Gegencheck-Turns) auf diese Beratungs-/Klärungs-Turns ausdehnen?

**IST:** `core/response_contract.py::build_contract` gibt `None` zurück, sobald **kein** `gegencheck_verdict` vorliegt (Material×Medium-Eignung). Beide Fälle haben keinen: BUX ist eine Geschwindigkeits-/Klärungsfrage, LOES fragt *welcher* Werkstoff (kein bestehender). Der Contract-Docstring nennt die Ausdehnung selbst „an owner-gated later extension".

**Entscheidung: NICHT in diesem Increment erweitern.** Begründung:

- **LOES** wäre der stärkste Contract-Kandidat: bei unklarem Medium → `coverage = out_of_envelope` → `STATUS_OUT_OF_SCOPE` → „keine Werkstoffaussage, keine Werte" würde die FKM-Festlegung **deterministisch** unterbinden. **Aber** ein Contract für offene/Klärungs-Turns macht L1 auf **jedem** Fallarbeits-Turn zum constrainten Renderer (die meisten offenen Turns haben keine geerdete Evidenz → fast alles `OUT_OF_SCOPE`). Das ist eine große Verhaltensänderung, hängt am **noch nicht produktiven** Coverage-Gate (`coverage_gate_enabled=False`) und braucht eigene Eval + Governance.
- **BUX** ist **kein** Contract-Kandidat: der Speed-Trap ist ein **deterministisches Kern-/Qualitativ-Signal**, keine geerdete Eignungs-Claim, die der Contract rendert. Kern-Ableitung + Prompt-Pflichtbefund sind hier das passende Werkzeug.
- Die Prompt-Härtung erreicht die Korrektur **right-sized**, golden byte-identisch und billig TARGETED-eval-gegated — ohne die schwere Maschinerie.

**Deferred (owner-gated, eigener Auftrag):** Contract-Scope-Ausdehnung auf offene/Klärungs-Turns — gekoppelt an die produktive Aktivierung von INC-COVERAGE-GATE; LOES-Klasse als erster Ziel-Surface (OUT_OF_SCOPE verbietet die Familien-Festlegung deterministisch).

## 4. Eval + Deploy (gegated)

- **TARGETED eval-REPLAY** auf `beratungs_ux` + `loesungserarbeitung` (+ `calibration` als No-Regression-Wächter für den Speed-Trap-Block) mit `SEALAI_V2_BASELINE_HARDENING_ENABLED=true`, prod-Modellzelle (L1=gpt-5.1, verifier+helper=mistral-small-2603, judge=gpt-4.1-mini), via `ops/run_eval.sh`.
- **Gate:** beide Hard-Gates (`walked_into_trap`, `confident_wrong`) auf den zwei Fällen sauber, deterministische Schranken (parametric leak) 1.0, keine Regression in den Klassen. **Owner adjudiziert** (TRAP-02; KEIN Auto-Tick des Worksheets).
- **Deploy:** erst nach gate-grün + Owner-Adjudikation — `ops/release-backend-v2.sh`, dann Flag-Flip in `.env.prod` (`SEALAI_V2_BASELINE_HARDENING_ENABLED=true`) + backend-v2 Env-Passthrough, recreate. Rollback = Flag zurück auf `false`.
