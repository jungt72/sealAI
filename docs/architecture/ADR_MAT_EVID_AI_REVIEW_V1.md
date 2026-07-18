# ADR: MAT-EVID-AI-REVIEW.v1 non-human evidence challenge

Status: accepted for additive, non-production implementation. This foundation
creates no factual content; a subsequent isolated RP-001 automation run may
research and create only source-bound non-authoritative candidates under this
contract. Human review, factual approval, ruleset activation, public output,
production migration and deployment are not authorized.

Date: 2026-07-18

## Context

MAT-EVID-01C deliberately requires three distinct verified humans. The owner
also requires a transparent automated path in which Codex constructs exact,
source-bound disqualifying candidates, Claude Sonnet 5 independently challenges
them, and Codex adjudicates the structured findings. Calling that path
`reviewed` or placing AI agents in verified-human subject fields would collapse
the authority boundary.

## Decision

Introduce the separate contract `MAT-EVID-AI-REVIEW.v1`. Its identity kind is
always `ai_agent`, its authority is always
`AI_CROSS_REVIEW_NON_AUTHORITATIVE`, and positive statements are structurally
forbidden. The contract accepts only exact MAT-GOV-03A and MAT-EVID-01A.v2
`material_relation` snapshots containing atomic `unvertraeglich` or opaque
`bedingt` rules. Every referenced `med_…` identity must additionally be bound
to an exact MAT-EVID-01A.v2 `media_identity` snapshot and assertion hash. That
candidate remains non-authoritative and is deliberately not a verified
`MediumCatalogEntryV1`. The contract does not change or import MAT-EVID-01C.

Each review snapshot is content addressed and includes:

- non-production environment and tenant boundary;
- exact ruleset/evidence snapshot IDs, content hashes and domain pack;
- exact media-identity Evidence snapshot IDs, hashes, assertion identities and
  source-derived identity claims for every rule medium;
- atomic rule, claim, material, canonical medium and condition scope;
- exact source identity, digest, locator, rights state and permitted excerpt;
- source-independence groups, explicit conflicts and source-risk treatment;
- separate creator-agent model/version/prompt/run/input/output provenance.

Source eligibility fails closed. Missing locators or permitted excerpts,
unknown or restricted rights, dangling/self conflict references, a family-wide single-source claim,
or an explicit quarantine treatment cannot reach the challenger. High-risk
single-source claims require exact narrow-scope or opaque-`bedingt` treatment;
this mechanism cannot manufacture a second source or support a family rule.

The challenger is exactly `anthropic/claude-sonnet-5`. Its execution contract
requires tools, MCP, hooks, web search, web fetch and session persistence to be
disabled. The audit input excludes customer identity, tenant identity, Codex
reasoning and any preapproval. It includes only the frozen corpus and closed
invariants. The output is a closed, complete per-claim report with
`PASS | CHANGES_REQUIRED | QUARANTINE`. Transport failure, invalid JSON,
permission denial, wrong model usage or incomplete coverage is not a verdict.

Codex adjudication is a third run with independent run identity. Every finding
must be covered. CRITICAL/HIGH/MEDIUM findings may only be corrected in a new
immutable and exactly rebound ruleset/evidence snapshot pair, a new exact
media-identity Evidence snapshot, or quarantined.
Factual changes never reuse an old PASS. LOW findings can be recorded as
nonblocking only when no fact, scope, source, rights or governance invariant is
affected.

The closed AI lifecycle is `ai_draft`, `ai_challenged`,
`ai_cross_reviewed_non_authoritative`, `changes_required`, `quarantined`, and
`revoked`. Human or approval states do not exist in this aggregate. Revocation
and quarantine are append-only; no event grants activation authority.

## Persistence and isolation

Migration `20260718_0019` creates seven initially empty tables for batch,
review snapshot, challenge, adjudication, validation, lifecycle and audit.
Internal references use `ON DELETE RESTRICT`. PostgreSQL and SQLite triggers
reject update/delete, downgrade refuses populated tables, and exact catalog
fingerprints protect structural adoption. Tenant and non-production environment
are revalidated on every repository access. The repository exposes no update,
delete, approval, active pointer, sampling, API or deployment method.

The authenticated local Claude CLI is invoked once from a new private directory
outside the repository. Secret-bearing environment variables are removed.
Input and result are mode `0600`; the returned session identifier is hashed for
provenance and redacted from disk. There is no API-key fallback or automatic
retry.

## Consequences

- The verified-human MAT-EVID-01C path remains the only factual-review path.
- AI cross-review may improve traceability and red-team coverage, but it grants
  no human, factual, approval, release or deployment authority.
- No rule, claim, media identity or material fact is seeded by this package.
- A first RP-001 pack requires separately researched sources and immutable
  claim/rule snapshots; unsuccessful candidates remain quarantined.
- All material feature flags remain false and sampling remains zero.
- Production migration, MAT-GOV-03C, activation, public output and deployment
  remain frozen.
