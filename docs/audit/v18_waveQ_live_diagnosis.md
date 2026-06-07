# V1.8 Wave Q — Live Model-Config Diagnosis

**Date:** 2026-06-07 · **Mode:** read-only diagnosis + one ephemeral local
experiment (no code change, no prod config change, no deploy) ·
**Branch:** `feat/v18-wave1-g1-refactor`

**Live target (from the running daemon, not memory):** backend
`ghcr.io/jungt72/sealai-backend:ab586f30-20260606-113347` — `running healthy`,
`APP_ENV=production`. `[E]`

**Evidence grammar:** `[E]` = code-/measurement-backed (`path:line` or run output) ·
`[A]` = assumption/reconstruction · `[NV]` = not verifiable with available data.

**Live env confirmed via `docker exec backend env`** `[E]`:
`OPENAI_ROUTER_MODEL=gpt-5.4-nano`, `SEALAI_CONVERSATION_MODEL=gpt-5.4-nano`,
`SEALAI_COMMUNICATION_RUNTIME_MODEL=gpt-5.4-nano`, `SEALAI_GATE_MODEL=gpt-4o-mini`,
`SEALAI_EXTRACTION_MODEL` **unset → default gpt-4o-mini**,
`SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=true`,
`SEALAI_ENABLE_COMMUNICATION_RUNTIME_LLM=true`, `GENERATION_MODEL=gpt-5-large`.

---

## 1. Config-Truth — env var → consuming call site

Registry: `backend/app/llm/registry.py`. `get_model_for_role(role)` (`:59-82`)
reads the role's env override first (`ROLE_ENV_MAPPING`, `:36-54`), else the
static default (`LLM_REGISTRY`, `:14-33`), else `gpt-4o-mini`. The env is read
**fresh on every call** (`os.getenv`, `:77`); `factory.get_async_llm` /
`get_sync_llm` (`backend/app/llm/factory.py:30-42` / `:16-26`) re-resolve the
model per call and build a fresh client. `[E]`

| Live env var | Live value | Registry role (`registry.py`) | Consuming call site `[E]` | Live-turn stage | In live path? |
|---|---|---|---|---|---|
| `OPENAI_ROUTER_MODEL` | gpt-5.4-nano | semantic_intent_router (`:40`) | `services/semantic_intent_router.py:158` (`get_async_llm`), invoked `agent/api/dispatch.py:739` | ROUTE — pre-gate refine | **YES** (`SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=true`; default would be `false`, `semantic_intent_router.py:107`) — **but only when** the turn is a router candidate (see §1.1) |
| `SEALAI_GATE_MODEL` | gpt-4o-mini | gate (`:38`) | `agent/runtime/gate.py:457` async `_call_gate_llm_async`, `:410` sync; `max_completion_tokens=220`, `temperature=0` (`:472-473`) | ROUTE — frontdoor mode | **YES** (decision layer 4 of 5; fail-safe → GOVERNED) |
| `SEALAI_EXTRACTION_MODEL` | *unset → gpt-4o-mini* | extraction (`:37`) | `agent/graph/nodes/intake_observe_node.py:471` `_llm_extract_params`; `max_tokens=512`, JSON, temp 0 (`:473-482`) | EXTRACTION | **YES — the only LLM in the whole graph** (see §3) |
| `SEALAI_CONVERSATION_MODEL` | gpt-5.4-nano | conversation (`:43`) + governed_reformulate (`:46`) | `agent/runtime/conversation_runtime.py:866`; also `runtime/user_facing_reply.py:31`, `communication/llm_service.py:48` | COMPOSER — conversation/smalltalk + governed reformulate | YES |
| `SEALAI_COMMUNICATION_RUNTIME_MODEL` | gpt-5.4-nano | communication_runtime (`:41`) | `agent/communication/communication_runtime_v8.py:185` | pre-graph intent decision | YES (`SEALAI_ENABLE_COMMUNICATION_RUNTIME_LLM=true`) |
| `SEALAI_KNOWLEDGE_ANSWER_COMPOSER_MODEL` | gpt-4o-mini | knowledge_answer_composer (`:44`) | `agent/communication/answer_composer.py:59`; `max_tokens=1800` (`:52`) | COMPOSER — knowledge | YES (flag default true) |
| `SEALAI_GOVERNED_ANSWER_COMPOSER_MODEL` | gpt-4o-mini | governed_answer_composer (`:45`) | `agent/communication/governed_answer_composer.py:133`; also `active_case_process_answer.py:365` | COMPOSER — governed (graph `output_contract`) | YES (flag default true) |
| `GENERATION_MODEL` / `GENERATION_TEMP` / `GENERATION_MAX_TOKENS` | gpt-5-large / 0.2 / 1024 | — none — | **No Python consumer anywhere** — defined only in `docker-compose.deploy.yml:57-59`; cited as "Live-Modell" in `docs/audits/2026-06-05_product_quality_audit.md:25` but read by no code | — | **NO** |

### 1.1 Per-stage answer to "which model actually serves … in the live turn"

- **route** = frontdoor gate **`gpt-4o-mini`** (`gate.py`), **plus** an optional
  pre-gate refinement by the nano semantic router **`gpt-5.4-nano`**. The
  deterministic `PreGateClassifier` (`services/pre_gate_classifier.py`, no model)
  runs first and owns the hard boundary; the nano router only refines, and is
  **skipped entirely** when `_hard_case_facts_present(message)` is true
  (`semantic_intent_router.py:115-133`) — i.e. a message carrying concrete
  numeric/unit facts never reaches the nano router.
- **extraction** = **`gpt-4o-mini`** (`intake_observe_node.py:471`). *Not nano.*
- **question_policy** = **no dedicated role/model.** The registry has no
  `question_policy` entry; the next-question is produced inside the governed graph
  (deterministic interaction policy + the governed composer `gpt-4o-mini`). The
  one historical "policy" LLM (`agent/runtime/interaction_policy.py`) is
  **DEPRECATED** (header `:2-5`, "Do not call from production paths").
- **composer** = **`gpt-4o-mini`** (knowledge + governed) / **`gpt-5.4-nano`**
  (conversation/smalltalk).

### 1.2 `gpt-5-large` is dead config (cost illusion)

`GENERATION_MODEL=gpt-5-large` is injected into the container env
(`docker-compose.deploy.yml:57`) and listed as a "live model" in the prior audit,
but **no Python reads `GENERATION_MODEL`/`GENERATION_TEMP`/`GENERATION_MAX_TOKENS`**
(`grep -rn … backend --include=*.py` → 0 hits) `[E]`. **gpt-5-large is unused in
chat and everywhere else.** It is not a latency or quality factor; it only
mis-signals the live fleet in env dumps. Recommend dropping it from the compose
env or wiring it to a real role — but that is a config hygiene item, not this
wave's change.

---

## 2. §7 check — what consumes `SEALAI_GATE_MODEL`?

**Consumer = the frontdoor *route* classifier, not a state writer.** `[E]`
`SEALAI_GATE_MODEL` → role `gate` → `gate.py::_call_gate_llm_async` (`:457`,
async) / `:410` (sync). The module docstring (`gate.py:1-24`) states its single
job: choose the frontdoor mode **CONVERSATION / EXPLORATION / GOVERNED**; it is
**stateless** (`:22`) and returns a `GateDecision` (`:368`) — it **writes no
CaseState**. It is decision **layer 4 of 5**; layers 1-3 are deterministic
(sticky session, hard pattern overrides, light-route heuristics) and uncertainty
biases to GOVERNED (`:18`, `max_completion_tokens=220`, `temperature=0`).

**No LLM sits in the V1.8 State-Gate write path.** `[E]` Grep over the entire
graph (`agent/graph/nodes/`) shows the **only** `get_async_llm` call site in any
node is extraction (`intake_observe_node.py:52,471`). The State-Gate single-writer
nodes (`assert` / `governance` / `compute`) call no LLM. → **V1.8 §7 satisfied:
the gate that writes case truth is deterministic code.** No violation finding.

**Naming-hazard finding (documented per directive):** the token "gate" is
overloaded across three distinct components — keep them separate when reading code
or config:

| "gate" | What it is | Model? |
|---|---|---|
| `SEALAI_GATE_MODEL` → `gate.py` | **Frontdoor *route* gate** — CONVERSATION/EXPLORATION/GOVERNED | gpt-4o-mini (decision only) |
| V1.8 **State Gate** | Single writer of case truth (`assert`/`governance`/`compute` graph nodes) | **none — deterministic** |
| Doctrine **output guard** | L1 `runtime/output_guard.py` / L2 `v92/final_guard.py` | **none — deterministic lexicon** (grep: 0 LLM calls) |

`SEALAI_GATE_MODEL` names the *first* of these. The name reads as if an LLM gates
case truth (it does not). Recommend a future rename to `SEALAI_FRONTDOOR_ROUTE_MODEL`
(naming only; out of scope here).

---

## 3. T1 truncation — config-side hypotheses

Symptom: a greeting turn (T1) emitted ~0 useful tokens (forensics row: "guten
Abend" → 0/59 tokens at **0.04 s** latency, `docs/audits/2026-06-05_session_quality_forensics.md`).

- **`GENERATION_MAX_TOKENS=1024` is excluded** — it is unused (§1.2), so it cannot
  cap anything. ✔ (confirms the directive's premise) `[E]`
- **The "16-token" coincidence is a dead path** — `interaction_policy.py:343/368`
  sets `max_tokens=16`, but that module is **DEPRECATED and not called in
  production** (`:2-5`); the `interaction_policy_v1` strings in
  `streaming.py`/`assembly.py` are only `getattr` metadata labels, not calls. `[E]`
- **The live conversation cap is 800, not ~15** — `conversation_runtime.py:768`
  (`max_output_tokens=800`) / `:776` (`max_tokens=800`). No live per-role cap
  matches a ~15-token cut. `[E]`

**Leading hypothesis (config-side):** the **greeting/Tier-0 fast-path emits
near-empty output**, not a token-limit cut. 0.04 s is far too fast for any LLM
round-trip → either a deterministic/canned/empty greeting branch or an immediate
stream cut, *before* any model generates. Inspect the greeting/smalltalk handling
in `conversation_runtime.py` (`_GREETING_RE` `:60`, `_SMALLTALK_RE` `:63`,
smalltalk preview suppression `:414-428`, trim `:431-448`) and the visible-segment
streaming in `streaming.py` (`:100-116`, 32-char chunking — not a token cut).

**Open / not yet verified `[NV]`:** whether an LLM was invoked at all on the live
T1. Next step (not done here): capture the live T1 SSE frames / LangSmith run to
confirm zero-LLM vs early-stop. Keep stream-termination and the greeting fast-path
as the live hypotheses; the token-limit family is excluded.

---

## 4. Q2(b) controlled experiment — the "salzsäure" misroute

> **Correction (2026-06-07, CR1) — read first.** The salzsäure messages used in
> this §4 were *reconstructed approximations* `[A]`. They are now superseded by
> **two real sources**: (1) the in-repo forensics **Session A** — whose medium turn
> is **T7 "wohl salzwasser … Getriebe hat Getriebeöl"** (`pending_slot_answer` for
> `medium` on an active case), *not* a salzsäure turn; and (2) an **owner-provided
> verbatim Session B** (`[E-owner]`) — a **second, separate** live session that *is*
> the real salzsäure session: **T1′ "hallo"** (reply truncated after *"…Dichtungs-
> bzw."*) and **T2′ "lass uns bitte meine dichtung besprechen. was für ein material
> ist für salzsäure optimal"** (reply = generic *"Werkstoffvergleich: PTFE vs POM"*
> + a next-question asking for the medium). The §4 conclusion below ("bump extraction
> gpt-4o-mini → gpt-4o captures most of the win") is **superseded by §6**, which runs
> the verbatim corpus and finds the extraction tier changes nothing — the real lever
> is the nano semantic router. Treat §4 as the honest record of the first probe; **§6
> is the current verdict.**

**Method `[E]`:** ephemeral `docker exec -i backend python` process (no service
mutation; in-process `os.environ` overrides only; LangSmith tracing disabled so
prod traces are not polluted). Called the **pure** route/extraction functions
directly — `PreGateClassifier.classify`, `refine_pre_gate_classification`,
`gate.decide_route_async`, `intake_observe_node._llm_extract_params` — none of
which persist state. No separate non-prod stack exists on this host; this is the
same diagnostic mechanism the 2026-06-05 forensics used.

**Caveat `[A]`:** the verbatim T2 wording was not available in-repo, so three
reconstructed messages spanning the "hard case facts" axis were used, plus two
regression guards. Conclusions are gated on the smoke-set, not this single repro.

**Configs:** baseline = current prod (`router gpt-5.4-nano`, `gate gpt-4o-mini`,
`extraction gpt-4o-mini`); treatment = whole route+extract chain one tier up
(`router gpt-4o-mini`, `gate gpt-4o`, `extraction gpt-4o`). Resolution confirmed
in-run via `get_model_for_role`.

| Turn (`[A]` input) | hard facts | baseline → treatment | flip |
|---|---|---|---|
| `Salzsäure` (bare) | no | router-applied F→T, both `KNOWLEDGE_QUERY`; gate **GOVERNED** both; medium extracted both | equivalent route; treatment slightly more knowledge-leaning |
| `Dichtung für Salzsäure` | no | **router reclass `KNOWLEDGE_QUERY` (applied) → stays `DOMAIN_INQUIRY` (not applied)**; gate GOVERNED both; medium extracted both | **YES — router** |
| `…Salzsäure 30%, 60 °C, 1500 U/min, Welle 40 mm` | yes (router bypassed) | gate `hard_override:numeric_unit` → GOVERNED both; **medium misfiled as `material` (medium_extracted=False) → correctly `medium` (True)** | **YES — extraction** |
| `Was ist PTFE?` (guard) | no | `KNOWLEDGE_QUERY` → gate `CONVERSATION` — **unchanged** | no regression ✔ |
| `Guten Abend` (guard) | no | `GREETING` → gate `CONVERSATION` — **unchanged** | no regression ✔ |

### 4.1 Findings (clean per-component attribution)

Because different turns exercise different components, the combined treatment still
attributes cleanly:

1. **Frontdoor route was never the bug.** The gate routed **GOVERNED** for all
   three salzsäure turns **even at baseline gpt-4o-mini** — no case leaked to
   CONVERSATION; the uncertainty-bias held. The strict plan decision-rule
   ("route flips to GOVERNED under treatment") is therefore **not met** — it was
   already GOVERNED.
2. **Nano *does* cause a pre-gate *classification* misroute.** On the borderline
   `Dichtung für Salzsäure`, the **nano** router (baseline) **overrode** the
   correct `DOMAIN_INQUIRY` (governed-case intent) to `KNOWLEDGE_QUERY`
   (`knowledge_explain`). Bumping the router to `gpt-4o-mini` stopped the override
   (stayed `DOMAIN_INQUIRY` / `governed_case_intake`). This is the real,
   reproducible nano-attributable defect — at the intent-classification layer
   that feeds dispatch path-selection, *not* at the frontdoor gate.
3. **The most damaging defect is extraction, and it is a *tier* issue, not nano.**
   On the concrete case, baseline **gpt-4o-mini** misfiled the central RWDR fact
   "Salzsäure 30%" into `material` (so `medium_extracted=False`); treatment
   **gpt-4o** correctly produced `medium=Salzsäure` + `medium_qualifiers=30%`.
   Extraction was never nano — this is `gpt-4o-mini → gpt-4o`.
4. **No regression** on knowledge/greeting routing under treatment.

### 4.2 Verdict on Q2(b) and the Q3(i) candidate

**Q2(b) "nano assignment is the primary cause" — partially confirmed, refined.**
Nano *is* confirmed to misroute the pre-gate classification of a borderline
case→knowledge inquiry. But it is **not the whole story**: the frontdoor route was
correct (GOVERNED) at baseline, and the highest-impact correctness defect
(medium → material misfile) is a **gpt-4o-mini extraction** limitation independent
of nano. Cause is **split** (router-nano *and* extraction-4o-mini), not solely
nano.

**Recorded as a Q3(i) instant-config candidate `[E]`:** raising the route+extract
chain one tier yields **2 correctness improvements, 0 regressions** on this
5-turn set — qualifying it as a config-only candidate.

**Gate (do not ship on this repro):**
- This is a **5-turn, reconstructed** set. Before any prod change, run a **proper
  before/after smoke-set** (no named artifact exists yet — define one):
  greeting (T1), the **verbatim** T2, ≥3 more media (incl. a benign water/oil
  case), a pure knowledge query, a comparison turn, and a governed multi-fact
  case. Score route-correctness, extraction field-slotting, latency, and cost
  delta.
- Consider **splitting the lever** in the smoke-set: extraction `gpt-4o-mini →
  gpt-4o` likely captures most of the win (the medium-field fix) at lower cost
  than also moving router and gate; isolate to avoid over-paying.
- Any prod config change **HALTs before prod** for owner approval (workflow.md);
  this wave makes **no** config change.

---

## 5. Reproducibility

Experiment harness: `/tmp/wq_exp.py` (ephemeral, not committed). Run:
`docker exec -i backend python - < /tmp/wq_exp.py` with `LANGCHAIN_TRACING_V2=false`
set in-process. Baseline/treatment env overrides and the captured route+extraction
per turn are in §4. Code evidence is against the running image
`ab586f30-20260606-113347` (line numbers track `feat/v18-wave1-g1-refactor`).
No `.env*` was read; no service, config, or state was mutated.

---

## 6. Smoke-set — four-arm config experiment (the current verdict)

**Method `[E]`:** same ephemeral envelope as §4 (`docker exec -i -w /app backend
python - < /tmp/wq_smoke.py`, in-process `os.environ` overrides only, LangSmith off,
pure functions, no state writes). **≥3 reps per LLM measurement, temp 0.** Harness
memoises by `(kind, model/flag, message)`, so identical (model, message) work is not
repeated across arms. Run output: `/tmp/wq_smoke_out.json`.

**Corpus (13 turns):** Session-B verbatim `[E-owner]` (C12 = T2′ salzsäure, C13 = T1′
"hallo"), Session-A `[A]` (C1/C2/C9/C10/C11), and designed controls/variants
(C3–C8). The pending-slot turns (C2–C8) carry an active-case
`PendingQuestion(target_field="medium", expected_answer_type="medium_value",
status="open")`; C12/C13 are fresh (no pending slot).

**Arms** (gate = `gpt-4o-mini` in all; composers out of harness):
`arm1 baseline` (router nano · sem ON · extract 4o-mini) ·
`arm2 extraction-only` (router nano · sem ON · extract 4o) ·
`arm3 router OFF` (sem **false** · extract 4o) ·
`arm4 router bumped` (router 4o-mini · sem ON · extract 4o).

### 6.1 Routing — the nano semantic router demotes legitimate case intent

Effective pre-gate label = `applied ? router_proposed : deterministic`. All six
case-intent turns are **`DOMAIN_INQUIRY` deterministically** (the deterministic
`PreGateClassifier` is correct); the semantic *refine* is where demotions enter. `[E]`

| Turn (`[E]`) | det | arm1 nano | arm2 nano | arm3 **OFF** | arm4 4o-mini | frontdoor gate (all arms) |
|---|---|---|---|---|---|---|
| C2 dual-medium slot | DOMAIN | **KNOWLEDGE ✗** | **KNOWLEDGE ✗** | DOMAIN ✓ | DOMAIN ✓ | GOVERNED |
| C5 w/ "material" slot | DOMAIN | **KNOWLEDGE ✗** | **KNOWLEDGE ✗** | DOMAIN ✓ | DOMAIN ✓ | EXPLORATION |
| C6 no-"material" slot | DOMAIN | **KNOWLEDGE ✗** | **KNOWLEDGE ✗** | DOMAIN ✓ | DOMAIN ✓ | GOVERNED |
| **C12 salzsäure (T2′)** | DOMAIN | **KNOWLEDGE ✗** | **KNOWLEDGE ✗** | DOMAIN ✓ | DOMAIN ✓ | GOVERNED |
| C3 bare "salzwasser" slot | DOMAIN | DOMAIN ✓ | DOMAIN ✓ | DOMAIN ✓ | **KNOWLEDGE ✗** | CONVERSATION |
| C7 "heißes Wasser" slot | DOMAIN | DOMAIN ✓ | DOMAIN ✓ | DOMAIN ✓ | **KNOWLEDGE ✗** | CONVERSATION |

Guards (invariant across **all** arms `[E]`): C1/C13 "Guten Abend"/"hallo" →
`GREETING`/CONVERSATION; C9 "Infos zu PTFE" + C10 "vergleiche mit NBR" →
`KNOWLEDGE_QUERY`; C11 "Bootswelle 60 mm…" → `DOMAIN_INQUIRY`/GOVERNED. **Zero
regressions** between arms on every guard.

Findings:
1. **nano** (baseline) demotes the *multi-word* case inquiries **C2/C5/C6/C12**
   `DOMAIN_INQUIRY → KNOWLEDGE_QUERY`. Three of them (C2/C6/C12) the frontdoor gate
   still routes **GOVERNED** — so the demoted label adds a *spurious knowledge
   side-answer on a governed case* (the live double-composer, forensics Q2b/§5).
   **This reproduces the live C12 (T2′) misroute: governed salzsäure case → generic
   material-comparison answer + medium re-ask.** `[E]`
2. **4o-mini router** fixes C2/C5/C6/C12 but **newly demotes C3/C7** (bare media) —
   a different regression set. `[E]`
3. **router OFF (arm3): zero demotions** — the deterministic label stands for all six.
   The only arm that is route-correct everywhere on this corpus. `[E]`

> **Harness limitation `[NV]`:** the C9/C10 *raw* frontdoor gate returns GOVERNED
> (its uncertainty→GOVERNED bias) although live dispatch routes knowledge turns to
> CONVERSATION via the `KNOWLEDGE_QUERY` label + `knowledge_override` guard. This is
> constant across arms (not a regression) and is mitigated downstream; the harness
> measures `gate.decide_route_async` in isolation, not full dispatch.

### 6.2 Three-layer medium attribution (S4)

| Turn | regex/specialist (deterministic) | slot-binder (deterministic) | LLM 4o-mini → 4o |
|---|---|---|---|
| **C2** "salzwasser … Getriebeöl" | **`medium_conflict:Getriebeöl \| Salzwasser` → canonical `None`** (`normalization.py:459-482`); `:1640` guard skips *all* medium keys | **`None`** — 44 ch / 6 words > 36/3 (`slot_answer_binding.py:94-111`) | **two `medium` extractions** (`salzwasser` + `Getriebeöl`, conf 0.85) **at both tiers** → reducer picks one + `ConflictRef` (`reducers.py:758-833`) |
| **C12** salzsäure (T2′) | **`Salzsäure` / requires_confirmation** (`medium_confirmation_required`) — captured deterministically | n/a (fresh, no pending slot) | **`[]` — nothing — at both tiers** |
| C3/C5/C6/C7/C8 (single medium) | clean `medium_normalized` (Salzwasser/Wasser/Hydrauliköl…) | binds C3/C7 (short), regex covers C5/C6/C8 | `medium` extracted, **rate 1.0 at both tiers** |

**Extraction tier is a no-op on this corpus.** Every medium turn's `medium`-rate is
**identical at gpt-4o-mini and gpt-4o** (1.0 where it matters; 0.0 for C12 where the
LLM ignores the medium and the *deterministic* specialist catches it). The salient
word "material" in C5/C12 **never** caused a `material` misfile (`material_rate=0.0`
everywhere). → **The Wave-Q §4 hypothesis — "bump extraction to fix the medium↔material
confounder" — is refuted: there is no model-tier confounder to fix here.** `[E]`

**Reducer is not the culprit for the drop:** when a single medium is produced it
asserts cleanly (`reducers.py:705-833`); the dual-medium *collapse* is the issue, not
a reducer bug.

### 6.3 Cost + latency (S3)

Extraction per pass (mean over medium turns, ≥3 reps `[E]`):

| extraction model | total tok / pass | latency / pass | AC3 ×4 tok | AC3 ×4 latency | $ rate `[A]` |
|---|---|---|---|---|---|
| gpt-4o-mini | ~535 | ~1.08 s | ~2 139 | ~4.30 s | $0.15/$0.60 per 1M (in/out) |
| gpt-4o | ~543 | ~0.88 s | ~2 172 | ~3.51 s | $2.50/$10.00 per 1M (in/out) |

Token counts are ~equal (same prompt + 512-cap). gpt-4o is marginally *faster* but
costs **~16× per token** for **zero** correctness gain on this corpus. The AC3
Class-B worst case (4 extraction passes) ≈ 2.1k tokens/turn either way. Separately,
**router OFF removes the nano refine LLM call entirely** on every borderline turn →
unambiguously cheaper and lower-latency (nano $ rate unknown `[A]`).

### 6.4 Verdict against the S1 decision rule

> *Smallest config delta that is route-correct + extraction-correct with zero
> regressions wins.*

**Winner = `SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=false`, extraction unchanged at
`gpt-4o-mini`** (= arm3 **minus** the unjustified 4o bump). It is:
- **route-correct** — restores `DOMAIN_INQUIRY` on C2/C5/C6/**C12** (the live salzsäure
  misroute), zero demotions on the corpus;
- **extraction-correct** — on the governed path the deterministic Pass-1 captures the
  medium (C12 salzsäure → `requires_confirmation`; single media → confirmed), so the
  governed turn asks the *right* follow-up instead of a generic comparison;
- **zero regressions** — all guards invariant; unlike arm4 it does **not** demote C3/C7;
- **cheapest** — removes the nano call, no extraction-tier spend.

| arm | fixes C2/C6/C12 governed demotion | new regressions | extraction gain | cost vs baseline |
|---|---|---|---|---|
| arm1 baseline | — | — | — | nano call present |
| arm2 extraction-only | **no** (nano still demotes) | none | none | +4o $ |
| **arm3 router OFF** | **yes** | **none** | none | **−nano call** (cheapest) |
| arm4 router bumped | yes | **C3/C7 demoted** | none | +4o-mini router call |

**Caveat — HALT before prod `[A]`:** the semantic router also participates in
**history/anaphora resolution** (`recent_history`, `needs_history_resolution`,
`semantic_intent_router.py:148-182`) — *not* covered by this single-turn corpus, but
required by AGENTS.md (context bridges "die beiden / beide / und X? / was ist besser").
Disabling the flag globally risks regressing multi-turn anaphora. Before any prod
flip: run an anaphora/context-bridge regression set. **If anaphora regresses, prefer a
narrower code fix** — stop the refine from *demoting* `DOMAIN_INQUIRY → KNOWLEDGE_QUERY`
(a guard in the router decision logic, `_decision_from_payload`
`semantic_intent_router.py:185+`) — over the global flag.

> **Resolved in §7 — PASS.** The regression gate ran: AN1 shows the refine layer's only
> functional consumer is the pre-gate label and anaphora resolution is router-independent
> (`KnowledgeContextBuilder`); AN2 shows router-OFF is equal-or-better on every scenario
> (and the router only *harms* case continuity on two). The flag flip is cleared for the
> owner-applied prod step (§7.3).

### 6.5 Q2a closed root cause (S4) + CR4 dual-medium ruling

**Live Q2a ("medium recognized, not asserted, re-asked") is closed as a dual-medium
representation gap — confirmed at three layers, model-independent:** `[E]`
1. **specialist:** two distinct media → `medium_conflict` → `canonical_medium=None`;
   `extract_parameters` skips *every* medium key (incl. the follow-up) at
   `normalization.py:1640` — the conflict is silently dropped;
2. **slot-binder:** rejects the answer (length/words) → `None`;
3. **reducer:** even when the LLM correctly extracts **both** media, the single-`medium`
   schema keeps **one** (Salzwasser) and drops the other (Getriebeöl) with a
   `ConflictRef` (`reducers.py:758-833`).

**CR4 ruling (recorded):** the gap is **"the single-`medium` schema cannot represent a
dual-medium (per-side) answer"**, *not* "answer too long". A boat-shaft RWDR genuinely
has two media (seawater outside, gear oil inside). **No config arm fixes this** → it is
a **code/schema arc** (medium *per side*, never disambiguate to one) — out of this
phase's config-only scope. HALT for a separate arc.

> Note `[A]`: on the §6 paraphrase the LLM *recovers* one medium (so the full pipeline
> would assert Salzwasser + a dropped conflict), whereas live Q2a dropped it entirely —
> a wording/path difference (paraphrase ≠ verbatim). Either net effect (re-ask, or
> pick-one-silently) is wrong for a dual-medium case; the CR4 ruling is unchanged.

### 6.6 CR3 — origin of "Werkstoffvergleich: PTFE vs POM"

The PTFE-vs-POM answer is the **`material_comparison` AnswerMode**, selected on the
KNOWLEDGE path when the pre-gate reason contains "material"/"vergleich"
(`conversation_controller_v7.py:281-283`), rendered from the curated profiles in
`app/services/knowledge/material_comparison.py` (PTFE `:367`, POM `:471`; framing
`prompts/communication/governed_technical_orientation.j2:6`). For C12 it is reachable
**only because the nano router demoted the turn to `KNOWLEDGE_QUERY`** — with the router
OFF the turn stays `DOMAIN_INQUIRY` and never enters `material_comparison`. CR3 thus
reinforces §6.4. No fix this phase.

### 6.7 T1 / T1′ truncation — still open, scheduled

C1 "Guten Abend" and C13 "hallo" route `GREETING`/CONVERSATION correctly in all arms
`[E]`; truncation is a **composer/streaming** property the route/extraction harness
does not exercise. The verbatim T1′ cut (*"…Wobei kann ich dir bei deiner Dichtungs-
bzw."*, `[E-owner]`) points at a sentence-trim / stream-termination in the greeting
composer, not a routing or token-cap cause (`GENERATION_MAX_TOKENS` already excluded,
§3). **Next small Q item:** capture the live greeting SSE frames / composer trace to
pin the exact cut point in code.

### 6.8 Prod path (S5)

- **Config-only proposal:** set `SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=false`; **leave
  extraction at `gpt-4o-mini`** (the §4 extraction bump is not justified). Bundle the
  dead-config removal of `GENERATION_MODEL`/`GENERATION_TEMP`/`GENERATION_MAX_TOKENS`
  (W5, §1.2) into the same operator action.
- **HALT before prod (workflow.md):** owner-applied in `.env.prod` (CC cannot). The
  anaphora/context-bridge gate has **PASSED (§7)** → cleared; the operator runbook is §7.3
  (flip + `GENERATION_*` removal + restart + live C1–C13 re-verify).
- **Out of config scope → separate arcs:** (a) CR4 dual-medium per-side schema (Q2a);
  (b) T1/T1′ greeting-composer truncation; (c) optional `material_comparison`
  single-material routing (forensics Q4).

**Reproducibility:** harness `/tmp/wq_smoke.py`, output `/tmp/wq_smoke_out.json`,
field-value probe `/tmp/wq_probe.py` (all ephemeral, not committed). Evidence against
image `ab586f30-20260606-113347`. No `.env*` read; no service/config/state mutated.

---

## 7. Anaphora / context-bridge regression gate (AN1–AN4)

The §6.4 caveat — "router-OFF might regress multi-turn anaphora" — is the gate on the
prod flip. Resolved here. **Verdict: PASS** (router-OFF introduces no anaphora
regression; it is equal-or-better on every scenario).

### 7.1 AN1 — consumer map (this alone nearly settles it) `[E]`

**The semantic refine layer's only *functional* consumer is the pre-gate label.**
At `agent/api/dispatch.py:739-745` the decision is used exactly twice:
`pre_gate = semantic_decision.classification_result(pre_gate)` (the label +
`escalate_to_graph`, model `:76-87`) and `semantic_decision.as_trace()` →
`semantic_pre_gate_trace`, which flows **only** to logging / `emit_quality_trace`
(`dispatch.py:1285-1316`). The decision's rich fields (`materials`,
`compared_entities`, `needs_history_resolution`, `:70-72`) appear **only** in
`as_trace()` — **no business logic consumes them.**

**Anaphora/context resolution lives elsewhere and is router-independent.** It is
`agent/communication/knowledge_context_builder.py` — `KnowledgeContextBuilder` resolves
referents from conversation `recent_history` (`_last_history_material_subject` `:336`,
`_requested_material_subjects` `:278`, `_comparison_subjects_from_answer` `:317`), invoked
at `dispatch.py:1395-1416` with `recent_history`, **not** with the router decision. The
governed case state (Postgres event store) carries case continuity independently.

→ Disabling `SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER` **cannot** disable anaphora
*resolution*. The residual risk narrows to one thing: the **history-blind** deterministic
`PreGateClassifier.classify` (`pre_gate_classifier.py:26`, no history param) might
mis-route a history-dependent follow-up that the router's history-aware reclassification
would otherwise fix. Structurally that risk is bounded: `semantic_pre_gate_candidate`
(`semantic_intent_router.py:115-134`) **skips the router entirely** for turns with
concrete facts (`_hard_case_facts_present`) or a `KNOWLEDGE_QUERY` deterministic label —
which covers most anaphoric follow-ups (`und bei 80 °C?`, `vergleiche mit NBR`).

### 7.2 AN2 — multi-turn regression run (router ON vs OFF, ≥3 reps, nano) `[E]`

Measured the follow-up turn with the prior turns as `recent_history`. OFF label =
deterministic (history-blind); ON label = `applied ? proposed : deterministic`. Harness
`/tmp/an_harness.py`, output `/tmp/an_out.json`.

| # | follow-up | router fires? | OFF label / escalate | ON (nano) label / escalate | verdict |
|---|---|---|---|---|---|
| i | "wohl salzwasser … Getriebeöl" (T6→T7) | **yes** | DOMAIN_INQUIRY / ✓ | **KNOWLEDGE_QUERY / ✗ (demoted)** | **OFF better** |
| ii | "bitte vergleiche mit NBR" (after PTFE) | no (det=KNOWLEDGE) | KNOWLEDGE_QUERY | KNOWLEDGE_QUERY (applied=False) | equal |
| iii-a | "und bei 80 °C?" | no (hard facts) | DOMAIN_INQUIRY / ✓ | DOMAIN_INQUIRY / ✓ | equal |
| iii-b | "reicht das auch bei 5 bar?" | no (hard facts) | DOMAIN_INQUIRY / ✓ | DOMAIN_INQUIRY / ✓ | equal |
| iv | "zurück zur Welle: welches Medium…" | no (bypassed) | DOMAIN_INQUIRY / ✓ | DOMAIN_INQUIRY / ✓ | equal |
| v | "salzwasser" (pending slot after digression) | **yes** | DOMAIN_INQUIRY / ✓ | **UNSTABLE {DOMAIN,KNOWLEDGE}** across reps | **OFF better** |

Frontdoor gate route is **router-independent** (gate model constant) and unchanged by
the flag. Findings:
- **4/6 scenarios: router bypassed** (`candidate=False`) → ON ≡ OFF, identical. The
  anaphora is resolved by `KnowledgeContextBuilder` regardless (AN1).
- **2/6 (i, v): router-ON harms** — it demotes (i) or *flakily* demotes (v, non-deterministic
  across reps) a legitimate case-continuation turn `DOMAIN_INQUIRY → KNOWLEDGE_QUERY`;
  OFF holds the correct `DOMAIN_INQUIRY`/escalate.
- **Router-ON never improved on deterministic** anywhere in this corpus; it only left it
  alone or demoted it. **Zero evidence the router adds anaphora value; positive evidence
  it harms case continuity.**

*Method note `[E]+[A]`:* the harness measures the pre-gate **label + route + escalate**
(the router's only functional output, AN1); case-field continuity is carried by the
governed event store + `KnowledgeContextBuilder` (history), both router-independent — so
label/route preservation is sufficient to conclude continuity is preserved. Not a full
stateful multi-turn graph replay (corpus is 6 representative scenarios, not exhaustive).

### 7.3 AN3 — decision matrix → **PASS**

The gate passes. **Recommended operator action (Thorsten; `.env.prod`; CC cannot apply):**
1. `SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER=false`
2. remove dead `GENERATION_MODEL` / `GENERATION_TEMP` / `GENERATION_MAX_TOKENS` (W5, §1.2)
3. recreate/restart the backend service
4. **post-flip live verification:** re-run the C1–C13 smoke corpus (§6) against the live
   service and confirm C2/C5/C6/**C12** hold `DOMAIN_INQUIRY` and the guards are unchanged.

Keep extraction at `gpt-4o-mini` (the §4 bump is unjustified, §6.2). Every prod deploy is
logged in `docs/ops/GOVERNANCE_LOG.md`.

**Unchosen option (recorded, not built — verdict is PASS):** had AN2 *failed*, the fix
would have been a **narrow code patch** blocking the `DOMAIN_INQUIRY → KNOWLEDGE_QUERY`
demotion inside the refine layer (`semantic_intent_router._decision_from_payload`,
`:185+`), with red-before-green tests + a `doctrine-reviewer` pass (it touches routing),
leaving the flag ON. Not implemented.

### 7.4 AN4 — deferred-arc sequencing (RE-PLAN GATE decision)

- **T1 / T1′ greeting-composer truncation** — next small Q item *after* the flip decision;
  cheap, isolated (greeting SSE/composer trace, §6.7).
- **CR4 dual-medium per-side schema (Q2a, PILOT-BLOCKING)** — touches
  `intake_observe_node`, `reducers.py`, `normalization.py`, **the exact files the G1
  refactor is about to reshape**. **Decision: schedule it as the FIRST post-G1 item, not
  pre-G1**, to avoid a refactor collision. Recorded here as an explicit RE-PLAN GATE
  decision (ordering, not drift): doing it pre-G1 would be rebased away by G1; doing it
  first post-G1 lands it on the new seams.

**Reproducibility:** `/tmp/an_harness.py` → `/tmp/an_out.json` (ephemeral, not committed).
Evidence against image `ab586f30-20260606-113347`. No `.env*` read; no service/config/
state mutated.
