# ADR: MAT-EVID-01C factual evidence review

- Status: accepted implementation, runtime use blocked
- Date: 2026-07-18
- Scope: immutable factual review dossiers and append-only human lifecycle only

## Decision

MAT-EVID-01C is a new versioned companion to one exact MAT-EVID-01A snapshot.
It does not reinterpret the accepted 01A or 01B contracts. A content-addressed
review dossier covers every and only every 01A source and claim and repeats the
exact source identity (document ID, revision, edition, and content digest) and
claim scope. It adds document title, publisher, a closed document type, an
explicit exact-or-unavailable locator, a closed rights state, an optional short
excerpt with a 280-character/1024-byte ceiling, claim type, required source
types, and typed conflict or supersession relations.

The dossier parser rejects duplicate JSON properties, non-NFC Unicode,
unknown fields and versions, ambiguous empty fields, incomplete coverage,
source/scope drift, dangling relations, inconsistent claim-type requirements,
and supersession cycles. Approval additionally fails closed when source rights
are unknown or restricted, when a claim lacks its declared required source
type, or while any conflict/supersession relation remains in the pinned
evidence snapshot. Correction requires a new immutable 01A and 01C snapshot.
No full standard text or long copyrighted passage belongs in this aggregate.

## Review and approval axes

Factual review and factual approval are separate typed axes. Review lifecycle
events are outside the dossier content hash and form an append-only,
sequence-numbered hash chain. Creation, review, and approval require exact
`VerifiedIdentity` values carrying the corresponding material-evidence role
and the verified-human role. Creator, reviewer, and approver subjects must be
pairwise different. No LLM or service process can satisfy that contract merely
by producing review text. Rejection, revocation, and quarantine are terminal
fail-closed transitions; historical snapshots and events stay reproducible.

`APPROVED` is only factual evidence review. Every snapshot and projection has
`runtime_authority=FACTUAL_REVIEW_ONLY` and
`positive_statement_allowed=false`. Technical 01B binding remains
`bound_unreviewed`; 01C does not upgrade it, change a verdict, select a ruleset,
or create a positive statement. Evidence-bound runtime use belongs to later,
separately reviewed packages.

## Persistence and activation boundary

Migration `20260718_0016` creates five initially empty tables for tenant-scoped
dossiers, content-addressed snapshots, technical validation events, lifecycle
events, and creation audit events. All internal foreign keys use `ON DELETE
RESTRICT`; SQLite and PostgreSQL triggers reject every update and delete. Every
load revalidates canonical bytes, hashes, the exact 01A snapshot, complete
source/claim coverage, and the unique validation/audit records. PostgreSQL is
the system of record; there is no cache, file, latest, or last-known-good path.

No seed, backfill, matrix import, public/admin API, feature activation, pointer,
deployment, frontend output, or production migration is introduced. Existing
material flags remain false and sampling remains zero. MAT-GOV-03C, MED-NORM-01,
evidence-bound rules, public integration, and deployment remain separate gates.
