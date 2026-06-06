# V1.8 Patch Plan (read-only deliverable — execution gated on approval)

**Date:** 2026-06-06
**Source:** gap list in `v18_audit_report.md` §E, Gate-1 items §G.
**Rules:** one dimension per patch; each ships tests or a written justification; each is checked
against the §7.10 prohibition list + the §11 acceptance criteria; Golden REPLAY (once CI exists)
stays green after every patch; additive/internal patches first, contract-breaking patches parked
behind a human decision.

**Order of execution:** P0-A → P2-P in sequence. **G1/G2/G3 are NOT scheduled** — they need a
decision first (see §Gate-1). Each patch below is independently revertible.

Legend for "Risk to live contracts": 🟢 internal/additive · 🟡 cross-cutting (prove serialization
+ frontend) · 🔴 breaks a contract → parked in Gate-1.

---

## Phase A — Foundation & low-risk hardening

### P0-A — Stand up CI (REPLAY + guardrails per PR)
- **Addresses:** TST-01, §11 AC5, §10.2 discipline. **Risk:** 🟢
- **Scope:** add `.github/workflows/ci.yml` running: broad backend (`app/agent/tests tests`),
  architecture+seam guardrails, frontend `test:run`, and `git diff --check`. No app-code change.
- **Files:** `.github/workflows/ci.yml` (new).
- **Test plan:** the workflow *is* the test; verify it green on a no-op PR.
- **API/SSE compat:** none. **Migration:** none. **Rollback:** delete the workflow file.

### P0-B — Strip caller-supplied tenant from MCP metadata_filters
- **Addresses:** SEC-02 (low-sev note). **Risk:** 🟢
- **Scope:** in `search_technical_docs`/`get_available_filters`, drop `tenant_id` and
  `metadata.tenant_id` keys from caller `metadata_filters` before the server tenant is applied.
- **Files:** `backend/app/agent/.../knowledge_tool.py` (~`:554-571,1169,1383`).
- **Test plan:** extend `backend/.../test_rag_injection.py` / `test_visibility_filter.py` with a
  case asserting an injected `tenant_id` filter cannot widen scope.
- **API/SSE compat:** none (server already re-adds the authoritative tenant). **Rollback:** revert.

### P0-C — SEC-04 trace encryption/TTL: decision + implementation
- **Addresses:** SEC-04, §7.11 (encrypted + TTL trace full-texts). **Risk:** 🟢 (doc) / 🟡 (if app-layer)
- **Scope:** (decision-dependent — see Risk #6) either (a) document that `chat_messages` /
  `case_state_snapshots` rely on infra at-rest encryption + add a retention job for
  transcript-bearing rows, or (b) add app-layer encryption for those columns.
- **Files:** `docs/architecture/` note + (option b) `backend/app/models/postgres_logger.py`,
  a retention script under `backend/scripts/` + an Alembic migration.
- **Test plan:** retention job unit test; (b) round-trip encrypt/decrypt test.
- **Migration:** option (b) needs a column migration + backfill. **Rollback:** revert; data
  remains readable under option (a).

---

## Phase B — State-world separation & observability (internal/additive)

### P1-D — Checkpointer holds execution state only
- **Addresses:** STA-01, §11 AC4, §7.2. **Risk:** 🟡 (must preserve `interrupt()`/resume)
- **Scope:** stop the LangGraph checkpointer from persisting `GovernedSessionState` business
  fields. Options: a reduced checkpoint state (execution-only keys) or a `Remainingvalue`/
  channel-filter so only `pending_message`, interrupt/resume cursor, and `output_*` are
  checkpointed. Add an explicit checkpoint-retention sweeper (the §7.2 "Retention-Job").
  **Keep the current `thread_id`** (the convention change is Gate-1 G3).
- **Files:** `backend/app/agent/graph/__init__.py` (GraphState split), `graph/topology.py`
  (checkpointer wiring), a retention job under `backend/scripts/`.
- **Test plan:** new test asserting a resumed turn (post-`interrupt`) reconstructs business
  state from the live store, not the checkpoint; assert no business keys in the checkpoint tuple.
- **API/SSE compat:** none. **Migration:** none (old checkpoints expire via TTL).
  **Rollback:** revert the state split.

### P1-E — Universal per-LLM-call trace (§7.11)
- **Addresses:** PRM-03, TST-02, §11 AC6. **Risk:** 🟢 additive
- **Scope:** extend the per-turn trace so **every** LLM call records `template_id@version`,
  `prompt_hash`, `model_ref`, `tokens`, `latency` (wire the already-defined but uncalled
  `metrics.track_llm_call`), and add `gate_decisions[]` + `envelope_hash` to the turn trace.
- **Files:** `backend/app/agent/runtime/answer_trace.py`, `backend/app/observability/metrics.py`
  call-sites, `backend/app/agent/v92/contracts.py` (`TraceSummary`).
- **Test plan:** extend `test_trace_summary.py` / `test_stage_a1_observability.py` to assert the
  new fields are populated for router + intake + composer.
- **API/SSE compat:** trace is internal/observability; the SSE trace dict gains fields (additive).
  **Rollback:** revert.

### P1-F — Governed stream≡invoke equivalence test
- **Addresses:** STR-03, §11 AC7 (partial). **Risk:** 🟢 test-only
- **Scope:** add a contract test that runs `run_governed_graph_turn` via both the `astream`
  branch and the `ainvoke` branch on the same input and asserts equal `result_state`/envelope.
- **Files:** `backend/app/agent/tests/test_governed_runtime_seam.py` (extend).
- **Test plan:** the test itself. **API/SSE compat:** none. **Rollback:** delete the test.

---

## Phase C — Prompt hygiene & schema vorsorge (additive — unblocks P2)

### P1-G — Untrusted-delimiter convention + No-Go completeness
- **Addresses:** PRM-02, PRM-05, §11 AC8. **Risk:** 🟢 additive
- **Scope:** wrap inlined user/RAG variables in legacy templates in an explicit marked
  untrusted-delimiter block (data only, never template source); add literal
  "können Sie bedenkenlos" to the No-Go phrase list.
- **Files:** `backend/app/prompts/final_answer_router.j2`, `response_router.j2`,
  `backend/app/agent/prompts/guard/unsafe_instruction_reply.j2`,
  `backend/app/agent/templates/no_go_guard.py`.
- **Test plan:** extend `no_go_guard` tests; a render test asserting user text stays within the
  delimiter. **API/SSE compat:** none. **Rollback:** revert.

### P1-H — Additive schema headroom (status/origin/lifecycle enums)
- **Addresses:** LIF-01 (substrate), §11 AC9 (substrate). **Risk:** 🟢 additive (no behavior change)
- **Scope:** extend `Provenance` with `datasheet_extracted` + `outcome_observation`; extend
  `FieldStatus` with the §6.2 members not yet present; add a typed `CaseLifecycleStatus` enum
  (`inquiring…closed`, default `inquiring`) as a field — **declared, not yet wired** into routing.
- **Files:** `backend/app/agent/state/models.py`.
- **Test plan:** enum round-trip + serialization tests; assert existing cases default correctly.
- **API/SSE compat:** additive enum values — verify frontend `contracts/agent.ts` tolerates
  unknown enum values gracefully. **Migration:** none (defaults). **Rollback:** revert enums.

### P1-I — `positions[]` headroom (default one)
- **Addresses:** LIF-03, §11 AC18. **Risk:** 🟡 cross-cutting (prove serialization + both render paths)
- **Scope:** introduce optional `Case.positions[]` (default exactly one) and make the brief field
  maps, `RfqState.dimensions`, and the cockpit projection **iterate** over positions (defaulting
  to one). No multi-position UX yet — pure headroom (AC18).
- **Files:** `backend/app/services/rwdr_mvp_brief.py` (field maps), `backend/app/agent/state/models.py`
  (`RfqState`), `backend/app/api/v1/projections/case_workspace.py`.
- **Test plan:** existing RWDR golden cases must stay green (single position); add a 2-position
  serialization test; frontend render test (desktop + mobile) with one position unchanged.
- **API/SSE compat:** projection payload gains an optional `positions` array; **must remain
  backward-compatible** (single-position consumers unaffected). **Migration:** snapshot reader
  tolerates absent `positions`. **Rollback:** revert (additive).

### P1-J — Move RWDR norm/calc specifics into the pack
- **Addresses:** PCK-01. **Risk:** 🟢 internal (guarded by `test_core_seal_type_branching.py`)
- **Scope:** add `standard_part_tables()`/calc hooks to `DomainPack`; have `norm_node`/
  `compute_node` resolve the registry/formula **via the pack** instead of hardwiring the RWDR
  DIN/ISO registry.
- **Files:** `backend/app/domain/domain_pack.py`, `backend/app/domain/seal_packs.py`,
  `backend/app/agent/graph/nodes/norm_node.py`, `nodes/compute_node.py`.
- **Test plan:** `test_core_seal_type_branching.py` + norm/compute node tests stay green; new test
  asserting the pack supplies the registry. **API/SSE compat:** none. **Rollback:** revert.

---

## Phase D — Solution Companion foundation (additive)

### P2-K — SolutionProfile envelope + datasheet ingestion
- **Addresses:** LIF-01, LIF-02, §11 AC10. **Risk:** 🟡
- **Scope:** add a `SolutionProfile` type (reusing `CaseField`/status/provenance), a
  `solution_profiles: list[SolutionProfile]` slice on the case, and wire
  `DocumentEvidenceState.candidate_facts` (datasheet/SDS) → SolutionProfile candidates stamped
  `origin=datasheet_extracted` with `source_doc + source_page`.
- **Files:** `backend/app/agent/state/models.py`, `backend/app/agent/v92/orchestrator.py`
  (document extraction), reducers for the new slice.
- **Test plan:** datasheet→SolutionProfile candidate test (origin + page stamped); single-writer
  test stays green. **API/SSE compat:** projection gains an optional solution panel payload.
  **Migration:** tolerate absent slice. **Rollback:** revert.

### P2-L — OperatingWindowCheck (pure code) + projection + `solution_docs` RAG scope
- **Addresses:** §11 AC11, AC17. **Risk:** 🟡
- **Scope:** deterministic `OperatingWindowCheck` (requirement vs solution limit, field-by-field,
  margin + flag; missing limit → suggested manufacturer question, never silent omission); a
  code-only Operating-Window projection + UI panel; a tenant-scoped `solution_docs` RAG scope
  with mandatory payload (doc-id + page).
- **Files:** `backend/app/services/operating_window.py` (new, pure), projection under
  `state/projections*.py`, `frontend/src/components/dashboard/OperatingWindow.tsx` (new),
  `backend/app/services/rag/` scope.
- **Test plan:** pure-code unit tests (margins/flags/missing-limit); projection snapshot test;
  RAG scope tenant-isolation test. **API/SSE compat:** additive panel. **Rollback:** revert.

---

## Phase E — Companion modes (additive, after substrate)

Each mode patch: register in the router (extend the enum + dispatch), add **≥1 golden
conversation (REPLAY fixture)**, enforce the safety formula ("laut Datenblatt…", explanation ≠
release) via the existing No-Go linter, and route through the State Gate (no bypass — AC15).

- **P2-M — `solution_explanation`** (grounded on SolutionProfile/RAG/norm; unanswerable →
  suggested manufacturer question). §11 AC12.
- **P2-N — `standard_part_fast_path`** (size-table `standard_part_tables()` in the pack →
  designation + compact checklist in a Tier-0 path; branch to full case anytime). §11 AC13, MOD-02.
- **P2-O — `installation_guidance` + `operation_qna`** (pack `installation_knowledge()` /
  `outcome_taxonomy()`; step acknowledgements documented to the case).
- **P2-P — `incident_intake` + Outcome-Records** (Soll-Ist diagnosis vs SolutionProfile →
  structured Outcome-Event; tenant-scoped Outcome-Record persistence + anonymized aggregation
  governance). §11 AC14, AC16.
  - **Files (representative):** `backend/app/services/semantic_intent_router.py`,
    `backend/app/agent/api/dispatch.py`, `backend/app/domain/seal_packs.py` (pack hooks),
    `backend/app/models/` (Outcome-Record model + Alembic migration, tenant NOT-NULL like
    `mutation_events`), golden fixtures under `backend/app/agent/tests/`.
  - **API/SSE compat:** additive modes; existing routes unchanged. **Migration:** new
    Outcome-Record table. **Rollback:** feature-flag each mode; revert migration last.

---

## Gate-1 — parked pending human decision (NOT scheduled)

| ID | Change | Why parked | Options |
|---|---|---|---|
| **G1** | Topology → §7.3 fan-out DAG; remove in-turn cycle; introduce `AnalysisModule`/`Proposal` + Dirty Scheduler; thin nodes | **Golden-affecting** (multi-turn behavior); large blast radius; overlaps the working reducer/single-writer seam | (a) full §7.3 rewrite; (b) thin-node + Proposal refactor keeping edges/cycle; (c) treat §7.3 as logical contract, defer reshape. **Rec: (b) then re-evaluate.** |
| **G2** | SSE: add `ack<100ms`, post-route progress/chip event, `messages` stream mode, rename to `envelope_final` | **Frontend SSE contract** (`route.ts`, `useAgentStream.ts`) | Ship a **compat shim**: keep current event names, add `ack` + chip as new events; frontend opt-in. |
| **G3** | `thread_id` `sealai:tenant:owner:session` → `case_id:turn_id` | Session-continuity / existing checkpoints | Dual-read migration window; or keep current scheme (already tenant-safe) and document the deviation. |

**Recommended first wave after approval:** P0-A, P0-B, P1-E, P1-F, P1-G, P1-H — all 🟢 additive/
internal, zero contract risk, and they unblock the rest. Then P1-D, P1-I, P1-J, then Phase D/E.
