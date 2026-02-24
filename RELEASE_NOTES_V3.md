# Release Notes v3

## Release-Zusammenfassung

Dieses Release fokussiert auf drei Kernziele: **Sicherheit**, **Resilienz** und **Performance** der LangGraph-v2-basierten RAG-Pipeline.

## Highlights

- Sicherheitsfix für Tenant-Isolation im RAG-Lookup (`tenant_id`-Korrektur).
- Stabile Node-Contracts mit konsistentem `last_node` über relevante Graph-Pfade.
- Robuster LLM-Retry mit exponentiellem Backoff für transiente API-Fehler.
- 3-stufiges Retrieval-Fallback:
  - Tier 1: Hybrid (Qdrant + BM25 + Rerank)
  - Tier 2: BM25-Fallback bei Qdrant-Ausfall
  - Tier 3: Graceful Empty Result ohne Graph-Abbruch
- Redis-basierter RAG-Cache (TTL 1h) für wiederholte Queries.
- Deterministische Parallelisierung im Frontdoor-Pfad (`factcard_lookup` + `compound_filter`) mit anschließendem Merge.
- Qualitätsverbesserungen durch Unit- und Plausibilitätschecks (u. a. PTFE-Temperaturgrenzen).

## Technische Änderungen

### Phase 0: Kritische Fixes

- Tenant-Filter im Retrieval korrekt auf `state.tenant_id` gesetzt.
- Rückgabeverträge in mehreren Nodes vereinheitlicht (`last_node` ergänzt).
- Orchestrator-Update-Handling für `Command.update` stabilisiert.

### Phase 2: Resilience Patterns

- Retry-Strategie für LLM-Aufrufe (bis zu 3 Versuche, Backoff 2s -> 4s, max 10s).
- Explizite Behandlung von transienten Fehlern (`APIError`, `RateLimitError`, `APITimeoutError`).
- Strukturierte Telemetrie/Logs für Fallback-Stufen.

### Phase 3: Performance Optimization

- Cache-Layer im RAG-Node integriert (Read-before-Query, Write-after-success).
- Kennzeichnung der Retrieval-Methode via `rag_method` (`hybrid`, `bm25_fallback`, `failed_gracefully`, `cache_hit`).
- Fan-out/Fan-in-Optimierung im deterministischen Graph-Abschnitt.

### Phase 4: Quality Gates

- Konsistenzprüfung von Einheiten (z. B. bar/psi, C/F).
- Physikalische Plausibilitätschecks zur Reduktion riskanter Halluzinationen.

## Ergebnis

- Höhere Betriebssicherheit im Multi-Tenant-Kontext.
- Deutlich robustere Fehlerbehandlung unter API- und Infra-Störungen.
- Spürbar geringere Latenz durch Caching und Parallelisierung.
- Verbesserte fachliche Antwortqualität durch zusätzliche Guardrails.
