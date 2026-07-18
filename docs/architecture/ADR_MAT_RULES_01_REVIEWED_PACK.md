# ADR: MAT-RULES-01 reviewed disqualify-only rule-pack boundary

Status: implemented as a runtime-inert capability and gap inventory on
2026-07-18. No material rule, factual claim, catalog entry, activation,
production migration, public output, or positive material statement is added.

## Context

MAT-GOV-03A can store immutable ruleset snapshots, MAT-EVID-01A/B can bind an
exact evidence snapshot technically, MAT-EVID-01C can record independent human
factual review, and MED-NORM-01 can issue a currently approved canonical-media
capability. None of those contracts alone proves that one material rule is
eligible for use. Existing matrix prose and the general knowledge ledger were
created under different contracts and cannot be imported or upgraded
automatically.

The completion Auftrag also requires a visible initial coverage result for a
closed set of material families and service groups. At this point no exact
rule/evidence/review/catalog chain has been supplied by three distinct verified
human subjects. Missing Evidence is therefore the correct result.

## Decision

`MAT-RULES-01.v1` introduces a repository-issued, non-serializable capability
that joins exactly:

- one MAT-GOV-03A ruleset snapshot and content hash;
- one MAT-EVID-01B `bound_unreviewed` companion;
- the exact MAT-EVID-01A manifest named by that companion;
- one approved MAT-EVID-01C review snapshot and its current lifecycle
  projection;
- one tenant-bound MED-NORM-01 catalog capability whose current approval is
  revalidated.

The capability is disqualify-only. A v1 rule verdict is exactly
`unvertraeglich` or opaque `bedingt`; `vertraeglich` is rejected. Every rule is
atomic over exactly one material, one canonical media ID, and one condition.
Its complete statement must equal exactly one approved primary atomic claim.
The primary claim type must be `incompatibility` for `unvertraeglich` or
`conditional_compatibility` for `bedingt`. Additional claims are restricted to
temperature, application, or regulatory constraints. All rule claims remain
complete, sorted and source-bound.

The repository is the only capability issuer and the private validator/binder
cannot be used from request-runtime code. Every authority-bearing access
revalidates the binding, ruleset, evidence, review projection, and catalog.
Same-ID retargeting, content drift, revocation, quarantine, tenant drift,
missing claims, non-atomic scope, claim-type drift, catalog drift, and statement
drift fail closed. There is no cache, `latest`, file fallback, or
last-known-good authority.

The separate `MAT-RULES-COVERAGE.v1` document is a strict content-addressed
gap inventory. Its authority is fixed to `NONE_EVIDENCE_GAPS_ONLY`, positive
statements are fixed false, and every required subject appears exactly once
with `evidence_gap` and empty rule/review references. It contains no rule,
claim, verdict, material property, temperature, coefficient, or approval.

## Compatibility and operational boundary

This package adds no model, table, migration, seed, backfill, pointer,
deployment state, evaluator integration, pipeline import, configuration flag,
prompt, serializer, productspec behavior, public API, or frontend component.
The existing request runtime, matrix seed, deployment configuration, and
material flags remain byte-identical. Sampling remains zero.

MAT-GOV-03C cannot begin from the gap inventory. Its prerequisite is at least
one real, exact rule/evidence/review/catalog chain created, reviewed and
approved by the required distinct verified human subjects. Codex cannot
self-review or self-approve factual material claims. The legacy matrix and the
79 general knowledge claims do not satisfy this new contract by implication.

## Consequences

- the full technical join can be tested with synthetic facts only;
- current revocation invalidates a held capability before reference access;
- positive family-level compatibility remains structurally impossible;
- all 53 requested initial coverage subjects are honestly visible as gaps;
- the next admissible step is human evidence curation and independent factual
  review, not MAT-GOV-03C activation work.
