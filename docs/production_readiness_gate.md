# Production Readiness Gate

This gate runs a small, read-only set of proofs to validate production readiness.

## What it checks
- `docker compose config` (syntax/merge validity)
- Backend health and metrics endpoints (smoke)
- RAG sanitizer proof
- Redis TTL proof (optional unless required)
- SSE replay keys in Redis (optional and only if required)

## Env vars

Optional:
- `BASE_URL` (default: `http://localhost:8000`)
- `ACCESS_TOKEN` (used for chat v2 smoke check)
- `REDIS_PASSWORD` (required to check TTLs)
- `COMPOSE_CMD` (default: `docker compose`)

Require checks (force FAIL if missing):
- `REQUIRE_REDIS=1` (fail if `REDIS_PASSWORD` missing)
- `REQUIRE_SSE_REPLAY=1` (fail if SSE replay keys missing and backend is redis)

## PASS/FAIL/SKIP
- PASS: check succeeded
- FAIL: check failed, gate exits non-zero
- SKIP: check skipped due to missing optional env or not applicable

## Expected runtime
- Typically under 1 minute, depending on Docker and service availability.

## Release policy
- Gate must be green (no FAIL) before production deploy.
