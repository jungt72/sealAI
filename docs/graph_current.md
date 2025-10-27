# Ist-Graph Dokumentation - SealAI

## Nodes, Edges, Subgraphs, State-Felder, Tool-Aufrufe, RAG-Nutzung, Streaming/HIL

### Nodes
- **Lokaler StateGraph** (langgraph/graph.py): Implementiert einen simplen StateGraph mit Checkpointer-Unterstützung. Nodes sind callable oder haben invoke-Methode.
- **RAG-Orchestrator** (backend/app/services/rag/rag_orchestrator.py): Handhabt Embedding, Retrieval, Reranking von Qdrant.
- **Chat-Streaming** (backend/app/services/chat/ws_streaming.py): Stellt Streaming über WebSockets bereit, aber LangGraph-Integration entfernt.
- **Memory-Service** (backend/app/services/memory/): Wahrscheinlich für Speicherung.
- **Auth-Service** (backend/app/services/auth/): Authentifizierung.

### Edges
- Im lokalen Graph: Definierte Edges und Conditional Edges basierend auf State.
- Keine expliziten Edges in Services, da direkt aufgerufen.

### Subgraphs
- Keine definierten Subgraphs im aktuellen Setup.

### State-Felder
- Im Graph: messages, slots, routing, context_refs, meta (aus Kommentaren und Merge-Logik).
- Keine strenge Validierung.

### Tool-Aufrufe
- Nicht direkt sichtbar; wahrscheinlich in Nodes integriert.

### RAG-Nutzung
- On-Demand über rag_orchestrator; liefert Volltexte, nicht IDs.

### Streaming/HIL
- Streaming über WS; kein HIL-Interrupt implementiert.

### Tabelle Komponente | Beschreibung | Abhängigkeiten | Status
| Komponente | Beschreibung | Abhängigkeiten | Status |
|------------|--------------|----------------|--------|
| StateGraph | Lokale Graph-Implementierung | constants.py | Aktiv |
| RAG-Orchestrator | Retrieval-Augmented Generation | Qdrant, Redis (optional BM25), SentenceTransformers | Aktiv |
| Chat-Streaming | WebSocket-Streaming | ws_commons.py | Stub nach LangGraph-Entfernung |
| Memory | Speicher-Service | - | Aktiv |
| Auth | Authentifizierung | - | Aktiv |