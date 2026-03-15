# SealAI Architecture Audit Report

**Branch:** `feature/frontend-workspace-cleanup`
**Date:** 2026-03-14
**Scope:** Full repository scan against CLAUDE.md §3 directory structure and §5–§7 rules

---

## Executive Summary

The codebase implements a **domain-driven, Blueprint-governed agent** under `backend/app/agent/`. This is a **deliberate architectural evolution** beyond the CLAUDE.md §3 spec, not a random deviation. However, several critical invariants from the spec are violated, and the prescribed directory structure does not exist at all. The sections below enumerate every gap without changing any code.

---

## 1. FILES_MISSING

Files prescribed in CLAUDE.md §3 that do not exist anywhere in the repository.

### 1.1 Top-level `sealai/` namespace does not exist

CLAUDE.md §3 prescribes a top-level `sealai/` package. The actual implementation lives under `backend/app/agent/`. No file exists at any of the canonical paths:

| Prescribed Path | Status |
|---|---|
| `sealai/core/__init__.py` | ❌ Missing |
| `sealai/core/enums.py` | ❌ Missing |
| `sealai/core/parameters.py` | ❌ Missing |
| `sealai/core/deterministic_state.py` | ❌ Missing |
| `sealai/core/case_state.py` | ❌ Missing |
| `sealai/core/engine_result.py` | ❌ Missing |
| `sealai/engine/__init__.py` | ❌ Missing |
| `sealai/engine/calculations.py` | ❌ Missing |
| `sealai/engine/signals.py` | ❌ Missing |
| `sealai/engine/qualification.py` | ❌ Missing |
| `sealai/engine/plausibility.py` | ❌ Missing |
| `sealai/engine/registry.py` | ❌ Missing |
| `sealai/guard/__init__.py` | ❌ Missing |
| `sealai/guard/whitelist.py` | ❌ Missing |
| `sealai/guard/invariant.py` | ❌ Missing |
| `sealai/orchestrator/__init__.py` | ❌ Missing |
| `sealai/orchestrator/graph.py` | ❌ Missing |
| `sealai/orchestrator/nodes.py` | ❌ Missing |
| `sealai/orchestrator/router.py` | ❌ Missing |
| `sealai/persistence/__init__.py` | ❌ Missing |
| `sealai/persistence/models.py` | ❌ Missing |
| `sealai/persistence/audit.py` | ❌ Missing |
| `sealai/persistence/redis_streams.py` | ❌ Missing |
| `sealai/persistence/checkpointer.py` | ❌ Missing |
| `sealai/api/__init__.py` | ❌ Missing |
| `sealai/api/commands.py` | ❌ Missing |
| `sealai/api/queries.py` | ❌ Missing |
| `sealai/api/stream.py` | ❌ Missing |
| `sealai/api/dependencies.py` | ❌ Missing |
| `sealai/templates/case_panel.html` | ❌ Missing |
| `sealai/templates/base.html` | ❌ Missing |
| `sealai/templates/fragments/layer1_inputs.html` | ❌ Missing |
| `sealai/templates/fragments/layer2_calculations.html` | ❌ Missing |
| `sealai/templates/fragments/layer3_signals.html` | ❌ Missing |
| `sealai/templates/fragments/layer4_qualification.html` | ❌ Missing |

### 1.2 Prescribed test files — Missing

| Prescribed Path | Status |
|---|---|
| `tests/core/test_parameters.py` | ❌ Missing |
| `tests/core/test_case_state.py` | ❌ Missing |
| `tests/engine/test_calculations.py` | ❌ Missing |
| `tests/engine/test_signals.py` | ❌ Missing |
| `tests/engine/test_qualification.py` | ❌ Missing |
| `tests/engine/test_plausibility.py` | ❌ Missing |
| `tests/guard/test_whitelist.py` | ❌ Missing |
| `tests/guard/test_invariant.py` | ❌ Missing |
| `tests/integration/test_flow.py` | ❌ Missing |

---

## 2. FILES_MISPLACED

Files that fulfill the **intent** of a spec module but live in a non-canonical location.

| CLAUDE.md §3 Prescribed | Actual Location | Functional Match | Notes |
|---|---|---|---|
| `sealai/core/enums.py` | — | ❌ None | `ExtractionCertainty`, `VerbindlichkeitsStufe`, `QualificationLevel`, `EngineStatus` do not exist |
| `sealai/core/parameters.py` | `backend/app/agent/domain/parameters.py` | ⚠️ Partial | `PhysicalParameter(value, unit)` exists but is **not** `ExtractedParameter[T]` with `certainty` / `confirmed` / `raw_text` |
| `sealai/core/engine_result.py` | — | ❌ None | No `EngineResult[T]` wrapper; engine functions return plain `dict` |
| `sealai/core/deterministic_state.py` | `backend/app/agent/agent/state.py` (layers) | ⚠️ Partial | Layer model exists as `TypedDict` not frozen Pydantic `BaseModel` |
| `sealai/core/case_state.py` | `backend/app/agent/case_state.py` | ⚠️ Partial | `CaseState` exists but as `TypedDict`, not Pydantic, no `extra="forbid"` |
| `sealai/engine/calculations.py` | `backend/app/agent/agent/calc.py` | ⚠️ Partial | `calculate_physics()` exists; returns mutated dict, not `EngineResult[float]` |
| `sealai/engine/signals.py` | `backend/app/agent/deterministic_foundation.py` | ⚠️ Partial | `build_engineering_signal_foundation()` exists; returns `dict`, not `EngineResult[str]` |
| `sealai/engine/qualification.py` | `backend/app/agent/material_core.py` | ⚠️ Partial | Qualification logic is extensive; returns DTOs, not `EngineResult[List[str]]` |
| `sealai/engine/plausibility.py` | — | ❌ None | No dedicated plausibility module; no out-of-range checks in `calc.py` |
| `sealai/engine/registry.py` | `backend/app/agent/runtime.py` | ⚠️ Partial | `route_interaction()` handles intent dispatch, not a parameter→function registry |
| `sealai/guard/whitelist.py` | — | ❌ None | No `parse_llm_output()` chokepoint; see GUARD_GAPS below |
| `sealai/guard/invariant.py` | — | ❌ None | No `assert_deterministic_unchanged()` post-LLM check |
| `sealai/orchestrator/graph.py` | `backend/app/agent/agent/graph.py` | ✓ Match | LangGraph orchestration present |
| `sealai/orchestrator/nodes.py` | `backend/app/agent/agent/logic.py` + `selection.py` | ⚠️ Partial | Logic scattered across two 1,000+ LOC files |
| `sealai/orchestrator/router.py` | `backend/app/agent/runtime.py` | ⚠️ Partial | Intent classification present; no regex→embedding→LLM fallback cascade |
| `sealai/persistence/audit.py` | `backend/app/services/audit/audit_logger.py` | ⚠️ Partial | Audit logger exists (Sprint 9); not wired to agent layer events |
| `sealai/persistence/checkpointer.py` | `backend/app/services/history/persist.py` | ⚠️ Partial | `load_structured_case` / `save_structured_case` present; no TTL or Redis fallback |
| `sealai/api/commands.py` | `backend/app/agent/api/router.py` (`POST /chat`) | ⚠️ Partial | Combined in one router; not split into commands/queries/stream |
| `sealai/api/stream.py` | — | ❌ None | No SSE stream endpoint in agent router |
| `sealai/templates/` | — | ❌ None | No Jinja2 templates; rendering done in Python (`selection.py`, `case_state.py`) |

---

## 3. SCHEMA_VIOLATIONS

Violations of the Pydantic model rules defined in CLAUDE.md §5.

### 3.1 `confidence: float` on LLM-facing models (CLAUDE.md §12 anti-pattern)

**File:** `backend/app/agent/evidence/models.py:24`
**File:** `backend/app/agent/agent/state.py:37` (`ObservedInputRecord.confidence`)
**File:** `backend/app/agent/agent/state.py:47` (`IdentityRecord.normalization_confidence`)
**File:** `backend/app/agent/agent/tools.py:9` (`submit_claim` tool parameter)

```python
# evidence/models.py — Claim is the LLM's ONLY write interface
confidence: float = Field(..., ge=0.0, le=1.0)

# agent/state.py — Raw intake from LLM tool call
class ObservedInputRecord(TypedDict, total=False):
    confidence: float               # LLM self-assessment stored directly in state

class IdentityRecord(TypedDict, total=False):
    normalization_confidence: float  # LLM self-assessment on normalization step
```

**CLAUDE.md §12 rule:** "LLM self-assessment is unreliable. Use `ExtractionCertainty` enum derived from output structure."
The `Claim.confidence` float flows directly into `ObservedInputRecord.confidence` in `graph.py:308`, which propagates into the observed layer of `SealingAIState`. This is the exact anti-pattern the spec prohibits.

### 3.2 `Any` types in function signatures (CLAUDE.md §11 rule 2)

**File:** `backend/app/agent/deterministic_foundation.py`
```python
from typing import Any, Dict, List, TypedDict

def build_calculation_foundation(
    sealing_state: Dict[str, Any],   # Any — violates §11 rule 2
    working_profile: Dict[str, Any], # Any
    rwdr_state: Dict[str, Any],      # Any
) -> Dict[str, DeterministicCalculationRecord]:
    ...
    value: Any  # TypedDict field — untyped value in calculation record
```

**File:** `backend/app/agent/agent/state.py`
```python
class ObservedLayer(TypedDict):
    raw_parameters: Dict[str, Any]   # Any — entire raw parameter dict is untyped

class AssertedLayer(TypedDict):
    medium_profile: Dict[str, Any]   # Any — untyped asserted profile
    machine_profile: Dict[str, Any]  # Any
    operating_conditions: Dict[str, Any]  # Any
```

**File:** `backend/app/agent/agent/graph.py:1,218`
```python
relevant_fact_cards: List[Dict[str, Any]]  # Any in AgentState
working_profile: Dict[str, Any]            # Any in AgentState
```

### 3.3 No `ExtractedParameter[T]` wrapper on Layer-1 fields

`RawInputState` with `extra="forbid"` and all fields typed as `ExtractedParameter[T]` does not exist. Instead:

- `SealingAIState.observed.raw_parameters` is `Dict[str, Any]` — plain values, no provenance tracking
- There is no `certainty: ExtractionCertainty` on any parameter
- There is no `confirmed: bool` flag on any parameter
- There is no `is_calculable` property gating engine use

This means the deterministic engine (`calc.py`, `deterministic_foundation.py`) receives raw unvalidated floats from the LLM with no provenance, certainty, or confirmation tracking.

### 3.4 Mutable state objects — no `frozen=True` on deterministic layer

**File:** `backend/app/agent/agent/state.py`

`SealingAIState` is a `TypedDict` (mutable). CLAUDE.md §5.4 requires `DeterministicState` to have `model_config = {"frozen": True}`. TypedDict has no immutability mechanism.

The derived/calculated layers (`GovernanceLayer`, `CycleLayer`, `SelectionLayer`) can be mutated in-place anywhere in the call chain. Example from `graph.py:374`:
```python
new_sealing_state = dict(sealing_state)      # shallow copy
new_sealing_state["selection"] = selection_state  # direct mutation on copy
```
A shallow dict copy does not protect nested TypedDicts from in-place mutation.

### 3.5 `EngineResult[T]` wrapper absent — engine functions return plain dicts

**File:** `backend/app/agent/agent/calc.py`
Functions `calc_kinematics`, `calc_tribology`, `calc_thermodynamics`, `calc_mechanics`, `calculate_physics` all:
- Receive a mutable `Dict[str, Any]`
- Mutate it in-place (`profile["v_m_s"] = ...`)
- Return the same mutated dict

No `EngineResult[T]` wrapper, no `status: EngineStatus` signal, no `missing_inputs: List[str]`. Insufficient data is handled by `None` checks and silent omission rather than explicit `EngineStatus.INSUFFICIENT_DATA`.

**File:** `backend/app/agent/deterministic_foundation.py`
`build_calculation_foundation()` returns `Dict[str, DeterministicCalculationRecord]`. Status is embedded as `"status": "valid"` string inside the record dict — not the typed `EngineStatus` enum.

### 3.6 Missing `EngineStatus` enum

No `EngineStatus` enum (`COMPUTED`, `INSUFFICIENT_DATA`, `OUT_OF_RANGE`, `NO_MATCH`, `CONTRADICTION_DETECTED`) exists anywhere in the codebase. Status is communicated via ad-hoc strings (`"valid"`, `"blocked"`, `"inadmissible"` etc.).

### 3.7 Missing `ExtractionCertainty`, `VerbindlichkeitsStufe`, `QualificationLevel` enums

`backend/app/agent/agent/state.py` defines `ReleaseStatus`, `RFQAdmissibility`, `SpecificityLevel` as `Literal` types, which partially cover `VerbindlichkeitsStufe` and `QualificationLevel`, but:
- `ExtractionCertainty` (`EXPLICIT_VALUE`, `EXPLICIT_RANGE`, `INFERRED_FROM_CONTEXT`, `AMBIGUOUS`, `ASSUMED_DEFAULT`) does not exist
- `VerbindlichkeitsStufe` (`KNOWLEDGE`, `ORIENTATION`, `CALCULATION`, `QUALIFIED_PRESELECTION`, `RFQ_BASIS`) is replaced by `ReleaseStatus` (different semantics)

### 3.8 `extra="forbid"` missing on state-layer TypedDicts

TypedDicts cannot have `extra="forbid"`. This is architecturally correct for TypedDict, but means:
- `SealingAIState` sub-layers accept unknown keys at runtime
- `raw_parameters: Dict[str, Any]` is fully open — any key, any value

The API models (`backend/app/agent/api/models.py`) correctly apply `extra="forbid"` on Pydantic models at the HTTP boundary, but this does not protect internal state layers.

---

## 4. GUARD_GAPS

Paths where LLM output reaches state without passing through `RawInputState.model_validate()`.

### 4.1 Primary LLM → State path: no whitelist guard

**File:** `backend/app/agent/agent/graph.py:278–323` (`evidence_tool_node`)

```
LLM tool call: submit_claim(claim_type, statement, confidence, ...)
    ↓
Claim(claim_type=args["claim_type"], statement=args["statement"], confidence=args["confidence"])
    ↓  [Pydantic Claim validation — guards claim structure, NOT state fields]
evaluate_claim_conflicts(claims, asserted_state, fact_cards)
    ↓  [returns intelligence_conflicts + validated_params]
process_cycle_update(old_state, intelligence_conflicts, validated_params, raw_claims, ...)
    ↓  [logic.py reducer — mutates SealingAIState TypedDict]
new_sealing_state written back to AgentState
```

**Gap:** `validated_params` from `evaluate_claim_conflicts` flows into `process_cycle_update` without any Pydantic whitelist validation. The `Claim` model validates that the LLM submitted a well-formed claim object, but does NOT enforce which state fields can be written to. There is no equivalent of `RawInputState.model_validate(raw_llm_json)` with `extra="forbid"` as a chokepoint.

### 4.2 No `assert_deterministic_unchanged()` post-LLM check

After `evidence_tool_node` returns a new `sealing_state`, the graph does not call any invariant check to verify that the governance/qualification/calculation layers were not mutated. CLAUDE.md §7.2 requires this after every LLM node execution. There is no `deterministic_state_hash()` or equivalent.

### 4.3 `extract_parameters()` in reasoning node writes directly to `working_profile`

**File:** `backend/app/agent/agent/graph.py:229`
```python
new_profile = extract_parameters(query, current_profile, cards_data) if query else current_profile
```

`extract_parameters()` in `logic.py` parses the raw user query string and writes values (diameter, speed, pressure, material) directly into `working_profile` — a `Dict[str, Any]` on `AgentState`. This bypasses the claim submission mechanism entirely. There is no Pydantic validation, no `ExtractionCertainty` tracking, and no guard on what keys can be written.

### 4.4 `sealing_state["asserted"]` written without whitelist in `process_cycle_update`

**File:** `backend/app/agent/agent/logic.py` (`process_cycle_update`)
The reducer accepts `validated_params: dict` and merges values into the asserted layer of `SealingAIState`. The `validated_params` dict is produced by `evaluate_claim_conflicts`, which translates claim statements into key-value pairs. This translation has no schema enforcement: any key can be written to `asserted.operating_conditions`, `asserted.machine_profile`, etc.

### 4.5 Fast path bypasses all guards

**File:** `backend/app/agent/runtime.py` (`execute_fast_calculation`, `execute_fast_knowledge`)

The runtime has fast paths that skip LangGraph entirely:
- `FAST_CALCULATION` path: parses `extract_calc_inputs()` from raw text → calls `calculate_physics()` directly
- `FAST_KNOWLEDGE` path: returns hardcoded or KB text

`extract_calc_inputs()` writes plain floats from regex matches directly into a profile dict. No `ExtractionCertainty`, no `Claim` submission, no guard.

---

## 5. TEST_GAPS

### 5.1 Prescribed test files — entirely missing

All 9 test files specified in CLAUDE.md §5.6, §6, §7 are missing (see section 1.2).

### 5.2 Existing tests vs. prescribed test requirements

| CLAUDE.md §5.6 Test ID | Requirement | Covered? | File |
|---|---|---|---|
| T01 | `AMBIGUOUS` → `is_calculable == False` | ❌ No `ExtractedParameter` exists | — |
| T02 | `INFERRED` + `confirmed=False` → `is_calculable == False` | ❌ | — |
| T03 | `INFERRED` + `confirmed=True` → `is_calculable == True` | ❌ | — |
| T04 | `EXPLICIT_VALUE` + `parsed_value=None` → `is_calculable == False` | ❌ | — |
| T05 | `EXPLICIT_VALUE` + `parsed_value=150.0` → `is_calculable == True` | ❌ | — |
| T06 | `RawInputState.model_validate(valid L1 dict)` → succeeds | ❌ No `RawInputState` | — |
| T07 | `RawInputState.model_validate({"medium": "Wasser"})` → `ValidationError` | ❌ | — |
| T08 | `RawInputState.model_validate({"pv_value": 42.0})` → `ValidationError` | ❌ | — |
| T09 | `RawInputState.model_validate({"hard_stops": [...]})` → `ValidationError` | ❌ | — |
| T10 | `DeterministicState` frozen → assignment raises `ValidationError` | ❌ State is TypedDict | — |
| T11 | `EngineResult(status="computed", value=42.5).is_usable == True` | ❌ No `EngineResult` | — |
| T12 | `EngineResult(status="insufficient_data").is_usable == False` | ❌ | — |
| T13 | `EngineResult(status="computed", value=None).is_usable == False` | ❌ | — |

**All 13 prescribed core tests: 0/13 covered.**

### 5.3 Prescribed engine tests — not covered

| CLAUDE.md §6 Test ID | Requirement | Covered? |
|---|---|---|
| E01 | Both inputs → `status=computed`, value correct to 3 decimals | ❌ (`calc.py` has no status) |
| E02 | `shaft_diameter` missing → `status=insufficient_data` | ❌ |
| E03 | `speed_rpm` with `certainty=AMBIGUOUS` → `insufficient_data` | ❌ (no `ExtractionCertainty`) |
| E04 | Result > 150 m/s → `status=out_of_range` | ❌ (no plausibility gate) |
| E05 | `d=0` → `value=0.0, status=computed` | ❌ |
| E06 | Negative rpm — documented decision | ❌ |
| E07–E09 | Speed class thresholds (low/medium/high) | ❌ (no `signals.py`) |
| E10 | `temperature_celsius` not calculable → `insufficient_data` | ❌ |
| E11 | Medium not in DB → `status=no_match` | ❌ |
| E12 | Hard stop: temp > material max | ❌ |
| E13 | No hard stops → shortlist computed | ❌ |
| E14 | Missing critical L3 signal → qualification blocked | ❌ |

### 5.4 Prescribed guard tests — not covered

All 10 guard tests (CLAUDE.md §7.3) require `guard/whitelist.py` and `guard/invariant.py` which do not exist.

### 5.5 Existing test coverage summary

The following tests exist and cover the **actual implementation**, not the prescribed spec:

| Test File | Scope | Assessment |
|---|---|---|
| `backend/tests/agent/test_agent_graph.py` | LangGraph node wiring | ✓ Covers actual graph |
| `backend/tests/agent/test_agent_graph_e2e.py` | End-to-end agent flow | ✓ Covers actual flow |
| `backend/tests/agent/test_agent_logic.py` | `logic.py` state reducer | ✓ Covers actual logic |
| `backend/tests/agent/test_selection.py` | `selection.py` | ✓ Covers actual selection |
| `backend/tests/agent/test_firewall_feedback.py` | Conflict detection | ✓ Partial guard coverage |
| `backend/tests/agent/test_rwdr_contracts.py` | RWDR governance contracts | ✓ Covers actual RWDR |
| `backend/tests/agent/test_rwdr_orchestration.py` | RWDR flow stages | ✓ Covers actual RWDR |
| `backend/tests/agent/test_domain_parameters.py` | `PhysicalParameter` model | ✓ Covers actual model |
| `backend/tests/agent/test_domain_material.py` | `MaterialValidator` | ✓ Covers actual validator |
| `backend/tests/agent/test_api_models.py` | FastAPI model validation | ✓ Covers HTTP boundary |
| `backend/tests/agent/test_api_router.py` | HTTP endpoint behavior | ✓ Covers actual router |
| `tests/api/test_agent_case_state_foundation.py` | Case state integration | ✓ Covers actual state |
| `tests/api/test_agent_deterministic_foundation.py` | L2/L3 deterministic layer | ✓ Covers actual foundation |
| `tests/api/test_agent_material_core_foundation.py` | Material qualification | ✓ Covers actual core |
| `tests/api/test_agent_material_invalidation_foundation.py` | Material invalidation | ✓ Covers actual invalidation |
| `tests/api/test_agent_persistent_case_store.py` | Persistence layer | ✓ Covers actual persistence |
| `tests/api/test_agent_runtime_foundation.py` | Runtime routing | ✓ Covers actual runtime |

### 5.6 Untested engine functions

| Function | File | Test Coverage |
|---|---|---|
| `calc_kinematics()` | `agent/agent/calc.py:7` | ❌ Not unit-tested in isolation |
| `calc_tribology()` | `agent/agent/calc.py:22` | ❌ Not unit-tested in isolation |
| `calc_thermodynamics()` | `agent/agent/calc.py:36` | ❌ Placeholder only |
| `calc_mechanics()` | `agent/agent/calc.py:41` | ❌ Placeholder only |
| `build_calculation_foundation()` | `deterministic_foundation.py:28` | Partially via `test_agent_deterministic_foundation.py` |
| `build_engineering_signal_foundation()` | `deterministic_foundation.py:82` | Partially via `test_agent_deterministic_foundation.py` |
| `execute_fast_calculation()` | `runtime.py` | Via `test_agent_runtime_foundation.py` |
| No plausibility checks | — | ❌ No plausibility module exists |

---

## 6. Summary Matrix

| Category | Count | Severity |
|---|---|---|
| Missing prescribed files (core + engine + guard) | 35 | HIGH — spec gate 1–3 cannot pass |
| Missing prescribed test files | 9 | HIGH — acceptance gates are undefined |
| Schema violations (`confidence: float` anti-pattern) | 4 locations | HIGH — violates §12 anti-pattern |
| Schema violations (`Any` in signatures) | 12+ locations | MEDIUM — violates §11 rule 2 |
| Schema violations (no `ExtractedParameter[T]`) | All L1 fields | HIGH — core provenance model absent |
| Schema violations (no `EngineResult[T]`) | All engine functions | HIGH — status signaling absent |
| Schema violations (mutable deterministic state) | All derived layers | HIGH — violates §5.4 `frozen=True` |
| Guard gaps (no whitelist chokepoint) | 1 primary path | CRITICAL — §7.1 requirement |
| Guard gaps (no invariant check) | Post-LLM path | CRITICAL — §7.2 requirement |
| Guard gaps (extract_parameters bypass) | Fast path + reasoning | HIGH — unguarded write |
| Prescribed core tests not covered | 13/13 | HIGH |
| Prescribed engine tests not covered | 14/14 | HIGH |
| Prescribed guard tests not covered | 10/10 | HIGH |

---

## 7. Notes on Architectural Intent

The existing codebase is **not simply incomplete** — it implements a substantially different and more sophisticated architecture than CLAUDE.md §3 prescribes:

- **Blueprint v1.2/v1.3 governance model** replaces the simpler L1–L4 model
- **Claim-based LLM interface** (`submit_claim` tool) is more structured than a raw `RawInputState` fill
- **5-layer state** (Observed → Normalized → Asserted → Governance → Cycle) is an evolution of the L1–L4 model
- **RWDR selector** (multi-stage confidence field collection) is domain logic not in the spec
- **Material candidate governance** (`material_core.py`, `promoted_candidate_registry_v1.json`) goes far beyond the spec's `material_shortlist`

The gaps identified above are **real gaps** that weaken the safety guarantees the spec was designed to provide, regardless of the architectural evolution. The most critical ones — the missing whitelist guard and the `confidence: float` anti-pattern — should be addressed even if the directory structure is never migrated to the §3 layout.
