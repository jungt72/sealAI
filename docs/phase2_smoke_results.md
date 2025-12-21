# Phase 2 Smoke Results

## Commit 76e54bfab2efc0715d4ecc652337f44f27cfcf4b (chore(cleanup): quarantine backup files)
- GET /api/v1/langgraph/health -> http_code=000 (curl exit 7: connection refused)
- POST /api/chat SSE -> connection failed (curl exit 7: localhost:3000 not reachable)
- GET /api/conversations -> http_code=000 (curl exit 7: connection refused)
