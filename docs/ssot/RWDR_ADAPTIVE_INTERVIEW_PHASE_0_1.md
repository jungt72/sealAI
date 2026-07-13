# RWDR Adaptive Interview Phase 0/1

Status: `implemented_default_off`
Pack: `rwdr.v1@1.0.0`
Policy: `adaptive-interview.lexicographic.1.0.0`
Question catalog: `rwdr.questions.1.0.0`
Updated: 2026-07-13

This document records the implemented shadow slice. It does not activate a
public interview and does not raise product maturity.

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
- Existing `missing_information`, frontend `FIELD_PRIORITY`, response fields,
  and visible ChatPane behavior remain in authority during shadow.

## Runtime evidence

| Concern | Canonical implementation |
| --- | --- |
| Typed contracts | `backend/sealai_v2/core/interview/contracts.py` |
| Lexicographic policy | `backend/sealai_v2/core/interview/policy.py` |
| Pack loader | `backend/sealai_v2/knowledge/domain_packs.py` |
| Pack data | `backend/sealai_v2/knowledge/domain_packs/rwdr.v1.json` |
| Orchestration | `backend/sealai_v2/pipeline/adaptive_interview.py` |
| Persistence | `backend/sealai_v2/db/interview.py` |
| Schema migration | `backend/sealai_v2/db/migrations/versions/20260713_0009_adaptive_interview_shadow.py` |
| API contract | `backend/sealai_v2/api/serializers.py`, `frontend-v2/src/contracts.ts` |

## Feature gates

All gates default to `false` in Settings and `docker-compose.deploy.yml`:

```text
SEALAI_V2_ADAPTIVE_INTERVIEW_ENABLED
SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_ENABLED
SEALAI_V2_ADAPTIVE_INTERVIEW_PACK_RWDR_ENABLED
```

Active or shadow mode requires the pack gate. While both mode flags are false,
the service and repository are not constructed.

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
rule refs, divergence, duration, and separated completeness counts. It stores
no turn text, answer text, document body, secret, email, or exact user-facing
legacy question. `additional_llm_calls_by_controller` is always `0`.
Unsupported primary cases are still deterministically rejected by the pure
policy, but they create neither RWDR interview state nor RWDR shadow records.

## Rollback

1. Set all three adaptive interview flags to `false` and recreate the backend
   container only during an authorized release operation.
2. With both mode flags false the old response and frontend behavior remain in
   authority; no schema rollback is required.
3. If a development database schema rollback is explicitly required, first
   retain the append-only audit according to the data policy, then downgrade
   Alembic from `20260713_0009` to `20260713_0008`. This drops only the two new
   tables.
4. Never downgrade production merely to disable the controller; flags are the
   operational rollback.

## Deferred deletion register

Do not remove during shadow:

- free structured-answer `missing_information` questions in
  `backend/sealai_v2/core/l1_generator.py` and deterministic renderers;
- `FIELD_PRIORITY` and `missingRows` in
  `frontend-v2/src/components/ChatPane.tsx`;
- legacy fallback labels/mappings used by current form and compute panels.

`FIELD_PRIORITY` remains active during shadow phase. It must lose policy
authority and be deleted or reduced to display-only ordering after successful
frontend cutover.

## Activation gate

Shadow activation is not a product release. Before enabling it, migration
`20260713_0009` must be applied and the exact served tree must pass offline
contracts and schema checks. A later visible cutover requires owner review of
the RWDR stop profile, question wording, conflict resolution semantics, and
measured shadow divergence. No paid LLM eval is required for this cost-neutral
shadow implementation itself.
