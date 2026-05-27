# RWDR Case Snapshots & Recovery Report

Date: 2026-05-27

## Scope

This patch adds revision snapshots for backend-owned RWDR case state and improves frontend recovery by persisted `case_id`.

The RWDR MVP boundary remains unchanged:

- No manufacturer marketplace.
- No manufacturer routing.
- No paid listings.
- No material, product, manufacturer, or final design recommendation.
- No final technical release claim.
- Backend Evidence Gate remains authoritative.

## Files changed

- `backend/app/services/rwdr_mvp_brief.py`
  - Uses the existing `case_state_snapshots` model for RWDR case-state revision history.
  - Writes append-only snapshots for important RWDR mutations.
  - Adds deterministic snapshot payload/hash generation excluding audit metadata.
  - Adds snapshot list/detail repository functions.
  - Adds export revision metadata for Markdown and PDF exports.

- `backend/app/api/v1/endpoints/rfq.py`
  - Adds RWDR snapshot list/detail endpoints.

- `backend/app/api/tests/test_rfq_endpoint.py`
  - Extends fake RWDR session with snapshot storage.
  - Adds assertions for snapshot events, monotonic revisions, and export snapshot retrieval.

- `frontend/src/lib/bff/workspace.ts`
  - Adds BFF/backend path builders for RWDR snapshot retrieval.

- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/snapshots/route.ts`
  - Adds BFF proxy for RWDR snapshot list retrieval.

- `frontend/src/components/dashboard/RfqPane.tsx`
  - Restores RWDR cases from URL `rwdr_case_id` or recent localStorage case reference.
  - Stores only `sealai_rwdr_case_id` in localStorage, not authoritative EvidenceFields.
  - Fetches backend case state and snapshot summaries.
  - Shows subtle RWDR case reference and a compact revision list.

- `frontend/src/components/dashboard/RfqPane.test.tsx`
  - Adds recovery assertions for URL case ID, backend restoration, localStorage behavior, and revision rendering.
  - Updates confirmation test to account for snapshot fetches.

## Snapshot approach

The implementation reuses the existing `case_state_snapshots` table/model:

- `CaseRecord.payload` remains the current RWDR case-state projection.
- `case_state_snapshots` stores append-only revision history.
- No new table or migration was required.

Repository path:

- `DbRWDRCaseStateRepository` writes current state to `CaseRecord.payload`.
- The same repository writes a `CaseStateSnapshot` after each tracked mutation.

Snapshot creation is performed in the same repository operation before commit where practical, so current-state update and snapshot append are committed together by the endpoint.

## Snapshot payload shape

Each RWDR snapshot stores `CaseStateSnapshot.state_json` with:

- `snapshot_id`
- `case_id`
- `revision_number`
- `previous_revision_number`
- `event_type`
- `schema_version`
- `rule_version`
- `extraction_version`
- `deterministic_payload_hash`
- `deterministic_payload_json`
- `snapshot_payload`
- `created_at`
- `created_by`
- `export_reference`

`snapshot_payload` contains the current RWDR case-state projection, including:

- raw inquiry text
- EvidenceFields and confirmation statuses
- missing critical/helpful fields
- computed values
- review flags
- manufacturer questions
- measurement recommendations
- source evidence summary
- evaluation status
- generated Technical RWDR RFQ Brief if present
- export content/metadata if present

## Determinism

The deterministic snapshot payload excludes audit-only fields before hashing:

- `created_at`
- `updated_at`
- `user_action_timestamp`

These fields do not influence status, missing fields, computed values, question ordering, review flags, or deterministic payload hash.

## Snapshot events

Snapshots are now created for:

- `case_created_after_analyze`
- `extraction_candidates_stored`
- `confirmation_decision_applied`
- `evidence_field_edited`
- `field_marked_explicitly_unknown`
- `field_rejected`
- `evaluation_generated`
- `technical_brief_generated`
- `markdown_export_generated`
- `pdf_export_generated`

Revision numbers are monotonic per case and append-only.

## API changes

Added:

- `GET /api/v1/rfq/rwdr/cases/{case_id}/snapshots`
  - Returns snapshot summaries.

- `GET /api/v1/rfq/rwdr/cases/{case_id}/snapshots/{revision_number}`
  - Returns a specific snapshot payload.

Existing RWDR endpoints continue to use DB-backed case state:

- `POST /api/v1/rfq/rwdr/analyze`
- `GET /api/v1/rfq/rwdr/cases/{case_id}`
- `POST /api/v1/rfq/rwdr/cases/{case_id}/confirmations`
- `POST /api/v1/rfq/rwdr/cases/{case_id}/evaluate`
- `POST /api/v1/rfq/rwdr/cases/{case_id}/brief`
- `GET /api/v1/rfq/rwdr/cases/{case_id}/export.md`
- `GET /api/v1/rfq/rwdr/cases/{case_id}/export.pdf`

## Frontend recovery behavior

The RWDR pane now:

- writes the backend `case_id` to the URL query parameter `rwdr_case_id` after analyze/restore;
- stores only the recent `sealai_rwdr_case_id` in localStorage;
- on page load, prefers the URL `rwdr_case_id`, then falls back to localStorage;
- fetches the backend case by `case_id`;
- restores EvidenceFields, confirmation statuses, brief state, export content, and snapshot summaries from backend state;
- renders a subtle `RWDR Case: <short id>` marker;
- shows `aus Backend wiederhergestellt` after recovery;
- shows a compact `Versionsverlauf` with recent revision events.

localStorage is convenience-only and is not an authoritative evidence source.

## Export integration

Markdown export:

- Uses the persisted backend RWDR case state.
- Writes `markdown_export_generated`.
- Returns export metadata with `case_id`, `revision_number`, and `export_format`.

PDF export:

- Uses the persisted backend RWDR Technical RWDR RFQ Brief.
- Writes `pdf_export_generated`.
- Returns PDF bytes through the existing PDF renderer path.
- Export metadata references `case_id` and snapshot revision.

## Tests added or updated

Backend:

- Snapshot list is created after analyze.
- Confirmation decisions create revision snapshots.
- Explicit unknown creates a dedicated snapshot.
- Evaluation and brief generation create snapshots.
- Markdown and PDF export create export snapshots.
- Revision numbers are monotonic.
- Specific snapshot retrieval returns persisted EvidenceFields.

Frontend:

- Recovery by URL `rwdr_case_id`.
- Backend state restoration of confirmation statuses.
- localStorage stores only case ID.
- Revision panel rendering.
- Confirmation test updated for snapshot fetches.

## Commands run

```bash
pwd
git status --short
git branch --show-current
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rfq_endpoint.py
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py
PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/services/rwdr_mvp_brief.py backend/app/api/v1/endpoints/rfq.py backend/app/api/v1/renderers/rfq_pdf.py
git diff --check
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer" backend frontend docs
```

## Test results

Green:

- `backend/app/api/tests/test_rfq_endpoint.py`: 13 passed
- Focused backend RWDR/RFQ suite: 72 passed
- Focused frontend suite: 16 passed
- Python compile check: passed
- `git diff --check`: passed
- Forbidden-language search: 406 hits, classified as tests/guards/prompt controls, legacy docs, knowledge data, non-RWDR legacy surfaces, and allowed negating/disclaimer context. No new RWDR confirmation/snapshot customer-facing surface introduced manufacturer matching, material/product recommendation, or final-release wording.

Known warning:

- `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning in endpoint test. This is unrelated to RWDR snapshot behavior.

## Known limitations

- EvidenceField history is revisioned as JSON snapshots, not relational child rows.
- Snapshot diff endpoint is not implemented.
- PDF export remains basic, although it is now generated from persisted backend state.
- Broad forbidden-language repository search remains noisy because legacy docs/tests/prompts contain prohibited terms for tests, guards, and historical context.
- Frontend recovery is implemented in `RfqPane`; a dedicated case-history page is not implemented.

## Next recommended patch

Add a snapshot diff endpoint and UI affordance for comparing two revisions at field level:

- field value changes
- confirmation status changes
- missing-field changes
- brief/export revision references

Keep the diff read-only and backed by persisted `case_state_snapshots`.
