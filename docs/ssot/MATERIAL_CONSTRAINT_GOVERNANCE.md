# Material-Constraint Governance

Status: MAT-GOV-01/02, the inert MAT-GOV-03A snapshot foundation, the
owner-accepted non-authoritative MAT-GOV-03B shadow/pinning foundation, and the
inert MAT-EVID-01A evidence-manifest foundation, MAT-EVID-01B fail-closed
runtime-binding companion, MAT-EVID-01C factual-review foundation, and the
inert MED-NORM-01 closed media-catalog foundation, and the MAT-RULES-01
reviewed-pack seam plus gap-only coverage inventory are implemented default-off
locally; no real material rule, reviewed catalog content,
material-rule activation, production migration, or production runtime binding
is authorized. MAT-GOV-03C and every activation gate remain
required. Owner decisions ratified through 2026-07-18.

This companion specification applies the ratified SSoT principles P1-P5 and
P12 to material constraints. It does not add material facts, media classes,
evidence, formulas, coefficients, or a release authority.

## Canonical contract

The only material-compatibility verdict values are the existing matrix values:

```text
vertraeglich
unvertraeglich
bedingt
```

`MaterialConstraintResult` is the canonical typed result. Material and medium
each carry an independent `known | missing | unknown | ambiguous` resolution
state. `MediumCardinality` separately records only the structurally established
count `none | single | multiple | unknown`; it performs no lexical or technical
medium normalization. Their relation is separately `undetermined | resolved |
unresolved | not_applicable`, and evaluation is `evaluated | blocked |
no_rule_data`. A verdict exists only for `evaluated`; its absence is never an
executable wildcard. `unobtainable` remains exclusively an adaptive-interview
`NeedStatus`.

The cross-field contract is closed: missing media are `none + undetermined`,
unknown or ambiguous media are `unknown + undetermined`, one known medium is
`single + not_applicable`, and multiple known media are either `multiple +
unresolved` or `multiple + resolved`. MAT-GOV-01 evaluates only the
single/not-applicable form. Every multiple cardinality is blocked, including a
relation marked resolved: that relation state alone does not prove that a
structured, separately evaluable list of contact media exists. No punctuation
or conjunction in free text is used to infer cardinality. MED-NORM-01 must
establish the structured media representation before any multiple-media
evaluation can become eligible. The unchanged public and legacy paths still
block all multiple media. The internal MED-NORM companion may evaluate
`known + multiple + resolved` only with separately identified components and
exactly one explicit relationship for every pair.

`bedingt` is opaque and cannot collapse into `vertraeglich`. Every applicable
conditional rule remains attached through its stable matrix-cell reference,
including when an incompatible rule wins the legacy precedence. The existing
Gegencheck response remains a backward-compatible projection and continues to
show only the strongest member of the winning category.

All matches are canonically ordered by verdict precedence, stable rule
reference, statement, and neutral source reference. Duplicate rule references
are invalid. Therefore `matches`, `conditions`, `decisive_ref`, and serialized
JSON do not depend on seed, input, or database order. The canonical evaluator
is complete and unbounded: every applicable match and condition is retained.
The historical six-hit bound exists only inside the Legacy-Gegencheck
projection, after the canonical verdict and decisive reference have been
computed from the complete result; projection cannot mutate that result.

The canonical `source_ref` is exactly `matrix-cell:<rule_ref>` and construction
rejects every other value.
`evidence_binding_state` is fixed to `unbound` until MAT-EVID-01 establishes a
claim/evidence/review binding. Legacy `Quelle` labels do not confer evidence or
review status on this contract.

`vertraeglich` and the legacy `matrix_compatible` projection mean only:

```text
keine dokumentierte Unverträglichkeit
```

They never authorize a positive compatibility statement, material selection,
component release, or `COVERED_RECOMMENDATION` on their own. The canonical
contract enforces `positive_statement_allowed=false` for every result.

## Preconditions and precedence

The evaluator accepts typed preconditions and emits canonically ordered stable
blocker references. It resolves them before any matrix access in this order:

1. authentication, tenant, legal, product, and approval hard gates;
2. explicit material-governance scope;
3. active case conflicts;
4. material and medium input resolution;
5. medium cardinality and relation;
6. material rules;
7. coverage;
8. response projection.

A blocked result carries no verdict, match, or decisive reference. Every
multiple cardinality is blocked before matrix access whether its relation is
`unresolved` or `resolved`. Recognized material candidates may establish
`ambiguous`; punctuation, conjunctions, slashes, or token concatenation never
establish media cardinality or a multi-medium evaluation.

`matrix_compatible` is an internal neutral state on the governed path. Its
maximum external projection is `PARTIAL_ENVELOPE + COVERED_CAUTION`, with
reason code `matrix_no_documented_incompatibility` and the exact notice:

```text
Keine dokumentierte Unverträglichkeit gefunden; daraus folgt keine Eignungs- oder Freigabeaussage.
```

Missing, unknown, ambiguous, or otherwise blocked chemical input maps to a
missing chemical axis, never to `not_applicable`. The legacy coverage and
prompt projection remain unchanged while `material_constraints_enabled=false`.

## Interview override and failure contract

`NeedState.is_documented` and `NeedState.is_completion_satisfying` are separate.
`BLOCKED` is documented but cannot produce `COMPLETE`. `UNOBTAINABLE` accepts
only a typed audit record with `need_id`, reason, actor reference, UTC time,
domain-pack version, and policy version. It is allowed only where the domain
pack explicitly enables the need as `primary_need_id`; related needs require
their own primary contract and are never updated as a side effect. Active
conflicts precede the override. Legacy untyped status dictionaries are rejected
and are not migrated implicitly. There is no public override writer.

Active adaptive-interview contract failures never collapse to `None`. Before a
normal response they project as HTTP 503 with the stable code
`adaptive_interview_unavailable`; after streaming starts they terminate the
stream with one error event and no normal result. Shadow-only operation remains
fail-open and non-authoritative. Domain-pack booleans accept only JSON booleans.

## Work-package boundaries

| Package | Binding scope |
| --- | --- |
| MAT-GOV-01 | Canonical typed result, unchanged verdict values, stable conditional references, legacy Gegencheck adapter, default-off additive serialization |
| MAT-GOV-02 | Typed preconditions; scope/null/unknown/multiple-media precedence; audited `unobtainable`; fail-closed interview errors; neutral coverage/response projection |
| MAT-GOV-03A | Versioned ruleset/snapshot identity, sealingAI JCS profile v1, domain-separated content hash, deep immutability, empty technical persistence and append-only technical audit; no runtime selection |
| MAT-GOV-03B | Pointerless exact-snapshot shadow bindings, canonical-input eligibility, pseudonymous request/session/evaluation pinning, isolated cache/worker and bounded reconciliation; owner accepted, default-off, sampling frozen at zero |
| MAT-GOV-03C | Evidence-bound ruleset approval, active pointers, cohorts, leases, CAS activation and rollback; NO-GO until evidence-bound rules and separate owner approval |
| MAT-EVID-01A | Versioned atomic claim/source identities, exact claim scope, structured rule-to-claim binding, content-addressed immutable manifests, empty persistence and technical audit; no runtime binding or authority |
| MAT-EVID-01B | Implemented inert/default-off fail-closed evidence binding in evaluation; technical binding grants no factual authority |
| MAT-EVID-01C | Implemented inert factual Evidence review with immutable dossiers, separate review/approval axes, and distinct verified-human creator/reviewer/approver; no runtime authority |
| MED-NORM-01 | Closed versioned media catalog, stable IDs, exact reviewed-Evidence provenance, structured components/relations, and internal per-medium attribution; initially empty and runtime-inert |
| MAT-RULES-01 | Repository-issued exact join of 03A/01A/01B/01C/MED-NORM for reviewed disqualify-only atomic rules, plus a content-addressed gap-only coverage inventory; no real rules or runtime integration |

MAT-GOV-01/02 contain no database migration or ruleset lifecycle. MAT-GOV-03A
and MAT-EVID-01A add only inert technical snapshot persistence and are not
imported by the request runtime. No package imports existing evidence or adds a
material rule, catalog entry, thermal model, or frontend recommendation.
`material_constraints_enabled` defaults to false. While false, the historical
Gegencheck code path and API payload remain unchanged and contain no
`material_constraints` key. Enabling the contract requires the separately
default-off compatibility matrix setting; an invalid flag combination is
rejected during settings validation.

## MAT-GOV-03A technical snapshot contract

Snapshot schema v1 contains the closed fields
`snapshot_schema_version`, `canonicalization_version`,
`mat_gov_contract_version`, `domain_pack_id`, fixed
`positive_statement_allowed=false`, and an ordered rule array. Every rule uses
the existing `MaterialConstraintVerdict`; 03A introduces no second verdict
taxonomy. Rule scopes contain the only explicitly set-valued fields:
`materials`, `media`, and `conditions`.

Evidence schema v1 is exactly:

```json
{"state":"unbound"}
```

No additional field, null value, claim/source/review/authority reference, or
bound/reviewed/approved/grounded state is accepted. MAT-EVID-01A introduces a
separate evidence-manifest schema version. Existing ruleset snapshots are never
mutated or reinterpreted.

Canonicalization v1 is the sealingAI I-JSON/JCS profile:

- duplicate properties, unknown fields, floats, non-finite numbers, implicit
  conversions, invalid Unicode, non-NFC strings, and BOMs are rejected;
- validated strings, prose, whitespace, line endings, case, media labels, and
  units are not normalized;
- JSON properties are recursively sorted and serialized as compact UTF-8
  without BOM;
- ordinary array order is retained;
- only the three typed scope sets are deduplicated and sorted by UTF-8 bytes.

The exact content identity is:

```text
canonical_bytes = UTF8(JCS_V1(validated_snapshot_payload))
content_sha256 = SHA-256(
  b"sealai.material-ruleset.content.v1\x00" + canonical_bytes
)
snapshot_id = "mss_" + SHA-256(
  b"sealai.material-ruleset.snapshot.v1\x00"
  + ASCII(ruleset_id) + b"\x00" + ASCII(content_sha256)
).hexdigest()
```

`ruleset_id` is server-generated as `mrs_<32 lowercase hex>`. Creator,
timestamp, future monotone version, lifecycle, review, audit, deployment, and
activation metadata do not enter the content hash. Schema, canonicalization
version, MAT-GOV contract version, domain pack, ordered rules, scopes, and the
unbound evidence object do enter it.

Four initially empty Postgres tables persist family identities, immutable
snapshots, technical validation events, and append-only technical audit events.
Internal foreign keys use `ON DELETE RESTRICT`; database triggers reject update
and delete. This is the bounded ADR exception to the legacy No-FK convention.
The repository exposes no update/delete/lifecycle API and revalidates schema,
bytes, hash, identity, and domain-pack binding on every read. Drift produces a
controlled quarantine-candidate error but no 03C lifecycle mutation.

03A performs no seed import, backfill, runtime dependency injection, pipeline
or cache integration, API/serializer/frontend change, pointer selection,
pinning, review, approval, activation, rollback, readiness, or reconciliation.
Its migration is not approved for production execution.

## MAT-EVID-01A immutable manifest contract

MAT-GOV-03A schema v1 remains unchanged and continues to mean exactly
`{"state":"unbound"}`. MAT-EVID-01A uses the separate closed manifest schema
`MAT-EVID-01A.v1`; no 03A payload is reinterpreted.

Each source identity requires `document_id`, `document_revision`,
`publication_edition`, and the source-content SHA-256 digest. `source_ref` is a
domain-separated hash of all four fields. A URL field is not part of the schema
and a URL can never be the sole source identity.

Each atomic claim has an NFC claim text, exact `materials`, `media`, and
`conditions` scope, and at least one source reference. `claim_ref` is a
domain-separated hash of claim text plus exact scope; source revision changes
therefore preserve logical claim identity, while text or scope changes create a
new claim identity. Every claim is explicitly bound through one or more
`rule_ref -> claim_ref` pairs to a rule in one exact immutable 03A snapshot.
Dangling, duplicate, and orphan references fail closed.

The manifest snapshot has its own schema and canonicalization version,
domain-separated content hash, and `mes_<hash>` identity bound to a stable
`mef_<id>` family. Strict JSON rejects duplicate/unknown properties, floats,
invalid or non-NFC Unicode, implicit conversions, and unsupported versions.
Sources, claims, source refs, typed scope sets, and bindings are canonically
ordered. Golden hashes freeze every identity and event-hash contract.

Four additive empty tables persist manifest families, snapshots, technical
validation events, and technical audit events. Restrictive foreign keys bind
the manifest to its exact 03A snapshot and preserve the new aggregate.
PostgreSQL and SQLite triggers reject update/delete. Every repository load
revalidates the complete evidence and 03A binding. The repository exposes no
review, approval, deployment, pointer, activation, public API, or runtime
selection method.

Technical validity proves only structural and cryptographic consistency. It is
not factual review, approval, compatibility, recommendation, or release.
MAT-EVID-01A imports no matrix text, legacy source label, existing evidence
card, RAG document, URL, seed, backfill, or LLM-generated content. MAT-EVID-01B
separately implements fail-closed evaluation binding. MAT-EVID-01C separately
implements factual evidence review; MAT-GOV-03C owns the still-separate
ruleset-approval and deployment axes.

## MAT-EVID-01A.v2 typed scope extension

RP001-OD-01 is implemented additively by `MAT-EVID-01A.v2`; v1 is not changed,
converted, copied, or reinterpreted. Version 2 uses a closed homogeneous target
and claim-scope discriminator:

- `material_relation` names one exact ruleset snapshot and permits only claims
  with non-empty `materials` and `media`, exact `conditions`, and complete
  object-specific `rule_ref -> claim_ref` bindings;
- `media_identity` names exactly one scalar `media_ref` and permits only claims
  containing that exact scalar and one exact identity-assertion reference. It
  has no `materials` property and no rule bindings.

Mixed variants, unknown properties, nullable or plural media identities,
target/scope drift, foreign rules, incomplete identities, and unsupported
versions fail closed. Version 2 has separate canonicalization and source,
claim, content, snapshot, validation, review, runtime-result, and audit hash
domains with frozen golden hashes. Fourteen additive empty v2 tables preserve
manifest, technical runtime-companion, and factual-review histories without
touching any v1 row.

`MAT-EVID-01B.v2` binds only `material_relation` manifests and pins exact v2
snapshot/hash/version/scope identities; it rejects `media_identity` as outside
the material evaluator. `MAT-EVID-01C.v2` reviews both variants object-exactly;
`media_identity` is restricted to `other_technical` and grants only
`FACTUAL_REVIEW_ONLY`. MED-NORM can validate that approved v2 identity-review
shape without a material placeholder. None of these seams creates a claim,
catalog entry, rule, positive statement, active pointer, sampling, public
projection, production migration, or deployment.

## MAT-EVID-01B fail-closed runtime binding

MAT-EVID-01B is a new companion contract and does not reinterpret either
MAT-GOV-03A v1 or MAT-EVID-01A v1. It pins an exact ruleset snapshot ID/hash and
an exact evidence-manifest snapshot ID/hash. The only binding states are
`unbound` and `bound_unreviewed`; the only authority gained by a technically
complete binding is `TECHNICAL_UNREVIEWED`. Positive material statements remain
constructively forbidden.

For `bound_unreviewed`, every rule in the exact ruleset requires one or more
claims. Each `rule_ref -> claim_ref` is resolved object-exactly; foreign or
missing rules, claim reuse across rules, hash/version/domain drift, and any
difference between rule scope and claim scope block before evaluation. Claim
text is never interpreted. The existing evaluator then runs unchanged, and
verdict, precedence, matches, decisive reference, and technical result hash are
preserved exactly. The evidence companion adds only immutable technical
references and its own envelope hash. Any integrity failure yields
`integrity_blocked` without verdict, matches, or decisive reference.

Five additive empty tables store immutable companions and append-only technical
audit events with restrictive foreign keys and update/delete triggers. The
separate collision-safe cache domain pins both snapshot identities and hashes,
all relevant versions, tenant HMAC identity, runtime/build identity, and input
hash; blocked results are not cached. No active pointer, review, approval,
deployment, public/admin API, seed, backfill, matrix import, or LLM evidence is
introduced. The feature defaults off, sampling remains zero, and production
migration and deployment remain prohibited.

## MAT-EVID-01C factual review foundation

MAT-EVID-01C adds a separate `MAT-EVID-01C.v1` content-addressed dossier pinned
to one exact 01A snapshot ID/hash/version. Every 01A source and claim is covered
object-exactly. Source metadata includes document identity, title, publisher,
closed document type, revision, edition, digest, exact-or-unavailable locator,
rights state and only an optional bounded short excerpt. Claim metadata repeats
the exact scope and declares a closed claim type plus required source types.
Conflict and supersession are typed relations; dangling references,
supersession cycles, incomplete coverage and inconsistent source requirements
fail closed.

Review and approval remain separate axes backed by a hash-chained append-only
event stream. Exact `VerifiedIdentity` actors must carry both a verified-human
role and the required create/review/approve role; creator, reviewer and approver
subjects are pairwise different. Unknown/restricted rights, unmet source-type
requirements and unresolved conflict/supersession block approval. Rejection,
revocation and quarantine are terminal fail-closed states. Technical binding is
not factual confirmation: even an approved dossier has only
`FACTUAL_REVIEW_ONLY` authority, keeps `positive_statement_allowed=false`, and
does not upgrade the 01B runtime state.

Every free 01C metadata field has an explicit character and UTF-8 byte ceiling.
01C approval also rejects referenced 01A atomic claim text above 512 characters
or 1024 bytes. This approval-only guard does not reinterpret MAT-EVID-01A.v1.

Migration `20260718_0016` adds five empty tenant-scoped immutable tables with
restrictive foreign keys and append-only validation, lifecycle and audit
events. There is no seed, backfill, public/admin API, pointer, activation,
frontend, cache, or deployment path.

## MED-NORM-01 closed normalization foundation

`MED-NORM-01.v1` is a separate immutable catalog schema. Every entry has a
stable media ID, exact canonical label, typed identity kind, optional exact
aliases, and exact approved MAT-EVID-01C review/hash/claim provenance. The
catalog is tenant-isolated and initially empty. It contains no built-in media
facts, generic fallback class, trade-name mapping, seed, or backfill.
The reviewed claim scope binds the derived media ID and a domain-separated hash
of the canonical name, identity kind, and complete alias set.

Evidence validation is version-explicit. Historical v1 identity reviews retain
their exact legacy material/media/condition shape. New identity reviews use
only the v2 `media_identity` scope with the exact scalar `media_ref` and
identity-assertion reference; no material placeholder is accepted. Both paths
remain tenant-bound, approval-dependent, and fail closed.

Only an exact whole-value match in one pinned catalog snapshot or a verified
user confirmation of an existing catalog entry can create a canonical
component. An LLM value is permanently a candidate and cannot satisfy the
canonical provenance contract. No punctuation, conjunction, fuzzy match, or
token heuristic establishes a medium or cardinality.
Resolution accepts only a tenant-bound capability issued after repository
revalidation of the exact approved Evidence. User confirmation is
domain-separated HMAC-bound to the verified tenant and subject, confirmation,
snapshot, and media; caller-supplied provenance strings carry no authority.
Every resolution invokes the non-serializable repository guard; evaluation
invokes it before and after component evaluation. Revocation or quarantine
therefore invalidates held capabilities and discards previously normalized
unpublished results without a last-known-good fallback.

Canonical medium components form a stable ordered tuple. Multiple known media
without relationships remain `multiple + unresolved`. A resolved set requires
exactly one explicit relation for every component pair. Unknown and ambiguous
inputs carry no canonical components and block before evaluation. The internal
companion evaluates every resolved component separately, preserves all matches
with component and media attribution, and uses the existing verdict enum and
precedence. It never permits a positive statement.

Four additive empty tables persist catalog families, snapshots, validation and
creation audit. Mutation triggers and restrictive foreign keys enforce
immutability. The repository revalidates tenant, catalog identity, hashes,
technical audit, and the exact approved factual-review state on every read.
There is no active pointer, `latest`, cache authority, public API, pipeline
import, or production migration authorization.

## MAT-RULES-01 reviewed rule-pack boundary

`MAT-RULES-01.v1` does not reinterpret any prior schema. It creates an internal
repository capability only after the exact 03A ruleset, 01B companion, 01A
manifest, approved 01C review/projection, and tenant-bound MED-NORM catalog
validate together. All dependencies are identity- and hash-pinned and are
reloaded before every authority-bearing access. Revocation, quarantine,
same-ID retargeting, catalog approval drift, tenant drift, or any content drift
invalidates the held capability without cache or last-known-good fallback.

Rules are atomic over one material, one canonical media ID, and one condition.
Only `unvertraeglich` and opaque `bedingt` are accepted. The complete rule
statement must equal exactly one approved primary claim of the matching closed
claim type. Supporting claims are limited to temperature, application, and
regulatory constraints. The capability has
`FACTUAL_REVIEWED_DISQUALIFY_ONLY` authority and permanently forbids positive
statements; it grants no activation or public-output authority.

`docs/ssot/material-rule-coverage-v1.json` is the separate
`MAT-RULES-COVERAGE.v1` gap inventory. It lists all 53 required material/service
subjects exactly once as `evidence_gap`, has authority
`NONE_EVIDENCE_GAPS_ONLY`, and contains no rule, claim, review, verdict, fact,
temperature, coefficient, or positive statement. No existing matrix prose or
knowledge-ledger claim is migrated. Creating a real rule pack requires new
exact Evidence and distinct verified-human creator, reviewer, and approver.

This package adds no persistence or migration because it composes the existing
immutable aggregates. It has no pointer, evaluator, pipeline, cache, API,
serializer, frontend, prompt, productspec, config, deployment, or activation
integration. MAT-GOV-03C remains blocked until a real reviewed rule pack exists.

## MAT-GOV-03B non-authoritative shadow contract

03B selects no snapshot implicitly. An immutable, time-bounded binding names
one exact 03A `snapshot_id` and `content_sha256` together with environment,
fixed shadow purpose, global or verified-tenant-canary scope, domain-pack,
evaluator/kernel/runtime/build identity, creator, reason, and a zero-percent
sampling policy. Tenant canary precedes global without fallback. Transactional
partition locks and exact overlap checks prevent concurrent bindings for the
same interval; revocation does not release the reserved interval early.

A persistable input requires server-verified canonical structured material and
single-medium IDs plus the closed `known + single + not_applicable` state. Free
text, unknown, ambiguous, missing, multiple, separator-derived, or LLM-derived
input is `ineligible_unresolved_input` and creates no pin, job, evaluation, or
cache entry. MED-NORM-01 now supplies an inert verified catalog seam, but no
public or shadow runtime adapter imports it before the later integration gate.

The shadow pin is always `SHADOW_NON_AUTHORITATIVE` and can never allow a
positive statement. Pin and outbox job are atomic; tenant/session/request/case/
decision correlation is domain-separated, uint32-length-prefixed HMAC-SHA-256
with a versioned key ID, never raw identity. Every subordinate reference binds
the verified tenant; session lookup and uniqueness additionally use the
persisted tenant HMAC.
Session versions are immutable and explicitly upgraded; a per-session advisory
lock and monotone sequence prevent concurrent creation or worker reordering.

The isolated `mat-shadow:v2:` cache namespace binds tenant HMAC/key version,
exact snapshot and hash, evaluator/kernel/domain/policy versions, and a
canonical input fingerprint through a versioned, uint32-length-prefixed UTF-8
encoding. Legacy, malformed and unknown key versions are cache misses.
The isolated worker persists only verdict/reference projections and stable
technical codes. Postgres remains authoritative; Redis and notification are
optimizations with no in-process, last-known-good, or cross-snapshot fallback.
Every database-locked worker claim consumes exactly one attempt and carries a
database-time lease owner/expiry. Expiry at the attempt boundary terminates the
job with `SHADOW_LEASE_ATTEMPTS_EXHAUSTED` and cannot requeue it.
Bounded reconciliation defaults to 15-second polling, a 60-second lease, a
two-second DB timeout, and deterministic jitter. Its thread-safe lease map is
partitioned by tenant/key, scope/binding, domain pack, runtime, build, evaluator,
and kernel; no partition can inherit another partition's lease.

All flags default false and sampling is fixed at zero. `/chat` capture occurs
only after the public answer and contains every exception. In the absence of a
server canonical-ID provider it stops before DB/Redis construction. Therefore
the public response, prompt, serializers, visible answer cache, productspec and
frontend remain unchanged. The worker has no Compose or deployment integration.

Migration `20260717_0012` is additive and empty. It creates only the isolated
binding/event/pin/session/outbox/evaluation aggregate with restrictive internal
foreign keys and mutation guards. Additive empty migration `20260717_0013`
adds only bounded worker-lease columns and transition guards and refuses a
populated retrofit. Neither migration adds a pointer, approval, deployment
state, cohort, stage acknowledgment, seed, backfill, public/admin API, or
case/decision mutation. Production execution is not authorized. Sampling above
zero remains blocked until a tested 90-day evaluation purge and maintenance role
exist; aggregate metrics may be retained for 13 months.

Pre-existing unpublished MAT-GOV objects are adopted only on an exact
dialect-specific catalog fingerprint covering columns, constraints, restrictive
FKs, indexes, predicates, triggers, and trigger-function definitions. Adoption
is read-only; name-only matches, partial objects, and semantic drift fail closed.

## Ratified owner decisions

1. Every multiple-media input fails closed in MAT-GOV-01. An unresolved
   relationship remains `unresolved`; `resolved` is a reserved fachlicher state
   but does not itself prove an evaluable structured media list. Activation of
   multiple-media evaluation belongs to MED-NORM-01 and MAT-GOV-02.
2. Internally attested matrix cells may block, caution, or remain conditional,
   but cannot create a positive compatibility statement.
3. `matrix_compatible` cannot alone create `COVERED_RECOMMENDATION`.
4. Existing Produktspec rules remain default-off and are not migrated
   automatically.
5. Unreviewed LLM material tendencies cannot create a canonical or positive
   material statement.
6. Conflicts and hard gates always precede `unobtainable`.
7. Executable RWDR thermal calculation remains NO-GO until separately sourced,
   reviewed, tested, and owner-activated.
8. Canonical media assignments require an exact Evidence-bound catalog entry
   or a verified user confirmation of such an entry. Model output remains a
   non-authoritative candidate.
9. A media-identity claim never receives a material placeholder. It requires a
   typed Evidence Manifest v2 `media_identity` scope with no `materials` field
   and exactly one `media_ref`; MAT-EVID-01A.v1 remains immutable.

Items 1, 2, 3, and 6 are enforced by MAT-GOV-02. Technical immutable snapshot
identity is implemented by MAT-GOV-03A, runtime pinning by MAT-GOV-03B, and the
inert fail-closed Evidence companion by MAT-EVID-01B, and factual Evidence
review by MAT-EVID-01C. Evidence-bound ruleset approval and activation require
MAT-GOV-03C. Structured multi-medium evaluation exists only in the inert
MED-NORM companion. Until initial reviewed catalog content and the remaining
packages, both MAT-GOV-02 activation follow-ups, independent review,
and owner activation are complete, the contract remains default-off and no
snapshot is approvable or active.
