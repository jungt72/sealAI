# RWDR MVP Validation Audit

Date: 2026-05-26

## Scope

Read-only validation of the RWDR MVP rebuild after the `Technical RWDR RFQ Brief`
was added to backend, PDF export, frontend RFQ panel, deployment image pins, and
SSoT documentation.

This audit did not change production logic. It validates whether the current
implementation matches the product boundary:

> AI extracts. User confirms. SealingAI structures. Manufacturer or responsible
> engineer evaluates.

## Validated Architecture Path

### Source of truth

- `AGENTS.md` defines the active RWDR MVP boundary and artifact title.
- `docs/audits/sealingai-engine/11_rwdr_mvp_implementation_report.md` reflects
  that backend, export, PDF, frontend panel, and tests are implemented.

### Backend path

- `backend/app/services/rwdr_mvp_brief.py`
  - Defines `technical_rwdr_rfq_brief`.
  - Defines only three statuses: `COMPLETE`, `NEEDS_CLARIFICATION`,
    `OUT_OF_SCOPE`.
  - Separates confirmed case fields from deterministic calculation fields.
  - Sets:
    - `no_final_technical_release=True`
    - `dispatch_enabled=False`
    - `manufacturer_matching_enabled=False`

- `backend/app/services/rfq_preview_service.py`
  - Builds `technical_rwdr_rfq_brief` during RFQ preview payload creation.
  - Embeds it into both `payload["rfq_preview"]` and top-level payload.
  - Includes the brief in the allowlisted export contract.

- `backend/app/api/v1/renderers/rfq_pdf.py`
  - Renders only the allowlisted RFQ export content.
  - Includes the `Technical RWDR RFQ Brief` section in generated PDF output.

- `backend/app/api/v1/endpoints/rfq.py`
  - PDF endpoint returns `application/pdf`.
  - Preserves no-dispatch/no-external-contact/no-final-release headers.

### Frontend path

- `frontend/src/components/dashboard/RfqPane.tsx`
  - Reads `technical_rwdr_rfq_brief` from backend payload.
  - Does not infer manufacturer ranking or material release in the frontend.
  - Displays:
    - status,
    - final release boundary,
    - manufacturer matching state,
    - confirmed facts,
    - calculations,
    - open points.

## Deployment Validation

Resolved images:

- Backend: `sealai-backend:v10-local-20260521-rfq-pdf`
- Frontend: `sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2`

Container state:

- `backend`: healthy
- `sealai-frontend-1`: healthy

Runtime checks:

- Backend `/health`: healthy
- Frontend container `/api/health`: ok
- Browser state: current in-app browser is on Keycloak login, no visible server
  error or configuration error.

## Test Evidence

Executed successfully:

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rfq_preview_service.py backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rfq_endpoint.py`
  - 49 passed

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_rwdr_slice.py backend/app/agent/tests/test_rwdr_professional_checks_patch5.py backend/app/agent/tests/test_calculation_state_ledger.py`
  - 71 passed

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_question_scenario_matrix.py backend/tests/unit/services/test_semantic_intent_router.py backend/tests/unit/services/test_pre_gate_classifier.py`
  - 97 passed

- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx`
  - 6 passed

- `npm --prefix frontend run test:run -- src/app/api/bff/rfq/[caseId]/preview/[previewId]/export/route.spec.ts`
  - 1 passed

- `npm --prefix frontend run build`
  - successful

## Findings

### P0 - Ambiguous RWDR scope can still become COMPLETE

File: `backend/app/services/rwdr_mvp_brief.py`

Evidence:

- `_rwdr_scope()` can return `rwdr_needs_scope_confirmation`.
- Status selection only checks:
  - `scope == "out_of_scope"` -> `OUT_OF_SCOPE`
  - `missing_semantics or blocked_fields` -> `NEEDS_CLARIFICATION`
  - otherwise -> `COMPLETE`

Observed characterization:

```text
status: COMPLETE
scope: rwdr_needs_scope_confirmation
complete_enough: True
out_of_scope_reasons: ["RWDR-Bezug ist noch nicht eindeutig bestaetigt."]
open_points: []
```

Impact:

The artifact can claim manufacturer-evaluation completeness while the RWDR MVP
scope itself is not confirmed. That violates the explicit MVP boundary.

Required fix:

- Treat `rwdr_needs_scope_confirmation` as `NEEDS_CLARIFICATION`.
- Add an explicit open point for RWDR scope confirmation.
- Add a regression test proving that complete technical fields are not enough
  when the RWDR scope is ambiguous.

### P0 - `needs_confirmation` status is not blocking by itself

File: `backend/app/services/rwdr_mvp_brief.py`

Evidence:

- `_BLOCKING_FIELD_STATUSES` does not include `needs_confirmation`.
- `_BLOCKING_VALIDATION_STATUSES` does not include `needs_confirmation`.

Observed characterization:

```text
status: COMPLETE
confirmed_medium:
  field: medium_name
  status: needs_confirmation
  validation_status: needs_confirmation
  allowed_in_brief: True
blocked: []
```

Impact:

A liability-bearing field can enter confirmed brief facts even though its status
says it still needs confirmation, unless `confirmation_required=True` or another
blocking status is also present. This is too weak for a governed RFQ brief.

Required fix:

- Add `needs_confirmation` to blocking field and validation statuses.
- Add a regression test for `status=needs_confirmation` with
  `confirmation_required=False`.

### P1 - PDF bytes are not deterministic because export time is rendered live

File: `backend/app/api/v1/renderers/rfq_pdf.py`

Evidence:

- `_build_rfq_lines()` uses `datetime.now(timezone.utc)` for
  `Export erzeugt`.

Impact:

This is acceptable for a user-visible generated export timestamp, but the PDF is
not byte-for-byte deterministic. It must not be used as the canonical seal hash
unless the timestamp is supplied from the frozen export metadata.

Required fix:

- Prefer export metadata timestamp when present.
- Keep live timestamp only as a fallback.
- Do not include volatile PDF bytes in the deterministic decision-basis hash.

### P1 - Deployment is healthy, but release state is not version-clean

Evidence:

- VPS worktree contains many modified and untracked files.
- Core new MVP files are still untracked in git.

Impact:

Runtime is healthy, but exact rebuild reproducibility is not yet release-grade.
A future deploy from git alone would not reproduce this state.

Required fix:

- Stage and commit the intentional MVP files.
- Remove AppleDouble `._*` files after explicit cleanup approval.
- Keep unrelated dirty work separated from the RWDR MVP release commit.

### P2 - Frontend logs show stale Server Action requests after deployment

Evidence:

Frontend container logs contain repeated:

```text
Failed to find Server Action "x". This request might be from an older or newer deployment.
```

Impact:

The app is healthy and the logged errors are consistent with stale browser tabs
after a new Next.js deployment. Still, this should be monitored because users
with old tabs may see failed interactions after deployments.

Required fix:

- Add a client-visible stale-build recovery pattern or force reload strategy.
- Track frequency after the next clean deployment.

### P2 - Backend JWT verification uses a redirected JWKS URL

Evidence:

Backend logs showed:

```text
JWT verify failed: Redirect response '308 Permanent Redirect'
for url 'https://auth.sealai.net/realms/sealAI/protocol/openid-connect/certs'
Redirect location: 'https://sealingai.com/realms/sealAI/protocol/openid-connect/certs'
```

Impact:

The backend is healthy, but authenticated API calls may intermittently fail or
pay avoidable latency if JWT verification is configured against a redirected
issuer/certs URL.

Required fix:

- Set the backend Keycloak/JWKS configuration to the canonical URL that does not
  redirect.
- Add a deployment check that fetches the JWKS URL with no 3xx response.

## Audit Conclusion

The implemented architecture is on the right target line: backend-owned brief,
allowlisted export, PDF rendering, frontend display, no dispatch, no matching,
and no final release language are now wired together.

However, the rebuild is not yet a 10/10 governance backbone because two
deterministic gating edge cases can incorrectly produce `COMPLETE`.

Next patch should be narrow:

1. Fix ambiguous RWDR scope status handling.
2. Block `needs_confirmation` as a liability-bearing status.
3. Add regression tests for both edge cases.
4. Re-run the existing focused backend/frontend suite.
5. Then create a clean release commit or equivalent immutable deployment record.
