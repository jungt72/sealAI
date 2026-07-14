# RWDR Adaptive Interview Phase 0/1

Status: `production_active_limited_rwdr`
Pack: `rwdr.v1@1.0.1`
Policy: `adaptive-interview.lexicographic.1.0.0`
Question catalog: `rwdr.questions.1.0.1`
Updated: 2026-07-14

This document records the owner-approved, visible RWDR slice. ODR-10 limits the
activation to explicit RWDR cases and does not raise the maturity of H2 as a
whole.

## Boundary

The one canonical decision path is:

```text
CaseStateV2 + derived facts + persisted interview state + rwdr.v1
  -> decide_next_interview_step(...)
  -> InterviewDecision
  -> optional NextQuestionPayload
```

The LLM is not reachable from this path. Retrieval, technical release,
calculation formulas, and answer generation are not part of the decision
object. Circumferential speed is read from the existing persisted derived
channel produced by `umfangsgeschwindigkeit`; the controller never implements
the formula.

## Baseline delta verified before implementation

- The canonical facts remain `CaseStateV2`, projected from `RememberedFact`
  rows and revisioned by the existing session `case_revision`; the interview
  state stores no second fact set.
- Existing edit and batch paths already use the canonical memory transaction,
  revision checks, and derived-slice recomputation. The controller hooks run
  only after those commits.
- The productive RWDR form submits `dichtungstyp` before its field values. The
  pack therefore starts only from an explicit RWDR case or an existing RWDR
  signal field; a general knowledge-only turn remains untouched.
- The existing `rauheit` field does not distinguish Ra from Rz. Both precise
  Need IDs remain inactive and the current value maps only to the explicitly
  ambiguous `rwdr.shaft.roughness` Need.
- `user-form` provenance was previously collapsed to generic `user` during the
  `RememberedFact` projection. The canonical projection now preserves
  `user_form`, including round-trip compatibility, so origin and verification
  remain semantically distinct.
- Existing `missing_information` remains an answer-body fallback. The backend
  `NextQuestionPayload` is the single visible next-question authority for an
  active RWDR case; the frontend RFQ checklist is display-only.

## Runtime evidence

| Concern | Canonical implementation |
| --- | --- |
| Typed contracts | `backend/sealai_v2/core/interview/contracts.py` |
| Lexicographic policy | `backend/sealai_v2/core/interview/policy.py` |
| Pack loader | `backend/sealai_v2/knowledge/domain_packs.py` |
| Pack data | `backend/sealai_v2/knowledge/domain_packs/rwdr.v1.json` |
| Orchestration | `backend/sealai_v2/pipeline/adaptive_interview.py` |
| Persistence | `backend/sealai_v2/db/interview.py` |
| Schema migration | `backend/sealai_v2/db/migrations/versions/20260713_0009_adaptive_interview_shadow.py`, `backend/sealai_v2/db/migrations/versions/20260714_0010_rwdr_pack_1_0_1_cutover.py` |
| API contract | `backend/sealai_v2/api/serializers.py`, `backend/sealai_v2/api/routes/conversations.py`, `frontend-v2/src/contracts.ts` |
| Visible projection | `frontend-v2/src/App.tsx`, `frontend-v2/src/components/Answer.tsx`, `frontend-v2/src/components/ChatPane.tsx` |
| Owner evidence | `docs/ssot/reviews/2026-07-14-rwdr-adaptive-interview-cutover/` |

## Feature gates

All gates default to `false` in Settings and `docker-compose.deploy.yml`:

```text
SEALAI_V2_ADAPTIVE_INTERVIEW_ENABLED
SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_ENABLED
SEALAI_V2_ADAPTIVE_INTERVIEW_PACK_RWDR_ENABLED
SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_REPORTING_ENABLED
```

Active or shadow mode requires the pack gate. Production runs active and
shadow observation together; all flags remain independent rollback controls.
While both mode flags are false, the service and repository are not
constructed.

## RWDR field mapping

The mapping layer preserves persisted field keys. `roughness_ra` and
`roughness_rz` are deliberately inactive because the current `rauheit` field
does not identify which parameter was entered.

| Existing field key | Need ID | Pack status | Source |
| --- | --- | --- | --- |
| `anwendungsziel` | `rwdr.application.goal` | active, required | explicit pack requirement |
| `medium` | `rwdr.medium.primary` | active, required | universal core |
| `betriebstemperatur` | `rwdr.temperature.operating` | active, required | universal core |
| `spitzentemperatur` | `rwdr.temperature.maximum` | active, optional | universal core |
| `druck`, `druck_max`, `druckrichtung` | `rwdr.pressure.regime` | active, required | universal core/RWDR |
| `druck` | `rwdr.pressure.normal` | active, optional | universal core |
| `druck_max` | `rwdr.pressure.maximum` | active, optional | universal core |
| `wellendurchmesser` | `rwdr.shaft.diameter` | active, required | RWDR pack/kernel binding |
| `gehäusebohrung` | `rwdr.housing.diameter` | active, optional | RWDR pack |
| `einbaubreite` | `rwdr.seal.width` | active, optional | RWDR pack |
| `drehzahl` | `rwdr.rotation.speed` | active, required | RWDR pack/kernel binding |
| derived `umfangsgeschwindigkeit` | `rwdr.circumferential_speed` | active, required, kernel-only | calc registry |
| `bauform` | `rwdr.profile.type` | active, optional | RWDR pack |
| `staublippe` | `rwdr.dust_lip.required` | active, optional | RWDR pack |
| `verschmutzung`, `spritzwasser`, `uv_aussen` | `rwdr.environment.external` | active, optional | RWDR pack |
| `schmierung` | `rwdr.lubrication` | active, optional | RWDR pack |
| `wellenwerkstoff` | `rwdr.shaft.material` | active, optional | RWDR pack |
| `haerte` | `rwdr.shaft.hardness` | active, optional | RWDR pack |
| `rauheit` | `rwdr.shaft.roughness` | active, optional/ambiguous parameter | RWDR pack |
| `rundlauf` | `rwdr.shaft.runout` | active, optional | RWDR pack |
| `versatz` | `rwdr.shaft.eccentricity` | active, optional | RWDR pack |
| `drall` | `rwdr.shaft.lead_free_surface` | active, optional | RWDR pack |
| none | `rwdr.medium.concentration` | future/inactive | no current field |
| none | `rwdr.temperature.minimum` | future/inactive | no current field |
| none | `rwdr.shaft.roughness_ra` | future/inactive | current field is ambiguous |
| none | `rwdr.shaft.roughness_rz` | future/inactive | current field is ambiguous |
| none | `rwdr.shaft.wear_groove` | future/inactive | no current field |
| none | installation/requirement/RFQ need IDs | future/inactive | no current field or approved rule |

The complete register and every question schema live in the versioned pack
JSON; this table is a navigation projection, not a second registry.

Patch `1.0.1` expands the application-goal question and its answer schema from
three to five represented goals: new design, replacement, retrofit,
optimization, and failure analysis. This is a catalog correction discovered
during the invalidated controlled review v1; it does not change policy order.

Migration `20260714_0010` performs the owner-approved transition to `1.0.1` by
deleting only reconstructable `rwdr.v1@1.0.0` pending interview state. It never
touches canonical CaseState, messages, derived values, or append-only shadow
decisions. The next reconciliation reconstructs pending state under `1.0.1`.

## Policy tiers

| Tier | Stable rule | Condition | Result |
| --- | --- | --- | --- |
| T0 | `AI-T0-SCOPE-001` | explicit unsupported primary case | escalate/out of scope |
| T0 | `AI-T0-VERSION-001` | pinned pack version unavailable | escalate; no migration |
| T2 | `AI-T2-CONFLICT-001` | active decision-critical conflict | clarify conflict |
| T2 | `AI-T2-CONFIRM-001` | required critical candidate not confirmed | confirm fact |
| T3 | `AI-T3-PENDING-001` | one pending question remains valid | continue it |
| T4 | `AI-T4-REQUIRED-001` | required need is unknown/partial | ask canonical question |
| T6 | `AI-T6-KERNEL-001` | inputs exist but required derived result is absent | escalate kernel fault |
| T6 | `AI-T6-COMPLETE-001` | required stop profile is documented | complete |

Within T4 the order is `dependency_depth`, `curated_domain_order`, descending
`downstream_unlock_count`, then stable `question_id`. No weighted score exists.

## Persistence and revision behavior

`v2_interview_state` is keyed by tenant, canonical session, and topic. It stores
only interview state coupled to `CaseStateV2`: pending questions, explicit need
status overrides, conflict history, tracked fact snapshots, and version refs.
It does not duplicate the canonical fact set.

The current session `case_revision` still owns fact concurrency. A fact edit or
batch submit increments that revision through the existing row lock. Shadow
evaluation stores the revision it observed and refuses to overwrite a newer
interview state. A changed decision-critical tracked value preserves both
candidate values and receives a stable conflict ID. Kernel derived values are
wholesale recomputed by the existing derived channel.

One active pending question per topic is enforced when patches are applied.
Version, catalog existence, need state, dependency snapshot, and directive
purpose are revalidated on every decision. A pending question from a future
state revision is invalidated; an older one may continue only while its
dependencies and Need remain valid. A new pack version does not silently
rewrite an open pending question. Existing unevaluated cases remain
`legacy_unversioned`; they are pinned only when actually evaluated.

## Shadow telemetry

The append-only log stores hashed case reference, state/pack/policy versions,
legacy-question presence and HMAC fingerprint, controller directive/question,
mapped legacy Need ID, rule refs, divergence, duration, and separated
completeness counts. It stores
no turn text, answer text, document body, secret, email, or exact user-facing
legacy question. `additional_llm_calls_by_controller` is always `0`.
Unsupported primary cases are still deterministically rejected by the pure
policy, but they create neither RWDR interview state nor RWDR shadow records.

The separate reporting flag exposes only an admin- and tenant-gated aggregate
at `GET /api/v2/admin/adaptive-interview/shadow-summary`. It returns counts,
rates, Need-transition counts, completeness, and latency percentiles. It never
returns case references, fingerprints, raw decisions, or question text and
always reports `automatic_activation_authorized=false`.

## Rollback

1. Set `SEALAI_V2_ADAPTIVE_INTERVIEW_ENABLED=false` to restore the visible
   legacy fallback. The pack and shadow flags may stay enabled for diagnostics.
2. Set all four adaptive interview flags to `false` and recreate the backend
   container to stop the service and reporting entirely.
3. No schema rollback is required. Migration `20260714_0010` deleted only
   reconstructable `1.0.0` pending state and its downgrade is intentionally a
   no-op. Never delete append-only shadow evidence as a runtime rollback.
4. Never downgrade production merely to disable the controller; flags are the
   operational rollback.

## Deferred deletion register

Retain during the limited cutover:

- free structured-answer `missing_information` questions in
  `backend/sealai_v2/core/l1_generator.py` and deterministic renderers;
- `RFQ_CORE_FIELDS` and `missingRfqCoreFields` in
  `frontend-v2/src/components/ChatPane.tsx` as display-only fallback;
- legacy fallback labels/mappings used by current form and compute panels.

`RFQ_CORE_FIELDS` has no question-selection authority. It remains only for the
disabled/out-of-scope fallback and RFQ presentation.

## Activation gate

ODR-10 authorizes the limited visible cutover based on 30 controlled blinded
cases. The owner explicitly waived a second production-derived review
population and paid Eval-REPLAY for this cutover. Migration, property,
contract, tenant-isolation, frontend, build, and production smoke checks still
apply to the exact served artifact. Automatic activation remains forbidden.
