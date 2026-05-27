# RWDR Demo Commit / Deploy Verification Report

Date: 2026-05-27

## 1. Git Ausgangszustand

- Start branch: `redesign/sealai-cockpit-overview`
- Start HEAD: `97e32a9f64568ff728757e309a711d2ebf3be777`
- Start upstream: `origin/redesign/sealai-cockpit-overview`
- Start state: dirty worktree with mixed RWDR demo files and unrelated V10/Graph/Legacy drift.
- Safety artifacts created locally under `_release_backups/rwdr_demo_release/` and intentionally not committed.
- `.codex` was tracked and accidentally deleted in the worktree; it was restored and not committed.
- One untracked AppleDouble file, `paperless/data/log/.__paperless.lock`, was removed.

## 2. Branch

- Release branch: `demo/rwdr-limited-external`
- Branch base: `97e32a9f64568ff728757e309a711d2ebf3be777`
- Upstream after push: `origin/demo/rwdr-limited-external`

## 3. Commit Hash

- Commit: `f1f11626dc1d28423b76996e2ade410055e68c10`
- Message: `feat(rwdr): prepare limited external demo`

## 4. Staged Dateien

The committed scope contains RWDR MVP backend/API/export code, RWDR tests and fixtures, frontend RWDR/BFF routes, RFQ dashboard components, guided-demo documentation, and release hygiene files.

Explicitly excluded from the commit:

- broad `backend/app/agent/**` V10/Graph/Legacy drift
- agent stream/BFF changes outside RWDR
- marketing/page design changes
- `_deploy_backups/`
- `_release_backups/`
- local `.env*` files and credential-like files
- `.codex`
- AppleDouble files

## 5. Nicht gestagte Restdateien

The worktree remains intentionally dirty after the RWDR demo commit. Remaining files are unrelated or not proven necessary for the limited external RWDR demo branch, including:

- V10/Graph/agent runtime and test drift under `backend/app/agent/**`
- semantic router and knowledge-service drift outside the RWDR demo gate
- frontend chat/stream/dashboard shell and marketing/layout drift
- package/lockfile and nginx/deploy-compose drift
- local `_deploy_backups/` and `_release_backups/`
- untracked broader audit notes `docs/audits/sealingai-engine/01_...09_...`
- untracked V10 concept doc
- untracked brand and stream-workspace adapter files

## 6. Tests/Gates

Passed:

- `bash scripts/check_rwdr_mvp_demo.sh`
- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py`
- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py`
- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts`
- `npm --prefix frontend run test:run`
- `git diff --check`
- staged secret/path hygiene checks

Forbidden-language scan:

- Command executed across `backend frontend docs`.
- New RWDR-relevant hits were classified as guard test data, golden-case forbidden phrase fixtures, explicit forbidden-language documentation, audit command records, or internal status vocabulary.
- No customer-facing RWDR must-fix hit was identified in the committed scope.

## 7. Push Ergebnis

- SSH auth succeeded for GitHub user `jungt72`.
- Push command: `git push -u origin demo/rwdr-limited-external`
- Local HEAD: `f1f11626dc1d28423b76996e2ade410055e68c10`
- Upstream HEAD: `f1f11626dc1d28423b76996e2ade410055e68c10`
- Ahead/behind after push: none.

## 8. Deploy-Mechanismus

Observed mechanisms:

- `docs/runbook_stack.md` documents `./ops/up-prod.sh` as the canonical backend/keycloak production restart path.
- `ops/up-prod.sh` deploys pinned production images from `.env.prod` and starts backend/keycloak/gotenberg/tika, then refreshes nginx.
- `ops/release-backend.sh` can build and push a backend image and update `.env.prod`.
- `ops/release-frontend.sh` and `frontend/scripts/deploy.sh` target PM2-based frontend deployment.
- Actual runtime showed a Docker frontend container (`sealai-frontend-1`) rather than a `sealai-frontend` PM2 process.

Conclusion: deploy mechanism for this combined backend + frontend RWDR demo branch is not unambiguous. Backend-only deploy would not deploy the new frontend/BFF/RFQ UI changes, and the documented frontend PM2 path does not match the observed running frontend container.

## 9. Deploy Ergebnis

- Deploy was not executed.
- Reason: deploy mechanism is unclear for the complete RWDR demo branch, and the request forbids deploy when gates or staging/deploy safety are unclear.
- No production migrations were run.
- No `.env.prod` changes were made.

## 10. Live Health Checks

Local:

- `http://127.0.0.1:8000/health`: healthy
- `http://127.0.0.1:8000/api/health`: not found
- `http://127.0.0.1:3000`: not reachable directly from host
- `http://127.0.0.1:8080`: not reachable directly from host

Public:

- `https://sealingai.com`: HTTP 200
- `https://sealingai.com/api/health`: `{"status":"ok"}`
- `https://sealingai.com/api/agent/health`: `{"status":"ok","service":"SSoT Agent Authority"}`

## 11. RWDR Smoke Test

- Local `POST /api/v1/rfq/rwdr/analyze`: `404 Not Found`
- Public `POST /api/v1/rfq/rwdr/analyze`: `404 Not Found`

Result: live RWDR smoke test could not verify the new RWDR demo flow because the running environment does not expose the new endpoint.

## 12. Live Commit Nachweis

- No live commit endpoint was found or verified.
- Running backend image: `sealai-backend:v10-local-20260526-rwdr-gates`
- Running frontend image: `sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2`
- These image tags do not prove the live runtime is `f1f11626dc1d28423b76996e2ade410055e68c10`.

Conclusion: Kein Live-Commit-Nachweis vorhanden.

## 13. Restblocker

- Full-app release remains not ready due to unrelated V10/Graph/Legacy drift and dirty worktree state.
- Deploy path for a combined backend + frontend RWDR demo branch must be clarified.
- Live environment does not expose the new RWDR analyze endpoint.
- No live commit/version endpoint is available for deterministic runtime provenance.

## 14. Nächster Schritt

Define a safe deploy path for `demo/rwdr-limited-external` that handles both backend and frontend artifacts from the same commit, then deploy that exact commit and rerun live RWDR smoke plus commit provenance verification.
