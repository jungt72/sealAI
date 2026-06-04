# RWDR Confirmation UX Report

Datum: 2026-05-27

## Discovery Commands

- `pwd` -> `/home/thorsten/sealai`
- `git status --short` -> dirty worktree with many pre-existing backend/frontend/docs changes.
- `git branch --show-current` -> `redesign/sealai-cockpit-overview`
- `rg --files backend frontend docs | rg -i 'rwdr|rfq|RfqPane|ManufacturerFitPanel|unsafeProductCopy|route|endpoint' | sort`

## Relevant Files

- Backend domain: `backend/app/services/rwdr_mvp_brief.py`
- Backend RFQ API: `backend/app/api/v1/endpoints/rfq.py`
- Backend RFQ preview: `backend/app/services/rfq_preview_service.py`
- Frontend BFF helpers: `frontend/src/lib/bff/workspace.ts`
- Frontend BFF routes:
  - `frontend/src/app/api/bff/rfq/rwdr/analyze/route.ts`
  - `frontend/src/app/api/bff/rfq/rwdr/brief/route.ts`
- Frontend UI: `frontend/src/components/dashboard/RfqPane.tsx`
- Frontend tests: `frontend/src/components/dashboard/RfqPane.test.tsx`

## UX Flow Implemented

1. User pastes a RWDR inquiry in `RfqPane`.
2. UI calls RWDR analyze endpoint.
3. Backend returns deterministic extraction candidates with `origin`, `confirmation_status`, `source_span`, `liability_bearing`.
4. UI renders liability-bearing fields with value, unit, exact source span, origin and status.
5. User can choose `Bestätigen`, `Bearbeiten`, `Nicht angegeben / unbekannt`, or `Verwerfen`.
6. Each action posts the updated field state to the RWDR brief endpoint.
7. Backend Evidence Gate decides whether the field may enter confirmed facts.
8. Missing critical fields, questions and measurement hints are shown from the backend brief sections.
9. The user can trigger `Technical RWDR RFQ Brief erstellen`.
10. The generated brief can be copied as markdown/text from the brief panel.

## API Contracts Added

- `POST /api/v1/rfq/rwdr/analyze`
  - Input: `{ "raw_inquiry": string }`
  - Output: candidate fields plus preliminary `Technical RWDR RFQ Brief`.

- `POST /api/v1/rfq/rwdr/brief`
  - Input: `{ "raw_inquiry": string, "fields": EvidenceFieldLike[] }`
  - Output: backend-generated `Technical RWDR RFQ Brief`.

BFF routes mirror these endpoints under:

- `/api/bff/rfq/rwdr/analyze`
- `/api/bff/rfq/rwdr/brief`

## Files Changed

- `backend/app/services/rwdr_mvp_brief.py`
- `backend/app/api/v1/endpoints/rfq.py`
- `backend/app/api/tests/test_rfq_endpoint.py`
- `backend/tests/unit/services/test_rwdr_mvp_brief.py`
- `frontend/src/lib/bff/workspace.ts`
- `frontend/src/app/api/bff/rfq/rwdr/analyze/route.ts`
- `frontend/src/app/api/bff/rfq/rwdr/brief/route.ts`
- `frontend/src/components/dashboard/RfqPane.tsx`
- `frontend/src/components/dashboard/RfqPane.test.tsx`
- `docs/audits/sealingai-engine/13_rwdr_confirmation_ux_report.md`

## Tests Added

Backend:

- Analyze endpoint returns candidates with source spans and unconfirmed state.
- Brief endpoint honors confirmation payload.
- Confirmed extracted field enters confirmed facts with source span.
- Unconfirmed LLM field stays out of confirmed facts.
- `explicitly_unknown` does not become a confirmed fact.
- Same confirmed input produces deterministic brief sections.

Frontend:

- Source-span candidate shows Confirm/Edit/Unknown/Reject.
- Confirm action sends `confirmation_status=confirmed` and preserves `source_span`.
- Missing source-span field shows uncertainty warning.
- Edit action sends edited value and `edited_by_user`.
- Unknown action sends `explicitly_unknown`.
- Reject action sends `rejected`.
- RWDR flow does not render Partner-Fit / matching copy.

## Commands Run

- `PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/services/rwdr_mvp_brief.py backend/app/api/v1/endpoints/rfq.py`
- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rfq_endpoint.py`
- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py`
- `npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts`
- `git diff --check`
- `rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution" backend frontend docs`

## Test Results

- Backend RWDR/API focused: passed, `29 passed`.
- Backend RWDR/RFQ/API focused: passed, `65 passed`.
- Frontend focused: passed, `3 files / 14 tests passed`.
- `git diff --check`: passed.

## Forbidden-Language Scan

The repository-wide scan still reports legacy tests, guards, prompts, knowledge JSON and the forbidden-language documentation itself. The RWDR confirmation UI, RWDR BFF routes, RWDR backend endpoints and touched customer-facing RWDR surfaces do not introduce positive recommendation or final-decision language.

## Remaining Limitations

- Extraction is deterministic MVP extraction, not a production LLM adapter.
- Confirmation state is held in the frontend flow and submitted to the backend brief endpoint; durable persistence of per-field confirmations into case state remains future work.
- Existing case-based RFQ preview remains separate from the paste-based RWDR confirmation flow.
- Existing PDF export remains tied to persisted RFQ previews; the local confirmation flow provides text/markdown copy.

## Next Recommended Patch

Persist RWDR confirmation decisions into backend case state, then let the case-based RFQ preview/export flow reuse the same confirmed EvidenceFields without re-entering them locally.
