# Routing Overhaul Migration Notes

## Überblick
Diese Migration ersetzt sämtliche untypisierten Dict-Schnittstellen zwischen den LangGraph-Knoten durch eine einheitliche IO-Schicht auf Basis von gefrorenen Pydantic-Modellen (`backend/app/langgraph/io/*`). Der Graph `graph_chat.py` bildet die neue Referenzkette Discovery → Intent → Router → {Agents} → Synthese → Safety. Die SSE-API wurde von `app/api/v1/endpoints/langgraph_sse.py` nach `app/api/routes/chat.py` verschoben und validiert JWTs per Dependency.

## Auswirkungen
- **API**: `POST /chat/stream` (JWT-pflichtig) ersetzt den bisherigen SSE-Endpunkt. Request-Payload: `{chat_id, input_text, parameters[]}`; Response streamt `final` + `done` Events.
- **Graph**: Alle Kernknoten validieren nun Inputs/Outputs mit `frozen=True, extra="forbid"`. Legacy-Agenten werden über Adapter (`app/langgraph/agents/adapters.py`) angebunden; direkte Dict-Aufrufe sind nicht mehr zulässig.
- **Units**: Parameter werden zentral normalisiert (`normalize_bag`, °C→K, bar→Pa). Downstream-Code muss mit SI-Werten rechnen.
- **Observability**: Neue Telemetrie (`app/common/obs.py`) liefert strukturierte KPIs (Confidence, Coverage, Risk, RAG, Safety, Latenz). Logging-Konfiguration ggf. anpassen, damit `app.routing.telemetry` eingesammelt wird.
- **Benchmarks**: Routing-Benchmarks liegen unter `benchmarks/routing/*.yaml`. Runner `scripts/run_benchmarks.py` evaluiert Accuracy, RAG-Quote, First-Pass-Rate.

## To-do nach Merge
1. Makefile-Zeilenumbruch reparieren (Zeile 99) und CI-Jobs für `make test` / `make bench` aktivieren.
2. Legacy-Agenten schrittweise auf native Pydantic-Modelle migrieren (Adapter entfernen, sobald möglich).
3. Observability an bestehende Monitoring-Pipelines anbinden (z.B. OpenTelemetry, ELK).
4. Benchmarks regelmäßig in CI ausführen und Zielwerte kalibrieren (Accuracy ≥ 0.85, First-Pass ≥ 0.70, RAG-Quote reduziert).
