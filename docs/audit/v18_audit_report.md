# V1.8 Deep Audit Report (read-only)

**Date:** 2026-06-06
**Spec:** `docs/sealing_intelligence_v1_8_universal_sealing_lifecycle_platform_blueprint.md`
**Conflict rule applied:** V1.8 > V1.7 > V1.6 on architecture/orchestration; V1.6 wins on the
contract level unless V1.8 §5/§6 says otherwise.
**Evidence rule:** every claim carries a repo-relative `path:line`. Where the repo names a
structure differently from the blueprint, it is **equivalence-mapped**, not declared a gap.
**Tests:** broad backend `4688 passed, 9 skipped` (exit 0); architecture+seam guardrails
`23 passed` (exit 0). See `v18_phase0_inventory.md` §5.

> **Headline.** The repo is the *Anbahnung* (inquiry) half of V1.8, built on a **strong,
> CI-testable security/state foundation** but in an orchestration **shape that differs from
> §7.3**. Two truths sit side by side: (1) the governed runtime already honours most V1.8
> *invariants* — single-writer State Gate, calculations-as-code, no module write-tools,
> server-side tenant filters, RAG-can't-write-truth, deterministic RFQ, a real No-Go linter;
> (2) the *form* is a long linear graph with a bounded in-turn loop and fat nodes (not a
> Send fan-out DAG of thin adapters), and the entire **Begleithälfte** (lifecycle,
> SolutionProfile, Operating Window, Outcome-Records, 5 new modes) is **not yet built**.
> Net: the P0/P1 orchestration items are mostly *re-shaping* work; the P2 lifecycle items
> are *additive* work on a reusable envelope substrate.

---

## A. Audit matrix — all 30 Annex-A IDs

Legend: ✅ erfüllt · 🟡 teilweise · ❌ fehlt · ⬜ n/a

### Orchestration (ORC)

| ID | Status | Evidence (`path:line`) | Rationale (1-line) |
|---|---|---|---|
| ORC-01 Turn graph vs §7.3 | 🟡 | `graph/topology.py:312-393`; node constants `:284-304` | A real compiled StateGraph exists, but topology is a 20-node **linear chain + bounded cycle**, not `route→state_gate_intake→dirty_scheduler→fan-out→merge→compose`. |
| ORC-02 Node thickness | ❌ | `nodes/intake_observe_node.py` (708 L, 12 local defs, 2 core imports); `evidence_node.py` (549/14/1); `matching_node.py` (529/10/4); `rfq_handover_node.py` (439) | Nodes carry substantial in-node logic; not the §7.3 "≤~15 lines → pure `core/` function" adapter shape. |
| ORC-03 LLM calls / Tier-1 turn | ✅ | router `semantic_intent_router.py:312`; in-graph `intake_observe_node.py:473` + composer `governed_answer_composer.py:296-348`; cycle `cycle_control.py:51` | **3 LLM calls baseline** (router + intake + composer); worst case **5** at `SEALAI_MAX_CYCLES=3` (router + 3×intake + composer). ≤5 budget met; loop erodes the margin. |
| ORC-04 Loops / supervisor / handoffs | 🟡 | `cycle_control.py:74-98`; `topology.py:363-364` | A **bounded, deterministic** re-analysis loop exists in the hot path (≤3); no supervisor-LLM, no agent-to-agent handoffs. Violates §1.6/§11.1 "no in-turn loops". |
| ORC-05 Send / fan-out + reducers | ❌ | `topology.py:353-376` (only `add_edge`); reducers `state/reducers.py` (layer-merge, not parallel) | No `Send`, no parallel branches; reducers exist for the 4-layer governed-state merge, not for parallel-write keys. |
| ORC-06 interrupt() usage | 🟡 | `graph/output_contract_assembly.py:1870,1970`; flag `state/models.py:846` | `interrupt()` is used for **RFQ user-confirmation/consent**, not §7.3 "merge-gate on Risk/Safety/Compliance". Resume is auth-bound via `_canonical_scope` (SEC-01). |
| ORC-07 Structured output + retry | 🟡 | `intake_observe_node.py:479` (`json_object`); `runtime/gate.py:121-124` & `user_facing_reply.py:64` (`json_schema`); composer retry `governed_answer_composer.py:310,346` | Structured output is used widely; retry exists (composer regenerate-once on No-Go), but there is **no uniform "exactly one retry with compacted error"** across all LLM calls. |
| ORC-08 Calculations = code | ✅ | `nodes/compute_node.py` (no LLM) → `app/services/calculation_engine`; MVP `v=π·d1·rpm/60000` | All engineering values are deterministic code; no LLM-performed calculation found. |
| ORC-09 Consolidation state | 🟡 | analysis spread across `medium_intelligence_node`, `domain/challenge_engine.py`, `v92/adversarial_review.py`; no `cross_impact`/`pack_impact` module | Analyses exist but are **not consolidated** into the §7.4 `cross_impact`/`pack_impact`/`adversarial` module taxonomy; no `Proposal`/`AnalysisModule` types. |

### State worlds (STA)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| STA-01 Checkpointer contents | 🟡 | `graph/__init__.py:7-24,41` (`GraphState(GovernedSessionState)`); `topology.py:197-250`; no `get_state` business reads | Business truth is **not read** from checkpoints (loaded from the live store), but the checkpointer **persists business fields** as a side effect when enabled — the two worlds aren't cleanly separated. Not a P0 read-leak; a P1 separation gap. |
| STA-02 Event store | ✅ | `domain/mutation_events.py:64` (`@dataclass(frozen=True)` immutable); `case_service.py:38-39` ("single write path"); snapshots `persistence.py:230-247`; `outbox_model.py` | Append-only immutable mutation events + snapshots + outbox; `CaseService` is the single writer (enforced by `tests/architecture/test_single_writer_invariant.py`). |
| STA-03 thread_id + retention | 🟡 | `governed_runtime.py:108`; Redis TTL `persistence.py:40,246`; checkpointer `topology.py:209-224` | `thread_id` exists and is **tenant-scoped** (`sealai:tenant:owner:session`) but not the §7.2 `case_id:turn_id` convention; checkpoint retention = Redis 24h TTL (no explicit checkpoint-sweeper job). |

### Prompts (PRM)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| PRM-01 Prompt inventory | ✅ | `agent/prompts/__init__.py:39-114`; `core/prompts.py:8-44`; ~101 `.j2`; ~0 inline LLM prompt strings | All productive prompts are repo Jinja2 templates via `Environment` registries; no LangChain hub/inline-string prompts. |
| PRM-02 StrictUndefined + untrusted delimiters | 🟡 | `agent/prompts/__init__.py:49-55` (StrictUndefined); composer passes user text as a separate JSON `user` message `governed_answer_composer.py:393-398`; inline vars in `prompts/final_answer_router.j2:53`, `guard/unsafe_instruction_reply.j2:24` | StrictUndefined holds and user text can't become template *source*, but there is **no explicit marked untrusted-delimiter** convention as §7.7 requires. |
| PRM-03 Template versioning in trace | 🟡 | `v92/contracts.py:43-51` (`PromptTrace`); `v92/prompt_audit.py:16-59`; emitted only for composer `governed_answer_composer.py:514-546`; absent in `runtime/answer_trace.py` | `template_id@version + prompt_hash` exists and is correct, but is **only emitted for the governed composer**, not for every LLM call. |
| PRM-04 RFQ composer determinism | ✅ | `templates/rfq/rfq_one_pager.j2` (pure iteration); `communication/rfq_one_pager.py:224-375` (snapshot + SHA-256); `rfq_preview_service.py` & `api/v1/renderers/rfq_html.py:3-5` ("no LLM") | RFQ structure/values are 100% deterministic from a `case_revision` snapshot; LLM fills only bounded, guarded intro/confirmation slots. |
| PRM-05 No-Go linter | ✅ | `templates/no_go_guard.py:19-112`; approval patterns `governed_answer_composer.py:52-70`; regenerate-once `:130-163,1206-1223` | Deterministic post-check with regenerate-once-then-fallback; list matches V1.6 §18.3 + V1.8 §5.4 release/suitability (minor: literal "können Sie bedenkenlos" not an explicit entry). |

### Streaming (STR)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| STR-01 stream_modes + SSE vocab | 🟡 | `governed_runtime.py:375-379` (`["values","updates","custom"]`); `api/sse_contract.py:21-178`; BFF `route.ts:22-26,483-500` | Typed SSE contract with no LangGraph leakage, but `messages` mode is **not** consumed (`values` substituted), and the event vocabulary (`delta/state_update/progress/done`) ≠ blueprint (`ack/progress·chip/cockpit_patch/token/envelope_final`). |
| STR-02 ack <100ms + early chip | ❌ | `streaming.py:1249-1468` (first `yield` only after full dispatch); no `ack` event in `api/`; chips folded into terminal `state_update` `:956-959` | First SSE byte is gated behind the full async safety-guard + routing (≥1 classifier/LLM); no sub-100ms ingest `ack`, no standalone post-route progress/chip event. |
| STR-03 stream≡invoke test | ❌ | only structural seam `test_governed_runtime_seam.py:103-156`; conversation-parity `test_conversation_runtime.py:986-997` | No test compares the governed graph's streamed final envelope to its `ainvoke()` result. (Draft-token withholding before final guard **is** enforced — `governed_runtime.py:345-348`, `governed_answer_composer_node.py:138-141`.) |

### Security / Tenant (SEC) — P0

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| SEC-01 Tenant at repository layer | ✅ | `case_service.py:782-788` (`_require_tenant_id`); read scope `:316,322-323`; ORM `case_record.py:68-75`; DB NOT-NULL migration `alembic/versions/b8c4d6e2f901_*.py:30-67`; `auth/dependencies.py:129-144` | Tenant is mandatory at ORM + service + DB layers; reads are owner+tenant scoped with no existence-leak; **no IDOR path found**. |
| SEC-02 Vector filters server-side | ✅ | `rag_orchestrator.py:646-733` (`must:[tenant]` + `should:[visibility]`); `evidence_node.py:471` + `real_rag.py:110-120` (abort if no tenant) | Single collection, indexed `tenant_id` keyword filter, filters built **server-side** from the verified user; no LLM-output path constructs the live filter. (Low-sev: strip caller `tenant_id` from MCP `metadata_filters` — `knowledge_tool.py:1169`.) |
| SEC-03 No module write-tools | ✅ | `topology.py` (no `ToolNode`/`bind_tools`); MCP tools read/stub only `knowledge_tool.py:424-490`; `graph/tools.py` bound only in `cli.py`/tests | Governed runtime is a pre-fetch DAG; entire LLM-callable surface is read-only/stubbed; no tool mutates case truth. |
| SEC-04 Secrets/trace handling | 🟡 | hash-only `prompt_audit.py:1-59`; redaction `observability/sealai_quality.py:25-148`; `langsmith_capture_llm_content=False`; but plaintext `postgres_logger.py:16`, no `encrypt`/`Fernet`; Postgres snapshot text has no TTL | Secrets/prompt full-texts are kept out of logs (hash + redaction); **gap vs §7.11**: stored conversation/snapshot text is app-layer plaintext and durable snapshots have no code-visible TTL. |

### Knowledge (KNW)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| KNW-01 Cross-cutting vs domain + payload | 🟡 | split in `services/knowledge/*`; `rag_schema.py:53-57` (`pack_affinity`), `:42-80` payload; second thinner stack `agent/rag/setup_collections.py:39-44` | The split is real (`pack_affinity` flag) and most mandatory payload is present, but **`Norm` is not a structured payload field** and `pack_affinity` is currently retrieval-inert. |
| KNW-02 RAG can't write confirmed | ✅ | gate `rwdr_mvp_brief.py:3788-3843`; `_NEVER_BRIEF_SOURCE_TYPES` `:301-305`; echo note `:2863-2886`; `source_validation.py:263-268` | RAG is structurally barred from becoming confirmed case truth; surfaces only as a `rag_supported` note. (Nominal: the literal `rag_supported_note` token/full §6.2 status set isn't in the central enum.) |

### Lifecycle (LIF)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| LIF-01 Schema headroom §6 | ❌ | readiness-only `rwdr_mvp_brief.py:26-31`; free-form `case_record.py:32-34`, `models.py:854-857`; no `SolutionProfile`/`OutcomeRecord` (0 hits); `Provenance` `models.py:128-141` lacks `datasheet_extracted`/`outcome_observation` | No lifecycle state machine, no SolutionProfile envelope, no Outcome-Record, and the status/origin enums lack the §6.2 vocabulary. The §6 constructs are net-new. |
| LIF-02 Hooks (manufacturer_response, document_analysis) | 🟡 | `source_validation.py:18-20` + `rwdr_mvp_brief.py:2825-2860`; doc extraction `v92/orchestrator.py:1037-1200` → `DocumentEvidenceState` `v92/models.py:307-329` | Both hooks the blueprint says "exist" are confirmed and usable as the SolutionProfile seam, but currently feed the requirement profile / echo note and don't stamp `datasheet_extracted` + source-page. |
| LIF-03 "exactly one position" assumptions | ❌ | `rwdr_mvp_brief.py:33-81,115-164`; `RfqState.dimensions` flat dict `models.py:815`; projection `case_workspace.py:572-720`; DB `case_record.py:24-66` | Single-position is assumed structurally throughout (one d1/D/b); no `positions[]` headroom anywhere — violates §6.6/AC18. |

### Modes (MOD)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| MOD-01 Mode inventory + extensibility | 🟡 | `domain/pre_gate_classification.py:12-21`; `semantic_intent_router.py:21-31`; `v7_contracts.py:23-37` (`AnswerMode` 14); dispatch cascade `dispatch.py:649-1250` | A rich V1.6/V1.7 conversation-mode layer exists, but the **5 V1.8 §5.3 companion modes are absent** and the router is a hard-coded branch cascade, not a route-node + mode table. |
| MOD-02 Standard-part lookup | ❌ | `norm_modules/din_3760_iso_6194.py:17-213` (a *checker*, not a size table); `standard_designation` is passthrough only `inquiry_extract_service.py:84` | No size-series→designation lookup exists; the DIN module only pre-checks geometry consistency. |

### Pack / Core (PCK)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| PCK-01 Core/Pack boundary | 🟡 | `domain/domain_pack.py:24-58` (`DomainPack` Protocol); `seal_packs.py:35-71`; enforcer `tests/architecture/test_core_seal_type_branching.py`; but RWDR logic in `nodes/norm_node.py:30,206`, `nodes/compute_node.py:21-22` | A genuine, CI-enforced Core↔Pack seam exists, but the `DomainPack` contract covers only ~6 of §3.2's ~20 members and RWDR norm/calc specifics remain wired into generic graph nodes. |
| PCK-02 Registry mechanic | ✅ | `seal_packs.py:74-80` (`pack_for`), `:108-159` (path/calc/fields selectors) | Runtime `seal_type/family/path/calc_id → pack` resolution exists; deliberately a one-entry tuple per Rule of Three. |

### Tests / Observability (TST)

| ID | Status | Evidence | Rationale |
|---|---|---|---|
| TST-01 Test pyramid + REPLAY | 🟡 | 333 backend `test_*.py`; stubs `backend/conftest.py:411-604,827-875`; goldens `test_golden_conversations_v16.py`, `api/tests/test_rwdr_golden_cases.py`; CI `.github/workflows/backend-contracts.yml`, `langgraph-v2-guardrails.yml` | Strong core-first suite that runs without the real graph/LLMs, and golden conversations exist — but they are **deterministic-code goldens, not REPLAY of recorded LLM answers**. **CORRECTION:** CI **does exist** (the earlier "empty `.github`" note was a mirror artifact — root dotfiles were excluded from the analysis mirror); it is deliberately light (architecture enforcers + a small doctrine/golden subset), with the broad suite + full REPLAY deferred to a "future full-stack job". |
| TST-02 Turn-trace vs §7.11 | 🟡 | `v92/contracts.py:381+` (`TraceSummary`); `prompt_audit.py` (template+hash); `turn_timing.py`; but `metrics.py:352` `track_llm_call` **never called**; no `proposals[]`/`dirty_set`/`gate_decisions[]`/`envelope_hash`; no eval metrics | A real per-turn trace (route/tier/timing) + composer prompt-audit exist, but §7.11 is materially incomplete (no tokens/latency/model_ref captured, no proposals/dirty_set/gate-array/envelope_hash, no LIVE eval metrics). |

**Tally:** ✅ erfüllt ×11 · 🟡 teilweise ×14 · ❌ fehlt ×5 · ⬜ n/a ×0.

---

## B. Core/Pack boundary map + equivalence table

**Type-agnostic Core (correct):** `domain/domain_pack.py`, `domain/seal_packs.py` (seam +
selectors), graph plumbing (`topology.py`, boundary/intake/normalize/assert/governance/
output/composer nodes), `state/reducers.py` (routes via `state_gate_type_sensitive_fields_for`),
`challenge_engine.py`/`risk_readiness.py`/`case_workspace.py` (routed via `pack_for_*`).

**RWDR-specific (correct location — the pack):** `domain/seal_packs.py::RwdrPack`,
`agent/domain/rwdr_calc.py`, `services/rwdr_mvp_brief.py`,
`norm_modules/din_3760_iso_6194.py`.

**RWDR logic leaking into plumbing (PCK-01 finding):** `nodes/norm_node.py:30,206`
(hardwires the RWDR DIN/ISO registry into the governed topology); `nodes/compute_node.py:21-22`
(RWDR DIN-3760 formula assumptions in a generic node).

**Equivalence map (blueprint term ↔ repo term)** — load-bearing rows:

| V1.8 term | Repo equivalent | Location |
|---|---|---|
| State Gate (single writer) | reducer chain + `CaseService` (AST-enforced) | `state/reducers.py`; `tests/architecture/test_single_writer_invariant.py` |
| Module / Proposal (§7.4) | graph **nodes** mutating `GraphState` via reducers (no typed `Proposal`) | `graph/nodes/*` |
| Dirty Scheduler (§7.5) | **none** — fixed linear topology | `topology.py` |
| `cross_impact`/`pack_impact`/`adversarial` | `medium_intelligence` + `challenge_engine` + `v92/adversarial_review` (unconsolidated) | resp. files |
| `compose` node | `governed_answer_composer_node` | `nodes/governed_answer_composer_node.py` |
| `project_and_persist` | `output_contract_node` + `state/projections.py` | resp. files |
| Event Store | `mutation_events` + snapshots + outbox | `domain/mutation_events.py` |
| Checkpointer (execution only) | LangGraph Redis/InMemory saver (but holds business too) | `topology.py:197-250` |
| DomainPack (§3.2, ~20 members) | `DomainPack` Protocol (~6 members) | `domain/domain_pack.py:24-58` |
| `domains/registry.py` | `seal_packs._PACKS` tuple + `pack_for*` | `domain/seal_packs.py:71-159` |
| Field Envelope / origin | `CaseField` (status/provenance) | `state/models.py:156-168` |
| `rag_supported_note` | note `status="rag_supported"` (echo) | `rwdr_mvp_brief.py:2885` |
| Operating Window (§5.6) | **none** (`_known_operating_window` is a material lookup) | `material_intelligence.py:231` |
| SolutionProfile / Outcome-Record | **none** | — |

---

## C. State-worlds inventory

| Concern | World | Store | Single writer? | Lifetime |
|---|---|---|---|---|
| Case truth (fields, status, provenance) | Business | Postgres `case_record` + `case_state_snapshot`; live via `_load_live_governed_state` | Yes — `CaseService` / reducer chain (`test_single_writer_invariant.py`) | durable |
| Case events | Business | immutable `mutation_events` (frozen dataclass) + `outbox` | Yes — `CaseService` | durable (append-only) |
| Conversation/session | Business | Redis governed-state JSON | via persistence wrapper | 24h TTL |
| Turn execution (node state, interrupt, resume) | Execution | LangGraph checkpointer (Redis prod / InMemory dev / None) | LangGraph runtime | Redis 24h (no explicit sweeper) |
| **Leak** | — | `GraphState⊇GovernedSessionState` ⇒ checkpointer holds business fields when enabled; **not read back as truth** | — | — |

**Verdict:** the two worlds exist and business truth is sourced from the event store, not the
checkpointer (good). The remaining §7.2 work is to **stop the checkpointer from persisting
business fields** (strip to execution-only) and adopt the `case_id:turn_id` thread_id + an
explicit checkpoint-retention job.

---

## D. Prompt inventory + mode inventory

**Prompt inventory (PRM-01):** ~101 `.j2` across 5 registries, all via Jinja2 `Environment`
with `StrictUndefined` (except the RAG-ingest `DebugUndefined` renderer, by design); ~0 inline
LLM prompt strings. Versioning + SHA-256 hash exist (`PromptTrace`) but are emitted only for
the governed composer. Two roles (§7.7) are separated: assembly registries vs deterministic
RFQ/chat output renderers.

**Mode inventory (MOD-01):**

| V1.8 §5.3 companion mode | Present? | Nearest repo equivalent |
|---|---|---|
| `standard_part_fast_path` | ❌ | none (mobile *leakage* fast path is unrelated, `dispatch.py:670-700`) |
| `solution_explanation` | ❌ | none (no SolutionProfile to ground it) |
| `installation_guidance` | ❌ | none |
| `operation_qna` | ❌ | none |
| `incident_intake` | ❌ | `ConversationIntent.failure_analysis`/`complaint_case` + leakage triage — no Soll-Ist, no Outcome-Event |
| *implemented today* | ✅ | `GREETING, META_QUESTION, KNOWLEDGE_QUERY, DEEP_DIVE, BLOCKED, DOMAIN_INQUIRY, RECOVERY` + 14-value `AnswerMode` |

---

## E. Gap list keyed to the 18 §11 acceptance criteria

Severity uses V1.8 phase priority (P0 foundation → P3 expansion). "Blast radius" = contracts/
files a fix touches.

| # | §11 criterion | Status | Sev | Blast radius |
|---|---|---|---|---|
| 1 | Standard turn is a DAG, no supervisor/loops | 🟡 | P1 | topology + cycle_control + governance routing; **golden-affecting** (the cycle changes multi-turn behavior) |
| 2 | Analysis returns typed Proposals; gate is single writer | 🟡 | P1 | single-writer ✅ already; adding a `Proposal` type touches every node + reducers |
| 3 | ≤5 LLM Tier-1, ≤1 Tier-0, calc=code | ✅ | — | calc-as-code ✅; keep loop ≤ budget |
| 4 | Business data only in event store; checkpointer retention | 🟡 | P1 | `GraphState`/`graph/__init__.py`, `topology.py` checkpointer wiring; **no public contract** |
| 5 | Thin nodes; core testable w/o graph; REPLAY green in CI | 🟡 | P1 | node refactor (large) + a CI workflow; goldens exist but not REPLAY |
| 6 | All prompts versioned Jinja2 StrictUndefined; id@version+hash per LLM call in trace | 🟡 | P1 | additive: extend `answer_trace.py` to carry `PromptTrace` for every call |
| 7 | SSE ack<100ms, first progress<1s, stream≡invoke test | ❌ | P0/P1 | `streaming.py` + BFF `route.ts` + `useAgentStream.ts`; **SSE contract / frontend-affecting** |
| 8 | Untrusted only as delimited data vars; no module write-tools | 🟡 | P1/P2 | write-tools ✅; add explicit untrusted delimiter to legacy templates (additive) |
| 9 | Lifecycle status as event sequence; modes/dirty lifecycle-sensitive | ❌ | P2 | new enum + transition events; `state/models.py`, router |
| 10 | ≥1 SolutionProfile with datasheet origin+page | ❌ | P2 | new envelope type; reuse `CaseField`; `Provenance` enum +`datasheet_extracted` |
| 11 | Operating Window deterministic projection | ❌ | P2 | new `OperatingWindowCheck` (pure code) + projection + UI panel |
| 12 | solution_explanation grounded only | ❌ | P2 | new mode + grounding on SolutionProfile/RAG |
| 13 | standard_part_fast_path <60s | ❌ | P2 | size-table in pack + new mode + Tier-0 path |
| 14 | Incident → Soll-Ist + outcome event | ❌ | P2 | new mode + Outcome-Event |
| 15 | No path bypasses gate; safety formula in companion modes | 🟡 | P1 | gate not bypassed today ✅; safety formula must extend to (not-yet-built) companion modes |
| 16 | Outcome-Records schema + tenant-scoped persistence + anon aggregation | ❌ | P2 | new model + repo (tenant-scoped) + governance |
| 17 | RAG `solution_docs` scope tenant-scoped; server-side filters | 🟡 | P2 | server-side filters ✅; add `solution_docs` scope/payload |
| 18 | `positions[]` — no hard "exactly 1" | ❌ | P3 (vorsorge now) | brief field maps + `RfqState.dimensions` + projection |

---

## F. Risks & open questions (max 10)

1. **Topology reshape vs goldens (Gate-1).** Moving to the §7.3 fan-out DAG and removing the
   in-turn cycle would change multi-turn behaviour that `test_golden_conversations_v16.py`
   depends on. **Question:** adopt §7.3 as a true rewrite, or keep the linear+cycle runtime
   and treat §7.3 as the *logical* contract (thin-node + proposal refactor without changing
   edges)? Recommendation: the latter first.
2. **`Proposal` type vs current reducer model.** The repo already enforces single-writer via
   reducers; introducing `AnalysisModule`/`Proposal` is large and overlaps existing seams.
   Worth it only if it buys testability/consolidation — needs an explicit decision.
3. **SSE contract change (Gate-1).** Adding `ack`/renaming to `envelope_final`/adding a
   post-route chip event touches the frontend BFF + hook. Must ship a **compatibility shim**
   (keep current event names, add new ones) to avoid breaking the live UI.
4. **thread_id convention change (Gate-1).** Switching `sealai:tenant:owner:session` →
   `case_id:turn_id` risks breaking session continuity / existing checkpoints. Needs a
   migration/forward-compat plan.
5. **Checkpointer business-data separation.** Stripping `GovernedSessionState` fields from the
   checkpointed `GraphState` must not break `interrupt()`/resume (which currently relies on
   the full state). Needs care; covered by P1 patch.
6. **SEC-04 encryption/TTL.** Decide explicitly: rely on infra-level at-rest encryption for
   `chat_messages`/snapshots (and document it) **or** add app-layer encryption + a retention
   job. Today it is plaintext with no code-visible TTL on durable transcript rows.
7. **CI is light, not absent (corrected).** CI exists (`backend-contracts.yml` +
   `langgraph-v2-guardrails.yml`, on push/PR) but is deliberately minimal — architecture
   enforcers + a small doctrine/golden subset; the broad suite + full golden REPLAY are
   deferred to a "future full-stack job". So "REPLAY green per PR" (§7.11/AC5) is only
   partially enforced. (The earlier "empty `.github`" claim was a mirror artifact.)
8. **Two RAG stacks.** `services/rag/*` (rich payload, `pack_affinity`, visibility) vs the
   thinner `agent/rag/setup_collections.py` (only `sts_*`/`doc_type`/`language` indexed).
   Confirm which is authoritative before adding `solution_docs` scope.
9. **MOD-01 router shape.** The 5 new modes are blocked less by routing than by missing
   substrate (SolutionProfile/Operating Window/size-table). Sequencing must build §6 schema
   before the companion modes (matches V1.8 P1→P2).
10. **`scripts/check_rwdr_mvp_demo.sh` / demo gate.** Referenced in `AGENTS.md` but not in the
    mirror — confirm it exists on the VPS, else the guided-demo gate can't run.

---

## G. Gate 1 — items requiring a human decision before Phase 3

These would break a V1.6 golden, a public API, or a frontend-consumed SSE event, so per the
mission they are **parked for decision** and excluded from the auto-proceed scope:

- **G1.** Topology rewrite to §7.3 fan-out + removal of the analysis cycle → **golden-affecting**
  (risk #1). Options: (a) full §7.3 rewrite; (b) thin-node/Proposal refactor keeping edges;
  (c) defer.
- **G2.** SSE event-vocabulary change (`ack`, `envelope_final`, post-route chip) → **frontend
  contract** (risk #3). Requires a compat shim.
- **G3.** `thread_id` → `case_id:turn_id` (risk #4) → session-continuity migration.

Everything else in §E is **additive or internal** and can proceed in small patches once the
report is approved (see `v18_patch_plan.md`).
