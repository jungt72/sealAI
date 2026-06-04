# V1.7 Gap-Audit — Re-Run · `demo/rwdr-limited-external` @ `38f579c7` · 2026-06-04

> **Messlatte:** V1.7 *Universal Sealing Case Platform* Blueprint §11 (AC 1–10),
> read-only via `git show origin/feat/v1.7-blueprint:docs/sealing_intelligence_v1_7_universal_sealing_case_platform_blueprint.md`
> (Blueprint-Datei single-commit `c9c3b47b` — **unverändert** seit dem letzten Audit;
> der Branch-Ref steht jetzt auf `7e215e06`), **plus** die fünf ergänzenden
> S-Kriterien des 2026-06-03-Audits (S1 Trace §6.1 · S2 Tier §6.2 · S3 State-Gate
> Single-Writer · S4 RFQ-Readiness · S5 Mode-Coverage §5.3). **Inklusive der seitdem
> dokumentierten Amendments als gültige Latte** (C7-Liefervertrag · C2/C4-Lesarten ·
> `:499` als dokumentierter Core-Check · C5-Routing-Deferral) — diese werden
> **verifiziert** (existieren? datiert? begründet?), nicht hinterfragt.
>
> **Methodik (identisch zur Vorlage `docs/audits/2026-06-03_v17_gap_audit.md`):**
> strikt **read-only** (Read/Grep/Glob/`git show`/`docker inspect`); keine Patches.
> Default je Kriterium **FEHLT bis zum Beweis**, in beide Richtungen falsifiziert.
> Evidenz-Grammatik `[E] path:line — "Zitat"` / `[A]` / `[NV]`. Verfahren: 20
> read-only Verifikations-Agenten (1× je Kriterium + 4× Amendment + 1× adversariale
> Core-Sweep), jeder Befund anschließend **per Hand am Live-Code nachgeprüft**.
>
> **Prüfgegenstand = was DEPLOYED ist, nicht nur was gemerged ist** (Owner-Vorgabe,
> Tiefe: Digest-Pin + statisch):
> - **Live-Backend:** `ghcr.io/jungt72/sealai-backend:3627b2f7-20260604-144259@sha256:05953eda…`,
>   `status=running health=healthy` (aus dem Daemon, nicht aus Erinnerung). Tag-Commit
>   `3627b2f7` = **demo-HEAD (`38f579c7`) minus ausschließlich den Docs-Closeout-Merge #62**
>   (`git log 3627b2f7..HEAD` = zwei Docs-Commits). → **aller C5/C10/P0/P1-*Code* ist live**;
>   nur die Closeout-*Doku* fehlt im Image. Working-Tree-Code = Live-Code (byte-identisch).
> - **Live-Frontend:** `ghcr.io/jungt72/sealai-frontend:ac7402ea-20260604-101815@sha256:f27f9b5e…`,
>   `healthy`. `git diff --stat ac7402ea..HEAD -- frontend/` = **leer** → Frontend-Code
>   aktuell mit demo-HEAD; der P0-3-Fix (PocketCockpit `rfq_status`) ist live.

## 1. IST-Zustand

Der Runtime ist ein governed V9.2/V10-Stack. Die **C6-Tenant-Härtung** (P0-1/P0-2)
hält der unabhängigen Nachprüfung stand: LTM ist tenant-gescoped, fehlender
Tenant-Claim ist strikt 401, alle Case/RFQ/Evidence-Routen filtern query-level.
Der **RWDR-Killer-Flow** (C7) ist durchgängig live mit single-sourced `rfq_status`;
der **Mobile-First-Contract** (C8), die **RFQ-Readiness** (S4) und das
**zentrale Trace/Tier-Instrumentarium** (S1/S2 — beide auf *allen* Streaming-Routen)
sind sauber. **Herstellerfeedback** (C10) ist strukturell aufgenommen und
laundering-resistent.

Die Re-Run **weicht in drei Punkten vom 2026-06-03-Audit ab** — alle durch
Falsifikation und Hand-Nachprüfung am Live-Code belegt:

1. **C1 (Core/Pack-Trennung) ist überstellt als ERFÜLLT.** Die Seam
   (`app/domain/seal_packs.py`) existiert und wird von den **drei** Dateien, die
   P1-1/P1-3 explizit adressiert haben (`orchestrator.py`, `calculation_projection.py`,
   `risk_readiness.py`), korrekt benutzt; `:499` ist ein legitimer dokumentierter
   Core-Check. **Aber** der Kern trägt weiterhin **nicht-dokumentierte
   `== "rwdr"`-Verzweigung** in drei generisch benannten Core-Flächen, die die
   P1-Arbeit nie berührt hat und die `CORE_PACK_BOUNDARY.md` als „resolved" überzeichnet:
   die **State-Gate-Reducer** (per-Typ-Pflichtfeld-Dict), die **Challenge-Engine**
   (live im Turn-Chain) und die **Cockpit/Workspace-Projektion**. Das ist exakt das von
   §3.3 verbotene „RWDR-Logik in der Plumbing"-Muster.
2. **S3 (State-Gate Single-Writer) ist strenggenommen TEILWEISE.** Die Invariante ist
   an zwei Stellen dokumentiert und für direkte Konstruktoren sauber, **aber** nicht
   test-erzwungen, und zwei Produktionsstellen erzeugen via `model_copy(update=…)`
   neue governed-Layer-Instanzen mit berechnetem Inhalt außerhalb der Reducer-Kette.
3. **Matrix-vs-Detail-Inkonsistenz im Vor-Audit** für **S1/S2**: die Matrix-Zeilen
   standen noch auf TEILWEISE, während die Detail-Sektionen (P1-2) bereits ERFÜLLT
   ausweisen. Wahrer aktueller Stand = **ERFÜLLT** (hier rekonziliert).

Zusätzlich zwei verdikt-neutrale **LOW-Vorbehalte**: **C9** ist als Scaffold-Frage
erfüllt, aber der Kern trägt eine voll implementierte, unbedingt aufgerufene
O-Ring-Berechnung (`_oring_calculations`) — die Kehrseite des C1-Befunds; **C10**s
`rag_supported`-Echo ist implementiert + getestet, aber in **keinen** Live-Output-Pfad
verdrahtet (AC10 „vorgesehen" gleichwohl erfüllt).

## 2. Gap-Matrix

| # | Kriterium (Kurzform) | Verdikt (Re-Run) | Diff vs. 2026-06-03 | Kern-Evidenz | Konf. | Schwere |
|---|---|---|---|---|---|---|
| **C1** | Core/Pack-Trennung (kein RWDR in Plumbing) | **TEILWEISE** | **↓ war ERFÜLLT** — 3 nicht-erfasste Core-Flächen | `reducers.py:200`, `challenge_engine.py:574/719/755/787`, `case_workspace.py:976/1343/1835` — live `== "rwdr"`, nicht seam-routet, nicht der `:499`-Check | 8 | **HIGH** |
| **C2** | DomainPack-Extension-Point | **ERFÜLLT-per-Amendment** | = (Tabelle) | `domain_pack.py:24` Protocol + `seal_packs.py:65` 1-Eintrag-`_PACKS`; Registry per §3.5 deferred | 8 | — |
| **C3** | Klassifikationsstufe wählt Pack | **ERFÜLLT** | = | `orchestrator.py:315→333` `normalize_seal_type()`→`required_fields_for`→`pack_for` (`seal_packs.py:82`) | 8 | — |
| **C4** | required_fields domänenspezifisch | **ERFÜLLT** | = Verdikt, Beleg stärker (Core-Tupel relocated); Konf. ↓ | `seal_required_fields.py:19` (relocated 6-Tupel) ≠ `rwdr_mvp_brief.py:115` (31) — ∩ = ∅; Querbezug `reducers.py:200` s. C1 | 8 | — |
| **C5** | Cross-Cutting vs. Domain-Wissen getrennt | **ERFÜLLT-per-Amendment** | = | `rag_schema.py:57` `pack_affinity`, gesetzt `rag_ingest.py:1023`; retrieval-inert (nicht in `_SUPPORTED_METADATA_FILTER_KEYS`) | 9 | — |
| **C6** | Tenant-Scoping (Case/Datei/Evidence/RFQ) | **ERFÜLLT** | = | `dependencies.py:132` strikt 401; LTM `memory_core.py:64-70` tenant+user; RWDR/RFQ-Gateways query-gefiltert | 9 | — |
| **C7** | RWDR-Killer-Flow durchgängig live | **ERFÜLLT-per-Amendment** | = | Kette live; Stubs entfernt `contracts.py:303-305`; `rfq_status` single-source `dashboard_contract.py:105` | 9 | — |
| **C8** | Mobile <1s Fortschritt + Degraded-Photo | **ERFÜLLT** | = | `mobile_triage.py:166` `first_progress_ms:0`; `PocketCockpit.tsx:56-69` Empty-Spinner-Guard; echte <1s = `[NV]` | 9 | — |
| **C9** | Keine spekulative Abstraktion über RWDR | **ERFÜLLT** | = Verdikt, **Konf. 9→8 + LOW-Vorbehalt** | keine `o_ring/`/`flat_gasket/`-Scaffolds; **aber** `_oring_calculations` (`orchestrator.py:469`) unbedingt aufgerufen `:625` (Querbezug C1) | 8 | LOW |
| **C10** | Herstellerfeedback strukturell aufgenommen | **ERFÜLLT** | = Verdikt, **+ LOW-Vorbehalt** (Echo nicht verdrahtet) | Intake `rfq.py:279`; `_NEVER_BRIEF_SOURCE_TYPES` short-circuit `rwdr_mvp_brief.py:3327`; Echo `…:2478` ohne Caller | 9 | LOW |
| **S1** | Trace-Felder (§6.1) | **ERFÜLLT** | **↑ Matrix-Zeile war TEILWEISE (stale); Detail war ERFÜLLT** — rekonziliert | `turn_timing.py:21-56` zentraler Timer; `sse_contract.py:103-114` stempelt alle 10 finalen `state_update` | 9 | — |
| **S2** | Tier-Disziplin (§6.2) | **ERFÜLLT** | **↑ Matrix war TEILWEISE (stale); Detail war ERFÜLLT** — rekonziliert | `turn_tier.py` fail-closed + `enforce_retrieval_allowed()` am `hybrid_retrieve`-Funnel; BM25-Fallback = latente Defense-in-Depth | 8 | LOW |
| **S3** | State-Gate Single-Writer | **TEILWEISE** | **↓ war ERFÜLLT** — kein Test-Enforcer + 2 `model_copy`-Bypässe | `reducers.py:16-19` Invariante (sauber f. Konstruktoren) **aber** `api/utils.py:180`, `output_contract_assembly.py:1822` schreiben governed-Layer außerhalb; kein AST-Test | 7 | LOW |
| **S4** | RFQ-Readiness | **ERFÜLLT** | = | `rfq_one_pager.py:21-33` 5 Bänder + `evaluate_rfq_readiness()` (deterministisch) + `build_rfq_snapshot(case_revision=…)` | 9 | — |
| **S5** | Mode-Coverage (§5.3) | **TEILWEISE** | = | `contracts.py:15-27` 11 TurnRoutes vs. 30 §5-Modes; verteilt über Template-`allowed_modes` (16) + `KnowledgeMode` (7) + Verhalten; Upload/Document-Familie real unvollständig | 8 | LOW |

Verdikt-Verteilung Re-Run: **ERFÜLLT 7** (C3,C4,C6,C8,S1,S2,S4) · **ERFÜLLT-per-Amendment 3**
(C2,C5,C7) · **ERFÜLLT + LOW-Vorbehalt 2** (C9,C10) · **TEILWEISE 3** (C1 HIGH, S3 LOW, S5 LOW).

## 3. Befunde im Detail (nur wo Verdikt/Evidenz bewegt)

### C1 — Core/Pack-Trennung · **TEILWEISE · HIGH** (war ERFÜLLT)
Die Seam ist real und für die drei P1-adressierten Dateien korrekt benutzt — das
hält der Nachprüfung stand: `[E] backend/app/agent/v92/calculation_projection.py:88
— "if pack_for_calc_id(calc_id) is not None:"`, `[E] backend/app/agent/domain/risk_readiness.py:438/465/533/561`
(pack-routet), `[E] backend/app/agent/v92/orchestrator.py:54 — "from app.domain.seal_packs
import required_fields_for as _required_fields_for"`. `:499`/`:505` ist ein legitimer
dokumentierter Core-Check (s. §4 A-499).

**Falsifikation (in Richtung BRECHEN) — drei live, nicht-dokumentierte Core-Branches gefunden:**
- `[E] backend/app/agent/state/reducers.py:200 — "_SEALING_TYPE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = { … \"rwdr\": (\"shaft_diameter_mm\",\"speed_rpm\"), \"o_ring\": …, \"gasket\": …, \"packing\": … }"`,
  konsumiert live in der **State-Gate-Reducer** `[E] :300-302 — "if sealing_type in _SEALING_TYPE_REQUIRED_FIELDS: type_sensitive.extend(_missing(assertions, _SEALING_TYPE_REQUIRED_FIELDS[sealing_type]))"`.
  Eine per-Typ-Pflichtfeld-Map **im kanonischen Kern** — `CORE_PACK_BOUNDARY.md:13` verbietet das wörtlich („the core … never hardcodes per-type field lists"). Dritte, nicht-relocatete Pflichtfeld-Quelle (≠ `seal_required_fields.py`, ≠ `_MINIMAL_RWDR_FIELDS`).
- `[E] backend/app/agent/domain/challenge_engine.py:574/719/755/787 — 4× "engineering_path == \"rwdr\""` (+ `:575` `_contains_any(seal_text,("rwdr","radial","welle","rotier"))`), in einem **generisch benannten** Modul `[E] :1 — "V9 governed Dichtungsfall challenger."`. **Live im Turn-Chain:** `[E] backend/app/agent/graph/topology.py:8 — "… → v92_engineering → challenge → governance"`, `:324 graph.add_node(NODE_CHALLENGE, challenge_node)`, `[E] backend/app/agent/graph/nodes/challenge_node.py:13 — "from app.agent.domain.challenge_engine import build_challenge_state"`.
- `[E] backend/app/api/v1/projections/case_workspace.py:976/1343/1835 — "== \"rwdr\""` in der **Cockpit/Workspace-Projektion** (von `CORE_PACK_BOUNDARY.md:10-13` als core-that-must-not-branch benannt).

**Dating:** alle drei **PRE-EXISTING** (`git log -S`): `challenge_engine` → `967cbb24`,
`reducers` → `2dd3ac5b`, `_oring_calculations` → `89e0d419` — kein Regress *im Code*,
sondern ein **vom Vor-Audit übersehener** Bestand. `git diff aee6f536~1 38bea51d`
bestätigt: die P1-1/P1-3-Reihe berührte **ausschließlich** `risk_readiness.py`,
`calculation_projection.py`, `orchestrator.py` — nie `challenge_engine`, `reducers`,
`case_workspace`. Borderline (verteidigbare Pack-Tiefe, **nicht** als Treiber gewertet):
`technical_case_challenge.py`, `norm_modules/din_3760_iso_6194.py:33`, `ptfe_rwdr_enrichment.py:107`.
**Verdikt:** Seam existiert und wirkt für die auditierten Dateien → kein FEHLT; aber AC1
(„RWDR-Spezifik liegt nicht in der Plumbing") ist durch live Core-Branching **verletzt** → TEILWEISE/HIGH.
**Fix-Richtung (read-only, nicht angewandt):** die drei Flächen über `pack_for_engineering_path`/
Pack-Klassifikation routen (verhaltensneutral, wie `risk_readiness.py:533/561`); `CORE_PACK_BOUNDARY.md:53-62`
auf die tatsächliche Core-Fläche erweitern (die „resolved"-Behauptung ist unvollständig).

### C9 — Keine spekulative Abstraktion · **ERFÜLLT · LOW-Vorbehalt** (Konf. 9→8)
Als wörtliche Scaffold-/Universal-Layer-Frage **sauber**: `[E] sweep` — `class \w*Pack`
liefert exakt `RwdrPack` + `DomainPack`-Protocol; keine `o_ring/`/`flat_gasket/`/
`hydraulic`-Pack-Dirs; O-Ring/Hydraulik nur als markierte SHALLOW STUBS hinter der Seam
(`seal_required_fields.py:28/38`). **Kehrseite (per Auftrag falsifiziert):**
`[E] backend/app/agent/v92/orchestrator.py:469 — "def _oring_calculations(state, *, snapshot_hash)"`
(reale 5-Calc-O-Ring-Geometrie) **unbedingt** aufgerufen `[E] :625 — "results.extend(_oring_calculations(state, snapshot_hash=snapshot_hash))"`
in `build_calculation_state` (nur intern kurzgeschlossen, wenn `oring_cross_section_mm`
fehlt); dazu eine zweite O-Ring-Screening-Impl in `seal_design_intake_service.py`. Das ist
das §3.3-Anti-Pattern in Frühform — O-Ring-Engineering im generischen Kern, kein leerer
Scaffold. Kippt C9 nicht (Kriterium zielt auf spekulative Leer-Abstraktion), gehört aber
gemeinsam zu C1; die `seal_packs.py`-„SHALLOW STUB"-Doku unterschätzt den Calc-Pfad.

### C10 — Herstellerfeedback · **ERFÜLLT · LOW-Vorbehalt**
Struktur bestätigt + laundering-resistent: `[E] backend/app/services/rwdr_mvp_brief.py:3327
— "if source_type in _NEVER_BRIEF_SOURCE_TYPES: return …"` **vor** den Origin-Zweigen
(`:3333/3337/3345`), keyed auf das rohe `source_type` (`:515`); 5×5-Laundering blockt
(`extra="forbid"` `rfq.py:102-109`; hartkodiertes `source_type=manufacturer_response`/
`candidate` `:2463-2467`; Matching/Dispatch `=False` `:1940-1941`). **Neuer Befund (nicht
im Vor-Audit):** `[E] backend/app/services/rwdr_mvp_brief.py:2478 — "def manufacturer_response_echo_notes("`
hat **keinen Caller** in `backend/app`/`frontend/src` (grep = nur die Definition) →
dead-on-runtime. AC10 („als Wissensquelle **vorgesehen**") ist durch die implementierte +
getestete Funktion erfüllt; Verdikt unverändert, aber LOW-Wiring-Lücke offengelegt.

### S1/S2 — Trace/Tier · **ERFÜLLT** (Matrix-Zeile war stale TEILWEISE)
Das 2026-06-03-Audit ist **intern inkonsistent**: Matrix-Zeilen 25/26 lasen noch
TEILWEISE, die Detail-Sektion (Z.83-84, P1-2) las bereits ERFÜLLT. Live-Code-Re-Derive:
`[E] turn_timing.py:21-56` (ein Contextvar-Timer) + `[E] sse_contract.py:103-114` stempelt
`first_progress_ms`/`latency_ms` auf **alle** finalen `state_update` (10 Routen, keine
umgeht den Builder) → **S1 ERFÜLLT**. `[E] turn_tier.py:25/57` fail-closed Tier-0-Guard +
`[E] rag_orchestrator.py:852-854 enforce_retrieval_allowed()` am einzigen `hybrid_retrieve`-
Funnel → **S2 ERFÜLLT**; einzige unbewachte Retrieval-Fläche (BM25-Fallback hinter
`real_rag` broad-except) ist per Tier-0-Routing nicht erreichbar = latente Defense-in-Depth
(LOW). **Empfehlung:** Matrix S1/S2 im Vor-Audit auf ERFÜLLT korrigieren (Docs-Defekt).

### S3 — State-Gate Single-Writer · **TEILWEISE · LOW** (war ERFÜLLT)
Invariante real + doppelt dokumentiert: `[E] backend/app/agent/state/reducers.py:16-19 —
"These are the ONLY functions that may produce NormalizedState, AssertedState, or
GovernanceState instances."` + `models.py:8-15`; direkte Konstruktoren grep-sauber (nur die
4 Reducer-Return-Sites). **Falsifikation:** (1) **kein** AST-/Architektur-Test erzwingt die
Regel (grep „only.*reducer"/„single.writer"/„may produce" in `tests/architecture` + Agent-Tests
= leer) — nur Docstring/Konvention. (2) Zwei Produktionsstellen erzeugen via `model_copy(update=…)`
neue governed-Layer-Instanzen mit **berechnetem** Inhalt außerhalb der Reducer-Kette:
`[E] backend/app/agent/api/utils.py:180 — "governed_state.governance.model_copy(update={\"requirement_class\": …, \"rfq_admissible\": … == \"ready\"})"`
und `[E] backend/app/agent/graph/output_contract_assembly.py:1822 — "state.decision.model_copy(update={\"blocking_reasons\": list(admissibility.blocking_reasons)})"`
(DecisionState ist GovernanceState-Subklasse). `[A]` Bei enger Lesart von „produce" (nur
`Type(...)`-Konstruktoren) rundet S3 auf ERFÜLLT; bei wörtlicher Lesart („produce …
instances", was `model_copy` einschließt) sind die beiden Stellen Soft-Bypässe → TEILWEISE.
LOW, weil beide deterministische Inhalts-Syncs sind (kein LLM→Governance-Shortcut; die
`Observed`-Only-LLM-Grenze ist intakt). **Fix-Richtung:** AST-Test + die beiden Writes durch
einen Reducer routen (oder `model_copy`-Assembly im Docstring formal aus der Invariante schneiden).

### Bestätigt ohne Verdikt-Bewegung (Kurz)
**C2** ERFÜLLT-per-Amendment — Protocol+Seam+Registry-Deferral sauber; die ~18 sonstigen
`== "rwdr"`-Treffer sind Pack-Tiefe **bis auf** die unter C1 genannten. **C3/C4** ERFÜLLT —
`normalize_seal_type()`→`pack_for` gebunden; Core-6-Tupel nach `seal_required_fields.py:19`
relocatet (Vor-Audit-Zeilenref `orchestrator.py:55` ist damit **stale**), 6∩31 = ∅ (C4-Konf.
8 statt 9 wegen `reducers.py:200`-Querbezug). **C6** ERFÜLLT — Residual: `case_service.apply_mutation`
vertraut `case_row.tenant_id` ohne In-Query-Caller-Tenant-Filter, heute nur tenant-verifiziert
erreichbar (Defense-in-Depth-Notiz, kein Live-Leak). **C7** ERFÜLLT-per-Amendment (s. §4 A-C7).
**C8/S4** ERFÜLLT. **S5** TEILWEISE unverändert — 30 §5-Modes über 3 Vokabulare abgebildet;
einziger materieller Rest = Upload/Document/Visual-Familie (`[NV]` read-only); GEWOLLTE
Divergenz (TurnRoute = schlanke Guard-/Streaming-/Mutation-Achse).

## 4. Amendment-Verifikation (existieren? datiert? begründet?)

| Amendment | Verdikt | Datiert | Begründet | Beleg / Vorbehalt |
|---|---|---|---|---|
| **A-C7** Envelope-Liefervertrag (Stub-Entfernung, §11/§28.2) | **VERIFIZIERT-mit-Vorbehalt** | 2026-06-04 | ja | `contracts.py:303-305` (Stubs entfernt, 0 Refs) + **V1.6**-Blueprint §11 `:1749-1759` „**Amendment 2026-06-04 (P0-3, gap-audit C7 — Owner decision Option 2)**" + §28.2-Spiegel `:3547-3548` + `GOVERNANCE_LOG.md:80-81`. **Vorbehalt:** V1.7-*Universal* §6.4 (`origin/feat/v1.7-blueprint`, single-commit) listet `CaseUnderstandingPatch+RFQBriefPatch` weiterhin — **unrekonziliert**, aber off-branch + nicht-bindend (AGENTS.md: V1.6/RWDR-MVP bindend); das §11-Amendment adressiert die „§6.4"-Referenz explizit. |
| **A-C2/C4** Lesarten (Protocol-now/Registry-later; orchestrator≠brief) | **VERIFIZIERT-mit-Vorbehalt** | 2026-06-04 | ja | C2 voll in `CORE_PACK_BOUNDARY.md:5/30/46` + `GOVERNANCE_LOG.md:82` + Code (`domain_pack.py:5`, `seal_packs.py:64`). **Vorbehalt:** die C4-Substanz steht im **Code-Docstring** `seal_required_fields.py:9-13` (commit `6f1abc03`); die quantifizierte „6 ≠ 31"-Formulierung steht **nur** in den Vor-Audit-Notizen (`2026-06-03_v17_gap_audit.md:54`), nicht in `CORE_PACK_BOUNDARY.md`/`GOVERNANCE_LOG.md`. |
| **A-499** `:499` dokumentierter Core-Check | **VERIFIZIERT** | 2026-06-04 | ja | In-Code `risk_readiness.py:499-505 — "# P1-3: deliberately a CORE check … owner decision 2026-06-04"` (deckt sich wörtlich mit) `CORE_PACK_BOUNDARY.md:53-62` + `GOVERNANCE_LOG.md:57/63-65`. **Minor-Drift:** Doku zitiert Geschwister `:527/:555`, live `:533/:561` — berührt den `:499`-Record nicht. |
| **A-C5** Routing-Deferral (`pack_affinity` retrieval-inert) | **VERIFIZIERT** | 2026-06-04T14:43Z | ja | `GOVERNANCE_LOG.md:9/26-30` + `rag_schema.py:53-57` + Test `test_rag_pack_affinity_marker.py:87-94`. „Marker now" code-belegt + inert; „routing later" ist bewusst Intent (kein Consumer). |

**Fazit Amendments:** alle vier **existieren, sind datiert (2026-06-04), begründet**;
zwei tragen einen dokumentierten, design-konsistenten Vorbehalt (kein Defekt).

## 5. Live-vs-Merged

| Artefakt | Live-Digest (Daemon) | Tag-Commit | vs. demo-HEAD `38f579c7` |
|---|---|---|---|
| Backend | `…3627b2f7-20260604-144259@sha256:05953eda…` running/healthy | `3627b2f7` | **HEAD − Merge #62 (Docs-Only)** — `git log 3627b2f7..HEAD` = `2baaa78d`+`38f579c7`, beide Docs |
| Frontend | `…ac7402ea-20260604-101815@sha256:f27f9b5e…` healthy | `ac7402ea` (#48) | **frontend-Code aktuell** — `git diff --stat ac7402ea..HEAD -- frontend/` leer |

**Befund:** **deployed == merged für *allen Code*.** Der einzige Live-vs-Merged-Delta ist
**Dokumentation** (der #62-Closeout, der C5/C10 ERFÜLLT markiert + den Deploy-Eintrag setzt).
Der GOV-LOG-Eintrag `2026-06-04T14:43Z` bestätigt exakt den Live-Backend-Digest `…05953eda…`
(„live pilot smoke 14/14 PASS"). Die Re-Run-Verdikte tragen damit auf den deployten Stand.
`[NV]` Laufzeit-Verhalten/Latenzen + Live-Qdrant-Backfill-Stand (Owner-Vorgabe: statisch,
keine In-Container-Proben).

## 6. Offene Fragen, Annahmen [A], Nicht-Prüfbares [NV]
- `[NV]` **Echte <1s-Mobile-Latenz (C8)** — nur der LLM/RAG/Graph-freie Fast-Path ist read-only prüfbar.
- `[NV]` **Laufzeit-Erreichbarkeit** der C1-Branches als Output-Änderung (vs. inert) — read-only;
  die Branches emittieren aber distinkte `ChallengeFinding`-Objekte, sind also funktional, nicht tot.
- `[A]` **S3-Strenge** hängt an der Lesart von „produce" (`model_copy` einbezogen ja/nein) —
  wörtliche Lesart → TEILWEISE, enge Konstruktor-Lesart → ERFÜLLT; Befund als wörtlich gewertet.
- `[A]` **C6-Residual** (`apply_mutation` trust-by-case-id) ist auf der heutigen Call-Graph
  nicht exploitierbar; ein künftiger ungescopeter Caller wäre ein Cross-Tenant-Write — Defense-in-Depth.
- `[NV]` Test-/Suite-/Deploy-Beweise in GOV-LOG/Amendments (EXIT=0, doctrine-reviewer APPROVE,
  Backfill-Accounting) sind read-only nicht re-runbar.

## 7. Coverage-Erklärung (was wurde NICHT auditiert)
- **Nicht ausgeführt:** App/Tests/Build, keine In-Container-Proben (Owner-Vorgabe statisch);
  Funktions-/Render-/Latenz-Korrektheit über die Verdrahtung hinaus → `[NV]`.
- **Tenant-Tiefe:** die C6-Gateways + LTM voll re-walked; die ~35 „scoped" Routen stichprobenartig
  über das geteilte `require_tenant_id` + Persistenz-Filter bestätigt, nicht jede einzeln.
- **Doku als Intent, nicht als Presence** gewertet; RWDR-Strings in Tests/Fixtures/UI-Labels nie
  als C1-Verletzung (nur live Core-Branching in generisch benannten Modulen).
- **Nicht im Fokus:** Prompt-Injection-Tiefe, Upload-Path-Traversal, MCP-Tool-Tenant-Scoping,
  Rate-Limiting/DoS, Style/Deps.

---

**Gesamtverdikt: V1.7 erreicht — *nein* (knapp verfehlt).** Neun der zehn Acceptance
Criteria und vier der fünf S-Kriterien sind erfüllt (drei davon per dokumentiertem,
verifiziertem Amendment), aber **AC1 (Core/Pack-Trennung) ist nachweislich verletzt** —
live, nicht-dokumentierte RWDR-Verzweigung im kanonischen Kern (State-Gate-Reducer,
Challenge-Engine, Cockpit-Projektion), die die P1-Arbeit nie berührte und
`CORE_PACK_BOUNDARY.md` als „resolved" überzeichnet; nach der „FEHLT-bis-Beweis"-Methodik
ist ein verifizierter Verstoß gegen den Wortlaut einer AC mit „ja/ja-mit-Amendments"
nicht vereinbar. Es ist ein **knappes „nein"**: der Befund ist ein Vollständigkeits-/
Dokumentations-Gap (die Seam existiert und wirkt für die auditierten Dateien; sie ist nur
nicht über den ganzen Kern durchgesetzt), kein Produktfunktions-Ausfall — schließbar durch
verhaltensneutrales Routen der drei Flächen über die bestehende Pack-Seam plus Korrektur der
Boundary-Doku, womit C1 auf ERFÜLLT und das Gesamtverdikt auf „ja-mit-Amendments" käme.

---

*Erstellt strikt read-only (Read/Grep/Glob/`git show`/`docker inspect`). Keine Patches in
dieser Session. Verfahren: Live-Digest-Pin (Daemon) → 20 read-only Verifikations-Agenten
(Kriterien + Amendments + adversariale Core-Sweep) → Hand-Nachprüfung jeder Verdikt-Bewegung
am Live-Code → Synthese. Evidenz-Grammatik `[E]/[A]/[NV]` durchgesetzt; Default FEHLT-bis-Beweis,
in beide Richtungen falsifiziert.*
