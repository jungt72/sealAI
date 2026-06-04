# LLM Answer Quality And Token Expiry Audit

Date: 2026-05-27
Branch: `demo/rwdr-limited-external`
Repo: `/home/thorsten/sealai`

## Scope

Audit target: sudden `expired token` failures and degraded LLM answer quality for PTFE/FKM knowledge answers, SBB/RWDR case handling, repeated content, German tone consistency, and explicit RWDR challenge mode.

Boundary respected: no manufacturer routing, no material recommendation, no final suitability/release wording, no evidence-gate weakening, no production migration, no deploy.

## Discovery Commands

- `pwd` -> `/home/thorsten/sealai`
- `git status --short` -> repository already had many modified/untracked files before this audit; changes were not reset.
- `git branch --show-current` -> `demo/rwdr-limited-external`
- `rg -n "expired|refresh|accessToken|idToken|refresh_token|Keycloak|NextAuth|Authorization|Bearer|401|403|token" frontend backend`
- `rg -n "answer_composer|final_answer|FinalAnswer|composer|communication_runtime|conversation_runtime|governed_answer|knowledge_answer|fallback|duplicate|response|assistant_message|answer_markdown|Technical RWDR|RWDR" backend frontend`
- `rg -n "PTFE|FKM|Salzwasser|SBB|Druckluft|RWDR|Radialwellendichtring|challenge|stumpfe Parameterabfrage" backend frontend docs || true`

## Root-Cause Hypotheses

### Expired Token

Confirmed root cause: the frontend already stores and refreshes Keycloak tokens, but the BFF stream route did not retry a backend request when the backend rejected a bearer token as expired after the BFF had considered it locally usable.

Evidence:

- NextAuth stores `accessToken`, `idToken`, `refreshToken`, and `expiresAt` in JWT/session callbacks: `frontend/src/auth.ts:124-143`, `frontend/src/auth.ts:149-156`.
- NextAuth refreshes with Keycloak `refresh_token`: `frontend/src/auth.ts:53-83`.
- BFF can refresh expired tokens before calls, using `expiresAt` and a 30 s buffer: `frontend/src/lib/bff/auth-token.ts:178-184`, `frontend/src/lib/bff/auth-token.ts:286-310`.
- Backend normalizes expired JWTs to `token_expired` and returns HTTP 401 through the auth dependency: `backend/app/services/auth/token.py:125-135`, `backend/app/services/auth/dependencies.py:159-166`.
- Before this patch, `frontend/src/app/api/bff/agent/chat/stream/route.ts` mapped the 401 to a UI message but did not force-refresh and retry the stream request.

Likely trigger: clock skew, token lifetime race, or backend-side stricter JWT validation after the BFF-side local `expiresAt` check.

### LLM Answer Quality / Duplicate Answers

Root cause is mixed and only partly fixed:

- Knowledge composer prompt encouraged broad material-comparison depth but did not constrain PTFE vs FKM to compact sealing decision axes. This can produce long, generic answers instead of a sealing-intelligence comparison.
- Governed answer composer had challenge findings/hypotheses support but did not explicitly preserve user instructions like "challenge den Fall" / "keine stumpfe Parameterabfrage" as an answer mode.
- BFF intentionally synthesizes `answer.token` events from final `state_update` text and then forwards the `state_update`. The hook replaces the streaming text with final text and finalizes once, so this is not proven as a frontend duplicate-render root cause. Relevant paths: `frontend/src/app/api/bff/agent/chat/stream/route.ts:440-465`, `frontend/src/hooks/useAgentStream.ts:491-505`, `frontend/src/hooks/useAgentStream.ts:329-362`.
- Broad backend suite failures show existing routing/graph drift in unrelated or pre-existing areas, including knowledge composer passthrough/debug behavior and governed graph dispatch tests. These are risks for real chat quality but were not safely attributable to this patch.

## Answer Quality Errors Observed

- PTFE vs FKM can become encyclopedia-like instead of a precise comparison of Fluorpolymer vs Elastomer.
- Explicit challenge instructions were not hard-coded into the governed composer contract, so the answer could collapse into a standard next-slot question.
- Existing prompt contracts already ban routine thanks and final suitability wording, but this needed stronger task-shape guidance for challenge cases.
- The codebase contains no verified single root cause for duplicated SBB/RWDR answer blocks. The likely suspects remain backend assembly/fallback plus frontend synthetic final streaming, but direct duplicate rendering is guarded by `finalizedRequestIdRef` and last-message equality.

## Token-Expiry Error Path

1. Frontend session stores Keycloak token data: `frontend/src/auth.ts:124-143`.
2. BFF reads Auth.js JWT cookie and returns locally usable token if `expiresAt` is still outside the 30 s buffer: `frontend/src/lib/bff/auth-token.ts:286-300`.
3. BFF calls backend stream with `Authorization: Bearer ...`: `frontend/src/app/api/bff/agent/chat/stream/route.ts:300-315`.
4. Backend verifies JWT and raises `token_expired`: `backend/app/services/auth/token.py:125-135`.
5. Backend auth dependency returns 401: `backend/app/services/auth/dependencies.py:159-166`.
6. Before patch: BFF returned controlled 401 but did not retry.
7. After patch: BFF detects backend auth expiry, force-refreshes, retries once, persists rotated cookies, and only returns re-login if retry/refresh fails: `frontend/src/app/api/bff/agent/chat/stream/route.ts:289-360`.

## Implemented Small Fixes

- Added `forceRefresh` support to BFF token retrieval so a locally-valid token can still be refreshed after backend expiry rejection: `frontend/src/lib/bff/auth-token.ts:31-32`, `frontend/src/lib/bff/auth-token.ts:286-310`.
- Added one retry in the BFF SSE stream route on backend `401` with token-expiry-like details: `frontend/src/app/api/bff/agent/chat/stream/route.ts:289-360`.
- Kept UI-facing auth error sanitized as a re-login message; no token details are exposed: `frontend/src/app/api/bff/agent/chat/stream/route.ts:265-276`.
- Tightened knowledge composer prompt for PTFE-vs-FKM axes and anti-encyclopedia behavior: `backend/app/agent/prompts/knowledge/answer_composer.j2:15-18`.
- Added material-comparison depth/breadth validation and repair path for over-broad PTFE/FKM answers: `backend/app/agent/communication/answer_composer.py:142-164`, `backend/app/agent/communication/answer_composer.py:334-356`.
- Tightened governed composer challenge-mode instructions: `backend/app/agent/prompts/governed/answer_composer.j2:28-30`, `backend/app/agent/prompts/governed/answer_composer.j2:47-50`.

## Tests Added / Updated

- `frontend/src/lib/bff/http.test.ts`: force-refresh path for backend-expired token retries.
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`: retry once after backend token expiry and preserve rotated session cookie.
- `backend/app/agent/tests/test_knowledge_answer_composer.py`: PTFE/FKM prompt axes and over-broad answer rejection.
- `backend/app/agent/tests/test_governed_answer_composer.py`: governed prompt preserves explicit case-challenge mode.

## Test Results

Green:

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_knowledge_answer_composer.py backend/app/agent/tests/test_governed_answer_composer.py`
  - 65 passed.
- `npm --prefix frontend run test:run -- src/app/api/bff/agent/chat/stream/route.spec.ts src/hooks/useAgentStream.test.tsx src/lib/bff/http.test.ts`
  - Vitest reported 2 files, 29 tests passed. Note: `src/lib/bff/http.test.ts` is Node test style and is not counted by Vitest.
- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx src/hooks/useAgentStream.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts`
  - 5 files, 51 tests passed.
- `git diff --check`
  - passed.

Failed / pre-existing broader-suite drift:

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/tests/unit/services backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py`
  - failed with 11 failures.
  - Representative failures:
    - `backend/app/agent/tests/graph/test_normalize_node.py::TestNoLLM::test_openai_never_called` expected 3 normalized parameters but got 4 due `ambiguous_pressure_bar`.
    - `backend/app/agent/tests/test_knowledge_debug_trace.py` expected composer path/debug source but got no captured request / `reply_passthrough`.
    - several `backend/app/agent/tests/test_phase_f_streaming_cut.py` governed-path authority expectations failed.
    - `backend/app/agent/tests/test_turn_context.py` open-points summary expectation failed.
    - `backend/app/agent/tests/test_v7_runtime_dispatch.py` expected mocked graph path answer but got empty answer markdown.
    - `backend/app/agent/tests/v92/test_v92_orchestrator.py` expected ready/review actions but got missing-input paths.

Forbidden-language scan:

- `rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs`
  - returned many hits in tests, forbidden-phrase fixtures, legacy docs, internal workflow states, and knowledge source data. This audit did not classify every hit; prior audit files already note this as legacy/internal vocabulary risk.

## Recommended Fixes

Priority A:

- Add backend-visible answer-mode metadata for explicit case challenge, not just prompt text. The router/dispatch should carry a value like `technical_case_challenge` into `GovernedAnswerContext`.
- Add deterministic RWDR challenge assembly for concrete cases before LLM wording: d1/D/b, medium, temperature, pressure, rpm, surface speed, pressure/speed flags, counterface/runout, missing critical fields, review flags, next best question.
- Add a backend integration test with the exact Salzwasser/RWDR challenge prompt and assert the required section shape.
- Investigate broad backend suite failures before relying on the current governed graph path for SBB/RWDR production quality.

Priority B:

- Add response-level duplicate block detection in backend final assembly: compare `reply`, `answer_markdown`, deterministic fallback, and composer output before emitting.
- Add frontend event-id/turn-id de-duplication when backend starts emitting stable IDs.
- Add German tone lint for mixed `du`/`Sie` in final visible answers.

## Remaining Risks

- This patch improves prompt/control surfaces but does not prove the full SBB/RWDR case is always processed as a `Technical RWDR RFQ Brief`.
- The broad backend suite currently fails, including routing/graph/knowledge-debug tests that can affect answer quality.
- The BFF stream retry covers startup 401 before streaming begins. It does not refresh mid-stream if the backend closes an already-open stream due to auth expiry.
- Forbidden-language scan still returns many legacy/internal hits. They are not necessarily user-facing, but the scan is not clean.
- The repo was dirty before this audit; only the files above were intentionally touched for this task.

