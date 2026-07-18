# ADR: MED-NORM-01 closed media catalog

Status: implemented as an inert, default-off foundation on 2026-07-18. No
production migration, runtime activation, public projection, catalog seed, or
positive material statement is authorized.

## Context

The legacy extractor recognizes vocabulary copied from the unbound matrix and
stores a primary display string. It cannot prove whether punctuation denotes a
mixture, alternatives, sequential exposure, or separate contact media. The
MAT-GOV contract therefore blocks every multiple-medium input before matrix
access. A canonical medium identity must not originate from free text or an LLM.

## Decision

MED-NORM-01 introduces a separate closed schema `MED-NORM-01.v1`:

- stable full-SHA-256 `med_<id>` identities derived from exact canonical name
  plus explicit identity kind;
- immutable, content-addressed tenant catalog snapshots;
- exact canonical labels and aliases only; no token splitting or fuzzy match;
- an exact approved MAT-EVID-01C review snapshot, content hash, and claim refs
  for every catalog entry;
- structured component identities and explicit pairwise relationships for a
  resolved multiple-medium input;
- the existing `known | missing | unknown | ambiguous`, cardinality, and
  relation axes rather than a competing state taxonomy;
- exact catalog-evidence or verified-user-confirmation provenance for every
  canonical component;
- a permanently non-authoritative LLM-candidate value that cannot satisfy the
  canonical component constructor;
- a companion evaluator that evaluates every canonical component separately,
  retains medium attribution, applies the existing verdict precedence, and
  keeps `positive_statement_allowed=false`.

`unknown` and `ambiguous` have no canonical components. Multiple known media
without relations are `unresolved`. A resolved set requires exactly one
explicit relationship for every unordered component pair. A whole observed
value is compared exactly after strict Unicode validation; characters such as
`+`, `/`, comma, or conjunctions never establish cardinality.

The catalog is initially empty. No trade name, fluid class, refrigerant,
brake fluid, hydraulic fluid, additive system, or sterilization medium is
embedded or inferred. Those identities require separately reviewed Evidence.

## Persistence and authority

Migration `20260718_0017` creates four initially empty tables for catalog
families, immutable snapshots, technical validation, and creation audit. The
aggregate uses restrictive internal foreign keys, `ON DELETE RESTRICT`, and
database mutation triggers. The family is tenant-bound. The repository loads
the referenced factual review through a `VerifiedIdentity`, requires exact
content and claim refs, and requires factual approval before storage or read.
Each referenced claim must be `other_technical` and scoped to exactly the
derived media ID. Its sole condition must be the domain-separated hash of the
exact media ID, canonical name, identity kind, and complete alias set. A
compatibility, unrelated, or differently scoped identity claim cannot
authorize an identity mapping; changing an alias requires new reviewed
Evidence and a new immutable catalog snapshot.

Raw parsed snapshots are data only. Canonical resolution accepts an exact
repository-issued capability that binds the tenant after persisted hashes,
audit records, and current 01C approval have been revalidated. Directly
constructed or cryptographically consistent but unreviewed snapshots are
rejected. Catalog provenance contains that capability and the exact entry,
rather than caller-supplied hash strings. User-confirmation provenance is
created only by the server factory and domain-separated HMAC-binds the verified
tenant and subject, confirmation reference, catalog snapshot, and media ID.
The capability also carries a non-serializable repository guard. Resolution
and user confirmation revalidate the current 01C approval. Evaluation performs
both preflight and postflight revalidation, so revocation or quarantine before
or during evaluation discards the unpublished result. A held capability or
already-normalized input cannot use a cached or last-known-good approval.

The persisted authority is fixed to `NORMALIZATION_ONLY`; it cannot create a
material verdict, factual approval, recommendation, active pointer, or public
statement. Postgres remains the future source of record. There is no file,
cache, latest-snapshot, or last-known-good fallback.

## Compatibility boundary

The request pipeline, public runtime maturity response, prompt, serializers,
frontend, legacy extractor, matrix seed, Compose settings, and feature flags
remain byte-identical. The existing
single-medium shadow contract is unchanged. Public adoption belongs to the
later public-integration package and remains default-off. The canonical
`MaterialConstraintResult` is still the result for one medium; the new
multi-medium result is an internal attribution companion using the same
`MaterialConstraintVerdict`.

## Consequences

- MED-NORM-01 infrastructure is testable without introducing material facts.
- A catalog entry can be curated only after factual Evidence review.
- Technical normalization still grants no positive compatibility statement.
- Initial catalog content, evidence-bound rules, MAT-GOV-03C, public
  integration, staging migration, and activation remain separate gates.
