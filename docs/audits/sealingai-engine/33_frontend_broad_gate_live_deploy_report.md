# 33 Frontend Broad Gate Live Deploy Report

Date: 2026-05-27

## Scope

Target branch: `demo/rwdr-limited-external`

Deploy worktree: `/home/thorsten/sealai-rwdr-demo-deploy`

Final deployed commit: `2303261e2ab8cafac68569987ec5f80979e7c22d`

## 1. Frontend Failures vorher

Reproduced in the fresh deploy worktree with:

```bash
npm --prefix frontend run test:run
```

Failing files:

- `frontend/src/components/dashboard/CaseScreen.test.tsx`
- `frontend/src/components/dashboard/ChatComposer.test.tsx`
- `frontend/src/components/dashboard/ChatPane.test.tsx`

Failing tests / assertions:

- `CaseScreen.test.tsx` / `maps a real workspace fixture into the RFQ workspace view`
  - Expected stale text matching `72 % geklärt`.
  - Current UI renders the cockpit/RFQ workspace with tabs, direct intake, known parameter form, open points, and calculation sections.
- `ChatComposer.test.tsx` / `renders the ChatGPT-style composer controls`
  - Expected accessible controls for `Antwortlänge`, `Spracheingabe`, and disabled `Sprachmodus`.
  - Current composer did not expose those labels/controls.
- `ChatPane.test.tsx` / `places message identity icons above the related text`
  - Expected stable avatar test ids and identity/icon ordering.
  - Current pane rendered icons without stable test ids; the user-avatar order expectation was inverted for the current DOM.
- `ChatPane.test.tsx` / `places the composer in a Gemini-style first-run state with sealing prompts`
  - Expected the hero first-run copy without the older secondary greeting.
  - Current UI still rendered `Schön, dass du wieder hier bist.`
- `ChatPane.test.tsx` / `renders a restrained streaming placeholder before text chunks arrive`
  - Expected `thinking-indicator`.
  - Current placeholder had no stable test id.

Classification:

- `CaseScreen`: RWDR/dashboard fixture expectation drift.
- `ChatComposer`: chat UI accessibility/control drift.
- `ChatPane`: chat/SSE UI testability and copy drift.
- No RWDR backend logic regression was found in these failures.

## 2. Root Cause

The broad frontend suite was red because frontend UI and tests had drifted:

- One RFQ workspace test still asserted an obsolete progress-strip copy instead of the current cockpit/RFQ workspace layout.
- Chat composer controls lacked stable accessible labels required by the existing UI contract.
- Chat pane tests relied on avatar test ids and streaming placeholder ids that the current markup did not provide.
- The hero copy and one DOM order assertion were stale relative to the intended current UI.

During Docker build validation two additional deployment blockers appeared:

- Frontend stream request types did not include the current `conversationId` / `turnId` aliases used by the BFF route.
- Backend runtime imported redacted LangSmith observation-span helpers that were absent from `backend/app/observability/langsmith.py`, causing the backend container to restart.
- The frontend container did not receive auth/Keycloak server environment in `docker-compose.deploy.yml`, causing unauthenticated BFF RWDR smoke to return `500 auth_error` instead of the expected auth gate.

## 3. Fix

Committed fixes:

- `2b96425b2abb7bef442cda8427a64feb93a9c60e`
  - `test(frontend): stabilize rwdr demo broad gate`
  - Added missing ChatComposer accessible controls/labels.
  - Added stable ChatPane avatar and thinking-indicator test ids.
  - Removed stale secondary hero copy.
  - Updated CaseScreen/ChatPane tests to match current intended UI.
- `01b4668e`
  - `fix(frontend): type stream turn id aliases`
  - Aligned BFF stream route typing with current turn id alias handling.
- `064b226d`
  - `fix(frontend): align stream request contract`
  - Added optional `conversationId`, `turnId`, and `turn_id` to `AgentStreamRequest`.
- `e451a1780523703266a37465f5735c4808bb39ef`
  - `fix(backend): restore redacted langsmith span helper`
  - Restored the minimal redacted observation-span helper expected by runtime imports.
- `2303261e2ab8cafac68569987ec5f80979e7c22d`
  - `fix(deploy): pass auth env to frontend container`
  - Passed required auth/Keycloak server environment into the frontend container without changing product behavior.

No RWDR Fachlogik, Evidence Gate, Confirmation UX, Manufacturer Routing, Marketplace, material/product recommendation, or production migration was changed.

## 4. Commit Hash

Final runtime/deploy commit:

```text
2303261e2ab8cafac68569987ec5f80979e7c22d
```

## 5. Push Status

Pushed to:

```text
origin/demo/rwdr-limited-external
```

Remote and deploy worktree both resolved to `2303261e2ab8cafac68569987ec5f80979e7c22d`.

## 6. Deploy Worktree Commit

After final sync:

```text
2303261e (HEAD, origin/demo/rwdr-limited-external) fix(deploy): pass auth env to frontend container
```

Deploy worktree status was clean before deploy.

## 7. Gate Ergebnis

Final full deploy-worktree gate:

```bash
PYTHON_BIN=/home/thorsten/sealai/.venv/bin/python bash scripts/check_rwdr_mvp_demo.sh
```

Result:

- RWDR golden cases: 13 passed.
- RWDR/RFQ backend focused suite: 86 passed, 1 known deprecation warning.
- RWDR frontend focused suite: 3 files passed, 16 tests passed.
- Frontend broad suite: 27 files passed, 150 tests passed.
- `git diff --check`: clean.
- Forbidden-language scan: known historical/test/documentation hits were printed by the gate; no new RWDR customer-facing blocker was introduced by this patch set.

Additional focused verification:

- `PYTHONPATH=backend /home/thorsten/sealai/.venv/bin/python -m pytest -q backend/tests/unit/observability/test_langsmith_helpers.py`: 8 passed.
- `npm --prefix frontend run build`: passed before frontend image build.

## 8. Deploy-Befehl

Executed from `/home/thorsten/sealai-rwdr-demo-deploy`:

```bash
docker compose --env-file /home/thorsten/sealai/.env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml build backend frontend
docker build -t sealai-backend:v10-local-20260526-rwdr-gates -f backend/Dockerfile backend
docker build -t sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2 -f frontend/Dockerfile frontend
docker compose --env-file /home/thorsten/sealai/.env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml up -d backend frontend
```

Note: Compose reported `No services to build` because the deploy compose file uses pinned image references. Local Docker builds were run against the clean deploy worktree and the pinned local tags were then used by Compose.

After the auth-env deploy-config commit:

```bash
docker compose --env-file /home/thorsten/sealai/.env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml build backend frontend
docker compose --env-file /home/thorsten/sealai/.env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml up -d backend frontend
```

No `docker compose down`, `docker prune`, volume deletion, or migration command was executed.

## 9. Container Status

Final status:

```text
backend             sealai-backend:v10-local-20260526-rwdr-gates                    Up healthy   127.0.0.1:8000->8000/tcp
sealai-frontend-1   sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2  Up healthy   3000/tcp
nginx               nginx:1.29.4                                                     Up healthy   0.0.0.0:80/443
keycloak            ghcr.io/jungt72/sealai-keycloak:2026.05.14-1                    Up
```

Build/container proof:

```text
backend image id:  sha256:71c267a7af84981cbf4329e3840c93ed56464ed42460442a7626f7da80872f2a
frontend image id: sha256:970a1d00ce1afdbb522dc8685bc93c06ce8703180372cb1720b9562b7954cfb3
```

## 10. Health Results

```text
curl -I https://sealingai.com
HTTP/2 200

curl -s https://sealingai.com/api/health
{"status":"ok"}

curl -s https://sealingai.com/api/agent/health
{"status":"ok","service":"SSoT Agent Authority"}

curl -s http://127.0.0.1:8000/api/agent/health
{"status":"ok","service":"SSoT Agent Authority"}

curl -s http://127.0.0.1:8000/api/v1/ping
{"pong":true}
```

## 11. RWDR Analyze local direct

Request:

```bash
curl -s -o /tmp/rwdr_direct_response.txt -w "%{http_code}" \
  -X POST http://127.0.0.1:8000/api/v1/rfq/rwdr/analyze \
  -H 'Content-Type: application/json' \
  -d '{"raw_inquiry":"Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend."}'
```

Result:

```text
401
{"detail":"Authorization header fehlt oder ungültig"}
```

Conclusion: route is mounted and no longer returns 404. Local direct is auth-gated.

## 12. RWDR Analyze public direct

Request:

```bash
curl -s -o /tmp/rwdr_public_direct_response.txt -w "%{http_code}" \
  -X POST https://sealingai.com/api/v1/rfq/rwdr/analyze \
  -H 'Content-Type: application/json' \
  -d '{"raw_inquiry":"Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend."}'
```

Result:

```text
401
{"detail":"Authorization header fehlt oder ungültig"}
```

Conclusion: public direct route is present and auth-gated, not 404.

## 13. BFF Auth Gate

Request:

```bash
curl -s -o /tmp/rwdr_bff_unauth_response.txt -w "%{http_code}" \
  -X POST https://sealingai.com/api/bff/rfq/rwdr/analyze \
  -H 'Content-Type: application/json' \
  -d '{"rawInquiryText":"Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend."}'
```

Result:

```text
401
{"error":{"code":"auth_error","message":"Unauthorized"}}
```

Conclusion: BFF RWDR analyze exists, is not 404, and is auth-gated for unauthenticated requests.

## 14. Remaining Blockers

No deployment-blocking issue remains for the RWDR demo gate.

Residual non-blocking notes:

- Direct RWDR analyze requires authentication. The smoke only proves route mount and auth-gating, not an authorized end-to-end analysis body.
- The gate's forbidden-language scan still prints known historical/test/documentation/internal hits. These were pre-existing and not introduced by this patch set.
- Compose deploy image tags remain historical local tag names. Runtime proof is therefore based on clean deploy worktree commit, local image build timestamps/ids, and container health, not image tag naming.

## 15. Next Step

Run an authenticated RWDR analyze smoke with a real session/token and capture only redacted evidence of:

- HTTP status.
- `Technical RWDR RFQ Brief` response shape.
- Evidence-confirmation/open-point behavior.
- No recommendation or final suitability wording.
