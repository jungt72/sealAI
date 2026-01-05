# Runbook: Chat v2 SSE (E2E + Troubleshooting)

## Architektur (6 Zeilen)

- Browser/UI sendet `POST /api/chat` (Next.js Route Handler, SSE passthrough)
- Proxy validiert Contract + verlangt `Authorization: Bearer …`
- Proxy forwardet an Backend `POST /api/v1/langgraph/chat/v2`
- Backend setzt `user` ausschließlich aus JWT und startet LangGraph v2
- Backend streamt `text/event-stream` (`event: token`, optional `event: confirm_checkpoint`, `event: done`)
- Keepalive wird als Kommentarframe gesendet: `: keepalive`

## Contract

**Request (JSON, strikt):**

```json
{
  "input": "string (required, trim>0)",
  "chat_id": "string (required, trim>0)",
  "client_msg_id": "string (optional)",
  "metadata": { "any": "object (optional)" }
}
```

**Verboten (Proxy antwortet `400`):**
- `thread_id`, `threadId`, `user_id`, `userId`
- beliebige andere unbekannte Keys

**Auth:**
- `Authorization: Bearer <ACCESS_TOKEN>` ist Pflicht (`401` wenn fehlt)

## E2E Smoke Test

Script: `ops/smoke_chat_v2_sse.sh`

Beispiel:

```bash
export ACCESS_TOKEN="…"
export BASE_URL="http://localhost:3000"
ops/smoke_chat_v2_sse.sh "demo-chat-123" "Hallo, bitte kurz bestätigen."
```

Erwartung im Output:
- `: keepalive` (während Backend rechnet)
- mehrere `event: token` Frames
- am Ende `event: done`

## Observability / Log-Korrelation

Der Proxy setzt/forwardet `X-Request-Id` und loggt `request_id` + `chat_id`.

Schnelle Greps:

```bash
docker compose logs backend --since 5m | rg "langgraph_v2_chat_request|chat_id|request_id"
docker compose logs frontend --since 5m | rg "\\[api/chat\\]|request_id|chat_id"
```

## Troubleshooting Matrix

### 401 Unauthorized

**Symptom:** `/api/chat` gibt `401 Missing Authorization: Bearer token`  
**Ursache:** `ACCESS_TOKEN` fehlt/leer oder kein `Authorization` Header.  
**Check:** Script env `ACCESS_TOKEN` gesetzt? Session/Token in NextAuth gültig?

### 400 Bad Request (Contract)

**Symptom:** `/api/chat` gibt `400 Unknown keys in request body` oder `chat_id must not be empty`  
**Ursache:** Request enthält verbotene Keys oder `input/chat_id` leer.  
**Fix:** Nur `{input, chat_id, client_msg_id?, metadata?}` senden.

### 422 Unprocessable Entity

**Symptom:** Backend liefert `422` (Pydantic)  
**Ursache:** JSON Typen stimmen nicht (z.B. `metadata` ist kein Objekt) oder `chat_id/input` fehlen.  
**Check:** Proxy-Logs: bei korrektem Proxy sollte 422 selten sein, außer Backend contract driftet.

### 502/504 (Proxy/Nginx)

**Symptom:** `/api/chat` liefert `502 Backend unreachable` oder Nginx `504`  
**Ursache:** Backend down, falsche Backend-URL Env, Nginx timeouts/buffering.  
**Checks:**
- `docker compose ps`
- `docker compose logs backend --since 5m | tail -n 200`
- Nginx SSE Hardening (siehe unten)

### “Stream hängt” / keine Tokens

**Symptom:** Verbindung bleibt offen, aber UI zeigt keine Tokens.  
**Ursache:** Nginx/Proxy buffering, zu kurze read timeouts, oder LLM braucht lange.  
**Checks:**
- sieht man `: keepalive` im Stream? Wenn ja: Backend sendet, aber Proxy/Nginx puffert.
- Nginx `proxy_buffering off;` und `proxy_read_timeout` hoch setzen.

## Nginx SSE Hardening (wenn Nginx vor dem Proxy sitzt)

Für SSE Locations (z.B. `/api/chat`) sollten folgende Direktiven gesetzt sein.

Repo-Referenz: `nginx/default.conf` enthält eine dedizierte `location ^~ /api/chat { ... }` mit diesen Einstellungen.

```nginx
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_buffering off;
proxy_cache off;
gzip off;
proxy_read_timeout 3600;
proxy_send_timeout 3600;
add_header X-Accel-Buffering no;
```
