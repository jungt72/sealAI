# Runtime-Audit Fix-Map

Status ledger for the V10 governed-runtime audit fixes (doctrine + composition +
routing + final-guard enforcement). Versioned in-repo so the fix-map, deploy
ledger, and verification findings survive sessions/compaction.

Scope: `demo/rwdr-limited-external` (guided limited external demo). All product
boundaries from `AGENTS.md` apply — no suitability/selection/ranking/final-release
language; guards are never weakened to make a test pass.

---

## Fix-map taxonomy (roots)

| Group | Theme | ACs | Root (file:line) | State |
|-------|-------|-----|------------------|-------|
| **A / A.3** | Doctrine — comparative-ranking leaks | — | `agent/runtime/output_guard.py` `_COMPARATIVE_RANKING_PATTERNS` (both guard layers inherit via `comparative_ranking_patterns()`); L2 backstop `agent/v92/final_guard.py` | **Shipped** |
| **C** | Composition — dedup side-answer seam (T5.1) | 1, 2, 11 | `agent/api/routes/chat.py:516-532` (`_side_answer_with_resume`) + `agent/communication/active_case_side_claim_policy.py:~422` (`_ensure_required_context`) | **Shipped** |
| **D** | Routing — `case_facts_present` collapse (T3.1) | 9, 13 | `services/semantic_intent_router.py:~180` (`_decision_from_payload`) | **Shipped** |
| **B** | State — re-ask loop (T4.2) + persist-gap (T4.1) | 3, 9, 13, 14, 18 | `agent/communication/active_case_resume.py:94-101` + parsers `:151-184` + `agent/graph/slot_answer_binding.py:158-207`; T4.1 nuance `agent/runtime/runtime_contract.py:~182` | **Closed by D** (see below) |
| **F1** | Final-guard — exploration stream bypass | — | `agent/api/streaming.py:646` (`_stream_exploration_reply` now routes the assembled reply through `apply_v92_contracts_to_payload(route_hint="knowledge")`; late block reuses the existing `text_reset`+fallback) | **Shipped** |
| **F2** | Final-guard — non-technical block inert | — | `agent/v92/runtime_contract.py:~500` (non-technical branch substitutes `FAST_PATH_GUARD_FALLBACK` on block + re-validates, mirroring the technical branch `:471-477`) | **Shipped** |

---

## Deploy ledger

All deploys: red-before-green → CI (`agent-bff-guardrails`) green → merge →
pre-deploy gate `pytest backend -q -rf` exit 0 → `ops/release-backend.sh`
(backend only) → live acceptance in the deployed container. No rollbacks.

Rollback anchor is always re-verified from the running daemon (`docker inspect backend`),
never from memory.

| Group | PR | Merge | Live image digest (healthy) | Live acceptance |
|-------|----|-------|------------------------------|-----------------|
| Doctrine A + A.3 | #30 | `39615b39` | `ghcr.io/jungt72/sealai-backend:39615b39-20260603-133014@sha256:703728995bd8c3488e8d6c8761fcb5bfe729adeec21b04a1b76f24de0392d01e` | original repro blocked at both layers; neutral render clean |
| C dedup (T5.1) | #31 | `7429131a` | `ghcr.io/jungt72/sealai-backend:7429131a-20260603-140325@sha256:a452646c2d05ba2ab2a043e450d6658168650e55e57d68f13fd153cb111719b5` | S8 one-acknowledgment; value-absent seam preserved |
| D routing (T3.1) | #32 | `bac97dff` | `ghcr.io/jungt72/sealai-backend:bac97dff-20260603-142535@sha256:70ae180638f872891432b51395413046e133c8030d3b691a5d54fdb35a943c5d` | S5 both intents → case path; AC9 no over-route |
| F1/F2 final-guard enforce | #34 | `8431dda2` | `ghcr.io/jungt72/sealai-backend:8431dda2-20260603-190217@sha256:d102da8820b9f4c66057d85573a11d55a1e99d2c3359176db4233708fca9f78e` | deployed-container: enforce-on-block (`guarded_fallback_used=True`, `initial=block`); AC8 clean knowledge unchanged; doctrine repros still block at L1; smoke all PASS |

Pre-A.3 rollback anchor (daemon-verified at the time):
`ghcr.io/jungt72/sealai-backend:aa7a450c-20260603-055758@sha256:b86b08ac41a84d418224d56e84e48262bdd2e0ca65cb3d44315054c17cbcae29`

---

## Group B — CLOSED BY D (verification, not implementation)

Group B was planned as a CaseState-mutation fix ("route narrative facts into the
state-gate candidates" + break the re-ask loop). A read-only probe of the **pure
deterministic** routing (no LLM, no mutation) shows the audited bug **does not
reproduce** after D — red-before-green fails at **red**.

Evidence (reproducible):

- `_hard_case_facts_present("wir verwenden FKM bei 100°C") = True` — "100°C" is a concrete case marker.
- `PreGateClassifier().classify("wir verwenden FKM bei 100°C") -> DOMAIN_INQUIRY`
  (reason `deterministic_domain_inquiry`) — **independent of the LLM**.
- `ConversationControllerV7.decide(...)` on that message with an open `medium` slot:
  - post-D `pre_gate=DOMAIN_INQUIRY` → `governed_intake` (mutation=`proposed`) → governed graph → extract + persist candidates.
  - pre-D `pre_gate=KNOWLEDGE_QUERY` → `active_case_side_question` (mutation=`forbidden`) → resume seam → re-ask, fact loss.
- `side_question_detection.classify_message_as_knowledge_side_question(...)` returns `None`
  for the S6 message (`side_question_detection.py:80`: `contains_concrete_case_marker` short-circuits the side classifier).
- `run_governed_graph_turn` returns `persisted_state` → the governed-intake path persists the
  **full** state (observed extractions / candidate facts / asserted claims), not just
  `conversation_messages` (the latter is what `loaders.persist_visible_governed_turn` writes on the no-mutation routes).

Conclusion: the B roots (`active_case_resume.py:94-101` re-ask;
`persist_visible_governed_turn` messages-only) are reached **only** on the
no-mutation `active_case_side/process_question` paths. A concrete-fact-bearing turn
no longer lands there — **D (T3.1) is exactly the flip** from
`active_case_side_question` to `governed_intake`. The audited T4.2 (loop) and T4.1
(persist) were downstream symptoms of D's routing collapse, now deployed live.

Implementing the proposed resume-seam "route-to-state-gate" mutation would (1)
duplicate the existing `governed_intake` → graph candidate-extraction path and (2)
violate doctrine — the resume seam is "intentionally communication-only … never
writes engineering state", and `AGENTS.md` forbids a second mutation runtime beside
the governed runtime. Decision: **accept closed-by-D; do not add a resume-seam
mutation; do not weaken a seam to satisfy a non-reproducing test.**

Note the genuinely D-dependent variant is material-only without a numeric marker
(e.g. "wir verwenden FKM" → `deterministic_standalone_technical_knowledge` →
KNOWLEDGE), which staying on the knowledge path is **doctrinally correct** under AC9
(a bare material mention without application facts must not enter the case flow).

---

## Backlog — log only (not actioned)

**Slot over-capture (explicit-medium parser).** `"das medium ist Öl bei 100°C"` →
`resolve_slot_answer_binding` returns `medium="Öl bei 100"`: the explicit-medium
regex char-class (`agent/graph/slot_answer_binding.py:206-207` and the mirror in
`agent/communication/active_case_resume.py:164-168`) swallows the trailing
temperature fragment and stops at `°`. Lands as a *candidate* with
`needs_clarification` (mutation `proposed`), not an asserted fact — low severity,
pre-existing. Would need its own red-before-green + zero-regression pass before any
change.

---

## F1 / F2 — SHIPPED (final-guard enforcement)

PR #34, merge `8431dda2`, live digest `…@sha256:d102da88…` (see ledger). Enforcement
only — **what** blocks is unchanged (`output_guard.py` L1 lexicon untouched); only that
an L2 block now enforces.

- **F1** — `streaming.py:646` `_stream_exploration_reply` routes the assembled reply
  through `apply_v92_contracts_to_payload(route_hint="knowledge", state=None)` so L2
  runs on the streamed knowledge path; a late block reuses the existing
  `text_reset`+`_visible_stream_segments` fallback. Closes a real L2-only leak class
  L1 misses (plural/adverb suitability, e.g. "sind geeignet" / "ist sicher geeignet").
- **F2** — `runtime_contract.py` non-technical branch substitutes `FAST_PATH_GUARD_FALLBACK`
  on block + re-validates + records `initial_guard` (mirror of technical `:471-477`).
  Fixes every non-technical knowledge caller of the contract guard. Live-verified:
  `guarded_fallback_used=True`, `initial_final_guard_decision="block"`.

### Residual (accepted / characterise — not actioned)

- **(a) L2-block streaming flash** — pre-existing for L1 (`streaming.py:605`/`636`) and
  inherent to token streaming + post-hoc lexical guarding; F1 reuses the same path,
  fires only on an actual block. **Accepted.** Durable answer = a semantic doctrine
  check **before** the stream starts (see Next-up #1).
- **(b) Slot over-capture** — `"das medium ist Öl bei 100°C"` → `medium="Öl bei 100"`
  (explicit-medium regex swallows the temp fragment). Candidate/`needs_clarification`,
  low severity. (Same item as the Backlog above.)
- **(c) `übertrifft` pattern is lemma-list only** — trade names / "alle anderen" objects
  slip the material⇄material `übertrifft` denylist (only the fixed material lemma list
  is an object). Comparative-ranking leak via a non-lemma object would pass.
- **(d) `es|das` pronoun edge** — the A.3a/A.3b material-subject anchor includes the
  pronouns `es|das`; an unusual pronoun subject not in the set is not caught. Fail-closed
  (a missed match only *under*-blocks a rare phrasing; never over-blocks).
- **(e) L2 optimum anchor narrower than L1** — L2's `comparative_ranking` optimum anchor
  is tighter than L1's broad `(ideal|optimal|perfekt) für`; harmless while L1 ran first,
  but now that L2 is **enforced on the stream** it should be re-evaluated for parity.

### Next-up (document only — no time pressure, do NOT implement now)

1. **Semantic doctrine check as a denylist supplement** (strategic). A meaning-level
   suitability/ranking/release check that runs **before** the stream starts would both
   eliminate the (a) flash and subsume the lexical gaps (c)/(d)/(e). Larger design; needs
   its own plan + red-before-green + zero-FP corpus pass.
2. **E.1 scenario-replay of soft-transition phrasings** — the probabilistic routing
   surface (knowledge↔case soft transitions) is only *characterisable*, not deterministically
   fixable; replay-harness to measure misroute rate, not a lexical patch.

---

## Parked-items closeout — 2026-06-05

- **C10 manufacturer-response echo — SHIPPED + DEPLOYED to prod** (PR #84, merge `9615dd52`):
  wired the dead projection `manufacturer_response_echo_notes()` at the single funnel
  `RWDRCaseOrchestrator.build()` → `TechnicalRWDRRFQBrief.manufacturer_echo_notes` + a
  conditional brief section. `rag_supported`, never a confirmed fact, guard-scrubbed.
  Red-before-green; **doctrine-reviewer APPROVE**; backend pre-deploy gate EXIT=0;
  **prod DEPLOYED 2026-06-05** (digest `…@sha256:045c2c2f…`; rollback `…6d3c3826…`);
  `demo→main` carry #86 merged (`79f3ab66`, main ⊇ demo).
- **Branch strategy — DECIDED** (keep the demo-integration model; codified in
  `.claude/rules/ops.md`); was parked. CI-trigger / `ruff format` scope stays parked.
- **Keycloak — `registrationAllowed=false`** on realm `sealAI` (+ both seed exports);
  master-realm cleanup: master `jungt` deleted (runbook (b) premise corrected — it had a
  valid credential), `superadmin` rotated, recovery `test` deleted; end state only
  `superadmin`. Item (d) (`.env` `KEYCLOAK_ADMIN_PASSWORD`) left deliberately open (owner).
- Full detail + evidence: `docs/ops/GOVERNANCE_LOG.md` (2026-06-05T05:42Z) and
  `docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md`.

---

## Standing governance digest

- **Order:** doctrine (A + A.3) → C → B → D → F1/F2. C/B/D autonomous incl. deploy;
  F1/F2 autonomous to demo, HALT before prod.
- **Per-fix:** tight plan (root file:line, ACs, blast radius); define the concrete
  user repro and **verify against it** (lesson: audit sibling ≠ reported bug);
  red-before-green; zero-FP proof if a guard/lexicon is touched; atomic conventional
  commits; honest messages.
- **HALT to human** at: a change to live enforcement/streaming/mutation/runtime_contract
  before prod-deploy; a doctrine/security design decision; a test that would only pass
  by weakening a guard (never weaken — HALT); a real FP/regression/ambiguity that can't
  be cleanly resolved; live behavior contradicting tests; a finding outside the fix-map
  (log + surface, do not silently action).
- **Ops:** rollback anchor verified from the running daemon (`docker inspect backend`),
  never from memory. Commit → PR on `demo/rwdr-limited-external` (never `main`) →
  CI (`agent-bff-guardrails`) green → `gh pr merge --merge --delete-branch` → checkout
  demo + pull. Prod only via `ops/release-backend.sh` (backend only). Pre-deploy gate
  `cd backend && python -m pytest -q -rf` (exit code authoritative). Live acceptance +
  recorded live digest.
