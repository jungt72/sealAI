# SSoT Invariant Mapping

This map records implementation evidence, not aspiration. `partial` and
`remediation required` remain blocking states for the relevant activation.

| Principle | Implementation evidence | Verification | Status |
| --- | --- | --- | --- |
| P1 Kernel decides, LLM formulates | `backend/sealai_v2/core/calc/`, `core/l1_generator.py` | `backend/tests/architecture/test_i5_narration_no_numbers.py` | implemented |
| P2 No technical claim without status | typed claim lifecycle; claims without independent current human review quarantined; 79 owner-approved claims bound to exact authority fingerprints; source-less traps block-only; unsourced matrix inactive; MAT-GOV-02 forbids positive statements; MAT-GOV-03A stores only technically validated immutable snapshots whose evidence state is exactly unbound | knowledge, L3, matrix, material-constraint, neutral-coverage, MAT-GOV-03A hash/immutability/migration, and owner-review artifact tests | implemented technical boundary; H1 behavior gate M15, MAT-EVID-01, 03B/03C, and material-rule activation gates remain open |
| P3 Unknown is a domain state | `core/case_state.py`, coverage contracts, typed `NeedStatus`/`PendingQuestion` in `core/interview/`, orthogonal material input/cardinality/relation/evaluation states, typed blockers, and missing chemical coverage; every multiple cardinality including `resolved` is blocked before matrix access | case-state, coverage, adaptive-interview, exhaustive material-state, precedence, and no-matrix-access tests | partial; MED-NORM-01 remains open |
| P4 Family orients, compound is assessed, component is externally released | Fachkarten kinds, framing, and `MaterialConstraintResult.positive_statement_allowed=false` | doctrine, response, and material-constraint serialization tests | partial; no material-rule activation |
| P5 State unknowns first | response contract, typed material blockers, fail-closed adaptive-interview HTTP/SSE error, and renderer | response-contract, precedence, API, and streaming tests | partial |
| P6 Matching follows the technical case | verified Capability Profile registry is independent of billing | capability and partner tests | partial: H4 remains disabled pending pilot evidence |
| P7 Field experience is evidence, not autopilot | contribution review queue | contribution tests | partial |
| P8 Product is the decision document | immutable case snapshots, decision records, append-only reviews, and inert content-addressed MAT-GOV-03A technical snapshots | case-decision and MAT-GOV-03A snapshot/restore-contract tests | partial: material pinning and dashboard projection remain open |
| P9 Depth before breadth | feature flags and maturity manifest | SSoT governance tests | partial |
| P10 Boundaries are in the product | framing contract | frontend/backend framing tests | partial |
| P11 Technical fit is not purchasable | verified capability pool ignores commercial activation and plan | capability registry tests | implemented |
| P12 Every scope extension needs an eval gate | config flags, release gate, default-off `material_constraints_enabled`, MAT-GOV-02 typed preconditions, complete canonical evaluation, and inert MAT-GOV-03A identity/hash/persistence without runtime wiring | deploy-gate, flag-default, flag-off serialization/prompt, blocker precedence, canonical completeness, legacy projection, and 03A runtime-isolation tests | remediation required; MAT-GOV-03B/03C, MAT-EVID-01, both MAT-GOV-02 activation follow-ups, MED-NORM-01, and activation evidence open |

| Gate | Current evidence | Status | Closure condition |
| --- | --- | --- | --- |
| G1 Tenant | server-derived identity and query scoping | implemented | keep cross-tenant suite green |
| G2 Evidence | typed evidence/applicability/reviewer/expiry, stable logical claim IDs, authority fingerprint with automatic review invalidation, explicit human review origin, owner decision record for 79 claims, quarantine/Qdrant deletion, expiry check at resolution, block-only unsourced traps, default-off unsourced matrix | implemented | keep the 51 external and 28 internal-attestation evidence classes distinct; revalidate before their respective expiries |
| G3 Kernel | deterministic calculation registry | implemented | no LLM numeric escape |
| G4 Approval | explicit orientation/release boundary | implemented | no sealingAI final release language |
| G5 Neutrality | verified capability pool has no commercial projection; independent reviewer role, COI attestation, and self-recusal | partial | pilot broader affiliation disclosure/recusal operations and real reviewed profiles |
| G6 Audit | immutable case snapshots, evidence-bound decisions, SSoT review states, append-only non-self reviews, and append-only MAT-GOV-03A technical snapshot events | implemented technical foundation | keep tenant, evidence-binding, hash, trigger, and immutability contracts green; 03B/03C remain open |
| G7 Release | manual final-only production workflow; production candidate rejected; immutable image and rollback | implemented | keep exact adjudicated evidence binding green |
| G8 Scope | runtime maturity endpoint plus fail-closed knowledge, fit, handoff, and owner-approved explicit `rwdr.v1` interview scope gate | partial | keep ODR-10 rollback/evidence binding intact; migrate every remaining scope flag into the shared activation registry |
