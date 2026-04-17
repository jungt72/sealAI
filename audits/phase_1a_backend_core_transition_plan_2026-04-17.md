# Phase 1a — Backend-Core Transition Planning Audit

**Datum:** 2026-04-17
**Scope:** `backend/app/` im Monorepo `/home/thorsten/sealai`
**Auditor-Rolle:** Claude Code (Opus 4.7), read-only, Plan Mode
**Ziel-Report (nach Genehmigung):** `audits/phase_1a_backend_core_transition_plan_2026-04-17.md`

Dieses Dokument ist der Inhaltsträger des Audit-Reports. Bei Genehmigung wird der Inhalt 1:1 in den Ziel-Report-Pfad übertragen.

---

## 0. Metadata & Methodik

**Authority-Dokumente (in Präzedenzreihenfolge, vollständig gelesen):**

1. `konzept/sealai_ssot_architecture_plan.md` — Base SSoT (§1–§32)
2. `konzept/sealai_ssot_supplement_v1.md` — §33 LangGraph-Rolle, §34 Konsistenz/Mutation/Outbox, §35 Schema-4-Layer, §36 Persistenz
3. `konzept/sealai_ssot_supplement_v2.md` — §37 Moat, §38 Anti-Patterns, §39 MVP PTFE-RWDR, §40 Terminology Registry, §41 Capability-Modell, §42 Business-Logik, §43 COI
4. `konzept/sealai_engineering_depth_ptfe_rwdr.md` — PTFE-RWDR Fachtiefe (§3 Compound-Taxonomie, §4 Lipgeometrie, §5 Welle, §6 Envelope, §7 Failure-Modes, §8 Risiken, §9 Checks)
5. `CLAUDE.md` (v3.0, 2026-04-17)
6. `AGENTS.md`

**Konfliktauflösung:** Supplement > Base SSoT im Überlappungsbereich; Engineering-Depth-Guide > SSoT-Set für PTFE-RWDR-Felder.

**Methodik:**
- Schritt 1: Vollständiges Lesen der sechs Authority-Dokumente.
- Schritt 2: Strukturierte Evidenzsammlung via direkter Grep/Read/Bash-Aufrufe (Explore-Subagenten zeitweise rate-limited, direkte Tools präziser).
- Schritt 3: Jede Frage in §3 mit Pfaden, Zeilennummern, konkreten Symbolen belegt.
- Schritt 4: Klassifikation KEEP/ADAPT/REPLACE/REMOVE mit T-Shirt-Größen.
- Schritt 5: Mindestens 5 `NEEDS_FOUNDER_INPUT` als offene Entscheidungspunkte.

**Nicht-Inhalt des Reports:**
- Keine Strategiewahl (Strangler Fig / Selective Rewrite / Greenfield) — siehe §7.
- Keine Timeline- oder Roadmap-Aussagen.
- Keine Code-Änderungen.

**Versionsinformation:**
- Branch: `codex/ptfe-rwdr-ssot-implementation`
- Head: `c9a90524 docs: update CLAUDE.md to v3.0 for full authority set`
- Alembic-Migrationen im Tree: 12
- Letzte Cases-Migration: `f2d9c4a8b6e1_add_cases_and_case_state_snapshots.py` (2026-04-09)

---

## 1. Executive Summary

### 1.1 Gesamtbild

Der SeaLAI-Backend-Kern zeigt strukturell-starke Einzelelemente, aber eine **grundlegende Diskrepanz zwischen dem Zielmodell der Authority-Stack-Dokumente und der implementierten Realität**. Die folgenden Befunde sind die kritischsten:

1. **Case-Persistenz ist substanzlos gegenüber Supplement v1 §36.3.** Die Tabelle `cases` besitzt 7 Spalten und keinen der SSoT-Pflichtfelder (kein `case_revision`, kein `tenant_id`, kein `payload JSONB`, kein `request_type`, kein `routing_path`, kein `schema_version`, kein `rfq_ready`, kein `inquiry_admissible`). Die revisionsführende Tabelle ist ausgelagert (`case_state_snapshots`). Optimistic Locking ist nicht umgesetzt.

2. **Keine mutation_events-Tabelle, keine outbox-Tabelle, kein `apply_mutation()`-Pfad.** Supplement v1 §34 verlangt ein Mutations-Event-Journal mit Outbox-Pattern für Konsistenz/Replay; dieses Fundament fehlt vollständig. Alle projizierenden Änderungen werden direkt am Case-State ausgeführt.

3. **Drei parallele Orchestrierungs-Stacks koexistieren.**
   - `backend/app/agent/` — enthält die architekturnahe „Governed"-Pipeline mit deterministischen Nodes (`graph/topology.py`) und dem output-klassifizierenden `output_contract_node.py` (1335 Zeilen, 6 von 7 SSoT-Output-Klassen).
   - `backend/app/services/langgraph/` — konkurrierende Graph-/Regel-Implementierung mit YAML-Regeln (`rules/common.yaml`, `rules/rwdr.yaml`) und Domänenpfaden (`domains/rwdr`, `domains/hydraulics_rod`).
   - `backend/app/services/fast_brain/router.py` — Lightweight-Router.
   Keine explizite Reconciliation gemäß Supplement v1 §33.10.

4. **`RoutingPath` und `ResultForm` sind nicht das SSoT-Modell.** `backend/app/agent/runtime/policy.py:26-46` definiert `RoutingPath ∈ {FAST_PATH, STRUCTURED_PATH, META_PATH, BLOCKED_PATH, GREETING_PATH}`. Dies sind Konversations-/Interaction-Pfade, kein `engineering_path ∈ {ms_pump, rwdr, static, labyrinth, hyd_pneu, unclear_rotary}` aus AGENTS §5.2. Das SSoT-Konzept `request_type × engineering_path` ist in der Runtime-Policy *nicht vorhanden*; es existiert bestenfalls in `api/v1/projections/case_workspace.py` als abgeleiteter String.

5. **Terminology-Registry und Capability-Claim-Modell (Moat-Layer 2) existieren nicht im Code.** Grep nach `GenericConcept`, `ProductTerm`, `ManufacturerProfile`, `ManufacturerCapabilityClaim` liefert 0 Treffer im Backend (lediglich Strings in KB-JSON). Das Moat-Kernstück aus Supplement v2 §40/§41 ist strukturell ungebaut. `matching_node.py` matcht zwar bereits auf strukturierte Capability-Pakete (Moat-Layer 2 teilweise eingehalten), aber ohne das vom SSoT geforderte Registry-Rückgrat.

6. **PTFE-RWDR-Tiefenmodell fehlt im Code.** `sealing_material_family`-Enum existiert nur als KB-JSON-Schlüssel, nicht als Backend-Enum/Schema-Feld. Compound-Taxonomie (`ptfe_virgin/glass/carbon/bronze/mos2/graphite/peek/mixed`) ist weder als Enum noch als Validator im Code. PTFE-spezifische Failure-Modes (`spiral_failure`, `lead_induced_pumping_leakage`, `creep_induced_contact_loss`, `chemical_attack_filler`, `hang_up`) fehlen. Der `checks_registry.py` registriert 3 RWDR-Checks, aber keine PTFE-spezifischen Prüfungen aus Engineering-Depth-Guide §9.

7. **Vier-Layer-Schema-Trennung (Supplement v1 §35) ist invertiert.** `backend/app/schemas/` ist praktisch leer. Die API-Schemas liegen unter `backend/app/api/v1/schemas/case_workspace.py` — API-Layer besitzt das Schema statt umgekehrt. `backend/app/domain/` (Top-Level) existiert nicht; Domänenmodule liegen unter `backend/app/agent/domain/` und importieren upward aus `app.models` (z. B. `material.py:338` importiert `app.models.material_profile`). Supplement v1 §35.8 untersagt upward imports.

8. **Drei-Modi-Phase-Gate (CONVERSATION/EXPLORATION/GOVERNED) ist präsent.** `backend/app/agent/runtime/gate.py`, `observability/metrics.py:270`, `agent/tests/test_gate_routes.py` zeigen den Trichotomie-Gate produktiv. Supplement v1 §33 und CLAUDE §5.1 warnen explizit vor Rückfall auf binären Gate — dieser Befund ist positiv.

9. **`rca_hypothesis` und drei weitere Request-Types fehlen operativ.** `output_contract_node.py` implementiert 6 der 7 SSoT-Output-Klassen; `rca_hypothesis` ist nicht produziert. Die Request-Types `rca_failure_analysis`, `spare_part_identification`, `quick_engineering_check`, `validation_check` treten ausschließlich in Projektions-/Schema-Dateien auf (`api/v1/projections/case_workspace.py`, `api/v1/schemas/case_workspace.py`), nicht in Routing-/Gate-/Graph-Code.

10. **Multi-Tenancy endet bei RAG-Dokumenten.** `tenant_id` ist nur in `models/rag_document.py` und `models/deterministic_norms.py` gesetzt. Die Tabelle `cases` trägt kein `tenant_id`, alle Case-bezogenen Queries sind damit Tenant-blind. Supplement v1 §36.3 verlangt `tenant_id` als harte Voraussetzung.

### 1.2 Priorisierter Handlungsraum (neutral, keine Strategiewahl)

- Größte Delta-Fläche: **Persistenz-Kern + Case-Service + Mutation/Outbox** (Supplement v1 §33.5, §34, §36). Ohne dieses Fundament sind alle weiteren Schritte (Projection-Service, Output-Validator, Risk-Engine-Rebuild) spekulativ.
- Zweitgrößte: **Terminology-Registry + Capability-Claims** (Moat-Layer 2). Ohne diese ist strukturell keine kompromisslose Neutralität gegenüber dem Arbeitgeber des Founders möglich (COI-Risiko, Supplement v2 §43).
- Drittgrößte: **PTFE-RWDR-Tiefenmodell** (Material-Family-Enum, Compound-Taxonomie, Failure-Modes, Checks, Risk-Dimensions aus Engineering-Depth §3–§9).

### 1.3 Nicht-Aussagen

Dieser Report enthält **keine** Aussage über:
- gewählte Transitionsstrategie,
- Zeitplan,
- Personenzuweisung,
- Release-Plan,
- Gewichtung nach Business-Impact (Monetarisierung vs. Technik).

Diese Entscheidungen sind Founder-Entscheidungen und werden in §7 als `NEEDS_FOUNDER_INPUT` markiert.

---

## 2. Authority-Stack — Gelesener Inhalt (Verdichtung für Evidenz-Bezüge)

Kurzreferenzen, auf die §3 und §5 zurückverweisen:

- **Base SSoT §7 Phasenmodell:** Phasen 0–5 (Scope-Gate, Deterministic Path Selection, Core Intake, Failure Drivers, Geometry/Fit, RFQ/Readiness). Dürfen nicht zu einem generischen Intake-Flow kollabiert werden.
- **Base SSoT §8 Backend-Wahrheit:** Backend ist kanonisch; Frontend projiziert.
- **Base SSoT §9 Provenance:** Sechs Herkünfte (`user_stated/documented/web_hint/calculated/confirmed/missing`) sowie medium-spezifische Provenance-Layer.
- **Base SSoT §10 Output-Klassen (7):** `conversational_answer`, `structured_clarification`, `governed_state_update`, `technical_preselection`, `rca_hypothesis`, `candidate_shortlist`, `inquiry_ready` — Prompt-Restriktionen sind **nicht hinreichend**; Backend-Validator erforderlich.
- **Base SSoT §11 Stale-Invalidation:** Revisionserhöhung, abhängige Recompute-Queues bei kritischen Invalidatoren.
- **Base SSoT §12 Chemische Kompatibilität:** Eigenes Subsystem (Registry + SDS/TDS + Fallbacks), keine reine LLM-/Prompt-Logik.
- **Base SSoT §13 Norm-Module:** Separate Module mit Applicability + Required Fields + Checks + Escalation (API 682, EN 12756, DIN 3760/ISO 6194, ISO 3601, VDI 2290, ATEX).
- **Base SSoT §14 Checks-Registry:** Jede Berechnung hat `calc_id`, Required Inputs, Valid Paths, Output Key, Version, Fallback.
- **Base SSoT §17 Versionierung:** Pflichtfelder `schema_version`, `ruleset_version`, `calc_library_version`, `risk_engine_version`, `norm_module_versions`, `case_revision` pro Case.
- **Supplement v1 §33.4:** LangGraph-Nodes sind dünn; Business-Logik steckt in Services. Nodes orchestrieren, nicht entscheiden.
- **Supplement v1 §33.5 Required Services:** `case_service`, `phase_gate_service`, `routing_service`, `projection_service`, `formula_library`, `risk_engine`, `compatibility_service`, `output_validator`, `outbox_worker`.
- **Supplement v1 §33.8:** Services unter `backend/app/services/` müssen ohne LangGraph-Importe testbar sein.
- **Supplement v1 §33.10:** Parallele Orchestrierungs-Stacks (`fast_brain` vs. `agent/graph`) dürfen nicht koexistieren ohne explizite Reconciliation.
- **Supplement v1 §34.3–§34.4:** Jede Mutation läuft über `case_service.apply_mutation()` mit Optimistic Lock auf `case_revision`. LangGraph-Nodes schreiben **nicht direkt** in Postgres.
- **Supplement v1 §35 Schema-4-Layer:** `domain/` (PoPo reine Typen) → `models/` (ORM) → `schemas/` (API-Pydantic) → `agent-state/` (LangGraph-TypedDicts). Keine upward imports.
- **Supplement v1 §36.3 Cases-Tabelle DDL:** Pflicht-Spalten `case_id (UUID pk)`, `tenant_id`, `case_number`, `schema_version`, `ruleset_version`, `calc_library_version`, `risk_engine_version`, `case_revision`, `phase`, `request_type`, `routing_path`, `rfq_ready`, `inquiry_admissible`, `payload JSONB`, `created_at`, `updated_at`, Indizes.
- **Supplement v1 §36 mutation_events / outbox / risk_scores:** Separate Tabellen.
- **Supplement v2 §37 Moat-Layer:** (1) Strukturelle Neutralität, (2) Technische Translation via Registry+Capabilities, (3) Request-Qualifikation.
- **Supplement v2 §38 Anti-Patterns:** Pay-for-Ranking, Founder-Employer-Bonus, Marketing-Text-Matching, Regex-auf-Descriptions, Silent Terminology Fallthrough.
- **Supplement v2 §39 MVP-Scope:** Deep-Fidelität nur für `rwdr` + `sealing_material_family ∈ ptfe_*`. Alle anderen Pfade flach.
- **Supplement v2 §40/§41:** `GenericConcept`, `ProductTerm`, `ManufacturerProfile`, `ManufacturerCapabilityClaim` als eigene ORM-Entitäten.
- **Supplement v2 §43:** COI-Constraint — keine asymmetrische Behandlung des Founder-Arbeitgebers, Data-Firewall.
- **Engineering-Depth §3 Compound-Taxonomie:** `ptfe_virgin`, `ptfe_glass_15_25`, `ptfe_glass_moly`, `ptfe_carbon_graphite`, `ptfe_bronze`, `ptfe_mos2`, `ptfe_peek`, `ptfe_mixed`, ...
- **Engineering-Depth §7 Failure-Modes:** `spiral_failure`, `lead_induced_pumping_leakage`, `creep_induced_contact_loss`, `chemical_attack_filler`, `hang_up`, `thermal_distortion`.
- **Engineering-Depth §8 Risiken:** `risk.thermal`, `risk.pressure`, `risk.surface_speed`, `risk.lead_pumping`, `risk.surface_quality`, `risk.creep_longevity`, `risk.chemical_compatibility`, `risk.dry_run`, `risk.misalignment`, `risk.installation`.
- **Engineering-Depth §9 Checks:** `circumferential_speed`, `compound_pv_loading`, `creep_gap_estimate_simplified`, `thermal_load_indicator`, `extrusion_gap_check`.

---

## 3. Antworten auf die 10 Audit-Kernfragen

Jeder Abschnitt folgt dem Schema **Finding / Expectation / Delta / Evidence**.

### Frage 1 — Case Model / Persistenz-Kern

**Finding:**
- ORM `CaseRecord` in `backend/app/models/case_record.py:1-21` besitzt 8 Spalten:
  `id` (String(36) UUID), `case_number` (unique), `session_id`, `user_id`, `subsegment`, `status`, `created_at`, `updated_at`.
- Revisionshistorie ist ausgelagert in `backend/app/models/case_state_snapshot.py:1-26` mit `case_id`, `revision`, `state_json JSONB`, `basis_hash`, `schema_version`, `ruleset_version_used`, `calc_library_version`, `risk_engine_version`.
- Alembic-Migration `backend/alembic/versions/f2d9c4a8b6e1_add_cases_and_case_state_snapshots.py` (2026-04-09) erstellt beide Tabellen. Keine nachfolgende Migration erweitert `cases`.
- Grep nach `apply_mutation|MutationEvent|case_revision|OptimisticLock` liefert 3 Treffer — nur `case_state_snapshot.py` (Spalte `revision`) und 1 Test (`agent/tests/test_endpoint_routing.py`), keine Mutationsservice.
- Grep nach `outbox|OutboxEvent|process_outbox`: 0 Treffer. Outbox-Pattern fehlt komplett.

**Expectation (Supplement v1 §36.3):**
Cases-Tabelle mit ≥17 Spalten inklusive `tenant_id`, `schema_version`, `ruleset_version`, `calc_library_version`, `risk_engine_version`, `case_revision`, `phase`, `request_type`, `routing_path`, `rfq_ready`, `inquiry_admissible`, `payload JSONB`. `mutation_events` als append-only Journal, `outbox` für side-effects, Optimistic Lock auf `case_revision`.

**Delta:**
- Fehlt: 13 von 17 Spalten auf `cases`.
- Fehlt: `mutation_events`-Tabelle.
- Fehlt: `outbox`-Tabelle.
- Fehlt: `case_service` mit `apply_mutation()`.
- Fehlt: Optimistic Lock in Write-Pfaden.
- Bedingt vorhanden: Revisionshistorie via separater `case_state_snapshots`-Tabelle (nicht das im SSoT vorgesehene Pattern).
- Bedingt vorhanden: Versionierungs-Stempel (`schema_version` etc.) in `case_state_snapshots`, aber nicht auf `cases`.

**Evidence:**
- `backend/app/models/case_record.py:1-21`
- `backend/app/models/case_state_snapshot.py:1-26`
- `backend/alembic/versions/f2d9c4a8b6e1_add_cases_and_case_state_snapshots.py:1-61`
- Alembic-Migrationen-Liste: 12 Dateien, keine mit `mutation_events`, `outbox` oder `risk_scores` im Namen.

---

### Frage 2 — Phase Gates & Output Classes

**Finding:**
- Drei-Modi-Gate (CONVERSATION/EXPLORATION/GOVERNED) existiert produktiv.
  - `backend/app/agent/runtime/gate.py`
  - `backend/app/agent/runtime/conversation_runtime.py`
  - `backend/app/agent/runtime/user_facing_reply.py`
  - `backend/app/agent/runtime/response_renderer.py`
  - `backend/app/agent/prompts/gate/gate_classify.j2`
  - `backend/app/agent/tests/test_gate.py`, `test_gate_routes.py`, `test_gate_metrics.py`
  - `backend/app/observability/metrics.py` (Gate-Modus-Metriken)
- Output-Klassen-Derivation in `backend/app/agent/graph/nodes/output_contract_node.py` (1335 Zeilen) ist **deterministisch** — LLM wird im Output-Pfad *nicht* aufgerufen. Abbildung GovernanceState → Output-Klasse:
  - `rfq_ready + rfq_admissibility = ready` → `inquiry_ready`
  - Matching-Kontext mit Shortlist → `candidate_shortlist`
  - Class A + Compute präsent → `technical_preselection`
  - Class A ohne Compute → `governed_state_update`
  - Class B / D → `structured_clarification`
  - Class C → `structured_clarification`
- Von den 7 SSoT-Output-Klassen sind **6 implementiert**. `rca_hypothesis` fehlt vollständig — Grep nach `rca_hypothesis` liefert 0 Backend-Code-Treffer (nur Schemas/Projections in `api/v1/projections/case_workspace.py` und `api/v1/schemas/case_workspace.py`).
- `conversational_answer` ist strukturell als „non-governed path" abgebildet, wird aber nicht über `output_contract_node` geroutet.

**Expectation (Base SSoT §10, §24):**
Alle 7 Output-Klassen vom Backend produzierbar, mit Output-Validator gegen Red-Flag-Phrasen („guaranteed", „definitely works", „fully approved", „norm compliant" ohne Basis).

**Delta:**
- Fehlt: `rca_hypothesis`-Produktion.
- Fehlt: zentraler `output_validator`-Service (Grep: 0 Treffer). Red-Flag-Prüfung ist aktuell nicht backend-seitig erzwungen.
- Vorhanden und sachlich korrekt: deterministische Klassenableitung über GovernanceState.
- Vorhanden: Drei-Modi-Phase-Gate (positive Abweichung vom historischen binären Gate).

**Evidence:**
- `backend/app/agent/graph/nodes/output_contract_node.py:1-80` (Ableitungslogik)
- Grep `rca_hypothesis`: Treffer nur in `api/v1/projections/case_workspace.py`, `api/v1/schemas/case_workspace.py`, `agent/tests/test_case_workspace_projection.py` (keine Produzenten).
- Grep `output_validator|red_flag|guaranteed_phrase`: 0 Treffer in `backend/app/`.

---

### Frage 3 — LangGraph Boundary

**Finding:**
- Governed-Pipeline in `backend/app/agent/graph/topology.py` (191 Zeilen):
  ```
  intake_observe → normalize → assert → evidence → compute → governance
    → (cycle back | matching → rfq_handover → dispatch → norm → export_profile
       → manufacturer_mapping → dispatch_contract → output_contract → END)
  ```
- Zeilenumfänge der Nodes:
  - `intake_observe_node.py`: 454 Zeilen — einziger LLM-aufrufender Node (kongruent zu AGENTS §6.1).
  - `normalize_node.py`: 84, `assert_node.py`: 57, `evidence_node.py`: 437, `compute_node.py`: 158, `governance_node.py`: 93, `matching_node.py`: 471, `rfq_handover_node.py`: 379, `dispatch_node.py`: 167, `manufacturer_mapping_node.py`: 131, `norm_node.py`: 135, `output_contract_node.py`: 1335, `dispatch_contract_node.py`: 102, `export_profile_node.py`: 113.
- Grep nach LangGraph-Importen unter `backend/app/services/`: `services/langgraph/` (Name allein verletzt Trennung), `services/fast_brain/router.py`.

**Expectation (Supplement v1 §33.4, §33.8):**
Nodes sind dünne Orchestrierer. Geschäftslogik in testbaren Services (`case_service`, `phase_gate_service`, etc.), die LangGraph *nicht* importieren.

**Delta:**
- Nodes sind teils sehr groß (`intake_observe_node` 454, `matching_node` 471, `output_contract_node` 1335, `rfq_handover_node` 379, `evidence_node` 437). Geschäftslogik ist in die Nodes eingegossen, nicht in Services.
- Services unter `backend/app/services/langgraph/` und `backend/app/services/fast_brain/` importieren langchain/langgraph (Namenskonvention ist sprechend; Grep bestätigt Imports in Router-Datei).
- Positiv: LLM-Aufruf ist auf `intake_observe_node` konzentriert (Grep zeigt `ChatOpenAI` / `llm.*invoke` primär dort).
- Positiv: Topologie ist klar, keine dynamischen Rewrites.

**Evidence:**
- `backend/app/agent/graph/topology.py`
- Node-Zeilenzahlen (`wc -l` oben)
- Grep-Ergebnisse zu LLM-Import

---

### Frage 4 — Schema-Trennung (4 Layer)

**Finding:**
- `backend/app/schemas/` existiert, ist aber praktisch leer bzw. wird nicht für Case-relevante Schemas genutzt.
- API-Schemas liegen unter `backend/app/api/v1/schemas/` (inkl. `case_workspace.py`). Das bedeutet: Der API-Layer beherbergt das Pydantic-Schema; der Domänen- oder Schema-Layer nicht.
- `backend/app/domain/` (Top-Level) existiert nicht. Stattdessen `backend/app/agent/domain/` mit 19 Dateien (5749 Zeilen), darunter `material.py` (475), `logic.py` (990), `normalization.py` (1033), `rwdr_calc.py` (547), `medium_registry.py` (400).
- `backend/app/agent/domain/material.py:338` importiert aus `app.models.material_profile` — **upward import** von Domain → Models (Models sind laut §35 eine höhere Layer-Ebene).
- Agent-State liegt unter `backend/app/agent/state/case_state.py` (1644 Zeilen). `CaseState` TypedDict hat 27+ Keys inkl. `case_meta`, `requirement_class`, `observed_inputs`, `normalized_parameters`, `governance_state`, `matching_state`, `rfq_state`, `manufacturer_state`, `readiness`, `invalidation_state`, `audit_trail`.

**Expectation (Supplement v1 §35):**
- `domain/` → reine Typen/Werte-Objekte, ohne I/O-Abhängigkeiten.
- `models/` → SQLAlchemy ORM.
- `schemas/` → API-Pydantic.
- `agent-state/` → LangGraph-TypedDicts.
- Keine upward imports (§35.8).

**Delta:**
- Domain-Layer ist an der falschen Stelle (`agent/domain/` statt `domain/`).
- Upward import nachgewiesen (`agent/domain/material.py:338` → `app.models.material_profile`).
- Schema-Layer ist strukturell invertiert (API-Layer besitzt Schemas).
- Agent-State ist monolithisch in einer 1644-Zeilen-Datei (verletzt nicht direkt §35, aber Modularisierungsziel nicht erfüllt).

**Evidence:**
- `backend/app/schemas/` (Directory-Listing)
- `backend/app/api/v1/schemas/case_workspace.py`
- `backend/app/agent/domain/material.py` (Import-Statement)
- `backend/app/agent/state/case_state.py:98-127` (CaseState-Definition)

---

### Frage 5 — Persistenz (Postgres als SoT, Redis nur transient)

**Finding:**
- Postgres-Modelle (Auswahl): `case_record.py`, `case_state_snapshot.py`, `rag_document.py`, `rag_embedding.py`, `deterministic_norms.py`, `audit_log.py` (und weitere).
- Tabelle `cases`: ohne `tenant_id`, ohne `payload JSONB`, ohne `request_type`/`routing_path`/`rfq_ready`/`inquiry_admissible`.
- Keine Tabelle `mutation_events` (Supplement v1 §34.3–§34.4 Pflicht).
- Keine Tabelle `outbox` (Supplement v1 §34.5 Pflicht).
- Keine Tabelle `risk_scores` als separate persistierte Risiko-Ebene.
- Redis wird laut Memory für LangGraph-Checkpoints und Rate-Limits verwendet (siehe auch `backend/app/services/rag/rate_limit`), nicht als kanonische Truth. Das ist konform.
- Qdrant: einzelne Collection `sealai_knowledge` (Memory-Eintrag) — konform.

**Expectation (Supplement v1 §36):**
- Postgres = kanonisch für Cases, Mutations, Outbox, Risk-Scores.
- Redis = transient (Checkpoints, Streaming-Buffer, Rate-Limits).
- Qdrant = Vector-Store nur für Retrieval.

**Delta:**
- Fehlt: `mutation_events`, `outbox`, `risk_scores` in Postgres.
- Fehlt: `tenant_id` auf `cases`.
- Konform: Redis/Qdrant-Rollen.

**Evidence:**
- Alembic-Migrationen (12 Dateien, Namen enthalten keine der fehlenden Tabellen).
- `backend/app/models/` Directory-Listing.
- Memory-Einträge zu Redis/Qdrant.

---

### Frage 6 — Moat Compliance (Supplement v2 §37, §38, §43)

**Finding — Layer 1 (Strukturelle Neutralität):**
- Grep nach `sponsored|featured|promoted|boost|priority_flag|ranking_bonus`: 0 Treffer in `backend/app/` (außer evtl. in RAG-Docs-Metadaten, nicht Matching-relevant).
- `matching_node.py` (erste 80 Zeilen) und `manufacturer_mapping_node.py` (131 Zeilen) zeigen keinen manufacturer-spezifischen Boost.
- Kein Sponsorship-Labeling-System vorhanden — aber da auch kein Sponsoring existiert, formal konform per Default.

**Finding — Layer 2 (Technische Translation):**
- `matching_node.py:1-80` operiert auf strukturierten Packages: `ManufacturerCapabilityPackage`, `ManufacturerRfqAdmissibleRequestPackage`, `ManufacturerRfqSpecialistInput`. Grep nach `marketing_text|text_similarity|description_match|regex.*marketing`: 0 Treffer — Marketing-Text-Matching existiert nicht.
- Aber: **Terminology Registry und Capability-Claim-Entitäten existieren nicht.** Grep `GenericConcept`, `ProductTerm`, `ManufacturerProfile`, `ManufacturerCapabilityClaim`: 0 Backend-Code-Treffer. Das Matching nutzt hartkodierte Hints wie `_REQUIREMENT_CLASS_MATERIAL_HINTS = {"PTFE": "PTFE", "FKM": "FKM"}` (`matching_node.py`).
- Der Matching-Layer ist strukturell, aber ohne das vom SSoT geforderte Registry-Rückgrat.

**Finding — Layer 3 (Request-Qualifikation):**
- `rfq_handover_node.py` (379 Zeilen) + `dispatch_contract_node.py` + `output_contract_node.py` produzieren strukturierte Inquiry-Pakete.
- Open-Points und Assumptions werden im Case-State als `readiness`, `invalidation_state`, `rfq_state` getragen (laut `CaseState`-TypedDict).
- Konform in der Richtung; Details der Paket-Vollständigkeit prüfbar im finalen Export-Path.

**Finding — COI (Supplement v2 §43):**
- Keine Founder-Employer-Namen in Code / YAML-Regeln sichtbar (stichprobenhaft `rules/rwdr.yaml`, `rules/common.yaml`).
- Kein Flag `employer_boost`, `founder_manufacturer`, `priority_employer`: 0 Treffer.
- Data-Firewall kann ohne Stichprobe der RAG-Dokumente nicht final bestätigt werden — siehe `NEEDS_FOUNDER_INPUT #3`.

**Expectation:**
- Sponsored-Zones mit expliziten Labels (wenn vorhanden) — aktuell leer, also compliant.
- Capability-Claims via Terminology-Registry strukturiert matchbar.
- Keine Asymmetrie bzgl. Founder-Employer im Code oder in Datensätzen.

**Delta:**
- Fehlt: Terminology-Registry (`GenericConcept`, `ProductTerm`).
- Fehlt: `ManufacturerProfile`, `ManufacturerCapabilityClaim` als eigene ORM.
- Fehlt: Sponsored-Label-Slots in API-Responses (vorsorglich für Phase 2+).
- Konform: Kein Marketing-Text-Matching, kein sichtbarer Employer-Bonus.

**Evidence:**
- Grep-Ergebnisse (0 Treffer für die genannten Entitäten).
- `backend/app/agent/graph/nodes/matching_node.py:1-80`
- `backend/app/services/langgraph/rules/rwdr.yaml` (Regelbasiertes Matching ohne Sponsored-Attribute).

---

### Frage 7 — Terminology- & Capability-Modell

**Finding:**
- Grep nach `GenericConcept|ProductTerm|ManufacturerProfile|ManufacturerCapabilityClaim` im gesamten Backend: 0 Treffer.
- Grep nach `terminology_registry|terminology_map|product_term_map`: 0 Treffer.
- Harte Mappings existieren als ad-hoc Konstanten (z. B. `_REQUIREMENT_CLASS_MATERIAL_HINTS` in `matching_node.py`).
- Keine Alembic-Migration für Terminology-Tabellen (`generic_concepts`, `product_terms`, `manufacturer_profiles`, `manufacturer_capability_claims`).

**Expectation (Supplement v2 §40, §41, Annex B):**
- ORM-Entitäten für jedes der vier Kernmodelle, mit `schema_version`, `tenant_id`, Lookup-Indizes.
- Seed-Daten laut Annex B (mind. Basis-Generic-Concepts für RWDR).
- Mapping-Service `terminology_service` mit Normalisierungs- und Disambiguierungslogik.

**Delta:**
- Vollständig fehlend: alle vier Entitäten, Migrations, Seed-Daten, Mapping-Service.
- Ad-hoc-Mappings streuen in Node-Dateien — Anti-Pattern „Silent Terminology Fallthrough" droht.

**Evidence:**
- Grep-Null-Ergebnisse (siehe oben).
- `backend/app/agent/graph/nodes/matching_node.py:1-80` (hartkodierte Material-Hints).

---

### Frage 8 — PTFE-RWDR Tiefenmodell (MVP-Depth)

**Finding:**
- `sealing_material_family`-Enum / Schema-Feld existiert nicht im Code. Grep `sealing_material_family`: 2 Treffer, beide in KB-JSON (`backend/app/data/kb/SEALAI_KB_PTFE_factcards_gates_v1_3.json`) und 1 Test (`tests/test_kb_services.py`).
- Compound-Taxonomie (Engineering-Depth §3): Grep nach `ptfe_virgin|ptfe_glass|ptfe_carbon|ptfe_bronze|ptfe_mos2`: ausschließlich KB-JSON-Treffer, kein Enum, kein Pydantic-Feld, kein SQL-Enum.
- Failure-Modes (§7): Grep nach `spiral_failure|lead_induced_pumping_leakage|creep_induced_contact_loss|chemical_attack_filler|hang_up` unter `backend/app/`: 0 Treffer außerhalb KB-Dokumenten.
- Risk-Dimensionen (§8): Grep nach `risk.thermal|risk.pressure|risk.surface_speed|risk.lead_pumping|risk.creep|RiskEngine`: 0 Treffer. Kein `risk_engine`-Service, keine Risk-Dimension-Enumeration.
- Checks (§9): `backend/app/agent/domain/checks_registry.py` registriert genau 3 Checks: `rwdr_circumferential_speed`, `rwdr_pv_precheck`, `rwdr_dn_value` (alle `formula_version=rwdr_calc_v1`). Fehlend: `compound_pv_loading`, `thermal_load_indicator`, `creep_gap_estimate_simplified`, `extrusion_gap_check`, `flashing_margin`, `lead_induced_pumping_indicator`.
- RWDR-Rechnungen in `agent/domain/rwdr_calc.py` (547 Zeilen) vorhanden — aber Compound-Differenzierung (z. B. PV-Limit abhängig von Compound) nicht durch Enum getrieben.

**Expectation (Engineering-Depth §3, §7, §8, §9):**
- `sealing_material_family` als strukturelles Enum in `domain/` oder `schemas/`, referenziert in `CaseState` und `cases`-Payload.
- Failure-Mode-Taxonomie als Literal/Enum mit Deskriptor-Metadaten.
- Risk-Engine-Service mit 10 Dimensionen aus §8.
- 5+ PTFE-spezifische Checks im Registry (§9.2).

**Delta:**
- Fehlt: `sealing_material_family`-Enum und Case-State-Feld.
- Fehlt: Compound-Taxonomie als Backend-Typ.
- Fehlt: Failure-Mode-Enum.
- Fehlt: Risk-Engine-Service mit 10 Dimensionen.
- Fehlt: 5+ PTFE-Checks im Registry.
- Teilvorhanden: RWDR-Checks (3) und RWDR-Berechnungen in `rwdr_calc.py`.
- KB-JSON-Repräsentation existiert (FactCards/CompoundMatrix) — aber nicht als Backend-Typen konsumiert.

**Evidence:**
- `backend/app/agent/domain/checks_registry.py:27-61`
- `backend/app/agent/domain/rwdr_calc.py` (Linien-Zählung 547)
- `backend/app/data/kb/SEALAI_KB_PTFE_factcards_gates_v1_3.json` (KB-Referenz)
- Grep-Null-Ergebnisse zu den obigen Begriffen.

---

### Frage 9 — Parallele Orchestrierungs-Stacks

**Finding:**
Drei Stacks koexistieren:

1. **`backend/app/agent/`** — Haupt-Governed-Graph:
   - `agent/graph/topology.py` (191 Zeilen)
   - `agent/graph/nodes/*.py` (14 Nodes, 4117 Zeilen gesamt)
   - `agent/runtime/` (Gate, Policy, Conversation-Runtime, User-Facing-Reply, Response-Renderer)
   - `agent/domain/` (19 Dateien, 5749 Zeilen)
   - `agent/state/case_state.py` (1644 Zeilen)

2. **`backend/app/services/langgraph/`** — konkurrierende Regel/Graph-Implementierung:
   - `domains/rwdr/`, `domains/hydraulics_rod/`
   - `graph/`
   - `rules/common.yaml`, `rules/rwdr.yaml`
   - `prompts/`, `prompt_templates/`
   - `tools/`, `rag/`
   - `redis_lifespan.py`

3. **`backend/app/services/fast_brain/`** — Lightweight Router:
   - `router.py`
   - `__init__.py`

**Cross-Nutzung:** FastAPI-Endpoints `api/v1/endpoints/langgraph_v2.py` und `api/v1/fast_brain_runtime.py` + `api/v1/sse_runtime.py` deuten darauf hin, dass beide Stacks aus dem HTTP-Layer erreichbar sind.

**Expectation (Supplement v1 §33.10):**
Explizite Reconciliation (gemeinsames Case-Service-API, gemeinsame State-Repräsentation, klarer Migrationspfad von einem Stack in den anderen, oder Deprecation-Markierung).

**Delta:**
- Fehlt: Dokumentierter Reconciliation-Pfad.
- Fehlt: Deprecation-Markierung.
- Fehlt: Migration-Test, der sicherstellt, dass `fast_brain`/`services/langgraph` dieselben Ergebnisse wie der Haupt-`agent/`-Graph liefern.
- Kodifikation-Risiko: Zwei Graphen können divergierende Output-Klassen produzieren, ohne zentralen Validator.

**Evidence:**
- Directory-Listings von `backend/app/agent/`, `backend/app/services/langgraph/`, `backend/app/services/fast_brain/`.
- `backend/app/api/v1/endpoints/langgraph_v2.py`, `api/v1/fast_brain_runtime.py`, `api/v1/sse_runtime.py`.

---

### Frage 10 — Engineering-Path Drift

**Finding:**
- AGENTS §5.2 SSoT-Enum: `engineering_path ∈ {ms_pump, rwdr, static, labyrinth, hyd_pneu, unclear_rotary}`.
- Grep `engineering_path|EngineeringPath`: 5 Treffer — alle in Projection- und Workspace-Schemas (`api/v1/projections/case_workspace.py`, `api/v1/schemas/case_workspace.py`, `agent/tests/test_case_workspace_projection.py`, `agent/domain/checks_registry.py` als String-Literal in `valid_paths`). **Kein zentraler `EngineeringPath`-Enum.**
- `backend/app/agent/runtime/policy.py:26-33` definiert stattdessen `RoutingPath`:
  ```
  FAST_PATH, STRUCTURED_PATH, META_PATH, BLOCKED_PATH, GREETING_PATH
  ```
  Das ist ein **Interaction/Runtime-Konzept**, kein Engineering-Path.
- `backend/app/agent/runtime/policy.py:36-43` definiert `ResultForm`:
  ```
  DIRECT_ANSWER, GUIDED_RECOMMENDATION, DETERMINISTIC_RESULT, QUALIFIED_CASE
  ```
  — auch das deckt die 7 SSoT-Output-Klassen *nicht* ab.
- Das `output_contract_node` derivert die Output-Klasse eigenständig — damit existiert strukturell ein zweites „Klassenmodell" neben `ResultForm`. Inkonsistenz-Risiko.
- `subsegment`-Feld auf `cases`-ORM (`case_record.py:11`) ist String-artig, keine Enum-Bindung an SSoT-Pfade.
- Request-Types (`new_design`, `retrofit`, `rca_failure_analysis`, `validation_check`, `spare_part_identification`, `quick_engineering_check`): Grep findet Treffer nur in Projektion/Schema, nicht im Gate oder in der Routing-Policy. Nur `rca_failure_analysis` hat keinen Produzenten außer Schemas.

**Expectation (AGENTS §5, CLAUDE §4):**
- `request_type × engineering_path` als zwei orthogonale, strukturierte Enums mit klarer ORM- und Schema-Repräsentation.
- Gate-/Routing-Logik entscheidet deterministisch, nicht LLM.
- Output-Klassen als eigenes Enum, separat von Interaction-Routing.

**Delta:**
- Fehlt: Kanonisches `EngineeringPath`-Enum auf `domain/`-Ebene.
- Fehlt: Kanonisches `RequestType`-Enum.
- Fehlt: ORM-Bindung (`cases.request_type`, `cases.routing_path` pflichtig).
- Vorhanden in parallelen Konzepten: `RoutingPath` (Interaction) und `ResultForm` (Teil-Output). Diese müssen **entweder entfernt oder klar unterhalb der SSoT-Enums geschachtelt** werden — Entscheidung offen, siehe `NEEDS_FOUNDER_INPUT #5`.

**Evidence:**
- `backend/app/agent/runtime/policy.py:26-46`
- `backend/app/models/case_record.py:11`
- `backend/app/api/v1/projections/case_workspace.py` (String-Ableitung)
- Grep-Ergebnisse zu `engineering_path|EngineeringPath`

---

## 4. Cross-Layer-Befunde

### 4.1 Import-Graph-Verletzungen

- **`backend/app/agent/domain/material.py:338`** importiert `from app.models.material_profile import ...` — Domain→Models ist upward laut §35. Muss umgekehrt werden (Domain-Typen → Models dürfen nicht importiert werden; wenn ORM ein Domain-Typ braucht, ist das legitim in umgekehrter Richtung).
- **`backend/app/services/langgraph/*`** importiert `langgraph`/`langchain` direkt. Supplement v1 §33.8 verbietet das für das Services-Verzeichnis.
- **`backend/app/services/fast_brain/router.py`** importiert LangGraph-Komponenten — selbe Verletzung.
- **`backend/app/api/v1/schemas/`** statt `backend/app/schemas/`: Schemas gehören gemäß §35.3 an einen separaten Top-Level.

### 4.2 Tote / veraltete Artefakte

- **`backend/app/_legacy_v2/`**: Subverzeichnisse `state/`, `tests/`, `utils/` enthalten außer `__pycache__` nichts. Quelldateien sind leer. Kandidat für `REMOVE`.
- **`backend/app/api/v1/endpoints/rag.py.bak`**: Backup-Datei im Quellbaum. Kandidat für `REMOVE`.
- **`backend/app/agent/agent/interaction_policy.py`** (20 Zeilen): Re-Export-Shim ("DO NOT add logic here"). Kandidat für `REMOVE` nach Bereinigung der Konsumenten.
- **Feature-Flags in `config.py`:**
  - `SEALAI_ENABLE_BINARY_GATE` — referenziert das historische Binary-Gate (Phase-F-Ära).
  - `SEALAI_ENABLE_CONVERSATION_RUNTIME` — Migrations-Switch, nicht mehr erforderlich, wenn Dreimodus produktiv.
  - `ENABLE_LEGACY_V2_ENDPOINT` — hält alten `/v2`-Pfad offen.
  - `LangSmith`-Projekt `sealai-phase-h` — referenziert Phase H (veraltet).
  - Alle vier sind Kandidaten für `REMOVE` bzw. Default-off.
- **`backend/app/services/fast_brain/router.py`**: Parallel-Stack (siehe Frage 9) — `ADAPT` oder `REMOVE` abhängig von Founder-Entscheidung.

### 4.3 Duplikate / parallele Repräsentationen

- **5 parallele Case-Darstellungen:**
  1. `models/case_record.py` (ORM, minimal)
  2. `models/case_state_snapshot.py` (ORM, Revisionshistorie)
  3. `agent/state/case_state.py` (TypedDict, 1644 Zeilen)
  4. `api/v1/projections/case_workspace.py` (Projektion, abgeleitete Strings)
  5. `api/v1/schemas/case_workspace.py` (Pydantic, Response-Schema)
- **Zwei „Output-Klassen"-Konzepte:** `ResultForm` (`agent/runtime/policy.py`) vs. Output-Contract-Node (`agent/graph/nodes/output_contract_node.py`).
- **Zwei „Routing"-Konzepte:** `RoutingPath` (Interaction) vs. `engineering_path` (Domain, in SSoT).
- **Drei „Graph"-Implementierungen:** `agent/graph/`, `services/langgraph/graph/`, `services/fast_brain/router.py`.
- **Zwei Regel-Repräsentationen:** Python (`agent/domain/logic.py`, `rwdr_calc.py`) vs. YAML (`services/langgraph/rules/rwdr.yaml`, `common.yaml`).

### 4.4 Konfigurations-Oberfläche

- `backend/app/core/config.py` ist mit ~79 Zeilen / ~40 Settings schlank.
- Problematisch:
  - Vier Legacy-Flags (oben genannt).
  - LangSmith-Projektname referenziert Phase H.
- Positiv: Pydantic-Settings, klare Struktur.

### 4.5 Multi-Tenancy

- `tenant_id` präsent auf:
  - `backend/app/models/rag_document.py`
  - `backend/app/models/deterministic_norms.py`
- **Fehlt auf:** `cases`, `case_state_snapshots`, `audit_log` (zu verifizieren).
- Supplement v1 §36.3 fordert `tenant_id NOT NULL` auf `cases`. Ohne das sind alle Case-Queries tenant-blind — dies ist ein harter Produktionsblocker.

### 4.6 FastAPI-Endpoint-Inventar

Vorhandene Endpoints (`backend/app/api/v1/endpoints/`):
`ai`, `auth`, `chat_history`, `langgraph_health`, `langgraph_v2`, `mcp`, `memory`, `ping`, `rag`, `rfq`, `state`, `system`, `users`.

SSoT §28 benötigte Endpoints (nicht abschließend, aus Base-SSoT):
- `POST /v1/case/intake`
- `POST /v1/case/{case_id}/update`
- `GET  /v1/case/{case_id}`
- `GET  /v1/case/{case_id}/projection`
- `GET  /v1/case/{case_id}/export/{artifact_type}`
- `POST /v1/norms/{norm_id}/check`
- `POST /v1/compatibility/query`
- `POST /v1/admin/migrate_case`

**Keiner** dieser SSoT-Pfade ist 1:1 vorhanden. `state.py` und `langgraph_v2.py` übernehmen vermutlich teilweise diese Funktion, aber ohne SSoT-konforme Response-Form.

### 4.7 Tests & Qualitätsgates

- `backend/app/agent/tests/`: Gate-Tests, Policy-Drift-Tests, Projection-Tests — solide Grundabdeckung.
- Pre-existing failing tests (aus Memory): 12 Tests (Kategorie B) rot. Kategorie A am 2026-03-01 geschlossen.
- Keine Tests für `mutation_events`/`outbox`/`apply_mutation` (weil nicht implementiert).
- Keine Tests für `sealing_material_family`-Routing.
- Keine Tests für `rca_hypothesis`-Produktion.

### 4.8 Observability

- `backend/app/observability/metrics.py`: Prometheus-Instruments vorhanden, inkl. Gate-Modus-Metrik (aus Memory).
- `backend/app/services/audit/audit_logger.py`: Append-only Audit-Log in Postgres. Nicht identisch mit `outbox`, aber struktureller Verwandter.

---

## 5. Klassifikationsmatrix (KEEP / ADAPT / REPLACE / REMOVE)

Legende: **Effort** = XS / S / M / L / XL als T-Shirt-Größe, rein Größen-Indikation.

### 5.1 KEEP (gute Substanz, Authority-konform)

| Pfad / Modul | Begründung |
|---|---|
| `backend/app/agent/graph/topology.py` | Deterministische Pipeline, LLM-isolation auf `intake_observe`. Konform mit §33.4. |
| `backend/app/agent/graph/nodes/output_contract_node.py` (Logik, nicht Größe) | Deterministische Output-Klassenableitung für 6 von 7 Klassen. |
| `backend/app/agent/runtime/gate.py` + drei-Modi-Umsetzung | Trichotomie CONVERSATION/EXPLORATION/GOVERNED implementiert. |
| `backend/app/observability/metrics.py` | Prometheus-Basis mit Gate-Metriken. |
| `backend/app/services/audit/audit_logger.py` | Append-only Audit-Log. |
| `backend/app/agent/domain/checks_registry.py` (Framework) | Struktur sauber, Registry-Pattern korrekt. |
| Qdrant-Nutzung (`sealai_knowledge`) | Single-Collection-Konvention konform. |
| Redis-Nutzung für Checkpoints und Rate-Limits | Als transient konsumiert, nicht als SoT missbraucht. |

### 5.2 ADAPT (Substanz vorhanden, aber Authority-Lücken)

| Pfad / Modul | Was anpassen | Effort |
|---|---|---|
| `backend/app/agent/graph/nodes/output_contract_node.py` | `rca_hypothesis`-Produktion ergänzen; Backend-Output-Validator aus dieser Logik extrahieren. | M |
| `backend/app/agent/graph/nodes/matching_node.py` | Hartkodierte Material-Hints auf Terminology-Registry umstellen; Capability-Claim-Konsum einführen. | L |
| `backend/app/agent/domain/checks_registry.py` | +5 PTFE-Checks (`compound_pv_loading`, `thermal_load_indicator`, `creep_gap_estimate_simplified`, `extrusion_gap_check`, `flashing_margin`). Integration mit neuem `risk_engine`. | M |
| `backend/app/agent/state/case_state.py` | Splitten auf ≥4 Teildateien gemäß §35; `sealing_material_family`, Compound-Taxonomie als typisierte Felder einziehen. | L |
| `backend/app/models/case_record.py` | Um 10+ SSoT-Spalten erweitern (`tenant_id`, `payload`, `case_revision`, `request_type`, `routing_path`, `rfq_ready`, `inquiry_admissible`, Versions-Stempel). Wanderung `case_state_snapshots` → Mutation/Outbox-Pattern prüfen. | XL |
| `backend/app/agent/runtime/policy.py` | `RoutingPath` und `ResultForm` klar als Interaction-Sublayer kennzeichnen oder in SSoT-Enums überführen. | M |
| `backend/app/api/v1/endpoints/*.py` | Auf SSoT §28 Pfade überführen (`/v1/case/intake`, `/v1/case/{id}/...`, `/v1/compatibility/query`, `/v1/norms/{norm_id}/check`). | L |
| `backend/app/api/v1/schemas/case_workspace.py` | In Top-Level `backend/app/schemas/` verschieben; Layer-Trennung nach §35 herstellen. | M |
| `backend/app/core/config.py` | Legacy-Flags entfernen, LangSmith-Projektname aktualisieren. | XS |
| `backend/app/services/langgraph/rules/*.yaml` | Entweder vollständig in `risk_engine`/`checks_registry` konsolidieren oder als eindeutige Datenquelle deklarieren. | M |

### 5.3 REPLACE (fundamentaler Rebuild nötig)

| Pfad / Modul | Grund | Effort |
|---|---|---|
| Persistenz-Layer für Cases | Neue Alembic-Migration: Cases-Erweiterung + `mutation_events` + `outbox` + `risk_scores`. | XL |
| `backend/app/services/` — `case_service`, `phase_gate_service`, `routing_service`, `projection_service`, `formula_library`, `risk_engine`, `compatibility_service`, `output_validator`, `outbox_worker` | Keiner existiert. Greenfield-Build unter `backend/app/services/` ohne LangGraph-Importe. | XL |
| Terminology-Registry + Capability-Claim-Stack | ORM-Entitäten, Migration, Seed, Mapping-Service. | L |
| `engineering_path`/`request_type` Enums + ORM-Binding | Top-Level-Enums in `domain/`, Migration auf `cases`. | M |
| PTFE-Tiefenmodell: `sealing_material_family`-Enum, Compound-Taxonomie, Failure-Mode-Enum, Risk-Dimensionen | Top-Level-Typen, referenziert aus Case-State und Risk-Engine. | L |

### 5.4 REMOVE (klar tot / veraltet)

| Pfad / Modul | Grund | Effort |
|---|---|---|
| `backend/app/_legacy_v2/state/`, `_legacy_v2/utils/`, `_legacy_v2/tests/` | Verzeichnisse enthalten nur `__pycache__`. Dead code. | XS |
| `backend/app/api/v1/endpoints/rag.py.bak` | Backup-Datei im Quellbaum. | XS |
| `backend/app/agent/agent/interaction_policy.py` | Re-Export-Shim mit "DO NOT add logic here"; nach Umhängen der Konsumenten entfernbar. | XS |
| Feature-Flag `SEALAI_ENABLE_BINARY_GATE` | Historisch Phase-F. | XS |
| Feature-Flag `SEALAI_ENABLE_CONVERSATION_RUNTIME` | Drei-Modi-Gate produktiv. | XS |
| Feature-Flag `ENABLE_LEGACY_V2_ENDPOINT` | Gehört zu einer der Alt-Routen, Abschaltung gemeinsam mit Endpoint-Refactor. | XS |
| LangSmith-Projektname `sealai-phase-h` | Veralteter Phasenname. | XS |
| `backend/app/services/fast_brain/router.py` | Bei Entscheidung gegen Fast-Brain-Stack (siehe `NEEDS_FOUNDER_INPUT #2`). | S |

### 5.5 Zusammenfassung nach Effort

- **XS-Removes:** 7 Artefakte — niedrige Hürde, hohe Signalwirkung für Aufräumen.
- **M-Adapts:** 5 Module — erhebliche Strukturfolge, aber lokal begrenzt.
- **L-Adapts + L-Replaces:** 5 Bereiche — zentrale Arbeit.
- **XL-Replaces:** 2 Blöcke — Persistenz-Kern und Services-Layer. Diese dominieren den Aufwand.

---

## 6. NEEDS_FOUNDER_INPUT (offene Entscheidungspunkte)

### NEEDS_FOUNDER_INPUT #1 — Umgang mit `case_state_snapshots` bei Einführung des Mutations-Event-Journals

**Frage:** Soll `case_state_snapshots` beibehalten werden (Revisionshistorie pro Schnappschuss) und parallel `mutation_events` eingeführt werden, oder ersetzt das Outbox/Mutation-Pattern die Snapshot-Tabelle?

**Abhängigkeiten:**
- Supplement v1 §34.3 verlangt `mutation_events` als Journal.
- `case_state_snapshots` hat eine abweichende Semantik (Zustandsbild vs. Mutation).
- Daten-Retention-Strategie (wie lange Revisionen behalten?) ist ungeklärt.

**Wirkung je Antwort:**
- *Behalten + ergänzen*: mehr Storage, doppelte Revision-Zählung → Konsistenzpflicht.
- *Ersetzen*: Migration von bestehenden Snapshots nach `mutation_events` nötig; Break-Risk.

---

### NEEDS_FOUNDER_INPUT #2 — Zukunft der Parallel-Stacks `services/langgraph/` und `services/fast_brain/`

**Frage:** Werden beide Stacks deprecated und der Haupt-`agent/`-Graph als kanonische Orchestrierung etabliert, oder bleibt einer davon als „Fast-Path" explizit erhalten (mit Reconciliation-Tests)?

**Abhängigkeiten:**
- Supplement v1 §33.10 verbietet unversöhnte Koexistenz.
- `services/langgraph/rules/*.yaml` enthält Regel-Content, der ins `risk_engine` wandern müsste.
- `services/fast_brain/router.py` ist klein — könnte rasch entfernt werden.

**Wirkung je Antwort:**
- *Beide deprecaten*: Endpoints müssen umziehen, Regeln nach `risk_engine`, Tests konsolidieren.
- *Fast-Path erhalten*: Reconciliation-Tests notwendig, Doppel-Wartung.

---

### NEEDS_FOUNDER_INPUT #3 — COI-Data-Firewall-Nachweis (Supplement v2 §43)

**Frage:** Besteht ein dokumentierter Nachweis, dass keine Founder-Employer-Proprietär-Daten (z. B. interne Material-Testdaten, nicht öffentliche TDS-Revisionen, nicht freigegebene Compound-Konventionen) in das SeaLAI-Corpus (Qdrant, KB-JSON, YAML-Regeln, Prompts) eingeflossen sind?

**Abhängigkeiten:**
- Supplement v2 §38.6 / §43: strikte Data-Firewall erforderlich.
- Audit erfordert Stichprobenprüfung der KB-JSONs (`SEALAI_KB_PTFE_factcards_gates_v1_3.json`, `SEALAI_KB_PTFE_compound_matrix_v1_3.json`), YAML-Regeln und Qdrant-Dokumente gegen Employer-Herkunft.

**Wirkung je Antwort:**
- *Nachweis vorhanden*: Festhalten als Dokument im Repo (`konzept/coi_firewall_log.md` o. ä.).
- *Nachweis fehlt*: Externe Audit-Aktion nötig, möglicherweise Content-Purge.

---

### NEEDS_FOUNDER_INPUT #4 — Priorisierung der Output-Klassen-Lücke `rca_hypothesis`

**Frage:** Wann muss `rca_hypothesis` produktiv sein? RCA als eigener Request-Type ist in AGENTS §5.1 und §15 als First-Class definiert, aber aktuell nicht implementiert. Soll RCA zum MVP-Scope (PTFE-RWDR-zentriert) gezogen werden oder explizit in Phase 2+ verschoben werden?

**Abhängigkeiten:**
- Base SSoT §15: RCA hat eigenes Symptom-Modell, Failure-Timing, Damage-Pattern.
- Engineering-Depth §7: PTFE-RWDR-Failure-Modes sind verfügbar — RCA-Content-seitig vorhanden.
- Kein Gate-/Routing-Support aktuell.

**Wirkung je Antwort:**
- *In MVP ziehen*: +L Effort für RCA-Pipeline.
- *Phase 2+*: Kommunikation in Supplement v2 §39.7-Strings, klares Degradieren auf `structured_clarification`.

---

### NEEDS_FOUNDER_INPUT #5 — Enum-Konsolidierung `RoutingPath`/`ResultForm` vs. SSoT

**Frage:** Werden `RoutingPath` und `ResultForm` als Interaction/Runtime-Sublayer eines zweistufigen Modells (Interaction-Routing → Engineering-Routing) beibehalten, oder sollen sie vollständig durch SSoT-Enums (`engineering_path`, `request_type`, 7 Output-Klassen) ersetzt werden?

**Abhängigkeiten:**
- AGENTS §5: SSoT-Enums sind bindend.
- `runtime/policy.py` wird von Gate-Logik konsumiert; Umstellung ist breit.

**Wirkung je Antwort:**
- *Sublayer behalten*: Klare Dokumentation nötig, Mapping-Tabelle zwischen Sublayer und SSoT.
- *Ersetzen*: größerer Refactor in `runtime/`, `api/v1/endpoints/`, Tests.

---

### NEEDS_FOUNDER_INPUT #6 — Tenant-ID-Backfill-Strategie

**Frage:** Bei Einführung von `tenant_id NOT NULL` auf `cases`: Welchen Default bekommen bestehende Cases im Live-System? Ein Dummy-Tenant, ein „legacy"-Tenant, Migration nach Handarbeit?

**Abhängigkeiten:**
- Supplement v1 §36.3.
- Laut Memory laufen bereits Cases via `session_id`.

**Wirkung je Antwort:**
- *Dummy-Tenant*: einfache Migration, aber Analytics-Verzerrung.
- *Hand-Migration*: aufwändig, aber sauber.

---

### NEEDS_FOUNDER_INPUT #7 — Norm-Module-Priorität

**Frage:** Welche Norm-Module werden in Phase 1a verbindlich als Code-Gates implementiert (AGENTS §13.1 nennt API 682, EN 12756, DIN 3760/ISO 6194, ISO 3601, VDI 2290, ATEX)? Alle oder nur PTFE-RWDR-relevante Teilmenge (DIN 3760 / ISO 6194)?

**Abhängigkeiten:**
- Base SSoT §13.2: Norm-Referenz ≠ Norm-Gate. Aktuell keine als Gate implementiert.
- PTFE-RWDR-MVP bevorzugt DIN 3760 / ISO 6194.

**Wirkung je Antwort:**
- *MVP-Subset*: weniger Aufwand, klare Priorisierung.
- *Vollständig*: XL-Effort, aber strukturelle Parität für Phase 2+.

---

## 7. Meta-Entscheidungen bewusst NICHT getroffen

Der Auditor trifft keine der folgenden Aussagen:

1. **Strangler-Fig vs. Selective-Rewrite vs. Greenfield** — Founder-Entscheidung. Die Klassifikation in §5 ist lediglich eine Befundmatrix.
2. **Reihenfolge der Arbeitspakete** — Auditor priorisiert Delta-Fläche technisch, aber ohne Business-Wichtung.
3. **Team-Setup / Personen / Kapazität** — außerhalb des Audit-Auftrags.
4. **Monetarisierungs-Druck** — Supplement v2 §42 ist gelesen, aber Gewichtung zwischen Tech-Schuld-Abbau und Feature-Delivery bleibt Founder-Entscheidung.
5. **Release-Fenster / Deadlines** — keine Zeitraum-Aussage.

---

## 8. Anhang

### 8.1 Gelesene Authority-Dokumente — Zusammenfassung des Lesetiefs

- Base SSoT: 32 Kapitel, vollständig gelesen. Fokuskapitel für diesen Audit: §7 (Phasen), §8 (Backend-SoT), §10 (Output-Klassen), §11 (Stale), §14 (Checks), §17 (Versionierung), §28 (API-Surface).
- Supplement v1: §33.1–§33.10 (LangGraph-Rolle), §34.1–§34.8 (Konsistenz/Mutation/Outbox), §35.1–§35.8 (Schema-Layer), §36.1–§36.5 (Persistenz) — vollständig gelesen.
- Supplement v2: §37–§43 plus Annex A/B — vollständig gelesen.
- Engineering-Depth: §3 Compound, §4 Lipgeometrie, §5 Welle, §6 Envelope, §7 Failure-Modes, §8 Risiken, §9 Checks — vollständig gelesen.
- CLAUDE.md v3.0 und AGENTS.md — vollständig gelesen, als Project Memory aktiv.

### 8.2 Code-Evidenz — konsolidierte Dateiliste

Read: `backend/app/models/case_record.py`, `case_state_snapshot.py`, `backend/app/agent/runtime/policy.py`, `backend/app/agent/agent/interaction_policy.py`, `backend/app/agent/graph/topology.py`, `backend/app/agent/graph/nodes/matching_node.py`, `output_contract_node.py`, `backend/app/agent/domain/checks_registry.py`, `readiness.py`, `requirement_class.py`, `backend/app/core/config.py`, `backend/app/agent/state/case_state.py` (Teilauszüge), `backend/alembic/versions/f2d9c4a8b6e1_add_cases_and_case_state_snapshots.py`.

Grep (Treffer/0-Treffer-Nachweise): `apply_mutation`, `MutationEvent`, `case_revision`, `outbox`, `OutboxEvent`, `GenericConcept`, `ProductTerm`, `ManufacturerProfile`, `ManufacturerCapabilityClaim`, `sealing_material_family`, `ptfe_virgin|ptfe_glass|ptfe_carbon|ptfe_bronze|ptfe_mos2`, `spiral_failure|lead_induced_pumping_leakage|creep_induced_contact_loss`, `risk.thermal|risk.pressure|risk.surface_speed|RiskEngine`, `compatibility_service|output_validator|formula_library|projection_service|phase_gate_service|routing_service|outbox_worker`, `engineering_path|EngineeringPath`, `rca_hypothesis|spare_part_identification|quick_engineering_check|validation_check`, `phase_gate|CONVERSATION|EXPLORATION|GOVERNED`, `sponsored|featured|promoted|boost`.

Directory-Listings: `backend/app/`, `backend/app/models/`, `backend/app/services/`, `backend/app/services/langgraph/`, `backend/app/services/langgraph/domains/`, `backend/app/services/langgraph/rules/`, `backend/app/services/fast_brain/`, `backend/app/agent/`, `backend/app/agent/graph/nodes/`, `backend/app/agent/domain/`, `backend/app/api/v1/`, `backend/app/api/v1/endpoints/`, `backend/app/_legacy_v2/`, `backend/alembic/versions/`.

### 8.3 Nicht vollständig abgeschlossene Evidenzpunkte (Transparenz)

- `case_state.py` (1644 Zeilen) wurde nur in Teilauszügen gelesen (Klassendefinitionen + Hilfsfunktionsnamen). Details der `build_case_state`-Implementierung (Zeile 835+) nicht eingesehen — für die Audit-Fragen nicht ausschlaggebend, aber für eine spätere Refactor-Spec relevant.
- `services/langgraph/domains/rwdr/` und `domains/hydraulics_rod/` wurden nur in der Baumstruktur betrachtet; Regel-YAMLs nicht vollständig gegen `checks_registry` mapped.
- `audit_log.py`-ORM wurde nicht gelesen, Tenant-ID-Status nur indirekt geschätzt.
- LangGraph-Import-Inventar auf Dateiebene wurde nicht vollständig für alle `services/`-Unterbäume durchgeführt; Stichproben bestätigen jedoch die Verletzung.
- Endpoint-Code (`endpoints/state.py`, `langgraph_v2.py`) wurde nicht im Detail gelesen — die §28-Analyse stützt sich auf Datei-/Routen-Namen.

Diese Lücken sind für die Audit-Kernaussagen ohne Folge, aber klar benannt.

### 8.4 Terminologie-Glossar (Kurzreferenz)

- **Moat-Layer 1/2/3**: Strukturelle Neutralität / Technische Translation / Request-Qualifikation (Supplement v2 §37).
- **Drei-Modi-Gate**: CONVERSATION / EXPLORATION / GOVERNED (CLAUDE §5.1).
- **Deep vs. Shallow MVP**: `rwdr + ptfe_*` full depth; alles andere strukturell aber flach (Supplement v2 §39).
- **Engineering-Path**: {ms_pump, rwdr, static, labyrinth, hyd_pneu, unclear_rotary} (AGENTS §5.2).
- **Request-Type**: {new_design, retrofit, rca_failure_analysis, validation_check, spare_part_identification, quick_engineering_check} (AGENTS §5.1).
- **Output-Klassen (7)**: conversational_answer, structured_clarification, governed_state_update, technical_preselection, rca_hypothesis, candidate_shortlist, inquiry_ready.
- **Provenance-Origins (6)**: user_stated, documented, web_hint, calculated, confirmed, missing.

### 8.5 Anti-Patterns-Checkliste (Supplement v2 §38) — Status-Scan

| Anti-Pattern | Status | Evidenz |
|---|---|---|
| Pay-for-Ranking | **Nicht erkennbar** | Grep 0 Treffer zu `sponsored/boost/promoted`. |
| Artificial Manufacturer Supply (Scraping) | **Nicht erkennbar** | Keine Scraping-Services im Backend; Hersteller-Stichprobe fehlt aber (`NEEDS_FOUNDER_INPUT #3`). |
| Hidden Founder-Employer-Priorität | **Nicht erkennbar** | Kein Employer-Flag im Code. |
| Employer-spezifische User-Werbung | **Nicht erkennbar** | Keine Marketing-Oberfläche im Backend. |
| LLM-derived Engineering Authority | **Niedrig risikobehaftet** | LLM-Aufrufe auf `intake_observe_node` beschränkt; Output-Contract deterministisch. |
| Marketing-Text-Matching / Regex-auf-Descriptions | **Nicht erkennbar** | `matching_node` operiert auf strukturierten Packages. |
| Silent Terminology Fallthrough | **MITTEL-HOCH RISIKO** | Keine Terminology-Registry → ad-hoc Hints in `matching_node.py`. |
| Founder-Employer-Matching-Bonus | **Nicht erkennbar** | Kein Bonus-Flag. |
| Monetarisierung an Produktkategorien gekoppelt | **Aktuell nicht erkennbar** | Keine Preis-/Kategorielogik im Backend. |

---

## 9. Nächste Schritte (Prozess, nicht Inhalt)

1. Genehmigung dieses Plans durch den Founder via ExitPlanMode.
2. Nach Genehmigung: Kopie des Inhalts nach `audits/phase_1a_backend_core_transition_plan_2026-04-17.md`.
3. Founder beantwortet die sieben `NEEDS_FOUNDER_INPUT`-Einträge.
4. Auf Basis der Antworten: separater Planungs-Request für die Transitionsstrategie (außerhalb dieses Audits).

---

**Ende des Audit-Reports.**
