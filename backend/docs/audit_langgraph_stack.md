# SealAI LangGraph/Stack Audit (IST, $(date -u +"%Y-%m-%d"))

## 1. Stack-Übersicht (IST-Zustand)

- **Container-Verbund**: Das Compose-File liefert das produktive Setup aus Postgres 15, Redis Stack 7.4, Qdrant 1.15, Keycloak (eigene Build), FastAPI-Backend (`sealai-backend:local`), Next.js-Frontend (GitHub Container Registry), Strapi-Backend und Nginx als Reverse Proxy (`docker-compose.yml:1-154`). Healthchecks und Abhängigkeiten sind für Datenbank, Redis, Qdrant und Keycloak hinterlegt.
- **Rollen**:
  - Backend (FastAPI + LangGraph) bedient REST, WebSockets und SSE auf Port 8000 und hängt an Redis/Qdrant/Postgres für State, RAG und Persistenz.
  - Frontend konsumiert Backend `/api/v1` sowie NextAuth gegen Keycloak; Strapi liefert CMS-Inhalte über `/admin` und `/api`.
  - Nginx terminiert TLS für `sealai.net` und `auth.sealai.net`, leitet `/api/v1/**`, `/api/v1/ai/ws`, `/api/v1/langgraph/**` und SSE speziell an das Backend und pflegt dedizierte Locations für Strapi und NextAuth (`nginx/default.conf`).
- **Backend-Libraries (fix laut `backend/requirements.txt`)**: FastAPI 0.120.x, Uvicorn 0.38, Pydantic 2.12, OpenAI SDK 2.3.0, LangChain 1.0.x, LangGraph 1.0.x inkl. Prebuilt, Supervisor und Redis-Checkpoint, SQLAlchemy 2.0.44 + AsyncPG, Qdrant-Client 1.15.1, Redis 6.4.0, structlog 24.2.0 sowie pytest/pytest-asyncio.
- **Telemetry & Observability**: `configure_telemetry` aktiviert LangSmith-Tracing und – falls OTEL installiert – FastAPI/Requests/Redis-Instrumentierung (`backend/app/common/telemetry.py`).

## 2. Backend-Architektur & API-Status

- **App-Boilerplate**: `backend/app/main.py` erstellt eine FastAPI-App mit CORS/GZip, verdrahtet `api_router` unter `/api/v1`, Healthchecks sowie den Chat-WebSocket Router (auch gespiegelt auf `/api/v1` und `/api/v1/ai`).
- **Routing-Layer**: `backend/app/api/v1/api.py` bündelt die Version-1-Endpunkte:
  - `ai.py` stellt `/api/v1/ai/langgraph/chat` (REST) und `/api/v1/ai/langgraph/chat/stream` (SSE) bereit und reicht Requests direkt an `run_langgraph_stream`.
  - `langgraph_sse.py` bietet GET `/api/v1/langgraph/chat/stream` für SSE-Polling mit manuellen Token-/Tool-Events.
  - `consult_invoke.py` und `system.py` spiegeln Test-/Legacy-Routen (`/api/v1/test/consult/invoke`, `/api/v1/system/test/consult/invoke`), indem sie Request-Payloads in `request.state.langgraph_payload` setzen und denselben LangGraph-Helper nutzen.
  - `memory.py` ist das produktive LTM-Interface mit POST/GET/DELETE gegen Qdrant (Consent-Pflicht, `backend/app/api/v1/endpoints/memory.py`).
  - `rfq.py` belässt RFQ-Downloads beim Filesystem (direktes `FileResponse`, keine Strapi-Anbindung).
  - `auth.py` liefert einen Keycloak-Redirect, `users.py` nur Health-Ping.
- **Realtime-Kanal**: `backend/app/api/routes/chat.py` öffnet `/ws` (und via Routing auch `/api/v1/ws` / `/api/v1/ai/ws`). Der Handler erzwingt Token (wenn `WS_AUTH_OPTIONAL=0`), validiert Consent/Input, führt Ratelimiting via Redis (`token_bucket_allow`) und streamt Graph-Events über `services/chat/ws_streaming.py`. Die WebSocket-Pipeline unterstützt Debug-Events, PII-Gates und persistiert Ergebnisse nur bei erteiltem Consent.
- **Status**: REST/SSE/WS-Pfade sind produktionsreif (komplette Fehlerbehandlung, Rate Limits, Telemetrie). Die Test-Routen (`/test/consult/invoke`) wirken experimentell/legacy und sollten nicht öffentlich bleiben.

## 3. LangGraph-Implementierung

- **State-Modell**: `SealAIState` ist ein `TypedDict` mit `messages`, `slots`, `routing`, `context_refs` und `meta`, ausgestattet mit `add_messages`-Semantik und Slot-Validierung gegen Ausreißer (`backend/app/langgraph/state.py`).
- **Graph/Streaming**: `create_main_graph` baut einen linearen Pfad (Entry → Discovery → Intent Projector → Context Retrieval → Planner → Specialist Executor → Challenger → Quality Review → Exit) und cached die Kompilierung (`backend/app/langgraph/compile.py:42-85`). `run_langgraph_stream` kapselt SSE/REST-Antworten inklusive Fallback, thread-config (`checkpoint_ns`) und Streaming über `astream_events`.
- **Checkpointer**: `make_checkpointer` bevorzugt MemorySaver und aktiviert Redis nur, wenn `USE_REDIS_CHECKPOINTER` gesetzt ist; Fallbacks stellen sicher, dass fehlende Redis-Features den Graph nicht blockieren (`backend/app/langgraph/utils/checkpointer.py:27-135`). In PROD läuft somit Memory-Saver, sofern Redis explizit nicht aktiviert wurde.
- **Nodes**:
  - `entry_frontend`, `discovery_intake`, `intent_projector` sind noch Heuristiken (Slots spiegeln, Defaults setzen) ohne echte NLP/slot-filling Logik.
  - `context_retrieval` ruft `services.rag.hybrid_retrieve` auf, hängt RAG-Kontext als `SystemMessage` an und pflegt `context_refs`/`slots`.
  - `planner_node`, `specialist_executor`, `challenger_feedback`, `quality_review` und `exit_response` orchestrieren Domain-Agenten aus `nodes.members` plus Offlinestubs aus `agents.yaml`. `specialist_executor` ruft die empfohlenen Agenten sequentiell auf, loggt Routing-Metriken und baut eine Sammelantwort.
  - `nodes/supervisor_factory.py` implementiert einen Handoff-Supervisor (inkl. Offline-Heuristik und Tooling), wird jedoch im aktuellen `create_main_graph` nicht referenziert – Supervisor-basierter Flow ist vorbereitet, aber nicht angeschlossen.
  - Weitere Nodes wie `confirm_gate.py` und `resolver.py` sind vorhanden, aber ebenfalls nicht im Graph verkabelt.
- **Subgraphs**: Die Verzeichnisse `langgraph/subgraphs/{debate,material,profil,recommendation,validierung}` enthalten keine Module – Subgraph-Dekomposition ist nur vorbereitet.
- **Agents & Tools**: `config/agents.yaml` beschreibt Planner/Profil/Material/Standards/Validierung/Challenger/Reviewer inkl. Modelle, Prompts und Tool-Referenzen (`backend/app/langgraph/config/agents.yaml`). `nodes/members.py` lädt diese Definitionen, resolved Tools unter `langgraph/tools` (Materialrechner, Standards-Lookup) und bietet Offline-Stubs, falls `OPENAI_API_KEY` fehlt.
- **Streaming-API**: Neben REST (`run_langgraph_stream`) existiert ein dedizierter SSE-Router (`langgraph_sse.py`) und der WebSocket-Streamer (`services/chat/ws_streaming.py`) mit Event-V1-Unterstützung, Debugging, Persistenz-Hooks und Fallback-Texten.
- **Bewertung**:
  - **Voll implementiert**: State-Verwaltung, SSE/WS-Streaming, Heuristischer Multi-Agent-Loop (Planner → Specialists → Challenger → Reviewer), RAG-Einbindung, Tools (Material/Standards), Consent/Persistenz.
  - **Teilweise**: Discovery/Intent/Planner liefern hauptsächlich Defaults, Supervisor/Handoff-Mechanik ist nur vorbereitet, Redis-Checkpointing ist optional und standardmäßig deaktiviert, Subgraph-Ordner leer.
  - **Stub**: Confirm-Gate, Resolver, Debate-/Material-/Profil-Subgraphs (keine Dateien), kein echter Multi-Agent-Supervisor im Laufzeitgraphen.

## 4. Memory, RAG & Tools

- **Redis Memory**: `services/memory/conversation_memory.py` implementiert einen STM-Ringpuffer pro Chat (Redis-Listen mit TTL) plus Agent-Hints (`set_last_agent`). Wird in der aktuellen Graph-Pipeline noch nicht zurückgelesen, dient aber WS-Layern/Analytics.
- **Long-Term Memory (Qdrant)**: `memory_core.py` verwaltet eine dedizierte LTM-Collection (`<main_collection>-ltm`), stellt Export/Delete-Funktionen bereit und wird über die REST-API mit Consent abgesichert.
- **RAG**: `services/rag/rag_orchestrator.py` nutzt SentenceTransformer + CrossEncoder für Hybrid Retrieval gegen Qdrant via `httpx`, optional BM25 über Redis und External-Fallbacks per `AGENT_*_URL`. `context_retrieval` ist aktuell die einzige Graph-Stelle, die `hybrid_retrieve` nutzt.
- **Ingestion**: `services/rag/rag_ingest.py` bietet CLI-gestütztes Befüllen der Qdrant-Collection.
- **Tools**: `langgraph/tools/material_calculator.py` (Masse & Verschnitt) und `standards_lookup.py` (deterministischer Norm-Lookup) werden über `agents.yaml` in Material/Standards-Agenten gebunden.
- **Bewertung**: Redis/Qdrant-Integration ist produktiv nutzbar; Memory-Persistenz erfordert Consent-Flags und hat Safeguards. RAG greift ausschließlich via HTTP-API auf Qdrant zu (kein qdrant-client im Retrieval-Path), d. h. Netzwerkausfälle werden lediglich mit Logging/Empty-Results behandelt.

## 5. Authentifizierung & Integration

- **Keycloak**: JWT-Verifikation erfolgt doppelt – `app/services/auth/token.py` stellt `verify_access_token` (RS256, JWKS-Cache, Audience-Check) für HTTP/WS-Dependencies bereit, während `api/v1/dependencies/auth.py` Token für WebSockets auch aus Query-Params/Subprotokollen extrahiert.
- **NextAuth**: `/api/v1/auth/login` baut den Redirect gegen `settings.keycloak_issuer` und NextAuth-Callback (`backend/app/api/v1/endpoints/auth.py`).
- **Frontend/Backend-Brücke**: Nginx-Routing stellt sicher, dass WebSocket/SSE-Upgrade-Header an das Backend weitergegeben werden (`nginx/default.conf`), NextAuth-Aufrufe zum Frontend laufen separat.
- **Strapi**: Wird ausschließlich über Nginx proxied und besitzt eine eigene DB-Schema-Init; im Backend existiert keine direkte Strapi- oder CMS-Integration – Inhalte werden direkt vom Frontend geholt.
- **Weitere Schnittstellen**: RFQ-Downloads lesen Dateien lokal, Memory-API steuert Qdrant, RAG ruft Qdrant/optionale Agent-Microservices. Eine explizite Verbindung zu Strapi-Content, Keycloak-Groups o. Ä. ist nicht implementiert.

## 6. Tests & Qualitätssicherung

- **Testlauf**: `LANGGRAPH_USE_FAKE_LLM=1 OPENAI_API_KEY=dummy PYTHONPATH=backend pytest backend/app/langgraph/tests` → 9 Tests bestanden, 1 übersprungen, 1 Snapshot-Fehler.
  - Fehler: `test_supervisor_prompt_snapshot` erwartet noch das alte Supervisor-Prompt-Template; `agents.yaml` enthält bereits den erweiterten MAI-DxO-Text, Snapshot (`__snapshots__/supervisor_prompt.md`) ist veraltet.
- **Abdeckung laut Modulen**:
  - `test_state.py` prüft State/Slot-Validation.
  - `test_context_retrieval.py` und `test_resolver_determinism.py` sichern deterministische Antworten/RAG-Einbindung.
  - `test_singleflow_entry_to_exit.py`, `test_supervisor_handoff.py`, `test_supervisor_routing.py`, `test_offline_sim.py` simulieren Graph-Flows/Supervisor-Handoffs inkl. Offline-Modus.
  - `test_prompts_snapshot.py` schützt die agents.yaml-Prompts.
  - `test_config.py` validiert den YAML-Loader.
- **Gaps**: Keine End-to-End-Tests für REST-/WS-Schnittstellen, kein automatisiertes Persistenz-/Memory- oder Strapi-Keycloak-Nginx-Integrationstest. Snapshot-Drift blockiert CI, bis die Referenzdatei aktualisiert oder der Prompt stabilisiert wird.

## 7. Konkrete Feststellungen & Lücken

- **Implementiert & produktionsnah**
  - FastAPI-App, API-Router und WebSocket/SSE-Streaming inkl. Auth, Consent, Rate Limits und Telemetrie (`backend/app/main.py`, `backend/app/api/routes/chat.py`).
  - LangGraph-Pipeline mit Planner/Specialist/Challenger/Reviewer, RAG-Kontextanreicherung und Tool-Anbindung (`backend/app/langgraph/compile.py`, `nodes/*.py`, `langgraph/tools/*.py`).
  - Redis-basierte STM und Qdrant-basierte LTM mit REST-API und Consent-Governance (`backend/app/services/memory/*`, `backend/app/api/v1/endpoints/memory.py`).
  - RAG-Orchestrator (Embeddings, Reranker, HTTP-Fallbacks) + CLI-Ingest (`backend/app/services/rag/rag_orchestrator.py`, `rag_ingest.py`).
  - Keycloak-Integration (JWT-Verifikation, Redirects) und Nginx Reverse-Proxy-Setup für Backend/Frontend/Strapi (`backend/app/services/auth/token.py`, `nginx/default.conf`).

- **Teilweise implementiert / experimentell**
  - Discovery/Intent-Projektion sind Platzhalter (nur Slot-Validation/Defaults, keine echte Intent- oder Parameter-Extraktion).
  - Redis-Checkpointer ist optional und standardmäßig deaktiviert; Persistenz hängt von `USE_REDIS_CHECKPOINTER`.
  - Supervisor-/Handoff-Orchestrierung existiert, wird aber nicht im Main Graph genutzt; Subgraph-Verzeichnisse sind leer.
  - Memory-STM wird bislang nicht zurück in LangGraph gespeist; Persistenz (`persist_chat_result`) setzt auf Async-Jobs ohne Garantien.
  - Test-Routen (`/api/v1/test/...`) und SSE-Endpunkt arbeiten im Parallelbetrieb zur offiziellen AI-Route – mögliche Redundanz.

- **Nur vorbereitet / Stub**
  - `langgraph/subgraphs/(debate|material|profil|recommendation|validierung)` enthalten keine Dateien – Subgraph-Bibliothek fehlt.
  - `nodes/confirm_gate.py`, `nodes/resolver.py` werden im Graph nicht aufgerufen.
  - Strapi-Anbindung im Backend fehlt vollständig; alle CMS-Kontakte laufen außerhalb.
  - Snapshot-Dateien (Supervisor-Prompt) spiegeln nicht mehr den aktuellen agents.yaml-Inhalt; QA-Status ist blockiert, bis aktualisiert.

### Empfehlungen (keine Umsetzung erfolgt)

1. Snapshot/CI reparieren (`test_prompts_snapshot.py`) und – falls gewünscht – Quicktest-Docs anpassen.
2. Entscheiden, ob der vorbereitete Supervisor/Handoff-Fluss produktiv gehen soll; ansonsten ungenutzte Nodes/Subgraphs entfernen oder konsistent aktivieren.
3. Discovery/Intent/Missing-Parameter-Logik konkretisieren (z. B. Confirm-Gate einhängen) und Memory-STM im Graph berücksichtigen.
4. Dokumentieren, wie Strapi-Daten heute in den Beratungsflow gelangen (derzeit keine Backend-Verknüpfung) und ob Qdrant-LTM mit Frontend abgestimmt ist.
