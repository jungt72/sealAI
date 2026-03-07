# SealAI Blueprint v1.2 — Architecture Audit Report

**Date:** 2026-03-07
**Scope:** `backend/app/langgraph_v2/**`, adjacent services, state models, tests
**Blueprint:** `/home/thorsten/sealai/konzept/01_sealingai_blueprint_v1.2.docx`
**Mode:** READ-ONLY — no code changes

---

## 1. EXECUTIVE SUMMARY

**Verdict: NOT YET SAFE TO CLOSE BUILD PHASE.**

The implementation covers approximately 55-60% of Blueprint v1.2 by concept count, but the coverage is structurally uneven. Governance infrastructure is substantially implemented. Core state lifecycle and conflict resolution exist. However, several foundational blueprint concepts are either missing entirely, only declared in schema, or implemented under a fundamentally different architecture than specified.

### Key findings:

- The blueprint specifies a **5-layer state model** (Observed → Normalized → Asserted → Governance → Cycle Control). The implementation uses a **4-pillar architecture** (Conversation, WorkingProfile, Reasoning, System). These are fundamentally different decompositions. The 4-pillar model works but does not enforce the blueprint's mandatory state transition path.
- **No `observed_inputs` field exists anywhere.** User inputs flow directly into messages and extracted parameters — the blueprint's "Rohwerte, Units, Originalformulierungen" capture layer is absent.
- **No explicit normalization pipeline** with `identity_class` gating lookups exists. `ParameterIdentityRecord` is populated but its `lookup_allowed` and `promotion_allowed` flags are **never enforced** at runtime — only one filter in `node_prepare_contract` checks `identity_class == "confirmed"`.
- **No `MediumProfile`, `MachineProfile`, or `InstallationProfile`** typed asserted objects exist. Parameters live as flat fields on `WorkingProfile`.
- **No HITL interrupts** (`interrupt_before`) are wired in the current graph. The blueprint specifies three interrupt checkpoints (`snapshot_confirmation`, `rfq_confirmation`, `draft_conflict_resolution`) — none are implemented.
- **No three-agent parallel fan-out** via `Send()` as blueprint specifies. Fan-out exists but is material + mechanical (2 branches), not medium/machine/installation evidence agents (3 branches).
- **No `ResultContract`, `SealingRequirementSpec`, or `RFQDraft`** as specified in blueprint. Instead, `AnswerContract` and `RequirementSpec` exist with different schemas and semantics.
- **Conflict resolver is fully distributed** across `node_verify_claims` — not a standalone node. All 7 blueprint conflict types are exercised in runtime. Resolution status lifecycle (OPEN/RESOLVED/DISMISSED) works with fingerprint-based persistence.
- **RFQ admissibility gate** is robustly implemented with hard-blocker logic, `release_status` derivation, and BLOCKING_UNKNOWN enforcement. This is the strongest governance implementation.
- **Assertion cycle** with `analysis_cycle_id`, contract obsolescence, `superseded_by_cycle`, and revision tracking is operational but has only 2 unit tests.
- **Candidate clusters** (3-cluster model: plausibly_viable / viable_only_with_manufacturer_validation / inadmissible_or_excluded) are implemented deterministically in `candidate_semantics.py`.
- **Deterministic calculations** (chemical_resistance, material_limits, O-ring groove) exist and are enforced in `node_verify_claims` post-checks.
- **No `EvidenceClaim` schema with `claim_type`** (fact_observed / fact_lookup / fact_inferred / heuristic_warning / expert_pattern / manufacturer_specific_limit) exists anywhere in code.
- **No Graph DB** exists — blueprint's "Store 3 — Graph DB (ausschliesslich heuristisch)" is not implemented.
- **No `specificity_level` enum** (family_only / subfamily / compound_required / product_family_required) as blueprint defines. Instead, `CandidateItem.specificity` uses a different set: compound_specific / family_level / material_class / document_hit / unresolved.

---

## 2. TARGET vs REALITY MATRIX

| Blueprint Area | Target Concept | Actual Implementation | Evidence | Status | Risk |
|---|---|---|---|---|---|
| **State Schema** | 5-layer model (Observed/Normalized/Asserted/Governance/Cycle) | 4-pillar model (Conversation/WorkingProfile/Reasoning/System) | `sealai_state.py:990-996` | **DRIFTED** | HIGH — state transition path not enforced |
| **Observed Layer** | `observed_inputs` dict preserving raw user values | No equivalent field; messages only | Grep: zero matches for `observed_inputs` | **ABSENT** | MEDIUM — auditability gap |
| **Normalized Layer** | 3-stage pipeline with `identity_class` gating | `parameter_patch.py` assigns identity_class; single filter in `node_prepare_contract:620-631` | `_filter_identity_guarded_extracted_params()` | **PARTIAL** | HIGH — lookup_allowed never enforced |
| **Asserted Layer** | Typed profiles: MediumProfile, MachineProfile, InstallationProfile | Flat fields on WorkingProfile + legacy engineering_profile | Grep: zero matches for these types | **ABSENT** | MEDIUM — no type safety on asserted state |
| **Governance Layer** | release_status, rfq_admissibility, scope_of_validity, etc. | `GovernanceMetadata`, `RFQAdmissibilityContract`, `rfq_admissibility.py` | `rfq_admissibility.py:21-47` | **FULL** | LOW |
| **Cycle Control** | analysis_cycle_id, snapshot_parent_revision, contract_obsolete | `assertion_cycle.py`, `AnswerContract.obsolete/superseded_by_cycle` | `assertion_cycle.py:42-119` | **FULL** | LOW — only 2 tests |
| **Governance Enums: release_status** | inadmissible / precheck_only / manufacturer_validation_required / rfq_ready | Implemented identically | `RFQAdmissibilityContract:353-358` | **FULL** | LOW |
| **Governance Enums: rfq_admissibility** | inadmissible / provisional / ready | Implemented identically | `RFQAdmissibilityContract:346` | **FULL** | LOW |
| **Governance Enums: specificity_level** | family_only / subfamily / compound_required / product_family_required | Different set: compound_specific / family_level / material_class / document_hit / unresolved | `candidate_semantics.py:7-13` | **DRIFTED** | MEDIUM — mismatch with blueprint vocabulary |
| **Governance Enums: identity_class** | identity_confirmed / identity_probable / identity_family_only / identity_unresolved | Implemented as confirmed / probable / family_only / unresolved (without `identity_` prefix) | `ParameterIdentityRecord:373` | **PARTIAL** | LOW — naming difference only |
| **Governance Enums: claim_type** | 6 types for evidence classification | Not implemented anywhere | Grep: zero matches | **ABSENT** | HIGH — no evidence governance |
| **Governance Enums: conflict_severity** | 7 severity levels | 6 implemented (missing FALSE_CONFLICT as severity; it exists as conflict_type instead); adds WARNING not in blueprint; blueprint has SOFT → implemented as WARNING | `ConflictRecord:318-325` | **PARTIAL** | LOW |
| **Governance Enums: conflict_type** | 7 types | 9 types (7 from blueprint + FALSE_CONFLICT + UNKNOWN) | `ConflictRecord:304-314` | **FULL** | LOW |
| **Intent Layer** | 2-stage: LLM classification → deterministic validator | `frontdoor_discovery_node` (LLM) + `node_router` (deterministic) | `nodes_frontdoor.py`, `node_router.py` | **PARTIAL** | MEDIUM — not exactly 2-stage pipeline |
| **Risk-Driven Completeness Engine** | 7 categories, risk-based prioritization | Supervisor policy node has cost-based actions; `_REQUIRED_PARAMS_FOR_READY` list exists | `nodes_supervisor.py:47-53` | **PARTIAL** | HIGH — not risk-driven, field-based |
| **Three Depth Levels** | TRIAGE / PREQUALIFICATION / CRITICAL REVIEW | Not implemented as distinct modes | No evidence | **ABSENT** | MEDIUM |
| **Fast Brain Nodes** | intent_layer, normalization_engine, profile_builder, risk_completeness_engine, question_prioritizer, gate_checker, snapshot_confirmation | Distributed: frontdoor=intent, profile_loader≈profile, confirm_checkpoint≈gate; no normalization_engine or risk_completeness_engine nodes | Graph topology `sealai_graph_v2.py:320-404` | **PARTIAL** | MEDIUM |
| **Slow Brain Nodes** | 3 evidence agents (medium/machine/installation) via Send() | 2 analysis branches (material/mechanical) via normal edges | `sealai_graph_v2.py:374-377` | **DRIFTED** | MEDIUM — different decomposition |
| **Conflict Resolver Node** | Standalone node with 7-step resolver algorithm | Distributed across `node_verify_claims` (9 check functions) | `node_verify_claims.py:209-594` | **DRIFTED** | LOW — functionally equivalent |
| **Candidate Clusters** | 3 clusters with specificity_level | 3 clusters implemented; specificity uses different values | `candidate_semantics.py:149-184` | **FULL** | LOW |
| **Result Contract** | ResultContract with 14 mandatory fields | AnswerContract with different field set | `sealai_state.py:277-299` | **DRIFTED** | MEDIUM — different schema |
| **Sealing Requirement Spec** | SealingRequirementSpec with 12 mandatory fields | RequirementSpec with 4 fields | `sealai_state.py:263-274` | **DECLARATIVE** | HIGH — far from blueprint spec |
| **RFQ Builder** | RFQDraft with 10 mandatory fields | Not implemented; rfq_payload is deprecated dict | `ReasoningState:659` | **ABSENT** | HIGH — no RFQ generation |
| **HITL Checkpoints** | 3 interrupt points (snapshot, rfq, draft_conflict) | Zero interrupt_before in graph | Grep: zero matches in graph file | **ABSENT** | CRITICAL — no human-in-loop |
| **RAG Store 1 — Structured DB** | Deterministic lookups, material_compatibility schema | chemical_resistance.py + material_limits.py | `mcp/calculations/` | **PARTIAL** | MEDIUM — no full material_compatibility table |
| **RAG Store 2 — Vector Store** | Claim-structured embeddings | Qdrant with chunk embeddings, not claim-structured | `rag_orchestrator.py`, `knowledge_tool.py` | **PARTIAL** | LOW |
| **RAG Store 3 — Graph DB** | Heuristic-only graph traversal | Not implemented | No evidence | **ABSENT** | LOW — blueprint aspirational |
| **EvidenceClaim v1.2** | Structured claims with claim_type taxonomy | Not implemented | Grep: zero matches | **ABSENT** | MEDIUM |
| **Normalization Agent** | 3-stage pipeline (exact→fuzzy→LLM) with identity_class | Partial: identity_class assigned in parameter_patch; no explicit 3-stage pipeline | `parameter_patch.py` | **PARTIAL** | HIGH |
| **Trade Secret Handling** | Tenant isolation, operating_context_redacted | tenant_id scoping exists; no operating_context_redacted | `sealai_graph_v2.py:426-440` | **PARTIAL** | MEDIUM |
| **Turn Limit** | 12-turn hard limit | Implemented: max_turns=12, output_blocked flag | `ReasoningState:716-717` | **FULL** | LOW |

---

## 3. REAL SOURCES OF TRUTH

| Concept | Intended SoT (Blueprint) | Actual SoT | Competing Mirrors / Aliases | Drift Risk |
|---|---|---|---|---|
| **Assertion cycle** | `analysis_cycle_id` (string format `cycle_{session}_{n}`) | `reasoning.current_assertion_cycle_id` (int) + `reasoning.asserted_profile_revision` (int) | `working_profile.derived_from_assertion_cycle_id`, `system.derived_from_assertion_cycle_id` — three copies | MEDIUM — int vs string format differs from blueprint |
| **State revision** | `state_revision` (int, increments per change) | `reasoning.state_revision` | `reasoning.asserted_profile_revision` (parallel counter) | LOW — both increment together |
| **Answer contract** | `result_contract` (cycle-bound governance object) | `system.answer_contract: AnswerContract` | `reasoning.working_memory.material_requirements: RequirementSpec` (partial overlap) | LOW — single SoT |
| **Obsolete contract** | `contract_obsolete` flag on result_contract | `AnswerContract.obsolete` + `AnswerContract.obsolete_reason` + `AnswerContract.superseded_by_cycle` | None | LOW — clean |
| **Requirement spec** | `sealing_requirement_spec` (12 fields) | `AnswerContract.requirement_spec: RequirementSpec` (4 fields) | `reasoning.working_memory.material_requirements` (same object) | MEDIUM — two locations |
| **Missing critical params** | `unknowns_release_blocking` (governance layer) | `governance_metadata.unknowns_release_blocking` + `RequirementSpec.unknowns_release_blocking` + `RequirementSpec.missing_critical_parameters` | Three locations, partially overlapping | HIGH — fragmented |
| **RFQ admissibility** | `rfq_admissibility` enum on state root | `system.rfq_admissibility: RFQAdmissibilityContract` | `reasoning.rfq_ready` (deprecated bool, still read in fallback) | MEDIUM — legacy mirror |
| **Conflict records** | `conflicts: list[Conflict]` in result_contract | `system.verification_report.conflicts: List[ConflictRecord]` | `engineering_profile.conflicts_detected` (legacy combinatorial guard) | HIGH — two separate schemas |
| **Final output text** | governed_output_text | `system.governed_output_text` | `system.final_text`, `system.final_answer` (legacy mirrors, always set alongside) | MEDIUM — triple write |
| **User persona** | `user_persona` on state | `conversation.user_persona` | `reasoning.flags` may carry persona hints | LOW |
| **Identity classification** | `identity_class` per normalized field | `reasoning.extracted_parameter_identity: Dict[str, ParameterIdentityRecord]` | None | LOW — single location |

---

## 4. CRITICAL ARCHITECTURAL GAPS

### GAP 1: No HITL Interrupts (CRITICAL — Operational Risk: HIGH)
The blueprint specifies three `interrupt_before` checkpoints:
1. `snapshot_confirmation` — freeze Working Profile before Slow Brain
2. `rfq_confirmation` — user confirms RFQ before sending
3. `draft_conflict_resolution` — user resolves conflicting parameters

**None are wired.** The graph runs from START to END without any interrupt. `confirm_checkpoint_node` and `confirm_recommendation_node` are declared in `STABLE_V2_NODE_CONTRACT` but **not added to the graph builder** in `create_sealai_graph_v2()`.

This means: no user can confirm a working profile snapshot, approve an RFQ, or resolve a parameter conflict interactively. The system operates in full-auto mode with zero governance checkpoints.

**Evidence:** `sealai_graph_v2.py:309-424` — no `interrupt_before` call anywhere.

### GAP 2: No Observed → Normalized → Asserted Enforcement (HIGH — Structural Risk)
The blueprint's core invariant is: "Kein Agent darf direkt von observed_inputs nach asserted_* schreiben." The current implementation has no enforced transition path. Parameters extracted by the LLM (`node_p1_context`, `frontdoor_discovery_node`) are written directly into `working_profile.extracted_params` and `working_profile.engineering_profile` without passing through a normalization stage that gates on `identity_class`.

`lookup_allowed` and `promotion_allowed` in `ParameterIdentityRecord` are computed but **never checked** before parameters are used in calculations, RAG lookups, or candidate generation.

**Evidence:** `parameter_patch.py` assigns identity records; `node_prepare_contract.py:620-631` is the only place that checks `identity_class`, and only for filtering extracted params into resolved_parameters, not for gating lookups.

### GAP 3: SealingRequirementSpec is Skeletal (HIGH — RFQ Readiness Risk)
Blueprint specifies 12 mandatory fields including `operating_envelope`, `dimensional_requirements`, `normative_references`, `material_family_candidates`, `material_specificity_required`, `manufacturer_validation_scope`, `assumption_boundaries`, `invalid_if`, `open_points_visible`.

Current `RequirementSpec` has 4 fields: `operating_conditions`, `missing_critical_parameters`, `exclusion_criteria`, `unknowns_release_blocking`. The blueprint's SRS example (Section 08) is not achievable with current schema.

**Evidence:** `sealai_state.py:263-274`.

### GAP 4: No RFQ Generation Pipeline (HIGH — Business Value Risk)
`RFQDraft` does not exist. `rfq_payload` is a deprecated dict on `ReasoningState`. No node generates a structured RFQ. No manufacturer matching logic exists. The entire Section 08 of the blueprint (RFQ Builder) is unimplemented.

**Evidence:** Grep for `rfq_draft`, `RFQDraft`, `rfq_confirmed` — zero results.

### GAP 5: Evidence Claim Taxonomy Missing (MEDIUM — Governance Risk)
Blueprint defines `EvidenceClaim` with 6 `claim_type` values governing which sources can carry which decisions. No equivalent exists in code. RAG results are untyped chunks without claim classification. This means: there is no mechanism to distinguish whether a statement is `fact_lookup` (hard gate allowed) vs `heuristic_warning` (annotation only).

**Evidence:** Grep for `claim_type`, `fact_observed`, `EvidenceClaim` — zero results.

---

## 5. STATE HYGIENE / PAYLOAD HYGIENE FINDINGS

### 5.1 Flat Aliases
The `_migrate_flat_payload` model_validator on `SealAIState` (lines 1004-1052) accepts both flat and pillar-nested payloads. This enables backwards compatibility but also enables drift: any node can still emit flat keys (`final_text`, `last_node`, etc.) and they will be routed to the correct pillar. This is a convenience migration layer, not a governance enforcement.

**Risk:** Nodes that emit mixed flat+pillar payloads may work today but create confusion about canonical shapes.

### 5.2 Triple Output Write
`node_finalize` writes the final answer to three locations simultaneously:
- `system.governed_output_text` (primary SoT)
- `system.final_text` (legacy mirror)
- `system.final_answer` (legacy mirror)
Plus flat keys `final_text`, `final_answer` in the patch root.

**Evidence:** `node_finalize.py:350-368`.

### 5.3 Conflict Schema Split
Two incompatible `ConflictRecord` classes exist:
1. Blueprint v1.2 schema in `sealai_state.py:302-331` (used by answer subgraph)
2. Legacy schema in `services/rag/state.py` (used by `combinatorial_chemistry_guard_node`)

The guard's conflicts go into `engineering_profile.conflicts_detected` and are never merged with the v1.2 conflicts in `verification_report.conflicts`. They are separate governance worlds.

### 5.4 Reducer Behavior for WorkingProfile
`merge_working_profile` uses deep-merge-right-wins for list fields (dedup+append) and dict fields (update). For scalar fields, right value wins if set. This is reasonable but means: a node emitting `None` for a field will NOT clear it (because `exclude_none=True` in `model_dump`). This could lead to stale values persisting across turns.

### 5.5 derived_artifacts_stale Triplication
`derived_artifacts_stale`, `derived_artifacts_stale_reason`, `derived_from_assertion_cycle_id`, `derived_from_assertion_revision` appear on:
- `WorkingProfile` (lines 573-575)
- `ReasoningState` (lines 643-644)
- `SystemState` (lines 773-776)

All three copies are set by `assertion_cycle.py` during cycle bumps and cleared by `stamp_patch_with_assertion_binding`. This works but is fragile: if any path writes one copy without the others, stale detection breaks.

---

## 6. CONFLICT RESOLVER DEEP DIVE

### 6.1 Architecture
There is **no standalone conflict_resolver node**. Conflict detection is fully embedded in `node_verify_claims` (answer subgraph) via 9 dedicated check functions. This is architecturally different from the blueprint's standalone node but functionally complete.

### 6.2 Active Conflict Types (All 7 Blueprint Types + 2 Extensions)

| Type | Check Function | Severity | Trigger | Status |
|---|---|---|---|---|
| SOURCE_CONFLICT | `_check_resistance_claims()`, `_check_limits_claims()` | HARD | Chemical resistance contradiction, material limit violation | ACTIVE |
| SCOPE_CONFLICT | `_check_scope_conflicts()` | WARNING | Vague suitability language ("typischerweise", "oft") | ACTIVE |
| CONDITION_CONFLICT | `_check_condition_conflicts()` | HARD | Positive claim + missing critical parameters | ACTIVE |
| COMPOUND_SPECIFICITY_CONFLICT | `_check_specificity_conflicts()` | RESOLUTION_REQUIRES_MANUFACTURER_SCOPE | Draft mentions specific grade but contract has family-only | ACTIVE |
| ASSUMPTION_CONFLICT | `_check_assumption_conflicts()` | WARNING | Draft sounds certain while evidence is limited | ACTIVE |
| TEMPORAL_VALIDITY_CONFLICT | `_check_temporal_validity_conflicts()` | WARNING | Draft claims permanence while evidence is snapshot-bound | ACTIVE |
| PARAMETER_CONFLICT | `_check_parameter_conflicts()`, `_check_blocking_unknowns()` | WARNING / BLOCKING_UNKNOWN | Draft values differ from contract; draft claims without authority | ACTIVE |
| FALSE_CONFLICT | `_apply_resolution_status()` | (type, not severity) | Always set to DISMISSED | ACTIVE |
| UNKNOWN | Default in ConflictRecord | — | Never created in runtime | DECLARATIVE |

### 6.3 Resolution Status Lifecycle

- **Creation:** All conflicts created with `resolution_status="OPEN"` (default)
- **Persistence:** `_apply_resolution_status()` (line 653-684) uses fingerprint matching to preserve statuses across patch loops
- **Fingerprint:** Normalizes summary by removing numbers, quoted content, list brackets, whitespace
- **FALSE_CONFLICT special rule:** Always forced to `DISMISSED` (line 680-681)
- **RESOLVED status:** Never set by code — no automated resolution exists. Would need to be set by HITL (which doesn't exist)
- **Blocking logic:** Only OPEN conflicts with severity HARD/CRITICAL/BLOCKING_UNKNOWN/RESOLUTION_REQUIRES_MANUFACTURER_SCOPE block verification (line 860-864)

### 6.4 Robustness Assessment

**Strengths:**
- All 7 blueprint types are genuinely exercised in runtime
- Chemical resistance and material limits checks are deterministic (no LLM)
- Fingerprint-based status persistence prevents flip-flopping across patch loops
- FALSE_CONFLICT auto-dismissal is sound

**Weaknesses:**
- **RESOLVED status never reachable** — no code path sets it. Only HITL could, but HITL doesn't exist
- **No re-detection sync for non-verify paths** — conflicts are only created during answer subgraph verify_claims; if a user modifies parameters and the answer subgraph doesn't re-run, stale conflicts persist
- **SCOPE_CONFLICT detection is heuristic** — regex-based gray-zone language matching may produce false positives or miss edge cases
- **ASSUMPTION_CONFLICT uses certainty markers list** — static keyword list ("sicher", "garantiert", etc.) is brittle against paraphrasing
- **No compound_specificity awareness in candidate_semantics vs verify_claims** — candidate_semantics uses a different specificity vocabulary than the verify_claims checks

### 6.5 Blueprint Deviation
Blueprint specifies a 5-step resolver algorithm:
1. Check validity spheres → FALSE_CONFLICT
2. Classify conflict type
3. Apply evidence hierarchy (Rang 1 schlägt Rang 3)
4. Determine conservative value
5. Escalate to BLOCKING_UNKNOWN or RESOLUTION_REQUIRES_MANUFACTURER_SCOPE

Current implementation: Steps 1+2+5 are covered. Steps 3+4 (evidence hierarchy, conservative value determination) are NOT implemented. The resolver detects and classifies conflicts but does not resolve them by applying source ranking or computing conservative values. This is acceptable for current use (conflicts surface to user/HITL) but means the system cannot auto-resolve source conflicts.

---

## 7. TEST EVIDENCE ASSESSMENT

### 7.1 Overall Coverage

~67 test files with ~250+ test functions. Test quality varies dramatically.

| Area | Test File(s) | Test Count | Coverage Quality |
|---|---|---|---|
| **Assertion cycle** | `test_assertion_cycle.py` | 2 | MINIMAL — only tests obsolete marking and null safety |
| **RFQ admissibility** | `test_rfq_admissibility_hard_gate.py` | 12 | STRONG — covers all release_status values, blocker dominance, conflict integration |
| **Turn limit** | `test_turn_limit.py` | 4 | ADEQUATE — covers hard stop and boundary |
| **Candidate semantics** | `test_candidate_semantics.py` | 8+ | ADEQUATE — covers specificity inference and cluster building |
| **Conflict resolution** | `test_conflict_resolver_basis.py` | 7+ | MODERATE — covers type classification, severity levels, resolution persistence |
| **Verify & patch** | `test_subgraph_verify_and_patch.py` | 6+ | MODERATE — covers happy path, race condition, patch loop |
| **Working profile reducer** | `test_working_profile_reducer.py` | 5+ | ADEQUATE — covers merge semantics |
| **Prepare contract** | `test_node_prepare_contract_logic.py` | 10+ | STRONG — covers parameter resolution, governance metadata |
| **Graph topology** | `test_sealai_graph_v2_parallel_topology.py` | 3 | MINIMAL — only structural, no end-to-end |
| **Router** | `test_node_router.py` | 6+ | ADEQUATE — covers classification patterns |
| **Persona detection** | `test_persona_detection.py` | 4+ | ADEQUATE |
| **Parameter extraction** | `test_parameter_extraction.py`, `test_parameter_patch_utils.py` | 10+ | MODERATE |

### 7.2 High-Value Pilot Risks NOT Properly Tested

1. **Multi-turn state evolution** — No test simulates 3+ turns with parameter changes, cycle bumps, and conflict accumulation
2. **HITL resume flow** — `test_hitl_resume_contracts.py` exists but tests contract shape, not actual interrupt/resume behavior (which doesn't exist)
3. **Concurrent assertion cycle bumps** — No test simulates two parameter changes arriving close together
4. **Stale contract leakage** — No test verifies that an obsolete contract's governance metadata doesn't leak into the next cycle's output
5. **Conversation memory across sessions** — No integration test for checkpoint persistence and restoration
6. **LLM output variation handling** — Tests use fixed strings, not variable LLM outputs. No fuzz/adversarial testing of extraction or normalization
7. **Full graph end-to-end** — No test runs the compiled graph with real (or mocked) LLM and verifies governance output

---

## 8. CLEANUP RECOMMENDATION STACK

### Layer 1: Must-Clean Before Pilot

1. **Wire HITL interrupts** — At minimum: `snapshot_confirmation` before answer subgraph, `rfq_confirmation` gating any RFQ output. Without this, the system has zero human governance checkpoints.

2. **Enforce identity_class gating** — `lookup_allowed=False` must actually block RAG lookups for `identity_unresolved` parameters. Currently, an unresolved medium goes through Qdrant search without restriction.

3. **Consolidate conflict schemas** — Merge legacy `ConflictRecord` from `services/rag/state.py` into the v1.2 schema. The combinatorial chemistry guard's results must surface in `verification_report.conflicts`.

4. **Fix `RequirementSpec` to carry at minimum** `operating_conditions`, `missing_critical_parameters`, `normative_references`, `manufacturer_validation_scope`, `assumption_boundaries`. Current 4-field schema is insufficient for meaningful RFQ generation.

5. **Remove or gate `reasoning.rfq_ready`** — Legacy bool that still gets checked in `rfq_admissibility.py:153`. If True and no contract, it creates a `"legacy_rfq_ready_ignored_without_contract"` blocker — confusing rather than helpful.

### Layer 2: Should-Clean Soon

6. **Add `observed_inputs` capture** — Store raw user text per turn with timestamp and parameter extraction source. Enables audit trail as blueprint requires.

7. **Reduce `derived_artifacts_stale` triplication** — Consider keeping it only on `ReasoningState` and deriving from there. Three independent copies invite desync.

8. **Align `specificity` vocabulary** — Blueprint uses `family_only / subfamily / compound_required / product_family_required`. Code uses `compound_specific / family_level / material_class / document_hit / unresolved`. These should converge or have an explicit mapping.

9. **Add multi-turn integration tests** — At least 3 scenarios: (a) fresh case → parameter update → answer, (b) parameter correction → cycle bump → re-answer, (c) RFQ trigger with blocking unknowns.

10. **Strengthen assertion cycle tests** — Current 2 tests are insufficient. Add: concurrent bumps, stale artifact detection, contract retention across cycles.

### Layer 3: Leave Alone / Avoid Overengineering

11. **Graph DB (Store 3)** — Blueprint aspirational. Not needed for pilot. Would add complexity without clear operational value.

12. **3-agent parallel evidence fan-out** — Current 2-branch (material + mechanical) is pragmatically sufficient. Refactoring to 3 blueprint agents would be high-cost/low-value.

13. **Full EvidenceClaim taxonomy** — Useful long-term but premature to implement before the RAG pipeline itself is claim-structured.

14. **Depth Level system** (TRIAGE/PREQUALIFICATION/CRITICAL_REVIEW) — Adds complexity. Current completeness logic is simpler and adequate for pilot scope.

15. **Normalization Agent as distinct component** — Current parameter_patch approach works. Extracting a formal 3-stage normalization agent would be correct architecturally but risky as a refactor mid-stabilization.

---

## 9. PROPOSED CLOSEOUT SEQUENCE

These are minimal, non-expansionary actions to cleanly finish v1.2 for pilot readiness:

1. **Wire `interrupt_before` on `final_answer_node`** for snapshot confirmation — single-point HITL checkpoint that blocks auto-send of final answers. Smallest possible governance gate.

2. **Add `identity_class` check in `rag_tool.py`** / `knowledge_tool.py` — if identity_class is "unresolved", skip Qdrant lookup and trigger clarification. Single guard clause, ~10 lines.

3. **Merge combinatorial_chemistry guard conflicts into verification_report** — in `node_prepare_contract`, translate legacy ConflictRecords into v1.2 ConflictRecords and add to `governance_metadata.gate_failures`.

4. **Extend RequirementSpec** with 4 additional fields from blueprint: `normative_references`, `manufacturer_validation_scope`, `assumption_boundaries`, `invalid_if`. Populate from existing governance metadata.

5. **Write 3 integration tests** covering: (a) full happy-path through answer subgraph with governance metadata verification, (b) assertion cycle bump with contract obsolescence check, (c) RFQ admissibility blocking with BLOCKING_UNKNOWN conflict.

6. **Freeze conflict resolver** — current 7-type coverage is functionally complete. Mark as v1.2-stable, no further type additions.

7. **Delete `reasoning.rfq_ready`** or hard-deprecate with a warning log. It's a legacy trap.

8. **Document the 4-pillar → 5-layer deviation** explicitly in CLAUDE.md or a DECISIONS.md — acknowledge that the implementation uses a different state decomposition than the blueprint, and why. This prevents future confusion.

---

## 10. APPENDIX — EVIDENCE LEDGER

### A. State Model Evidence

| File | Lines | Finding |
|---|---|---|
| `sealai_state.py` | 990-996 | 4-pillar root: `conversation`, `working_profile`, `reasoning`, `system` |
| `sealai_state.py` | 263-274 | `RequirementSpec` — 4 fields vs blueprint's 12 |
| `sealai_state.py` | 277-299 | `AnswerContract` — no `contract_id`, no `release_status`, no `scope_of_validity` directly |
| `sealai_state.py` | 302-331 | `ConflictRecord` — 9 types, 6 severities, 3 resolution statuses |
| `sealai_state.py` | 345-367 | `RFQAdmissibilityContract` — fully blueprint-conformant |
| `sealai_state.py` | 370-379 | `ParameterIdentityRecord` — defined but `lookup_allowed` never enforced |
| `sealai_state.py` | 1059-1082 | `compute_knowledge_coverage()` — deterministic, blueprint-aligned |

### B. Graph Topology Evidence

| File | Lines | Finding |
|---|---|---|
| `sealai_graph_v2.py` | 309-424 | Full graph topology: 26 nodes, 0 interrupts |
| `sealai_graph_v2.py` | 355-364 | Entry path: START → profile_loader → safety_synonym_guard → combinatorial_chemistry_guard → node_router → frontdoor |
| `sealai_graph_v2.py` | 366-378 | Dual-path: frontdoor dispatches to "knowledge" (supervisor) or "analysis" (P1→fan-out→merge→answer) |
| `sealai_graph_v2.py` | 374-378 | Fan-out: P1 → material_analysis + mechanical_analysis (2 branches, not 3) |
| `subgraph_builder.py` | 143-178 | Answer subgraph: prepare_contract → draft → verify → (patch loop / finalize / safe_fallback) |

### C. Conflict Resolver Evidence

| File | Lines | Finding |
|---|---|---|
| `node_verify_claims.py` | 209-245 | `_check_resistance_claims()` — SOURCE_CONFLICT creation |
| `node_verify_claims.py` | 256-322 | `_check_parameter_conflicts()` — PARAMETER_CONFLICT creation |
| `node_verify_claims.py` | 325-366 | `_check_blocking_unknowns()` — BLOCKING_UNKNOWN creation |
| `node_verify_claims.py` | 369-424 | `_check_specificity_conflicts()` — COMPOUND_SPECIFICITY_CONFLICT creation |
| `node_verify_claims.py` | 427-459 | `_check_condition_conflicts()` — CONDITION_CONFLICT creation |
| `node_verify_claims.py` | 462-514 | `_check_assumption_conflicts()` — ASSUMPTION_CONFLICT creation |
| `node_verify_claims.py` | 517-556 | `_check_scope_conflicts()` — SCOPE_CONFLICT creation |
| `node_verify_claims.py` | 559-594 | `_check_temporal_validity_conflicts()` — TEMPORAL_VALIDITY_CONFLICT creation |
| `node_verify_claims.py` | 653-684 | `_apply_resolution_status()` — fingerprint-based persistence + FALSE_CONFLICT auto-dismiss |
| `node_verify_claims.py` | 860-864 | Blocking logic: only OPEN + HARD+ severity blocks |

### D. RFQ Admissibility Evidence

| File | Lines | Finding |
|---|---|---|
| `rfq_admissibility.py` | 21-47 | `derive_release_status()` — 5-rule deterministic cascade |
| `rfq_admissibility.py` | 87-172 | `normalize_rfq_admissibility_contract()` — collects blockers from governance metadata, answer contract, and verification conflicts |
| `rfq_admissibility.py` | 175-187 | `invalidate_rfq_admissibility_contract()` — cycle-bound invalidation |

### E. Assertion Cycle Evidence

| File | Lines | Finding |
|---|---|---|
| `assertion_cycle.py` | 36-39 | `get_assertion_binding()` — reads cycle_id and revision from reasoning pillar |
| `assertion_cycle.py` | 42-119 | `build_assertion_cycle_update()` — increments cycle, marks contract obsolete, resets derived artifacts, invalidates RFQ |
| `assertion_cycle.py` | 122-175 | `stamp_patch_with_assertion_binding()` — stamps derived artifacts with cycle binding |

### F. Missing Blueprint Concepts (Zero Evidence)

| Concept | Blueprint Section | Status |
|---|---|---|
| `observed_inputs` | Section 02, Field Table | Not implemented |
| `MediumProfile` / `MachineProfile` / `InstallationProfile` | Section 02, Asserted Layer | Not implemented |
| `EvidenceClaim` / `claim_type` | Section 05, RAG Architecture | Not implemented |
| `ResultContract` (full blueprint schema) | Section 07 | Not implemented (AnswerContract differs) |
| `SealingRequirementSpec` (full schema) | Section 08 | Skeletal (RequirementSpec has 4/12 fields) |
| `RFQDraft` | Section 08 | Not implemented |
| `interrupt_before` checkpoints | Section 04, HITL | Not implemented |
| Graph DB (Store 3) | Section 05 | Not implemented |
| 3-agent parallel evidence fan-out via `Send()` | Section 04, Slow Brain | Different architecture (2-branch) |
| Risk-Driven Completeness Engine (7 categories) | Section 03 | Not implemented (field-based instead) |
| Three Depth Levels | Section 03 | Not implemented |
| Manufacturer Portal | Section 10 | Not implemented (Phase D) |

---

*End of audit report.*
