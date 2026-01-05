# Phase 6 — Contract Tests hinzugefügt

Ziel: Contracts (Graph/Prompts/SSE/Tools) gegen Drift absichern, **ohne** externe Netzwerkzugriffe (kein OpenAI/Qdrant/Redis erforderlich).

## Tests

- `backend/tests/contract/test_graph_compile_contract.py`
  - Graph v2 kompiliert mit `MemorySaver` und registriert die erwarteten Node‑IDs.

- `backend/tests/contract/test_prompt_render_contract.py`
  - Rendert die im Prompt‑Audit gelisteten Templates über den v2 Jinja‑Renderer (`StrictUndefined`) mit Dummy‑Kontext.
  - Assertet wichtige Marker (z.B. `TL;DR:`) zur Format‑Stabilität.

- `backend/tests/contract/test_sse_contract.py`
  - Testet `_event_stream_v2` direkt (kein HTTP), mit Dummy‑Graph/`astream_events` + `aget_state`.
  - Assertet `done` genau einmal und als letztes Event; Error‑Fall endet deterministisch.
  - Assertet außerdem, dass Parameter‑Deltas **nicht doppelt** emittiert werden (keine parallelen `parameter_update` + `state_update` Parameter‑Slices).

- `backend/tests/contract/test_tool_contracts.py`
  - `set_parameters` liefert `{"parameters": TechnicalParameters}` und merged Werte korrekt.
  - `search_knowledge_base` formatiert Hits; Error‑Fall liefert user‑sichtbaren Fehlertext (hybrid_retrieve gemockt).

## Ausführen

```bash
cd backend
pytest -q tests/contract
pytest -q tests/contract -k sse
pytest -q tests/quality
```

## Environment

- `OPENAI_API_KEY` wird in Tests auf `dummy` gesetzt, damit die Graph‑Kompilierung (ChatOpenAI init) nicht scheitert.
