# SealAI — Claude Code Arbeitsanweisung
**Letzte Aktualisierung:** 2026-04-07
**Status:** Phase F — Foundation Cut AKTIV

---

## Verbindliche Dokumente

| Priorität | Dokument | Pfad | Funktion |
|---|---|---|---|
| 1 | **Finales Konzept** | `konzept/SEALAI_KONZEPT_FINAL` | Produkt, UX, Geschäftsmodell |
| 1 | **Stack-Architektur** | `konzept/SEALAI_STACK_ARCHITEKTUR` | Vollständiger technischer Stack |
| 2 | **Umbauplan V2** | `konzept/SEALAI_UMBAUPLAN_V2` | Operativer Migrationsplan (aktuell) |
| 2 | **Kommunikations-Zielbild** | `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md` | Normatives Kommunikationsverhalten |
| 3 | **Architekturnachtrag** | `konzept/audit/ARCHITEKTURNACHTRAG_2026-04-04.md` | Gate-Entscheidung (3-stufig) |
| 3 | **IST-Audit** | `konzept/audit/AUDIT_IST_2026-04-06.md` | Aktueller IST-Zustand der Codebase |

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
GOVERNED      vollst./teilw. Parameter für RWDR/RC → 8-Node Subgraph
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

### Governed Subgraph: 8 Kern-Nodes
```
intake_observe → normalize_node → assert_node → evidence_node →
compute_node → governance_node → output_contract → cycle_control/renderer
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
grafana               latest        Dashboards
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

## Aktuelle Phase: F — Foundation Cut

Audit abgeschlossen (2026-04-07). Umbauplan V2 liegt vor.
Phase F beginnt jetzt mit W1.1.

### Phase F Done-Kriterium

```
✓ "Gleitring für 80°C Salzwasser, 50mm, 6000 U/min"
  → Gate: GOVERNED → 8 Nodes → technical_preselection
  → Token-Stream am Frontend sichtbar
  → Cockpit: Parameter + PV-Wert + Vorauswahl
  → PDF via Gotenberg erzeugbar
  → Audit-Log in PostgreSQL

✓ "Welche Materialien für Salzwasser?"
  → Gate: EXPLORATION → 1 RAG + 1 LLM → conversational_answer

✓ "Hallo, wie geht es dir?"
  → Gate: CONVERSATION → direkt, < 1s

✓ Kein Request in langgraph_v2/
✓ Alle 1.573 Tests grün
✓ LangSmith zeigt Traces
✓ Gotenberg + Tika Container laufen
```

### Reihenfolge innerhalb Phase F

```
Woche 1 — Daten + Fundament
  W1.1  STS-Seed-Files anlegen         → agent/data/sts/*.json
  W1.2  Qdrant Collection fixen        → sealai_technical_docs, 384-dim
  W1.3  PromptRegistry implementieren  → agent/prompts/__init__.py
  W1.4  Gate-Routen umbenennen         → CONVERSATION/EXPLORATION/GOVERNED
  W1.5  25 fehlgeschlagene Tests fixen

Woche 2 — State + RAG
  W2.1  State auf 6 Schichten mappen   → DerivedState, EvidenceState, etc.
  W2.2  DEPENDENCY_MAP implementieren  → reducers.py
  W2.3  Idempotency + basis_hash       → models.py, persistence.py
  W2.4  EvidenceQuery + ExplorationQuery → evidence/
  W2.5  evidence_node verbinden
  W2.6  Pilot-Datenblätter in Paperless laden

Woche 3 — Naming + Legacy
  W3.1  Outward-Class-Rename (atomar)  → technical_preselection, inquiry_ready
  W3.2  Legacy-Import-Entkopplung      → 15+ Dateien
  W3.3  V2-Endpoint Feature-Flag
  W3.4  interaction_policy + FastBrainRouter entfernen
  W3.5  Keycloak-Rollen anlegen

Woche 4 — Pipeline + Integration
  W4.1  Gotenberg + Tika Container starten
  W4.2  Gotenberg-Client implementieren
  W4.3  Inquiry HTML-Template (Jinja2)
  W4.4  interrupt() für Clarification
  W4.5  StreamWriter Progress-Events
  W4.6  PostgreSQL Cases + State-Snapshots
```

Details zu jedem Schritt: `konzept/SEALAI_UMBAUPLAN_V2`

---

## Arbeitsregeln

### Vor jeder Aufgabe
- Lies `konzept/SEALAI_UMBAUPLAN_V2` vollständig (mind. relevanten Abschnitt).
- Prüfe: Welche Woche? Welcher Schritt?
- Prüfe: Verstößt die Änderung gegen eine der 16 Invarianten?
- Prüfe: Welche bestehenden Dateien werden angefasst?
- Prüfe: Bleiben alle 1.573 Tests grün?

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
- Wenn Phase F: End-to-End Smoketest möglich?

### Was du NICHT tun sollst
- Phase G/H starten bevor Phase F Done-Kriterium bestanden ist.
- `selection.py` erweitern (nur zerlegen).
- `langgraph_v2/` oder `_legacy_v2/` weiterentwickeln.
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

### Legacy (read-only, wird schrittweise entfernt)
```
backend/app/langgraph_v2/   ← Feature-Flag, wird deaktiviert (W3.3)
backend/app/_legacy_v2/     ← Adapter, wird nach Entkopplung entfernt (W3.2)
```

### Ziel-Ordnerstruktur nach Phase F
```
backend/app/agent/
├── api/
│   ├── handlers/           chat_handler, upload_handler, inquiry_handler
│   └── sse/                stream.py
├── prompts/                PromptRegistry + alle Jinja2-Templates
│   ├── renderer/           base.j2, conversational.j2, clarification.j2,
│   │                       state_update.j2, preselection.j2,
│   │                       candidate_list.j2, inquiry_ready.j2
│   ├── gate/               gate_classify.j2
│   ├── intake/             observe.j2
│   ├── exploration/        explore.j2, compare.j2, detail.j2
│   └── pdf/                inquiry.html.j2, styles.css
├── runtime/
│   ├── gate.py             3-Way Gate + Command
│   ├── session_manager.py  thread_id v3, Stickiness
│   ├── conversation_runtime.py
│   ├── exploration_runtime.py
│   └── response_renderer.py
├── graph/
│   ├── main_graph.py
│   ├── governed_subgraph.py
│   ├── nodes/              8 Kern-Nodes + StreamWriter
│   └── topology.py
├── state/
│   ├── models.py           6 Schichten
│   ├── reducers.py         + DEPENDENCY_MAP
│   ├── persistence.py      Redis Checkpoint v3
│   └── projections.py      Cockpit-Tiles
├── evidence/
│   ├── evidence_query.py
│   ├── exploration_query.py
│   └── retrieval.py        Qdrant Hybrid Search
├── domain/
│   ├── normalization.py
│   ├── rwdr_calc.py
│   ├── requirement_class.py
│   ├── threshold.py
│   └── fit_score.py
├── sts/
│   ├── loader.py
│   └── codes.py
├── manufacturers/
│   ├── capability_db.py
│   ├── matching_engine.py
│   └── payload_builder.py
├── documents/
│   ├── tika_client.py
│   └── pdf_generator.py    → Gotenberg
├── rag/
│   ├── ingest_service.py   Paperless-Webhook → Qdrant
│   └── setup_collections.py
└── data/
    ├── sts/                materials.json, sealing_types.json,
    │                       requirement_classes.json, media.json,
    │                       open_points.json
    ├── manufacturers/      pilot_manufacturers.json
    └── ontology/           failure_modes.json, norm_map.json
```

---

## Phasenübersicht

| Phase | Name | Status | Startet nach |
|---|---|---|---|
| AUDIT | IST-Analyse | ERLEDIGT 2026-04-07 | — |
| **F** | Foundation Cut | **AKTIV** | Audit ✓ |
| G | Domain Buildout | WARTET | Phase F Done |
| H | Commercial Buildout | WARTET | Phase G Teilabschluss |

---

## Erster Prompt für Phase F

```
Lies konzept/SEALAI_UMBAUPLAN_V2 vollständig.

Starte W1.1: Erstelle die STS-Seed-Files.

Neue Dateien:
  backend/app/agent/data/sts/materials.json
  backend/app/agent/data/sts/sealing_types.json
  backend/app/agent/data/sts/requirement_classes.json
  backend/app/agent/data/sts/media.json
  backend/app/agent/data/sts/open_points.json

Dann:
  backend/app/agent/sts/__init__.py
  backend/app/agent/sts/loader.py
  backend/app/agent/sts/codes.py

Dann:
  backend/app/agent/tests/test_sts_loader.py

Anforderungen:
- Mindestens 15 Materialcodes (STS-MAT-*) inkl. SiC, FKM, PTFE, EPDM, NBR, FKM-HT, WC, Grafit
- Mindestens 10 Dichtungstypen (STS-TYPE-*) inkl. GS-S, GS-CART, GS-D, RWDR-A, RWDR-B, OR-A, FLAT-A
- Mindestens 6 Requirement Classes (STS-RS-*)
- Mindestens 15 Mediumcodes (STS-MED-*)
- Mindestens 10 offene Prüfpunkte (STS-OPEN-*)
- loader.py: JSON laden + validieren (keine Duplikate, Pflichtfelder)
- codes.py: get_material(code), get_sealing_type(code), is_valid_code(code)
- Alle bestehenden 1.548 Tests müssen weiter grün bleiben.
```
