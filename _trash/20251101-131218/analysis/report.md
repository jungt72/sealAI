# Phase 0 - Routing Analyse

## Ist-Architektur
- `app/services/langgraph/graph` enthaelt mehrere StateGraph-basierte Flows (consult, supervisor, mvp) mit `TypedDict`-States wie `ConsultState` und `SupervisorState`, die dynamisch ueber dict-merges aktualisiert werden.
- Routing-Logik basiert auf heuristischen Scores (`app/services/langgraph/hybrid_routing.py`) sowie separaten LLM-basierten Klassifizierern; hart verdrahtete Schwellwerte und Synonymlisten.
- Parameteraufnahme und -ableitung erfolgt verteilt ueber Nodes (`consult/build.py`, `consult/nodes/*`) mit Alias-Mapping und manuellen Einheiten-Umrechnungen ohne zentrale Normalisierung.
- RAG wird breit eingesetzt (`hybrid_retrieve` in `graph/mvp_graph.py`, `consult/nodes/rag.py`) ohne harte Guard-Rails fuer Kosten oder Qualitaet; fallback Pfade greifen auf generische LLM-Antworten zurueck.
- SSE-Endpoint (`app/api/v1/endpoints/langgraph_sse.py`) orchestriert Graph-Aufrufe, Redis-Checkpointer und Streaming, aber Vertraege zwischen Nodes bleiben untypisiert.
- Observability beschraenkt sich auf Logging-Wrapper (`logging_utils.py`) und optionale LangSmith-Tracing Hooks, ohne metrische KPIs oder vertragliche Checks.
- Tests decken vor allem Prompt-Rendering ab (`app/services/langgraph/tests`); es fehlen Vertrags-, Routing- und End-to-End-Tests.

## Engpaesse
- Heterogene dict-Schnittstellen fuehren zu fragiler Kopplung; Validierungen fehlen, wodurch Still Errors erst spaet auffallen.
- Uneinheitliche Units (z.B. °C vs. K, bar vs. Pa) zwingen Nodes zu individuellen Alias-Maps und erschweren mathematische Checks.
- Routing-Entscheidungen besitzen keine standardisierte Metrik-Ausgabe; Confidence/Risk werden inkonsistent berechnet und nicht uebergeben.
- RAG-Aufrufe lassen sich nicht zentral drosseln oder auditieren, wodurch Kosten- und Latenzspruenge drohen.
- Fehlende Contract-Tests und Benchmark-Lineitems verhindern evidenzbasierte Regressionserkennung.
- Observability liefert keine zusammengefuehrten KPIs (Coverage, Risk, Safety), wodurch Prod-Insights fehlen.

## Umsetzung (Stand Routing-Overhaul)
- Einheitliche IO-Schicht mit `backend/app/langgraph/io/*` eingefuehrt; alle Kern-Nodes validieren Eingabe/Ausgabe strikt via frozen Pydantic-Modelle.
- Discovery→Intent→Router→Synthese→Safety-Kette als neuer Graph (`backend/app/langgraph/graph_chat.py`) verdrahtet; Legacy-Agents binden ueber Adapter `app/langgraph/agents/adapters.py` an.
- Einheitliche Unit-Normalisierung umgesetzt (`normalize_bag`), RoutingScores werden geklemmt und im Intent-Classifier genutzt.
- SSE-API auf `/chat/stream` migriert (`backend/app/api/routes/chat.py`) inkl. Redis-Checkpointer und JWT-Auth.
- Observability mit `backend/app/common/obs.py` eingefuehrt; KPI-Logging (Route, Scores, RAG, Safety, Latenz) vorhanden.
- Contract-/Smoke-Tests (`backend/tests/test_io_contracts.py`, `test_nodes_basic.py`, `test_synthese_safety.py`, `test_graph_smoke.py`, `test_obs_min.py`) sichern neue Sprache ab.
- Benchmarks vorbereitet (`benchmarks/routing/*.yaml`, `scripts/run_benchmarks.py`) – Ausfuehrung lokal erforderlich, da Makefile defekt.

## Restarbeiten / Follow-up
- Makefile reparieren (Tab an Zeile 99) und Benchmark/Test-Laeufe in CI verankern.
- Legacy-Agenten sukzessive auf native IO-Modelle migrieren, Adapter mittelfristig entfernen.
- Benchmarks automatisieren (CI-Job) und Zielwerte gegen Produktionsdaten kalibrieren.
- Observability an Metrik-Backend (z.B. OpenTelemetry) anbinden und Dashboards aufsetzen.
