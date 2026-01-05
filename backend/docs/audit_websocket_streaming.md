# WebSocket Streaming Audit – SealAI Chat

## 1. End-to-End Pfad (Backend ↔ Nginx ↔ Frontend)
- **Client URL**: `frontend/src/lib/useChatWs.ts:40-116` generiert den Socket-Endpunkt. Standardpfad ist `/api/v1/ai/ws`, basierend auf `NEXT_PUBLIC_*` Variablen; Protokolle werden automatisch auf `wss://` bzw. `ws://` umgestellt.
- **Nginx**: `nginx/default.conf:123-155` enthält zwei identische WebSocket-Locations für `/api/v1/chat/ws` und `/api/v1/ai/ws`, inklusive Upgrade-/Connection-Header – somit landet jeder Aufruf unter `/api/v1/ai/ws` korrekt beim Backend.
- **Backend Route**: FastAPI mountet den WebSocket-Router ohne Präfix (`backend/app/main.py:36-40`), d. h. `/api/v1/ai/ws` wird durch FastAPI → `backend/app/api/routes/chat.py:47-116` bedient. Dort übernimmt `_maybe_authenticate`, eine Handshake-Schleife und anschließend `stream_langgraph`.

## 2. Backend-Verhalten
- **Handshake-Anforderungen**: `ws_chat` wartet, bis der empfangene JSON-Payload eines der Felder `input`, `input_text` oder `text` enthält (`backend/app/api/routes/chat.py:65-72`). Ohne diese Felder sendet der Server lediglich `{"event": "noop"}` und wartet weiter.
- **Payload-Nutzung**: Später extrahiert `user_input = payload.get("input") or ... or payload.get("text")` (`backend/app/api/routes/chat.py:86-93`). In `stream_langgraph` wird derselbe Ausdruck verwendet; wenn er leer bleibt, sendet der Server `{"event":"error","message":"input_empty"}` gefolgt von `{"event":"done"}` und beendet den Ablauf (`backend/app/services/chat/ws_streaming.py:152-161`).
- **LangGraph-Streaming**: Sobald ein gültiger Input existiert, `stream_langgraph` ruft `graph.astream_events(..., version="v1")` auf und emittiert `{"event": "token", "text": "...", "agent": "<optional>"}` für jeden Chunk sowie `{"event":"final", "payload":{...}}` und `{"event":"done"}` am Ende (`backend/app/services/chat/ws_streaming.py:197-311`).

## 3. Frontend-Verhalten
- **Senden**: Der Hook `useChatWs` konstruiert Payloads ausschließlich mit dem Feld `message` – kein `input`/`text` wird gesetzt (`frontend/src/lib/useChatWs.ts:503-534`). Dadurch erfüllt der Client die Backend-Anforderung nicht.
- **Empfang**: `handleMessage` reagiert auf Events `start`, `token`, `final`, `done`, `error` und formatiert Tokens in Echtzeit (`frontend/src/lib/useChatWs.ts:412-493`). Das Frontend ist somit bereit, `token`-Events mit `text` zu rendern – bekommt sie aber nicht, weil der Server mangels Input direkt einen Fehler sendet.

## 4. Festgestellte Ursachen
1. **Request-Feld mismatch**  
   - Backend verlangt `input`/`input_text`/`text`, Frontend sendet ausschließlich `message`.  
   - Folgen: Handshake bricht nie aus der Schleife → Server antwortet nur mit `event:"noop"` oder – wenn `stream_langgraph` trotzdem aufgerufen wird – `input_empty`. Kein Graph-Lauf, keine Tokens.
2. **State-Building nutzt ebenfalls keine `message`-Felder**  
   - `_initial_state` und `stream_langgraph` ignorieren `payload["message"]`, selbst wenn die Handshake-Schleife irgendwann modifiziert würde. Ohne Anpassung bleibt `user_input` leer.

## 5. Belegende Symptome
- Logs/Frontend zeigen nur generische Events (noop/error), keine Token-Streams.
- SSE-Routen funktionieren, da Client/Server dort beide `input`-Felder verwenden; Problem ist auf den WS-Client beschränkt.

## 6. Empfohlene Fix-Optionen (nicht umgesetzt)
1. **Frontend anpassen**  
   - Beim Senden neben `message` auch `input` (oder `text`) setzen und optional den Handshake-Schlüssel `input` schon im ersten Frame mitsenden.  
   - Vorteil: Backend bleibt kompatibel zu SSE/REST, kein Server-Change nötig.
2. **Backend toleranter machen**  
   - Ergänze in `ws_chat` sowie in `stream_langgraph`/`_initial_state` einen Fallback auf `payload.get("message")`.  
   - Ggf. `has_input_field = any(key in payload for key in (..., "message"))`.
3. **Kombination**  
   - Kurzfristig Backend-Fallback implementieren, langfristig Frontend vereinheitlichen, um divergierende Felder zu vermeiden.

## 7. Offene Empfehlungen
- Frontend sollte Fehler-Events (z. B. `input_empty`) visuell anzeigen, damit Nutzer erkennen, warum keine Antwort erfolgt.  
- Ein automatisierter Smoke-Test (z. B. `wscat -c wss://.../api/v1/ai/ws` mit gültigem JSON, das sowohl `chat_id` als auch `input` enthält) sollte in die Betriebs-Playbooks aufgenommen werden, um Format-Drift frühzeitig zu erkennen.

## 8. Schneller Smoke-Test (manuell)
```bash
wscat -c wss://<host>/api/v1/ai/ws <<'EOF'
{"chat_id":"test-ws","input":"Hallo WS","consent":true}
EOF
```
- Erwartet: `event:start` → mehrere `event:token` → `event:final` → `event:done`. Optional weitere Felder (`message`, `metadata`, Auth-Token) können ergänzt werden; wichtig ist, dass mindestens eins der Input-Felder (`input`/`text`/`message`) gesetzt ist.
