# SSoT Invariant Mapping

This map records implementation evidence, not aspiration. `partial` and
`remediation required` remain blocking states for the relevant activation.

| Principle | Implementation evidence | Verification | Status |
| --- | --- | --- | --- |
| P1 Kernel decides, LLM formulates | `backend/sealai_v2/core/calc/`, `core/l1_generator.py` | `backend/tests/architecture/test_i5_narration_no_numbers.py` | implemented |
| P2 No technical claim without status | typed claim lifecycle; claims without independent current human review quarantined; 79 owner-approved claims bound to exact authority fingerprints; source-less traps block-only; unsourced matrix inactive | knowledge, L3, matrix, migration, and owner-review artifact tests | implemented; H1 behavior gate M15 open |
| P3 Unknown is a domain state | `core/case_state.py`, coverage contracts, typed `NeedStatus`/`PendingQuestion` in `core/interview/` | case-state, coverage, and adaptive-interview invariant tests | partial; rwdr.v1 limited production slice active |
| P4 Family orients, compound is assessed, component is externally released | Fachkarten kinds and framing | doctrine and response tests | partial |
| P5 State unknowns first | response contract and renderer | response-contract tests | partial |
| P6 Matching follows the technical case | verified Capability Profile registry is independent of billing | capability and partner tests | partial: H4 remains disabled pending pilot evidence |
| P7 Field experience is evidence, not autopilot | contribution review queue | contribution tests | partial |
| P8 Product is the decision document | immutable snapshots, decision records, append-only reviews | case decision tests | partial: dashboard projection remains open |
| P9 Depth before breadth | feature flags and maturity manifest | SSoT governance tests | partial |
| P10 Boundaries are in the product | framing contract | frontend/backend framing tests | partial |
| P11 Technical fit is not purchasable | verified capability pool ignores commercial activation and plan | capability registry tests | implemented |
| P12 Every scope extension needs an eval gate | config flags and release gate | deploy-gate tests | remediation required |

| Gate | Current evidence | Status | Closure condition |
| --- | --- | --- | --- |
| G1 Tenant | server-derived identity and query scoping | implemented | keep cross-tenant suite green |
| G2 Evidence | typed evidence/applicability/reviewer/expiry, stable logical claim IDs, authority fingerprint with automatic review invalidation, explicit human review origin, owner decision record for 79 claims, quarantine/Qdrant deletion, expiry check at resolution, block-only unsourced traps, default-off unsourced matrix | implemented | keep the 51 external and 28 internal-attestation evidence classes distinct; revalidate before their respective expiries |
| G3 Kernel | deterministic calculation registry | implemented | no LLM numeric escape |
| G4 Approval | explicit orientation/release boundary | implemented | no sealingAI final release language |
| G5 Neutrality | verified capability pool has no commercial projection; independent reviewer role, COI attestation, and self-recusal | partial | pilot broader affiliation disclosure/recusal operations and real reviewed profiles |
| G6 Audit | immutable snapshots, evidence-bound decisions, SSoT review states, append-only non-self reviews | implemented | keep tenant, evidence-binding, and immutability contracts green |
| G7 Release | manual final-only production workflow; production candidate rejected; immutable image and rollback | implemented | keep exact adjudicated evidence binding green |
| G8 Scope | runtime maturity endpoint plus fail-closed knowledge, fit, handoff, and owner-approved explicit `rwdr.v1` interview scope gate | partial | keep ODR-10 rollback/evidence binding intact; migrate every remaining scope flag into the shared activation registry |
