# ADR: MAT-EVID-01B fail-closed runtime evidence binding

- Status: accepted implementation, activation blocked
- Date: 2026-07-18
- Scope: technical shadow-only binding; no factual review or production use

## Decision

MAT-EVID-01B adds a separate, versioned companion to the immutable
MAT-GOV-03B binding and pin. It never changes MAT-GOV-03A schema v1 or the
canonical `MaterialConstraintMatch`, whose evidence state remains `unbound`.
The companion pins one exact ruleset snapshot ID/hash and either an explicit
`unbound` state or one exact MAT-EVID-01A manifest snapshot ID/hash in
`bound_unreviewed` state.

Before evaluation, every rule in the pinned ruleset must have at least one
object-exact claim binding. Foreign rules, missing rules, claim reuse across
rules, domain/version/hash drift, and any difference between rule and claim
scope fail closed. A claim may not support more than one rule in v1; multiple
claims for one rule remain allowed. No claim text is interpreted by this
package.

Technical binding grants only `TECHNICAL_UNREVIEWED` authority. It never
changes verdict, precedence, matches, decisive reference, or the existing
MAT-GOV-03B result hash and can never allow a positive statement. Integrity
failure produces a separate `integrity_blocked` result without verdict,
matches, or decisive reference. Evidence references are appended only to the
new isolated evaluation companion.

## Persistence and failure contract

Migration `20260718_0015` creates five initially empty tables for immutable
binding, pin, evaluation, evaluation-reference, and technical audit records.
All aggregate foreign keys are restrictive; database triggers reject update
and delete. Binding creation and pin capture write their shadow record and
evidence companion in one transaction. No pointer, review, approval,
deployment, seed, backfill, or public/admin API exists.

The separate `mat-evid-bind:v1:` cache key is collision-safe and binds tenant
HMAC/key identity, both snapshot IDs and hashes, binding/schema/contract
versions, evaluator/kernel/domain/runtime/build identities, and input hash.
Integrity-blocked results are never cached. Postgres remains the system of
record; no file, latest-snapshot, or last-known-good fallback exists.

## Activation boundary

`material_evidence_runtime_binding_enabled` defaults to `False` and requires
the already default-off 03B shadow and persistence flags. Sampling remains
owner-frozen at zero. The primary request pipeline, API serializers, prompts,
visible answer cache, frontend, matrix seed, and productspec remain unchanged.
Production migration, runtime activation, sampling, MAT-GOV-03C, and
deployment remain prohibited.
