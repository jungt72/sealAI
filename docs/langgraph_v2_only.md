# LangGraph v2-only (Operations)

## Architektur (BFF)
- /api/chat -> Next.js BFF -> backend /api/v1/langgraph/chat/v2 (SSE)
- /api/langgraph/parameters/patch -> backend /api/v1/langgraph/parameters/patch
- /api/langgraph/state -> backend /api/v1/langgraph/state
- /api/langgraph/confirm/go -> backend /api/v1/langgraph/confirm/go

## Warum BFF
- Unabhaengig von NGINX-Rewrites (funktioniert auch ohne Reverse-Proxy).
- Konsistentes Auth-Handling (Bearer Token wird serverseitig validiert).
- Zentrale Logging-/Tracing-Punkte im Frontend-Proxy.

## Backend Base Resolution (Server)
Die BFF-Handler nutzen folgende ENV-Reihenfolge, um die Backend-Base zu finden:
- NEXT_PUBLIC_BACKEND_URL
- NEXT_PUBLIC_API_BASE
- BACKEND_URL
- API_BASE
- Fallback: http://backend:8000

## v1 ist deaktiviert
Legacy LangGraph v1 Endpoints sind entfernt bzw. liefern 410 Gone mit Hinweis:
"Legacy LangGraph v1 endpoint removed; use /api/v1/langgraph/* (v2)."

## Beispiele
- BASE_URL=http://localhost:3000 ./ops/smoke_langgraph_v2_bff.sh
- BASE_URL=https://sealai.net BEARER_TOKEN=... ./ops/smoke_langgraph_v2_bff.sh
- ./ops/check_no_langgraph_v1.sh

## CI Guardrails
Der Workflow `.github/workflows/langgraph-v2-guardrails.yml` fuehrt folgende Checks aus:
- v2-only Code Check (failt bei v1 Imports oder direkten Client-Calls zu `/api/v1/langgraph/*`).
- Smoke-Test gegen die BFF-Routen ohne Token (401 gilt als Erfolg).

Der Build bricht ab bei:
- v1 Importen ausserhalb `backend/app/archive/**`.
- Direkten Client-Calls zu `/api/v1/langgraph/*` ausserhalb der erlaubten Server-Routen.
- Nicht erreichbaren BFF-Routen (z.B. fehlender 401/200).
