# SealAI LangGraph Audit – Radialwellendichtung Flow (IST)

## 1. Übersicht LangGraph-Architektur (IST)
- **State & Speicher**: `SealAIState` kapselt Nachrichten, Slots, Routing, Kontext-Referenzen und Meta-Infos (`backend/app/langgraph/state.py:1-43`). Slot-Validierung begrenzt Werte auf 1000 Zeichen, aber es existiert kein Feld für explizite Phasen oder Fortschritt.
- **Checkpointer**: `make_checkpointer` bevorzugt `MemorySaver` und aktiviert Redis nur, wenn `USE_REDIS_CHECKPOINTER` gesetzt ist; bei inkompatiblen redis-py-Versionen fällt ein `_NoopSaver` zurück (`backend/app/langgraph/utils/checkpointer.py:27-135`). Standardsystem speichert dadurch keine Zustände außerhalb des Arbeitsspeichers.
- **Graph-Orchestrierung**: `create_main_graph` baut einen linearen Pfad START → `entry_frontend` → `discovery_intake` → `intent_projector` → `context_retrieval` → `planner` → `specialists` → `challenger` → `quality_review` → `exit_response` → END (`backend/app/langgraph/compile.py:42-66`). Ein Supervisor wird hier nicht eingebunden, obwohl `nodes/supervisor_factory.py` einen Handoff-Agenten erzeugen kann.
- **Subgraphs**: Die Verzeichnisse `backend/app/langgraph/subgraphs/{debate,material,profil,recommendation,validierung}` sind aktuell leer; es existiert kein separierter Subgraph-Flow für die genannten Domänen.
- **LangGraph-Aufrufpfade**:
  - REST/SSE: `/api/v1/ai/langgraph/chat` und `/api/v1/ai/langgraph/chat/stream` benutzen `run_langgraph_stream` (`backend/app/api/v1/endpoints/ai.py:5-14`).
  - SSE-only: `/api/v1/langgraph/chat/stream` nutzt einen dedizierten Router (`backend/app/api/v1/endpoints/langgraph_sse.py:12-125`).
  - WebSocket: `/api/v1/ai/ws` streamt Events aus LangGraph, orchestriert Debug-/Consent-Handling und Persistenz (`backend/app/services/chat/ws_streaming.py:1-197`).

## 2. Discovery- / Intake-Phase (Bedarfsanalyse)
- **Vorhandene Nodes**:
  - `entry_frontend` spiegelt nur den Slot `user_query` als `HumanMessage` wider (`backend/app/langgraph/nodes/entry_frontend.py:6-17`).
  - `discovery_intake` ruft ausschließlich `validate_slots` auf – keine Parametrierung, keine Rückfragen (`backend/app/langgraph/nodes/discovery_intake.py:6-8`).
  - `intent_projector` setzt statische Defaults für Confidence/Coverage/Domains (z. B. Primary Domain immer „material“, `backend/app/langgraph/nodes/intent_projector.py:6-19`).
  - `planner_node` ruft einen generischen Planner-Agenten auf, der JSON-Pläne erzeugt, aber sich nicht speziell auf Radialwellendichtung-Bedarfsanalysen bezieht (`backend/app/langgraph/nodes/planner_node.py:33-67`).
- **Geeignetheit für RWD-Bedarfsanalyse**: Die Phase sammelt keine strukturierten Parameter (Maschine, Medium, Temperatur, Drehzahl, Druck, Geometrie, Oberflächen, Normen, Historie). Es existiert weder ein Fragenkatalog noch Persistenzfelder für diese Attribute; Confirm-/Intent-Gates würden nur Sinn machen, wenn `confirm_gate.py` und `resolver.py` in den Graph eingebunden wären – aktuell sind sie ungenutzt.
- **Fehlende Elemente**:
  - Kein Slot-Schema für RWD-spezifische Parameter.
  - Keine Heuristik zur Coverage-Ermittlung oder Rückfragen (Coverage-Werte sind fixe Defaults).
  - Keine Memory-Anbindung, um erfasste Antworten über mehrere Turn-Taking-Schritte hinweg zu nutzen (STM existiert, wird aber nicht gelesen).

## 3. Berechnungs-Agent (Calculator-Phase)
- **Vorhandene Artefakte**:
  - `langgraph/tools/material_calculator.py` bietet Funktionen zur Massen- und Verschnittberechnung, kann von Agenten über `create_domain_agent` gebunden werden (`backend/app/langgraph/tools/material_calculator.py:1-44`).
  - Weitere Berechnungen (Umfangsgeschwindigkeit, PV-Wert, Reibleistung) sind nicht implementiert; auch kein separater Node/Subgraph greift das Tool verpflichtend auf.
- **Fehlende Struktur**:
  - Es existiert keine Node-Kette, die nach der Discovery-Phase deterministisch Berechnungen ausführt. Der Material-Agent kann optional das Tool nutzen, aber es gibt keinen dedizierten „Berechnungs-Agent“-Abschnitt zwischen Discovery und Fachauswahl.
  - Slots enthalten keine Felder für berechnete Kennwerte; die Pipeline übergibt keine Parameter (z. B. Drehzahl) an Tools.
  - Kein Supervisor- oder Planner-Schritt erzwingt, dass Berechnungen abgeschlossen sind, bevor Fachagenten entscheiden.
- **Erforderliche Ergänzungen**: Ein eigener Node/Subgraph müsste Slots validieren/komplettieren, Berechnungen durchführen, Ergebnisse speichern (z. B. `slots["calc"]["pv"]`) und Success-Kriterien liefern, bevor `specialist_executor` läuft.

## 4. Fachagenten (Material, Profil, Validierung, Debate/Challenger)
- **Agent-Definitionen**: `agents.yaml` listet Domains für Planner, Profil, Validierung, Material, Standards, Challenger, Reviewer inkl. Modelle, Prompts und Tools (`backend/app/langgraph/config/agents.yaml:1-93`).
- **Orchestrierung**:
  - `specialist_executor` liest `slots["recommended_agents"]` aus dem Planner, ruft nacheinander Material/Profil/Standards/Validierung auf und aggregiert Antworten (`backend/app/langgraph/nodes/specialist_executor.py:37-96`).
  - `challenger_feedback` und `quality_review` wirken als nachgelagerte Checks (`backend/app/langgraph/nodes/challenger_feedback.py:32-67`, `backend/app/langgraph/nodes/quality_review.py:1-107`).
  - `supervisor_factory` kann einen Handoff-Supervisor erzeugen, ist aber nicht im Main Graph verdrahtet (`backend/app/langgraph/nodes/supervisor_factory.py:1-214`). Tests wie `test_supervisor_routing.py` referenzieren ihn trotzdem.
- **Trennung der Phasen**: Aktuell wechselt der Flow unmittelbar nach `planner_node` zu Fachagenten. Da Discovery keine Parameter persistiert und kein Berechnungs-Checkpoint existiert, können Fachagenten vorzeitig laufen. Subgraph-Strukturen (material/profil/validierung/debate) fehlen vollständig; alles findet innerhalb generischer Agenten statt.

## 5. State-Modell & Phasensteuerung
- **Felder**: `SealAIState` enthält `slots`, `routing`, `context_refs`, `meta`, aber kein `phase`- oder Statusfeld (`backend/app/langgraph/state.py:23-29`). `quality_review` schreibt `slots["quality_review"]` und aktualisiert Confidence in `routing`, doch dies erfolgt erst am Ende.
- **Fehlende Steuerung**:
  - Weder der Planner noch ein anderer Node markiert, ob Discovery abgeschlossen ist.
  - `intent_projector` setzt fixe Coverage-Werte (0.2) – es gibt keine Messung realer Abdeckung.
  - `confirm_gate.py` würde Coverage-basierte Nachfragen generieren, wird aber nicht aufgerufen.
  - Es gibt keine Persistenz von „Berechnung erfolgt“ oder Kennzahlen, die in späteren Phasen geprüft werden könnten.
- **Erforderliche Erweiterungen**: Einführung eines Phasenfelds (`slots["phase"]`), strukturierter Slots für alle Bedarfsanalyse-Parameter, Berechnungsergebnisse und Validierungsflags. Nutzung des bestehenden `confirm_gate`-Nodes würde helfen, wenn er in den Graph eingebettet würde.

## 6. Tests & Simulation des Flows
- **Vorhandene Tests**:
  - `test_singleflow_entry_to_exit.py` verifiziert, dass Supervisor und Main Graph kompilieren (`backend/app/langgraph/tests/test_singleflow_entry_to_exit.py:9-24`). Lauf mit `LANGGRAPH_USE_FAKE_LLM=1 OPENAI_API_KEY=dummy PYTHONPATH=backend pytest app/langgraph/tests/test_singleflow_entry_to_exit.py` → 2 Tests bestanden, Warnung zu `create_react_agent`.
  - `test_supervisor_routing.py` prüft Handoff-Tool-Namen (`backend/app/langgraph/tests/test_supervisor_routing.py`). Lauf mit gleicher Umgebung → 1 Test bestanden, gleiche LangGraph-Warnung.
  - Weitere Tests fokussieren State-Validation, Context-Retrieval, Offline-Simulation, Snapshot-Prompts, aber keiner modelliert den Dreischritt Discovery → Berechnung → Auswahl.
- **Lücken in Tests**: Es fehlen Szenarien, die
  - konkrete Parameter erfassen und validieren,
  - Berechnungen durchführen und Resultate weiterreichen,
  - sicherstellen, dass Fachagenten erst nach Abschluss dieser Schritte agieren.
  - Supervisor/Planner-Handoffs im Kontext einer RWD-spezifischen Pipeline abbilden.

## 7. Konkrete Feststellungen & Lücken für den RWD-Flow

### Bereits gut vorbereitet
- `context_retrieval` integriert Qdrant-RAG inkl. Quellenreferenzen und `slots["rag_sources"]` (`backend/app/langgraph/nodes/context_retrieval.py:19-77`).
- Material/Standards-Agenten können Tools nutzen; `material_calculator` erlaubt deterministische Berechnungen, falls der Agent die richtigen Parameter bekommt.
- Streaming-Anbindung (REST/SSE/WS) funktioniert stabil und kann zukünftige Phasen ohne größeren Infrastrukturaufwand bedienen.

### Vorhanden, aber anzupassen
- Discovery-Nodes existieren, erfassen aber keine Struktur. Sie müssten erweitert werden, um die komplette Parameterliste einer Radialwellendichtung abzufragen und in `slots` zu persistieren.
- `confirm_gate.py` und `resolver.py` liegen bereit, sind aber nicht in den Graphen eingebunden – eine Integration würde Coverage/Nachfrage-Mechanismen aktivieren.
- `supervisor_factory` könnte Handoffs zwischen Discovery-, Berechnungs- und Fachagenten steuern; dafür müsste `create_main_graph` angepasst und Worker/Subgraph-Definitionen ergänzt werden.
- `specialist_executor` nutzt Planner-Empfehlungen, sollte aber erst nach einem „Berechnungen abgeschlossen“-Flag starten.

### Fehlt noch komplett
- Ein dedizierter Berechnungs-Agent/Subgraph, der von den erfassten Parametern gespeist wird und technische Kennwerte (Umfangsgeschwindigkeit, PV-Wert, Reibleistung, Temperaturprofile) berechnet.
- Slot- und Schema-Definitionen für sämtliche RWD-Parameter sowie Berechnungsergebnisse.
- Phasenabhängige State-Steuerung inklusive Validierungslogik (z. B. `phase in {"bedarfsanalyse","berechnung","auswahl"}`).
- Subgraph-Dateien für material/profil/validierung/debate, um komplexere Workflows zu kapseln.
- Tests, die den gesamten Dreischritt simulieren und sicherstellen, dass Agenten nur mit vollständigen Daten arbeiten.

## Tests & Kommandos
- `LANGGRAPH_USE_FAKE_LLM=1 OPENAI_API_KEY=dummy PYTHONPATH=backend pytest app/langgraph/tests/test_singleflow_entry_to_exit.py`
- `LANGGRAPH_USE_FAKE_LLM=1 OPENAI_API_KEY=dummy PYTHONPATH=backend pytest app/langgraph/tests/test_supervisor_routing.py`

Beide Läufe waren erfolgreich (Warnungen bzgl. veralteter LangGraph-APIs). Weitere Tests wurden nicht angepasst.

## Kleine Code-Verbesserungen im Rahmen des Audits
- Keine Codeänderungen vorgenommen; Analyse rein dokumentarisch.

## Implementierungsstand RWD-Flow (update durch Codex)
- **Neue Strukturen**: `SealAIState` speichert jetzt `phase`, strukturierte `RwdRequirements`, Berechnungsergebnisse (`RwdCalcResults`) sowie eine `requirements_coverage`-Kennzahl.
- **Discovery-Phase**: `entry_frontend` initialisiert die Phase, `discovery_intake` harmonisiert/merged RWD-Anforderungen, `rwd_confirm_node` fasst die Angaben zusammen und steuert den Übergang in die Berechnungsphase.
- **Berechnungen**: `rwd_calculation_node` ermittelt Umfangsgeschwindigkeit, Druckdifferenz und PV-Wert und setzt die Phase auf „auswahl“, sobald genügend Daten vorliegen.
- **Fachagenten**: `specialist_executor` prüft jetzt, ob die Berechnungsphase abgeschlossen wurde, bevor Material-/Profil-/Validierungs-Agenten aktiv werden.
- **Graph-Flow**: Main-Graph-Reihenfolge wurde zu Discovery → Confirm → Berechnung → Planner → Specialists angeglichen; neue Tests (`test_rwd_flow.py`) überwachen den Phasenfortschritt.
- **TODOs**: Supervisor/Subgraph-Aufteilung, echte NLP-Extraktion der Anforderungen, erweiterte Berechnungen (Reibleistung, Temperaturprofile) sowie engeres Zusammenspiel mit Confirm-Gate/Memory sind noch offen.
