# MAT-GOV-03B sealed-baseline audit summary

Status: owner-accepted sealed implementation baseline; merge, migration, and
activation remain blocked.

## Sealed implementation

- Branch: `feature/mat-gov-03b`
- Commit: `da126b1a6a1f75faf4790de7115284a21099e290`
- Tree: `479728cb57717faf25219299d14345b9ffc530ae`
- Parent: `c650c44b70326949f2985e9f0ff7ae82bf2f931a`
- Commit count relative to parent: `1`
- Worktree at evidence capture: `CLEAN`

The sealed commit must not be amended, rebased, squashed, rewritten, or
force-pushed. Follow-ups are child commits.

## Independent audit

- Auditor model: `claude-sonnet-5`
- Audit completed: `2026-07-17T10:54:28Z`
- Result: `APPROVED_WITH_NONBLOCKING_FINDINGS`
- Web accesses: `0`
- Permission denials: `0`
- Audit input SHA-256:
  `fb81a9f44e4d6f4797bd72816f79b964f64a6a3297243b064fec602a7b1d9465`
- Audit result SHA-256:
  `5bd5e153f292b698fce6154818d1fd541ac886bb72382c52070c3bb3524ceaaa`

The final successful run used Claude Code `2.1.205`, tool access disabled,
plan permission mode, an empty strict MCP configuration, disabled hooks,
disabled session persistence, disabled Chrome integration, model
`claude-sonnet-5`, `max-turns=2`, and `max-budget-usd=5.00`. The two-turn limit
was required only because this Claude Code version returned
`error_max_turns` before emitting a report with `max-turns=1`; the successful
result itself reports one model turn.

## Evidence interpretation

- Ruff checked all 440 backend Python files and reported that all were already
  formatted. Ruff did not modify 440 files. The sealed commit changes 38 files.
- Migration `20260717_0012` is an additive schema migration that creates nine
  empty tables and performs no data migration or backfill. It is not an empty
  migration.
- The raw audit input, raw audit output, PostgreSQL evidence, and test logs are
  not committed because they contain a large proprietary source diff or
  machine-oriented output.
- Durable, access-controlled artifact storage and its retention policy remain
  `PENDING_OWNER_PROVIDED_ARTIFACT_LOCATION`. This is a merge-evidence gate;
  local `/tmp` storage is not treated as durable evidence.

## Mandatory findings

The following findings are HIGH and block merge, migration, activation, and
sampling:

1. `MAT-GOV-03B-HF1`: replace separator-concatenated cache keys with a
   collision-safe, versioned, length-prefixed encoding.
2. `MAT-GOV-03B-HF2`: count every successful worker lease acquisition as one
   attempt and durably terminalize repeatedly orphaned jobs at the configured
   limit.

## Test evidence for the sealed baseline

- Backend: 2,273 collected; 2,271 passed; two dedicated PostgreSQL tests were
  hermetically skipped and passed separately against PostgreSQL 16.
- Focused MAT-GOV-03B suite: 55 passed.
- Architecture and SSoT: 30 passed.
- Frontend: 34 files and 307 tests passed; typecheck and production build
  passed.
- Secret-control tests: 44 passed; worktree and staged scans found no secret
  artifacts.
- Ruff format/check, JSON parsing, bytecode compilation, and
  `git diff --check` passed.

## Activation boundary

MAT-GOV-03B remains default-off, zero-sampling, pointerless, and
non-authoritative. MAT-GOV-03C, MAT-EVID-01, MED-NORM-01, production migration,
runtime activation, and sampling above zero remain `NO-GO`.
