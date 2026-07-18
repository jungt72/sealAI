# ADR: MAT-GOV-03A immutable snapshot persistence

Status: accepted for technical implementation only; production migration and
material-rule activation are not authorized.

Date: 2026-07-17

## Context

The established V2 schema deliberately avoids database foreign keys across its
older, independently evolving aggregates. MAT-GOV-03A introduces a new,
self-contained technical aggregate whose value depends on durable identity,
content addressing, append-only evidence, and object-level immutability. An
application-only reference check would not provide the required restore and
tamper contract.

## Decision

The four MAT-GOV-03A tables form one isolated aggregate:

- `v2_material_rulesets`;
- `v2_material_ruleset_snapshots`;
- `v2_material_snapshot_validation_events`;
- `v2_material_snapshot_audit_events`.

Foreign keys inside this aggregate are real database constraints with
`ON DELETE RESTRICT`. No existing V2 table receives a foreign key, and no
cross-subsystem relationship is introduced.

Ruleset families, snapshots, technical validation events, and audit events are
append-only. PostgreSQL and the SQLite migration-test profile install database
triggers that reject `UPDATE` and `DELETE`. Snapshot correction means creating
a new snapshot; the stored content is never patched. The repository exposes
create/read methods only and revalidates schema, canonical bytes, content hash,
snapshot identity, and domain-pack binding on every load.

The migration creates empty tables. It imports no matrix seed, performs no
legacy backfill, creates no lifecycle/pointer/pinning table, and may downgrade
only while all four tables are empty.

## Database-role boundary

No global or production database role is changed by MAT-GOV-03A. The desired
future least-privilege split is documented, not provisioned here:

- runtime reader: `SELECT` on families and snapshots only;
- technical snapshot writer: `INSERT` on the four aggregate tables through the
  bounded repository transaction;
- migration owner: DDL only during an explicitly approved migration;
- restore verifier: read-only hash/FK/trigger verification.

Direct `UPDATE`, `DELETE`, trigger bypass, lifecycle mutation, review, approval,
pointer selection, and activation privileges are outside 03A. Provisioning
these roles requires a separate infrastructure review and owner authorization.

## Consequences

- The documented legacy No-FK convention remains unchanged outside this new
  aggregate.
- A technically valid snapshot is neither reviewed nor approved and cannot be
  selected by the request runtime.
- Evidence schema v1 remains exactly `{ "state": "unbound" }`. MAT-EVID-01A
  uses a separate explicitly versioned evidence-manifest schema rather than
  mutating or reinterpreting v1 ruleset snapshots.
- Hash or schema drift returned by a database read is a quarantine candidate
  represented as a controlled technical error. MAT-GOV-03A performs no
  lifecycle mutation.
- MAT-GOV-03B and MAT-GOV-03C remain separate, owner-gated packages.
