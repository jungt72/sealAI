# sealingAI — Deep-Dive Re-Audit (2026-07-03)

Auditiert von: Claude Sonnet 5 (Haupt-Auditor + 4 parallele Recherche-Agenten, direkte SSH/LangSmith-Verifikation).
Auftrag: Re-Prüfung gegen Leitbild V3 (Juli 2026, unverändert gegenüber der 2026-07-02-Fassung — MD5 des Dokuments nicht historisch vergleichbar, aber Inhalt/Leitsätze identisch zur vorigen Auditgrundlage) + Abgleich gegen das V2.1-Konzept (`docs/V2/sealingai_v2_1_produkt_konzept.md`, `sealingai_v2_1_implementierungs_konzept_cc.md`) + Live-Verdrahtungsprüfung + reale LangSmith-Trace-Analyse.
Repo-Stand: `main`, Commit `1974aa61` (Worktree clean).

**Direkte Antwort auf die Auftragsfrage — "sind wir optimal aufgestellt und ist alles optimal verdrahtet?":** Nein, nicht optimal — aber deutlich besser als am 2026-07-02, mit klar benennbaren, überwiegend bekannten Lücken. Die Kern-Trust-Spine (Kernel-Zahlen, Gegencheck, Guard, Verify) ist real und läuft; die 8 produktiven Feature-Flags zeigen **kein aktuelles Auseinanderlaufen**. Die Verdrahtungsprüfung fand aber **2 schlafende Lücken derselben Bug-Klasse**, die diese Session dreimal aktiv traf (Abschnitt 3) — bislang nie ausgelöst, aber real. Die größten offenen Lücken sind heute vor allem **Wissenstiefe** (RWDR-Gold-Pfad: 0 reviewte Claims) und **zwei komplett ungebaute V2.2-Kernstücke** (Flywheel-Loop, strukturierte Normen-Schicht) — beides bekannte, bewusst zurückgestellte Entscheidungen, keine Überraschungen.

---

## 1. Leitsatz-Ampel — Re-Verifikation

| Leitsatz | Ampel JETZT | Ampel 2026-07-02 | Verändert? |
|---|---|---|---|
| L1 Kernel entscheidet, LLM formuliert | 🟡 | 🟡 | Gleich — P0-B ist live, aber ein Sicherheitsnetz-Prefilter, keine neue Kernel-Autorität. Weiterhin nur 3 hart geschützte Größen |
| L2 Verdikt→Quelle→Status→Coverage | 🟡 | 🟡 | Gleich — P2-D fixt nur einen Tie-Break; Coverage-Gate bleibt inert (`coverage_gate_enabled=False`, bestätigt im Live-Container) |
| L3 Unsicherheit als Zustand | 🟢 | 🟡 | **Hoch** — Frontend konsumiert jetzt echt Backend-State (P4, `Answer.tsx`) |
| L4 Familie orientiert, Compound bewertet | 🟡 | 🟡 | Gleich — keine Compound-Entität existiert |
| L5 Nicht-Wissen zuerst | 🟡 | 🟡 | Gleich — nur Prompt-Doktrin |
| L6 Matching folgt dem Verdikt | 🟢 | 🔴 | **Hoch** — P0-C-Precondition bestätigt gemerged + live auf main |
| L7 Felddaten ≠ Autopilot | 🟢 | 🟢 | Gleich |
| L8 Produkt = Entscheidungsdokument | 🟡 | 🟡 | Gleiche Stufe, aber Lücke schmaler (P3 Wissensstand + P5 Offene-Punkte schließen 2 von 4 Teil-Lücken; Dokument bleibt unpersistiert/unversioniert) |
| L9 Coverage-Tiefe vor Breite | 🟡 | 🔴 | **Hoch, aber qualifiziert** — Katalog jetzt reproduzierbar, aber nur 28/550 Claims reviewed; **0 reviewte Claims auf jeder RWDR-Karte trotz RWDR als Gold-Pfad** |
| L10 Grenzen im Produkt | 🟢 | 🟢 | Gleiche Stufe, Lücke schmaler (gleiche P4-Evidenz wie L3) |

**4 von 10 Leitsätzen sind seit dem letzten Audit real gestiegen (L3, L6, L9, L10), keiner gefallen.** Die verbliebenen 🟡 (L1, L2, L4, L5, L8) sind alle bekannte, im vorigen Audit bereits benannte strukturelle Lücken — keine neuen.

---

## 2. V2.1/V2.2-Konzept vs. Live-Implementierung — echte Lücken

Live-Container bestätigt (`docker exec backend-v2 env`, 2026-07-03): `RESPONSE_CONTRACT_ENABLED=true`, `RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED=true`, `MEDIUM_INTEL_ENABLED=true`, `MATERIAL_PARAM_TABLE_ENABLED=true`, `COVERAGE_GATE_ENABLED=false`, `PRODUKTSPEC_ENABLED=false`.

**Speicher-Korrektur:** `feat/v22-coverage-gate` mergte via **PR #142 / Commit `e1ff942d`** — nicht `670419f1` wie zuvor in einem Memory-Eintrag fälschlich notiert (das ist der unabhängige Frontend-Rebrand-Merge). Alle 4 Coverage-Gate-Commits sind selbst als "(inert)" gelabelt; der Flag bleibt bestätigt aus.

### Echte Lücken (Konzept verspricht, NULL Code existiert)

1. **Flywheel-Loop** (Gap-Logging → Owner-Kuratierungs-Queue → Auto-Eval-Append) — von V2.2 selbst als *tragendes* Langzeit-Moat-Element bezeichnet. Kein einziger Code-Treffer für `flywheel`/`coverage_gap`/`queue` irgendwo im Repo. Nicht einmal ein Scaffold.
2. **Strukturierte Geometrie-Normen-Schicht** (DIN 3760/3761, ISO 3601 als abfragbarer, provenienzbehafteter Datenspeicher) — existiert nur als unstrukturierte Prosa in Fachkarten-/Versagensmodi-Texten. `Case.geometry` und `anwendbare_regime` sind überall leere Scaffolds.
3. **Gegencheck-Zustand `OUT_OF_ENVELOPE` als eigener, narrierter 4. Zustand** — fällt in den generischen `no_matrix_data`/`no_medium`-Eimer ohne eigene L1-Klausel.
4. **5 neue V2.2-Kalibrierungs-Metriken** (insb. false-hedge-rate, unsupported-claim-rate als getrackte Raten) — größtenteils nicht implementiert; nur ein Coverage-Classification-Eval-Case existiert, keiner ist in der hart gegateten Triade.
5. **2 der geplanten Archetyp-Profile** (Elektromotor, Hydraulikzylinder) — Maschinerie fertig, Seed hat nur `getriebe` + `ruehrwerk`, null Inhalt für die anderen zwei.

### Bewusst zurückgestellt (keine Lücken, sondern dokumentierte Owner-Entscheidungen)
Diagnose-/Alternativen-Vertiefung (Dim.5/6), Prelon-Felddaten (Owner-Lock L2, permanent ausgeschlossen), breitere Archetyp-Welle, Token-Streaming, Redis-Working-Memory, Postgres-canonical-Knowledge.

---

## 3. Live-Verdrahtungs-Sweep — Ergebnis: 2 dormant Lücken derselben Bug-Klasse gefunden — **BEHOBEN 2026-07-03T07:00**

**Update:** alle 3 Funde dieses Abschnitts (die 6 Kill-Switches, die 2 Rollen-Felder, das tote `keycloak_proxy.conf`) sind behoben — Commit `ad40ba98`, deployed, live-verifiziert (`docker exec backend-v2 env` + `Settings()`-Re-Parse zeigen alle 8 neuen Passthroughs mit identischen Werten zu vorher — reines No-Op, kein Verhaltensunterschied). Öffentliche Health-Checks (Site + Keycloak) nach dem Deploy grün. Der `JUDGE_PROVIDER`/`JUDGE_MODEL`-Fund stellte sich als kein Bug heraus (siehe unten) und wurde nicht angefasst.

Direkter Abgleich `config/settings.py` (alle 51 `SEALAI_V2_*`-Felder) ↔ `docker-compose.deploy.yml`-Passthrough ↔ `.env.prod` ↔ tatsächlicher Live-Container-Zustand (zwei unabhängige Durchläufe, sich gegenseitig bestätigend) — genau die Prüfklasse, die diese Session dreimal traf (Qdrant `EMBED_*` 2026-06-26, `RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED` 2026-07-03, nginx-Rate-Limit-Mount 2026-07-03).

**Die 8 produktiven Feature-Flags sind alle korrekt durchgereicht** und stimmen dreiseitig (Code-Default, `.env.prod`, Live-Prozess) überein — kein aktuelles Auseinanderlaufen. Nginx-Includes (`snippets/v2_dashboard.conf`, `sealai_proxy_headers.conf`) sind beide über das Whole-Directory-Mount abgedeckt; kein verwaister Include, kein fehlender Mount (die Rate-Limit-Fehlerklasse ist durch den Revert vollständig weg).

**Aber: zwei echte, aktuell schlafende Lücken derselben Bug-Klasse gefunden** — beide betreffen Felder, die von echtem Laufzeit-Code gelesen werden (nicht nur Eval/Tests), aber keinen Compose-Passthrough haben:

1. **Die 6 dokumentierten "Incident-Kill-Switches"** (`verify_enabled`, `ground_enabled`, `compute_enabled`, `memory_enabled`, `understand_enabled`, `distill_enabled`) — ihre eigenen Docstrings sagen ausdrücklich, sie seien für einen Notfall per Env flippbar. Sie fehlen komplett in `docker-compose.deploy.yml`. Noch nie ausgelöst (nie in `.env.prod` gesetzt) — aber genau im Ernstfall, wenn jemand `SEALAI_V2_VERIFY_ENABLED=false` als Notbremse setzen will, würde das lautlos nichts tun.
2. **`auth_admin_role` / `auth_manufacturer_role`** — steuern echten Laufzeit-Zugriff auf die Hersteller-Partner-Admin-/Self-Service-Fläche (`api/deps.py`), fehlen ebenfalls im Compose-Passthrough. Aktuell nicht bestätigt ausnutzbar (die Defaults „admin"/„manufacturer" passen wahrscheinlich zu den echten Keycloak-Rollennamen) — aber unverifiziert, gleiche Bug-Form.

Kleinere Funde (kein funktionaler Bug, nur Aufräum-Kandidaten): `nginx/snippets/keycloak_proxy.conf` war gemountet, aber nirgends `include`d — **gelöscht** (bestätigt tot: hardcodete `https`/`443`, während die 4 echten Keycloak-Blöcke in `default.conf` korrekt `$scheme`/`$server_port` nutzen — kein DRY-Kandidat, echt überholt). `SEALAI_V2_JUDGE_PROVIDER`/`JUDGE_MODEL` stehen in `.env.prod`, wirken aber nie auf `backend-v2` — **geprüft, kein Bug**: `ops/run_eval.sh` liest sie explizit direkt aus `.env.prod` für den lokalen Eval-Harness (anderer Laufzeitpfad, by design), nicht angefasst.

---

## 4. LangSmith — reales Routing-Verhalten (nicht nur Code-Lektüre)

Stichprobe: 60 Root-Runs, letzte ~48h, Projekt `sealai-production`.

- **Modell-Routing:** `answer_model` ist in 100% der 39 vollständigen Turns `gpt-5.1-2025-11-13` — bestätigt die dokumentierte L1-Bindung. (Verifier/Helper-Modell-Routing ist über dieses Feld nicht direkt sichtbar — separater Beobachtbarkeits-Fund, siehe unten.)
- **Grounded-Rate: nur 32,5%** (13/40) der realen Turns sind `grounded=True`. **Konkreter Befund, der Aufmerksamkeit verdient:** dieselbe Frage "Bitte gebe mir informationen zu PTFE" grounded **in allen 4 beobachteten Wiederholungen `False`** — obwohl PTFE mehrfach in der Wissensbasis vorkommt (u. a. FK-PTFE-KALTFLUSS, reviewed). Das ist ein plausibler Retrieval-Treffer, der nie zündet — wert einer gezielten Nachprüfung, nicht Teil dieses Audits.
- **Fehler:** 3× `RateLimitError` (429), alle am 2026-07-01 in einem 6-Sekunden-Fenster, alle mit leerer Frage (vermutlich Health-/Warmup-Calls, keine echten Nutzer-Turns). Keine sonstigen Fehler in 56 erfolgreichen Runs.
- **Incident-Fenster (2026-07-03, ~06:05–06:11 UTC) — präziser als beim Live-Debugging möglich:** Für den tatsächlich fehlgeschlagenen Request (nginx-504 um 06:05:35–06:05:40) existiert **überhaupt kein LangSmith-Trace** — das Signal, dass der Request hing/starb, **bevor** er `Pipeline.run` erreichte (Proxy-/Queueing-/Verbindungsebene, nicht die instrumentierte Pipeline selbst). Ein separater, späterer Trace (06:11:37, Frage "hallo") folgte einem Keycloak-500 (Re-Login-Versuch) und blieb **bis heute `pending`, 0 Child-Runs** — dieser einzelne Turn hat den Server nie erreicht, obwohl das System sich Minuten später von selbst erholte (bestätigt durch erfolgreiche 200er ab 06:14:30). Root Cause bleibt aus LangSmith allein nicht vollständig bestimmbar (kein Trace = kein Beweismittel für das WARUM), aber die Eingrenzung "vor der Pipeline, nicht in ihr" ist neu und wertvoll.
- **Beobachtbarkeits-Lücke, neu gefunden:** LangSmith-Traces zeigen KEINE benannten Stage-Spans (understand/ground/compute/generate/verify) — nur eine flache Kette Root→4×ChatOpenAI. Stage-Timing ist nur über die App-Log-Zeile `v2_turn_timing` sichtbar (nicht über LangSmith abfragbar). Ein Beispiel-Turn zeigte `generate_ms≈17000` — nahe an dem, was einen nginx-Upstream-Timeout auslösen würde. Wer künftig "welche Stufe hat gefeuert" aus LangSmith beantworten will, kann das heute nicht — nur aus den strukturierten Logs.

---

## 5. Priorisierte Einschätzung

**Was heute wirklich fehlt, in Reihenfolge der Signifikanz:**
1. **RWDR-Gold-Pfad hat 0 reviewte Claims** — der laut Leitbild/Konzept wichtigste Anwendungsfall ist wissensseitig am dünnsten belegt. (Bewusst zurückgestellt lt. Owner — "Wissen später vertiefen" — aber diese Zahl sollte bewusst sein, nicht implizit.)
2. **Flywheel-Loop und strukturierte Normen-Schicht sind komplett ungebaut** — beides V2.2-eigene, selbst-deklarierte Kernstücke, beide bei 0% Code.
3. ~~2 dormant Compose-Passthrough-Lücken~~ — **BEHOBEN** (Commit `ad40ba98`, deployed + live-verifiziert, siehe Abschnitt 3).
4. **PTFE-Grounding-Muster** — ein konkreter, reproduzierbarer Fall (4/4 Wiederholungen), der eine bestehende Karte nicht trifft, obwohl sie da ist — lohnt eine gezielte Nachprüfung.
5. **LangSmith-Stage-Sichtbarkeit fehlt** — für künftige Incident-Diagnose wertvoll, aktuell nicht möglich.

**Was NICHT mehr offen ist, entgegen möglicher Annahme:** die komplette Relay-Audit-Backlog vom 2026-07-02-Audit (P0-A/B/C, P2-D, P3, P4, P5) — alle bestätigt live, alle bestätigt korrekt verdrahtet. Die 8 produktiven Feature-Flags zeigen kein aktuelles Auseinanderlaufen; die einzigen gefundenen Lücken sind schlafend (noch nie ausgelöst), nicht aktiv.
