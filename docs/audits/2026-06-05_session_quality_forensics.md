# Session-Qualitäts-Forensik — reale Owner-Test-Session (2026-06-05)

**Modus:** strikt read-only · keine Fixes · keine Commits ohne Owner-Go · HALT am Ende.
**Session:** `sealai-production` thread `h_a750f88fd0741f41a19c`, 7 Turns, **18:49:17–18:53:30 UTC**.
**Backend:** `e50c5407-20260605-183643@sha256:18275f1197e7…` (Post-Deploy A1+B+C, Stage-C-Cache aktiv).

**Evidenz-Grammatik:** `[E]` code-/trace-belegt (Run-Zeit / `path:line`) · `[A]` Annahme · `[NV]` nicht verifizierbar.
**Daten-/Secret-Disziplin:** Owner-Freigabe galt **nur für diese Session**, inkl. `inputs/outputs`/Evidence-Queries.
Im Bericht stehen **nur Paraphrasen + Run-Referenzen** — keine Roh-Inhalte kopiert. Externe Hashes/IDs gekürzt.

---

## 0. Turn-für-Turn-Tabelle (alle 7 Turns) `[E]`

| T | Zeit | Nachricht (paraphrasiert) | pre_gate | Route / Tier | Composer / Template | Modell | Evidence: Query (paraphr.) · refs · Cache | tok | Dauer | Vollgen. |
|---|---|---|---|---|---|---|---|---:|---:|---:|
| 1 | 18:49:17 | Begrüßung („guten Abend") | GREETING | CONVERSATION / **T0** | Persona „Thomas Reiter" (Responses-API) | gpt-5.4-nano `[A]` | — (no-case) | 0/59 | 0.04s | 1 |
| 2 | 18:49:36 | „Infos zu PTFE" | KNOWLEDGE_QUERY | CONVERSATION / T1 | KnowledgeAnswerComposer, Modus **material_comparison** | gpt-4o-mini | KnowledgeService kuratierte PTFE-FactCards · **kein governed Evidence-Node** · Cache n/a | 3102 | 6.1s | 1 |
| 3 | 18:49:55 | „bitte vergleiche mit NBR" | KNOWLEDGE_QUERY | CONVERSATION / T1 | KnowledgeAnswerComposer, Modus **no_case_knowledge** | gpt-4o-mini | kuratierte Vergleichs-Hinweise · Cache n/a | 686 | 1.3s | 1 |
| 4 | 18:50:31 | „Funktionsweise eines **rwdfr**?" | KNOWLEDGE_QUERY | CONVERSATION / T1 | KnowledgeAnswerComposer (kuratierte Hinweise) | gpt-4o-mini | **themenfremde PTFE-Fragmente** (FactCard-Bleed) · Cache n/a | 5243 | 7.3s | 1 |
| 5 | 18:51:08 | „danke … was genau benötigst du von mir?" | **GREETING** *(Fehlroute)* | CONVERSATION / **T0** | Persona „Thomas Reiter" | gpt-5.4-nano `[A]` | — | 0/390 | 0.002s* | 1 |
| 6 | 18:51:53 | Bootswelle 60 mm, 5000 U/min, ~2 bar | DOMAIN_INQUIRY | **GOVERNED** / T1 | GovernedAnswerComposer (`…composer_v2`) **+ Repair** | gpt-4o-mini | `qhash 9c7bfc5c` „60mm 5000rpm 2bar Dichtung" · **refs=5** · **MISS** (Erst-Retrieval) | intake 631 + 5487 + 5585 | **14.95s** | **2** |
| 7 | 18:52:49 | „wohl salzwasser … Getriebe hat Getriebeöl" | KNOWLEDGE_QUERY | **GOVERNED** / T1 | **ZWEI:** active_case_side_answer (Knowledge) **+** GovernedAnswerComposer | gpt-4o-mini | side: **refs=0** · governed: `qhash c4d8df45` „2bar 40°C 60mm 5000rpm RWDR Dichtung" · **refs=5** · **MISS** (Query geändert → korrekt neu) | side 5864+2166 · gov intake 570 + 7615 | **~19.9s** (10.6 + 9.3) | **3** |

\* Dispatch-Dauer; der sichtbare Antworttext wurde dennoch von einem Conversation-LLM erzeugt (Fehlroute, s. §6).

**Stage-C-Cache-Bilanz der Session:** 2 governed Retrievals (T6, T7), **beide MISS**, weil die Query-Hashes
korrekt **verschieden** sind (`9c7bfc5c` ≠ `c4d8df45`; T7 fügte Temperatur/RWDR/Material hinzu). **Kein
stale-Cache-HIT.** Conversation-Turns (T1–T5) nutzen den governed Evidence-Node gar nicht. → Q1-Hypothese
„Cache-HIT mit alter Query" ist **widerlegt** (s. §Q1).

---

## Q1 — Turn 4 „rwdfr": Fehl-Erkennung + Konfabulation

**Befund `[E]`:** T4 (@18:50:31) fragte nach der Funktionsweise eines „**rwdfr**" (Tippfehler für RWDR).
Die Antwort erfand ein **nicht existierendes Akronym** und expandierte es frei (sinngemäß „Rotary Wiper
Dynamic Face Ring"), und mischte **themenfremde PTFE-Fakten** ein (HF-Freisetzungsschwelle >300 °C,
–CF2–CF2–-Kette, Permeations-/Beständigkeitsfragment).

- **Warum nicht als RWDR erkannt:** Das RWDR-Seal-Type-Muster ist **exakt-Token, ohne Tippfehler-Toleranz**:
  `\b(radialwellendichtring|wellendichtring|rwdr|wdr|simmerring)\b` — `[E]` `backend/app/domain/seal_type.py:378`.
  „rwd**f**r" matcht keines dieser Tokens → der **Scope/RWDR-Pack feuert nicht**, der Pre-Gate stuft generisch
  als `KNOWLEDGE_QUERY` ein `[E]` (Turn-Metadaten). Der semantische Zweitklassifizierer extrahierte zwar
  `materials:["RWDR","Dichtung"]`, routete aber zu `knowledge_explain` — d.h. die halbe Erkennung floss **nicht**
  in eine Scope-Korrektur.
- **Woher die PTFE-Fragmente:** **nicht** Stage-C-Cache (Conversation-Pfad hat keinen governed Evidence-Node;
  governed Hashes der Session sind ohnehin verschieden, §0). Die `deterministic_answer` des Turns kam aus der
  **KnowledgeService-Kuratierung** und enthielt PTFE-FactCard-Inhalt — ein **FactCard-Bleed**: „rwdfr" matchte
  kein KB-Topic, die kuratierte Hinweis-Schicht lieferte trotzdem PTFE-Fragmente (Carry-over aus dem PTFE-Kontext
  der Turns 2/4-Topik), die der Composer als RWDFR-Fakten verbaute. `[E]` Run @18:50:31.
- **Warum kein Guard:** L1/L2 prüfen Vergleichs-Ranking / Eignungs- / Hersteller- / Compliance-Claims — **nicht**
  „erfundener Bauform-Name" oder „falsche-Werkstoff-Fakten unter falscher Frage". Die Konfabulation passierte
  beide Guards ungehindert. **Doktrin-Lücke: kein Grounding-/Anti-Konfabulations-Guard.**

**Fehlerklasse:** Routing (Typo-Erkennung) **+ Wissensbasis-Lücke** (FactCard-Bleed) **+ DOKTRIN** (Konfabulation
ohne Evidenz, kein Guard). **Schweregrad: PILOT-BLOCKING.** **→ doctrine-review.**
**Fix-Richtung (Wirkung/Aufwand):** (a) Tippfehler-/Fuzzy-Normalisierung der Seal-Type-Tokens vor dem Match
(niedrig); (b) KnowledgeService: bei **kein KB-Topic-Match** keine themenfremden FactCards servieren —
„keine kuratierte Quelle" statt Bleed (mittel); (c) Grounding-Guard, der erfundene Bauform-Definitionen /
Quelle-Frage-Mismatch blockt (mittel, **doktrin-nah**).

---

## Q2 — Letzter Turn (Salzwasser/Getriebeöl)

**(a) Extraktion & Status `[E]`:** Der semantische Router erkannte die Nachricht als
`pending_slot_answer` für das offene Feld **`medium`** (Confidence 0.88, sinngemäß „nennt konkretes Medium
Salzwasser") `[E]` Run @18:52:49. **Aber der governed State enthält kein `medium`-Feld** — die asserted Felder
des Folge-Turns sind `sealing_type=RWDR, pressure_bar, temperature_c, shaft_diameter_mm, speed_rpm, material=NBR`,
**ohne** Medium/Fluid `[E]` Evidence-State @18:53:30. → `intake_observe` hat „salzwasser/getriebeöl" **im Routing
erkannt, aber nicht ins Feld extrahiert/asserted**. Folge: die governed Antwort listet unter **„Fehlende Blocker:
Medium an der Dichtlippe"** — fragt also nach dem **gerade genannten** Medium `[E]` (sichtbarer Antworttext
@18:53:30, paraphrasiert).
- *Drehzahl:* der governed Block listet die Drehzahl **nicht** als offen — er **nutzt** `speed_rpm=5000` und
  rechnet `v = π·d1·rpm/60000 ≈ 15,71 m/s` `[E]`. Die „Drehzahl-offen"-Wahrnehmung stammt vermutlich aus dem
  **Knowledge-Block** (side_answer), der generische Faktoren (Bewegung, Druck, Temperatur …) als „nötig" auflistet `[A]`.

**(b) Zwei Blöcke = zwei Composer-Läufe `[E]`:** T7 erzeugte **zwei getrennte Kompositions-Routen**:
1. `sealai.active_case_side_answer` @18:52:52 — Knowledge-Stil („## Technische Orientierung zu Salzwasser …"),
   **2 Vollgenerierungen**, **evidence_refs_count=0**.
2. `sealai.governed_graph_turn` @18:53:30 — governed Urteil („### Kurzurteil … RWDR-Review-Fall"), 1 Vollgen.
Der Turn lief als `KNOWLEDGE_QUERY` **und** GOVERNED (aktiver Case) → beide Composer feuerten → der User sah
**zwei strukturell verschiedene Blöcke** in einer Antwort.

**Fehlerklasse:** (a) **Extraktion/State-Gate** (Medium erkannt, nicht persistiert) · (b) **Routing/Composition**
(Doppel-Komposition pending-slot vs. knowledge). **Schweregrad: (a) PILOT-BLOCKING** (Kern-Flow „AI extrahiert,
User bestätigt" gebrochen — die gerade gegebene Angabe fällt durch); (b) **P1-hoch** (inkohärente Doppel-Antwort).
**Fix-Richtung:** (a) `intake_observe`/Reducer: `pending_slot_answer` für `medium` deterministisch ins Feld
schreiben, bevor governed antwortet (mittel); (b) bei `pending_slot_answer` **nicht** zusätzlich die
Knowledge-Side-Route auslösen — eine Antwort-Route pro Turn (mittel, Routing).

---

## Q3 — „bis 40 °C": Provenienz-Verlust bei einem nutzer-eingegebenen Wert (Cockpit)

> **Owner-Klärung (2026-06-05, nach Erst-Analyse):** Die 40 °C waren eine **echte Nutzereingabe über das
> Cockpit-Formular** — **kein Default, keine System-Annahme.** Damit ist dies **kein Fakten-Erfinden**; der
> Befund ist ein **Provenienz-Verlust** auf dem Übernahmepfad. Doctrine-relevant bleibt er, weil die Herkunft
> aus dem State **nicht beweisbar** war. (Die frühere „stille Annahme"-Einstufung ist hiermit korrigiert.)

**Befund `[E]`:** Der governed State führt **`temperature_c = 40.0`, confidence `confirmed`, ohne Origin-Tag**
`[E]` Evidence-State @18:53:30; der Wert floss in die **Retrieval-Query** („… 40.0 °C …", `qhash c4d8df45`) und in
den **sichtbaren** Antworttext („Temperaturfenster als Arbeitsstand: bis 40 °C") ein. Der Wert wurde vom Owner
real im **Cockpit-Formular** eingegeben (nicht im Chat).
- **Übernahmepfad:** Cockpit-Direkteingabe → Review-/Override-Endpoint `[E]` `backend/app/agent/api/routes/review.py`
  (`_override_analysis_message`, „… wurde als Nutzerangabe übernommen") → `_run_override_analysis_turn` setzt die
  Felder `confirmed`. Auf genau diesem Pfad geht das **Origin-Tag verloren**: der Wert wird `confirmed`, aber **ohne**
  Envelope, der **Cockpit-Eingabe** von **Chat-Bestätigung** unterscheidet — im State nicht mehr nachvollziehbar.
- **Doktrin-Kern:** Ein liability-tragender Brief-Fakt ist `confirmed`, aber seine **Provenienz ist aus dem State
  nicht belegbar** (Cockpit vs. Chat nicht unterscheidbar) und im Chat **nicht als Formular-Wert kenntlich**. Das
  verletzt das Field-Envelope-Prinzip (status + **origin** sichtbar). Der Wert ist **real und korrekt** — der
  Mangel ist die **fehlende Herkunfts-Attribution**, nicht eine erfundene Angabe.

**Fehlerklasse:** **DOKTRIN** (Provenienz-Verlust bei nutzer-eingegebenem Wert) + State-Gate (Origin-Tracking).
**Schweregrad: doctrine-relevant, KEIN Fakten-Erfinden** (Wert ist echte Cockpit-Eingabe) → **kein Pilot-Blocker
der Konfabulations-Klasse**, aber **Fix vor breitem Pilot** (Herkunft muss beweisbar + attribuiert sein).
**→ doctrine-review.**
**Fix-Richtung (Owner-Zuschnitt):** (a) Übernahmepfad taggt die Herkunft (`sheet_field_edit` / `user_override`
gemäß Field-Envelope), nie `default`→`confirmed` (mittel); (b) **Invariante als Test:** kein Feld erreicht
`confirmed` mit `origin ∈ {None, default}` (Property-Test über Reducer + Override-Pfad); (c) **Attribution im
Output** („via Cockpit-Eingabe"), damit Formular-Werte im Chat als solche erkennbar sind (niedrig).
**Teil (i) read-only verkürzt** (Owner-Klärung): nur klären, **wo** auf dem `review.py`-Pfad das Origin-Tag
verloren geht — **keine Frontend-Untersuchung, voraussichtlich kein Frontend-PR.**

---

## Q4 — Niveau-Gefälle: PTFE-Einzelfrage (dünn) vs. NBR-Vergleich (stark)

**Befund `[E]`:** Beide auf **derselben Route** (CONVERSATION, KnowledgeAnswerComposer, gpt-4o-mini), aber
**verschiedene deterministische Modi**:
- T2 „Infos zu PTFE": `deterministic_answer_mode = **material_comparison**` `[E]` — für eine **Einzel**-Material-Frage;
  Ergebnis dünn (Struktur, Schmelztemp, HF-Schwelle + generische Orientierung).
- T3 „vergleiche mit NBR": `deterministic_answer_mode = **no_case_knowledge**` `[E]`; der NBR-Vergleich wirkte stärker.

→ Die Differenz liegt **am deterministischen Modus/Template + an der kuratierten Ausbeute**, nicht am Modell
(identisch) und nicht am Composer-Pfad (identisch). Der `material_comparison`-Modus liefert bei einer **Einzel**-Frage
keinen Vergleichskontext und fällt auf dünne kuratierte Hinweise zurück; der Vergleichsfall hat zwei Entitäten und
damit mehr deterministische Substanz. `evidence_refs_count` pro Knowledge-Turn ist in den LLM-Spans nicht separat
ausgewiesen `[NV]` (KnowledgeService liefert kuratierte FactCards, kein governed Evidence-Node).

**Fehlerklasse:** **Composer/Template** (Modus-Wahl) + **Wissensbasis-Lücke** (kuratierte Ausbeute Einzel- vs.
Vergleichsfrage). **Schweregrad: P1-Backlog** (Tiefe/Stil, kein falscher Claim).
**Fix-Richtung:** Einzel-Material-Frage nicht in `material_comparison` routen; eigenständiges
„single_material_profile"-Template mit garantierter Struktur (Definition/Rolle/Werte/Grenzen/Anwendungen) (mittel).

---

## §5 — „Nächste-beste-Rückfrage" invertiert?

**Befund `[E]`:** Die **governed** Logik wählt korrekt **eine** priorisierte Frage:
`backend/app/agent/domain/challenge_engine.py::_select_next_best_question` (Emit `ASK_NEXT_BEST_QUESTION`),
konsumiert über `governed_answer_context._next_question` und das Prompt
`backend/app/agent/prompts/governed/answer_composer.j2` („Ask only the plan's next_best_question prominently").
**Aber:** Turn 5 („was genau benötigst du von mir?") wurde als **GREETING** fehlklassifiziert → CONVERSATION →
**Persona-Composer** statt Challenge-Engine. Die Antwort war ein **generischer Checklisten-Block** („schick mir
Anwendung + Medium + Belastungen … 1) Welche Maschine …") `[E]` Run @18:51:08 — also **„welche Angabe fehlt"**
statt **der einen wichtigsten konkreten Frage**.

→ Die Inversion ist primär **Routing**: aktiv-case-nahe „was brauchst du?"-Turns landen auf dem CONVERSATION-Pfad,
der **keinen Zugriff** auf `_select_next_best_question` hat. Zusätzlich zeigt der governed Repair-Grund
`bare_medium_intake_question` `[E]` (Run @18:51:55), dass selbst auf dem governed Pfad „nackte" Slot-Fragen
auftreten und nachträglich repariert werden müssen.

**Fehlerklasse:** Routing + Composer. **Schweregrad: P1-hoch** (Flow-Degradation, kein falscher Claim).
**Fix-Richtung:** (a) „Was brauchst du / lass uns starten" bei aktivem/halb-aktivem Case in den governed
Challenge-Pfad routen, nicht GREETING (mittel); (b) CONVERSATION-Pfad bei vorhandenem Case-Kontext Zugriff auf
die priorisierte Einzel-Frage geben (mittel).

---

## §6 — Schweregrad-Zusammenfassung (Pilot-Sicht)

| Befund | Klasse | Schweregrad | doctrine-review |
|---|---|---|---|
| Q1 Konfabulation „RWDFR" + PTFE-Bleed, kein Guard | Routing + Wissensbasis + **Doktrin** | **PILOT-BLOCKING** | **ja** |
| Q3 „40 °C" confirmed ohne Origin-Tag — **echte Cockpit-Eingabe**, Provenienz-Verlust (kein Fakten-Erfinden) | **Doktrin** (Provenienz) + State-Gate | doctrine-relevant · Fix vor breitem Pilot | **ja** |
| Q2a Medium erkannt, nicht extrahiert → fragt erneut | Extraktion/State-Gate | **PILOT-BLOCKING** | ja (Brief-Fakten-Gate) |
| Q2b Doppel-Composer (Knowledge + governed) in 1 Turn | Routing/Composition | P1-hoch | nein |
| §5 Nächste-Frage invertiert (T5 Fehlroute) | Routing + Composer | P1-hoch | nein |
| Q4 Niveau-Gefälle Einzel vs. Vergleich | Composer/Template + Wissensbasis | P1-Backlog | nein |
| T6 Doppel-Vollgenerierung (Composer+Repair, 14,95 s) | Composer (W3-Klasse) | P1-Backlog | ja (Repair = doktrin-nah) |

**Zwei Pilot-Blocker** (Q1, Q2a) **+ ein Doktrin-Provenienz-Befund** (Q3). Q1 (Konfabulation) erzeugt einen
**Schein-Fakt**; Q2a **verliert** eine reale Angabe (Medium). **Q3 ist nach Owner-Klärung KEIN Fakten-Erfinden** —
der 40-°C-Wert war eine echte Cockpit-Eingabe; der Befund ist der **Provenienz-Verlust** (Herkunft nicht
beweisbar/attribuiert), doctrine-relevant, Fix vor breitem Pilot.

---

## §7 — HALT

Read-only-Forensik abgeschlossen. **Keine Fixes, kein Commit, kein Deploy** ohne Owner-Go. Drei Befunde
**doctrine-review-relevant** (Q1 Konfabulation, Q2a Brief-Fakten-Gate, Q3 Provenienz-Verlust — echte
Cockpit-Eingabe, kein Fakten-Erfinden). Empfohlene
Reihenfolge nach Wirkung/Aufwand: **Q1(a) Typo-Normalisierung** (niedrig) → **Q2a Medium-Extraktion** (mittel) →
**Q3 Origin-Envelope** (mittel) → **Q1(b/c) FactCard-Bleed + Grounding-Guard** (mittel, doctrine) → P1-Backlog.
Jeder Guard-/Doktrin-Fix benötigt vor Merge eine `doctrine-reviewer`-Freigabe + Zero-FP-Proof.
