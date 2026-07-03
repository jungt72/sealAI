# sealingAI — Ist-Situation gegen Leitbild V3

Auditiert von: Claude Fable 5 (via Claude Code; fünf parallele Fable-5-Audit-Subagenten + Haupt-Auditor-Verifikation)
Datum: 2026-07-02
Repo-Stand: `main`, Commit `5d8b5570113dd8f9f366da3ec55204fa9abafc09` (Worktree clean)
Laufzeit-Stand (zusätzlich erhoben): prod-Container-Env `backend-v2` und prod-Qdrant, Stand 2026-07-02

**Metadaten zur Bewertungsherkunft:** Alle Abschnitte wurden von Fable 5 bearbeitet (Hauptschleife + Subagenten erben das Sessionmodell). Bei einem Subagenten (Fachkarten/L4-Bereich) war der automatische Safety-Classifier-Review-Sidecar (Opus) nicht verfügbar; dessen tragende Befunde (Seed-Kartenzahl, Fehlen der `kind`-Taxonomie) wurden vom Haupt-Auditor direkt gegen das VPS-Repo nachverifiziert und bestätigt.

**Methodische Vorbemerkung — drei divergierende Stände:** Dieses Audit trennt durchgängig (a) **Codestand `main`**, (b) **Laufzeitstand prod** (Env-Flags + Qdrant-Datenbestand) und (c) **Dokumentations-/Gedächtnisstand**. Alle drei weichen an entscheidenden Stellen voneinander ab:

1. **Fachkarten-Katalog:** `main` enthält `fachkarten_seed.json` v0 mit **9 Karten / 28 Claims, ohne `kind`-Feld** (verifiziert direkt auf dem VPS-Repo, nicht nur im Audit-Spiegel). Der dokumentierte Stand „47 Karten / 550 Claims + 8-`kind`-Epistemik-Taxonomie" existiert — aber ausschließlich auf dem **nie gemergten lokalen Branch** `feat/fachkarten-prov-promote` (einziger Commit `a22ac243`, 2026-06-28; Seed-Version `fachkarten_seed_v0+prov-promote-20260628`, `kind`-Validierung in `fachkarten.py:132-134` dort vorhanden). Das prod-Qdrant (`sealai_v2_fachkarten`, **614 Punkte**) wurde aus diesem Branch-Stand plus nachfolgenden Paperless-Drafts befüllt. **Konsequenz: der servierte Wissensbestand ist aus `main` nicht reproduzierbar.**
2. **Feature-Flags:** Die Code-Defaults sind sämtlich `False` (`config/settings.py:93-118`), aber prod setzt per Env: `RESPONSE_CONTRACT_ENABLED=true`, `MATERIAL_PARAM_TABLE_ENABLED=true`, `MEDIUM_INTEL_ENABLED=true`; dagegen bestätigt AUS: `COVERAGE_GATE_ENABLED=false`, `PRODUKTSPEC_ENABLED=false`, `BASELINE_HARDENING_ENABLED=false` (Container-Env verifiziert 2026-07-02). Wo Subagenten-Befunde „Flag OFF" sagten, ist unten der prod-korrigierte Stand eingearbeitet.

---

## 1. Leitsatz-Matrix (L1–L10)

| Leitsatz | Status | Beleg (Datei:Zeile) | Befund |
|---|---|---|---|
| **L1** Der Kernel entscheidet, das LLM formuliert | **Teilweise erfüllt** | `core/calc/evaluator.py:5-6,73,96-123`; `core/calc/leak_detector.py:61-69,145-148`; `pipeline/pipeline.py:574-583`; `api/serializers.py:117-119,157-159`; `core/response_contract.py:212-213` | Der Rechenkern ist pur, LLM-frei, fail-closed; Kernel-Kanäle (compute/gegencheck/coverage) erreichen das Frontend „verbatim … not from L1 prose". Kernel-Hoheit ist aber nur für **drei** Größen (`umfangsgeschwindigkeit`, `pv_wert`, `verpressung_prozent`) deterministisch und kill-switch-fest erzwungen. Alle übrigen Zahlen/Aussagen des Free-Narrators schützt live nur Prompt-Disziplin + LLM-Kritiker L3; der Claim-Level-Guard (`output_guard.py`) läuft in prod (Flag an), greift aber per Design nur auf Gegencheck-Turns (`build_contract` → `None` ohne Verdikt) und liefert nach BLOCK→einmal-Regenerieren in jedem Fall aus (`pipeline.py:535-548`). |
| **L2** Kein Verdikt ohne Quelle, keine Quelle ohne Status, keine Aussage ohne Coverage | **Teilweise erfüllt** | `knowledge/fachkarten.py:102-122`; `knowledge/matrix.py:89-94`; `core/coverage.py:17-19`; `config` prod-Env | Teil 1 hart erfüllt: Zirkularitäts-Guard ist Ladezeit-Fehler (reviewed Claim ohne Owner-Provenienz UND ohne Primärquelle → `ValueError`). Teil 2 rudimentär: Quellstatus = nur `reviewed|draft`; die im Leitbild geforderte Statustaxonomie (geprüft/Herstellerangabe/Normbezug/Erfahrungswert/unbestätigt/veraltet/widersprüchlich) existiert nirgends; die 8-`kind`-Taxonomie liegt ungemergt auf `feat/fachkarten-prov-promote`. Teil 3 nicht durchgesetzt: das Coverage-Gate ist gebaut + verdrahtet, aber in prod AUS („The flag stays OFF in prod today") — es gibt keinen Live-Pfad, der Aussagen außerhalb der Coverage verweigert; ungegroundete Antworten werden nur „vorläufig" gerahmt. |
| **L3** Unsicherheit ist ein Zustand, kein Textbaustein | **Teilweise erfüllt** | `core/gegencheck.py:43-47,90-96`; `core/response_contract.py:37,82-125`; `core/coverage.py:28-48`; `frontend-v2/src/contracts.ts:222-233` | Maschinenlesbare Unsicherheits-Zustände existieren vierfach (Gegencheck-`bedingt` mit `condition`+`source` live auf jedem Turn; Contract `NEEDS_CLARIFICATION`/`missing_fields` live auf Gegencheck-Turns; Coverage-Achsen und KandidatenSpec `open_verifications` hinter AUS-Flags). Aber: das Frontend konsumiert **keinen** dieser Zustände (`contracts.ts` kennt weder `gegencheck` noch `coverage` noch `verification`) — beim Nutzer kommt Unsicherheit heute als narrierter Text + ein binäres `grounded`-Badge an. |
| **L4** Werkstofffamilie orientiert. Compound bewertet. Bauteil wird freigegeben — nicht von uns | **Teilweise erfüllt** | `knowledge/fachkarten.py:37-69`; `core/contracts.py:236`; `knowledge/produktspec/contracts.py:126,169-171`; `trap_catalog.json:154-174`; `material_parameters_seed.json:7` | Es existiert **keine Compound-Entität** im gesamten Datenmodell-Stack (Fachkarten, Matrix, Case, Calc, Produktspec, Frontend-Schema — alles Familienebene; feinste Auflösung sind Qualifier wie „EPDM (peroxidvernetzt)"). Die Familie≠Compound-Doktrin ist als Text-/Prompt-Verteidigung präsent (Traps `PREC-COMPOUND-NUMMER`/`PREC-EINZELZAHL` live via L3; Contract-Pflichtklausel „finale Compound-Freigabe trifft der Hersteller" auf Gegencheck-Turns; „nicht von uns" strukturell via `freigegeben=False`-Invariante G1). Der Ist-Stand der Leitbild-Tabelle (Abschnitt 9, Zeile 3) ist hier unverändert gültig. |
| **L5** Was das System nicht weiß, sagt es zuerst | **Teilweise erfüllt** | `prompts/system_l1.jinja:225-231,342-346`; `core/output_guard.py:369-373`; `frontend-v2/src/components/Answer.tsx:12-21` | Klären-vor-Empfehlen und Vorläufig-Offenlegung sind Prompt-Doktrin; deterministisch erzwungen ist nur die Badge-Position (Kandidat/vorläufig **vor** dem Antworttext) und — auf Gegencheck-Turns — das Vorhandensein von Pflichtklauseln. Kein Code prüft die **Reihenfolge** missing-knowledge-first im Antworttext. |
| **L6** Matching folgt dem Verdikt, nie umgekehrt | **Verletzt** | `pipeline/stages.py:38-42,364` | Der Hersteller-/Alternativen-Trigger ist ein reines Keyword-Gate auf der Nutzerfrage (`_ALT_RE`: „alternativ\|hersteller\|lieferant…") **ohne jede Verdikt-Vorbedingung** — im ersten Turn „welcher Hersteller kann NBR-RWDR?" werden Partner gerankt, bevor irgendeine Situationsanalyse existiert. Mildernd: das Ranking selbst ist rein capability-deskriptiv und zahlungsneutral (siehe Abschnitt 5), und der Anfrage-Endpoint rendert das volle Briefing mit. Die Leitbild-Reihenfolge Stufe 1→2→3 ist im Code nicht erzwungen. |
| **L7** Felddaten sind Evidenz, kein Autopilot | **Erfüllt** | `db/models.py:128-145`; `db/contributions.py:1-6,29`; `api/routes/contribute.py:49-51,63-66,70-113` | Contributions sind eine eigene, anonymisierte, als „NEVER auto-feeds the trust spine" firewalled Evidenzklasse mit Owner-Review-Statusmaschine (`neu|reviewed|promoted|rejected`); es existiert kein Code-Pfad Contribution→Fachkarte/Matrix/Seed. Kontext-Hinweis (kein L7-Verstoß, da Doku-Ingestion, nicht Felddaten): der Paperless-Webhook schreibt LLM-extrahierte **Draft**-Fachkarten automatisch in den Live-Qdrant-Index — die dann allerdings im Antwortpfad verworfen werden (siehe Abschnitt 2.3/7.3). Clustering + kodierter Regressions-Gate am Promotion-Pfad fehlen (Leitbild Abschnitt 6 nur teilweise). |
| **L8** Das Produkt ist das Entscheidungsdokument | **Teilweise erfüllt** | `api/routes/briefing.py:29-48`; `render/renderer.py:70-99`; `render/templates/briefing.jinja`; `core/contracts.py:369-376`; `db/models.py:122-123` | Ein deterministisch gerendertes Briefing-Artefakt mit Provenienz-Abschnitt, fail-closed-Offenlegung und Geltungsrahmen existiert (+ client-seitiges PDF). Aber es ist eine **flüchtige Projektion**: nicht persistiert (einzige Ausnahme: Kopie im Lead bei Partner-Anfrage), nicht versioniert, ohne eingefrorene Wissensstand-Referenz (Artifact hat kein Version-/Hash-Feld), ohne strukturierte Trennung Verdikt/Begründung und **ohne Abschnitt „offene Punkte"** — die vorhandenen `open_verifications` der KandidatenSpec fließen nicht ein. Details Abschnitt 3.2. |
| **L9** Coverage-Tiefe vor Breite | **Verletzt** | `knowledge/fachkarten_seed.json` (9 Karten); Branch `feat/fachkarten-prov-promote` (`a22ac243`); prod-Qdrant 614 Punkte; `frontend-v2/src/schema/situations.ts:99-226` | Auf `main`: 9 Fachkarten (28 Claims, 8× Werkstoff-Chemie als Reframing der Trap-Corrects, 1× O-Ring-Verpressung) — **0 RWDR-Karten**, obwohl RWDR der ausgebaute Gold-Pfad ist (9 Feldgruppen im Frontend, Produktspec-Kernel RWDR-only, 2 Archetypen). Die Tiefe liegt auf der Achse Werkstoff×Medium-Disqualifikation, nicht auf einer Dichtungsklasse. Der 47-Karten-Ausbau existiert nur ungemergt + als nicht-reproduzierbarer Qdrant-Laufzeitbestand; die Ausbaureihenfolge (5 Medium- + 7 RWDR/Hydraulik-Karten, dann Paperless-Drafts beliebiger Themen) verstreut sich zusätzlich. |
| **L10** Die Grenzen des Systems stehen im Produkt — nicht im Kleingedruckten | **Erfüllt** (mit benannter Lücke) | `core/framing.py:18-41`; `frontend-v2/src/components/SafetyBanner.tsx:6-13`, `Shell.tsx:140`, `Answer.tsx:12-21`; `api/serializers.py:153`; `pipeline/stages.py:372-399` | Die Doktrin-Zeile („Orientierung, keine Freigabe…") ist Single-Source im Backend, permanent gemountet und contract-getestet; jede Antwort trägt das Kandidat-Badge, ungegroundete zusätzlich „vorläufig"; Panels (Medium/KandidatenSpec/Alternativen) tragen Pflicht-Badges; leerer Partner-Pool wird ehrlich benannt. Lücke: die **fallspezifischen** Grenz-Zustände (Coverage-Status, Gegencheck-Verdikt, L3-Verification) enden am Serializer und erreichen die UI nicht. |

---

## 2. Kernprinzipien (Abschnitt 4)

### 4.1 Compound- vs. Werkstofffamilien-Logik — **Teilweise erfüllt** (Datenmodell: nicht vorhanden)

Beleg: `knowledge/fachkarten.py:37-69` (Claim/Fachkarte ohne Compound-Feld); `core/contracts.py:236` (MatrixCell.werkstoff = „one canonical material" = Familie); `core/seal_spec_extract.py:13-25` (Kanonisierung liefert Familien-Tags); `knowledge/produktspec/contracts.py:126` („G2: no single material before expert_signed"); `frontend-v2/src/schema/situations.ts:193-195` (Werkstoffvorgabe-Enums = Familien); `material_parameters_seed.json:7` (Kennwerte pro Familie, mit Compound-Vorbehalts-Text).

Befund: Die Unterscheidung existiert als **Doktrin** (durchgängig, dreischichtig: L3-Traps `PREC-COMPOUND-NUMMER`/`PREC-EINZELZAHL` immer aktiv; Contract-Pflichtklauseln auf Gegencheck-Turns; Verbots-Vokabular im Produktspec) — aber **nicht als Ebene im Datenmodell**: keine Compound-ID, keine Datenblatt-Entität, kein struktureller Typ-Check, der eine Familien-Quelle an compound-präziser Formulierung hindert. Die Verteidigung ist Phrasen-Matching, nicht Typsystem. Der bekannte Risikopunkt aus Leitbild Abschnitt 9 besteht unverändert.

### 4.2 Risikoklassen — **Teilweise erfüllt** (im Live-Antwortpfad: nicht vorhanden)

Beleg: `knowledge/produktspec/contracts.py:65-69` (`Kritikalitaet: NORMAL/CAUTION/HIGH_RISK/OUT_OF_SCOPE`); `knowledge/produktspec/kernel.py:24-40,66-72,392-394` (Keyword-Eskalation atex/pharma/fda/wasserstoff… → L0-Eskalation); prod-Env `SEALAI_V2_PRODUKTSPEC_ENABLED=false`; `core/contracts.py:98-103` + `api/deps.py:31-33` (zwei globale, fallunabhängige Prompt-Booleans `compliance_hint`/`safety_critical`, in prod pauschal True).

Befund: Eine maschinenlesbare Kritikalitäts-Klassifikation existiert genau einmal — im Produktspec-Kernel, der in prod AUS und zudem RWDR-only ist; `OUT_OF_SCOPE` wird dort nie vergeben (toter Enum-Wert, nur geprüft `kernel.py:393`). Im Live-Pfad gibt es keine Risikoklassen-Schicht: keine der fünf Leitbild-Klassen, keine klassengesteuerte Prüftiefe, keine Pflichtparameter je Klasse, keine Eskalationsschwellen — nur zwei statische Prompt-Blöcke. Leitbild Abschnitt 9 („Risikoklassen-Schicht existiert konzeptionell, nicht im Kernel") ist zu präzisieren: sie existiert inzwischen **im Code**, aber inert und nicht als Kernel-Schicht des Antwortpfads.

### 4.3 Quellenhierarchie / Konfliktlogik / Versionierung — **Teilweise erfüllt** (Hierarchie: nicht vorhanden)

- **Quellenhierarchie: Verletzt / nicht vorhanden.** Kein Code rankt Quell-Typen (Datenblatt > Norm > Schadensfall > …). Vorhandene Ordnungen sind anderes: `review_state`-Zweistufigkeit (`fachkarten.py:31`), Retrieval-Relevanz-Scoring (`retrieval.py:31-32`), Verdikt-Präzedenz im Gegencheck (`gegencheck.py:53-56`: unverträglich > bedingt — Kategorie-Fold, keine Quellgüte).
- **Quellstatus: Teilweise.** Nur `reviewed|draft` + Provenienz-Prefixe; die Leitbild-Statustaxonomie fehlt vollständig. Die 8-`kind`-Epistemik liegt ungemergt (Branch `feat/fachkarten-prov-promote`). Schwächen im Enforcement: `sources` ist inhaltlich unvalidiert (jeder nicht-leere String zählt), `startswith("owner")` matcht ohne Doppelpunkt (`fachkarten.py:33,55-56`).
- **Konfliktlogik: Teilweise (Fragmente).** (1) `matrix_crosscheck`-Feld (`fachkarten.py:67`) wird geladen und **nirgends ausgewertet** — totes Metadatum; (2) widersprüchliche Nutzereingaben → fail-closed Drop mit sichtbarer Notiz (`core/calc/binding.py:247-266`) — Input-, nicht Quellenkonflikt; (3) Gegencheck-Fold disqualify-lean. Eine Datenblatt-A-vs-Hersteller-B-vs-Norm-Auflösung existiert nicht.
- **Versionierung: Teilweise.** Deploy-Ebene ja: `tree_hash` bindet Image-Inhalt an adjudizierte Eval-Runs (`backend/tests/test_eval_manifest_binding.py:3-4`, `test_v2_deploy_gate.py:3,111-113`); Seeds tragen Katalog-Versionen. **Pro Antwort nein:** `api/serializers.py:157-190` enthält kein Wissensstands-Feld; keine Empfehlung ist auf den Wissensstand rückführbar, aus dem sie entstand. Verschärfend der Laufzeitbefund: der servierte Qdrant-Bestand (614 Punkte) ist aus `main` (Seed v0, 9 Karten) **nicht reproduzierbar** — die „eingefrorener Wissensstand"-Anforderung ist damit aktuell auch auf Deploy-Ebene faktisch durchbrochen.

### 4.4 „bedingt" als Zustand — **Teilweise erfüllt**

Beleg: `core/gegencheck.py:43-47,90-96` (live, jeder Turn: `{disqualified: False, basis: "matrix_conditional", condition, source}`); `core/contracts.py:239` (Matrix-Trichotomie `vertraeglich|unvertraeglich|bedingt` mit Begründung+Provenienz); `core/response_contract.py:37,82-125` (`COVERED_CAUTION`, `NEEDS_CLARIFICATION`, `missing_fields` — in prod aktiv, Scope nur Gegencheck-Turns); `core/coverage.py:28-48` (`PARTIAL_ENVELOPE` mit Achsen-Evidenz — prod AUS); `knowledge/produktspec/contracts.py:148-162` (`open_verifications`, `next_question`, `escalation` — prod AUS); `frontend-v2/src/contracts.ts:222-233` (Frontend konsumiert nichts davon).

Befund: „bedingt" existiert mehrfach als maschinenlesbarer Zustand, aber **kein einzelner Zustand trägt alle vier Pflichtfelder** des Leitbilds (Begründung ✓ im Gegencheck; fehlende Evidenz ✓ nur im Coverage-Gate [AUS]; nächster Klärschritt ✓ nur in Contract/KandidatenSpec [Gegencheck-only bzw. AUS]; Eskalationspfad existiert **nur als Textklausel**, nie als Feld). Der Eskalationspfad von „bedingt" zur Klärung ist unverändert nicht produktisiert (bestätigt Leitbild Abschnitt 9, Zeile 2). Beim Nutzer kommt der Zustand nicht an (kein UI-Rendering).

---

## 3. Architektur-Konsequenzen (Abschnitt 7)

### 7.1 Intake-Bindungskette — **Teilweise erfüllt** (Bindung: erfüllt; geführte Vervollständigung: ohne Risikoklassen-Steuerung)

Bindung Chat-Pfad (erfüllt): `api/routes/chat.py:62-70` → Recall `pipeline.py:295-302` → Same-Turn-Inline-Extraktion `pipeline.py:401` + `core/calc/inline_extract.py:41-86` (deterministischer Zahl-Einheit-Scanner über die vier Kernel-Felder) → `bind_params(merge_inline(...))` „fresh > recalled" `pipeline.py:408-410` → `stages.compute` `pipeline.py:418-424`; Folge-Turns via Distiller (`prompts/distill.jinja:33` nennt `druck` explizit als Zielfeld) + `recompute_derived_for` `pipeline.py:766-795`. Kernel-Konsum: `binding.py:133-141` (`druck→p_bar`, `wellendurchmesser→d1_mm`, `drehzahl→rpm`, `geschwindigkeit→v_m_s`); getestet End-to-End (`tests/test_calc_binding_channels.py:79-96`).

Bindung Form-Pfad (erfüllt): `frontend-v2/src/schema/situations.ts:90` (`druck`, role "kernel", kernelKey "p_bar") → `POST /conversations/current/facts` → `edit_fact(provenance="user-form")` → `compute_for` (`api/routes/conversations.py:107-142`); Post-Bind-Echo in der Confirmation (`api/confirmation.py:18-74`).

Geführte Vervollständigung (teilweise): fehlende Calc-Inputs werden deterministisch benannt (`evaluator.py:96-103` → `system_l1.jinja:411-430`); Unit-Recovery als strukturierte `BindClarification` mit One-Click (`binding.py:144-164,189-235`). Aber die Steuerung ist ausschließlich **statisch** (Calc-Def-`input_names`, Form-Schema, Archetyp-Seeds als advisory Prompt-Fragen) — es gibt keinen Pflichtparameter-Katalog je Risikoklasse und keinen deterministischen Erst-fragen-dann-empfehlen-Zwang außerhalb der Gegencheck-Turn-`NEEDS_CLARIFICATION`.

### 7.2 Entscheidungsdokument als First-Class-Objekt — **Teilweise erfüllt** (deutlich unter Leitbild-Definition)

| Leitbild-Kriterium | Ist | Beleg |
|---|---|---|
| persistiert + versioniert | Nein — pro Request neu gerendert, nur React-State; einzige Persistenz als Kopie im Lead | `api/routes/briefing.py:29-48`; `frontend-v2/src/App.tsx:247-271`; `db/models.py:122-123` |
| eingefrorene Wissensbasis-Referenz | Nein — `Artifact` ohne Version-/Hash-Feld; `tree_hash` existiert nur auf Deploy-/Eval-Ebene | `core/contracts.py:369-376`; `backend/tests/test_tree_hash.py:1-13` |
| Trennung Verdikt/Begründung/Provenienz/offene Punkte | Teilweise — Provenienz sauber getrennt; Verdikt+Begründung ungetrennt im L1-Prosatext; **offene Punkte fehlen strukturell** | `render/renderer.py:29-39,89-99`; `render/templates/briefing.jinja` |
| Export strukturiert + lesbar | Nur PDF (client-seitig) + JSON-Response; `kind: "rfq"` explizit „deferred" | `frontend-v2/src/lib/pdf.ts:12-54`; `core/contracts.py:373` |

„Ein Chat-Verlauf ist kein Entscheidungsdokument" ist zur Hälfte eingelöst: es gibt ein eigenes, deterministisch geerdetes Artefakt — mit dem Lebenszyklus eines Chat-Turns.

### 7.3 Fachkarten-Roadmap / Coverage-Tiefe — **Verletzt**

Faktischer Bestand auf `main`: 9 Fachkarten / 28 Claims / 100 % reviewed (8× Werkstoff×Medium-Chemie als 1:1-Reframing der Trap-Corrects, 1× O-Ring-Verpressung); Matrix 28 Zellen; Traps 18 reviewed + 2 draft; Versagensmodi 6 (alle draft); Calc 3 Defs; Material-Parameter 1 Block (PTFE, draft); Archetypen 2. **Null RWDR-Fachkarten** — bei RWDR als Gold-Pfad von Frontend-Schema (situations.ts:99-226), Produktspec-Kernel und Archetypen. Dieselben ~8 Chemie-Kernfälle sind dreifach kodiert (Fachkarten+Matrix+Traps) — konsistent für L3-Korrektur, redundant als Coverage. Der 47-Karten-Ausbau (Branch, ungemergt) + die laufende Paperless-Auto-Ingestion beliebiger Dokumentthemen folgen keinem erkennbaren Tiefe-vor-Breite-Pfad je Dichtungsklasse. Zusätzlich strukturell: auto-ingestierte Draft-Karten sind im Antwortpfad wirkungslos (siehe unten), d. h. der Wissensaufbau via Paperless zahlt derzeit auf keine Coverage ein.

**Struktureller Nebenbefund (toter Provisional-Kanal):** `stages.py:114-142` befüllt `RetrievalResult.provisional` (Draft-Claims), aber `pipeline.py:392-397` baut `l1_grounding = grounding_facts + matrix_facts` — `retrieval.provisional` wird **an keiner Stelle** von pipeline.py konsumiert; weder L1-Prompt noch Citations noch Frontend sehen Draft-Fachkarten. Damit ist die gesamte Kette Paperless-Upload → Draft-Fachkarte → Qdrant-Punkt live wirkungslos. Verschärfung: der Qdrant-Retrieval hat **keinen serverseitigen review_state-Filter** (`qdrant_retrieval.py:227-248`, nur `tenant_id`) — Drafts konkurrieren mit reviewed Claims um dieselben Top-k-Slots und können mit wachsendem Draft-Bestand reviewed Treffer verdrängen, die dann fehlen, während die Drafts verworfen werden. (Kontrast: Draft-Versagensmodi und Draft-Material-Parameter wirken sehr wohl, mit Vorläufig-Marker — `stages.py:323-337`.)

---

## 4. Bekannte P0-Defekte — aktueller Status

| P0 | Status | Beleg |
|---|---|---|
| **Binding-Bug Druck→Kernel** | **Behoben (im Code, getestet)** | `binding.py:30-32` („druck→p_bar was UNPARKED in Phase 2a … pressure feeds the PV kern, binding ONLY in bar") + `:136-137`; Same-Turn-Inline-Extraktor `inline_extract.py:41-56` (Test `test_calc_inline_extract.py:28-38`); `pv_wert` nicht seal_type-gated (calc_seed.json: `conditions = {}`); fehlendes `v_m_s` → ehrliches `NotComputed` statt stillem Verlust (`evaluator.py:96-103`). Bewusste, sichtbare fail-closed-Restgrenzen: nur exakt „bar" bindet (mbar/kPa/MPa/psi → Rückfrage, nie Rescale, `binding.py:67-104`); „16bar" ohne Leerzeichen fängt erst der Distiller im Folge-Turn (`inline_extract.py:32`); >1 Druck-Nennung/Nachricht → Defer an Distiller (`inline_extract.py:70-75`). Einschränkung: auditiert ist der Code-Stand `main`, nicht das aktuell deployte Image-Binärartefakt. |
| **L1-Scope-Leak** | **Teilbehoben** | Live und unbedingt: nur Prompt-Regeln (`system_l1.jinja:236-252` Off-Topic-Hartgrenze inkl. „Selbst-Lizenz ist ein Verstoß") + L3-Kritik (Traps/Matrix-Widersprüche; Karten-Widersprüche FLAG-only, `l3_verifier.py:225-259`) + parametrische Schranke (3 Kern-Größen). In prod zusätzlich aktiv: Response-Contract + Output-Guard — aber v1-Scope **nur Gegencheck-Turns** (`response_contract.py:212-213`: „Returns None for non-suitability turns") und BLOCK→Regen-once→ausliefern (`pipeline.py:535-548`). Der bindende Modus-Deckel (Coverage-Gate, `system_l1.jinja:51-61`) ist in prod AUS. Auf allen Nicht-Gegencheck-Turns kann der Free-Narrator scope-fremde, nicht-numerische Aussagen ungeprüft shippen. |
| **L1-Material-Grounding** | **Teilbehoben** | Grounding-Kanäle existieren (`pipeline.py:392-397` → „Belegte Fakten"-Block `system_l1.jinja:334-347`), aber der Prompt lizensiert Material-Ableitungen aus Prinzipien ausdrücklich auch ohne Matrix-Treffer (`system_l1.jinja:111-115`). Der claim-level `invented_material`/`invented_number`-Guard (`output_guard.py:347-367`) läuft in prod, greift aber nur auf Gegencheck-Turns; `baseline_hardening` („unklare Medienklasse → keine Werkstoff-Familie", `system_l1.jinja:124-136`) ist in prod AUS; der geerdete Kennwert-Store enthält genau **ein** Material (PTFE, draft — `material_parameters_seed.json`), Flag in prod AN — für jedes andere Material rendert L1 Kennwerte ohne Kernel-Quelle, deterministisch ungeprüft (L3 prüft nur Widersprüche gegen injizierte Zellen/Traps). |

Die Leitbild-Tabelle Abschnitt 9, Zeile 1 („Parameter-Binding erreicht den Kernel nicht durchgängig") ist damit **überholt** — das Binding ist durchgängig; Scope-/Grounding-Fehler bestehen abgeschwächt fort (deterministische Begrenzungsmaschinerie gebaut, aber teils AUS, teils Gegencheck-only).

---

## 5. Vier-Stufen-Matching-Modell — Baugrad

| Stufe | Baugrad | Beleg + Kernbefund |
|---|---|---|
| 1 Anwendungsprofil | **Gebaut** (Slots teils Scaffold) | Durables Case-State `v2_facts` mit Provenienz + `as_of_turn` (`db/models.py:43-53`); typisiertes `Case` (`core/contracts.py:491-546`, Slots `archetype/conditions/geometry` erklärter Scaffold „populated later"); typisiertes `Fall`-Profil ~20 Achsen für Produktspec (`produktspec/contracts.py:79-107`). |
| 2 Lösungsprofil | **Teilgebaut** | Werkstoffebene live: Matrix-Trichotomie + Gegencheck (disqualify-only, `stages.py:286-317`). Volles Lösungsprofil (primary/alternatives/excluded + reason_codes + Envelope-Bänder GREEN→RED) existiert im Produktspec-Kernel (`produktspec/contracts.py:129-144`, `kernel.py:85-113`) — prod AUS + RWDR-only (`produktspec_step.py:121-133`). Dichtungstyp-Ebene (welche Bauformen plausibel/ausgeschlossen) existiert typübergreifend nicht. |
| 3 Produkt-/Herstellerkandidaten | **Teilgebaut** (Datenmodell dünn; Neutralität vorbildlich) | Datenmodell `V2HerstellerPartner` (`db/models.py:78-104`): `werkstoffe, bauformen, groessen (Freitext), zertifikate` — **es fehlen** Produktlinien, Datenblätter, Sonderfertigung, Lieferfähigkeit; kein Produkt-Objekt existiert. Ranking = Material-+Bauform-Overlap (`hersteller_partner.py:45-61`). **Zahlungsneutralität strukturell + test-gelockt erfüllt:** `plan` nie Ranking-Input (`hersteller_partner.py:64-78`), Capability-Schicht wirft bei jedem Payment-Feld (`knowledge/hersteller.py:83-97`: „§3.9 kein pay-to-rank"), Test `tests/test_alternativen.py:50-98`; UI-Label „Partner · Anzeige". Ehrlicher Leerstand: leerer Pool → „kein Partner-Hersteller gelistet", null erfundene Firmen (`stages.py:372-382`). |
| 4 RFQ / menschliche Freigabe | **Teilgebaut** | `POST /api/v2/anfrage` (`api/routes/anfrage.py:44-96`): server-authoritatives Briefing, durabler Lead, `lead_email` nie an den User, expliziter Außerhalb-Hinweis (Z.91-95). **Offene Punkte für den Hersteller sind nicht strukturiert im RFQ** (KandidatenSpec-`open_verifications` erreichen das Briefing nicht). Der Leitbild-Satz „Herstellerkandidat noch nicht freigegeben" existiert nicht wörtlich, funktional äquivalent via `freigegeben=False`-Invariante (G1) + `GELTUNGSRAHMEN_SPEC` + Leerstands-Ehrlichkeit. |

Querbefund L6: die Stufenfolge ist nicht erzwungen (Keyword-Trigger, siehe Leitsatz-Matrix).

---

## 6. Klasse-C-Grenzverletzungen — Fundstellen

**Keine violation-fähige Fundstelle gefunden.** Im Einzelnen:

- **Freigabe-/Zulassungssprache:** Exhaustiver Grep (freigegeben, Freigabe erteilt, geprüft und zugelassen, zertifiziert, garantiert, bedenkenlos, ist zugelassen für, empfohlen und freigegeben) über `*.py/*.jinja/*.tsx/*.ts`: alle Treffer sind Abwehr-Infrastruktur — FORBIDDEN-Listen (`response_contract_policy.py:36-37`; `produktspec/contracts.py:18-24` `VERBOTENE_WOERTER`), strukturelle Invariante `freigegeben: bool = False` (G1, `produktspec/contracts.py:160`; `produktspec_step.py:115` „always False"), `bedenkenlos`-Detektor (`equivalence_guard.py:30`), sowie ausschließlich **negierende** Verwendungen in Prompt und Frontend („keine Werkstofffreigabe", „finale Freigabe bleibt beim Hersteller"). `zertifiziert` als Zusage: keine Fundstelle (nur `zertifikate` als Capability-Datenfeld).
- **Verdikt-Rendering:** Gegencheck ist per Doktrin disqualify-only („may DISQUALIFY, never QUALIFY … never an affirmative ‚passt'", `gegencheck.py:9-13`); affirmatives „ja, passt" ist im L1-Prompt verboten (`system_l1.jinja:153-164`); KandidatenSpec trägt „Screening, keine technische Freigabe" verbatim (`produktspec/contracts.py:14-17`).
- **Preis/Lieferzeit/Konditionen:** Kein Codepfad nennt oder verspricht Preise/Lieferzeiten; die RFQ-Route verweist die Angebotserstellung explizit nach außerhalb (`anfrage.py:91-95`); einzige „delivery"-Treffer betreffen E-Mail-Zustellung von Leads (`db/models.py:111`).
- **Restrisiko (kein Fund, aber benannte Enforcement-Lücke):** Ein generischer Detektor für Freigabe-Sprache im L1-Output existiert nur im Output-Guard-Prefilter (`output_guard.py:341-345` + `_SUITABILITY`-Vokabular `:48-71`) — in prod aktiv, aber nur auf Gegencheck-Turns; auf allen anderen Turns ist die Klasse-C-Grenze ausschließlich prompt- und L3-gedeckt. Kein Hard-Gate heißt „false_release".

---

## 7. Nicht auditierbare Bereiche

1. **Deploytes Image-Binärartefakt:** Auditiert wurde der Codestand `main` + Laufzeit-Env/Qdrant; ob das laufende prod-Image byte-genau `main@5d8b5570` entspricht, wurde nicht verifiziert (die P0-1-Bewertung „behoben" gilt für den Code-Stand).
2. **`ops/`-Gate-Skripte** (`ops/v2_deploy_gate.py`, `ops/tree-hash.sh`): außerhalb des Audit-Spiegels; bewertet nur mittelbar über ihre Tests (`backend/tests/test_v2_deploy_gate.py`, `test_tree_hash.py`). Anmerkung aus dem Repo-Kontext: das Eval-Gate im Release-Skript ist derzeit owner-autorisiert temporär deaktiviert (Memory-Stand; im Spiegel nicht prüfbar).
3. **Qualität des 47-Karten-Standes:** Der Branch `feat/fachkarten-prov-promote` wurde als Existenz-/Struktur-Nachweis geprüft (Kartenzahl, `kind`-Validierung), nicht inhaltlich auditiert — er ist nicht Teil von `main`.
4. **CI-Konfiguration:** Keine CI-Definitionsdateien im Spiegel; die „3 required status checks" auf `main` (Server-Meldung bei Push) waren nicht einsehbar.
5. **Live-Verhalten der LLM-Schichten:** Prompt-Disziplin-Aussagen (was L1/L3 „tut") sind aus Templates + Guards belegt; tatsächliches Modellverhalten ist nur per Eval messbar und war nicht Teil dieses Code-Audits.

---

## Anhang: Leitsatz-Ampel (Einzeiler)

| | Leitsatz | Ampel |
|---|---|---|
| L1 | Kernel entscheidet, LLM formuliert | 🟡 deterministischer Kern + 3 hart geschützte Größen; Rest Prompt/L3, Contract nur Gegencheck-Turns |
| L2 | Verdikt→Quelle→Status→Coverage | 🟡 Provenienz-Guard hart; Statustaxonomie fehlt; Coverage-Gate in prod AUS |
| L3 | Unsicherheit als Zustand | 🟡 Zustände gebaut (teils AUS), UI konsumiert keinen davon |
| L4 | Familie orientiert, Compound bewertet | 🟡 Doktrin dreischichtig, aber keine Compound-Ebene im Datenmodell |
| L5 | Nicht-Wissen zuerst | 🟡 Prompt-Doktrin + Badge-first; keine deterministische Reihenfolge-Prüfung |
| L6 | Matching folgt dem Verdikt | 🔴 Keyword-Trigger ohne Verdikt-Vorbedingung (Ranking selbst neutral) |
| L7 | Felddaten ≠ Autopilot | 🟢 Contributions strukturell firewalled, kein Auto-Pfad in die Wissensbasis |
| L8 | Produkt = Entscheidungsdokument | 🟡 deterministisches Briefing-Artefakt, aber ephemer, unversioniert, ohne offene Punkte |
| L9 | Coverage-Tiefe vor Breite | 🔴 9-Karten-Chemie-Kern auf main, 0 RWDR-Karten am Gold-Pfad; 47-Karten-Stand ungemergt; Qdrant nicht reproduzierbar |
| L10 | Grenzen im Produkt | 🟢 Doktrin-Zeile + Badges backend-owned und permanent; fallspezifische Status erreichen die UI nicht (benannte Lücke) |
