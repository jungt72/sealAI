# INC-NARRATOR-CONTRACT — CC-Arbeitsauftrag: Antwortvertrag + Renderer + claim-level Guard

**Status:** Ausführbar nach Audit + Owner-Review. Doktrin-gegateter Relay.
**Ersetzt:** INC-NARRATOR-SWAP vollständig. Das „Swap"-Framing entfällt — der Modellwechsel ist jetzt *nachgelagert* und durch eine Offline-Eval gegated, nicht das Ziel.
**Verhältnis zu V2.2:** Eng gekoppelt mit INC-COVERAGE-GATE (der Vertrags-`status` *ist* die Coverage-Gate-Ausgabe, §1). Teilt das Eval-Lineal mit INC-EVAL-CALIBRATION.
**Doktrin-Bezug:** I-COV-1 (LLM adjudiziert nichts deterministisch Entscheidbares), I-COV-4 / Unsupported-Claim-Rate, TRAP-02, Fail-closed, „Kernel besitzt die Fakten, L1 erzählt nur".

**Ziel in einem Satz:** L1 von einem *freien Narrator* zu einem *Renderer* eines vom Kernel gelieferten **Antwortvertrags** umbauen, einen **claim-level `output_guard`** bauen, der Satz-zu-Claim-Abdeckung fail-closed erzwingt (nicht Strings matcht), und die Modellwahl damit zu einer **Offline-Eval-Routine** machen — der Incumbent bleibt L1, bis ein Kandidat die Honesty-Schwelle gemessen schlägt.

---

## 0. Was dieser Auftrag ist — und was bewusst NICHT

**Der load-bearing Befund, auf dem das ruht:** In der n=3-Probe leckte Mistral Large 3 auf allen drei Honesty-Fällen (erfundene °C, Leeres als „belegt" etikettiert, Tabelle statt Rückfrage), während der Incumbent (gpt-5.1) hielt. Daraus folgt **nicht** „Mistral geht grundsätzlich nicht" — getestet wurde ein *freier* Narrator, kein slot-constrainter Renderer. Es folgt: **Der Freitextraum, in dem die Disposition lecken kann, muss durch Architektur entzogen werden — nicht durch Modellwahl.** Genau das baut dieser Auftrag. Die Pointe: Je enger der Vertrag, desto egaler das Modell.

**IN diesem Auftrag:** der Kernel-Antwortvertrag, das L1-Renderer-Reframing, der claim-level `output_guard`, die Offline-Eval-Harness.

**Incumbent bleibt L1** (heute gpt-5.1 — als *Rolle*, kein Modell-Pinning). **KEIN Produktionsswap** in diesem Auftrag.

**NICHT in diesem Auftrag (gegated/gesperrt):**
- **Produktionsswap** auf Mistral oder irgendein Modell ohne bestandene Offline-Honesty-Schwelle (§5).
- **Mistral (oder irgendein Modell) als finaler Verifier/Gatekeeper** — die vertrauenskritischste Rolle bekommt nicht das am wenigsten kalibrierte Modell. Höchstens Red-Team-Helfer im Offline-Eval.
- **LLM-Guard für Faktenverifikation** — der Kernel/L3 verifiziert; der claim-level Code-Guard erzwingt Abdeckung. Ein LLM kommt *höchstens* als Zuordnungs-Klassifikator für den semantischen Teil von Phase 3 in Frage — **gated hinter der gemessenen Overblocking-/Miss-Rate (§5), nicht jetzt**.
- **Router / Eskalation** — Folge von INC-COVERAGE-GATE; wenn später, auf ein *aktuelles* Modell, nie zurück auf ein auslaufendes.

Scope-Erweiterung über §0-IN hinaus ist ein Auftrags-Verstoß.

---

## 1. Audit zuerst — IST etablieren, dann HALTEN

CC beantwortet gegen das **echte Repo**, bevor irgendetwas gebaut wird. Keine Datei-/Funktionsnamen aus diesem Dokument annehmen.

- **Kernel-Ausgabe an L1:** Was liefert der Kernel heute? Reine Fakten oder schon strukturiert? Gibt es **Claim-/Quellen-IDs** und Erdungs-Provenienz pro Aussage?
- **Coverage-Gate / `status`:** Existiert INC-COVERAGE-GATE oder ein deterministischer Status-Klassifikator (`OUT_OF_SCOPE` / `NEEDS_CLARIFICATION` / `COVERED_CAUTION` / `COVERED_RECOMMENDATION`)? **Der Vertrags-`status` IST die Coverage-Gate-Ausgabe.** Wenn das Gate fehlt: Abhängigkeit melden — entweder INC-COVERAGE-GATE zuerst, oder ein minimaler Status-Klassifikator wird Teil von Phase 1 (Owner entscheidet).
- **L1 heute:** Freier Narrator-Prompt („schreibe eine fachliche Antwort") oder schon constrained?
- **L3 heute:** Was prüft die Verifikationsschicht? Der claim-level Guard **baut darauf auf, dupliziert nicht**.
- **Eval-Infrastruktur:** Existiert ein Lineal/Harness? Wird INC-EVAL-CALIBRATION parallel gebaut? → **kein zweites Mess-System**.

**Ausgabe:** IST-vs-SOLL-Bericht. CC hält für Owner-Review, bevor Phase 1 startet.

---

## 2. Phase 1 — Der Kernel-Antwortvertrag

Der Kernel gibt pro Fall nicht nur Fakten, sondern einen strukturierten **Vertrag**, der den erlaubten Antwortraum definiert. Schema-Skizze — CC verfeinert gegen den echten Kernel-Output:

```
{
  "status": "OUT_OF_SCOPE | NEEDS_CLARIFICATION | COVERED_CAUTION | COVERED_RECOMMENDATION",
  "allowed_claims": [
    { "id": "C-104", "facts": {...}, "text_de_canonical": "...", "severity": "caution|info|disqualify", "provenance": "<erdungs-ref>" }
  ],
  "required_clauses": [
    { "id": "RC-1", "text_de": "Keine Auslegung möglich ohne Temperaturangabe." },
    { "id": "RC-2", "text_de": "Keine Freigabe, nur Vorprüfung." }
  ],
  "missing_fields": ["temperature_max", "medium_exact"],
  "allowed_materials": ["FKM", "PTFE"],
  "allowed_values": { "temperature_max_c": 200, ... },
  "forbidden_phrases": ["geeignet", "belegt", "bewährt", "Richtwert", "freigegeben", "Fachliteratur", "typisch"]
}
```

Regeln:
- **`status`** kommt deterministisch aus dem Coverage-Gate (§1).
- **`allowed_claims`** sind die *einzigen* fachlichen Aussagen, die L1 machen darf — jede mit **ID + Erdungs-Provenienz**. Der Claim trägt die *Fakten* (+ optional eine kanonische deutsche Phrasierung); L1 liefert nur die flüssige Oberfläche *innerhalb* dieses Inhalts.
- **`required_clauses`** MÜSSEN in der Ausgabe erscheinen (Safety, fehlende Auslegung, keine Freigabe).
- **`forbidden_phrases`** = doktrin-konstante + status-abhängige Autoritäts-/Freigabeformeln, wo nicht explizit durch einen Claim erlaubt.
- **Owner-kuratiert, nie modell-generiert.** Die Claim-IDs *sind* die Erdungs-Provenienz.

Hinweis zur Kapazität: Der Vertrag ist der **load-bearing** Teil und Kernel-Arbeit (die knappe Ressource) — bewusst, weil er die Modellfrage *auflöst* statt sie zu entscheiden. Das ist die richtige Stelle, knappe Zeit zu investieren.

---

## 3. Phase 2 — L1 wird Renderer

- L1-Prompt von „schreibe eine fachliche Antwort" auf **„rendere diesen Vertrag in deutsche Prosa"** umstellen. Eingabe = der Vertrag, nicht rohe Fakten.
- **L1 DARF:** sortieren, kürzen, freundlich/verständlich formulieren, Deutsch glätten, Rückfragen verständlich machen, rein sprachliche Übergänge.
- **L1 DARF NICHT:** neue Temperaturen/Materialien/Eignungsaussagen/Literaturbezüge nennen; Autoritätsmarker („belegt"/„bewährt"/„typisch"/„geeignet") verwenden, wo nicht explizit im Vertrag erlaubt; Tabellen generieren, die der Kernel nicht lieferte.
- **Reasoning aus.** Strukturierte Eingabe (Vertrag), constrainte Ausgabe. Fixpräfix (Renderer-Instruktion) cachen.

---

## 4. Phase 3 — claim-level `output_guard` (CODE, fail-closed)

Der eigentliche Guard. Prüft **nicht Strings, sondern Satz-zu-Claim-Abdeckung** — er erzwingt *Erlaubtheit positiv*, statt nach verbotenen Mustern zu suchen. Das ist, was eine *Disposition* fängt und nicht nur Artefakte.

**Hauptprüfung — Abdeckung:** Jeder Satz der Renderer-Ausgabe muss zuordenbar sein zu **genau einem** von:
1. erlaubter Claim (per ID),
2. Pflichtklausel (per ID),
3. Rückfrage (zu einem `missing_field`),
4. Unsicherheits-/Nicht-Auslegbarkeits-Aussage,
5. rein sprachlicher Übergang ohne Fachinhalt.

Nicht-zuordenbarer Satz → **fail-closed** (blocken/regenerieren), GOVERNANCE_LOG-Eintrag.

**Deterministische Vorfilter (schnell, vorgeschaltet):**
- erfundene Zahl (nicht in `allowed_values`) → fail,
- Werkstoff nicht in `allowed_materials` → fail,
- `required_clause` fehlt → fail,
- `forbidden_phrase` ohne deckenden Claim → fail.

**Implementierungsdisziplin für die Zuordnung (Punkt 1–5):** Das ist die schwierige Stelle. Sie startet **deterministisch-konservativ** — Satz-Segmentierung + Abgleich gegen Claim-Texte/Pflichtklauseln + Whitelist sprachlicher Übergänge. **Wo die deterministische Zuordnung nicht sicher ist → fail-closed** (lieber Overblocking als Durchlass; Regeneration des Renderers fängt legitime Fälle auf). Ob für die Zuordnung ein *billiger* LLM-Klassifikator nötig wird, ist **nachgelagert und gemessen** (§5) — nicht jetzt gebaut. Falls ja, ist er ein *Zuordnungs*-Klassifikator, **kein** Fakten-Verifier.

Baut auf vorhandenem L3 auf (Audit §1), dupliziert nicht.

---

## 5. Phase 4 — Offline-Eval-Harness + Modell als Eval-Routine

Die n=3-Probe war Indizienlage; **dies ist die Messung.**

- **Eval-Set (massiv erweitert):** geerdete Fälle, ungeerdete Fälle, Grenzfälle, Safety-No-Gos, bewusst leere Groundings, falsche Nutzerannahmen, widersprüchliche Eingaben, fehlende Temperatur, fehlendes Medium, unzulässige Freigaben. In dasselbe Lineal wie INC-EVAL-CALIBRATION einhängen.
- **Offline gegen denselben Vertrag + Guard messen:** Incumbent (gpt-5.1) als Baseline, Mistral Large 3, und **jedes andere aktuelle Kandidatenmodell**. Modell-IDs aus Live-Docs, nicht aus diesem Dokument.
- **Metriken:** Unsupported-Claim-Rate (claim-level, **die entscheidende**), Required-Clause-Misses, Overblocking-Rate (Guard blockt legitime Renderings), deutsche Renderqualität (owner-adjudiziert), Latenz, Kosten/1000.
- **Modellwahl wird eine Eval-Routine, keine Architekturentscheidung.** Ein Kandidat ersetzt den Incumbent auf L1 **nur wenn**: er die Honesty-Schwelle **ohne** LLM-Guard erreicht **und** die Renderqualität ≥ Incumbent. Sonst bleibt der Incumbent.
- **Mistral darf hier als Red-Team-Helfer mitlaufen** (Kandidaten-Antworten attackieren, potenziell-unsupported phrases vorschlagen) — **nicht** als finaler Gatekeeper.

**Ausgabe:** Bericht für Owner-Review. Der Modell- und der etwaige Zuordnungs-Klassifikator-Entscheid werden AUS diesem Bericht getroffen (TRAP-02), nicht vorab.

---

## 6. Bewusst ausgeklammert (Sperrliste)

- Produktionsswap auf irgendein Modell ohne bestandene Offline-Schwelle.
- Mistral (oder irgendein Modell) als finaler Verifier/Gatekeeper.
- LLM-Guard für Faktenverifikation — Kernel/L3 verifiziert, Code-Guard erzwingt Abdeckung. LLM höchstens als Zuordnungs-Klassifikator, gated hinter §5.
- Router/Eskalation — Folge des Coverage-Gates; wenn später, auf ein aktuelles Modell.
- Modell-Pinning als Doktrin — „Incumbent", nicht „gpt-5.1 für immer".

---

## 7. Akzeptanzkriterien (owner-adjudiziert)

- **Vertrag:** Kernel emittiert `status` / `allowed_claims` (mit IDs + Provenienz) / `required_clauses` / `missing_fields` / `allowed_materials` + `allowed_values` / `forbidden_phrases`; owner-kuratiert; nachvollziehbare Erdung pro Claim-ID.
- **Renderer:** L1 rendert nur den Vertrag; kein neuer Fachinhalt; nachweisbar am Prompt und an Eval-Fällen.
- **Guard:** jeder nicht-zuordenbare Satz fail-closed; deterministische Vorfilter aktiv; konservative Zuordnung mit Overblock-vor-Durchlass; GOVERNANCE_LOG-Einträge.
- **Eval:** erweitertes Set; alle Metriken vorgelegt; Modell- und Klassifikator-Entscheid offen für Owner.
- **Sperrliste eingehalten:** kein §6-Element gebaut oder vorbereitet.

---

## 8. Disziplin (unverändert)

- **Audit-first, halten vor Bau.** Jede Phase owner-gegated. `ops/gate.sh` + GOVERNANCE_LOG + eval-REPLAY durchsetzend.
- **TRAP-02:** CC adjudiziert weder Eval-Ergebnisse noch Modell-/Guard-/Klassifikator-Entscheid — der Owner tut es.
- **Keine erfundenen Datei-/Funktionsnamen** (gegen Repo mappen). **Keine erfundenen Modell-IDs/Preise** (Live-Provider-Docs) — der gefährlichste Fehler in dieser Klasse.
- **Datei-Edits** via Python-Literal-Match-Patches oder Heredocs, nicht nano/inline-sed (Paste-Mangling-Risiko auf dem VPS).
- **Kein modell-generiertes Wissen:** der Vertrag ist owner-kuratiert, der Guard ist Code.

---

*Ende INC-NARRATOR-CONTRACT. Reihenfolge: Audit → Phase 1 (Vertrag) → Phase 2 (Renderer) → Phase 3 (Guard) → Phase 4 (Eval) → (Owner-Entscheid Modell/Klassifikator). Jeder produktiv-mutierende Schritt owner-freigegeben. Gemessen gegen das Eval-Lineal und das GOVERNANCE_LOG.*
