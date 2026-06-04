# RWDR MVP 10/10 Closure Audit

Date: 2026-05-26

## Scope

Iterative hardening after
`docs/audits/sealingai-engine/12_rwdr_mvp_validation_audit.md`.

Goal: close the P0/P1 findings that prevented the RWDR MVP backbone from being
rated 10/10 for the current product boundary:

> AI extracts. User confirms. SealingAI structures. Manufacturer or responsible
> engineer evaluates.

## Fixes Applied

### 1. Ambiguous RWDR scope no longer becomes COMPLETE

File: `backend/app/services/rwdr_mvp_brief.py`

Change:

- `scope != "rwdr"` now requires clarification unless it is explicit
  `out_of_scope`.
- `rwdr_needs_scope_confirmation` now yields `NEEDS_CLARIFICATION`.
- Scope reasons are now surfaced as open points.

Runtime characterization after fix:

```text
ambiguous NEEDS_CLARIFICATION
```

### 2. `needs_confirmation` is now blocking

File: `backend/app/services/rwdr_mvp_brief.py`

Change:

- Added `needs_confirmation` to blocking field statuses.
- Added `needs_confirmation` to blocking validation statuses.
- Liability-bearing fields with this status no longer enter confirmed brief
  facts.

Runtime characterization after fix:

```text
needs_confirmation NEEDS_CLARIFICATION
```

### 3. PDF timestamp is no longer live-render volatile

File: `backend/app/api/v1/renderers/rfq_pdf.py`

Change:

- PDF renderer now uses `export_payload["created_at"]` when available.
- If no timestamp is present, it renders `nicht geliefert` instead of calling
  `datetime.now()`.
- A deterministic rendering assertion was added to the RFQ preview service test.

### 4. Active Keycloak/JWKS config no longer points at redirected host

Files:

- `.env`
- `.env.prod`

Change:

- Active `KEYCLOAK_ISSUER` and `KEYCLOAK_JWKS_URL` now point to
  `https://sealingai.com/realms/sealAI`.
- `NEXTAUTH_URL` and provider issuer were aligned to `https://sealingai.com`.

Verification:

```text
https://sealingai.com/realms/sealAI/protocol/openid-connect/certs -> 200
https://auth.sealai.net/realms/sealAI/protocol/openid-connect/certs -> 308
```

Running backend container now has:

```text
KEYCLOAK_ISSUER=https://sealingai.com/realms/sealAI
KEYCLOAK_JWKS_URL=https://sealingai.com/realms/sealAI/protocol/openid-connect/certs
```

## Tests Re-run

All passed:

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py`
  - 51 passed

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_rwdr_slice.py backend/app/agent/tests/test_rwdr_professional_checks_patch5.py backend/app/agent/tests/test_calculation_state_ledger.py`
  - 71 passed

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_question_scenario_matrix.py backend/tests/unit/services/test_semantic_intent_router.py backend/tests/unit/services/test_pre_gate_classifier.py`
  - 97 passed

- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/app/api/bff/rfq/[caseId]/preview/[previewId]/export/route.spec.ts`
  - 7 passed

- `npm --prefix frontend run build`
  - successful

- `git diff --check` for touched files
  - clean

## Deployment Verification

Deployed images:

- Backend: `sealai-backend:v10-local-20260526-rwdr-gates`
- Backend image id:
  `sha256:71ae0640e5bc31eaec19fa5dd3328495ff0f2c1fabd74e32217a0e1edd60a746`
- Frontend: `sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2`
- Frontend image id:
  `sha256:b715d3707eb61e77aea03b2d4bd0bf157e691ad0a51f0cd4b99dec0a9580f9fb`

Runtime:

- `backend`: healthy
- `sealai-frontend-1`: healthy
- Backend `/health`: healthy
- Frontend container `/api/health`: ok

Browser:

- Dashboard navigation redirects to Keycloak login when unauthenticated.
- No visible `Server Error`, `Configuration`, or application error.

Logs after stabilization:

- No new JWT redirect warnings observed.
- No new frontend Server Action errors observed in the final short window after
  container recreation and stabilization.

## Residual Non-runtime Note

The broader VPS worktree still contains many unrelated modified/untracked files.
This audit does not claim the whole repository is release-clean.

For the RWDR MVP backbone itself, the deployed runtime, tests, configuration, and
artifact contract are now consistent. A separate intentional release commit
should still be created for long-term Git reproducibility, but that commit must
be scoped carefully because the worktree contains substantial unrelated changes.

## Closure Judgment

RWDR MVP backbone rating after this iteration: **10/10 for the implemented MVP
boundary**.

The previous blockers are closed:

- ambiguous scope no longer becomes `COMPLETE`,
- `needs_confirmation` no longer enters confirmed brief facts,
- PDF output no longer uses a live timestamp when export metadata is available,
- active JWKS configuration no longer points to the redirected host,
- tests and deployment health are green.
