# sealingAI V2.2 — IST-Audit (Repo vs. Build-Spec)

**Status:** Reiner Ist-Bericht (§10 Schritt 1–2). Kein Bau-Vorschlag aktiviert — die Owner-Locks **L1 (Wedge-Reihenfolge)** und **L3 (Eval-Schwellen)** sind noch offen; **L2 (Prelon-Abgrenzung)** ist ratifiziert und wurde respektiert (nichts Prelon-Feldwissens-Abhängiges berührt).
**Auditiert gegen:** `docs/V2/sealingai_v2_2_build_audit_spec.md`.
**Methode:** Read-only, 4 parallele Achsen-Audits, jede Aussage mit `file:line`-Beleg. Spiegelt den etablierten V2.1-IST-Audit (PR #139).
**Datum:** 2026-06-29.

---

## 1. Kernbefund

**Alle vier Audit-Achsen laufen auf dieselbe fehlende Schlüsselkomponente zusammen: das deterministische Coverage-Gate (§4).** Die korrigierte Assertivitäts-Mechanik (Status→Modus, §5), der `OUT`/`PARTIAL`-Zweig des Gegencheck-E-Wedge (§6), die Meta-Schranke *Coverage-Classification-Accuracy* (§8d) und der Flywheel (§9) hängen **alle** an diesem einen Teil. Die in der Spec vorgeschlagene Inkrement-Reihenfolge (Coverage-Gate zuerst) ist damit durch den Audit **bestätigt**.

**Entscheidender Hebel:** Die deterministische Engine, die das Gate braucht, **existiert bereits** — `backend/sealai_v2/knowledge/produktspec/kernel.py:85` `classify_envelope(fall)` erzeugt aus reinem Regelabgleich Bänder (`GREEN_BASE/GREEN_EXTENDED/YELLOW/ORANGE/RED`) + `resolve()` einen `ResponseLevel` (`contracts.py:27`). Das ist genau die „Daten-statt-LLM"-Mechanik (I-COV-1). Sie ist nur **flag-gated OFF** (`config/settings.py:97 produktspec_enabled=False`), **RWDR-scoped** und als **Render-only-Surface abgeschottet** (`pipeline/produktspec_step.py:9-17` — „NEVER injected into L1/L3"). → **INC-COVERAGE-GATE ist „generalisieren + verdrahten + L1-Prosa in Status→Modus-Kopplung wandeln", kein Bau bei null.**

---

## 2. IST-vs-SOLL je IN-Komponente (§3)

| Komponente | IST | Beleg | Lücke |
|---|---|---|---|
| **Coverage-Gate** (§4) | 🔴 fehlt (Engine inert da) | `produktspec/kernel.py:85`; flag OFF `settings.py:97`; render-only `produktspec_step.py:9` | kein `coverage_status` zwischen `compute`↔`generate` |
| **Assertivitäts-Mechanik** (§5) | 🔴 fehlt | Prosa `system_l1.jinja:54,79`; Inputs nur statische Bools `settings.py:66-67` | harte Status→Modus-Kopplung; 4 Output-Ebenen als Kernel-Enum |
| **Gegencheck-E** (§6) | 🟡 3 von 4 | `core/gegencheck.py` (5 Zustände), Stage `stages.py:286`, live | `OUT`-Zweig fehlt; `bedingt`-Narration fehlt im L1; Zell→Fall-Brücke |
| **Decode G1/G2** (§7) | 🟡 G1 da, G2 teilw. | `core/decode_extract.py:47`, wired `stages.py:342`, leak-safe | G2-Korridor: Cross-Reference-Store **deferred** |
| **Äquivalenz-Schranke** I-EQ-1 (§7) | 🟢 vorhanden | `core/equivalence_guard.py:24-27` + `confident_wrong`-Gate, in `l3_verifier.py` | — (erfüllt) |
| **Geometrie-Norm-Schicht** (§3) | 🔴 fehlt als Schicht | DIN 3760/3761·ISO 3601 nur Prosa-`sources`; `archetypes_seed.json:39 anwendbare_regime:[]`; `contracts.py:506 Case.geometry=None` | strukturierte Norm-/Einbauraum-Schicht |
| **3 Archetypen** (§3) | 🟡 1 von 3 | Maschinerie `archetypes.py` komplett+wired; Seed = `getriebe`+`ruehrwerk` | Elektromotor + Hydraulikzylinder Profile fehlen (`ruehrwerk` ist extra) |
| **5 Eval-Schranken** (§8) | 🔴 fehlen (a teilw.) | nur `confident_wrong` als Gate `contracts.py:657`; gated-Triade = parametric/memory/exfil `matrix.py:204` | (a)–(e) als getrackte Rate-Metriken |
| **Flywheel-Gerüst** (§9) | 🔴 fehlt | 0 Treffer (grep flywheel/coverage_gap/queue); `ops/ingest_fachkarte.py` = doc-driven | Gap-Logging + Häufigkeit + Queue + Auto-Eval-Append |

---

## 3. Invarianten-Konflikte (§2)

Wichtig: das ist **kein Bug**, sondern das **V2.1→V2.2-Delta**. Die heutige Haltung *ist* V2.1 (Assertivität-als-Prosa-Default) — genau das, was V2.2 durch den gemessenen, deterministischen Zustand ersetzt.

- **I-COV-1 verletzt** — das LLM bewertet seine eigene Coverage: `system_l1.jinja:54` „so assertiv wie die Erdung reicht". Kein Kernel-Status.
- **I-COV-2 verletzt** — Assertivität ist ein Default: `system_l1.jinja:79` „Immer eine Richtung". Die einzigen strukturierten Tone-Inputs (`compliance_hint`/`safety_critical`, `assembler.py:64`) sind statische Config-Bools (`settings.py:66-67`), nicht status-abgeleitet.
- **I-COV-3 Leak** — First-Principles für Chemie ist *eingeladen*: `system_l1.jinja:55-59` „aus Ingenieurprinzipien ableiten, auch ohne Matrix-Treffer". Es gibt einen Guard (`63-67`: Bauform eher aus Prinzipien als Werkstoff-Kompatibilität), aber **nur Prosa**, kein deterministisches Gate.
- **I-COV-4 teilweise** — vier Output-Ebenen existieren als Prompt-Prosa (`system_l1.jinja:68-81`), aber kein Kernel-Enum erzwingt sie; die echten `ResponseLevel`/`MaterialKind`-Enums liegen im inerten produktspec-Modul.
- **I-EQ-1 erfüllt** ✓ — `equivalence_guard.py` fängt „baugleich/1:1 austauschbar/…" deterministisch ab, hedged + `confident_wrong`-Gate, scoped auf Decode-Turns.
- **I-CAL-1 nicht erfüllt** — die Doktrin ist behauptet, nicht gemessen: die fünf Kalibrierungs-Schranken (§8) fehlen.

---

## 4. Fundament — was bereits trägt

- **Deterministische Envelope-Engine** vorhanden (inert): `produktspec/kernel.py:85 classify_envelope`, `:320 _din_label`, `resolve()→ResponseLevel`.
- **Matrix mit distinktem `bedingt`**: `matrix_seed.json` 28 Zellen, 3 Verdikte (`contracts.py:250 _MATRIX_VERDICTS`), `bedingt`=3 Zellen mit eigenem `condition`-Text; Circularity-Guard `matrix.py:99`. `matrix_conditional` überlebt Kernel→Outcome→Serializer **distinkt** → `PARTIAL_ENVELOPE` kann sauber darauf aufbauen (kollabiert es nicht).
- **Gegencheck-Kernel** (`core/gegencheck.py`) disqualify-only, 5 Zustände, live als Stage; trägt den E-Wedge zu **3 von 4**.
- **Äquivalenz-Guard fertig** (`equivalence_guard.py`) — I-EQ-1 erfüllt.
- **Decode-G1 fertig** (`decode_extract.py`) — Bezeichnung→Spec, leak-safe, render-only.
- **Archetyp-Maschinerie fertig** (`archetypes.py`: Profile + Loader + Circularity-Guard + Recognition annotate-only) — nur owner-gegroundeter Content fehlt.

---

## 5. Detailbefunde je Achse

### Achse 1 — Coverage-Gate + Assertivitäts-Mechanik
Pipeline-Reihenfolge (Ist, `pipeline/pipeline.py run()`): `flush_memory → recall → [gegencheck, diagnose, decode, alternativen, compute_kandidaten_spec (render-only)] → understand → ground(L2) → bind_params → compute(calc) → generate(L1) → verify(L3) → exfil_guard → cite → remember`. **Kein deterministischer Coverage-Schritt zwischen `compute` und `generate`** — L1 wird direkt nach `compute` aufgerufen (`pipeline.py:189`). `coverage_status`/`IN_ENVELOPE` existiert backend-weit **nirgends** (grep=0). Assertivität wird vollständig durch L1-Prosa gesteuert; das LLM bewertet seine eigene Erdung. Einzige strukturierte Engine = `produktspec/kernel.py` (inert, render-only, RWDR-scoped, flag OFF).

### Achse 2 — Matrix + Gegencheck-E
Matrix solide (28 Zellen, `bedingt` echt+distinkt, z. B. `MX-FEPM-DAMPF-CHEM`, `MX-NBR-SYNTHETIKOEL`, `MX-VMQ-FETT`). Gegencheck-Kernel (`core/gegencheck.py`) unterscheidet alle 5 Zustände (`disqualified True`; `matrix_conditional`+`condition`; `matrix_compatible` no-affirmation; `no_matrix_data`; `no_medium`), Doktrin E4-1 test-erzwungen. **E-Wedge 3/4:** passt/passt-nicht/bedingt vorhanden; **`OUT` („außerhalb geprüfter Daten") fehlt als eigenständiges geerdetes Verdikt** — existiert nur als blankes `no_matrix_data`/`no_medium` und wird im L1 (`system_l1.jinja:84-91`) mit dem no-affirmation-Bucket zusammengefasst; `bedingt` hat keine eigene Narrations-Klausel. **Zell→Fall-Brücke fehlt** (rein per-Zelle). Eval `gegencheck_v0.json` deckt 4 Fälle (inkl. den keine-Daten-Stand-in für OUT).

### Achse 3 — Decode + Geometrie-Normen + Archetypen
**Decode G1 fertig** (`decode_extract.py:47`, Maße aus Input echo'd, „uneindeutig" statt Fehl-Label, render-only). **G2 teilweise** — ehrliche Vergleichskorridor-Rahmung (`EQUIVALENZ_GRENZE` `decode_extract.py:35`), aber der **geerdete Cross-Reference-Store ist deferred** (seed `klass_note`). **Äquivalenz-Guard vorhanden** (`equivalence_guard.py`, in `l3_verifier.py`, eval `DEC-AEQUIVALENZ-GRENZE-01`). **Geometrie-Norm-Schicht faktisch abwesend** — DIN 3760/3761 nur in `versagensmodi_seed.json:113` + Draft-Karten; ISO 3601-2 als Prosa-Claims in `FK-ORING-VERPRESSUNG`; der strukturierte Hook `anwendbare_regime` ist leer, `Case.geometry` unbefülltes Gerüst. **Archetypen 1/3** — Maschinerie+Recognition komplett (`archetypes.py`, soft/annotate-only `stages.py:64-107`), Seed enthält `getriebe`+`ruehrwerk`; **Elektromotor + Hydraulikzylinder fehlen als Profile** (nur Dim-5-Tags); Eval `archetype_v0.json` spiegelt das.

### Achse 4 — Eval-Schranken + Flywheel
Heutiges Lineal: 7 Achsen (`contracts.py:634`), 8 Gates (`:655`), gated-hart-Triade nur parametric/memory/exfil (`matrix.py:204`). Von den 5 V2.2-Schranken: **(a) Confident-Wrong-Rate teilweise** (Gate da, keine Rate-Metrik, nicht in der Triade); **(b) False-Hedge, (c) Unsupported-Claim, (d) Coverage-Classification-Accuracy, (e) Equivalence-Overclaim — als Metriken abwesend** ((e) ist auf einen Decode-Fall in `confident_wrong` gefaltet, seed sagt explizit „keine neue Schranke"). **(d) ist der Keystone** — ohne Coverage-Gate kein Substrat; ohne den per-Claim „geerdet-vs-behauptet"-Vergleich fehlt (a)/(b)/(c) das Mess-Primitiv. **Flywheel vollständig abwesend** (grep=0); `RetrievalResult.grounded` (`contracts.py:203`) existiert, fließt aber nirgends persistent. `ops/ingest_fachkarte.py` ist **doc-driven** (Push), nicht das gap-driven (Pull) §9-Flywheel.

---

## 6. Lücken-/Inkrement-Reihenfolge (§10 Schritt 3) — Vorschlag, zum Halten

Jedes Inkrement mit Doktrin-Gate-Bezug, eigenen Eval-Schranken und Halt-Punkt; produktiv-mutierende Schritte owner-freigegeben.

1. **INC-COVERAGE-GATE** *(Fundament)* — `produktspec/kernel.py` zu einem Kernel-Schritt generalisieren, der `coverage_status ∈ {IN/PARTIAL/ANALOG/OUT}` emittiert; **nach `compute`, vor `generate`**; L1-Kalibrierungs-Prosa → harte Status→Modus-Kopplung (Prompt konsumiert Status, bewertet ihn nicht). Gates: I-COV-1/2/3/4.
2. **INC-EVAL-CALIBRATION** *(vor produktiver Doktrin, I-CAL-1)* — die 5 Schranken; Keystone = **Coverage-Classification-Accuracy** (per-Claim geerdet-vs-behauptet als Mess-Primitiv für a/b/c).
3. **INC-GEGENCHECK-E** — `OUT`-Zweig + dedizierte `bedingt`-Narration; Zell→Fall-Brücke (`PARTIAL_ENVELOPE` baut auf `matrix_conditional`).
4. **INC-DECODE-G12** — G2-Korridor + Geometrie-Norm-Schicht authoren (DIN 3760/3761, ISO 3601, Einbauraum).
5. **INC-FLYWHEEL-SCAFFOLD** — Gap-Logging (PARTIAL/ANALOG/OUT) + Häufigkeit + owner-Queue + Auto-Eval-Append; Kuration bleibt owner-manuell.

*Content-Häppchen (parallel, klein):* zwei Archetyp-Profile (Elektromotor, Hydraulikzylinder) + Eval-Fälle — die Maschinerie trägt sie bereits.

---

## 7. HALT (§10 Schritt 4)

CC adjudiziert keine Owner-finalen Gates (TRAP-02). Es wird **nichts gebaut**, bis folgende Locks bestätigt sind:

| Lock | Spec-Empfehlung | Owner-Entscheid |
|---|---|---|
| **L1 — Wedge-Reihenfolge** | Gegencheck-E primär (baut auf Vorhandenem; Käufer = Konstrukteur), Decode-G1/G2 sekundär | ☐ bestätigt / ☐ umsortiert |
| **L3 — Eval-Schwellen** | Confident-Wrong + Equivalence-Overclaim = Hard-Fail bei jedem Vorkommen; Coverage-Classification-Accuracy ≥ 0,95 | ☐ bestätigt / ☐ Schwellen: ___ |
| **L2 — Prelon-Abgrenzung** | *ratifiziert* — nichts Feldwissens-Abhängiges berührt; alle Dim-5/6-/D-/F-Teile verschoben (Flywheel-Pfad) | ✓ ratifiziert |

`ops/gate.sh` + GOVERNANCE_LOG + eval-REPLAY bleiben durchsetzend. Sperrliste (§11) respektiert: Diagnose (D), Alternativen (F), Hersteller-Fähigkeiten (Dim. 6), Versagensmodi (Dim. 5), breitere Archetyp-Welle, V2-Skalierungs-Deferrals — **nicht** vorbereitet.

---

*Ende V2.2 IST-Audit. Nächster Schritt: Owner bestätigt L1/L3 → CC macht aus Inkrement 1 (INC-COVERAGE-GATE) einen konkreten Bau-Vorschlag, wieder zum Review.*
