---
name: security-tenant
description: >-
  Review or change anything that touches the sealingAI V2 P0 security boundary —
  tenant isolation, the untrusted-content pipeline, secrets handling, or logging.
  Use when a task touches security/tenant.py, adds a DB query or retrieval path
  that must be tenant-scoped, ingests external/user content, or could put secrets
  in logs. Encodes cross-tenant-leak = P0 and the no-secrets-in-logs / .env
  never-read rules.
---

# Security & tenant boundary (P0) — `backend/sealai_v2/security/tenant.py`

A cross-tenant leak is a **P0 blocker**. Treat every data path that reads
persisted or retrieved content as tenant-scoped until proven otherwise.

## Non-negotiables

- **Server-side tenant filters.** Tenant scoping is enforced on the server, in the
  query/retrieval layer — never trust a client-supplied tenant id, never filter
  only in the frontend. Any new DB query, Qdrant query, or memory read must carry
  the tenant filter server-side.
- **Untrusted-content pipeline.** External/user/uploaded content (chat input,
  Paperless-ingested docs, upload evidence) is untrusted. It must not be able to
  steer the system into inventing facts or crossing a guard. Keep it on the
  untrusted path.
- **No secrets in logs.** Never log `OPENAI_API_KEY` or any credential. `.env*` is
  **never read, printed, or committed**. A live REPLAY sources the key transiently
  for that run only.
- **Respect Keycloak user/tenant scoping** end to end. Do not invent or expose
  secrets.

## Memory layers are tenant-sensitive

The 4-layer memory (session working-window / case-state / derived facts,
distiller, integrity guard, cross-session durable facts) persists per user/tenant:
`memory/store.py`, `memory/distiller.py`, `memory/integrity.py`,
`db/conversation_memory.py`, `db/cross_session_memory.py`. A cross-session or
cross-tenant read here is exactly the leak class to guard against — verify the
scope on every read/write path you touch.

## Review discipline

1. For any new persisted/retrieved path, ask: *what tenant scopes this, and is the
   filter server-side?* If you can't answer from the code, that's a finding.
2. A cross-tenant leak, a secret in a log, or an untrusted-content path that
   reaches a guard/fact surface is a **HALT + report**, not a silent fix.
3. New settings that gate security behavior still need the compose passthrough to
   take effect (see `backend-v2-deploy`) — a security flag that silently does
   nothing is worse than none.
4. Prefer typed contracts at the boundary (Pydantic) and typed fallbacks over
   broad `except`.

The broader ops-hardening posture (rate-limiting, backups, disk safeguard,
dependency scan) is tracked outside this skill; this skill is the per-change P0
boundary check.
