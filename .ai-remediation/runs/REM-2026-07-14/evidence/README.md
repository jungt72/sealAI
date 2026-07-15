# Evidence handling for REM-2026-07-14

This directory is intentionally ignored except for this policy marker. Raw host
inventories, command output, and scan reports remain local until they have been
reviewed and sanitized. Versioned evidence belongs in the structured manifests
one directory above and must never contain credentials, private-key data,
authorization material, production environment values, Redis values, or
personal data.

The versioned `../evidence-manifest.json` records only artifact names, record
counts, modes, checksums, and unresolved classification counts. It does not
make the ignored raw metadata suitable for publication or commit.

## P1 data authority

Sanitized local verification summary, 2026-07-15:

- Scope: RAG-001, DATA-001, APP-001, AUTH-003, and the locally implementable part of GOV-001.
- `ruff 0.6.9 format backend/` completed; `ruff 0.6.9 check backend/` passed.
- Full hermetic backend collection contained 2,788 tests. The run completed with 2,783 passed and
  5 expected skips: four explicit-DSN PostgreSQL GATE-07 cases and one Linux-only storage-lease
  test. No SQLite or mock result was counted as PostgreSQL/RLS evidence.
- `npm run verify` in `frontend-v2` passed boundary and terminology checks, TypeScript, 321 tests
  in 37 files, and the production build. The dependency audit reported zero vulnerabilities.
- Focused authority, ledger, cache, ownership, Briefing/RFQ, role, migration, worker-separation,
  transaction-scope, pool-reset, and legal-gate tests are included in that green full run.
- `ops/check-secret-hygiene.py --worktree` passed without finding a secret artifact.
- The combined base/deployment Compose model validated successfully with non-secret test-only
  placeholders; no daemon operation or container start was performed.
- Structured remediation JSON/YAML parsed successfully, remediation-control tests passed, and
  `git diff --check` reported no whitespace error.
- No external provider, daemon, production database, production container, deployment, schema
  validation, RLS/FORCE operation, role change, data backfill, data deletion, or push ran.
- `test_postgres_gate07_integration.py` and `test_postgres_runtime_scope_integration.py` remain
  opt-in and were not executed because no explicit empty ephemeral PostgreSQL DSN was supplied.
  The latter is wired to apply the real Alembic chain and exact cutover transaction; its skip is a
  hard GATE-07 evidence gap, not a local pass.

This summary is local implementation evidence only. It does not change production state and cannot
support `VERIFIED` without the gated production-equivalent and post-deployment checks.

## P1 API lifecycle

Sanitized local verification summary, 2026-07-15:

- Scope: API-001 only; production, external providers, legal authority, secret custody, and data
  retention decisions were not accessed or changed.
- The full V2 backend collection contained 2,181 tests: 2,176 passed and five explicit-DSN
  PostgreSQL cases were visibly skipped. No SQLite or mock result is counted as PostgreSQL/RLS
  evidence.
- The focused lifecycle collection contained 54 cases: 50 passed and four explicit-DSN
  PostgreSQL cases were skipped. It covers request/case limits, strict schemas, actor/tenant quotas,
  concurrency races, non-refundable storage admission, idempotency conflict/replay, expired-lease
  recovery, stale-completion fencing, keyset pagination, quarantine, receipts, retention, IDOR, and
  additive migrations.
- All 22 architecture tests passed. Ruff check and format-check passed for all 455 backend and test
  files.
- Frontend TypeScript passed; 321 tests in 37 files passed; boundary/terminology checks and the
  production Vite build passed.
- The combined base/deployment Compose model rendered successfully without interpolation or a
  daemon operation. Nginx and Compose preserve the default-off feature and hard limits.
- `ops/check-secret-hygiene.py --worktree` passed without a secret finding after the implementation
  and sanitized evidence were complete.
- No image build/push/pull, provider call, external message, production connection, production data
  read/write, migration, backfill, constraint validation, RLS/FORCE action, role change, deletion,
  deployment, or remote Git operation ran.
- Policy/purpose/consent authority, retention duration, receipt-HMAC lifecycle, quota capacity,
  role/privacy approval, restore proof, legacy profile, explicit ephemeral PostgreSQL execution,
  and exact-image deployment remain external Gate-06/07/08 requirements.

This package is `IMPLEMENTED_NOT_DEPLOYED`. Gate-06, Gate-07, and Gate-08 remain
`BLOCKED_EXTERNAL`; local evidence must never be reported as production verification.
