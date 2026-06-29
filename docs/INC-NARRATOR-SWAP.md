# INC-NARRATOR-SWAP — CC-Arbeitsauftrag: LLM-Schicht umstellen & optimieren

**Status:** Ausführbar nach Audit + Owner-Review. Doktrin-gegateter Relay.
**Verhältnis zu V2.2:** Eigenständiges Inkrement, **unabhängig** von INC-COVERAGE-GATE — kann parallel oder davor laufen. Die Mess-Harness teilt sich das Eval-Lineal mit INC-EVAL-CALIBRATION. Eskalation/Router warten ausdrücklich auf INC-COVERAGE-GATE (siehe §8).
**Doktrin-Bezug:** I-COV-1 (LLM adjudiziert nichts deterministisch Entscheidbares), I-COV-4 / Unsupported-Claim-Rate, TRAP-02 (Owner-finale Gates), Fail-closed.

**Ziel in einem Satz:** Den GPT-5.1-Generator durch Mistral Large 3 ersetzen, die LLM-Schicht optimieren (Reasoning aus, Prompt-Caching, PII-Minimierung, Code-Guard statt LLM-Challenger), und die Guard-/Eskalations-Entscheidung **messbar machen statt vorab zu committen**.

---

## 0. Was dieser Auftrag ist — und was bewusst NICHT

**IN diesem Auftrag:** Provider-Abstraktion, Generator-Swap auf Mistral Large 3, die Optimierungen, `output_guard` als **Code**, die Mess-Harness.

**NICHT in diesem Auftrag (gegated):**
- **LLM-Guard** — gated hinter der Messung (§7). CC baut ihn jetzt nicht.
- **Risiko-Router / Eskalations-Routing** — Folge von INC-COVERAGE-GATE, nicht hier (§8).
- **Reasoning-Routing** (dynamisch pro Fall) — hängt an der Coverage-Gate-Risikoklassifikation; später.

Scope-Erweiterung über §0-IN hinaus ist ein Auftrags-Verstoß, kein Mehrwert.

---

## 1. Audit zuerst — IST etablieren, dann HALTEN

CC beantwortet die folgenden Fragen gegen das **echte Repo** und meldet sie, **bevor** irgendetwas gebaut wird. Keine Datei-/Funktionsnamen aus diesem Dokument annehmen — gegen den Ist-Stand mappen.

- **Narrator-Verdrahtung:** Wie ist der L1-/„antworten"-Node heute angebunden? Hartkodiertes Modell (GPT-5.1) oder über eine Abstraktion?
- **Datenfluss in die LLM-Schicht:** Was genau bekommt der Narrator? Nur Kernel-Fakten + Frage-Intent, oder auch kunden-identifizierenden Kontext (Namen, Firma, RFQ-Freitext)?
- **Vorhandene Faithfulness-Prüfung:** Existiert in L3 („verifizieren") schon eine Prüfung, auf der `output_guard` aufbauen kann, statt zu duplizieren?
- **Mess-Infrastruktur:** Existiert das Eval-Lineal als einhängbarer Harness? Wird INC-EVAL-CALIBRATION parallel gebaut? → **nicht zwei Mess-Systeme bauen**.
- **Mistral-Anbindung:** Wie ist das heutige „challenge"-Mistral-Modell verdrahtet — als Generator-Anbindung wiederverwendbar?

**Ausgabe:** IST-vs-SOLL-Bericht. CC hält für Owner-Review, bevor Phase 1 startet.

---

## 2. Phase 1 — Provider-Abstraktion (Voraussetzung)

- **Modellwahl wird Konfiguration, nicht Code.** Wenn eine Abstraktion steht (LangChain-Chat-Interface o. ä.) → nutzen. Wenn nicht → dünnen Adapter einziehen, der Generator und Guard über Config austauschbar macht.
- **Ziel:** Generator und Guard ohne Node-Umbau swappen können — das ist die Voraussetzung dafür, dass die Messung (§6) überhaupt billig ist.
- **Modell-IDs NIE erfinden.** Die aktuellen API-Strings aus den Live-Provider-Docs ziehen (Mistral Large 3 via La Plateforme; Nano-IDs erst in §7). Owner/CC verifiziert jeden String und jeden Preis gegen die Live-Doku, bevor er ins Setup geht.

---

## 3. Phase 2 — Generator-Swap: GPT-5.1 → Mistral Large 3

- Im L1-/„antworten"-Node den **Default auf Mistral Large 3** umstellen, über die Abstraktion aus Phase 1.
- **Reasoning AUS** (Default). Geerdete Narration braucht kein Reasoning; Reasoning verschlechtert die Quellentreue auf Summarization-Aufgaben *und* kostet (versteckte Thinking-Tokens zum Output-Tarif).
- **Prompt-Caching auf dem Fixpräfix** (System-/Narrations-/Format-/Persona-Block). Der variable Teil ist nur die kleine Kernel-Fakten-Nutzlast → ~90 % Input-Rabatt auf jeden Call.
- **Strukturierte/constrainte Ausgabe** beibehalten (Schema), Output knapp (Output kostet 5–6× Input).
- **GPT-5.1 bleibt verdrahtet, aber NICHT Default** — verfügbar als Mess-Baseline (§6) und als *späterer* Eskalations-Kandidat. Eskalation wird hier **nicht** gebaut (§8).

---

## 4. Phase 3 — PII-Minimierung vor der LLM-Schicht

- Sicherstellen, dass **kunden-identifizierender Kontext** (Namen, Firma, Projekt-IDs, RFQ-Freitext mit PII) **vor** dem Narrator entfernt/minimiert wird. Der Narrator bekommt nur die technischen Fakten + Frage-Intent.
- Kernel-seitige Transformation, owner-reviewbar.
- Begründung: Das ist der belastbare DSGVO-Hebel — **Datenminimierung, nicht Anbieter-Flagge**. Mit gescrubbtem Kontext wird die Modellwahl frei (Verarbeitungsort/Subprozessoren/Trainingsnutzung entscheiden dann, nicht die Herkunft des Anbieters).

---

## 5. Phase 4 — `output_guard` als CODE (deterministisch, fail-closed)

Ersetzt den LLM-Challenger für **alles deterministisch Prüfbare**. Prüft die Narrator-Ausgabe gegen die vom Kernel gelieferten Fakten. **Code, kein LLM.** Baut auf vorhandenem L3 auf (Audit §1), dupliziert nicht.

Pflicht-Checks:
- **Erfundene-Grenzwerte-Check:** Jede Zahl in der Narration (Temperatur, Druck, Geschwindigkeit, Maß) muss in den Kernel-Fakten vorkommen oder daraus ableitbar sein. Sonst flaggen.
- **Allowlist-Check:** Werkstoff-/Typ-Nennungen nur aus der vom Kernel erlaubten Menge. Der Kernel entschied das Material — der Narrator darf kein anderes nennen.
- **Safety-Klausel-Check:** Bei kernel-markiert sicherheitskritisch / `OUT_OF_ENVELOPE` / Bestätigung-nötig muss der verlangte Vorbehalt in der Narration stehen.
- **Verbotene-Freigabe-Check:** Formulierungen blocken, die eine Finalfreigabe darstellen, wo der Kernel „bestätigen" / keine Finalfreigabe gesagt hat.

Bei jedem Verstoß → **fail-closed** (blocken/regenerieren), Eintrag ins GOVERNANCE_LOG. Das ist die Durchsetzung von I-COV-4 / Unsupported-Claim-Rate in Code.

---

## 6. Phase 5 — Mess-Harness (das Gate für den LLM-Guard)

- **Setups gegen das Eval-Lineal:** (A) Mistral Large 3 solo + Code-Guard. (B) Ist-Stand GPT-5.1 + Mistral als Baseline. (Optional (C) Mistral + Nano-LLM-Guard nur, falls der Owner vorab eine Vergleichszahl will — sonst erst §7.)
- **Metriken:** Unsupported-Claim-Rate (**die entscheidende**), Invented-Limit-Rate, Safety-No-Go-Misses, Overblocking-Rate, deutsche Antwortqualität (owner-adjudiziert), Latenz, Kosten pro 1.000 Fälle.
- **Ausgabe:** Bericht für Owner-Review. **Die LLM-Guard-Entscheidung (§7) wird AUS diesem Bericht getroffen, nicht vorab.**
- Wenn INC-EVAL-CALIBRATION parallel läuft → in **dasselbe** Lineal einhängen, kein zweites System.

Die Kernfrage, die der Bericht beantwortet: Hält der Kernel + Code-Guard + treuer Mistral-Generator die Unsupported-Claim-Rate schon nahe null? Dann ist **kein** LLM-Guard nötig — ein Generator-Modell reicht, und §7 entfällt.

---

## 7. Phase 6 — Bedingter LLM-Guard (NICHT bauen ohne Owner-Freigabe)

- CC baut den LLM-Guard **jetzt nicht**. Gated hinter dem Phase-5-Bericht + Owner-Entscheid (TRAP-02).
- **Nur falls** die gemessene *semantische* Rest-Unsupported-Claim-Rate (paraphrasierte ungestützte Behauptungen, die der Code-Guard nicht fängt) ihn rechtfertigt → separates Folge-Inkrement: ein **billiges Nano** (GPT-5.4-nano *oder* GPT-4.1-nano *oder* Gemini 2.5 Flash-Lite — Familie **divers** zu Mistral), das **ausschließlich** den semantischen Rest prüft. Reasoning aus.
- Modell-IDs + Preise aus Live-Docs, nicht aus diesem Dokument.
- Owner-Entscheid bei Freigabe: welches Nano (Default-Test GPT-5.4-nano; wenn GPT-4.1-nano auf den Evals gleich gut ist, das günstigere nehmen).

---

## 8. Bewusst ausgeklammert (Sperrliste für diesen Auftrag)

- **Risiko-Router** — Folge von INC-COVERAGE-GATE, nicht hier. Der Router setzt die deterministische Risiko-/Coverage-Klassifikation voraus, die das Coverage-Gate erst liefert.
- **Eskalations-Routing** — fällt *später* fast gratis aus dem Coverage-Gate ab (Eskalation = bei `OUT_OF_ENVELOPE`/`PARTIAL` auf ein stärkeres Modell). Wenn gebaut → auf ein **aktuelles** Modell (GPT-5.4 mini / GPT-5.5-Klasse), **nicht** GPT-5.1.
- **Reasoning-Routing** (dynamisch pro Fall) — hängt an derselben Coverage-Klassifikation; später.
- **Keine modell-generierte Logik.** Der Guard ist Code + Kernel-Fakten.

---

## 9. Akzeptanzkriterien (pro Phase, owner-adjudiziert)

- **Generator-Swap:** Narration läuft auf Mistral Large 3; Reasoning aus; Caching aktiv; deutsche Output-Qualität ≥ Baseline auf dem Lineal (Owner-blind bewertet).
- **PII-Minimierung:** kein kunden-identifizierender Kontext erreicht den Narrator; nachweisbar am Datenfluss.
- **Code-Guard:** fängt erfundene Grenzwerte / Nicht-Allowlist-Material / fehlende Safety-Klausel / verbotene Freigabe deterministisch; fail-closed; GOVERNANCE_LOG-Einträge vorhanden.
- **Messung:** Bericht mit allen Metriken vorgelegt; Guard-Entscheid offen für Owner.
- **Sperrliste eingehalten:** kein §8-Element gebaut oder vorbereitet.

---

## 10. Disziplin (unverändert)

- **Audit-first, halten vor Bau.** Jede Phase ist owner-gegated. `ops/gate.sh` + GOVERNANCE_LOG + eval-REPLAY bleiben durchsetzend.
- **TRAP-02:** CC adjudiziert weder die Messergebnisse noch den Guard-Entscheid — der Owner tut es.
- **Modell-IDs und Preise NIE erfinden** — gegen die Live-Provider-Docs verifizieren, bevor sie ins Setup oder in eine Schätzung gehen. (Erfundene Modellbezeichnungen/Preise sind der gefährlichste Fehler in dieser Klasse von Änderung.)
- **Datei-Edits** via Python-Literal-Match-Patches oder Heredocs, **nicht** nano/inline-sed (Paste-Mangling-Risiko auf dem VPS).

---

*Ende INC-NARRATOR-SWAP. Reihenfolge der Phasen: 1 → 2 → 3 → 4 → 5 → (Owner-Entscheid) → ggf. 6. Jeder produktiv-mutierende Schritt owner-freigegeben. Gemessen gegen das Eval-Lineal und das GOVERNANCE_LOG.*
