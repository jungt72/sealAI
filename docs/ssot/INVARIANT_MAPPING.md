# SSoT Invariant Mapping

This map records implementation evidence, not aspiration. `partial` and
`remediation required` remain blocking states for the relevant activation.

| Principle | Implementation evidence | Verification | Status |
| --- | --- | --- | --- |
| P1 Kernel decides, LLM formulates | `backend/sealai_v2/core/calc/`, `core/l1_generator.py` | `backend/tests/architecture/test_i5_narration_no_numbers.py` | implemented |
| P2 No technical claim without status | `knowledge/ledger.py`, `db/models.py` | knowledge ledger tests | remediation required |
| P3 Unknown is a domain state | `core/case_state.py`, coverage contracts | case-state and coverage tests | partial |
| P4 Family orients, compound is assessed, component is externally released | Fachkarten kinds and framing | doctrine and response tests | partial |
| P5 State unknowns first | response contract and renderer | response-contract tests | partial |
| P6 Matching follows the technical case | partner ranking | partner tests | remediation required |
| P7 Field experience is evidence, not autopilot | contribution review queue | contribution tests | partial |
| P8 Product is the decision document | briefing renderer | briefing tests | remediation required |
| P9 Depth before breadth | feature flags and maturity manifest | SSoT governance tests | partial |
| P10 Boundaries are in the product | framing contract | frontend/backend framing tests | partial |
| P11 Technical fit is not purchasable | ranking excludes plan | partner neutrality tests | remediation required |
| P12 Every scope extension needs an eval gate | config flags and release gate | deploy-gate tests | remediation required |

| Gate | Current evidence | Status | Closure condition |
| --- | --- | --- | --- |
| G1 Tenant | server-derived identity and query scoping | implemented | keep cross-tenant suite green |
| G2 Evidence | Postgres ledger plus derived Qdrant index | remediation required | typed applicability and no approved source-less claims |
| G3 Kernel | deterministic calculation registry | implemented | no LLM numeric escape |
| G4 Approval | explicit orientation/release boundary | implemented | no sealingAI final release language |
| G5 Neutrality | ranking ignores plan, but paid membership gates pool | remediation required | verified capability pool separated from commercial participation |
| G6 Audit | knowledge reviews and case revision exist | partial | versioned case decisions, approvals, and responsibilities |
| G7 Release | manual final-only production workflow; production candidate rejected; immutable image and rollback | implemented | keep exact adjudicated evidence binding green |
| G8 Scope | many flags exist; no single maturity/activation contract | partial | maturity manifest and runtime activation policy enforced |
