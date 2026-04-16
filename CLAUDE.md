# SealAI — Claude Code Arbeitsanweisung
**Letzte Aktualisierung:** 2026-04-11
**Status:** Phase H — Commercial Buildout AKTIV

---

## Verbindliche Dokumente

| Priorität | Dokument | Pfad | Funktion |
|---|---|---|---|
| 1 | **Finales Konzept** | `konzept/SEALAI_KONZEPT_FINAL` | Produkt, UX, Geschäftsmodell |
| 1 | **Stack-Architektur** | `konzept/SEALAI_STACK_ARCHITEKTUR` | Vollständiger technischer Stack |
| 2 | **Umbauplan V2** | `konzept/SEALAI_UMBAUPLAN_V2` | Operativer Migrationsplan (aktuell) |
| 2 | **Kommunikations-Zielbild** | `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md` | Normatives Kommunikationsverhalten |
| 3 | **Architekturnachtrag** | `konzept/audit/ARCHITEKTURNACHTRAG_2026-04-04.md` | Gate-Entscheidung (3-stufig) |
| 3 | **IST-Audit** | `konzept/audit/AUDIT_IST_2026-04-09.md` | Aktueller IST-Zustand der Codebase |

> Bei Konflikten: Finales Konzept + Stack-Architektur > Umbauplan V2 > Kommunikations-Zielbild > Architekturnachtrag > IST-Audit

**Lies vor jeder Aufgabe mindestens Umbauplan V2 vollständig.**

---

## Was SeaLAI ist (bindend)

SeaLAI ist der schnellste Weg von einem unklaren Dichtungsproblem
zu einer belastbaren, herstellerfähigen Anfrage.

**User (kostenlos):** Strukturierte Bedarfsanalyse ohne Fachwissen.
Neutrale technische Vorauswahl. PDF + JSON-Payload für Hersteller.

**Hersteller (zahlt für Listing):** Nur qualifizierte Leads die passen.
Alle technischen Daten strukturiert — kein Pre-Sales-Aufwand.

**Haftung:** Liegt beim Hersteller. SeaLAI gibt Vorauswahl auf Basis
von Parametern und `fit_score` — nie "Wahrscheinlichkeit".
Finale Freigabe: Hersteller.

---

## Architektur-Kernentscheidungen (alle bindend)

### Gate: 3-stufig
```
CONVERSATION  kein Domänenparameter → 1 LLM-Call, < 1s
EXPLORATION   Domänenkontext, keine vollst. Parameter → 1 RAG + 1 LLM, < 3s
GOVERNED      vollst./teilw. Parameter für RWDR/RC → Graph
```
Bias zu GOVERNED bei Unsicherheit. Zone-Stickiness: nur aufsteigend.

### State: 6 Schichten (TypedDict + Pydantic V2)
```
ObservedState      LLM schreibt NUR hier
NormalizedState    deterministisch — Terminologie, Einheiten
DerivedState       deterministisch — RWDR, PV-Wert, RC, Suitability
EvidenceState      RAG — source + doc_version + trust_level
DecisionState      deterministisch — outward_class, preselection, assumptions
ActionReadiness    PDF-Status, idempotency_key, inquiry_sent
```
Stale-State via DEPENDENCY_MAP. Idempotency Keys für alle Side Effects.
Revisionsbindung aller Artefakte an `decision_basis_hash`.

### Governed Graph: 15 Nodes (8 Kern + 7 kommerzielle Erweiterungen)
```
Kern (Phase F):
intake_observe → normalize_node → assert_node → evidence_node →
compute_node → governance_node → output_contract → cycle_control

Erweiterungen (deterministisch, Phase H):
matching → rfq_handover → dispatch → norm →
export_profile → manufacturer_mapping → dispatch_contract
```
MAX_CYCLES = 3. Nach Limit: `incomplete_analysis` oder
`assumptions_require_confirmation` — kein stilles Weiterlaufen.

### Prompts: Jinja2 (PromptRegistry Singleton)
Kein f-string in Python. Alle Prompts unter `agent/prompts/`.
LLM bekommt State-Snapshot via `build_renderer_context()` — nie rohen Chat.

### STS: internes Canonical Model
STS-MAT-* / STS-TYPE-* / STS-RS-* / STS-MED-* / STS-OPEN-*
Intern für Matching + Payload. Nach außen: Fachsprache + Normbezüge.
Niemals als "Standard" vermarktet oder so benannt.

### PDF: via Gotenberg
Jinja2 HTML-Template → Gotenberg → PDF.
Idempotency Key verhindert Doppel-Erzeugung.
Jedes PDF an exakten `state_hash` gebunden.

### RAG: Paperless-ngx → Qdrant
Admin taggt Datenblätter in Paperless (`doc_type:datasheet`, `sts_mat:STS-MAT-SIC-A1` etc.)
→ Webhook → Ingest-Service → Chunking + Embedding (384-dim MiniLM) → Qdrant.
Collection: `sealai_technical_docs`, Hybrid BM25 + Semantic.

### Outward Response Classes (6)
```
conversational_answer      CONVERSATION + EXPLORATION
structured_clarification   alle Pfade
governed_state_update      GOVERNED
technical_preselection     GOVERNED  ← nie "governed_recommendation"
candidate_shortlist        GOVERNED
inquiry_ready              GOVERNED  ← nie "rfq_ready"
```
`fit_score` — nie "Wahrscheinlichkeit".
Kein "ist geeignet für". Kein "garantiert". Kein "wird funktionieren".

---

## Stack

```
Service               Version       Rolle
──────────────────────────────────────────────────────────
backend (FastAPI)     aktuell       KI-Kern + LangGraph 1.1.6
nginx                 1.29.4        Reverse Proxy + TLS + SSE
keycloak              2026.04.03    Auth (OIDC/JWT)
redis-stack-server    7.4.0-v8      Checkpoint v3 + Session + Cache
postgres:15           15            Cases + Audit + State Snapshots
qdrant                v1.16.0       Vector DB (RAG, Hybrid)
paperless-ngx         2.20.10       RAG-Admin (Upload + Tag + Webhook)
tika                  2.9.2.1       OCR + Extraktion
gotenberg             8.15.0        PDF-Erzeugung
prometheus            latest        Metrics
grafana               latest        Dashboards (3 vorhanden)
──────────────────────────────────────────────────────────
ERPNext               —             NICHT in Scope
```

LLM: `gpt-4o-mini` (Gate/Classify) · `gpt-4o` (Observe/Render)

---

## Invarianten (nicht verhandelbar)

1. `backend/app/agent/` ist die einzige produktive Zielarchitektur.
2. `backend/app/langgraph_v2/` ist read-only Legacy. Nicht anfassen.
3. Gate ist 3-stufig: `CONVERSATION | EXPLORATION | GOVERNED`.
4. LLM schreibt nur in `ObservedState`.
5. RAG nur über `EvidenceQuery` / `ExplorationQuery` — nie roher Text.
6. Matching nie vor technischer Einengung (mind. Governance-Klasse B).
7. Inquiry nie ohne deterministische Admissibility.
8. Keine internen State-Artefakte im API-Response.
9. User-Override schreibt immer in `ObservedState`.
10. Kein Multi-Agenten-Theater, keine freie Node-Generierung.
11. `FastBrainRouter` nicht in EXPLORATION.
12. `selection.py` nur zerlegen — nicht erweitern.
13. `technical_preselection` statt `governed_recommendation`.
14. `fit_score` statt "Wahrscheinlichkeit" in allen Outputs.
15. `inquiry_ready` statt `rfq_ready`.
16. Jinja2 für alle Prompts — kein f-string in Python.

---

## Aktuelle Phase: H — Commercial Buildout

Phase G abgeschlossen 2026-04-11. 1851 Tests grün.

### Was in Phase F + G erledigt wurde

```
Phase F (Foundation Cut) — abgeschlossen 2026-04-10:
  ✓ STS-Seed-Files (30 MAT, 20 TYPE, 40 MED, 8 RS, 12 OPEN)
  ✓ Qdrant sealai_technical_docs (384-dim, BM25+Semantic)
  ✓ PromptRegistry Singleton + 12 Jinja2-Templates
  ✓ Gate 3-stufig: CONVERSATION / EXPLORATION / GOVERNED
  ✓ State 6 Schichten + DEPENDENCY_MAP + Idempotency Keys
  ✓ EvidenceQuery + ExplorationQuery + Hybrid Retrieval
  ✓ Outward-Class-Rename: technical_preselection, inquiry_ready
  ✓ Legacy-Imports: 0 verbleibend in Produktivcode
  ✓ V2-Endpoint: Feature-Flag False
  ✓ Gotenberg + Tika laufen, PDF-Pipeline komplett
  ✓ interrupt() für Clarification
  ✓ StreamWriter Progress-Events (3 Nodes)
  ✓ PostgreSQL: Alembic-Migration ausgeführt
  ✓ 1792 Tests grün

Phase G (Domain Buildout) — abgeschlossen 2026-04-11:
  ✓ agent/agent/ aufgelöst: 18 Dateien → Zielstruktur (Shims)
  ✓ case_state.py → state/case_state.py
  ✓ projections_extended.py → state/ (bereits dort)
  ✓ fastembed als einziger Embedding-Weg
  ✓ 3 Pilot-Chunks in Qdrant (SiC, FKM, PTFE)
  ✓ pilot_manufacturers.json (5 Hersteller)
  ✓ fit_score.py (4-Komponenten, deterministisch)
  ✓ payload_builder.py (inquiry_payload)
  ✓ STS erweitert: 30 MAT, 20 TYPE, 40 MED
  ✓ failure_modes.json (16 Schadensbilder)
  ✓ norm_map.json (8 Normen: DIN, API, ISO, ATEX, FDA)
  ✓ normalize_material() → STS-MAT-* Codes
  ✓ Grafana Dashboards 2+3 (RAG Intelligence, Business)
  ✓ Prometheus: 5 neue Instrumente
  ✓ 1851 Tests grün
```

### Phase H Done-Kriterium

```
✓ Inquiry Pipeline vollständig:
  - Admissibility-Check deterministisch
  - User-Confirmation via interrupt()
  - PDF mit state_hash erzeugt
  - Inquiry-Payload an Hersteller gesendet (Pilot)
  - Cases-Tabelle + Audit-Log geschrieben

✓ Frontend vollständig:
  - Chat + Cockpit in Produktion
  - SSE-Stream: Token + Progress-Events
  - Keycloak-Login: user_basic, manufacturer, admin

✓ Pilot-Betrieb:
  - Mindestens 1 echter Hersteller ongeboardet
  - Mindestens 5 echte Datenblätter in Paperless
  - Mindestens 1 Inquiry vollständig durchgelaufen

✓ Alle Tests grün (Ziel: 1900+)
```

### Empfohlene Reihenfolge Phase H

```
H1 — Inquiry Pipeline
  H1.1  Admissibility-Check (check_inquiry_admissibility)
  H1.2  User-Confirmation via interrupt()
  H1.3  Cases-Tabelle aktivieren (Alembic bereits ausgeführt)
  H1.4  Inquiry-Versand (JSON-Payload an Hersteller)
  H1.5  Audit-Log schreiben (inquiry_audit Tabelle)

H2 — Frontend Integration
  H2.1  Chat-Handler SSE vollständig verdrahten
  H2.2  Cockpit-Tiles aus projections.py live
  H2.3  Progress-Events vom StreamWriter empfangen
  H2.4  Keycloak-Login im Frontend

H3 — Pilot-Betrieb
  H3.1  Erster echter Hersteller onboarden (manuell)
  H3.2  Echte Datenblätter in Paperless laden + taggen
  H3.3  Paperless-Webhook → Qdrant aktivieren
  H3.4  Erster vollständiger Durchlauf mit echtem User
```

---

## Arbeitsregeln

### Vor jeder Aufgabe
- Lies `konzept/SEALAI_UMBAUPLAN_V2` vollständig (mind. relevanten Abschnitt).
- Prüfe: Welche Phase? Welcher Schritt?
- Prüfe: Verstößt die Änderung gegen eine der 16 Invarianten?
- Prüfe: Welche bestehenden Dateien werden angefasst?
- Prüfe: Bleiben alle 1.851 Tests grün?

### Während der Arbeit
- Kleine, testbare Schritte. Tests grün nach jedem Commit.
- Tests parallel zum Code schreiben.
- Keine Imports aus `langgraph_v2/` oder `_legacy_v2/`.
- Keine direkten State-Writes außer über Reducer.
- `fit_score` statt Wahrscheinlichkeit.
- `technical_preselection` statt `governed_recommendation`.
- `inquiry_ready` statt `rfq_ready`.
- Jinja2 für alle Prompts — kein f-string.

### Nach jeder Aufgabe
- Alle Tests grün?
- Neue Tests grün?
- Commit mit aussagekräftiger Message.

### Was du NICHT tun sollst
- `selection.py` erweitern (nur zerlegen).
- `langgraph_v2/` oder `_legacy_v2/` anfassen.
- STS als externen Standard benennen.
- conservative assumptions nach MAX_CYCLES.
- f-strings für Prompts verwenden.
- `governed_recommendation`, `rfq_ready` oder "Wahrscheinlichkeit" einführen.
- Architekturentscheidungen treffen die nicht im Umbauplan stehen
  — stattdessen Frage stellen.

---

## Codebase-Orientierung

### Produktiver Zielstack
```
backend/app/agent/          ← Single Source of Truth
```

### Legacy (de facto deaktiviert)
```
backend/app/langgraph_v2/   ← Feature-Flag False, nicht anfassen
backend/app/_legacy_v2/     ← Nur noch conftest.py
backend/app/agent/agent/    ← Nur noch Re-Export-Shims (18 Dateien)
```

### Aktuelle Ordnerstruktur (IST nach Phase G)
```
backend/app/agent/
├── api/                    router.py (2.771 LOC), sse_runtime.py
├── prompts/                PromptRegistry + 12 Templates + pdf/
├── runtime/                gate.py, session_manager.py, conversation_runtime.py,
│                           exploration_runtime.py, response_renderer.py,
│                           reply_builder.py, clarification.py, boundaries.py,
│                           output_guard.py, policy.py, selection.py,
│                           interaction_policy.py (deprecated)
├── graph/                  topology.py, legacy_graph.py, nodes/ (15 Nodes),
│                           tools.py
├── state/                  models.py (6 Schichten), reducers.py (DEPENDENCY_MAP),
│                           persistence.py, projections.py,
│                           projections_extended.py, case_state.py,
│                           agent_state.py, sync.py
├── evidence/               evidence_query.py, exploration_query.py, retrieval.py
├── domain/                 normalization.py, rwdr_calc.py, requirement_class.py,
│                           threshold.py, fit_score.py, logic.py, physics.py,
│                           readiness.py, review.py, material.py,
│                           manufacturer_rfq.py, medium_registry.py
├── sts/                    loader.py, codes.py
├── manufacturers/          commercial.py, payload_builder.py
├── documents/              tika_client.py, pdf_generator.py
├── rag/                    setup_collections.py, seed_pilot_chunks.py,
│                           paperless_tags.py
├── agent/                  18 Re-Export-Shims (kein produktiver Code)
└── data/
    ├── sts/                materials.json (30), sealing_types.json (20),
    │                       requirement_classes.json (8), media.json (40),
    │                       open_points.json (12)
    ├── manufacturers/      pilot_manufacturers.json (5 Hersteller)
    └── ontology/           failure_modes.json (16), norm_map.json (8)
```

---

## Phasenübersicht

| Phase | Name | Status | Abgeschlossen |
|---|---|---|---|
| AUDIT | IST-Analyse | ERLEDIGT | 2026-04-07 |
| F | Foundation Cut | ERLEDIGT | 2026-04-10 · 1792 Tests |
| G | Domain Buildout | ERLEDIGT | 2026-04-11 · 1851 Tests |
| **H** | Commercial Buildout | **AKTIV** | — |

---

## Erster Prompt für Phase H

```
Phase G abgeschlossen (1851 Tests grün).
Lies CLAUDE.md und konzept/SEALAI_UMBAUPLAN_V2 vollständig.

Starte H1.1: Admissibility-Check implementieren.

Neue Datei: backend/app/agent/domain/admissibility.py

Anforderungen:
- check_inquiry_admissibility(state: SealAIState) → AdmissibilityResult
- Deterministisch — kein LLM
- Pflichtfelder prüfen: medium, temperature_max_c, pressure_max_bar,
  shaft_diameter_mm, sealing_type
- parameter_status "assumed" für kritische Felder → blocking
- critical_review.py blocking_findings → blocking
- AdmissibilityResult enthält: admissible, blocking_reasons, basis_hash
- tests/test_inquiry_admissibility.py:
    vollständiger State → admissible=True
    fehlender Pflichtparameter → admissible=False
    "assumed" Druck → admissible=False
    blocking_reasons nie leer wenn admissible=False

Alle 1.851 Tests müssen grün bleiben.
```
