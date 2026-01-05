# Migration Plan - SealAI LangGraph 0.6.10

## ALT → NEU Zuordnung

### State
- **ALT:** Lokaler StateGraph mit messages, slots, etc.; Merge-Logik für Resume.
- **NEU:** Pydantic-State mit messages (append-only), slots (kleine primitive), routing (domains, primary_domain, confidence, coverage), context_refs (IDs/Meta), meta (thread_id, user_id, trace_id). Keine großen Artefakte.

### Prompts/Jinja2
- **ALT:** Prompts in prompts/ als .txt-Dateien; direkte String-Nutzung.
- **NEU:** Prompts als .md in backend/app/langgraph/prompts/; Jinja2-Renderer (utils/jinja_renderer.py) mit Variablen: user_query, messages_window, slots, context_refs, tool_results_brief, policy. Varianten über config/agents.yaml.

### Tools → ToolNode
- **ALT:** Tools wahrscheinlich direkt in Nodes aufgerufen.
- **NEU:** Tools in backend/app/langgraph/tools/ mit strikten I/O-Schemas; ToolNode in Subgraphs für parallele Ausführung, Fehler als ToolMessage. Caching über Redis (Key = hash(Input)).

### RAG → rag_select
- **ALT:** RAG-Orchestrator liefert Volltexte.
- **NEU:** rag_select liefert nur context_refs mit {kind:"rag", id, meta}; on-demand, Caching (TTL), Filter aus slots. Quellenauflösung im Exit.

### Memory → Redis-Checkpointer
- **ALT:** Lokaler Checkpointer-Protokoll.
- **NEU:** Redis-Checkpointer (RedisJSON/RediSearch); Namespaces: CHECKPOINTER_NAMESPACE_MAIN, optional pro Subgraph. HIL-Interrupt/Resume mit identischem thread_id.

### Supervisor/Resolver/Debate
- **ALT:** Keine Supervisor/Resolver; direkte Service-Aufrufe.
- **NEU:** Supervisor für Fan-out zu Domänen-Subgraphs; Resolver für deterministische Reduktion (Regeln: Normkonformität > Datenabdeckung > Tool-Evidenz > Confidence). Debate optional bei Unsicherheit (Limits: max. Runden, Kontext, Budget).

### Pfade respektieren
- Bestehende Pfade beibehalten (z.B. backend/app/services/rag/ als Basis für RAG); neue Struktur unter backend/app/langgraph/ ergänzen.
- Tools: Spiegelung nach backend/app/langgraph/tools/ mit Alias-Imports.
- Prompts: Verschieben nach backend/app/langgraph/prompts/, falls nötig, mit Symlinks.

### Feature-Flag
- ENABLE_LANGGRAPH_V06: Neue Pfade aktiv; Altpfade bleiben funktionsfähig bis Phase-2 abgeschlossen.