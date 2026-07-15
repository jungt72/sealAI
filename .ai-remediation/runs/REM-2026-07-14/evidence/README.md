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
