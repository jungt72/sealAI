# SSoT Invariant Mapping

This map records implementation evidence, not aspiration. `partial` and
`remediation required` remain blocking states for the relevant activation.

| Principle | Implementation evidence | Verification | Status |
| --- | --- | --- | --- |
| P1 Kernel decides, LLM formulates | `backend/sealai_v2/core/calc/`, `core/l1_generator.py` | `backend/tests/architecture/test_i5_narration_no_numbers.py` | implemented |
| P2 No technical claim without status | typed claim lifecycle; claims without independent current human review quarantined; 79 owner-approved claims bound to exact authority fingerprints; source-less traps block-only; unsourced matrix inactive; MAT-GOV-02 forbids positive statements; MAT-GOV-03A stores technically validated immutable unbound snapshots; MAT-GOV-03B pins are constructively non-authoritative and positive-statement-disabled; MAT-EVID-01A stores only structurally valid immutable atomic claim/source manifests without approval authority | knowledge, L3, matrix, material-constraint, neutral-coverage, 03A/01A hash/immutability/migration, 03B authority/privacy/worker, and owner-review artifact tests | implemented technical boundary; H1 behavior gate M15, MAT-EVID-01B, 03C, and material-rule activation gates remain open |
| P3 Unknown is a domain state | `core/case_state.py`, coverage contracts, typed `NeedStatus`/`PendingQuestion` in `core/interview/`, orthogonal material input/cardinality/relation/evaluation states, typed blockers, and missing chemical coverage; every multiple cardinality including `resolved` is blocked before matrix access | case-state, coverage, adaptive-interview, exhaustive material-state, precedence, and no-matrix-access tests | partial; MED-NORM-01 remains open |
| P4 Family orients, compound is assessed, component is externally released | Fachkarten kinds, framing, and `MaterialConstraintResult.positive_statement_allowed=false` | doctrine, response, and material-constraint serialization tests | partial; no material-rule activation |
| P5 State unknowns first | response contract, typed material blockers, fail-closed adaptive-interview HTTP/SSE error, and renderer | response-contract, precedence, API, and streaming tests | partial |
| P6 Matching follows the technical case | verified Capability Profile registry is independent of billing | capability and partner tests | partial: H4 remains disabled pending pilot evidence |
| P7 Field experience is evidence, not autopilot | contribution review queue | contribution tests | partial |
| P8 Product is the decision document | immutable case snapshots, decision records, append-only reviews, inert content-addressed 03A snapshots and 01A evidence manifests, and separate pseudonymous non-authoritative 03B pins that never claim a real decision used the shadow snapshot | case-decision, 03A/01A snapshot/restore, and 03B pin/session/reference-isolation tests | partial: authoritative material evidence pinning and dashboard projection remain open |
| P9 Depth before breadth | feature flags and maturity manifest | SSoT governance tests | partial |
| P10 Boundaries are in the product | framing contract | frontend/backend framing tests | partial |
| P11 Technical fit is not purchasable | verified capability pool ignores commercial activation and plan | capability registry tests | implemented |
| P12 Every scope extension needs an eval gate | config flags, release gate, default-off `material_constraints_enabled`, MAT-GOV-02 typed preconditions, inert 03A identity/hash/persistence, owner-accepted default-off 03B with sampling fixed to zero and no canonical-ID bridge, and runtime-inert 01A evidence manifests | deploy-gate, flag-default, flag-off serialization/prompt/no-access, blocker precedence, canonical completeness, legacy projection, 03A/01A isolation, and 03B API/privacy/readiness tests | remediation required; 03C, MAT-EVID-01B, both MAT-GOV-02 activation follow-ups, MED-NORM-01, purge, final dark-staging audit, and activation evidence remain open |

| Gate | Current evidence | Status | Closure condition |
| --- | --- | --- | --- |
| G1 Tenant | server-derived identity and query scoping | implemented | keep cross-tenant suite green |
| G2 Evidence | typed evidence/applicability/reviewer/expiry, stable logical claim IDs, authority fingerprint with automatic review invalidation, explicit human review origin, owner decision record for 79 claims, quarantine/Qdrant deletion, expiry check at resolution, block-only unsourced traps, default-off unsourced matrix | implemented | keep the 51 external and 28 internal-attestation evidence classes distinct; revalidate before their respective expiries |
| G3 Kernel | deterministic calculation registry | implemented | no LLM numeric escape |
| G4 Approval | explicit orientation/release boundary | implemented | no sealingAI final release language |
| G5 Neutrality | verified capability pool has no commercial projection; independent reviewer role, COI attestation, and self-recusal | partial | pilot broader affiliation disclosure/recusal operations and real reviewed profiles |
| G6 Audit | immutable case snapshots, evidence-bound decisions, SSoT review states, append-only non-self reviews, append-only 03A/01A technical snapshot events, and immutable 03B binding/session/evaluation references with stable technical codes | implemented technical foundation | keep tenant, evidence-binding, hash, trigger, privacy, ordering, and immutability contracts green; 01B and 03C remain open |
| G7 Release | manual final-only production workflow; production candidate rejected; immutable image and rollback | implemented | keep exact adjudicated evidence binding green |
| G8 Scope | runtime maturity endpoint plus fail-closed knowledge, fit, handoff, and owner-approved explicit `rwdr.v1` interview scope gate | partial | keep ODR-10 rollback/evidence binding intact; migrate every remaining scope flag into the shared activation registry |
