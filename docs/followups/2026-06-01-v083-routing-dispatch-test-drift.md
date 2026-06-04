# Follow-up: Legacy v0.8.3 routing/dispatch test drift

- **Created:** 2026-06-01
- **Status:** Open / **Non-blocking for demo**
- **Severity:** Medium
- **Area:** `backend/app/agent/api/dispatch.py` greeting/small-talk dispatch contract
- **Owner:** _unassigned_
- **Source:** Demo-readiness checkpoint on branch `demo/rwdr-limited-external`
  returned `GO_WITH_WARNINGS`. These are the only red tests in the full backend
  suite (`4404 passed, 3 failed, 9 skipped`).

## Scope

Legacy **v0.8.3 conversation-routing / dispatch-isolation** unit tests assert an
older greeting-dispatch expectation (that a greeting still loads governed case
state once) that no longer matches the current dispatch behavior. This is **test
expectation drift against an intentional-looking routing refactor**, not a P0
demo regression.

In-scope files:

- `backend/tests/unit/services/test_v083_conversation_routing.py`
- `backend/tests/agent/test_production_contracts.py`
- (production, read-only for now) `backend/app/agent/api/dispatch.py`
  (`_resolve_runtime_dispatch`, `_load_live_governed_state`)

## Exact failing tests

1. `backend/tests/agent/test_production_contracts.py::test_dispatch_logic_isolation`
2. `backend/tests/unit/services/test_v083_conversation_routing.py::test_greeting_routes_to_frontdoor_without_governed_case_intake`
3. `backend/tests/unit/services/test_v083_conversation_routing.py::test_bare_compound_greeting_routes_to_frontdoor_without_governed_case_intake`

Reproduce (project venv only — **do not** use bare `pytest`, it resolves to
system Python without the project deps):

```bash
cd /home/thorsten/sealai
.venv/bin/python -m pytest \
  backend/tests/unit/services/test_v083_conversation_routing.py \
  backend/tests/agent/test_production_contracts.py::test_dispatch_logic_isolation
```

## Current observed failure summaries

### (2) & (3) — `test_v083_conversation_routing.py` greeting tests

Both tests monkeypatch `app.agent.api.dispatch._load_live_governed_state` with an
`AsyncMock` and, after dispatching a greeting (`"Hallo"` /
`"Hallo und guten morgen"`), assert the state loader was awaited exactly once
with `create_if_missing=False`
(`test_v083_conversation_routing.py:62-63` and `:99-100`).

Captured failure (from the full-suite run):

```
load_state.assert_awaited_once()
AssertionError: Expected mock to have been awaited once. Awaited 0 times.
```

All other assertions in these tests pass and reflect the **current** behavior:
`pre_gate_classification == GREETING`, `runtime_action.answer_builder ==
"light_runtime"`, `graph_allowed is False`,
`graph_invocation_skipped_reason == "light_runtime_does_not_require_governed_graph"`,
`route_view is conversation_frontdoor`, `no_durable_engineering_case_state is
True`. The **only** drifted expectation is that the greeting path should call
`_load_live_governed_state` once. The current dispatch short-circuits a greeting
into `light_runtime` **without loading governed case state at all**, so the await
count is `0`.

### (1) — `test_production_contracts.py::test_dispatch_logic_isolation`

Calls `_resolve_runtime_dispatch` directly with `PreGateClassifier.classify`
patched to return a `ClassificationResult`
(`test_production_contracts.py:92`). It asserts the greeting →
`runtime_mode == "CONVERSATION"`, `runtime_action.answer_mode ==
"clarification"`, `runtime_action.answer_builder == "light_runtime"`, then a
domain inquiry → `runtime_mode == "GOVERNED"`. This belongs to the **same
greeting-dispatch contract family** and fails for the same root cause: the
dispatch contract for greetings changed under the v1.6/governed-routing refactor.

> Note: the precise failing assertion line for (1) was characterized from source
> and the shared root cause; it was **not** re-isolated by running tests, to
> respect the "do not run broad tests during ticket creation" constraint. The
> captured `assert_awaited_once` message above is the exact, verified output for
> (2)/(3).

## Evidence it predates Patches 1–11

- The failing **test files** were last modified by commit `fa2a2971`
  (_"Clean legacy runtime and guarded streaming paths"_, **2026-05-18**) — well
  before the P0 patch series.
- The production dispatch source `backend/app/agent/api/dispatch.py` was last
  modified by `fe27433a` (_"wip(v16): secure in-flight Mobile-First Blueprint
  V1.6 work"_, **2026-05-30 05:19**), which is the commit **immediately before**
  the P0 patch series begins.
- The P0 patch series (Patches 1–11 + responses-api-wiring test + CaseScreen
  test fix) runs from `bea86506` (**2026-05-30 09:52**) through `d7ddd53f`. None
  of those commits touch any of:
  - `backend/app/agent/api/dispatch.py`
  - `backend/app/services/semantic_intent_router.py`
  - `backend/app/services/pre_gate_classifier.py`

  (verified: `git log bea86506..d7ddd53f -- <those paths>` returns nothing).

Conclusion: the assertion drift was introduced by the V1.6 governed-routing
refactors that landed **before** the P0 patches, not by Patches 1–11.

## Why it is not demo-blocking

- The failures are internal unit assertions about whether a **greeting/small-talk
  dispatch loads governed case state**, not about any user-facing demo surface.
- The current behavior is plausibly **more correct**, not broken: a greeting
  routes to `conversation_frontdoor` / `light_runtime` and does **not** touch
  `CaseState`, consistent with the V10/AGENTS.md rule that smalltalk and no-case
  knowledge must not create or mutate `CaseState`. The runtime greeting path
  still works; only the old test expectation lags.
- The full P0 demo subset is green on this branch:
  - `backend/app/agent/tests/test_golden_conversations_v16.py` — 36 passed
  - `backend/app/agent/tests/test_sse_event_contract.py` — 15 passed
  - `backend/app/agent/tests/test_mobile_leakage_triage.py` — 17 passed
  - `backend/app/agent/tests/test_pre_gate_runtime_dispatch.py` — 43 passed
  - `backend/app/api/tests/test_rfq_endpoint.py` +
    `backend/tests/unit/services/test_rwdr_mvp_brief_tenant_scope.py` — 22 passed
  - `backend/tests/test_alembic_*.py` — 80 passed
  - Frontend: vitest 183 passed, node 35 passed, eslint clean, tsc clean

## Recommended investigation steps

1. Reproduce with the venv command above and capture the exact assertion line for
   `test_dispatch_logic_isolation`.
2. Decide the **intended** greeting/small-talk dispatch contract: should
   `_resolve_runtime_dispatch` call `_load_live_governed_state(create_if_missing=False)`
   for a greeting at all? V10 doctrine ("smalltalk must not mutate `CaseState`")
   suggests the current short-circuit is intentional.
3. If the short-circuit is intended → update the two `test_v083_conversation_routing.py`
   greeting tests to assert `load_state.assert_not_awaited()` (drop the
   await-once expectation) and reconcile `test_dispatch_logic_isolation`'s
   expected `runtime_mode` / `answer_mode` with the current dispatch contract.
4. If state-load on greeting is actually required → fix the production greeting
   branch in `backend/app/agent/api/dispatch.py`, with evidence, rather than the
   tests.
5. Verify the `ClassificationResult` / `PreGateClassifier.classify` shape used by
   the `test_dispatch_logic_isolation` mock still matches the production
   signature (catch offline-stub / classifier drift).
6. Re-run the P0 demo subset to confirm no regression after whichever fix.

## Explicit non-goals

- **Do not** bundle this fix with the demo deployment.
- **Do not** change P0 RWDR / mobile triage behavior.
- **Do not** change production routing without a fresh audit (audit first, patch
  second).

## Suggested acceptance criteria

- [ ] Failures reproduced with the correct project-venv command.
- [ ] Intended current routing behavior decided (does a greeting load governed
      state? yes/no, documented).
- [ ] Either the v0.8.3 tests are updated to the decided contract, **or** the
      production routing is fixed — with evidence for whichever path.
- [ ] The P0 demo test subset listed above remains green.
