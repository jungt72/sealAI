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
- incident recurrence and rollback success

Activity metrics alone do not prove technical quality.
