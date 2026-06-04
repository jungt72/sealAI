# 27 SSE Midstream Token Resilience Report

Datum: 2026-05-27

## Ziel

Mid-stream Auth- und Network-Failure dürfen keinen laufenden Chat-Turn als erfolgreiche finale Assistant Message abschließen. Teilantworten dürfen sichtbar bleiben, aber nicht in `messages` finalisiert werden. Der BFF darf keine rohen Token-/Backend-Fehlertexte an die UI durchreichen.

## Aktueller Streaming/Auth-Pfad

1. Frontend Chat:
   - `ChatPane` rendert `messages`, `streamingText`, `isStreaming` und `error` aus `useAgentStream`: `frontend/src/components/dashboard/ChatPane.tsx:273`.
   - Live-Teilantworten werden separat über `streamingText` gerendert, nicht als persistierte Assistant Message: `frontend/src/components/dashboard/ChatPane.tsx:619`.
2. Frontend Stream Hook:
   - `useAgentStream.sendMessage()` ruft `fetchEventSource("/api/bff/agent/chat/stream")` auf: `frontend/src/hooks/useAgentStream.ts:462`.
   - Vor diesem Patch wurde nach Rückkehr von `fetchEventSource` immer `finalizeAssistantTurn(requestId)` aufgerufen, wenn kein Throw im Catch landete.
3. BFF Stream Route:
   - `POST()` holt ein Access Token über `getAccessTokenResult()` und ruft das Backend mit `Authorization: Bearer ...` auf: `frontend/src/app/api/bff/agent/chat/stream/route.ts:341`.
   - Start-401 mit `token_expired` wird bereits per Force Refresh und einmaligem Retry behandelt: `frontend/src/app/api/bff/agent/chat/stream/route.ts:353`.
   - Der BFF liest Backend-SSE-Frames und gibt nur kontrollierte UI-Events weiter: `frontend/src/app/api/bff/agent/chat/stream/route.ts:399`.
4. Backend Stream:
   - `backend/app/agent/api/streaming.py` erzeugt technische Antworten erst nach Graph/Composer/Final Guard als `state_update` und danach `[DONE]`: `backend/app/agent/api/streaming.py:951`.

## Erkannte Failure Modes

- A. Backend 401 vor Streamstart: bereits vorhanden. Erwartetes Verhalten bleibt Force Refresh + genau ein Retry; danach kontrollierter 401 mit Re-Login-Text.
- B. Backend/Auth-Fehler nach Streamstart vor finalem `state_update`: Risiko war, dass bereits empfangene `answer.token`-Teile über die spätere Finalisierung als Assistant Message landen.
- C. Network abort mid-stream: Risiko war eine halb aufgebaute Antwort ohne klaren Interrupt-Zustand.
- D. Backend sendet `error` im SSE: Risiko war, dass der Hook zwar `error` setzt, aber der abgeschlossene `fetchEventSource`-Promise danach trotzdem finalisiert.
- E. Duplicate SSE Events: wenn Events `event_id` oder `turn_id` + `sequence` tragen, gab es keinen dedizierten Dedupe-Key im Hook.
- F. Manueller Retry nach Unterbrechung: bleibt explizit beim User; es gibt keinen automatischen Blind-Retry nach begonnenem Stream.

## Implementiertes Verhalten

### BFF

- Ergänzt `agentStreamErrorCode()` zur Klassifikation von Auth-/Network-/generischem Streamfehler ohne Rohdetails in der UI: `frontend/src/app/api/bff/agent/chat/stream/route.ts:289`.
- Vorhandene Backend-Stream-Metadaten `event_id`, `turn_id`, `sequence`, `is_final` und `error_code` werden an die UI weitergereicht, damit der Hook deduplizieren kann: `frontend/src/app/api/bff/agent/chat/stream/route.ts:311`.
- Wenn `reader.read()` während des Backend-SSE-Proxyings wirft, sendet der BFF jetzt ein strukturiertes Event:

```json
{
  "type": "interrupted",
  "code": "network_error",
  "error_code": "network_error",
  "message": "Die Verbindung zur Antwort wurde unterbrochen. Bitte versuche es erneut.",
  "is_final": false
}
```

Beleg: `frontend/src/app/api/bff/agent/chat/stream/route.ts:575`.

### Frontend Hook

- Ergänzt Stream-State-Refs:
  - `finalStateReceivedRef`
  - `streamDoneReceivedRef`
  - `streamInterruptedRef`
  - `seenStreamEventKeysRef`
  Beleg: `frontend/src/hooks/useAgentStream.ts:285`.
- `state_update` ist jetzt die Voraussetzung für finale Assistant-Message-Finalisierung: `frontend/src/hooks/useAgentStream.ts:563` und `frontend/src/hooks/useAgentStream.ts:632`.
- `error` und `interrupted` setzen den Turn auf unterbrochen, löschen die interne finale Assistant-Basis und verhindern `finalizeAssistantTurn()`: `frontend/src/hooks/useAgentStream.ts:440` und `frontend/src/hooks/useAgentStream.ts:602`.
- Network-Fehler im `onerror` werden als kontrollierte Unterbrechung behandelt und nicht automatisch erneut gesendet: `frontend/src/hooks/useAgentStream.ts:625`.
- Wenn der Stream ohne `[DONE]` und ohne `state_update` schließt, während schon Antwort-Token sichtbar sind, wird der Turn unterbrochen statt finalisiert: `frontend/src/hooks/useAgentStream.ts:606`.
- Event-Dedupe per `event_id` oder `turn_id` + `sequence` wurde ergänzt: `frontend/src/hooks/useAgentStream.ts:193` und `frontend/src/hooks/useAgentStream.ts:510`.

## Geänderte Dateien

- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`
- `frontend/src/hooks/useAgentStream.ts`
- `frontend/src/hooks/useAgentStream.test.tsx`
- `docs/audits/sealingai-engine/27_sse_midstream_token_resilience_report.md`

## Tests

Neue/erweiterte Testabdeckung:

- BFF erzeugt bei Mid-stream-Read-Failure ein strukturiertes `interrupted`-Event ohne rohen Backend-Fehlertext: `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts:450`.
- BFF erhält vorhandene Stream-Metadaten für Frontend-Dedupe: `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts:583`.
- Hook finalisiert Teilantworten bei Auth-Interrupt nicht als Assistant Message: `frontend/src/hooks/useAgentStream.test.tsx:341`.
- Hook finalisiert Teilantworten bei Network-Fehler nicht als Assistant Message: `frontend/src/hooks/useAgentStream.test.tsx:375`.
- Hook dedupliziert wiederholte Events mit identischer `event_id`: `frontend/src/hooks/useAgentStream.test.tsx:402`.
- Bestehende Start-401-/Refresh-Tests bleiben erhalten: `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts:420` und `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts:484`.

## Testbefehle

Ausgeführt:

```bash
pwd
git status --short
git branch --show-current
rg -n "EventSource|ReadableStream|SSE|stream|reader|done|abort|AbortController|retry|expired|token_expired|401|403|refresh|accessToken|Authorization|Bearer|turn_id|message_id|event_id|assistant" frontend/src backend/app
npm --prefix frontend run test:run -- src/hooks/useAgentStream.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_conversation_runtime.py backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_knowledge_answer_composer.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rwdr_golden_cases.py backend/app/api/tests/test_rfq_endpoint.py
npm --prefix frontend run test:run -- src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx src/hooks/useAgentStream.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts
```

Ergebnisse bisher:

- Frontend focused Stream/BFF: `2 passed`, `33 passed`.
- Backend conversation/composer focused: passed, exit code `0`.
- Backend RWDR/RFQ/API focused: passed, exit code `0`, eine bestehende DeprecationWarning zu `HTTP_422_UNPROCESSABLE_ENTITY`.
- Frontend focused requested suite: zuerst `4 passed`, `45 passed`; nach Metadaten-Pass-through erneut `4 passed`, `46 passed`.
- `git diff --check`: passed.
- Forbidden-Language-Scan: `469` bestehende Treffer, überwiegend Guard-/Test-/Fixture-/Legacy-Dokumentationsstellen und interne Workflow-Vokabeln. Kein neuer produktiver Antwortpfad wurde als Freigabe-/Empfehlungspfad eingeführt.

## Verbleibende Restlücken

- Backend-SSE-Events tragen nicht durchgehend `event_id`, `turn_id`, `sequence`, `is_final` und `error_code`. Der BFF reicht vorhandene Felder jetzt weiter; eine vollständige End-to-End-Event-ID-Policy fehlt noch.
- Der BFF kann Mid-stream Auth-Expiry nur strukturiert behandeln, wenn der Backend-Fehler als Reader-Error oder SSE-Error sichtbar wird. Ein semantisch typisiertes Backend-`interrupted`-Event für Auth-Expiry wäre sauberer.
- Es gibt weiterhin keinen idempotenten Turn-Resume-Mechanismus. Das ist absichtlich nicht gebaut worden, weil ein automatischer Blind-Retry nach Streamstart ausgeschlossen war.
- Partial `streamingText` bleibt sichtbar und wird über die Error-Box als unterbrochen markiert. Eine eigene UI-Badge/Message-Metadatenstruktur für `interrupted` wurde nicht eingeführt.

## Nächste Empfehlung

Als nächster Patch sollte der Backend-SSE-Contract typisierte IDs und Sequenzen für alle sichtbaren Events liefern:

- `turn_id`
- `event_id`
- `event_type`
- `sequence`
- `is_final`
- `error_code`

Danach kann der BFF diese Metadaten unverändert weiterreichen und die UI-Dedupe von heuristischem Fallback auf contract-basierte Idempotenz umstellen.
