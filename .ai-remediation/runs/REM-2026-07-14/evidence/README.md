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
- Full hermetic backend collection contained 2,615 tests. The run completed with 2,613 passed and
  2 expected skips: the explicit-DSN PostgreSQL GATE-07 proof and a Linux-only storage-lease test.
- `npm run verify` in `frontend-v2` passed boundary and terminology checks, TypeScript, 321 tests
  in 37 files, and the production build. The dependency audit reported zero vulnerabilities.
- Focused authority, ledger, cache, ownership, Briefing/RFQ, role, migration, and legal-gate tests
  are included in that green full run.
- `ops/check-secret-hygiene.py --worktree` passed without finding a secret artifact.
- The combined base/deployment Compose model validated successfully with non-secret test-only
  placeholders; no daemon operation or container start was performed.
- Structured remediation JSON/YAML parsed successfully, remediation-control tests passed, and
  `git diff --check` reported no whitespace error.
- No external provider, daemon, production database, production container, deployment, schema
  validation, RLS/FORCE operation, role change, data backfill, data deletion, commit, or push ran.
- `backend/sealai_v2/tests/test_postgres_gate07_integration.py` remains opt-in and was not executed;
  no explicit ephemeral PostgreSQL DSN was supplied. This is a hard GATE-07 evidence gap.

This summary is local implementation evidence only. It does not change production state and cannot
support `VERIFIED` without the gated production-equivalent and post-deployment checks.

## P1 reviewer governance

Sanitized local verification summary, 2026-07-15:

- Scope: the locally implementable AUTH-003 and GOV-001 controls only.
- The final hermetic backend collection contained 2,803 tests: 2,801 passed and
  2 expected tests skipped (the explicit-DSN PostgreSQL proof and Linux-only
  storage-lease lane).
- A final 138-test focused role, affiliation, COI, capability, knowledge,
  migration, cutover, remediation-control, and architecture run passed.
- Ruff 0.6.9 reported all 28 changed Python files formatted and lint-clean;
  Bash syntax, JSON/YAML parsing, remediation controls, supply-chain policy,
  and `git diff --check` passed.
- `ops/check-secret-hygiene.py --worktree` passed. Keycloak and cutover receipts
  contain counts and hashes only; legacy quarantine identifiers are HMACed with
  an externally injected key.
- The Keycloak reconciler was exercised only with synthetic offline state and
  mocked command responses. No Docker, Keycloak, provider, role, group, or user
  assignment mutation ran.
- Migration and transactional tests used local hermetic SQLite databases. No
  production or production-like PostgreSQL migration, constraint validation,
  authority import, legacy quarantine write, backfill, feature activation,
  container recreation, deployment, push, or PR ran.

Closure remains externally blocked. GATE-06 requires a human-owned production
role/group census and explicit membership decisions. GATE-07 requires an
access-controlled, peer-reviewed, versioned human affiliation bundle sourced
from an owner-attested identity roster, independent HR register, or contractual
affiliation register, plus isolated-restore schema/import/quarantine evidence.
GATE-08 requires exact-image deployment with both review features still off,
production-equivalent negative tests, and a separate activation decision.
AUTH-003 and GOV-001 therefore remain `BLOCKED_EXTERNAL`, never `VERIFIED`.
