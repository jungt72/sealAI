# Quality Assurance Plan

Status: minimum operating model for H0-H2. External legal and specialist review
remain required where identified by the SSoT.

## Review roles

- Domain reviewer: validates technical meaning, applicability, and conflicts.
- Evidence reviewer: validates source identity, version, location, and license.
- Release owner: confirms tests, eval evidence, migration, rollback, and public
  maturity.
- Independent reviewer: required for critical claims, connected manufacturers,
  and conflict-of-interest cases.

No person or model may complete its own independent verification.

## Change control

Every authoritative claim and formula records version, reviewer, review date,
review expiry, evidence, applicability, transferability, uncertainty, and change
reason. A source or applicability change creates a new version; history remains
auditable.

## Validation

- Offline contract tests cover deterministic and tenant/security invariants.
- Targeted development evals cover changed behavior cheaply.
- Final activation requires the complete adjudicated reference replay for the
  exact served tree, model, and runtime behavior profile.
- New vertical slices require expert-reviewed reference cases and hard-gate
  tests before their maturity can be raised.
- The default-off `rwdr.v1` interview shadow uses deterministic unit,
  invariant, contract, migration, and golden-case tests only. It adds no LLM
  call. Paid evals remain skipped for Phase 0/1; later changed prompt/model
  behavior uses targeted failed-topic replay, and only final activation uses
  the full adjudicated reference replay.
- Shadow promotion follows `RWDR_SHADOW_REVIEW_PROTOCOL.md`: tenant-admin
  aggregate reporting, at least 30 reviewable divergence cases, and a blinded
  human A/B worksheet. The report cannot authorize activation itself.

## Incident and CAPA

An unsafe, unsupported, cross-tenant, neutrality, or release-integrity event is
a stop condition. The response is: contain or disable, preserve evidence,
rollback if necessary, assess impact, correct root cause, add regression proof,
and record the release/claim versions affected. Re-enable only through the same
gate that originally governed activation.

## Quality metrics

- unsupported authoritative claim rate
- evidence and applicability coverage
- expert acceptance/correction rate
- hard-gate escape rate
- first-pass manufacturer-ready completeness
- clarification loops and time to manufacturer-ready
- required-need completeness with satisfied, conflicted, unobtainable,
  not-applicable, and blocked states reported separately
- legacy-versus-controller question divergence and scope/hard-gate escapes
- additional LLM calls from the interview controller (target: zero)
- incident recurrence and rollback success

Activity metrics alone do not prove technical quality.
