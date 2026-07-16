# Owner Decision Register

Status: ratified with sealingAI SSoT v2.0 on 2026-07-10.

## ODR-01: Platform model

Decision: sealingAI is a neutral knowledge, engineering, and case platform with
optional manufacturer handoff. It is not a price-driven marketplace.

Consequence: technical fit is independent from monetization.

## ODR-02: Knowledge mode

Decision: general sealing questions belong to the product, but activation
requires M15.

Consequence: feature flag, adjudicated reference set, hard gates, and explicit
owner activation are mandatory.

## ODR-03: 360-degree scope

Decision: 360 degrees is target architecture and lifecycle vision, not a claim
of current completeness.

Consequence: every public and product surface carries honest maturity.

## ODR-04: Operating claim

Decision: "Dichtungstechnik. Von der Frage zur pruefbaren Entscheidung."

Consequence: lifecycle language remains a vision until outcomes are observed.

## ODR-05: Trust claim

Decision: "Vollstaendigkeit vor Empfehlung. Quellen vor Behauptung. Freigabe
vor Einsatz."

Consequence: alternatives require a new Owner Decision Record.

## ODR-06: Architecture

Decision: modular monolith, API-first, four deployables.

Consequence: extract a service only through an ADR with measured need.

## ODR-07: Manufacturer fit

Decision: capability-based fit is never purchasable.

Consequence: capability verification and ranking are auditable and separate
from commercial membership.

## ODR-08: Outcomes

Decision: outcomes mature from passive signal to validated field experience.

Consequence: no outcome claim exceeds the proven maturity level.

## ODR-09: Initial governed knowledge corpus

Decision: on 2026-07-12 the sealingAI owner approved all 79 claims in the
SSoT-v2 review queue. The reviewer identity is the Keycloak subject
`7748ba15-bef4-43b4-b95a-cf80fcc476d8`; the exact decision contract is
`docs/ssot/reviews/2026-07-12-owner-claim-approval.json`.

Consequence: 51 claims may rely on their recorded external technical
references. Twenty-eight claims are approved only as internal domain-expert
attestations, must not be presented as externally researched, carry the
conservative uncertainty/transferability states in the decision record, and
require revalidation by 2026-10-12. Any authority-fingerprint change
invalidates the corresponding approval. H1 activation still requires M15.

## ODR-10: Limited RWDR adaptive-interview cutover

Decision: on 2026-07-14 the sealingAI owner approved implementation and
production activation of the visible RWDR adaptive interview on
`rwdr.v1@1.0.1`. The 30 blinded, controlled cases in review set
`rwdr-shadow-controlled-v2` are accepted as sufficient for this limited RWDR
cutover. A separate production-derived review population and a paid Eval-REPLAY
are explicitly waived for this cutover. The signed evidence is preserved under
`docs/ssot/reviews/2026-07-14-rwdr-adaptive-interview-cutover/`.

Consequence: the backend controller owns the visible next-question decision for
explicit RWDR cases. The legacy frontend checklist remains display-only and is
the operational fallback when the active flags are disabled. The controller
must remain cost-neutral, tenant-scoped, pack-versioned, and reversible through
the documented flags. This decision does not activate another seal type, raise
the maturity of H2 as a whole, authorize technical release, or waive future
final-release evidence outside this bounded cutover.

## ODR-11: Material-constraint governance boundary

Decision: on 2026-07-16 the owner authorized MAT-GOV-01 and the default-off
MAT-GOV-02 governance implementation. The existing verdict values remain
canonical; `bedingt` remains opaque and every applicable condition remains
bound by stable rule reference. Every multiple-media state fails closed,
including a relation marked `resolved`, until MED-NORM-01. Internally
attested cells cannot create a positive compatibility statement, and
`matrix_compatible` means only that no documented incompatibility was found.
It cannot alone create `COVERED_RECOMMENDATION`. Conflicts and hard gates always
precede `unobtainable`. An `UNOBTAINABLE` override is valid only for an
explicitly enabled `primary_need_id` and only as a typed, version-bound,
server-validated audit record; related needs are never changed implicitly.

Consequence: MAT-GOV-02 owns typed preconditions, scope, null, unknown,
multiple-media, conflict, override, coverage and response-projection
invariants. `matrix_compatible` projects only to neutral
`PARTIAL_ENVELOPE + COVERED_CAUTION` while the governed path is active and
must show the non-release notice. MAT-GOV-03 owns ruleset persistence, activation,
rollback, and snapshot pinning. Produktspec remains default-off and is not
automatically migrated. Unreviewed LLM material tendencies cannot become
canonical or positive material statements. Executable RWDR thermal calculation
remains NO-GO. No material-rule activation follows from MAT-GOV-01/02.
