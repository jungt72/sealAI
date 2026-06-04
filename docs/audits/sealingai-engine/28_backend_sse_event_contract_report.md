# 28 Backend SSE Event Contract Report

Datum: 2026-05-27

## Ziel

Backend-SSE-Events sollen stabile Metadaten tragen, damit BFF und Frontend Streams eindeutig deduplizieren, finalisieren, unterbrechen und debuggen können.

## Aktueller SSE-Event-Pfad

1. Backend Entry:
   - `backend/app/agent/api/routes/chat.py` gibt `StreamingResponse(event_generator(...), media_type="text/event-stream")` zurück.
2. Backend Stream Dispatch:
   - `event_generator()` in `backend/app/agent/api/streaming.py` entscheidet nach Dispatch zwischen Fast Response, Knowledge Response, Light Runtime, Governed Graph und direkten Governed-Payloads.
3. Governed Stream:
   - `_stream_governed_graph()` sammelt Graph-Progress, baut finalen Payload nach Composer/Final Guard und sendet danach `state_update` plus `[DONE]`.
4. BFF:
   - `frontend/src/app/api/bff/agent/chat/stream/route.ts` liest Backend-SSE, filtert Legacy-Preview-Events und erzeugt aus `state_update` synthetische `answer.stream.start`/`answer.token`/`answer.done` Events plus finalen `state_update`.
5. Frontend:
   - `frontend/src/hooks/useAgentStream.ts` dedupliziert nach `event_id` oder `turn_id` + `sequence` und finalisiert nur nach finalem `state_update`.

## Neues Event-Schema

Backend-SSE-Payloads behalten ihr Legacy-`type`-Feld, enthalten aber zusätzlich:

```json
{
  "turn_id": "turn:<session_id>:<message_hash>",
  "event_id": "<turn_id>:<sequence>",
  "sequence": 1,
  "event_type": "delta|state_update|final|error|interrupted|done|metadata",
  "is_final": false,
  "error_code": null,
  "data": {}
}
```

Regeln:

- `turn_id` wird pro User-Turn aus `request.turn_id`/`request.request_id` übernommen, falls vorhanden, sonst deterministisch aus `session_id` + User Message abgeleitet.
- `sequence` zählt monoton pro `SSEEventBuilder`.
- `event_id` ist `<turn_id>:<sequence>`.
- Genau ein erfolgreicher finaler Event darf `is_final=true` setzen; ein zweiter finaler Event löst `sse_final_event_already_emitted` aus.
- `error`/`interrupted` setzen `error_code`, aber nicht `is_final=true`.
- Legacy-Felder bleiben top-level erhalten; zusätzlich enthält `data` die strukturierte Nutzlast für neue Consumer.
- `[DONE]` bleibt als SSE-Sentinel erhalten und wird nicht als erfolgreiche Assistant Message interpretiert.

## Implementierung

### Backend Builder

Neu: `backend/app/agent/api/sse_contract.py`

- `stable_turn_id(...)`: deterministische `turn_id`-Ableitung.
- `infer_event_type(...)`: Legacy-`type` nach Contract-`event_type`.
- `SSEEventBuilder.event(...)`: Metadaten + `data` ergänzen.
- `SSEEventBuilder.frame(...)`: JSON-SSE-Frame serialisieren.

Belege:

- Schema/Typen: `backend/app/agent/api/sse_contract.py:11`
- `turn_id`: `backend/app/agent/api/sse_contract.py:22`
- `event_id`/`sequence`/`is_final`: `backend/app/agent/api/sse_contract.py:86`

### Backend Streaming

Geändert in `backend/app/agent/api/streaming.py`:

- Graph-Progress wird über `SSEEventBuilder` als `event_type=metadata` gesendet: `streaming.py:153`.
- Fast Response und Knowledge Response senden finales `state_update` mit `is_final=true`: `streaming.py:323` und `streaming.py:367`.
- Light Runtime normalisiert `text_chunk` zu `event_type=delta`, `state_update` zu finalem `state_update`, `done` zu `done`, `error` zu `error`: `streaming.py:715`.
- Governed Graph sendet Progress-Metadaten und genau ein finales `state_update`: `streaming.py:861`.
- Direkte `event_generator()`-Pfade wie Guard, RFQ, Active Case Side/Process und blocked graph erhalten ebenfalls finale Contract-Metadaten: `streaming.py:1047`.

### BFF

`frontend/src/app/api/bff/agent/chat/stream/route.ts` reicht jetzt auch `event_type` zusammen mit vorhandenen `event_id`, `turn_id`, `sequence`, `is_final` und `error_code` weiter.

Beleg: `frontend/src/app/api/bff/agent/chat/stream/route.ts:311`.

## Geänderte Dateien

- `backend/app/agent/api/sse_contract.py`
- `backend/app/agent/api/streaming.py`
- `backend/app/agent/tests/test_sse_event_contract.py`
- `backend/app/agent/tests/test_governed_runtime_seam.py`
- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`
- `docs/audits/sealingai-engine/28_backend_sse_event_contract_report.md`

## Tests

Neue/erweiterte Tests:

- `test_sse_event_builder_adds_stable_turn_metadata_and_monotonic_sequence`
- `test_sse_event_builder_allows_exactly_one_successful_final_event`
- `test_sse_event_builder_error_event_contains_error_code_without_final_success`
- `test_fast_response_stream_emits_contract_metadata_once`
- Governed seam test erwartet nun Metadaten auf Progress und finalem State Update.
- BFF-Test erwartet Pass-through von `event_type`.

## Testbefehle und Ergebnisse

Ausgeführt:

```bash
pwd
git status --short
git branch --show-current
rg -n "yield|SSE|stream|event:|data:|state_update|delta|final|done|error|turn_id|event_id|sequence|is_final|StreamingResponse|text/event-stream" backend/app frontend/src
PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/agent/api/sse_contract.py backend/app/agent/api/streaming.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_sse_event_contract.py backend/app/agent/tests/test_governed_runtime_seam.py
npm --prefix frontend run test:run -- src/app/api/bff/agent/chat/stream/route.spec.ts src/hooks/useAgentStream.test.tsx
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/app/api/tests/test_rfq_endpoint.py
npm --prefix frontend run test:run -- src/app/api/bff/agent/chat/stream/route.spec.ts src/hooks/useAgentStream.test.tsx src/lib/streamWorkspace.test.ts src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rwdr_golden_cases.py
git diff --check
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

Grün:

- Python compile: passed.
- SSE focused backend: `14 passed`.
- Frontend Stream/BFF focused: `2 passed`, `34 passed`.
- Frontend requested focused suite: `4 passed`, `46 passed`.
- RWDR focused suite: `36 passed`.
- `git diff --check`: passed.

Rot:

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/app/api/tests/test_rfq_endpoint.py`
- Ergebnis: mehrere bestehende Dirty-State-/Architektur-Testfehler außerhalb des SSE-Contract-Patches, u. a. Normalize-Node-Parameteranzahl, Knowledge Debug Composer, Phase-F routing mocks, Turn Context und V92 Orchestrator. Die SSE-spezifischen neuen Tests sind grün.

Forbidden-Language-Scan:

- `469` bestehende Treffer in Guard-Tests, Fixture-Forbidden-Phrases, historischen Konzepten, Knowledge-Daten und internen Workflow-States.
- Kein neuer produktiver Freigabe-/Materialempfehlungs-/Herstellerempfehlungs-Pfad wurde eingeführt.

## Verbleibende Restlücken

- Der Backend-Contract ergänzt Metadaten auf Backend-SSE-Payloads. BFF-synthetische `answer.stream.start`/`answer.token`/`answer.done` Events werden weiterhin aus dem finalen `state_update` erzeugt und sind noch kein echter backend-originärer Delta-Contract.
- `[DONE]` bleibt als Legacy-Sentinel ohne JSON-Metadaten. Das ist kompatibel mit BFF/Frontend, aber kein vollständiges JSON-`done`-Event.
- `turn_id` ist deterministisch aus Session + Message, wenn kein expliziter Request-/Turn-ID existiert. Für wiederholte identische User Messages im selben Session-Kontext kann das kollidieren; der nächste Patch sollte eine explizite request/turn id aus der Route Boundary übernehmen.
- Die breite Backend-Suite ist wegen vorhandener Dirty-State-Fehler nicht grün; diese wurden nicht in diesem Patch repariert, um die SSE-Änderung klein zu halten.

## Nächste Empfehlung

Als nächster Patch sollte die BFF-Synthetik reduziert werden: Backend sollte optional selbst `answer.stream.start`/`answer.token`/`answer.done` mit Contract-Metadaten oder einen expliziten `final` Event liefern. Danach kann der BFF als dünner SSE-Proxy arbeiten und muss keine UI-Stream-Events mehr aus `state_update` ableiten.
