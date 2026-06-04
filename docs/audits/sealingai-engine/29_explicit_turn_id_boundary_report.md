# 29 Explicit Turn ID Boundary Report

Datum: 2026-05-27

## Ziel

Jede gesendete User Message bekommt vor dem Backend-Streaming eine eindeutige
`turn_id`. Diese ID bleibt fuer alle sichtbaren Events dieses Turns stabil und
darf nicht mehr deterministisch aus `session_id` plus User-Text abgeleitet
werden.

## Aktueller turn_id-Pfad vor dem Patch

- Backend-SSE wurde zentral ueber `SSEEventBuilder` aufgebaut:
  `backend/app/agent/api/sse_contract.py`.
- `SSEEventBuilder.for_request()` las `request.turn_id` oder `request.request_id`,
  fiel aber ohne explizite ID auf eine deterministische Ableitung aus
  `session_id` und `message` zurueck.
- Der Backend-Stream startete mit `event_builder = SSEEventBuilder.for_request(request)`
  in `backend/app/agent/api/streaming.py`.
- Die BFF-Route leitete vorhandene Backend-Metadaten weiter, erzeugte aber bisher
  keine stabile Turn-ID an der Boundary.
- Der Frontend-Hook hatte Dedupe nach `event_id` beziehungsweise
  `turn_id + sequence`, sendete aber noch keine eigene `turnId`.

Risiko: Zwei identische User Messages in derselben Session konnten dieselbe
Fallback-`turn_id` erhalten.

## Neuer turn_id-Erzeugungspunkt

Primaerer Erzeugungspunkt ist jetzt der Frontend-Sendepunkt:

- `frontend/src/hooks/useAgentStream.ts:220` erzeugt eine Client-Turn-ID mit
  `crypto.randomUUID()` pro `sendMessage`.
- `frontend/src/hooks/useAgentStream.ts:450` erzeugt die ID unmittelbar vor dem
  Streamstart.
- `frontend/src/hooks/useAgentStream.ts:470` sendet `turnId` im BFF-Request.

Zweiter Boundary-Fallback fuer Legacy-Clients:

- `frontend/src/app/api/bff/agent/chat/stream/route.ts:336` uebernimmt
  `turnId`/`turn_id` oder erzeugt per `randomUUID()` eine neue ID.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:360` sendet
  `turn_id` an das Backend.
- Bei Start-401/Force-Refresh wird dieselbe `turn_id` fuer den einmaligen Retry
  wiederverwendet.

Backend-Fallback:

- `backend/app/agent/api/sse_contract.py:25` uebernimmt eine validierte explizite
  `turn_id`.
- Ohne valide explizite ID erzeugt der Backend-Builder jetzt `turn:<uuid>`.
- Der Fallback verwendet weder User-Text noch `session_id`.

## Durchreichung Backend / BFF / Frontend

Backend:

- `backend/app/agent/api/models.py:243` erweitert `ChatRequest` um
  `turn_id: Optional[str]`.
- `backend/app/agent/api/sse_contract.py:77` uebernimmt die Request-ID in
  `SSEEventBuilder.for_request()`.
- `backend/app/agent/api/sse_contract.py:103` baut weiterhin
  `event_id = <turn_id>:<sequence>` und erhoeht `sequence` monoton.

BFF:

- `frontend/src/app/api/bff/agent/chat/stream/route.ts:312` fuegt fehlende
  Backend-Metadaten mit der aktiven `turn_id` zusammen.
- Synthetische BFF-Events fuer `answer.stream.start`, `answer.token`,
  `answer.done`, `case_bound`, `error` und `interrupted` erhalten dieselbe
  Turn-ID, sofern das Backend keine eigene Metadaten liefert.
- Backend-originierte `turn_id`, `event_id`, `sequence`, `event_type`,
  `is_final` und `error_code` bleiben unveraendert.

Frontend:

- `frontend/src/lib/contracts/agent.ts:3` erlaubt `turnId` im
  `AgentStreamRequest`.
- `frontend/src/hooks/useAgentStream.ts:301` haelt die aktive Turn-ID.
- `frontend/src/hooks/useAgentStream.ts:526` ignoriert JSON-Events mit fremder
  `turn_id` fuer den aktuellen Stream.
- Bestehende Dedupe-Logik nach `event_id` beziehungsweise `turn_id + sequence`
  bleibt aktiv.

## Verhinderung identischer turn_id bei gleicher User Message

- Client und BFF verwenden UUID-basierte Erzeugung.
- Backend-Fallback erzeugt ebenfalls UUID-basiert.
- `session_id` und `message` werden nicht mehr zur Fallback-ID gehasht.
- Tests belegen, dass zwei gleiche Messages ohne explizite `turn_id`
  unterschiedliche Backend-Fallback-IDs erhalten.

## [DONE] Legacy

`data: [DONE]` bleibt als Legacy-Sentinel bestehen. Die finale Assistant Message
wird weiterhin nur aus dem finalen `state_update` finalisiert; `[DONE]` erzeugt
keine zweite Assistant Message.

## Geaenderte Dateien

- `backend/app/agent/api/models.py`
- `backend/app/agent/api/sse_contract.py`
- `backend/app/agent/tests/test_sse_event_contract.py`
- `backend/app/agent/tests/test_governed_runtime_seam.py`
- `frontend/src/lib/contracts/agent.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`
- `frontend/src/hooks/useAgentStream.ts`
- `frontend/src/hooks/useAgentStream.test.tsx`

## Tests

Ergaenzt beziehungsweise erweitert:

- Backend erzeugt UUID-basierte `turn_id`, wenn keine explizite ID vorhanden ist.
- Backend uebernimmt explizite `turn_id`.
- Ungueltige explizite `turn_id` wird nicht uebernommen.
- `event_id = <turn_id>:<sequence>` bleibt stabil.
- BFF uebernimmt Client-`turnId`.
- BFF erzeugt `turn_id` fuer Legacy-Clients.
- BFF verwendet dieselbe `turn_id` beim Start-401 Refresh-Retry.
- BFF-`interrupted` Event traegt die aktive `turn_id`.
- Frontend sendet pro `sendMessage` eine neue `turnId`.
- Frontend ignoriert finale Events mit fremder `turn_id`.

## Ausgefuehrte Befehle

```bash
pwd
git status --short
git branch --show-current
rg -n "turn_id|request_id|session_id|message_id|stream|SSEEventBuilder|for_request|ChatRequest|AgentChat|chat/stream|ReadableStream|useAgentStream|sendMessage" backend/app frontend/src backend/tests frontend/src/**/*.test.ts*
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_sse_event_contract.py backend/app/agent/tests/test_governed_runtime_seam.py backend/app/agent/tests/test_conversation_runtime.py
npm --prefix frontend run test:run -- src/app/api/bff/agent/chat/stream/route.spec.ts src/hooks/useAgentStream.test.tsx src/lib/streamWorkspace.test.ts src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rwdr_golden_cases.py backend/app/api/tests/test_rfq_endpoint.py
git diff --check
PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/agent/api/sse_contract.py backend/app/agent/api/models.py
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

## Gruene Tests

- Backend SSE/runtime focused: 79 passed.
- Frontend streaming/dashboard focused: 50 passed.
- Backend RWDR/RFQ focused: 50 passed, 1 DeprecationWarning in bestehendem Testcode.
- `git diff --check`: gruen.
- `py_compile` fuer die geaenderten Backend-Contract-Dateien: gruen.

## Forbidden-Language-Scan

Der Scan meldet weiterhin viele bekannte Alt-, Test-, Fixture-, Dokumentations-
und interne Workflow-Treffer, unter anderem Guard-Tests, historische Konzepte,
Forbidden-Phrase-Listen und interne `approved` Review-State-Felder. Dieser Patch
hat keinen neuen produktiven Recommendation-, Freigabe- oder
Materialentscheidungs-Pfad eingefuehrt.

## Verbleibende Restluecken

- BFF erzeugt weiterhin synthetische `answer.stream.*` Events aus finalem
  `state_update`; diese Events tragen jetzt `turn_id`, aber noch keine eigene
  backend-originierte `event_id`/`sequence`.
- `[DONE]` ist weiterhin als Legacy-Sentinel vorhanden.
- `SSEEventBuilder.for_request()` akzeptiert `request_id` noch als Kompatibilitaet,
  wenn keine `turn_id` vorhanden ist. Primaerer Pfad ist aber `turn_id`.
- Einige Streaming-Untergeneratoren koennen weiter eigene Builder anlegen; durch
  die explizite Request-`turn_id` bleibt die Turn-ID dabei stabil.

## Naechste Empfehlung

Naechster sinnvoller Patch: BFF-Synthetik weiter reduzieren und backend-originäre
`answer.stream.*` Events mit vollstaendigen Contract-Metadaten liefern, sodass
`[DONE]` isoliert oder abgeloest werden kann.
