# SEALAI MONOREPO AUDIT REPORT

## Executive Summary
Die SealAI Monorepo-Architektur befindet sich in einem funktionalen, aber noch inkonsistenten Übergangszustand zur v8 Ziel-Architektur. Das Backend nutzt ein modernstes LangGraph v2 Setup mit sauberen Checkpointern und exzellenten Guardrails (Combinatorial Chemistry Guard) vor dem LLM-Aufruf. Jedoch leidet die Supervisor-Logik unter einer starken Vermischung von veralteten RAG-Nodes und neuen Strukturen, während die geforderten 6 dedizierten Agenten nicht klar abgegrenzt sind. Das Frontend-Interface ist im Ansatz für Dual-Pane ausgelegt, jedoch existiert in der Live-Physik-Engine lediglich ein Berechnungsmodul anstelle der benötigten neun. Das Hybrid-Knowledge-Stack und die WORM-Evidence-Zertifizierung sind lobenswert etabliert, doch der kritische Hersteller-Layer und die Persona-Detection fehlen derzeit vollständig.

## 1. Ist-Zustand (Bestandsaufnahme)
- **Monorepo-Struktur**: Stark Backend-fokussiert (`backend/`, `frontend/`, `keycloak/`, `nginx/`). Es existieren Altlasten (`frontend_backup_20251120120347/`, `frontend_legacy_v2/`). Es fehlt ein dedizierter Workspace-Manager (wie pnpm workspaces oder Turborepo), Skripte arbeiten großteils mit `npm --prefix frontend`.
- **Tech-Stack Backend**: Python 3.11+, FastAPI (Async), LangGraph v2, OpenAI (`gpt-4.1-mini`, `gpt-5-large`), Redis (LangGraph Checkpointer & STM), PostgreSQL (Alembic Sync, Asyncpg Runtime), Qdrant (RAG).
- **Tech-Stack Frontend**: Next.js 16.0.10, React 18.2.0, TailwindCSS 3.4.1, NextAuth 5.0.0-beta.4, Framer Motion.
- **CI/CD**: GitHub Actions (Build & Push, Guardrails, CI, Deploy) sind eingerichtet.
- **Datenbankschemas**: Alembic SQL-Migrationen für `rag_documents`, `chat_transcripts`, `user_profiles` und `form_results` existieren. SQLAlchemy als ORM.
- **Agenten-Logik**: LangGraph v2 (`sealai_graph_v2.py`) fungiert als monolithischer Supervisor. Ein isolierter deterministischer `combinatorial_chemistry_guard.py` ist dem LLM-Routing optimal vorgeschaltet.
- **Memory**: Redis implementiert Short-Term Memory (Ring-Buffer in `conversation_memory.py`). PostgreSQL speichert den persistenten LangGraph-State.

## 2. Qualitäts-Assessment
### Was gut ist (Keep)
- **Safety Guard Layer**: Der deterministische `combinatorial_chemistry_guard.py` ist perfekt vor der LLM-Instanz positioniert und blockiert z. B. kritische FKM+Amin-Kombinationen.
- **WORM Evidence Bundle**: Die Implementierung in `worm_evidence_node.py` erzeugt saubere, per SHA-256 gesiegelte Immutable-Audits nach EU PLD Vorgaben.
- **LangGraph v2 Basis**: Die asynchrone State-Graph Architektur mit PostgreSQL-Checkpointern ist zukunftssicher.

### Was problematisch ist (Fix)
- **Frontend-Altlasten**: Parallele, unsauber getrennte Frontend-Verzeichnisse (`frontend/`, `frontend_backup`, `frontend_legacy_v2`) stören den Build-Prozess.
- **Agenten-Vermischung**: Die Supervisor-Logik in `sealai_graph_v2.py` ist stark aufgebläht (P1-P6 Nodes vs. Supervisor-Routing). Es gibt keine saubere Aufteilung in die 6 geforderten Spezialagenten.
- **RAG vs. Determinismus**: Es existieren erste Knoten für deterministische Factcard-Lookups, jedoch ist die Trennung zwischen freier Qdrant-Vektorsuche und strukturierten Normwerten in PostgreSQL nicht durchgehend erzwungen.

### Was fehlt (Build)
- **Calculation Engine Module**: 8 von 9 geforderten Berechnungsmodulen (wie Umlaufgeschwindigkeit, DIN-3770-Nutmaße etc.) fehlen. Aktuell ist nur die Flansch-/Gasket-Berechnung implementiert.
- **Hersteller-Layer**: Ein eigenständiges Dashboard für Hersteller und die Vorqualifizierungs-/Validierungspipelines fehlen komplett.
- **Persona Detection**: Keine Logik im Memory-System zur Einstufung des Nutzers (Einsteiger/Erfahrener/Entscheider).

## 3. Abgleich gegen SealAI v8

| Komponente | Ist-Zustand | Umbau-Aufwand | Priorität |
|---|---|---|---|
| Supervisor-Architektur | partial (Routing vorhanden, 6 Agenten unscharf) | L | P1 |
| Dual-Pane Interface | partial (LiveCalcTile für 1 Modul vorhanden) | M | P2 |
| Hybrid Knowledge Stack | partial (Ansätze für Qdrant/Postgres Trennung da) | L | P1 |
| Safety Guard Layer | vorhanden (Chemistry/Synonym Guard läuft VOR LLM) | S | P1 |
| Memory System | partial (Redis STM da, Rolling-Summary/Persona fehlt) | M | P2 |
| WorkingProfile v2.0 | partial (Felder da, 12-Turn Hard Limit lückenhaft) | M | P1 |
| Hersteller-Layer | fehlt komplett | XL | P2 |
| WORM Evidence Bundle | vorhanden (SHA-256 Implementierung etabliert) | S | P3 |

## 4. Kritische Lücken (was fehlt komplett)
1. **Saubere Kapselung der 6 Spezialagenten**: Die dedizierten Agenten (Medium, Seal Type, Material, Calculation, Compliance, Knowledge) müssen als modulare Nodes (in `backend/agents/`) ausgebaut und im Graph orchestriert werden.
2. **Deterministische Berechnung (8 von 9 Modulen)**: Die Berechnung der Umlaufgeschwindigkeit, DIN-3770-Nutmaße, Flächenpressung, Extrusionsspalt, Temp-Druck-Fenster, Beständigkeit, Materialvergleich und Auslegungs-PDF fehlen in der `app/mcp/` Toolchain und bedürfen einer Python-Entwicklung ohne LLM-Involvierung.
3. **Hersteller-Marketplace**: Das komplette UI und Backend für die Bereitstellung signierter Datenblätter und das Hersteller-Dashboard fehlen.
4. **Persona Detection & Rolling Summary**: Das bestehende Redis-Memory (in `conversation_memory.py`) besitzt noch keine Komprimierungslogik (ab Turn 6) und keine Erkennung für den Nutzertyp.

## 5. Umbauplan mit Phasen

### Phase 0 — Sofortige Bereinigung (vor allem anderen)
- Löschen der Legacy-Verzeichnisse (`frontend_legacy_v2/`, `frontend_backup_20251120120347/`, Unterordner aus `_trash/`).
- Setup eines echten Monorepo-Managements (pnpm workspaces oder Nx) zur Synchronisation von Scripts und Dependencies.
- Angleichung der `TechnicalParameters` (in `sealai_state.py`), um fehlende Felder analog zum `WorkingProfile` (in `rag/state.py`) zu erfassen.

### Phase 1 — Fundament (Was muss zuerst gebaut werden)
*Begründung: Erst wenn das dynamische Profil (WorkingProfile v2.0) und alle Berechnungs-Engines fehlerfrei deterministisch abrufbar sind, kann der Supervisor darauf fundiert operieren.*
- Implementierung des 12-Turn Hard Limits im Graph/Conversation Memory.
- Erstellung der 8 fehlenden Berechnungs-Stubs in `backend/app/mcp/` und schrittweise Ausprogrammierung.
- Verankerung des deterministischen Knowledge Coverage Checks (FULL/PARTIAL/LIMITED).

### Phase 2 — Kern (Supervisor + Agenten + Hybrid RAG)
- Modulares Refactoring von `sealai_graph_v2.py`: Extrahieren der Routing-Logik in 6 saubere Spezialagenten.
- Strikte Implementation des Hybrid Knowledge Stacks: Vektorsuchen in Qdrant (Schadensbilder etc.) und SQL-Lookups (Normtabellen) müssen exklusiv getrennt sein.
- Einbau des rollierenden Konversations-Summary und der Persona-Erkennung (Einsteiger/Erfahrener/Entscheider) in `conversation_memory.py`.

### Phase 3 — Interface (Dual-Pane + Live-Berechnung)
- Frontend-Ausbau von `LiveCalcTile.tsx` in `ChatInterface.tsx` zur iterativen Dual-Pane-Ansicht für alle 9 Berechnungsmodule.
- Real-Time Rendering der Berechnungsergebnisse synchron zum Chat-Verlauf.

### Phase 4 — Produktion (Hersteller-Layer + Evidence Bundle + Skalierung)
- Implementierung des Hersteller-Dashboards in Next.js (`frontend/src/app/manufacturer/`).
- Backend-Routen für vorqualifizierte Empfehlungen und Partner Marketplace.
- Performance-Tuning der WORM-Beweissicherung für Produktion.

## 6. Konkrete erste 10 Tasks (morgen früh anfangen)
1. Lösche `frontend_backup_20251120120347/` und `frontend_legacy_v2/` komplett.
2. Initialisiere `pnpm workspaces` (oder npm workspaces) im Monorepo-Root und verlinke `frontend` und `backend`.
3. Ergänze die fehlenden dynamischen Felder in `TechnicalParameters` (in `sealai_state.py`) synchron zum `WorkingProfile`.
4. Füge das 12-Turn Hard Limit in `conversation_memory.py` bzw. `_deterministic_termination_router` ein.
5. Lege Stub-Dateien für die 8 fehlenden Berechnungsmodule im Verzeichnis `backend/app/mcp/` an.
6. Implementiere das Berechnungsmodul "Umlaufgeschwindigkeit" in Python (rein deterministisch).
7. Implementiere das Berechnungsmodul "DIN-3770-Nutmaße" in Python (rein deterministisch).
8. Erweitere das UI in `LiveCalcTile.tsx`, um Platzhalter für die neuen Live-Berechnungsmetriken anzuzeigen.
9. Refactore `_deterministic_termination_router`, um den Knowledge Coverage Check strikt durchzusetzen.
10. Ergänze das `WorkingMemory` Schema in `sealai_state.py` um das Feld `user_persona`.