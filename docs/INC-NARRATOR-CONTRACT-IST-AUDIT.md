# INC-NARRATOR-CONTRACT — §1 IST-vs-SOLL-Audit

**Status:** Audit abgeschlossen 2026-06-29. **HALT** vor Phase 1 (owner-gegated). Nichts gebaut.
**Auftrag:** `docs/INC-NARRATOR-CONTRACT.md` (ersetzt INC-NARRATOR-SWAP vollständig).
**Verhältnis:** Konsument von INC-COVERAGE-GATE (der Vertrags-`status` *ist* die Coverage-Gate-Ausgabe);
teilt das Eval-Lineal mit INC-EVAL-CALIBRATION.

---

## Kernbefund

Das Substrat für den Antwortvertrag steht zu **~60 % bereits** — vieles davon diese Session gebaut. Die zwei
Komponenten, die die Spec als *möglicherweise fehlend* annimmt, **existieren beide**:

1. **Claim-IDs + Provenienz pro Aussage sind schon im L1-Input.** Jeder `GroundingFact`, den L1 heute bekommt,
   trägt `text`, `quelle`, **`card_id`** (Fachkarte-/Matrix-Zell-ID), **`sources`** (Primärquellen), **`kind`**
   (`"card"` | `"matrix"`). Das ist die `allowed_claims`-Basis — mit IDs + Provenienz, nicht erst zu bauen.
2. **Der Vertrags-`status` existiert** als deterministischer Coverage-Status (INC-COVERAGE-GATE, `core/coverage.py`).

→ Der Auftrag verkürzt sich von „Vertrag bei null bauen" auf **„formalisieren + constrainen + erzwingen"**.

---

## §1 — die fünf Audit-Fragen (repo-verankert)

| Frage | Befund (file:line) | SOLL-Lücke |
|---|---|---|
| **Kernel→L1: Claim-IDs + Provenienz?** | ✅ **Ja, schon da.** `l1_grounding = grounding_facts + retrieval.matrix_facts` (`pipeline/pipeline.py:385`); jeder = `GroundingFact{text, quelle, card_id, sources, kind}` (`core/contracts.py:127-133`; konstruiert `knowledge/qdrant_retrieval.py:64`, `knowledge/matrix.py:180`). | L1 darf heute **frei darüber hinaus** erzählen (kein „nur diese Claims"-Constraint). `required_clauses` / `forbidden_phrases` / `allowed_materials` / `allowed_values` fehlen als Formalisierung. |
| **Coverage-Gate / `status`** | ✅ **Existiert** (`core/coverage.py`: `CoverageStatus` IN/PARTIAL/ANALOG/OUT; `coverage_for()` rein berechenbar; `PipelineResult.coverage`). **Der Vertrags-`status` IST das.** | Nur Mapping + `NEEDS_CLARIFICATION`-Schicht (s.u.). **Dependency erfüllt** — Gate nicht zuerst zu bauen. |
| **L1 heute** | **Freier Narrator** (`prompts/system_l1.jinja`: „erarbeite aus Prinzipien + Fakten") — genau die Freitext-Disposition, die in der n=3-Probe leckte. | Renderer-Reframe (Phase 2) net-new. (Coverage-Mode-Kopplung ist der erste harte Deckel, flag-gated.) |
| **L3 heute** | Trap-Katalog (→ CORRECTED) + **Parametric-Leak-Detektor** (Zahlen) + Equivalence-Guard + Precision-Overapplication (`core/l3_verifier.py`); `kb_claims=[f.text for f in l1_grounding]` geht schon an L3 (`pipeline/pipeline.py:498`). | claim-level **Abdeckungs**-Guard (Satz→Claim, fail-closed) net-new — **baut auf** Parametric-Leak (Zahlen-Prefilter) + kb_claims, dupliziert nicht. |
| **Eval-Infra** | ✅ **Existiert + geteilt** (`eval/harness.py` / `scorer.py` / `matrix.py` + `eval/calibration.py` aus INC-EVAL-CALIBRATION). | Phase-4-Offline-Eval hängt ins **selbe** Lineal — kein zweites Mess-System. |

---

## Mapping Coverage-Status → Vertrags-`status`

| `CoverageStatus` (IST) | Vertrags-`status` (SOLL) |
|---|---|
| `IN_ENVELOPE` | `COVERED_RECOMMENDATION` |
| `PARTIAL_ENVELOPE` | `COVERED_CAUTION` |
| `ANALOG_ONLY` | `COVERED_CAUTION` (analogie-markiert) |
| `OUT_OF_ENVELOPE` | `OUT_OF_SCOPE` |
| *(neu)* `NEEDS_CLARIFICATION` | **NICHT** im Coverage-Kernel — abgeleitet aus blockierenden `missing_fields` als **Vorrang-Schicht** im Vertrag (Input-Vollständigkeit ≠ Wissensabdeckung). **Lead-Empfehlung: (b) ableiten, Kernel unangetastet.** |

---

## Net-new (Phasen-Scope)

- **Phase 1 — Vertrag:** v.a. *formalisieren + constrainen*. `allowed_claims` = die vorhandenen `GroundingFact`s
  (ID/Quelle/kind schon da); net-new = `status`-Mapping + `NEEDS_CLARIFICATION`-Vorrangschicht + `required_clauses`
  + `forbidden_phrases` + `allowed_materials` + `allowed_values`.
- **Phase 2 — Renderer:** `system_l1.jinja` von „schreibe eine Antwort" auf „rendere diesen Vertrag" umstellen;
  flag-gated/inert (golden byte-identisch bis Flag-Flip).
- **Phase 3 — claim-level Guard (Code, fail-closed):** Satz→Claim-Abdeckung; deterministische Vorfilter (erfundene
  Zahl via `allowed_values`, Werkstoff via `allowed_materials`, fehlende `required_clause`, `forbidden_phrase`).
  Baut auf L3-Parametric-Leak + kb_claims.
- **Phase 4 — Offline-Eval:** erweitertes Set ins geteilte Lineal; Incumbent (gpt-5.1) Baseline; Kandidaten gemessen;
  Modellwahl wird Eval-Routine, kein Architektur-Entscheid. Owner-adjudiziert (TRAP-02).

## Kopplung

INC-NARRATOR-CONTRACT ist der **Konsument** von INC-COVERAGE-GATE: Gate liefert `status` → Vertrag definiert den
Antwortraum → Renderer rendert nur ihn → Guard erzwingt Abdeckung. Die Probe-Daten validieren die
`forbidden_phrases` direkt („belegt" / „Richtwert" / „Fachliteratur" / „typisch" = exakt Mistrals P2/P3-Lecks).

## HALT (§1/§8)

Nichts gebaut. Owner-Review des Phase-1-Designs vor Implementierung. Offener Owner-Entscheid:
`NEEDS_CLARIFICATION` **(a)** fünfter Coverage-Status vs **(b)** abgeleitet aus `missing_fields` — **Lead-Empfehlung (b)**
(hält den deterministischen Chemie-Achsen-Kernel rein; mein committeter `coverage.py` + Tests bleiben grün).
