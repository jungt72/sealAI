# Baseline Report - SealAI

## Laufpfad (User-Input → Response)
1. User-Input über API/WebSocket.
2. Routing über Services (z.B. Chat-Service).
3. Aufruf von RAG-Orchestrator für Retrieval.
4. Streaming-Response über WS (Stub für LangGraph).
5. Kein aktueller Graph-Flow; direkte Service-Aufrufe.

## Token/Latency-Schätzung
- Tokens: Abhängig von Query; RAG-Retrieval ~6-12 Dokumente.
- Latency: Embedding ~100-500ms, Retrieval ~200ms, Rerank ~100ms; Gesamt ~1-2s pro Query.

## Bestehender Teststatus
- Tests vorhanden: test_consult_e2e.py, test_api_langgraph.py, test_supervisor_router.py, etc.
- Status: Wahrscheinlich grün, da LangGraph entfernt, aber Services aktiv.
- Smoke-Tests: e2e_test.py in backend.