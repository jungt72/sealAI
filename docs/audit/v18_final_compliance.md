# V1.8 Phase 4 — Final Compliance (first wave)

**Date:** 2026-06-06
**Branch:** `feat/v18-first-wave` (not pushed)
**Scope of this report:** the approved **first wave** of additive/internal patches (Gate-1
items G1/G2/G3 remain parked by decision). It records what changed, the before/after, and the
remaining gaps keyed to the §11 acceptance criteria. Companion: `v18_audit_report.md` (full
30-ID matrix), `v18_patch_plan.md` (ordered plan), `v18_phase0_inventory.md` (baseline).

---

## 1. What shipped (one patch = one commit, tests green after each)

| Commit | Patch | Annex-A / §11 | Tests |
|---|---|---|---|
| `1c78439` | docs(v18): blueprint + AGENTS/CLAUDE + audit artifacts | §10 discipline | n/a (docs) |
| `436c5ae` | **P0-B** strip caller-supplied tenant from MCP `metadata_filters` | SEC-02 / AC17 | +2 (injected-tenant ignored; reserved keys dropped) |
| `436d5b2` | **P1-G** V1.8 §5.4 "bedenkenlos"/suitability No-Go pattern | PRM-05 / AC8 | +6 (3 match, 3 no-match) |
| `efa79b5` | **P1-H** additive §6.2/§6.3 schema headroom | LIF-01 / AC9 | +~10 (origin/status/lifecycle round-trip) |
| `29cd7cad` | **P1-F** governed stream≡invoke equivalence test | STR-03 / AC7 | +1 (astream≡ainvoke) |
| `099f56f` | **P0-A** wire No-Go guardrail into existing CI doctrine suite | TST-01 / AC5 | CI step (77 passed under CI invocation) |

**Regression after the full wave:** broad backend suite `app/agent/tests tests` — **green,
exit 0** (see §4). Architecture + governed-seam guardrails green. No test silenced or weakened.

**§7.10 prohibition list check:** none of the patches add a write-tool, mutate case truth
outside the State Gate, add an LLM calculation, add a per-seal-type graph, or read business
data from the checkpointer. All are additive/internal.

---

## 2. Deferred from the first wave (with rationale)

- **P1-E (universal per-LLM-call trace — PRM-03/TST-02/AC6): deferred.** Done properly this
  instruments **all 17** `chat.completions.create` sites (or a metering wrapper at
  `app/observability/langsmith.py:197 wrap_openai_client`) to capture `tokens`/`latency`/
  `model_ref` and emit the already-defined-but-uncalled `metrics.track_llm_call`, plus
  `envelope_hash`/`gate_decisions[]` on the turn trace. The test env **stubs `openai`**, so
  token/latency capture cannot be meaningfully verified headlessly — it needs LIVE
  verification against real responses and careful handling of streaming vs non-streaming
  usage. Rushing it under stubs risks silently-wrong instrumentation or a broken stream.
  → Recommended as a focused, LIVE-verified follow-up (single wrapper chokepoint + a metering
  unit test with a fake usage object).
- **P1-G untrusted-delimiter half (PRM-02): deferred.** Wrapping inlined user/RAG variables in
  marked delimiters changes **rendered prompt text**, which stub tests can't validate for
  output-quality regression. Needs prompt-eval, not just stub tests. (The No-Go completeness
  half of P1-G shipped.)

---

## 3. §11 acceptance-criteria status (delta vs the audit baseline)

| # | Criterion | Baseline | After wave | Note |
|---|---|---|---|---|
| 3 | ≤5 LLM Tier-1, calc=code | ✅ | ✅ | unchanged (already met) |
| 5 | core testable w/o graph; REPLAY in CI | 🟡 | 🟡↑ | new No-Go guardrail now runs per PR; broad REPLAY still deferred to full-stack CI job |
| 6 | versioned prompts; id@version+hash per LLM call | 🟡 | 🟡 | unchanged — universal trace is P1-E (deferred) |
| 7 | ack<100ms / first<1s / stream≡invoke test | ❌ | 🟡↑ | **stream≡invoke test now exists** (P1-F); ack/chip still Gate-1 G2 |
| 8 | untrusted-as-data; no write-tools | 🟡 | 🟡↑ | No-Go §5.4 completeness shipped; explicit delimiter deferred; write-tools already ✅ |
| 9 | lifecycle status as event sequence | ❌ | 🟡↑ | typed `CaseLifecycleStatus` + status field declared (headroom); routing not yet lifecycle-sensitive |
| 17 | RAG server-side filters / `solution_docs` scope | 🟡 | 🟡↑ | MCP tenant-filter overwrite closed (P0-B); `solution_docs` scope still P2 |

All other criteria are unchanged from `v18_audit_report.md` §E (P2 lifecycle items and the
Gate-1 reshape were intentionally out of the first wave).

---

## 4. Before / after metrics

| Metric | Before | After |
|---|---|---|
| Broad backend suite | 4688 passed, 9 skipped (exit 0) | **4707 passed, 9 skipped** (exit 0) — +19 new cases, 0 failures |
| Architecture + seam guardrails | 23 passed | 23 + governed stream≡invoke test |
| New V1.8 guardrail tests in CI (per PR) | 0 | `test_no_go_guard_v18.py` (doctrine fast suite) |
| Tier-1 LLM calls / governed turn | 3 baseline / 5 max-cycle | unchanged (no orchestration change in this wave) |
| MCP `metadata_filters` tenant-overwrite | possible (`.update()` merge) | blocked (reserved keys stripped) |

(LLM-call count, time-to-first-SSE-event, and largest-node line counts are unchanged because
the orchestration reshape — G1 — was parked.)

---

## 5. Remaining gaps (parked by decision or deferred)

**Gate-1 (await decision — `v18_audit_report.md` §G):**
- **G1** topology → §7.3 fan-out + thin-node/Proposal refactor (user chose the thin-node +
  Proposal direction; not started — golden-affecting, scheduled as its own effort).
- **G2** SSE `ack<100ms` + post-route chip + `messages` mode (needs a frontend-compat shim).
- **G3** `thread_id` → `case_id:turn_id` (session-continuity migration).

**Deferred this wave:** P1-E (universal LLM trace), P1-G delimiter half — see §2.

**Not yet started (P1/P2, additive — next waves per the patch plan):** P1-D checkpointer
business-data separation · P1-I `positions[]` headroom · P1-J move RWDR norm/calc into the
pack · P2-K SolutionProfile + datasheet ingestion · P2-L OperatingWindowCheck + `solution_docs`
· P2-M…P spec companion modes + Outcome-Records.

**SEC-04 (open decision):** at-rest encryption + TTL for transcript-bearing rows — choose
infra-level (document it) vs app-layer (implement). Not a code change yet.

---

## 6. Honest corrections made during implementation

- **CI exists** — the audit's "empty `.github`" / "no CI" finding was a **mirror artifact**
  (the read-only analysis mirror excluded root dotfiles). Corrected in `v18_audit_report.md`
  (TST-01, Risk #7) and `v18_phase0_inventory.md` §6. P0-A was re-scoped from "stand up CI" to
  "wire the new guardrail into the existing light CI".

---

## 7. Definition-of-Done status

- ✅ Four artifacts exist: `v18_phase0_inventory.md`, `v18_audit_report.md`,
  `v18_patch_plan.md`, `v18_final_compliance.md`.
- ✅ All shipped patches green; broad backend suite green (exit 0) after the wave.
- ✅ Gate-1 conflicts documented and parked (not auto-resolved).
- ⏳ Full §11 pass is **not** claimed — the first wave closes/advances AC5, AC7, AC8, AC9, AC17
  and leaves the P2 lifecycle criteria and Gate-1 reshape for subsequent, separately-approved
  waves.
- ☐ Not pushed: the branch `feat/v18-first-wave` is local on the VPS; push/PR is the user's call.

---

## 8. Post-audit LIVE finding — manufacturer-matching containment [ACCEPTED] (V1.8 Wave 0, 2026-06-06)

> **Audit-gap:** the V1.8 deep audit scanned the **dormant trio** (`capability_service` /
> `manufacturer_fit_matrix_service` / `problem_first_matching_service`) but **missed a live
> path**: `graph/nodes/matching_node.py` → `agent/domain/manufacturer_rfq.py` computes
> `match_candidates` / `winner_candidate_id` / `recommendation_identity` internally (default
> data = Dummy provider seeding "Acme"/"SealTech"). Surfaced and verified (V1–V4) during
> Wave 0.

**No-Go verdict: CONTAINED → ACCEPTED.** The winner/recommendation is internal RFQ-handover
only; it is walled off from every user surface on three independent layers:
1. the wire DTO `PartnerMatchingSummary` (`extra="forbid"`) does not declare the identity
   fields → stripped at the wire (`schemas/case_workspace.py:281,978`);
2. the backend never emits `manufacturer_fit_matrix`, so the latent frontend
   `ManufacturerFitPanel` (unmounted) can never light up;
3. (backstop) the L1/L2 manufacturer/recommendation/comparative-ranking guard on ChatReply.

**Enforced going forward** by `tests/architecture/test_mfr_match_dormant.py` + the default-OFF
`SEALAI_ENABLE_MANUFACTURER_MATCHING` flag. Full evidence + C2 show-me:
`docs/audit/v18_wave0_mfr_match_report.md`. Removal of the dormant infra remains a later
product decision (kept as P4 groundwork).
