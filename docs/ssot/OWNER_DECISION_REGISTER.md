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

## ODR-12: MAT-GOV-03A technical snapshot foundation

Decision: on 2026-07-17 the owner authorized implementation of MAT-GOV-03A
only: versioned ruleset/snapshot identity, the sealingAI JCS profile v1,
domain-separated content addressing, deeply immutable domain values, additive
empty persistence, technical validation, and append-only technical audit. The
evidence object is exactly `{ "state": "unbound" }`; MAT-EVID-01A requires a
separate explicitly versioned manifest rather than mutation of v1.

Consequence: MAT-GOV-03A remains inert and default-off. It creates no request
pin, shadow selection, cache/readiness integration, active pointer, review,
approval, cohort, lease, activation, rollback, admin/public API, pipeline,
serializer, prompt, or frontend change. The matrix seed is neither imported nor
approved. The additive migration is not authorized for production execution.
MAT-GOV-03B and MAT-GOV-03C remain NO-GO pending separate owner adjudication;
MAT-EVID-01 and both MAT-GOV-02 activation blockers remain open. MED-NORM-01,
Produktspec, and RWDR-THERM-01 are unchanged.

## ODR-13: MAT-GOV-03B local shadow/pinning implementation

Decision: on 2026-07-17 the owner authorized one local MAT-GOV-03B commit on
the accepted 03A base. Shadow jobs require server-verified canonical material
and exactly one canonical medium ID. No free-text, separator, or LLM-derived
normalization is permitted; unresolved input creates no durable shadow object.
Bindings are pointerless, exact-snapshot, finite, append-only, tenant-scoped,
and sampling remains exactly zero. Pins and jobs are atomic, non-authoritative,
positive-statement-disabled, session-ordered, and correlated only through a
dedicated versioned HMAC-SHA-256 keyring.

Consequence: the implementation remains default-off and operationally inactive
for real unnormalized requests. The `/chat` seam is post-response and cannot
change public output; no worker is wired into Compose or deployment. Migration
`20260717_0012` is not authorized for production. Sampling above zero remains
blocked until a tested purge path and maintenance role exist. Independent
Claude-Sonnet-5 audit and explicit owner acceptance are still required for this
exact commit. Push, PR, merge, production migration, MAT-GOV-03C, MAT-EVID-01,
MED-NORM-01, active pointers, review/approval, activation, and visible material
output remain NO-GO.

## ODR-MAT-GOV-03B-20260717-01

### Decision

`ACCEPTED_AS_SEALED_IMPLEMENTATION_BASELINE`

MAT-GOV-03B is accepted as complete within its explicitly limited local,
non-authoritative, flag-off, zero-sampling shadow scope. This decision does not
authorize merge, production migration, activation, sampling, authoritative
use, MAT-GOV-03C, MAT-EVID-01, or MED-NORM-01.

### Sealed implementation

- Branch: `feature/mat-gov-03b`
- Commit: `da126b1a6a1f75faf4790de7115284a21099e290`
- Tree: `479728cb57717faf25219299d14345b9ffc530ae`
- Parent: `c650c44b70326949f2985e9f0ff7ae82bf2f931a`
- Commit count relative to parent: `1`
- Worktree at evidence capture: `CLEAN`

The sealed commit must not be amended, rebased, squashed, rewritten, or
force-pushed. All corrections must be implemented as traceable child commits.

### Audit evidence

- Auditor model: `claude-sonnet-5`
- Result: `APPROVED_WITH_NONBLOCKING_FINDINGS`
- Web accesses: `0`
- Permission denials: `0`
- Audit input SHA-256:
  `fb81a9f44e4d6f4797bd72816f79b964f64a6a3297243b064fec602a7b1d9465`
- Audit result SHA-256:
  `5bd5e153f292b698fce6154818d1fd541ac886bb72382c52070c3bb3524ceaaa`
- Controlled summary: `docs/audits/MAT_GOV_03B_AUDIT_SUMMARY.md`
- Durable raw-artifact location and retention:
  `PENDING_OWNER_PROVIDED_ARTIFACT_LOCATION`

The raw audit artifacts must be transferred from ephemeral storage to durable,
access-controlled artifact storage. Their durable location and retention policy
must be added to this record before merge adjudication.

### Mandatory findings

The following HIGH findings block merge, migration, activation, and sampling:

1. Cache-key segments must use collision-safe, versioned, length-prefixed or
   equivalently canonical encoding.
2. Every successful worker lease acquisition must consume an attempt.
   Repeatedly orphaned leases must eventually reach the configured limit and
   transition to a durable terminal state.

### Authorized actions

- Preserve and register the sealed commit.
- Push the unchanged branch to a protected remote reference.
- Open a Draft PR clearly marked as activation-blocked.
- Create traceable follow-up work from the sealed commit.
- Execute tests and independent audits in isolated environments.

### Prohibited actions

- Amend, rebase, squash, or otherwise rewrite the sealed commit.
- Merge before both HIGH findings are closed and re-audited.
- Execute the migration in production.
- Enable any MAT-GOV-03B runtime flag or increase sampling above zero.
- Add an activation or admin mutation path.
- Begin MAT-GOV-03C, MAT-EVID-01, or MED-NORM-01.
- Treat any shadow result as authoritative.

### Required next adjudication

A new Owner Adjudication is required after both HIGH findings are closed, the
full required test matrix and PostgreSQL concurrency/lease tests pass, flag-off
output remains byte-identical, the follow-up delta receives an independent
audit, and durable audit evidence is registered.

### Status

- MAT-GOV-03B implementation baseline: `ACCEPTED`
- Merge readiness: `HOLD`
- Production migration: `NO-GO`
- Activation readiness: `NO-GO`
- Sampling above zero: `NO-GO`
- MAT-GOV-03C: `NO-GO`
- MAT-EVID-01: `NO-GO`
- MED-NORM-01: `NO-GO`

## ODR-MAT-GOV-03B-20260717-05

### Decision

`INTERMEDIATE_CLAUDE_GATES_WAIVED_BY_OWNER`

Claude is no longer an intermediate implementation or review gate for the
current MAT-GOV-03B correction cycle. Codex leads implementation and internal
reviews. Exactly one external Claude-Sonnet-5 audit is deferred until after a
separately authorized dark-staging deployment.

### Consequence

This waiver creates no activation authority. Until that final audit passes,
all material flags remain `False`, sampling remains `0`, and no positive
material statement, ruleset activation, production migration, or production
deployment is authorized. The final external audit remains a prerequisite for
any later activation decision. MAT-GOV-03C, MAT-EVID-01, and MED-NORM-01 remain
`NO-GO`.

## ODR-MAT-EVID-01A-20260718-01

### Decision

`MAT_GOV_03B_OWNER_ACCEPTED` and `MAT_EVID_01A_PLAN_AND_IMPLEMENTATION_GO`.
The owner accepted MAT-GOV-03B at implementation head
`276cc84160d7411954629bf6adfd4852f29d5cba` and main merge
`5e24a235a4716c80b002628ad0d04e1c210e1a60`, with no open CRITICAL, HIGH, or
MEDIUM finding. The nonblocking `SHADOW_INVALID_PIN` error classification is a
registered follow-up.

The next authorized package is exclusively the additive MAT-EVID-01A
foundation: a new versioned evidence manifest, atomic stable claim identities,
complete source identities, exact claim scope, explicit rule-to-claim binding,
deep immutability, content-addressed snapshots, empty persistence, and
technical validation/audit events.

### Consequence

MAT-GOV-03A schema v1 is never changed or reinterpreted. No matrix text,
existing evidence, seed, backfill, URL-only source, or LLM-generated evidence
is imported. Technical evidence validity grants no factual review, approval,
recommendation, or deployment authority. Review, approval, and deployment stay
separate and remain MAT-GOV-03C scope.

MAT-EVID-01A adds no runtime activation, public/admin API, frontend projection,
or production migration. All material flags remain `False` and sampling stays
`0`. MAT-EVID-01B, MAT-GOV-03C, production migration, sampling, activation, and
deployment remain `NO-GO`. Intermediate Claude gates remain waived; Codex leads
implementation and cumulative review, while one external Claude-Sonnet-5 audit
remains required after a separately authorized dark-staging deployment and
before activation.

## ODR-MAT-EVID-01B-20260718-02

### Decision

`MAT_EVID_01B_PLAN_AND_IMPLEMENTATION_GO` is ratified as a strictly
default-off, non-authoritative runtime companion. Every rule in an exact
ruleset snapshot requires evidence; rule and claim scopes must be exactly
equal; one claim cannot support multiple rules; multiple claims per rule are
allowed. `bound_unreviewed` may carry the existing technical result unchanged,
but binding cannot create or change a verdict, precedence, match, decisive
reference, or positive statement.

### Consequence

The canonical `MaterialConstraintMatch` remains `unbound`. MAT-GOV-03A and
MAT-EVID-01A schema v1 are immutable and are not reinterpreted. Missing,
foreign, duplicated, contradictory, version-drifted, hash-drifted, or
scope-drifted bindings fail closed. Technical audit is append-only. A later
reviewed-evidence state requires a new contract; it cannot be added to 01A/01B
v1.

No existing matrix content is bound or seeded. No review, approval, public
API, frontend output, positive material assertion, production migration,
activation, sampling, or deployment is authorized. MAT-EVID-01C,
MED-NORM-01, MAT-GOV-03C, evidence-bound initial rules, dark staging, and the
single final external audit remain separate gates.

## ODR-MED-NORM-01-20260718-04

### Decision

`MED_NORM_01_PLAN_AND_IMPLEMENTATION_GO` is ratified by the autonomous material
intelligence completion Auftrag as an additive, empty and runtime-inert closed
media-catalog foundation. Canonical media require stable IDs and exact approved
MAT-EVID-01C provenance. Multiple media require structured components and
explicit relations. LLM output remains a candidate and cannot create a
canonical classification.

### Consequence

The implementation contains no media entries or material facts. Exact whole
catalog lookup and verified user confirmation are the only canonical
provenance forms; punctuation and token heuristics never release a
classification. The internal companion may evaluate separately identified,
resolved components and retains medium attribution, but the public pipeline,
legacy extractor, shadow capture, API, prompt, frontend and deployment remain
unchanged. Technical normalization grants no factual approval, verdict,
positive statement, active pointer, or deployment authority.

Migration `20260718_0017` is additive and initially empty and is not authorized
for production. Initial reviewed catalog content, evidence-bound material
rules, MAT-GOV-03C, public integration, dark staging, and the final external
audit remain separate gates. All material flags remain false and sampling
remains zero.

## ODR-MAT-EVID-01C-20260718-03

### Decision

`MAT_EVID_01C_FACTUAL_REVIEW_IMPLEMENTATION_GO` is ratified as a separate,
versioned and runtime-inert factual Evidence-review contract. One immutable
review dossier pins one exact MAT-EVID-01A snapshot, covers every source and
claim, binds complete document identity/metadata, exact claim scope, required
source types, rights/locator state, and typed conflict/supersession relations.

Creation, review, and approval require verified-human identities with separate
roles. Creator, reviewer, and approver are three different verified subjects.
Self-review, self-approval and model/service auto-approval fail closed.
Lifecycle events are append-only and hash-chained; revocation and quarantine
are terminal. Structured short excerpts are bounded; protected full texts and
long copyrighted passages are excluded.

### Consequence

Factual approval is not technical runtime authority. MAT-EVID-01A.v1 and
01B.v1 remain unchanged, 01B remains `bound_unreviewed`, and even an approved
01C dossier has `FACTUAL_REVIEW_ONLY` authority and cannot permit a positive
statement. The migration is additive and initially empty. No seed, backfill,
matrix import, public/admin API, frontend output, pointer, activation,
production migration, sampling, or deployment is authorized. MED-NORM-01,
evidence-bound rules, MAT-GOV-03C, public integration, dark staging, and the
single final external audit remain separate gates.
