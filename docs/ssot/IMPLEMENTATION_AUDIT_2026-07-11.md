# SSoT v2.0 Implementation Audit

Date: 2026-07-11. Baseline commit: `3461809d`.

## Decision

The modular-monolith direction, typed trust layers, deterministic kernel,
tenant boundary, Postgres knowledge ledger, derived Qdrant index, durable
outbox, immutable backend image, and rollback path are retained. LangGraph is
not introduced.

The repository is a strong candidate platform, but it is not yet a final SSoT
release. The migration follows the SSoT horizons; H3-H5 remain planned until
their own evidence and gates exist.

## Blocking gaps at baseline

1. `AGENTS.md`, the old registry, V10/RWDR documents, and SSoT v2.0 conflict on
   authority and active runtime.
2. General knowledge is active without a single M15 activation contract.
3. Of 79 active approved seed claims, 28 have no external source; the ledger
   lacks the complete applicability, uncertainty, transferability, and review
   lifecycle contract.
4. Paid partner membership controls manufacturer pool inclusion; capability
   verification and conflict-of-interest operations are incomplete.
5. Sessions and facts exist, but a durable decision/approval record does not.
6. Candidate deployments can reach production without exact adjudicated replay.
7. Maturity and North-Star quality metrics are not a shared runtime contract.
8. Off-host disaster recovery and immutable dashboard delivery remain open.

## Challenged implementation order

1. Materialize authority, ODRs, evidence, maturity, and executable governance.
2. Add fail-closed activation gates before broadening behavior.
3. Evolve claim and capability schemas additively with migrations and backups.
4. Quarantine unsupported approvals; never manufacture evidence to preserve
   answer coverage.
5. Add durable case/decision primitives without pretending H2 is complete.
6. Run offline and targeted verification throughout; run the complete paid
   replay once, at the final behavior tree.
7. Promote only through PR, protected CI, backup, migration, smoke, and rollback.

## Live baseline evidence

- VPS checkout was clean at `3461809df26c05cc880941db9d864ce6e2f86da2`.
- API and worker ran the same immutable backend image and were healthy.
- Database revision was `20260710_0003`.
- Active seed projection: 601 claims, 79 approved, 28 approved without sources.
- Manufacturer records: one active partner; zero captured leads.
- Current deployment was a candidate with paid final replay pending.

No production data is deleted by the migration. Schema changes are additive;
status corrections remain audited and derived Qdrant data is rebuildable.

## Foundation remediation recorded after the baseline

- G7 was closed in the foundation change: the production workflow is manual and
  final-only, and the release wrapper rejects candidates unless `APP_ENV` is
  explicitly `development`, `test`, or `staging`.
