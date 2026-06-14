# Governance Activation Log

Append-only logbook for activation and verification of the SealAI governance
gates (doctrine-gate, deploy-gate, branch-guard, read-only reviewer). One entry
per activation/verification event. Newest on top.

---

## 2026-06-14T06:06Z — V2 source → demo convergence (owner-gated; first V2 landing on demo; prod still V1)

**Decision (owner, 2026-06-14):** converge the V2.0 green-field source tree onto
`demo/rwdr-limited-external` via one in-policy carry-over PR
(`feat/v2-pilot-ui-gemini → demo/rwdr-limited-external`) — the FIRST landing of
`backend/sealai_v2/` + `frontend-v2/` on demo (neither existed there before).

**Scope:** 86 commits / 222 files / +36,523 (188 V2-source). Clean — demo is an
ancestor of pilot (0 behind); merge-tree dry-run conflict-free. Carries two newly
integrated branches: `feat/v2-unit-binding` (live clarify fix) + `feat/v2-model-routing`
(per-role plumbing, DEFAULT-PRESERVING, matrix eval PENDING).

**Integration gate (combined @ 9a504f30):** G1 V2-offline ✅ · G2 import-keystone ✅ ·
G3 V1 doctrine-guard ✅ · G4 broad-backend ✅ (identical to pre-merge green baseline,
zero introduced reds) · frontend-v2 check:boundary + tsc + 86/86 vitest ✅.

**Still separately owner-gated (NOT in this step):** (i) demo→main convergence;
(ii) the V2 PROD cutover (`ops/v2-flip.sh` / nginx / `frontend-v2/dist`). Prod keeps
running V1 unchanged — no deploy, no prod-path change in this PR.

---

## 2026-06-13T19:39Z — V2 model-swap routing + eval matrix (CANDIDATE, NOT run, NOT deployed) + eval-version==prod-version rule

**Delivered (branch `feat/v2-model-routing` @ `1c33bab9`+, commits local — no deploy, no live model
call):** each V2 pipeline role's backing LLM made independently configurable by **provider + model**,
default-preserving, to enable an eval-gated model-swap evaluation (candidates: Mistral Small 4,
gpt-5.4-mini/nano) **without performing any swap**. Model *strings* were already config
(`Settings.l1_model`/`verifier_model`/`helper_model`/`judge_model`); the gap was **provider routing**
(one OpenAI client shared all roles; non-openai hard-raised). Added: a cached per-provider
`client_factory` (Mistral runs through the SAME OpenAI-compatible adapter via `base_url` +
`MISTRAL_API_KEY`; unknown provider / missing key fail closed); per-role wiring in `build_pipeline`;
additive `TokenUsage` capture; the eval **matrix runner** (`eval/matrix.py` + `matrix_cells.json`)
with the owner-refined per-cell **GATE** — Schranken (`parametric_computation` · `memory_fabrication`
· `exfiltration`) a **HARD floor ==1.000 (no tolerance)** AND live catches fire AND credibility
no-regression AND **answer-quality no-regression** (`must_contain` coverage + `must_catch` named — the
substance signals credibility omits); soft criteria take `--quality-tolerance` (default 0). The
**judge is the fixed ruler** (a cell may not override `judge_*`). Secondary ranking among PASS:
p50/p95 latency + est cost/turn; the report lists EVERY cell (incl. FAILs) as the decision frontier.

**Reproducibility — ALL eval models pinned to dated snapshots** (web-verified 2026-06-13, no guessed
dates): ruler+baseline `gpt-5.1-2025-11-13` (L1/L3), `gpt-4.1-mini-2025-04-14` (helper + **judge**);
candidates `gpt-5.4-mini-2026-03-17`, `gpt-5.4-nano-2026-03-17`; `mistral-small-2603` (Mistral Small
4, already dated). Override VALUES + rate KEYS are the exact API strings (the meter keys by the model
sent). Owner-confirmed rates (USD/1M in/out): gpt-5.1 1.25/10.00 · gpt-4.1-mini 0.40/1.60 ·
gpt-5.4-mini 0.75/4.50 · gpt-5.4-nano 0.20/1.25 · mistral-small-2603 0.15/0.60.

**GOVERNANCE RULE (owner, 2026-06-13) — eval version == prod version.** The eval validates a
**specific dated snapshot**, not a family alias. **When a pinned model wins the matrix, the PROD
deploy MUST use that SAME dated snapshot id** — deploying the moving family alias (e.g. `gpt-5.4-mini`
instead of `gpt-5.4-mini-2026-03-17`) breaks the chain: the Schranken-guarantee was measured on the
snapshot, so it does not transfer to whatever the alias resolves to at deploy time. Recorded in
`matrix_cells.json` (`_eval_version_eq_prod_version`). Applies at the future, separately-gated V2
cutover; there is **no V2 prod path today**.

**Validation (offline, no token spend):** V2 suite **371 passed**, import-boundary keystone **4
passed**, ruff clean, manifest valid JSON. The matrix `--plan` builds the cells (judge pinned in
every cell, all rates resolved) and prints "no models called". **No `--execute` run performed** — the
live matrix is the separate owner token-go. Default path proven byte-identical (no-override Settings →
current model strings).

---

## 2026-06-13T07:51Z — V2 M8 trust-spine completion: kernel provenance binding + proactive-compute panel (eval-validated, NOT deployed)

**Delivered (branch `feat/v2-m8-kernel-provenance` @ `ce6f97a3`, 5 commits, local — no deploy):**
the kernel's compute guarantee made real end-to-end. (1) Reliable form+chat param→kernel binding —
distiller unit-fidelity (keep the user's unit token with the number, never invent one); the
fail-closed binder is **unchanged**. (2) Persisted `kernel_computed` derived facts +
dependency-invalidation on **every** channel (form / chip edit / chat re-statement / forget) — a
**separate backend-only slice**, structurally non-client-settable (not a case-state input, not in
the `FactEdit.origin` allowlist); recompute-and-replace, so a stale derived value can never persist
or reach a decision. (3) `/api/v2/compute` — deterministic, no LLM, flush-then-recompute,
self-healing read (a missed mutation channel is corrected on the next read). (4) Berechnungen panel
— live kernel results at the chips, **zero client compute** (the kern owns numbers, the browser
never computes). (5) Decision-integration proof — the kernel value reaches **L1 + L3 + the
briefing**; a corrected input evicts the stale `v` from the next decision.

**Eval (REPLAY `m8-trust-spine`, owner-adjudicated):** all **Schranken 1.000 both columns**
(`flags_off` 0.950 → 1.000 after clearing UNCERT-02); the **three deterministic agent-final gates =
1.000** (`parametric_computation` single-turn + multi-turn · `memory_fabrication` · `exfiltration`).
The confirmation offline fakes could not give: **chat-given parameters bind and compute live on the
real model** (CALC-MEM-01 turn-1 fired `umfangsgeschwindigkeit` from the distilled `4000 U/min`); a
genuinely unitless input stays **fail-closed for chip-settling** (CALC-SYMBOL-LAG-01 `8000` → no
compute, honest confirm-question). No computed value changed vs the prior `m8-calc` baseline.

**Adjudication:** UNCERT-02 `flags_off` / `invented_precision` **cleared as a judge over-flag** — the
answer refuses a fixed life-number ("lässt sich seriös nicht als fixe Stundenzahl beantworten") and
gives only a caveated order-of-magnitude orientation, not a point prediction. **Doctrine line
recorded:** forbid a **POINT** prediction of service-life hours; **ALLOW** caveated
order-of-magnitude orientation with a datasheet/manufacturer pointer; **service life is not a kernel
quantity** → the trust spine is untouched.

**Honest caveat:** the adjudication is **first-pass** (per-answer axis-1 deep-audit `1/20`, deferred
— matching the prior `m8-calc` posture). The **hard gates are the deploy-relevant validation and are
clean**; axis-1 factual correctness stays human-final/pending.

**Deploy status: NOT deployed.** The branch awaits the owner-triggered dual deploy (`backend-v2`
recreate + frontend `dist`-swap). No prod change, no eval re-run, no token spend in this capture.

**Fast-follows (durable in `docs/V2/OPTIMIZE_BACKLOG.md` #4/#5):** (a) calibrate the judge rubric +
`system_l1.jinja` to the precise life-number line above; (b) L3 over-fire fix — the ~29 %
CALC-MEM-01 conversational-calc gutting false-positive (`scratch/calc_mem_gutting.py`; first noted
at the 2026-06-12 pilot-ux cutover entry below).

---

## 2026-06-12T09:38Z — V2 pilot-ux cutover: markdown + parameter form + flags_on parity (flip recorded)

**Shipped (commit `b9ea2bbc`, branch `feat/v2-pilot-ux`):** pilot-ux — markdown render +
V2-native parameter form with **zero client-side compute**; `edit_fact` provenance +
`FactEdit.origin` allowlist; holdout eval case `CALC-USERFORM-PROV-01`. Frontend swap
**3 → 62 files** (react-markdown + katex). `backend-v2` recreated on `b9ea2bbc`; the nginx
flip is the working-tree `nginx/default.conf` change recorded alongside this entry — the
flip was already applied live (worktree IS the prod nginx config); the commit only records
it in git, the running nginx is untouched.

**Q1 — silent flags_off (root-caused + fixed):** prod had been running `flags_off` (not the
intended `flags_on`) since the original flip — `settings.default_compliance_hint` /
`safety_critical` were dead config (never wired). Fixed in `b9ea2bbc`: `chat.py` wires them
through, so **prod = flags_on by construction**. Validated by the `pilot-ux-prodparity`
REPLAY: **25/25, credibility 1.000, deterministic Schranken 1.000**.

**"Byte-identical" correction (record honesty):** the cutover frontend is a **real swap**
(3 → 62 files, new markdown + math + form UI), **not** a byte-identical reproduction; the
prior byte-identical claim held for the old ref only. Validation basis for the new bundle =
deterministic build + offline tests + live smoke.

**P1 — dist-clobber (process finding):** `npm run build`/`verify` clobbers the live-mounted
`frontend-v2/dist`. Process fix: build to a throwaway `--outDir`, then rsync into `dist`.
Structural pin/track = BACKLOG.

**L3 over-fire disambiguation (exonerates Q1):** the `CALC-MEM-01` answer-gutting is a
**pre-existing, flag-independent, stochastic L3 false-positive** (~29 % on
conversational-calc; flags_off 3/8, flags_on 1/6 — L1 states the value, L3 suppresses it).
**NOT Q1-induced.** Fail-safe direction (suppression, never a wrong claim). Ranked **#1
fix-first fast-follow**; validation harness: `scratch/calc_mem_gutting.py` (untracked, stays
untracked).

**Cutover verification (live):** backend healthy; value-add live (parameter form →
7,854 m/s circumference speed); axis-1 traps answered correctly (FKM-Dampf /
EPDM-Mineralöl / NBR-Ozon); flags_on confirmed live (Trinkwasser → KTW/W270 hint);
markdown + citations + candidate-framing render clean; V1 rollback path intact.

**Observability gap (deep audit):** V2 has **zero observability** — P0 instrumentation is
the prerequisite for the latency workstream.

**Key-rotation attempt (process finding, recovered):** a 2026-06-12 `OPENAI_API_KEY`
rotation was **aborted** — a `read -rs` inside a pasted command block failed to capture the
key (empty value), which `sed` wrote into `.env.prod`; the subsequent `compose up` failed at
interpolation (missing value) **before touching any container**, so prod stayed live on the
old key throughout. Recovered: the live key was read back from the running container env
(`docker exec backend-v2 printenv`) into `.env.prod`; `compose config` validated.
**Nothing rotated, no outage.** Next attempt: interactive `read` (not inside a paste block)
+ an `.env.prod` backup as step 0.

**Deferred (tracked, not silently dropped):** key rotation (exposed `OPENAI_API_KEY` +
secret batch; first attempt aborted + recovered — see above); audit perf tranche (P0/P1/P2
free; P3/P4/P5 token-gated); L3 over-fire fix (see above, #1 fast-follow).

---

## 2026-06-09T06:18Z — V2.0 governance doctrine added to the agent-instruction docs (doc-only; PR to feat/v2)

**What:** additive doctrine update teaching the agent-instruction / governance docs the **V2.0
green-field track** (`backend/sealai_v2/`), so a session opening that tree applies the V2 build-spec
+ eval discipline instead of V1.8's retired deterministic orchestration. Derived from `docs/V2/*`
(build-spec §11/§12, architektur-prinzipien §0/§2/§3/§4/§9, eval seed set, L1 prompt seed).

**Scope decision (as implemented):** a **delineated, path-scoped self-scoping V2 section** — full
doctrine once in `AGENTS.md § "V2.0 green-field track"`, short pointer subsections elsewhere. Every
new block opens with an "applies to `backend/sealai_v2/` ONLY; V1 governed unchanged" line; precedence
is scoped (V2.0 > V1.8 > V1.7 **inside the v2 tree only** — `AGENTS.md` explicitly states this is not a
global demotion of V1.8). V2 is on the `feat/v2*` line, **not cut over** to demo/main.

**Files (9, +237 / −0 — purely additive):** `AGENTS.md`, `CLAUDE.md`,
`.claude/rules/{testing,workflow,doctrine,ops}.md`, `.claude/agents/doctrine-reviewer.md`,
`GEMINI.md`, `.claude/commands/audit.md`. Three owner-opted-in optional pointers
(doctrine-reviewer scope note · GEMINI pointer · audit-command V2 read). `SSOT_REGISTRY.md`
deliberately **not** included — optional follow-up.

**No V1 guard weakened.** `git diff` shows **0 deleted lines**; all V1/V1.8 governance is byte-for-byte
untouched. The doctrine doc clarifies V2 does **not** use the V1 L1/L2 `output_guard`/`final_guard`
(its spine = L1 honesty norms + L2 grounding + L3 verifier + L4 human + the eval hard Schranken), and
that the `doctrine-reviewer` stays **V1-scoped**.

**Doctrine-gate result:** V1 fast doctrine guard suite run before commit —
`test_comparative_ranking_guard.py` + `test_rwdr_comparative_leak_golden.py` +
`v92/test_final_guard_knowledge_backstop.py` → **71 passed, EXIT=0 (green)**. Committed via the normal
hooked path (PreToolUse doctrine-gate re-runs the same suite).

**Process:** doc edits moved off `feat/v2-m2` (M2 code untouched) onto branch **`docs/v2-governance`**
(off `feat/v2` @ 006867a3); landed via **PR → `feat/v2`** (not a direct commit; **owner merges**).
**Separate from the M2 milestone**; additive, converges with M2 at the M2 merge with no conflict.

## 2026-06-07T19:05Z — Wave-Q config flip: semantic intent router OFF (config-only, owner-applied)

Owner-applied **config-only** prod change — CC cannot touch `.env*`. In `.env.prod`,
`SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER` was flipped **`true → false`** and the backend container
recreated. **No image change** — digest unchanged
`ghcr.io/jungt72/sealai-backend:ab586f30-20260606-113347@sha256:22f2f267a47ae91f09c52220948c7f3c0bc49e311ba19b0bdfeb7551ad00305b`,
`running healthy`, `APP_ENV=production`. Not a release-script deploy: no `ops/release-backend.sh`
run, no new pinned digest, no GHCR push.

**Rationale (Wave-Q §6/§7, `docs/audit/v18_waveQ_live_diagnosis.md`):** §6.4 verdict — router-OFF
is the smallest config delta that is route-correct, extraction-correct, zero-regression, and
cheapest. The nano semantic *refine* router was demoting legitimate case intent
`DOMAIN_INQUIRY → KNOWLEDGE_QUERY` on multi-word case inquiries (C2/C5/C6/**C12** — the live
salzsäure misroute: a governed salzsäure case answered with a generic "Werkstoffvergleich PTFE vs
POM" + a medium re-ask). Disabling the refine layer restores the correct deterministic label.
Extraction stays `gpt-4o-mini` (the §4 bump is unjustified, §6.2). §7 anaphora/context-bridge gate
(AN1–AN4) = **PASS**: the refine layer's only *functional* consumer is the pre-gate label; anaphora
resolution is router-independent (`KnowledgeContextBuilder` + the governed event store); router-ON
never improved on deterministic and harmed case continuity in 2/6 scenarios.

**Backup:** owner created `.env.prod.bak-20260607-1905` before the edit. Rollback = restore that file
+ recreate backend (same image digest, no GHCR pull).

**Live env confirmed (`docker exec backend env`):** `SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=false`.

**Post-flip verification (read-only, in-container, LLM-free — `docker exec -i -w /app backend python`,
19:28Z):** re-ran the C1–C13 pre-gate corpus against the live env (no in-process flag override; with
the flag false, `refine_pre_gate_classification` short-circuits to `_unchanged(deterministic)` with
**no LLM call**, so the effective label == the deterministic label on every turn). LangSmith disabled
in-process; pure route functions only; no state/persistence/config touched. **Result: ALL PASS.**

| group | turns | result |
|---|---|---|
| router off-confirmed | C1–C13 | `applied=False` every turn (`reason=not_a_semantic_router_candidate`) ✓ |
| case-intent restored | C2, C5, C6, **C12** | `DOMAIN_INQUIRY` ✓ (the live salzsäure misroute fixed) |
| no arm4-style demotion | C3, C7 | `DOMAIN_INQUIRY` ✓ |
| guards unchanged | C1/C13 · C9/C10 · C11 | `GREETING` · `KNOWLEDGE_QUERY` · `DOMAIN_INQUIRY` ✓ |
| flip-eligibility probe (LLM-free) | candidate-when-ON | `True` for exactly the six DOMAIN turns (C2/C3/C5/C6/C7/C12) — so OFF is what now protects them; `False` for C1/C4/C8/C9/C10/C11/C13 |

**End-to-end acceptance (programmatic, 2026-06-08): PASS.** The verbatim Session-B salzsäure turn
("lass uns bitte meine dichtung besprechen. was für ein material ist für salzsäure optimal") was run
function-level through the real route + governed composer, in-container against the live env
(`SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=false`), LangSmith off, ephemeral `InMemorySaver` checkpointer —
**no live-state load, no post-graph persist, no prod case written** (one real composer call). Result:
route **GOVERNED** · effective label **DOMAIN_INQUIRY** (`route_view=governed_domain_inquiry`,
`intent=new_rfq`; `semantic_pre_gate_trace=null` — the refine layer did not fire) · ChatReply from the
real `governed_composer`: *"Die technische Richtung ist schon enger, jetzt brauche ich noch genau einen
belastbaren Hebel. Um welchen Dichtungstyp oder welches Dichtprinzip geht es?"* (`pending_question.target_field=sealing_type`).
It is a governed case-intake next-question — **not** the generic "Werkstoffvergleich PTFE vs POM"
template — and it does **not** re-ask the medium: `medium="Salzsäure"` was extracted (single-medium;
source=llm, conf 0.6). The live C12 misroute is confirmed fixed end-to-end. Full closure summary +
known-gaps mirror in `docs/audit/v18_waveQ_live_diagnosis.md` §8. **Human browser-UI confirmation
remains the owner's** (this is its programmatic equivalent; the literal click is not automatable from CC).

**Pre-existing, flag-independent observation (out-of-scope, not a regression):** C4 ("das Medium ist
Salzwasser") and C8 ("Hydrauliköl HLP 46") carry a *history-blind* deterministic `KNOWLEDGE_QUERY`
label. This is unchanged by the flip — the router can only fire on a `DOMAIN_INQUIRY` det label, so
these were `applied=False` before the flip too (probe: candidate `False` even with the flag forced
ON). In the live flow these are pending-slot answers routed by the active-case / slot-binder path
(§6.2 "regex covers C5/C6/C8"), not the bare pre-gate label. Noted for a future look at the
deterministic classifier's history-blind labeling; not in scope here.

**W5 dead-config removal (this PR, §1.2):** `GENERATION_MODEL` / `GENERATION_TEMP` /
`GENERATION_MAX_TOKENS` have **no Python consumer** (`grep` → 0 hits) yet still appear in the running
container because they were **hardcoded** in `docker-compose.deploy.yml:57-59` (not in `.env.prod`).
Removed here; the change is **inert until the next regular deploy** recreates the container (no
urgency — rides the next deploy). The running `ab586f30` container still shows them until then.

**Governance:** PR → `demo/rwdr-limited-external` per workflow.md (no `main`). Docs + dead-config only
— no guard/lexicon/streaming/mutation path touched → **no `doctrine-reviewer` trigger**. The fast
doctrine guard suite was confirmed green before commit (gate prerequisite). Evidence record committed
alongside: `docs/audit/v18_waveQ_live_diagnosis.md`.

---

## 2026-06-05T18:41Z — Latency-hardening deploy (audit §5 Stages A1 + B + C)

Deployed `demo/rwdr-limited-external` @ `e50c5407` to prod through the standard gates,
on explicit owner go after a gathered deploy-risk HALT. Three latency/efficiency
stages from `docs/audits/2026-06-05_product_quality_audit.md` §5, each its own
reviewed PR; Stage D (composer) deferred by the owner pending the post-deploy baseline.

- **Deployed digest:**
  `ghcr.io/jungt72/sealai-backend:e50c5407-20260605-183643@sha256:18275f1197e7cf24d5c99c287ef41a1cdfa31b04a810dc36f34ec47a13bd1b44`
- **Rollback target (prior live, read from the running daemon, never memory):**
  `ghcr.io/jungt72/sealai-backend:417510cc-20260605-164136@sha256:34464e5b851e8254ce0a6d88b873a997c4cb7efe633ce7c819ce306dd43fc65e`
- **Pre-deploy gate (fresh, on `e50c5407`):** full backend suite `pytest backend -q -rf`
  **EXIT=0**; sentinels `pytest-green` + `anchor-verified` rewritten 18:30 (<1h).
  The MANDATORY stale-evidence regression `test_cache_invalidates_on_query_mutation`
  (`backend/app/agent/tests/graph/test_evidence_cache.py`) is collected by the gate
  (4 tests from that file) and green.
- **Diff inventory `417510cc..e50c5407`:** A1 (PR #102, observability — first_progress/
  latency + RAG tier timings + Tier-0 alert to structlog), B (PR #103, prewarm +
  semantic-router `asyncio.wait_for` 10s), C (PR #104, evidence re-retrieval cache),
  plus the §7 GOVERNANCE_LOG doc (PR #101). **Only runtime delta = those 9 files**;
  L1/L2 output guards, `turn_tier.py`, Guard-Repair, comparative-ranking lexicon all
  **unchanged**. A1 + C carry `doctrine-reviewer` APPROVE; B touches no doctrine path.
- Health `healthy` (redis / qdrant / agent_runtime); nginx reloaded; **live pilot smoke
  all PASS (15/15)**; auto-rollback not triggered.
- **In-container verification (deployed image, no user traffic):** A/B/C code markers
  present; **Stage B prewarm fired + completed at startup** (`RAG prewarm
  (embeddings/sparse/reranker/bm25) completed`) — default-on (`warmup_on_start=True`),
  no env change needed; Stage C cache key stable for an unchanged query and changes on
  mutation (`EvidenceState.query_hash` present); live config `semantic_router_timeout_s=10.0`.
- **Env:** no operator change required — prewarm default-on; `SEALAI_TIER0_RETRIEVAL_GUARD`
  unset = enforced (§7 guard intact across this delta).
- **Authoritative perf before/after (p50/p95 per route, incl. first_progress/C8): PENDING.**
  Per owner rule, the in-container `scripts/perf/measure_turn_timing.py` counts only as a
  first indicator; the authoritative table is built from real owner-driven frontend turns
  (5 governed + 5 knowledge), evaluated read-only against LangSmith `sealai-production` vs.
  the audit baseline. This entry will be amended with that table. Target budgets:
  governed `engineering_case_update` p50 <10s (baseline ~20s), smalltalk/side-questions
  <2s (baseline 5.4/7.9s — Stage C cache win), first_progress <1s server-side.
- **No `main`:** the `demo→main` convergence is the owner-gated per-milestone step, not
  performed here. Branch protection unchanged.

---

## 2026-06-05T16:44Z — HEAD deploy closing the §7 Tier-0-retrieval-guard pre-pilot blocker

Deployed `demo/rwdr-limited-external` @ `417510cc` to prod through the standard gates to
close the **§7 Pre-Pilot-Blocker** documented in
`docs/audits/2026-06-05_product_quality_audit.md` (the running image `ccdd4577` carried only
1 of 3 Tier-0 enforcement points; the cascade-close and dispatch re-raise lived on HEAD,
not in the image). Released on explicit owner go after a HALT with the deploy-risk summary.

- **Deployed digest:**
  `ghcr.io/jungt72/sealai-backend:417510cc-20260605-164136@sha256:34464e5b851e8254ce0a6d88b873a997c4cb7efe633ce7c819ce306dd43fc65e`
- **Rollback target (prior live, read from the running daemon, never memory):**
  `ghcr.io/jungt72/sealai-backend:ccdd4577-20260605-060228@sha256:045c2c2fc4583b1a13890437cd16006e72409ff4d1acf4313a781172adc4a933`
  (`running healthy` at read time).
- **Pre-deploy gate (fresh, on exactly this stand):** full backend suite
  `pytest backend -q -rf` **EXIT=0**; sentinels `pytest-green` + `anchor-verified` rewritten
  (16:36, <1h at deploy).
- **Diff inventory `ccdd4577..HEAD` (what shipped):** the **only runtime-code delta** is the
  two already-approved Tier-0 guard fixes — `real_rag.py` (+20, cascade-close B1/B2, **PR #91**
  `538302ea`) and `dispatch.py` (+7, knowledge re-raise, **PR #96** `972db6df`). Everything else
  is test/CI/docs: enforcer-reach (#94), reducers scanner (#98), CI contracts gate (#90),
  client-secret untrack + secret-scan (#95), governance/docs (#92, #87, #100). L1
  `output_guard.py` and L2 `final_guard.py` **unchanged** in the range.
- **Env (§7d):** `SEALAI_TIER0_RETRIEVAL_GUARD` **unset** in the running container → code-default
  *enforced* (`turn_tier.py:60` `or "1"`); **not** pinned to an off-value. No flag change made.
- Health `healthy` (redis / qdrant / agent_runtime); nginx reloaded; **standard live pilot
  smoke all PASS** (15/15).
- **Negative smoke (new, mandatory — in-container `docker exec`, no user traffic, no routing-bug
  simulation):** Tier-0 declared in the contextvar →
  (A) `retrieve_with_tenant` raises `TierViolation` at cascade entry → cascade-close **live**;
  (B) `_knowledge_rag_retriever` **re-raises** the `TierViolation` instead of degrading to `[]`
  → dispatch re-raise **live**;
  (C) undeclared tier → guard is a no-op → **no over-block** (AC8). Result **ALL_PASS** — all
  three Tier-0 enforcement points now live.
- **§7 Audit 2026-06-05 geschlossen.**
- **No `main`:** the `demo→main` convergence is the owner-gated per-milestone step and was **not**
  performed here. Branch protection unchanged.

---

## 2026-06-05T13:26Z — CI now runs the executable contracts + demo branch protection (Audit #3 fix)

Acting on the V1.7 deep-dive Audit #3 (`docs/audits/2026-06-05_v17_full_audit.md`, Risk #2
"CI doesn't run the enforcers" + the demo-unprotected finding).

- **CI contracts gate (new):** `.github/workflows/backend-contracts.yml` job **`backend-contracts`**
  now runs the architecture enforcers (`backend/tests/architecture` — seal-type, single-writer,
  SSOT) and the fast doctrine guard suite on every push + PR (merged **PR #90**,
  demo `d7f1a2cf`). Deliberately dependency-light (enforcers are pure-AST via `--noconftest`;
  doctrine targets import only pydantic). Acceptance: a planted `seal_type == "rwdr"` core branch
  turns the job red. The governed-seam / full-stack tests stay out of this fast gate (they need
  the full runtime stack) — deferred to a future image-based job.
- **demo branch protection (was UNPROTECTED, 404):** `demo/rwdr-limited-external` now requires
  status checks **`agent-bff-guardrails` + `backend-contracts`** (`strict:false`,
  `enforce_admins:false`, 0 required reviews — mirrors main's posture). Set via `gh api`.
- **main required-check update PENDING:** `backend-contracts` will be added to `main`'s required
  checks as part of the owner-gated `demo→main` carry (the workflow must land on main first; main
  currently requires only `agent-bff-guardrails`).
- **Discrepancy surfaced (not actioned):** the audit's Scope-C "Branches" row claims 23 remote /
  9 merged-deletable; live state is **96 remote branches, 40+ merged (`ahead:0` vs origin/main)**.
  Bulk remote-branch deletion is deferred to explicit owner confirmation given the contradiction.

---

## 2026-06-05T06:03Z — C10 echo prod deploy + Parked-Items-Closeout COMPLETE

C10 manufacturer-response echo deployed to prod through the standard gates (the HALT in the
05:42Z entry, released on explicit owner go). Pre-deploy gate **re-run** on the deploy
candidate `demo@ccdd4577` (`pytest backend` **EXIT=0**; sentinels not recycled — refreshed);
rollback anchor read from the running daemon, never memory. Deploy via
`ops/release-backend.sh` (build → GHCR push → pin `@sha256` in `.env.prod` → recreate backend
→ health + auto-rollback → nginx reload → live smoke).

- **Deployed digest:**
  `ghcr.io/jungt72/sealai-backend:ccdd4577-20260605-060228@sha256:045c2c2fc4583b1a13890437cd16006e72409ff4d1acf4313a781172adc4a933`
- **Rollback target (prior live, from the daemon):**
  `ghcr.io/jungt72/sealai-backend:2d325acf-20260604-181319@sha256:6d3c38266ccf116a9632b0e7f86974a53fd1b84ca7dc885fee923106fdb64877`
- Health `healthy` (redis / qdrant / agent_runtime); nginx reloaded; **live pilot smoke all
  PASS**; the echo wiring (`manufacturer_echo_notes`) is confirmed present in the running image.
- **Convergence:** `demo→main` carry **PR #86** merged as a merge-commit (`79f3ab66`; no squash;
  demo branch intact) → **main ⊇ demo**. Deploy/Build-Push workflows **did not run** on the main
  push (prod is digest-pinned; deployment happened via `ops/release-backend.sh`). Branch
  protection unchanged.

**Parked-Items-Closeout abgeschlossen 2026-06-05.** Open only:
(i) Keycloak service-account wiring for the admin scripts [documented, undated];
(ii) S5-Mode-Konsolidierung [LOW, deliberate];
(iii) item (d) `.env` `KEYCLOAK_ADMIN_PASSWORD` placeholder [owner-manual, instructions in the runbook].

---

## 2026-06-05T05:42Z — Parked-Items-Closeout (Keycloak cleanup, C10 echo wired, branch strategy decided)

Closeout session taking every parked item to a documented terminal state. Three owner
decisions: **C10 echo → wire**; **branch strategy → keep + codify**;
**`registrationAllowed` → false**. No undocumented open item remains; the one
deliberately-open item (d) is recorded with its reason.

**Phase 1 — Keycloak cleanup (live realm, owner-gated, lockout-safe order).** Owner logged
in interactively (recovery admin `test`); CC ran only read/cleanup `kcadm` against the
cached token — no secrets in the transcript. Read-only status **contradicted runbook item
(b)**: the master-realm `jungt` (`9f0906ab…`) was **not** a credential-less crashed-run row
— it had a valid password + non-admin roles. Surfaced (**HALT, not silent action**); owner
decided to delete it as accidental master-realm clutter. Order honored — **rotation before
recovery-user deletion**: the real admin is **`superadmin`** (there is no `admin` user);
owner rotated `superadmin`'s password (console, Temporary=OFF) + verified login, **then**
the recovery admin `test` (`bae9fa04…`) was deleted. `registrationAllowed=false` on the live
`sealAI` realm (B2B — self-registration only yields locked-out 401 users); realm backed up
first → `~/keycloak-backups/20260605T051149Z/sealAI-realm-export.json`, and both seed exports
updated (`keycloak/realm-export.json`, `keycloak/import/realm-export.json`). **Master-realm
end state verified: only `superadmin`; sealAI `jungt` (`7748ba15…`) untouched.** Closeout
recorded in `docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md`.
**Item (d) — DELIBERATELY OPEN (owner action; CC does not touch `.env*`):** remove the stale
`KEYCLOAK_ADMIN_PASSWORD` from `.env*`, keep exactly one authoritative store (password
manager). The app needs no master-admin password at runtime (bootstrap relic).

**Phase 2 — C10 manufacturer-response echo: WIRED** (PR #84 → demo, merge `9615dd52`). The
intake was live but the projection `manufacturer_response_echo_notes()` had no caller. Wired
the last hop at the single funnel `RWDRCaseOrchestrator.build()`: recorded responses (raw
envelopes) now surface as `rag_supported` notes on
`TechnicalRWDRRFQBrief.manufacturer_echo_notes` + a conditional brief section — never a
confirmed fact, guard-scrubbed to the neutral fallback. **Red-before-green** (2 wiring tests
red→green + 1 invariant guard). **doctrine-reviewer: APPROVE** (four comparative-ranking
repros still block at L1; AC8 no-over-block + AC9; no guard/lexicon/streaming/mutation
touched; purely additive, backend-only). CI green (`agent-bff-guardrails`, `backend
ruff-format`).
**Prod deploy: HELD at 🛑 HALT (owner-gated).** Pre-deploy gate `pytest backend` **EXIT=0**;
sentinels staged (`pytest-green`, `anchor-verified`); rollback anchor read from the running
daemon: `ghcr.io/jungt72/sealai-backend:2d325acf-20260604-181319@sha256:6d3c3826…`
(status=running health=healthy). No `release-backend.sh` run by CC.

**Phase 3 — Branch strategy: DECIDED (was parked).** Keep the demo-integration model and
codify it in `.claude/rules/ops.md`: all PRs target `demo/rwdr-limited-external`; `demo→main`
convergence is owner-gated, per milestone/day, with a carry-over PR per demo merge; matches
existing branch-guard/hooks/CI (no infra change). Trunk-based not adopted; the CI-trigger /
`ruff format` scope questions remain **separately parked**.

**Phase 4 — Ledger:** this entry + the journal (`docs/runtime-audit-fixmap.md`). Docs
(Phases 1 + 3 + 4) ship in one closeout PR → demo; each demo merge gets its `demo→main`
carry-over PR (owner-gated).

---

## 2026-06-04T20:05Z — Legacy cleanup: remove red double-CI + delete dead dirs (NO prod deploy)

Two owner-decided cleanups; no prod deploy; branch protection unchanged; demo→main convergence
held (each via PR → demo → small demo→main carry-over).

**TEIL 1 — removed the legacy `.github/workflows/ci.yml`** (PR #79 → demo, #80 → main). It was a
Sprint-9-origin, **main/master-only** workflow whose `Lint (ruff)` job ran whole-repo
`ruff format --check .` + `ruff check .` and was permanently red on the legacy debt → error mails
on every main push (alarm-deafness); its pytest/docker jobs only ever skipped (`needs: [lint]`).
Canonical CI is now `agent-bff-guardrails` (the required check) + the `backend-ruff-format`
re-debt guard; backend pytest is the local pre-deploy gate, docker build runs in the release
scripts. Lint was never a required check, so branch protection is unchanged. **No more red `CI` runs.**

**TEIL 2 — deleted dead legacy dirs** (PR #81 → demo, carry-over → main; pure deletions, 225 files):
`archive/` (21M, archived legacy frontend `legacy_phase2`) and `langgraph_backup/` (756K, backup
of the removed langgraph). **`seo/` KEPT** (recent `sealai_seo` tool with a systemd service — not
dead legacy). Safety-checked read-only first: **nothing imports either dir**; both recoverable from
git history; the `NON_CANONICAL_TREES` SSoT guardrail test stays green (doc-string check) and the
`check-secret-hygiene` allowlist entry is left vestigial-but-harmless (pure-deletion PR).

**Backlog closed:** the parked "legacy ruff cleanup" follow-up (noted in the 19:05 convergence
entry) is **resolved** — `archive/` + `langgraph_backup/` are gone; the only remaining whole-repo
`ruff format` non-conformance is `seo/`, which is kept as an active standalone tool and is outside
the `backend-ruff-format` guard's scope. Backend is ruff-format-clean and guarded; no further
legacy ruff work pending.

---

## 2026-06-04T19:05Z — demo→main convergence + v1.7.0 release tag (NO prod deploy)

Converged `demo/rwdr-limited-external` → `main` via PR #11 as a **merge-commit** (`bffa2188`;
no squash — the full ~677-commit governance trail is preserved). Production **untouched**
(digest-pinned; the main push's Deploy/Build-Push workflows **skipped**; no `release-*.sh` run).
No force-push, no history rewrite, no branch deletion — demo stays the active integration branch.

**STEP 0 (read-only):** main was **not** an ancestor of demo — main carried **6 unique
CI/CD-stabilization commits** (2026-04-23/24: `e406c705 430ecbf0 56bd8c89 9acf753e 5331a9d9
d846582f`); demo was **+677** ahead. Merge dry-run: the **only** conflicts were 4 CI/ops files —
**zero product-code conflicts**. Merge-base `042810ef`.

**Resolution (owner decision: demo-CI canonical):** merged `origin/main` into demo (`349e10ce`)
resolving the 4 conflicts (+ `ci.yml` / `check_no_langgraph_v1.sh`) to **demo's versions** — the
merged tree is **byte-identical to demo HEAD** (zero tree change; main's April CI content
superseded but preserved as a merge parent). Then PR #11 (demo→main) merged conflict-free.

**CI on main:** `agent-bff-guardrails` **green** (×2). The repo-wide `ruff format --check`
(`Lint (ruff)`, **716 files** — all of `backend/` + `seo/archive/langgraph_backup/...`) is **red**
but **pre-existing / repo-wide / not a V1.7 regression** and never gated demo PRs; accepted as an
out-of-scope follow-up (owner decision). pytest/docker jobs skipped by `ci.yml` conditions.

**Tag + release:** annotated **`v1.7.0`** on `bffa2188` + GitHub release. Verdikt: **V1.7 erreicht
— ja-mit-Amendments** (`docs/audits/2026-06-04_v17_gap_audit_rerun.md`).

**Branch protection on `main` (gh api, set):** PRs required (`required_approving_review_count: 0`);
**`agent-bff-guardrails`** as the **required** status check (the ruff debt deliberately NOT
required); force-pushes + deletions blocked; `enforce_admins: false`.

**Verification:** `git merge-base --is-ancestor 349e10ce origin/main` = true (main ⊇ demo); the
key V1.7 files (enforcer tests, `oring_calc.py`, GOVERNANCE_LOG, both audits, CORE_PACK_BOUNDARY)
exist on main.

---

## 2026-06-04T18:37Z — Frontend Brand/UI-Refresh prod deploy

Frontend-only release of the Codex-authored brand/chat-UI refresh (owner-approved; PR #72 on
`demo/rwdr-limited-external`, checked in verbatim). Not a doctrine/governance change — logged
per the **owner's standing rule (2026-06-04): every prod deploy is recorded here, no exceptions**
(backend, frontend, doctrine or brand).

**Scope:** new PNG logos + `SealAiBrand` (inline SVG → `next/image`); `DashboardShell`
header/sidebar restyle + user-identity card; `ChatComposer` pill/glass restyle; `ChatPane`
empty-start simplified (starter prompts + client-side JWT name greeting removed). 9 files, no
secrets / `.env` / build artifacts.

**Quality gate:** `next build` EXIT=0; `vitest` 198/199 — the only red, `workspaceMapping.test.tsx`,
**proven pre-existing** (fails on the clean tree with the changes stashed); `test:node` 35/35.

**Deploy (`ops/release-frontend.sh`, EXIT=0):** new pinned image
`ghcr.io/jungt72/sealai-frontend:d40d7145-20260604-183558@sha256:fdb5ced64153aee727b1b2eb7ad8d7fda0dec398c5b8d225cfabfb3ff7cc19d6`.
Frontend healthy (`/api/health` → `ok`); nginx reloaded; **live pilot smoke 14/14 PASS**. Rollback
target `…sealai-frontend:7eb3d9f4-20260604-174637@sha256:59e433fd58dba0baf9d9d3179780bc6d7d2fde113f440e2ccae3ab4a66ebc723`
via `.env.prod.rollback-20260604-183558` (read from the running daemon, not memory). Owner does the
visual acceptance check on https://sealingai.com.

---

## 2026-06-04T18:14Z — P1-4 prod deploy (C1/C9/S3 + enforcers)

Follow-up deploy to the demo-merge entry below. HALT-before-prod honoured: the four-part risk
summary presented (behaviour-neutral; all freezes byte-identical; both enforcers synthetic-proven;
L1/L2 + Tier-0 untouched; four comparative-ranking repros still block; two `doctrine-reviewer`
APPROVEs) + explicit operator **go**.

**Pre-deploy gate:** full backend suite `EXIT=0` re-run on the exact deployed commit `2d325acf`
→ fresh `pytest-green`; rollback anchor `…@sha256:05953eda…` (running/healthy from
`docker inspect backend`, never memory) → fresh `anchor-verified`. Confirmed PR6's docs-only merge
did **not** revert PR5b (3-way merge took demo's PR5b versions; `produce_*` + both enforcers
present on HEAD).

**Deploy (`ops/release-backend.sh`, RELEASE-EXIT=0):** new pinned image
`ghcr.io/jungt72/sealai-backend:2d325acf-20260604-181319@sha256:6d3c38266ccf116a9632b0e7f86974a53fd1b84ca7dc885fee923106fdb64877`.
Backend healthy (redis/qdrant collections=2/agent_runtime); nginx reloaded; **live pilot smoke
14/14 PASS**. Rollback target `…@sha256:05953eda…` via `.env.prod.rollback-20260604-181319`.

**Scoped re-verification on the deployed image (`docker exec backend`):**
- **C1 → ERFÜLLT** — seam selectors live in `seal_packs.py`; **zero** `== "rwdr"`/`!= "rwdr"`
  control-flow in the routed core (`reducers`/`challenge_engine`/`case_workspace`/`checks_registry`/
  `calculation_projection`).
- **C9 → closed** — `app/agent/domain/oring_calc.py` present; orchestrator core has **0**
  `_oring_calculations`.
- **S3 → ERFÜLLT** — 3 `produce_*` single-writer helpers live; **zero** governed-layer
  `model_copy` bypass in the routed sites.
- **C10 → ERFÜLLT (deferred, unchanged)** — `manufacturer_response_echo_notes` still caller-less,
  by design.

Re-Run-Doc verdict updated **nein → ja-mit-Amendments**. No guard/lexicon/doctrine test weakened;
no gate bypassed.

---

## 2026-06-04T17:57Z — P1-4 C1/C9/S3 closure + architecture enforcers (demo-merged; HALT-before-prod)

Closes the V1.7 re-run audit's open verdicts (`docs/audits/2026-06-04_v17_gap_audit_rerun.md`):
**C1 TEILWEISE/HIGH → ERFÜLLT**, **C9 LOW-Vorbehalt → closed**, **S3 TEILWEISE → ERFÜLLT**.
Eight small PRs to `demo/rwdr-limited-external`, P1-1 discipline (characterization-freeze
committed before each refactor, zero behaviour change):

- **C1** — routed the three audited core surfaces (`reducers.py` PR1, `challenge_engine.py` PR2,
  `case_workspace.py` PR3) **plus** the decision-A extras the inventory surfaced
  (`checks_registry.py` / `output_contract_assembly.py` / `calculation_projection.py`, PR3.5)
  through the pack seam. The calc_type sites use the new exact `pack_for_calc_type` (a dotted
  `rwdr.<id>` divergence vs `pack_for_calc_id` was red-proven and avoided).
- **C9** — relocated `_oring_calculations` out of the v92 core orchestrator into
  `app/agent/domain/oring_calc.py` (PR4; no `OringPack`).
- **S3** — routed all governed-layer `model_copy` content-syncs (`api/utils.py`,
  `output_contract_assembly.py`, `persistence.py`, `sheet_events.py`) through
  `reducers.produce_governance/produce_decision/produce_normalized` (PR5b).
- **Enforcers (the actual goal)** — `test_core_seal_type_branching.py` (no seal-type branching in
  the core outside a documented allowlist = the heterogeneous `risk_readiness` checks + the
  `normalize_seal_type` classifier) and `test_single_writer_invariant.py` (governed-layer state
  produced only by the reducer chain). Both carry synthetic-violation proofs; CI-effective (PR5a/PR5b).

**Reviews:** `doctrine-reviewer` APPROVE on PR1 (mutation core) and on PR5b (after one
REQUEST-CHANGES round that caught a bare-variable `normalized.model_copy` single-writer gap at
`sheet_events.py:190`, now closed). Boundary doc corrected (the earlier P1-3 "resolved" over-claim);
prior-audit S1/S2 matrix rows reconciled TEILWEISE → ERFÜLLT (stale; detail P1-2 already ERFÜLLT).

**Adjacent owner decisions:**
- **C10** (manufacturer-feedback echo) — **deferred** (not wired). `manufacturer_response_echo_notes`
  is implemented + tested but caller-less; wiring deferred to the Knowledge contract seam
  (`dashboard_contract._knowledge_notes`). AC10 ("als Wissensquelle vorgesehen") stays ERFÜLLT.
- **V1.7 §6.4 off-branch caveat** — `origin/feat/v1.7-blueprint` §6.4 still lists
  `CaseUnderstandingPatch + RFQBriefPatch`; off-branch + non-binding (AGENTS.md: V1.6/RWDR-MVP is
  binding). Noted, unrekonziliert by design.

**Pending:** 🛑 HALT-before-prod — the bundled prod release (full backend pytest exit=0 + fresh
daemon rollback anchor + enforcer proof) and the scoped C1/C9/S3/C10 re-verification → Re-Run
verdict update to "ja-mit-Amendments" are recorded in a follow-up entry at deploy.

---

## 2026-06-04T14:43Z — P2-1 Knowledge-Marker (C5) + Herstellerfeedback (C10) — Sammel-Release

Closes the last two open gap-audit items (`docs/audits/2026-06-03_v17_gap_audit.md`):
**C5 TEILWEISE → ERFÜLLT** and **C10 FEHLT → ERFÜLLT**. Two demo PRs + one fix,
then one combined prod release; HALT-before-prod honoured with the four-deliverable
risk summary and explicit operator go.

**Demo merges (each: full suite EXIT=0 + fast-doctrine green + CI `agent-bff-guardrails` pass):**
- **TEIL B (#59, C10) — doctrine/mutation path:** `manufacturer_response` intake
  (`POST /rfq/rwdr/cases/{id}/manufacturer-feedback`, tenant-scoped, open-point
  candidate under a namespaced key) + guarded `rag_supported` echo + brief-gate
  backstop (`_NEVER_BRIEF_SOURCE_TYPES` short-circuit in `_blocked_reason` **before**
  the origin branches — `_BLOCKING_SOURCE_TYPES` alone leaked via `user_entered`
  origin laundering). **doctrine-reviewer APPROVE**: full 5×5 laundering matrix → 0
  leaks; red-before-green load-bearing; four L1 comparative-ranking repros still
  block (`output_guard.py`/`final_guard.py` untouched); AC8 no over-block; AC9 echo
  is a pure read; zero-FP (no existing fact carries the source_type).
- **TEIL A (#60, C5) — additive, non-doctrine:** `ChunkMetadata.pack_affinity`
  (None=cross-cutting, "rwdr"=pack) + `classify_pack_affinity()` (single SoT
  ingest+backfill); ingest sets it; **retrieval-inert** (not in
  `_SUPPORTED_METADATA_FILTER_KEYS`; payloads read as raw dicts). Backfill script
  (dry-run-default, idempotent, conserved accounting).
- **#61 fix:** backfill default collection → `sealai_knowledge_v3` (live corpus).

**Prod deploy (`ops/release-backend.sh`, RELEASE-EXIT=0):**
- Pre-deploy gate: full backend suite `EXIT=0` → fresh `pytest-green`; rollback
  anchor `…@sha256:afb82cfb…` (running/healthy from `docker inspect backend`, never
  memory) → fresh `anchor-verified`.
- New pinned image
  `ghcr.io/jungt72/sealai-backend:3627b2f7-20260604-144259@sha256:05953eda7885130b8a5cd97021a46742ff497aefe6b4a51480e5349a0d470362`
  (built from demo `3627b2f7`). Backend healthy (redis/qdrant/agent_runtime,
  qdrant collections=2); nginx reloaded; **live pilot smoke 14/14 PASS**. Rollback
  target `…@sha256:afb82cfb…` via `.env.prod.rollback-20260604-144259`.

**Post-deploy backfill + characterization (operator sequence):**
- Backfill `sealai_knowledge_v3` (script `docker cp`-ed in — the image does not ship
  `scripts/`): dry-run = `--apply` accounting **total 83 = 0 already + 7 rwdr + 76
  cross-cutting** (conserved); applied 83 writes, `post_check_missing_marker=0`;
  2nd dry-run `writes=0` (idempotent).
- **Retrieval characterization: identical hit-sets before/after across 5 queries
  (0 result-diff)** — the marker is inert, exactly as designed. Temp script +
  baseline removed from the prod container afterward.

Gap-audit **C5 + C10 → ERFÜLLT**; the P2-1 (last) patch-order item is closed. No
guard/lexicon/doctrine test weakened; no gate bypassed.

---

## 2026-06-04T13:04Z — P1-3 residual rwdr risk branches (closes C1 residual)

Behaviour-neutral follow-up to P1-1 PR3's surfaced residual (`risk_readiness.py`).
Same P1-1 discipline: STEP-0 map → characterization freeze committed before the
refactor → small commits.
- `:527` runout_risk + `:555` surface_risk (clean `== "rwdr"`) → `pack_for_engineering_path`.
- `:499` speed_pv_risk (`{rwdr, ms_pump, unclear_rotary}` — heterogeneous, no 1:1 pack
  equivalence) → **HALT → owner chose: keep as a documented CORE check** (honest core
  check > contorted abstraction). PR #56.
- Proof: characterization freeze green before+after (incl. the `:499` neutrality pin
  that ms_pump/unclear_rotary still emit the risk); full backend suite EXIT=0;
  **doctrine-reviewer APPROVE** (`pack_for_engineering_path(x) ⇔ x=="rwdr"`, 1:1).
- Deploy `…@sha256:afb82cfb…` (operator-approved HALT); live spot-check confirms
  rwdr runout/surface via pack, `:499` set intact for all three paths, tier-0 guard
  still enforced. Gap-audit **C1 → ERFÜLLT** (residual closed).

---

## 2026-06-04T12:41Z — P1-2 Trace/Tier (S1/S2) + prod-deploy chain since P0-2

Prod-deploy continuity since the P0-2 entry (each via `ops/release-backend.sh`,
full-suite `EXIT=0` + fresh `pytest-green`/`anchor-verified` sentinels + live
pilot smoke; HALT-before-prod honoured with explicit operator go each time):
- **P0-3** (pocket `rfq_status` single-source + envelope-stub removal) →
  `…@sha256:6916d557…` + frontend `…@sha256:f27f9b5e…`.
- **P1-1** (Core/Pack boundary — DomainPack protocol, RWDR-only; behaviour-neutral)
  → `…@sha256:d5ff7e08…`.
- **P1-2** (this entry) → `ghcr.io/jungt72/sealai-backend:d582544d-20260604-124056@sha256:808e5cae…`.

**P1-2 — Gap-audit S1 + S2, two PRs, different blast radius:**
- **TEIL A (#53, obs):** one central streaming timing source fills
  `first_progress_ms`/`latency_ms` for all TurnRoutes (`turn_timing.py` contextvar
  timer; `SSEEventBuilder.event()` stamps the final `state_update`). Mobile trace
  byte-identical. Autonomous → demo.
- **TEIL B (#54, enforcement):** fail-closed Tier-0 retrieval guard — `turn_tier.py`
  (`TierViolation`, declared-tier contextvar, kill-switch `SEALAI_TIER0_RETRIEVAL_GUARD`
  default ON / incident-only / logged) + **one** `enforce_retrieval_allowed()` at the
  `hybrid_retrieve` funnel; tier declared in `dispatch.py` from the pre-gate
  classification. Tier-0 = {GREETING, META_QUESTION, BLOCKED} (operator decision,
  strict-safe). Red-before-green + **false-trip proof** (scenario matrix S1-S10 +
  golden + dispatch + full suite + live smoke → 0 TierViolation on legitimate
  paths). **doctrine-reviewer APPROVE.**
- Live acceptance (deployed container): guard default-ON, Tier-0 → `TierViolation`,
  Tier-1 → allowed; timer fills the timing fields.
- Reviewer note recorded: the broad `except` at the 3 call sites catches
  `TierViolation` → a wrongly-Tier-0 retrieval manifests as a logged failure + no
  cards (fail-safe, not a 500). Kill-switch doc: `.claude/rules/ops.md`.

Gap-audit S1+S2 → ERFÜLLT; risk #5 closed. Residual rwdr branches
(`risk_readiness.py:498/:527/:555`) deliberately untouched (own later pass).

---

## 2026-06-04T09:00Z — P0-2 tenant-fallback removal: code + migration + prod deploy

Closes audit **C6** (`docs/audits/2026-06-03_v17_gap_audit.md`) together with P0-1.
Three gated steps, each evidence-backed; HARD HALTs honoured (operator-approved
migration scope and deploy).

- **(A) Code — demo PR #46.** New strict resolver
  `app.services.auth.dependencies.require_tenant_id` → missing/empty tenant claim is
  a hard 401, never `"default"`/`user_id`. Converted request-scoped sites
  `deps.py:23`, `rfq.py:42`, `memory.py:40` (LTM), `rag.py:57` (private RAG),
  `chat_history.py` ×4. Shared-tenant (`RAG_SHARED_TENANT_ID`, Paperless) paths
  untouched — invariant test. Red-before-green
  `backend/tests/unit/services/test_p0_2_strict_tenant_resolver.py` (8 red → green);
  affected + fast-doctrine suites green. No deploy on (A).
- **(B) Migration — prod DB.** `ops/migrations/p0_2_unify_tenant_to_sealai.sql`
  (idempotent, dry-run-default). pg_dump backup first
  (`~/sealai-db-backups/20260604T084655Z/sealai_p0_2_pre_migration.dump`, 40 MB).
  Dry-run + idempotency proof → HARD HALT → operator approved **real-data scope**.
  Applied: **374** cases (353 `default` + 21 real realm-user) + 1337/1337
  `mutation_events`/`outbox` `default` rows → `sealai`. Untouched: 21 test-label
  cases, `rag_documents` (7, shared-tenant), `audit_log` (9, append-only). Per-table
  totals conserved; 2nd pass = `UPDATE 0`.
- **(C) Deploy — prod backend.** Pre-deploy gate: full backend suite exit 0 →
  fresh `pytest-green`; rollback anchor `…@sha256:c0406be9…` running/healthy →
  fresh `anchor-verified`. `ops/release-backend.sh` RELEASE-EXIT=0. New pinned image
  `ghcr.io/jungt72/sealai-backend:f3a8aa20-20260604-090045@sha256:6916d557…`;
  backend healthy (redis/qdrant/agent_runtime); nginx reloaded; live pilot smoke
  passed. **Live acceptance:** in-container `present-claim → "sealai"`,
  `no-claim → 401 missing_tenant_claim`. Rollback target `…@sha256:c0406be9…` via
  `.env.prod.rollback-20260604-090045`.

**Onboarding consequence (logged, accepted):** the realm has
`registrationAllowed=true`, so a new/attribute-less user now gets 401 on
case/RFQ/RAG/memory/chat-history until an admin sets their `tenant_id`. The 6
existing realm users carry `tenant_id=sealai`. Runbook
`docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md` updated with the admin onboarding step.

---

## 2026-06-04T06:00Z — First production deploy through the active deploy gate (P0-1)

P0-1 (LTM tenant scoping) shipped to prod as the **first real release gated by the
active deploy-gate**. The gate passed on two FRESH sentinels, each produced by a
real gate step (never fabricated):
- `pytest-green` — full backend suite `.venv/bin/python -m pytest backend -q -rf`
  exit 0 (chained `&& touch`); 0 failures.
- `anchor-verified` — `docker inspect backend` digest matched the expected rollback
  anchor `…@sha256:d102da88…`, status running/healthy.

Release via `ops/release-backend.sh` (RELEASE-EXIT=0):
- **Rollback anchor (pre-deploy):**
  `ghcr.io/jungt72/sealai-backend:8431dda2-20260603-190217@sha256:d102da8820b9f4c66057d85573a11d55a1e99d2c3359176db4233708fca9f78e`
- **New live image (post-deploy, from daemon):**
  `ghcr.io/jungt72/sealai-backend:89d73ff3-20260604-055825@sha256:c0406be90c136bf73c6e4c746b9fedbe220e380cf922ee34331a79cd7d132127`
  (built from demo `89d73ff3`, which includes P0-1 `d072a892`), status running/healthy,
  started 2026-06-04T05:58:54Z.

Acceptance: `/health` healthy (redis/qdrant/agent_runtime); live pilot smoke 14/14
PASS; `GET /api/v1/memory/export` → 401 (auth boundary intact, no 500). `LTM_ENABLE`
unset live → endpoints early-return, so P0-1 is enforcement-neutral (zero behavior
change for current single-tenant logins), exactly as the pre-deploy HALT analysis
predicted.

The deploy-gate behaved correctly: it required both fresh sentinels and did not
wrongly block. No gate weakened or bypassed; no P0-2 code (awaits the manual
Keycloak `tenant_id` mapper — see `docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md`).

---

## 2026-06-04T05:48Z — Gate hardening F1/F2/F3 + four-quadrant re-verification

Both PreToolUse hooks now match on the executed command only
(`jq -er '.tool_input.command // empty'`), never the whole payload; the deploy
gate fires only on an actual **invocation** of the release script. **Fail-closed**:
jq missing / malformed payload / undeterminable command → BLOCK (validated). The
payload shape was verified live before the change (`.tool_input.command`), and the
new logic was validated out-of-band (16/16 synthetic cases) before an atomic swap,
so a parse bug could not lock the session out. **Session:**
`1b1be06d-dfd9-4cc6-895d-2ec7353181c6`. Branch `proof/gate-harden-reverify` removed;
worktree clean.

| Quadrant | Expectation | Result | Evidence |
|---|---|---|---|
| **FP1** | `git diff` with "git commit" in the **description**, suite RED | **now PASS (not blocked)** | command ran rc=0; no doctrine-gate log entry (gate short-circuited on command-only match) — contrast prior `05:14:24Z BLOCK` |
| **FP2** | real `git commit` whose **message** names `ops/release-backend.sh` | **now PASS (allowed)** | commit `68a3fcd1` succeeded rc=0 (deploy gate saw a mention, not an invocation) |
| **TP1** | real `git commit` with synthetic RED suite | **still BLOCK** | `05:46:32Z BLOCK — guard suite FAILED`; `DOCTRINE GATE (fail-closed): … FAILED` |
| **TP2** | real `bash ops/release-backend.sh` with no sentinel | **still BLOCK, no build** | `DEPLOY GATE (fail-closed): missing sentinel — full backend pytest exit 0` |

Out-of-band fail-closed proofs (all BLOCK): malformed payload, absent command
field, jq unavailable (stripped PATH) — for both hooks. Standard proofs re-run:
branch-guard (`git push origin HEAD:main` → permission denied), reviewer
(`doctrine-reviewer` toolset = Read, Bash only), ops.md ↔ `deploy-gate.sh`
freshness consistent (`<1h` / `MAX_AGE=3600`). No quadrant failed; no gate was
weakened (changes tighten matching and keep fail-closed).

Docs in the same change: `.claude/rules/ops.md` gains a command-parsing +
deliberate-residual-gaps note (`sh -c`/alias/variable constructs not caught — a
discipline anchor, not a sandbox) and the hot-reload activation reality;
`.claude/agents/doctrine-reviewer.md` gains the F3 read-only (Bash-by-convention)
line.

---

## 2026-06-04T05:26Z — Re-verification against the durable (merged) gates

**Governance aktiv ab 2026-06-04T05:07Z**, durable auf `demo` (activation commit
`645e9f62`, merged via PR #38). **Session:** `1b1be06d-dfd9-4cc6-895d-2ec7353181c6`.
Fresh, independent re-run of the six live gate proofs against the
already-committed/merged hooks (not the in-session hot-reload). Throwaway branch
`proof/governance-reverify`; all synthetic artifacts removed, worktree clean.

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Hooks registered (committed) & live | **PASS** | `git show HEAD:.claude/settings.json` carries the hooks block (`:94-105`); activation commit `645e9f62`; live PASS log entries through 05:25Z |
| 2 | Doctrine-gate RED → commit BLOCKED | **BLOCK ✓** | `05:25:29Z BLOCK — guard suite FAILED`; `DOCTRINE GATE (fail-closed): … FAILED`; `test_synthetic_doctrine_gate_reverify_DELETE_ME` failed; HEAD `e1abae9e` unchanged |
| 3 | Doctrine-gate GREEN → commit ALLOWED | **PASS** | `05:25:52Z PASS`; throwaway commit `d5f19b03` (`rc=0`) after probe removal |
| 4 | Branch-guard → push to `main` denied | **BLOCK ✓** | `git push origin HEAD:main --dry-run` → `Permission … denied` (pre-execution; no real push) |
| 5 | Deploy-gate → release w/o sentinel denied | **BLOCK ✓** | `bash ops/release-backend.sh --help` → `DEPLOY GATE (fail-closed): missing sentinel`; no build started |
| 6 | Reviewer cannot Write/Edit | **PASS** | `doctrine-reviewer` subagent toolset = Read, Bash only |
| 7 | ops.md sentinel docs consistent | **PASS** | `ops.md:12,18,26` ↔ `deploy-gate.sh:24` (`MAX_AGE=3600`) |

Outcome: identical to the first run — gates enforce idempotently from the durable
state. No proof failed. F1/F2 (payload over-match, see prior entry) remain open
and unchanged; no gate was weakened.

---

## 2026-06-04 — Governance activated and mechanically verified

**Governance aktiv ab 2026-06-04T05:07Z** (Hooks hot-reloaded in-session),
durable auf `demo/rwdr-limited-external` via **PR #38** (merge `64f4bcc2`).
**Session:** `1b1be06d-dfd9-4cc6-895d-2ec7353181c6`.

Activation: the reviewed `.claude/settings.json.proposed` was renamed onto the
active `.claude/settings.json`, registering the `PreToolUse → Bash` hooks
(`ops/hooks/doctrine-gate.sh`, `ops/hooks/deploy-gate.sh`) and the tightened
permissions (main-push denies, release-script `ask`-gate). The previously active
settings had **no `hooks` block** — the gates were authored but not loaded. The
machinery, rules, and reviewer were untracked and are now committed
(`f25079d1`, `645e9f62`).

### Gate → Proof → Evidence

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Hooks registered & live | **PASS** | `.claude/settings.json:94-110` hooks block (merged #38); `doctrine-gate.log` live PASS entries 05:06–05:16Z (one per real `git commit`/`git push`) |
| 2 | Doctrine-gate RED → commit BLOCKED | **BLOCK (correct)** | `05:13:46Z BLOCK — guard suite FAILED`; stderr `DOCTRINE GATE (fail-closed): fast doctrine guard suite FAILED`; synthetic `assert False` probe in `test_comparative_ranking_guard.py`; HEAD unchanged |
| 3 | Doctrine-gate GREEN → commit ALLOWED | **PASS** | `05:15:53Z PASS`; throwaway commit `2a149589` succeeded (`rc=0`) after the probe was removed |
| 4 | Branch-guard → push to `main` denied | **BLOCK (correct)** | `git push origin HEAD:main --dry-run` → `Permission to use Bash … has been denied` (settings deny, pre-execution; no real push) |
| 5 | Deploy-gate → release w/o sentinel denied | **BLOCK (correct)** | `bash ops/release-backend.sh --help` → `DEPLOY GATE (fail-closed): missing sentinel — full backend pytest exit 0`; no build started; `…/sentinels/` absent |
| 6 | Reviewer cannot Write/Edit | **PASS** | `doctrine-reviewer` subagent toolset = Read, Bash only; no `Write`/`Edit` tool to invoke |
| 7 | ops.md sentinel docs present & consistent | **PASS** | `.claude/rules/ops.md:6-19` documents `touch …/sentinels/{pytest-green,anchor-verified}` + <1h freshness, consistent with `deploy-gate.sh:24,50-51` |

Red-before-green integrity: the doctrine-gate proof reproduced a real RED (suite
failing) and a real GREEN (suite passing) on the same throwaway branch. All
synthetic artifacts (probe test, throwaway file, `proof/governance-gates` branch)
were fully removed; no sentinels were created; worktree left clean.

### Findings (surfaced, not auto-fixed — gate changes require their own plan)

- **F1 — Doctrine-gate over-matches the payload.** The hook greps the *whole*
  `PreToolUse` payload (incl. the Bash `description` field), not just
  `tool_input.command`. A benign `git restore` whose description merely contained
  the text "git commit" triggered a full suite run and was blocked
  (`05:14:24Z BLOCK`). Fix direction: parse `jq -r '.tool_input.command'` and
  match only the command.
- **F2 — Deploy-gate over-matches the payload.** It matches `ops/release-backend.sh`
  anywhere in the command string, so a `git commit` whose *message* referenced
  that path was falsely blocked. Same fix direction as F1.
- **F3 (low) — Reviewer has Bash.** The read-only guarantee is enforced for
  `Write`/`Edit` via the tool-list, but file mutation via Bash redirection is not
  tool-blocked; the read-only role for Bash is by convention (Bash is needed to
  run the guard suite).

Neither F1 nor F2 weakens a gate — both cause *over*-blocking (fail-closed in the
safe direction). They are robustness/usability findings, not security gaps.
