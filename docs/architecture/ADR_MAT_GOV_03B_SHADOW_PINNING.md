# ADR: MAT-GOV-03B pointerless shadow pinning

Status: locally implemented, default-off, non-authoritative, and not approved
for production migration or activation.

Date: 2026-07-17

## Context

MAT-GOV-03A provides immutable, content-addressed technical snapshots but no
runtime selection. MAT-GOV-03B must prove deterministic pinning, tenant
isolation, durable ordering, cache binding, and bounded reconciliation without
creating an active pointer, approval state, public material statement, or
implicit normalization boundary.

MED-NORM-01 does not yet provide server-verified canonical material and medium
identifiers. Persisting prompt, answer, question, or extracted free text would
make an asynchronous evaluation irreproducible and create an unreviewed
normalization path.

## Decision

### Eligibility and authority

A shadow input is persistable only when material and exactly one contact medium
already carry server-verified canonical structured IDs, both resolution states
are `known`, cardinality is `single`, relation is `not_applicable`, and the
domain-pack identity and version are explicit. Unknown, ambiguous, missing,
multiple, free-text, separator-derived, or LLM-derived input is
`ineligible_unresolved_input` and creates no pin, job, evaluation, or cache
entry. No normalization is implemented here.

`ShadowMaterialRulesetPin` is a separate closed type. Its authority is
constructively `SHADOW_NON_AUTHORITATIVE`, `positive_statement_allowed` is
constructively false, and there is no authoritative pin type or public
serializer.

### Pointerless binding

Every immutable binding names one exact `snapshot_id` and expected
`content_sha256`, plus closed environment, purpose and scope types, domain-pack,
evaluator, kernel, runtime-profile, build commit/tree, finite validity interval,
creator, stable technical reason code, and sampling policy. Scope is either `GLOBAL` or
`TENANT_CANARY`; the canary tenant comes only from `VerifiedIdentity` and is
persisted solely as the key-versioned pair `(hmac_key_id, tenant_ref_hmac)`.
No raw tenant identifier is written to the shadow aggregate.

Production bindings are bounded to four hours and non-production bindings to
24 hours. Tenant canary precedes global, and a present invalid canary never
falls back to global. A PostgreSQL transaction advisory lock serializes each
verified tenant scope partition independently of the active HMAC key before a
keyring-wide overlap query. Retained old keys therefore cannot create a second
overlapping canary interval during rotation. A terminal event does not release
the original interval before `valid_until`.

There is no `latest`, file/environment/request snapshot selection, active
pointer, approval, deployment state, cohort, stage acknowledgment, or binding
management API.

### Atomic pin and outbox

Pin, immutable session version, monotone session sequence, and outbox job are
committed in one database transaction under a tenant/session advisory lock.
The exact stored binding is locked and revalidated before persistence. A pin
must be acquired inside its binding interval and cannot be created after an
effective `REVOKED` or `TERMINATED` event. There is no pin without a job and no
job without a pin. An explicit binding change creates a new immutable session
version and upgrade event; sessions never switch silently.

Durable rows contain only canonical IDs, typed states, version/hash references,
stable rule references and technical codes, and HMAC correlation references.
They never contain raw material/medium/question/answer/prompt/document text,
LLM material tendency, exception text, name, email, or raw tenant/session/case
identifier.

Tenant, session, request, case, and decision references use HMAC-SHA-256 with a
dedicated versioned `hmac_key_id`. The keyring is server-only and excluded from
runtime-profile hashes, logs, audits, and database rows. Old keys must remain
available for the full retention of records created under them. Every HMAC
input has a distinct versioned domain and uint32-big-endian-length-prefixed
UTF-8 fields. Session, case, request, and decision references bind the verified
tenant as a separate field; session rows persist tenant HMAC and key ID and use
all three values for lookup and uniqueness. Session lookup checks every retained
key version under a collision-safe key-independent transaction lock, so rotation
continues the existing immutable session lineage rather than silently creating
another one. Missing key material stops only shadow processing.

### Worker, cache and reconciliation

The isolated worker uses `FOR UPDATE SKIP LOCKED` together with a correlated
earlier-unfinished check, so a later sequence cannot overtake an earlier
pending or processing sequence. Claims have finite leases, retries are bounded
and exponential, evaluation plus job completion is atomic, and only stable
error codes persist. Each successful database-locked claim increments exactly
one attempt and records a worker owner plus an expiry derived from database
time. Completion and failure require the same unexpired owner lease. An expired
lease at the configured attempt boundary becomes immutable `failed` with
`SHADOW_LEASE_ATTEMPTS_EXHAUSTED`; it is neither requeued nor reconciled back.

The separate Redis namespace is `mat-shadow:v2:`. One central encoder binds
tenant HMAC/key version, snapshot ID/hash, evaluator/kernel/domain/policy
versions and the canonical input fingerprint as UTF-8 byte segments. The
versioned domain and every segment are encoded with an unsigned 32-bit
big-endian length before base64url projection, so empty, separator-bearing and
Unicode segments cannot collide. Unknown, legacy or malformed key versions are
cache misses and are never authoritative. Values contain reference-only
evaluation projections. Redis failure stops shadow; there is no in-process,
cross-snapshot, or last-known-good fallback.

Postgres remains the system of record. Process-local reconciliation is a
thread-safe map keyed by tenant HMAC/key ID, environment, purpose, scope,
domain-pack identity/version, runtime/build identity, evaluator/kernel version,
and the resolved binding when present. Only the exact partition can reuse its
lease. It polls every 15 seconds by default with deterministic +/-10 percent
jitter and a 60-second monotonic lease; DB timeout defaults to two seconds.
Expired leases cannot revive a prior selection. Shadow readiness is internal
and never changes primary readiness or creates a public 503 in this package.

### Runtime and activation boundary

All flags default false and sampling is frozen at exactly zero. The first
integration is exclusively `/chat`, post-response and exception-contained;
`/chat/stream` is unchanged. Since no canonical-ID provider exists before
MED-NORM-01, the production-facing seam returns `ineligible_unresolved_input`
before constructing a database or cache dependency. Flag-off performs no
shadow import, DB call, Redis call, prompt change, serialization change, or
frontend change.

The worker is not added to Compose, deployment, readiness, or production
process supervision. Individual evaluations expire after 90 days. Aggregate
metrics may be retained for 13 months, but sampling above zero remains blocked
until a tested purge process and maintenance role are separately owner-approved.

## Persistence boundary

Migration `20260717_0012` creates nine initially empty tables for bindings,
binding events, pins, session versions, session upgrades, outbox jobs,
evaluations, evaluation matches, and evaluation references. Internal foreign
keys use `ON DELETE RESTRICT`. Immutable payload tables reject update/delete;
the outbox permits only bounded operational state transitions. Additive empty
migration `20260717_0013` adds the owner-bound lease owner/expiry fields and
their atomic attempt-transition guards; it refuses a populated retrofit.
Adoption is allowed only when the complete catalog fingerprint matches the
known revision exactly, including ordered columns and types, checks, unique and
foreign-key semantics, indexes, predicates, triggers, and trigger-function
definitions. Adoption never drops, creates, or rewrites an existing object.
Partial or drifting schemas fail closed. Downgrade is allowed only while every
03B table is empty.

No existing case, decision, session, answer-cache, matrix, snapshot, prompt,
serializer, or frontend table is changed. The migration is not authorized for
production execution.

## Consequences

- MAT-GOV-03B can be tested locally without making any material assertion or
  establishing an activation path.
- Real requests remain ineligible until a later, separately governed canonical
  ID provider exists; no heuristic bridge is permitted.
- HMAC rotation preserves an existing pseudonymous shadow-session lineage while
  old key versions remain available for their retention period.
- MAT-EVID-01, MED-NORM-01, tested purge operations, both MAT-GOV-02 activation
  follow-ups, independent review, owner acceptance, and MAT-GOV-03C remain
  blockers.
- Active pointers, review/approval, deployment cohorts, CAS activation,
  rollback, admin mutation surfaces, production migration, and visible material
  output remain MAT-GOV-03C or later and are not authorized here.
